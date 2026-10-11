"""Taking patches in: `collect` (leaf patches from the inbox) and `answer` (a human claim)."""

from __future__ import annotations

from . import rereview as rereview_mod, anchor as anchor_mod, claimgate as claimgate_mod, gates as gates_mod, query as query_mod, tiering as tiering_mod
from .schema import Validator, schema_path, shape_errors, validate_patch
from .session import Paths, check_repo_matches_manifest, fold_and_write, git_identity, new_run_id, next_generation, open_store, stamp_claims
from .util import CdpError, SKILL_ROOT, stable_hash
from .verify import LENIENT, STRICT
from pathlib import Path
from typing import Dict, List, Optional


def escalation_rate(patches: List[Dict]) -> Optional[float]:
    """M6.3 (4.2): fraction of claims across this batch self-reporting
    `escalated: true` -- `None`, not `0.0`, when nothing in the batch used
    digest mode, so a real 0% escalation run is never confused with "the
    question doesn't apply here"."""
    claims = [c for patch in patches for c in (patch.get("claims") or [])]
    if not claims:
        return None
    return sum(1 for c in claims if c.get("escalated")) / len(claims)


def _other_runs(backend, repo_id: str, active: str, current: str) -> Dict[str, str]:
    """`run_id -> commit` for the other snapshots of this repo (a run id is derived from its commit)."""
    out = {}
    for snap in backend.list_snapshots():
        if snap.get("repo_id") == repo_id:
            base = snap["commit_sha"].split("+dirty:")[0]
            run = new_run_id(base)
            if run != active and base != current:
                out[run] = base
    return out


def _abandoned_task(backend, run_id: str, scope_hash, node: str) -> List[str]:
    if scope_hash and run_id and backend.supports_run_tracking():
        row = backend.task_states(run_id).get(scope_hash)
        if row and row["state"] == "abandoned":
            return ["/node: scope %s was abandoned in run %s; a later patch for it is not accepted "
                    "(re-run it with `cdp run --resume`)" % (node, run_id)]
    return []


