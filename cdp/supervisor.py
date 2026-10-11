"""Phase 5 (M5.2/M5.3) -- the task state machine and `cdp run`'s wave loop.

    pending -> dispatched -> returned -> validated -> folded
                  |             |           |
                  +-- expired --+-- invalid-+-- anchors_failed -- empty
                                       |
                                    retry (up to MAX_ATTEMPTS) -> abandoned

Each failure has a different remedy, and conflating them is why failures were
undiagnosable before this milestone (`phase_5_plan.md` M5.2):

    invalid          the patch violates the schema -- fix the value.
    anchors_failed   every claim's anchor was fabricated or the file moved.
    empty            yield collapse -- a well-formed patch with nothing in it.
    expired          the task did not return in time, whether the runner
                     crashed, timed out, or (once M5.4 exists) the supervisor
                     itself died -- the cause lives in `last_error`; the
                     remedy (redispatch) is the same for all three, so one
                     state covers them rather than inventing a fourth category
                     the plan's vocabulary does not name.

`snapshot_task` (`store/sqlite_backend.py`) is where every transition is
recorded, keyed by `(run_id, scope_hash)` -- ephemeral supervisor bookkeeping,
distinct from the immutable patch log. Only the *terminal* outcome of a
scope's retry loop touches the log: a success appends a `complete` patch (the
same shape `cmd_collect` already writes), an exhausted retry loop appends a
`status: "failed"` patch with no claims -- `state.fold`'s existing superseded-
node handling (`cdp/state.py:178-197`) then synthesises the "not successfully
examined" unknown from that alone (R6), so this module needs no new fold-side
code to keep a failed scope from being a silent gap.
"""

from __future__ import annotations

import datetime
import threading
from concurrent.futures import ThreadPoolExecutor

from . import claimgate as claimgate_mod, entail as entail_mod, rereview as rereview_mod, freshness as freshness_mod, gates as gates_mod, query as query_mod, reflect as reflect_mod, trajectory as trajectory_mod
from .prompts import build_prompt
from .lock import repo_lock
from .runner import read_usage
from .schema import Validator, schema_path, validate_patch
from .session import Paths, check_repo_matches_manifest, fold_and_write, next_generation, next_run_id, open_store, resolve_backend, stamp_claims
from .store import registry as registry_mod
from .util import CdpError, SKILL_ROOT, git_head, read_json, stable_hash, write_text
from .verify import FileCache, LENIENT, STRICT, verify_patch
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Set


PENDING = "pending"
DISPATCHED = "dispatched"
RETURNED = "returned"
VALIDATED = "validated"
FOLDED = "folded"

EXPIRED = "expired"
INVALID = "invalid"
ANCHORS_FAILED = "anchors_failed"
EMPTY = "empty"
ABANDONED = "abandoned"

#: States that are candidates for another attempt, up to `MAX_ATTEMPTS`.
RETRY_STATES = frozenset([EXPIRED, INVALID, ANCHORS_FAILED, EMPTY])

#: 4.7 names this the CLI's `--max-attempts` default; the flag itself is
#: M5.5 -- this session hardcodes the default it will read from.
MAX_ATTEMPTS = 3

#: M5.4 (4.5): held by the supervisor, not the leaf -- a leaf on a slow
#: frontier model never sees these numbers, which is what keeps the runner
#: protocol text-in/JSON-out. A dead supervisor is detected within
#: `LEASE_SECONDS` regardless of which tier's runner it was driving. Until
#: Phase 9's star exists there is no per-`dim_tier` p99 to derive this from
#: (`phase_5_plan.md` M5.4 says so explicitly) -- v1 ships this conservative
#: constant and records `wall_ms` per task from day one so a future ceiling
#: has real data to replace it with, rather than another guess.
LEASE_SECONDS = 90
HEARTBEAT_SECONDS = 30


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


