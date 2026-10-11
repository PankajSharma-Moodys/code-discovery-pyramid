"""Phase 3 -- incremental extract (0.11, M3.2) and `cdp refresh` (3.1, M3.3).

Graph, xref and dataflow are always recomputed in full: partition assignment
and manifest-declared edges are global properties of the whole file set, so a
cached graph after one file moves is a wrong graph, not an optimisation
deferred (`PHASE/phase_3_plan.md` M3.2). Only per-file extraction
(`defines`/`uses`/`io_edges`) is incremental, because `extract_file` is already
pure per file (`extract.py`).

Rename-awareness (`git diff -M`, `cdp/drift.py`) is derived by `state.fold` itself, per claim,
from the claim's `claim_reviewed_at` and HEAD, so the materialized state stays exactly
fold(patches, xref); `refresh` never hands `fold` anything the log does not imply (R5).
"""

from __future__ import annotations

import datetime

from . import rereview as rereview_mod, dataflow as dataflow_mod, freshness as freshness_mod, graph as graph_mod, inventory as inventory_mod, partition as partition_mod, query as query_mod, resolve as resolve_mod, rollback as rollback_mod, schedule as schedule_mod, snapshot as snapshot_mod, state as state_mod
from .extract import MAX_PARSE_BYTES, _sorted
from .lang import extract_file
from .derived import build_derived_patch
from .session import Paths, check_repo_matches_manifest, extra_excludes, git_head_or_raise, open_store
from .util import CdpError, read_lines, stable_hash
from .store import registry as registry_mod
from .drift import HistoryUnavailable, classify_changes, classify_full, diff_status  # noqa: F401 -- re-exported
from .verify import STRICT
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Set, Tuple


def scope_hash(repo: Path, scope: Dict) -> str:
    """Content fingerprint of one partition scope (M3.4).

    Sorted `(path, content)` pairs, so a rename with no content change (or a
    diff to a *different* scope) does not move this scope's hash, and any
    added/removed/edited file within it does. This is the cache key `refresh`
    compares across a commit to decide which scopes actually need re-dispatch
    -- "unchanged hash -> reuse the claim, skip the agent".
    """
    repo = Path(repo)
    parts = []
    for path in sorted(scope["files"]):
        parts.append(path)
        parts.extend(read_lines(repo / path))
    return stable_hash(parts)


def annotate_scope_hashes(repo: Path, partition: Dict) -> None:
    """Mutates `partition["scopes"]` in place, adding `scope_hash` to each."""
    for scope in partition["scopes"]:
        scope["scope_hash"] = scope_hash(repo, scope)


def changed_scopes(old_partition: Optional[Dict], new_partition: Dict) -> Set[str]:
    """Node names whose `scope_hash` moved (or is new) between two partitions.

    A node absent from `old_partition` (new scope, or a scope that changed
    shape entirely) counts as changed -- there is nothing to reuse for it.
    """
    old_hashes = {s["node"]: s.get("scope_hash") for s in (old_partition or {}).get("scopes", [])}
    return {
        s["node"] for s in new_partition["scopes"]
        if old_hashes.get(s["node"]) != s.get("scope_hash")
    }