def collect(paths: Paths, mode: str = STRICT) -> Dict:
    """Validate, verify and append every patch an agent left in the inbox.

    §3.5's retry contract lives here in its terminal form: a patch that fails
    validation is recorded `invalid` with the specific violations attached, and
    no claim from it enters state. The three attempts happen in the session,
    which is the only place that can ask the agent to try again.
    """

    backend = open_store(paths, durable=True)
    store = query_mod.Store(backend)
    check_repo_matches_manifest(paths, store.manifest)
    inbox = backend.read_inbox()

    validator = Validator.load(schema_path(SKILL_ROOT))
    scope_nodes = {s["node"] for s in store.partition["scopes"]}
    node_to_hash = {s["node"]: s.get("scope_hash") for s in store.partition["scopes"]}
    other_runs = _other_runs(backend, paths.repo_id, str(store.manifest.get("run_id")), str(store.inventory.get("head")))
    dirty = set(backend.choice.dirty_files)
    accepted: List[Dict] = []
    rejected: List[Dict] = []
    rejected_claims: List[Dict] = []

    for name, patch in inbox:
        if isinstance(patch, ValueError):
            rejected.append({"file": name, "errors": ["not valid JSON: %s" % patch]})
            backend.reject_inbox(name)
            continue
        if not isinstance(patch, dict):  # `[]`, `null`, `42`, `"x"`: valid JSON, not a patch
            rejected.append({"file": name, "errors": ["/: a patch must be a JSON object, got %s"
                                                       % type(patch).__name__]})
            backend.reject_inbox(name)
            continue
        node = str(patch.get("node", ""))
        errors: List[str] = shape_errors(patch)
        if not errors and node in scope_nodes:
            had_claims = bool(patch.get("claims"))
            patch, dropped = claimgate_mod.screen_claims(patch, validator, claimgate_mod.Context.of_store(store, node, paths.repo))
            rejected_claims += [dict(d, node=node) for d in dropped]
            if had_claims and not patch["claims"] and not patch.get("unknowns"):
                errors.append("/claims: every claim was rejected (%s)" % "; ".join(
                    "%s: %s" % (d["id"], d["reasons"][0]) for d in dropped[:3]))
        errors += validate_patch(patch, validator)
        if node not in scope_nodes:
            errors.append("/node: %r is not a scope in partition.json" % node)
        run = str(patch.get("run_id", ""))
        if run in other_runs:
            errors.append("/run_id: %r is the run of commit %s; this index is at %s (run %s) -- "
                          "the patch describes another snapshot" % (
                              run, other_runs[run][:12], (store.inventory.get("head") or "?")[:12],
                              store.manifest.get("run_id")))
        errors += _abandoned_task(backend, run, node_to_hash.get(node), node)
        cited = [] if shape_errors(patch) else sorted(
            {str(a.get("file")) for c in patch.get("claims") or [] for a in c.get("evidence") or []} & dirty)
        if cited:
            errors.append("/claims: cites file(s) with uncommitted changes (%s); commit them and `refresh`, "
                          "or cite unchanged files" % ", ".join(cited[:5]))
        if errors:
            rejected.append({"file": name, "node": node, "errors": errors[:12]})
            backend.reject_inbox(name)
            backend.append_patch(
                {
                    "schema_version": "1.0.0",
                    "node": node or Path(name).stem,
                    "run_id": str(patch.get("run_id", store.manifest.get("run_id", "cdp"))),
                    "status": "invalid",
                    "error": "; ".join(errors[:6]),
                },
                (node or Path(name).stem) + "-invalid",
            )
            continue
        accepted.append(patch)

    # M4.2: the four unknown gates. Subject/negative-entailment/provenance run
    # here, per-patch, before a patch's `unknowns[]` is appended to the log --
    # the same point schema validation already runs at. Clustering (gate 4)
    # runs inside `fold` instead (`cdp/gates.py` `cluster_unknowns`), since
    # cluster membership is a property of the whole current unknown set.
    def_fqns, edge_subjects, edges_by_key = gates_mod.build_extraction_index(store.extraction)
    node_to_hash = {s["node"]: s.get("scope_hash") for s in store.partition["scopes"]}
    task_states_cache: Dict[str, Dict[str, Dict]] = {}
    unknown_rejections: List[Dict] = []

    def _task_rows_for(run_id: str) -> Dict[str, Dict]:
        if run_id not in task_states_cache:
            task_states_cache[run_id] = backend.task_states(run_id)
        return task_states_cache[run_id]

    # M2.3: append the raw, unverified patch. Verification runs inside
    # `fold`, against `paths.repo`, not here — see `cli.py` `cmd_scan`.
    log_so_far = backend.load_patches()
    rereview_marker = backend.read_report("rereview", {}) or {}
    marker_used = False
    for patch in accepted:
        patch.setdefault("author_kind", "llm")
        if mode == LENIENT:
            patch["verify_mode"] = LENIENT
        node = str(patch.get("node", "leaf"))
        marked = (rereview_marker.get("nodes") or {}).get(node) if rereview_marker.get("head") == store.inventory.get("head") else None
        if marked:  # the prompt covered only the stale claims and changed files: the live rest stays
            rereview_mod.carry_forward(patch, node, marked["carry"], log_so_far)
            rereview_marker["nodes"].pop(node)
            marker_used = True
        patch["generation"] = next_generation(log_so_far, node)
        log_so_far.append(patch)
        stamp_claims(patch.get("claims") or [], store.inventory["head"])
        run_id = str(patch.get("run_id", store.manifest.get("run_id", "cdp")))
        task_rows = _task_rows_for(run_id).get(node_to_hash.get(node))
        kept_unknowns, patch_rejections = gates_mod.gate_patch_unknowns(
            patch.get("unknowns") or [], node, def_fqns, edge_subjects, edges_by_key,
            scope_nodes, {node: task_rows},
        )
        patch["unknowns"] = kept_unknowns
        unknown_rejections.extend(patch_rejections)
        backend.append_patch(patch, node)
        backend.clear_inbox(str(patch.get("node", "")))

    if marker_used:
        backend.write_report("rereview", rereview_marker)
    folded = fold_and_write(backend, store.xref, store.partition, repo=paths.repo, mode=mode)
    stats = folded["verification"]
    stats["escalation_rate"] = escalation_rate(accepted)
    backend.write_report("verify", stats)
    backend.write_report("rejected", {"rejected": rejected})
    backend.write_report("unknown_gates", {"rejected": unknown_rejections})

    # M6.4 (4.8): the rule's post-dispatch half. A T2 leaf's own claims may
    # self-report `escalated: true` (M6.3) -- upgrade that scope's logged
    # tier in place, reason `leaf_escalated`, rather than only ever deciding
    # tier before the leaf ran.
    tiering_report = dict(backend.read_report("tiering", {}).get("tiering", {}))
    tiering_upgrades = []
    for patch in accepted:
        node = str(patch.get("node", "leaf"))
        if tiering_mod.apply_leaf_escalation(tiering_report, node, patch.get("claims") or []):
            tiering_upgrades.append(node)
    if tiering_upgrades:
        backend.write_report("tiering", {"tiering": tiering_report})
    backend.close()
    return {
        "accepted": accepted, "rejected": rejected, "unknown_rejections": unknown_rejections,
        "rejected_claims": rejected_claims,
        "tiering_upgrades": tiering_upgrades, "stats": stats, "coverage": folded["coverage"],
    }