class _LeaseHeartbeat:
    """Renews one task's lease every `interval` seconds for as long as a
    runner call is in flight, via `heartbeat_fn` (a zero-arg callable the
    caller closes over its own `backend.heartbeat_lease`/`heartbeat_link_lease`
    call -- generalised, post-Phase-9 item 5, so `link.dispatch_link_task` can
    reuse this class against `link_task`'s lease instead of duplicating it).
    Runs in a background thread because the main thread is blocked inside
    `runner.run()` -- there is no between-calls point to renew from. If the
    process dies, this thread dies with it and the lease simply expires; that
    is the entire death-detection mechanism, not a special case of it."""

    def __init__(self, heartbeat_fn, interval: float) -> None:
        self._heartbeat_fn = heartbeat_fn
        self._interval = interval
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, daemon=True)

    def start(self) -> "_LeaseHeartbeat":
        self._thread.start()
        return self

    def _loop(self) -> None:
        while not self._stop.wait(self._interval):
            self._heartbeat_fn()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=self._interval + 1)


def dispatch_scope(
    scope: Dict,
    inventory: Dict,
    extraction: Optional[Dict],
    xref: Dict,
    sched: Dict,
    prior_claims: Sequence[Dict],
    run_id: str,
    runner,
    backend,
    prompts_dir: Path,
    validator: Validator,
    repo: Path,
    mode: str = STRICT,
    lease_seconds: float = LEASE_SECONDS,
    heartbeat_seconds: float = HEARTBEAT_SECONDS,
    max_attempts: int = MAX_ATTEMPTS,
    lesson_hints: Optional[Dict] = None,
    plan: Optional["rereview_mod.Plan"] = None,
) -> Optional[Dict]:
    """Run one scope through the retry loop to a terminal state.

    Returns `{"node", "scope_hash", "state", "attempts", "last_error",
    "patch"}` -- `patch` is the accepted patch dict only when `state ==
    VALIDATED` (the caller appends it to the log and folds; this function
    never touches the log itself, so a wave's fold stays one call, not one
    per scope). Returns `None` if another supervisor already holds this
    scope's lease -- not this process' scope to dispatch right now, not a
    failure of it.
    """
    node = scope["node"]
    scope_hash = scope.get("scope_hash") or node
    hints = lesson_hints or {}
    prompt_kwargs = {}
    if hints.get("max_inherited") is not None:
        prompt_kwargs["max_inherited"] = hints["max_inherited"]
    text, prompt_stats = build_prompt(
        scope, inventory, extraction, xref, sched, prior_claims, run_id,
        extra_third_party=hints.get("third_party_patterns", frozenset()),
        prompt_fixes=hints.get("prompt_fixes", ()), inbox_dir=backend._inbox_dir(),
        rereview=plan.as_prompt() if plan is not None else None, **prompt_kwargs
    )
    prompt_path = prompts_dir / (node.replace("/", "__") + ".md")
    write_text(prompt_path, text)
    patch_path = backend._inbox_dir() / (node.replace("/", "__") + ".json")

    ctx = claimgate_mod.Context(scope, {n for w in sched["waves"] for n in w["nodes"]},
                                inventory, extraction, xref, node, repo)
    state = PENDING
    last_error: Optional[str] = None
    patch: Optional[Dict] = None
    attempt = 0
    spent: Dict = {"wall_ms": 0}  # across attempts: time, and cost when the runner reports it (L14)
    for attempt in range(1, max_attempts + 1):
        if not backend.acquire_lease(run_id, scope_hash, lease_seconds):
            return None
        backend.reject_inbox(patch_path.name)  # a leftover is never this attempt's output
        backend.upsert_task(
            run_id, scope_hash, state=DISPATCHED, attempts=attempt,
            dispatched_at=_now(), last_error=None,
        )
        heartbeat = _LeaseHeartbeat(
            lambda: backend.heartbeat_lease(run_id, scope_hash, lease_seconds), heartbeat_seconds
        ).start()
        try:
            result = runner.run(prompt_path, patch_path)
        finally:
            heartbeat.stop()
        spent["wall_ms"] += result.wall_ms or 0
        for key, value in read_usage(patch_path).items():
            spent[key] = (spent.get(key) or 0) + value
        if not result.ok:
            state, last_error, patch = EXPIRED, result.error or "runner reported failure with no message", None
        else:
            backend.upsert_task(run_id, scope_hash, state=RETURNED, wall_ms=result.wall_ms)
            state, last_error, patch = _classify_returned(patch_path, node, validator, repo, mode, ctx)
        backend.upsert_task(run_id, scope_hash, state=state, last_error=last_error, wall_ms=result.wall_ms)
        if state != VALIDATED:
            backend.reject_inbox(patch_path.name)  # out of the inbox: a later `collect` must not take it
        backend.release_lease(run_id, scope_hash)
        if state not in RETRY_STATES:
            break
    if state in RETRY_STATES:
        state = ABANDONED
        backend.upsert_task(run_id, scope_hash, state=state, last_error=last_error)
        patch = None
    return {
        "node": node, "scope_hash": scope_hash, "state": state,
        "attempts": attempt, "last_error": last_error, "patch": patch,
        "prompt_stats": prompt_stats, "rereview": plan.marker() if plan is not None else None, **spent,
    }