def incremental_extract(
    repo: Path, inventory: Dict, prior_extraction: Dict, changed_files: Set[str]
) -> Dict:
    """Re-extract every file in a module that touched a changed file; carry
    every other module's rows forward untouched.

    Module granularity, not file granularity: `declared_deps`/`module_notes`
    are aggregated per module with no per-file attribution kept in the stored
    artifact, so carrying a module forward while re-deriving only one of its
    files would silently drop the rest. Re-deriving the whole module whenever
    any of its files changed is what makes this byte-identical to a full
    `run_extract` -- the equivalence the milestone's acceptance test checks.
    """
    repo = Path(repo)
    entries = inventory["files"]
    entry_by_path = {e["path"]: e for e in entries}
    changed_modules = {entry_by_path[p]["module"] for p in changed_files if p in entry_by_path}
    stale = {e["path"] for e in entries if e["module"] in changed_modules}
    carried_paths = {e["path"] for e in entries if e["path"] not in stale}

    prior_files = prior_extraction.get("files", {})
    defines = [r for r in prior_extraction.get("defines", []) if r.get("file") in carried_paths]
    uses = [r for r in prior_extraction.get("uses", []) if r.get("file") in carried_paths]
    io_edges = [r for r in prior_extraction.get("io_edges", []) if r.get("file") in carried_paths]
    imports = [r for r in prior_extraction.get("imports", []) if r.get("file") in carried_paths]
    per_file: Dict[str, Dict] = {p: prior_files[p] for p in carried_paths if p in prior_files}
    declared = {
        m: list(v) for m, v in (prior_extraction.get("declared_deps") or {}).items()
        if m not in changed_modules
    }
    module_notes = {
        m: list(v) for m, v in (prior_extraction.get("module_notes") or {}).items()
        if m not in changed_modules
    }

    for entry in entries:
        rel = entry["path"]
        if rel not in stale:
            continue
        if entry["binary"] or entry["bytes"] > MAX_PARSE_BYTES:
            continue
        lines = read_lines(repo / rel)
        if not lines:
            continue
        facts = extract_file(rel, lines, entry["module"])
        module = entry["module"]
        for row in facts.defines:
            row = dict(row)
            row["file"] = rel
            row["module"] = module
            defines.append(row)
        for row in facts.uses:
            row = dict(row)
            row["file"] = rel
            row["module"] = module
            row["scope_package"] = facts.package
            uses.append(row)
        for row in facts.io_edges:
            row = dict(row)
            row["file"] = rel
            row["module"] = module
            io_edges.append(row)
        for row in facts.imports:
            imports.append({"file": rel, "module": module, "fqn": row["fqn"],
                            "line": row["line"], "anchor": row["anchor"]})
        if facts.declared_deps:
            declared.setdefault(module, []).extend(facts.declared_deps)
        if facts.notes:
            module_notes.setdefault(module, []).extend(facts.notes)
        per_file[rel] = {
            "language": facts.language, "package": facts.package, "primary": facts.primary,
            "loc": facts.loc, "signals": facts.signals, "defines": len(facts.defines),
            "imports": len(facts.imports), "io_edges": len(facts.io_edges),
        }

    return {
        "head": inventory["head"],
        "files": per_file,
        "defines": _sorted(defines, ("fqn", "file", "kind")),
        "uses": _sorted(uses, ("fqn", "file")),
        "io_edges": _sorted(io_edges, ("source", "target", "channel", "file")),
        "imports": _sorted(imports, ("file", "fqn")),
        "declared_deps": {k: sorted(set(v)) for k, v in sorted(declared.items())},
        "module_notes": {k: sorted(set(v)) for k, v in sorted(module_notes.items())},
        "totals": {
            "parsed_files": len(per_file),
            "defines": len(defines),
            "uses": len(uses),
            "io_edges": len(io_edges),
            "imports": len(imports),
        },
    }


class CarrySource:
    """The snapshot whose model/human patches (and rollback ledger) a new snapshot inherits."""

    def __init__(self, snapshot_id: int, ledger: Dict, model_patches: int) -> None:
        self.snapshot_id, self.ledger, self.model_patches = snapshot_id, ledger, model_patches


def carry_source(backend) -> Optional[CarrySource]:
    """Read, before `begin_snapshot` moves the selection, the snapshot a new one builds on: the
    one `snapshot.choose_snapshot` selected (HEAD's own, else the nearest clean ancestor), never
    another branch's or a dirty scan's. None when there is none (nothing scanned, or no git)."""
    choice = getattr(backend, "choice", None)
    if choice is None or choice.scan_needed or choice.row["ephemeral"]:
        return None
    patches = backend.load_patches()
    return CarrySource(backend.snapshot_id(), backend.read_artifact(rollback_mod.LEDGER_ARTIFACT, {"events": []}),
                       sum(1 for p in patches if p.get("author_kind") != "python" and p.get("status") == "complete"))


