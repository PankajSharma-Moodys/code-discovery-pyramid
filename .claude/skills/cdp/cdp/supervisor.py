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
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from .prompts import build_prompt
from .schema import Validator, validate_patch
from .util import git_head, read_json, write_text
from .verify import FileCache, STRICT, verify_patch

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
    """Renews one scope's lease every `interval` seconds for as long as a
    runner call is in flight. Runs in a background thread because the main
    thread is blocked inside `runner.run()` -- there is no between-calls point
    to renew from. If the process dies, this thread dies with it and the
    lease simply expires; that is the entire death-detection mechanism, not a
    special case of it."""

    def __init__(self, backend, run_id: str, scope_hash: str, lease_seconds: float, interval: float) -> None:
        self._backend = backend
        self._run_id = run_id
        self._scope_hash = scope_hash
        self._lease_seconds = lease_seconds
        self._interval = interval
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, daemon=True)

    def start(self) -> "_LeaseHeartbeat":
        self._thread.start()
        return self

    def _loop(self) -> None:
        while not self._stop.wait(self._interval):
            self._backend.heartbeat_lease(self._run_id, self._scope_hash, self._lease_seconds)

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
    text, _stats = build_prompt(scope, inventory, extraction, xref, sched, prior_claims, run_id)
    prompt_path = prompts_dir / (node.replace("/", "__") + ".md")
    write_text(prompt_path, text)
    patch_path = backend._inbox_dir() / (node.replace("/", "__") + ".json")

    state = PENDING
    last_error: Optional[str] = None
    patch: Optional[Dict] = None
    attempt = 0
    for attempt in range(1, max_attempts + 1):
        if not backend.acquire_lease(run_id, scope_hash, lease_seconds):
            return None
        if patch_path.exists():
            patch_path.unlink()
        backend.upsert_task(
            run_id, scope_hash, state=DISPATCHED, attempts=attempt,
            dispatched_at=_now(), last_error=None,
        )
        heartbeat = _LeaseHeartbeat(backend, run_id, scope_hash, lease_seconds, heartbeat_seconds).start()
        try:
            result = runner.run(prompt_path, patch_path)
        finally:
            heartbeat.stop()
        if not result.ok:
            state, last_error, patch = EXPIRED, result.error or "runner reported failure with no message", None
        else:
            backend.upsert_task(run_id, scope_hash, state=RETURNED, wall_ms=result.wall_ms)
            state, last_error, patch = _classify_returned(patch_path, node, validator, repo, mode)
        backend.upsert_task(run_id, scope_hash, state=state, last_error=last_error, wall_ms=result.wall_ms)
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
    }


def run_wave(
    nodes: Sequence[str], store, backend, runner, paths, run_id: str,
    validator: Validator, sched: Dict, mode: str = STRICT,
    lease_seconds: float = LEASE_SECONDS, heartbeat_seconds: float = HEARTBEAT_SECONDS,
    max_attempts: int = MAX_ATTEMPTS, skip_hashes=frozenset(),
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
    prompts_dir = paths.state / "prompts"
    prompts_dir.mkdir(parents=True, exist_ok=True)
    backend.ensure_inbox()
    prior = list(store.state.get("claims", []))
    node_set = set(nodes)
    results = []
    for scope in store.partition["scopes"]:
        if scope["node"] not in node_set:
            continue
        if scope.get("scope_hash") in skip_hashes:
            continue
        row = dispatch_scope(
            scope, store.inventory, store.extraction, store.xref, sched, prior,
            run_id, runner, backend, prompts_dir, validator, paths.repo, mode,
            lease_seconds, heartbeat_seconds, max_attempts,
        )
        if row is not None:
            results.append(row)
    return results


def mark_folded(backend, run_id: str, results: Sequence[Dict]) -> None:
    """Bump every `VALIDATED` scope from this wave to the terminal `FOLDED`
    state, once the wave-level fold that consumed its patch has succeeded."""
    for row in results:
        if row["state"] == VALIDATED:
            backend.upsert_task(run_id, row["scope_hash"], state=FOLDED)


def _classify_returned(patch_path: Path, node: str, validator: Validator, repo: Path, mode: str):
    """The runner returned `ok=True` -- classify what it left behind into
    `(state, last_error, patch_or_None)`."""
    if not patch_path.exists():
        return EMPTY, "runner returned ok but wrote no patch", None
    try:
        patch = read_json(patch_path)
    except (ValueError, OSError) as exc:
        return INVALID, "not valid JSON: %s" % exc, None
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