def run_wave(
    nodes: Sequence[str], store, backend, runner, paths, run_id: str,
    validator: Validator, sched: Dict, mode: str = STRICT,
    lease_seconds: float = LEASE_SECONDS, heartbeat_seconds: float = HEARTBEAT_SECONDS,
    max_attempts: int = MAX_ATTEMPTS, skip_hashes=frozenset(),
    lesson_hints: Optional[Dict] = None, parallel: int = 1,
    progress: Optional[Callable[[Dict], None]] = None,
    plans: Optional[Dict[str, "rereview_mod.Plan"]] = None,
) -> List[Dict]:
    """Dispatch every scope named in `nodes`, sequentially within this
    process -- M5.4's atomic lease acquisition is what makes it safe for a
    *second* `cdp run` process to dispatch the same wave concurrently (each
    scope is claimed by exactly one of them); until a real concurrent driver
    exists, one process working the list in order is behaviourally identical
    to M5.3's own acceptance comparison (SKILL.md's manual loop, same scopes,
    same template version). A scope another live supervisor already holds the
    lease for is dropped from the results, not reported as any task state --
    it is that other process' outcome to report. `store` is re-read fresh by
    the caller between waves so `prior_claims` here reflects the previous
    wave's fold.

    `skip_hashes` (M5.5, `--resume`): scope hashes the caller has already
    determined are `folded` -- for this run (unchanged partition) or inherited
    from a superseded one (partition changed, scope content did not). Neither
    dispatched nor reported here, which is what keeps a folded scope "untouched
    and unpaid-for again" rather than silently re-billed on every resume."""
    prompts_dir = paths.work / "prompts"
    prompts_dir.mkdir(parents=True, exist_ok=True)
    backend.ensure_inbox()
    prior = list(store.state.get("claims", []))
    node_set = set(nodes)
    plans = plans or {}
    todo = [s for s in store.partition["scopes"]
            if s["node"] in node_set and s.get("scope_hash") not in skip_hashes
            and not (s["node"] in plans and plans[s["node"]].empty)]  # reviewed, nothing stale: nothing to send
    workers = max(1, min(int(parallel or 1), len(todo)))

    def dispatch(scope: Dict) -> Optional[Dict]:
        row = dispatch_scope(
            scope, store.inventory, store.extraction, store.xref, sched, prior,
            run_id, runner, backend, prompts_dir, validator, paths.repo, mode,
            lease_seconds, heartbeat_seconds, max_attempts, lesson_hints, plans.get(scope["node"]),
        )
        if row is not None and progress is not None:
            progress(row)
        return row

    if workers == 1:
        rows = [dispatch(scope) for scope in todo]
    else:
        # Scopes of one wave do not depend on each other (the schedule's waves
        # are dependency levels), so they run together. Results keep partition
        # order, so the fold does not depend on which finished first.
        with ThreadPoolExecutor(max_workers=workers) as pool:
            rows = [f.result() for f in [pool.submit(dispatch, scope) for scope in todo]]
    return [row for row in rows if row is not None]


def mark_folded(backend, run_id: str, results: Sequence[Dict]) -> None:
    """Bump every `VALIDATED` scope from this wave to the terminal `FOLDED`
    state, once the wave-level fold that consumed its patch has succeeded."""
    for row in results:
        if row["state"] == VALIDATED:
            backend.upsert_task(run_id, row["scope_hash"], state=FOLDED)