def carry_leaf_log(backend, source: Optional[CarrySource], model_only: bool = False) -> bool:
    """Seed the just-selected snapshot with `source`'s patch log and rollback ledger, verbatim, so the
    claims a model wrote stay in the index: `refresh` re-verifies them against the new tree, and `scan`
    does the same on a new commit or a dirty tree (the fold re-anchors each claim, demoting what no
    longer holds). Only when the snapshot has no model patch of its own (it is new). `model_only`
    (scan): skip when `source` holds none, so a repo no model has touched scans exactly as before.
    Returns whether it carried."""
    if source is None or source.snapshot_id == backend.snapshot_id():
        return False
    if model_only and not source.model_patches:
        return False
    if any(p.get("author_kind") != "python" for p in backend.load_patches()):
        return False
    backend.copy_patches_from(source.snapshot_id)
    if source.ledger.get("events"):
        backend.write_artifact(rollback_mod.LEDGER_ARTIFACT, source.ledger)
    return True


def refresh_repo(
    paths: Paths,
    *,
    mode: str = STRICT,
    exclude: Optional[Sequence[str]] = None,
    say: Callable[..., None] = lambda *a: None,
) -> int:
    """M3.3: re-verify every live claim against HEAD, zero model calls.

    Re-derives nothing: the patch log is untouched (R5). What moves is the
    *view* -- incremental extraction (M3.2) for `xref`/`graph`/`dataflow`, and
    rename-aware re-verification for the claims already in the log, via the
    same `rename_map`/`edited_files` arguments `state.fold` now accepts.
    """

    backend = open_store(paths)
    try:
        return _refresh(backend, paths, mode, exclude, say)
    finally:
        backend.close()