def answer(
    paths: Paths,
    *,
    scope: str,
    subject: str,
    statement: str,
    anchor_ref: str,
    kind: str,
    confidence: str,
    author: Optional[str] = None,
    channel: Optional[str] = None,
    mode: str = STRICT,
) -> Dict:
    """M4.4: a human claim against an unknown, through the *entire* pipeline
    -- validate, verify the anchor, entail, fold -- exactly like a leaf
    agent's patch (`collect`). `author_kind=human` changes merge
    precedence (R11) and, per `entail.py`, whether a contradiction is
    silently accepted -- it never changes the gate itself.
    """

    backend = open_store(paths, durable=True)
    store = query_mod.Store(backend)
    check_repo_matches_manifest(paths, store.manifest)

    scope_nodes = {s["node"] for s in store.partition["scopes"]}
    if scope not in scope_nodes:
        backend.close()
        raise CdpError("%r is not a scope in partition.json" % scope)

    file_part, sep, line_part = anchor_ref.rpartition(":")
    if not sep or not line_part.isdigit():
        backend.close()
        raise CdpError("--anchor must be FILE:LINE, got %r" % anchor_ref)
    if file_part in backend.choice.dirty_files:
        backend.close()
        raise CdpError("%s has uncommitted changes: an answer is anchored to a commit, so it cannot cite "
                       "a file that differs from HEAD (dirty: %s). Commit and `cdp refresh`, or cite an "
                       "unchanged file." % (file_part, ", ".join(backend.choice.dirty_files[:5])))
    abs_path = (paths.repo / file_part)
    try:
        text = abs_path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        backend.close()
        raise CdpError("cannot read %s: %s" % (file_part, exc))
    anchor = anchor_mod.build_anchor(file_part, text.splitlines(), int(line_part) - 1)
    if anchor is None:
        backend.close()
        raise CdpError("no citable anchor at %s:%s -- humans are not exempt from anchor "
                        "verification either" % (file_part, line_part))

    claim = {
        "id": "human.%s" % stable_hash([scope, subject, statement])[:16],
        "kind": kind,
        "subject": subject,
        "statement": statement,
        "evidence": [anchor],
        "confidence": confidence,
        "author_kind": "human",
        "author": author or git_identity(paths.repo),
    }
    if channel:
        claim["channel"] = channel

    log_so_far = backend.load_patches()
    patch = {
        "schema_version": "1.0.0",
        "node": scope,
        "run_id": "cdp-answer-%s" % claim["id"].split(".", 1)[1][:8],
        "status": "complete",
        "author_kind": "human",
        "generation": next_generation(log_so_far, scope),
        "claims": [claim],
    }
    if mode == LENIENT:
        patch["verify_mode"] = LENIENT
    validator = Validator.load(schema_path(SKILL_ROOT))
    errors = validate_patch(patch, validator)
    if errors:
        backend.close()
        raise CdpError("schema-invalid claim:\n  " + "\n  ".join(errors[:10]))

    stamp_claims(patch["claims"], store.inventory["head"])
    backend.append_patch(patch, scope)

    folded = fold_and_write(backend, store.xref, store.partition, repo=paths.repo, mode=mode)
    row = next((c for c in folded["claims"] if c["id"] == claim["id"]), None)
    discharged = [u for u in folded["unknowns"]
                  if u.get("status") == "resolved"
                  and (u.get("resolved_by") or {}).get("claim_id") == claim["id"]]
    backend.close()
    return {"claim": claim, "row": row, "kept": row is not None, "discharged": discharged}