def _classify_returned(patch_path: Path, node: str, validator: Validator, repo: Path, mode: str,
                       ctx: Optional["claimgate_mod.Context"] = None):
    """The runner returned `ok=True` -- classify what it left behind into
    `(state, last_error, patch_or_None)`."""
    if not patch_path.exists():
        return EMPTY, "runner returned ok but wrote no patch", None
    try:
        patch = read_json(patch_path)
    except (ValueError, OSError) as exc:
        return INVALID, "not valid JSON: %s" % exc, None
    if not isinstance(patch, dict):
        return INVALID, "a patch is a JSON object, got %s" % type(patch).__name__, None
    if ctx is not None:
        had_claims = bool(patch.get("claims"))
        patch, dropped = claimgate_mod.screen_claims(patch, validator, ctx)
        if had_claims and not patch["claims"] and not patch.get("unknowns"):
            return INVALID, "every claim was rejected (%s)" % "; ".join(
                "%s: %s" % (d["id"], d["reasons"][0]) for d in dropped[:3]), None
    errors = validate_patch(patch, validator)
    if str(patch.get("node", "")) != node:
        errors.append("/node: %r does not match dispatched scope %r" % (patch.get("node"), node))
    if errors:
        return INVALID, "; ".join(errors[:6]), None
    claims = patch.get("claims") or []
    unknowns = patch.get("unknowns") or []
    if not claims and not unknowns:
        return EMPTY, "well-formed patch with zero claims and zero unknowns", None
    if claims:
        cache = FileCache(repo)
        _verified, stats = verify_patch(dict(patch), cache, mode, git_head(Path(repo)))
        if stats["claims_kept"] == 0:
            reasons = ", ".join("%s %d" % kv for kv in stats["reasons"].items()) or "no anchor survived"
            return ANCHORS_FAILED, "every claim's anchor failed (%s)" % reasons, None
    return VALIDATED, None, patch


def apply_wave_results(backend, store, results: List[Dict], run_id: str, mode: str, paths: "Paths",
                         trajectory: Optional["trajectory_mod.TrajectoryStore"] = None,
                         repo_id: Optional[str] = None, model: Optional[str] = None,
                         rejected_unknowns: Optional[List[Dict]] = None) -> Dict:
    """The terminal outcome of one wave: append a `complete` patch for every
    scope that validated, a `status: failed` patch (no claims) for every one
    abandoned -- `state.fold`'s existing superseded-node handling turns the
    latter into an honest unknown (R6) with no further code here -- then one
    fold for the whole wave, and bump `validated` tasks to `folded`."""
    log_so_far = backend.load_patches()
    def_fqns, edge_subjects, edges_by_key = gates_mod.build_extraction_index(store.extraction)
    scope_nodes = {s["node"] for s in store.partition["scopes"]}
    node_to_hash = {s["node"]: s.get("scope_hash") for s in store.partition["scopes"]}
    node_to_scope = {s["node"]: s for s in store.partition["scopes"]}
    task_rows = backend.task_states(run_id)
    tiering_report = backend.read_report("tiering", {}).get("tiering", {})
    for row in results:
        node = row["node"]
        claims_emitted = unknowns_emitted = None
        entailed = consistent = contradicted = elision_regret = None
        if row["state"] == VALIDATED and row["patch"] is not None:
            patch = dict(row["patch"])
            patch["node"] = node
            patch["run_id"] = run_id
            patch["status"] = "complete"
            patch.setdefault("author_kind", "llm")
            if mode == LENIENT:
                patch["verify_mode"] = LENIENT
            if row.get("rereview"):  # a partial re-review: the live claims it did not resend stay
                rereview_mod.carry_forward(patch, node, row["rereview"]["carry"], log_so_far)
            patch["generation"] = next_generation(log_so_far, node)
            log_so_far.append(patch)
            stamp_claims(patch.get("claims") or [], store.inventory["head"])
            kept, rejected = gates_mod.gate_patch_unknowns(
                patch.get("unknowns") or [], node, def_fqns, edge_subjects, edges_by_key,
                scope_nodes, {node: task_rows.get(node_to_hash.get(node))},
            )
            patch["unknowns"] = kept
            if rejected_unknowns is not None:
                rejected_unknowns.extend(rejected)
            backend.append_patch(patch, node)
            backend.clear_inbox(node)
            claims_emitted = len(patch.get("claims") or [])
            unknowns_emitted = len(kept)
            # M9.2 (6.3): output scorecard -- entailment split on this leaf's
            # own emitted claims, against the same extraction the leaf saw.
            verdicts = [c.get("verdict") for c in entail_mod.entail_claims(patch.get("claims") or [], store.extraction)]
            entailed = verdicts.count(entail_mod.ENTAILED)
            consistent = verdicts.count(entail_mod.CONSISTENT)
            contradicted = verdicts.count(entail_mod.CONTRADICTED)
            # M9.2 (6.4): elision regret -- did this leaf emit an unknown
            # about a subject the digest budget had already elided as a
            # prior claim? That is the concrete "was the answer in a row the
            # budget elided" question `prompts.py`'s ranking function needs
            # graded against.
            elided_subjects = (row.get("prompt_stats") or {}).get("elided_subjects") or []
            unknown_subjects = [str(u.get("subject", "")) for u in kept]
            elision_regret = trajectory_mod.elision_regret(elided_subjects, unknown_subjects)
        elif row["state"] == ABANDONED:
            backend.append_patch(
                {"schema_version": "1.0.0", "node": node, "run_id": run_id, "status": "failed",
                 "error": row["last_error"] or "abandoned after %d attempts" % row["attempts"]},
                node + "-abandoned",
            )
        if trajectory is not None and repo_id is not None:
            scope = node_to_scope.get(node, {})
            prompt_stats = row.get("prompt_stats") or {}
            trajectory.record_leaf_run(
                run_id=run_id, node=node, scope_hash=node_to_hash.get(node), repo_id=repo_id,
                model=model, scope_shape_key=trajectory_mod.scope_shape_key(scope),
                template_version=None, tier=tiering_report.get(node, {}).get("tier"),
                task_kind="scope", state=row["state"], attempts=row.get("attempts"),
                wall_ms=row.get("wall_ms"), cost_usd=row.get("cost_usd"),
                tokens_in=row.get("tokens_in"), tokens_out=row.get("tokens_out"),
                claims_emitted=claims_emitted, unknowns_emitted=unknowns_emitted,
                rows_elided=prompt_stats.get("elided_claims"), tokens_est=prompt_stats.get("tokens_est"),
                digest_mode=prompt_stats.get("digest_mode"), entailed=entailed,
                consistent=consistent, contradicted=contradicted, elision_regret=elision_regret,
                sigma_claims=prompt_stats.get("sigma_claims"),
            )
    folded = fold_and_write(backend, store.xref, store.partition, repo=paths.repo, mode=mode)
    mark_folded(backend, run_id, results)
    return folded