def _refresh(backend, paths: Paths, mode: str, exclude, say: Callable[..., None]) -> int:
    choice = backend.choice
    if choice.scan_needed:
        raise CdpError("scan needed: %s; run `cdp scan`" % choice.reason)
    store = query_mod.Store(backend)
    check_repo_matches_manifest(paths, store.manifest)
    # The snapshot the shared rule chose is the base: HEAD's own (nothing to do) or the
    # nearest clean ancestor. Never another branch's, never a dirty scan's.
    base = carry_source(backend)
    base_snapshot_id = backend.snapshot_id()

    stored = list(store.manifest.get("excludes") or [])
    if snapshot_mod.is_dirty(paths.repo, stored + list(exclude or [])):
        raise CdpError("refresh requires a clean working tree (dirty trees are ephemeral, "
                       "never a refresh target)")
    prev_head = store.inventory.get("head")
    new_head = git_head_or_raise(paths.repo)
    if prev_head in (None, "unpinned"):
        raise CdpError("no prior scan to refresh from -- run `cdp scan` first")
    if new_head == prev_head:
        say("refresh   HEAD unchanged (%s); nothing to do" % new_head[:12])
        return 0

    history_ok = True
    try:
        rename_map, edited, added, deleted, reformatted = classify_full(
            paths.repo, prev_head, new_head,
            snapshot_mod.exclusion_patterns(paths.repo, store.manifest.get("excludes") or []) + tuple(exclude or ()))
    except HistoryUnavailable:
        history_ok = False
        rename_map, edited, added, deleted, reformatted = {}, set(), set(), set(), set()

    excludes = list(store.manifest.get("excludes") or []) + list(exclude or [])
    new_inventory = inventory_mod.build_inventory(paths.repo, extra_excludes=extra_excludes(paths.repo, excludes))
    if history_ok:
        changed = set(rename_map.values()) | edited | added | reformatted
    else:
        changed = {e["path"] for e in new_inventory["files"]}
    new_extraction = incremental_extract(paths.repo, new_inventory, store.extraction, changed)

    new_graph = graph_mod.build_graph(new_inventory, new_extraction)
    new_xref = resolve_mod.build_xref(new_inventory, new_extraction, new_graph)
    budgets = store.manifest.get("budgets", {})
    new_part = partition_mod.partition(
        new_inventory,
        budgets.get("max_leaf_files", partition_mod.DEFAULT_MAX_FILES),
        budgets.get("max_leaf_loc", partition_mod.DEFAULT_MAX_LOC),
    )
    annotate_scope_hashes(paths.repo, new_part)
    dispatch = changed_scopes(store.partition, new_part)
    new_flow = dataflow_mod.build_dataflow(
        new_extraction, new_xref, new_graph, budgets.get("max_hops", dataflow_mod.DEFAULT_MAX_HOPS)
    )

    # Read before `begin_snapshot` moves the backend's selection forward --
    # `store` wraps this same backend instance, and `state` is not read
    # anywhere above this line, so reading it after the snapshot switch would
    # silently return the new (not-yet-written) snapshot's empty default.
    before_demoted = len(store.state.get("unknowns", []))

    backend.begin_snapshot(*snapshot_mod.resolve_snapshot(paths.repo, new_inventory["head"], excludes),
                         checkout=registry_mod.checkout_key(paths.repo))
    registry_mod.remember_alias(paths.repo)
    # M2.4's per-snapshot patch isolation means the snapshot just selected starts with an empty log.
    # Carry the base snapshot's log (and its rollback ledger, so rolled-back claims stay out) forward --
    # refresh re-verifies the *existing* log (D10), it never appends model claims, so an empty one
    # would fold to zero claims. `scan` carries the same way (`pipeline.scan`).
    if base is not None and base.snapshot_id == base_snapshot_id:
        carry_leaf_log(backend, base)
    backend.write_artifact("inventory", new_inventory)
    backend.write_artifact("extract", new_extraction)
    backend.write_artifact("graph", new_graph)
    backend.write_artifact("partition", new_part)
    backend.write_artifact("xref", new_xref)
    backend.write_artifact("dataflow", new_flow)
    # A scan writes this too; without it `status` and the schedule-reading
    # commands fail on the refreshed snapshot ("missing artifact 'schedule'").
    new_sched = schedule_mod.build_schedule(
        new_part, new_graph, budgets.get("max_concurrent", schedule_mod.DEFAULT_MAX_CONCURRENT))
    backend.write_artifact("schedule", new_sched)
    # The scan's own claims are regenerated for the new tree, as a fresh scan would.
    backend.write_derived_patch(build_derived_patch(
        paths.repo, new_inventory, new_extraction, new_graph, new_xref, new_part, new_flow,
        backend.load_patches()))
    folded = state_mod.fold(
        backend.load_patches(), new_xref, new_part, repo=paths.repo, mode=mode,
        excluded_run_ids=rollback_mod.load_excluded_run_ids(backend),
        extraction=new_extraction,
    )
    backend.write_artifact("state", folded)
    backend.write_artifact(
        "manifest",
        dict(store.manifest, head=new_inventory["head"], **({"excludes": excludes} if excludes else {}),
             generated_at=datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")),
    )

    buckets = freshness_mod.bucket_counts(folded["claims"], paths.repo, new_head, store=backend)
    after_demoted = len(folded.get("unknowns", []))
    say("refresh   %s -> %s" % (prev_head[:12], new_head[:12]))
    if not history_ok:
        say("          history unavailable for that range (rebase/shallow) -- full "
            "re-extract, staleness reported as unknown rather than assumed live")
    say("extract   %d file(s) changed (renamed/edited/added), %d total parsed"
        % (len(changed), new_extraction["totals"]["parsed_files"]))
    say("rename    %d file(s) renamed, %d edited, %d added, %d deleted"
        % (len(rename_map), len(edited), len(added), len(deleted)))
    # C2: a changed scope needs a leaf only for its stale claims and new files, and only the
    # changed files go to it; a changed scope with nothing stale keeps every claim it had.
    plans = rereview_mod.plans_for(query_mod.Store(backend), paths.repo, sorted(dispatch))
    needed = sorted(n for n in dispatch if n in plans and not plans[n].empty)
    unplanned = sorted(n for n in dispatch if n not in plans)
    say("scopes    %d/%d changed (dispatch needed for %d: %d stale claim(s) in %d changed file(s); "
        "%d changed scope(s) reuse every claim%s)"
        % (len(dispatch), len(new_part["scopes"]), len(needed + unplanned),
           sum(len(plans[n].stale) for n in needed), len({f for n in needed for f in plans[n].files}),
           len(dispatch) - len(needed) - len(unplanned),
           ", %d never reviewed by a leaf" % len(unplanned) if unplanned else ""))
    say("verify    %d live, %d stale, %d anchored-but-unreviewed, %d unknown-churn "
        "(%d newly demoted), zero model calls"
        % (buckets[freshness_mod.LIVE], buckets[freshness_mod.STALE],
           buckets[freshness_mod.UNREVIEWED], buckets[freshness_mod.UNKNOWN_CHURN],
           after_demoted - before_demoted))
    say("next      cdp query stats")
    return 0