def stale_nodes(store: "query_mod.Store", repo: Path) -> List[str]:
    """Scopes `--stale-only` re-reviews: a scope a leaf reviewed before is stale when it has a
    claim to re-check or a new file (`rereview.plan_scope`); any other scope is stale when it owns
    a non-`live` claim (M3.1's freshness bucket)."""
    head = store.inventory.get("head")
    if not head or head == "unpinned":
        return []
    cache: freshness_mod.ChurnCache = {}
    scopes = freshness_mod.scope_paths(store.partition)
    plans = rereview_mod.plans_for(store, repo, [s["node"] for s in store.partition["scopes"]])
    nodes = {n for n, p in plans.items() if not p.empty}
    for claim in store.state.get("claims", []):
        owners = claim.get("source_nodes") or ([claim["source_node"]] if claim.get("source_node") else [])
        if all(o in plans for o in owners):
            continue
        if freshness_mod.claim_bucket(claim, repo, head, cache, store=store.backend, scopes=scopes) != freshness_mod.LIVE:
            nodes.update(o for o in owners if o not in plans)
    return sorted(nodes)


def lessons_hint(trajectory: "trajectory_mod.TrajectoryStore") -> Optional[str]:
    """Every `LESSONS_HINT_EVERY` finished runs (global, cross-repo cadence,
    per the user's own decision -- cutting itself stays manual), the message
    that pending promotions exist and the exact command to freeze them.
    None off-cadence, or when nothing is pending."""
    count = trajectory.finished_run_count()
    if count % trajectory_mod.LESSONS_HINT_EVERY != 0:
        return None
    pending = trajectory.pending_promotion_count()
    if pending == 0:
        return None
    return ("lessons   %d promotion(s) pending after %d runs -- `cdp lessons cut` to freeze them"
            % (pending, count))


def run_waves(
    paths: Paths,
    runner,
    *,
    runner_cmd: Optional[str],
    timeout: float,
    mode: str,
    max_attempts: int,
    resume: bool,
    lessons: Optional[int],
    no_lessons: bool,
    stale_only: bool,
    scope: Optional[str],
    wave: Optional[int],
    say: Callable[..., None],
    parallel: int = 1,
) -> Dict:
    """M5.3: `read schedule -> dispatch a wave -> collect -> adjudicate ->
    fold -> next wave`. `prompts`/`collect` still work standalone (M5.1's
    protocol doc); this drives them through this module's state machine
    (M5.2) instead of a human running the loop from `SKILL.md`.

    `--resume` (M5.5, 4.6): `runs.partition_hash` (a `stable_hash` of every
    scope's `(node, scope_hash)`, computed fresh from *this* invocation's
    partition) decides which of two things happened since the run named by
    `manifest.run_id` last touched this store:

      unchanged  -- the same run continues. Any task still `dispatched` past
                    its lease is reclaimed as `expired` (the supervisor that
                    held it is presumed dead) and re-attempted; `folded` tasks
                    are left alone -- untouched and unpaid-for again.
      differs    -- a file changed the partition since this run started
                    (Phase 3's open interaction: a `refresh` landing mid-run).
                    Folding stale work against a changed partition is exactly
                    what R6/the merge operator must not do, so this opens a
                    *new* run (`<run_id>-rN`) rather than continuing the old
                    one, inheriting every scope whose own `scope_hash` did not
                    move (nothing to redo) and re-queuing the rest.

    Without `--resume`, a second invocation behaves as before M5.5: it
    reuses the existing run row (`begin_run` is idempotent) and redispatches
    everything asked for, from a fresh `--max-attempts` budget -- correct, but
    not resume-aware.
    """

    backend = open_store(paths, durable=True)
    if not backend.supports_run_tracking():
        raise CdpError(
            "%s has no run/task tracking -- `cdp run` needs the sqlite or "
            "postgres backend" % type(backend).__name__
        )
    store = query_mod.Store(backend)
    check_repo_matches_manifest(paths, store.manifest)
    sched = store._load("schedule")
    run_id = str(store.manifest.get("run_id", "cdp"))
    validator = Validator.load(schema_path(SKILL_ROOT))
    if parallel > 1:
        say("run       up to %d scope(s) at a time within each wave (--parallel)" % parallel)
    if not runner_cmd:
        say("run       no --runner-cmd given -- waiting for a human/external "
              "process to drop the patch file (FileRunner, timeout %ss)" % timeout)

    partition_hash = stable_hash(
        sorted((s["node"], s.get("scope_hash")) for s in store.partition["scopes"])
    )
    skip_hashes: Set[str] = set()
    partition_changed = False
    existing = backend.get_run(run_id)
    if existing is None:
        backend.begin_run(run_id, partition_hash)
    elif not resume:
        backend.begin_run(run_id, partition_hash)  # idempotent no-op; pre-M5.5 behaviour
    elif existing["partition_hash"] == partition_hash:
        reclaimed = backend.reclaim_expired(run_id, force=True)  # we hold the repo lock: no live owner
        if reclaimed:
            say("resume    run %s: partition unchanged, reclaimed %d task(s) left dispatched by a dead run"
                  % (run_id, len(reclaimed)))
        skip_hashes = {sh for sh, row in backend.task_states(run_id).items() if row["state"] == "folded"}
    else:
        old_run_id = run_id
        partition_changed = True
        old_folded = {sh for sh, row in backend.task_states(old_run_id).items() if row["state"] == "folded"}
        new_hashes = {s.get("scope_hash") for s in store.partition["scopes"]}
        unchanged = old_folded & new_hashes
        run_id = next_run_id(backend, old_run_id)
        backend.begin_run(run_id, partition_hash)
        backend.copy_folded_tasks(old_run_id, run_id, unchanged)
        skip_hashes = set(unchanged)
        say("resume    partition changed since run %s -- opened new run %s, "
              "inherited %d unchanged scope(s), %d re-queued"
              % (old_run_id, run_id, len(unchanged), len(new_hashes) - len(unchanged)))

    repo_id = registry_mod.repo_identity(paths.repo)
    model = (runner_cmd.split()[0] if runner_cmd else "human")
    trajectory = trajectory_mod.TrajectoryStore()
    trajectory.record_run_event(run_id=run_id, repo_id=repo_id, event="started")

    if no_lessons:
        lessons_version = None
    elif lessons is not None:
        lessons_version = lessons
    else:
        lessons_version = trajectory.latest_lesson_version(repo_id)  # None until a cut applies to this repo (6.7)
    backend.set_run_lessons_version(run_id, lessons_version)
    lesson_hints: Dict = {}
    if lessons_version is not None:
        lesson_hints = reflect_mod.apply_lessons(trajectory.load_lessons(lessons_version))
        say("lessons   pinned v%d" % lessons_version)

    if stale_only:
        stale = stale_nodes(store, paths.repo)
        if not stale:
            say("stale-only  zero scopes need review")
            backend.finish_run(run_id, "complete")
            trajectory.record_run_event(run_id=run_id, repo_id=repo_id, event="finished", reason="complete")
            hint = lessons_hint(trajectory)
            trajectory.close()
            backend.close()
            return {"run_id": run_id, "any_incomplete": False, "nothing_stale": True, "hint": hint,
                    "tasks": {}, "rejected_unknowns": []}
        wave_groups = [("stale", stale)]
    elif scope:
        if scope not in {s["node"] for s in store.partition["scopes"]}:
            raise CdpError("%r is not a scope in partition.json" % scope)
        wave_groups = [("scope", [scope])]
    elif wave is not None:
        found = next((w for w in sched["waves"] if w["wave"] == wave), None)
        if found is None:
            raise CdpError("no wave %d (schedule has %d)" % (wave, len(sched["waves"])))
        wave_groups = [(wave, found["nodes"])]
    else:  # --wave-all
        wave_groups = [(w["wave"], w["nodes"]) for w in sched["waves"]]

    backend.write_report("rereview", {})  # `run` carries claims itself; no `prompts` marker may outlive it
    plans: Dict[str, rereview_mod.Plan] = {}
    if stale_only or partition_changed:  # C2: a scope a leaf reviewed before gets only what changed
        plans = rereview_mod.plans_for(store, paths.repo, [n for _label, ns in wave_groups for n in ns])
        quiet = sorted(n for n, p in plans.items() if p.empty)
        if quiet:
            say("rereview  %d scope(s) changed but hold no stale claim and no new file: not re-sent" % len(quiet))
    any_incomplete = False
    totals: Dict[str, int] = {}
    rejected_unknowns: List[Dict] = []
    for label, nodes in wave_groups:
        results = run_wave(
            nodes, store, backend, runner, paths, run_id, validator, sched, mode,
            max_attempts=max_attempts, skip_hashes=skip_hashes, lesson_hints=lesson_hints,
            parallel=parallel, plans=plans,
            progress=lambda row: say("  done      %-9s %s" % (row["state"], row["node"])),
        )
        with repo_lock(paths, *resolve_backend(paths.state), shared=False):  # held per write, not per run
            apply_wave_results(backend, store, results, run_id, mode, paths,
                               trajectory=trajectory, repo_id=repo_id, model=model,
                               rejected_unknowns=rejected_unknowns)
        counts: Dict[str, int] = {}
        for row in results:
            counts[row["state"]] = counts.get(row["state"], 0) + 1
            totals[row["state"]] = totals.get(row["state"], 0) + 1
        say("wave %-6s %2d scope(s)  %s" % (label, len(results),
              ", ".join("%s %d" % kv for kv in sorted(counts.items())) or "nothing to dispatch"))
        for row in results:
            if row["state"] != VALIDATED:
                say("  %-9s %-40s attempts %d  %s"
                      % (row["state"], row["node"], row["attempts"], row["last_error"] or ""))
                any_incomplete = True
        store = query_mod.Store(backend)  # re-read state.json: next wave inherits this wave's claims

    backend.finish_run(run_id, "complete")
    trajectory.record_run_event(run_id=run_id, repo_id=repo_id, event="finished", reason="complete")
    hint = lessons_hint(trajectory)
    trajectory.close()
    backend.close()
    return {"run_id": run_id, "any_incomplete": any_incomplete, "nothing_stale": False, "hint": hint,
            "tasks": totals, "rejected_unknowns": rejected_unknowns}
