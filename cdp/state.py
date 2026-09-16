"""The fold invariant (§3.4).

    state.json  =  fold(merge_operator, patches/, xref.json)

Nothing may enter `state.json` that is not derivable from the log. This is an
invariant, not a description of how the first implementation happens to work.

The temptation during implementation is to let the merge phase write a
convenience field directly into the materialized state — a cached count, a
resolved label, a hand-patched fix. Every such write makes the view diverge from
its log *silently*, and silent divergence between a fact and its provenance is
the exact failure this project is organised against. So `fold` takes only
patches and the xref index, returns a fresh dict, and `check_fold` recomputes it
to prove the file on disk is still the fold of the log.

Note the third argument. A node's state is *not* a fold over that node's patches
alone: ownership resolution needs the global symbol table, which is the union of
`defines[]` across the whole run. Derivation is two-stage, both stages are
replayable, and an implementation that assumes otherwise hits the circularity
and improvises around it.

**What this buys.** Because merge is a replayable function of on-disk data, a
change to merge policy is an offline recomputation, not a re-run. Alternative
tie-break orders and detection sensitivities sweep over a fixed log at zero
token cost. The limit is the schema: claims were *shaped* by the vocabulary in
force when the agents ran, so replay can sweep resolution rules but cannot
answer a question about a different vocabulary.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Dict, FrozenSet, Iterable, List, Optional, Sequence

from .entail import entail_claims, summarize as summarize_entailment
from .gates import build_extraction_index, cluster_unknowns, discharge_unknowns, grandfather_needs
from .merge import merge_claims
from .util import git_head, stable_hash
from .verify import STRICT, verify_all

if TYPE_CHECKING:
    from .store import WorkspaceStore

# Status precedence for retry supersession. A successful attempt outranks a
# failed one whichever order they were written in; nothing below `complete`
# contributes claims, so ranking the failure modes only decides what the gap is
# *reported* as.
STATUS_RANK = {"pending": 1, "failed": 2, "invalid": 3, "complete": 4}


def fold(
    patches: Sequence[Dict],
    xref: Dict,
    partition: Optional[Dict] = None,
    repo: Optional[Path] = None,
    mode: str = STRICT,
    rename_map: Optional[Dict[str, str]] = None,
    edited_files: Optional[FrozenSet[str]] = None,
    excluded_run_ids: Optional[FrozenSet[str]] = None,
    extraction: Optional[Dict] = None,
) -> Dict:
    """The whole of state derivation. Deterministic: same inputs, same bytes out.

    `repo` is optional so every existing caller that folds a synthetic or
    already-verified patch list keeps working unchanged. When given, it is
    `PHASE/phase_2_plan.md` M2.3's move: the log holds raw agent output, and
    `fold` re-verifies every claim's anchors against `repo` before merging,
    rather than `cmd_collect`/`cmd_scan` verifying before the log is written.
    That is what makes re-verification against a *different* commit (Phase 3's
    `refresh`) a fold argument instead of a rewrite.

    `rename_map`/`edited_files` are Phase 3's rename-awareness (`cdp/refresh.py`
    M3.3): threaded straight through to `verify_all` so a `git mv` never mass-
    demotes a corpus (`verify.py:43-46`'s landmine) and R9's review-invalidation
    rule is applied without ever mutating a patch already in the log (R5).
    `head_sha` for the two freshness dates (0.8) is read from `repo` itself,
    not passed in and not the wall clock: two folds of the same commit must
    still be byte-identical (`cli.py` `_run_id`'s same argument), and this
    system's own notion of "when" is already `(repo_id, commit_sha)`.

    Verification is a per-patch, independent map over the log — it never reads
    another patch or the merge result — so composing it in front of the
    existing order-independent merge cannot introduce order-dependence; the
    property `check_order_independence` tests continues to hold for the same
    reason it always did.

    `excluded_run_ids` (Phase 3, M3.7 -- `cdp/rollback.py`) is a rolled-back
    run's identity, never a position: a patch whose `run_id` is in this set is
    dropped before anything else runs, so it contributes no claim, no status,
    no coverage -- as if it had never been appended, without the log itself
    ever being rewritten (R5). This is what makes rollback exact rather than
    approximate: fold is pure in its patch-list argument, so excluding the same
    run_ids twice, or excluding them via a different ledger entry, always
    yields the same bytes.

    `extraction` (Phase 4, M4.1) is this same commit's `io_edges`/`defines`
    (`cdp/entail.py`), used only to assign each claim a `verdict` -- never to
    add, drop or reword a claim.
    """
    if excluded_run_ids:
        patches = [p for p in patches if str(p.get("run_id")) not in excluded_run_ids]
    raw_patches = list(patches)
    verification = None
    verified_patches = raw_patches
    if repo is not None:
        head_sha = git_head(Path(repo))
        verified_patches, verification = verify_all(
            Path(repo), raw_patches, mode, head_sha, rename_map, edited_files
        )

    claims: List[Dict] = []
    unknowns: List[Dict] = []
    node_status: Dict[str, str] = {}
    node_errors: Dict[str, str] = {}

    for patch in verified_patches:
        node = str(patch.get("node", "?"))
        status = str(patch.get("status", "pending"))
        # A node's status is the BEST of its attempts, not the last one in the
        # log. §3.5 retries a failed node in a following wave, so a node
        # routinely has an `invalid` attempt and a `complete` one — and "last
        # wins" makes the answer depend on which order the log is read in.
        #
        # That is the order-dependence §5.5 forbids, and it is not a hypothetical:
        # it is deterministic-but-arbitrary across runs, so the determinism
        # harness would score it 1.0 while the pipeline silently discarded a
        # successful retry whenever the log happened to be read the other way.
        # Precedence over the status enum is order-independent by construction.
        if STATUS_RANK.get(status, 0) > STATUS_RANK.get(node_status.get(node, "pending"), 0):
            node_status[node] = status
        else:
            node_status.setdefault(node, status)
        if patch.get("error"):
            node_errors[node] = str(patch["error"])

    # A node re-run yields one generation, not an accumulation of every attempt
    # ever appended (M3.4, ARCHITECTURE.md's sharp-edges table: "both patches are
    # `complete`; neither supersedes"). Among a node's `complete` patches, only
    # the highest `generation` contributes claims. `generation` is data stamped
    # onto the patch at append time (`cli.py` `cmd_collect`/`cmd_scan`), not a
    # position in this list, so this selection is order-independent by
    # construction the same way `node_status` above is: permuting `patches`
    # cannot change which patch owns the max generation for a node.
    best_complete: Dict[str, Dict] = {}
    for patch in verified_patches:
        if str(patch.get("status", "pending")) != "complete":
            continue
        node = str(patch.get("node", "?"))
        gen = int(patch.get("generation") or 1)
        current = best_complete.get(node)
        if current is None:
            best_complete[node] = patch
            continue
        cur_gen = int(current.get("generation") or 1)
        if gen > cur_gen or (gen == cur_gen and stable_hash(patch) > stable_hash(current)):
            best_complete[node] = patch

    for node, patch in best_complete.items():
        for claim in patch.get("claims") or []:
            row = dict(claim)
            row.setdefault("source_node", node)
            claims.append(row)

    # R12: unknowns are sticky. Unlike claims, they accumulate across *every*
    # `complete` patch for a node, not just the highest generation -- a later
    # re-run's patch that simply omits a question it already asked must not
    # make that question silently vanish (`_dedupe_unknowns` collapses an
    # exact repeat; discharge below is the only thing that closes one out).
    for patch in verified_patches:
        if str(patch.get("status", "pending")) != "complete":
            continue
        node = str(patch.get("node", "?"))
        for unknown in patch.get("unknowns") or []:
            row = dict(unknown)
            row.setdefault("source_node", node)
            unknowns.append(row)

    superseded = {n for n, s in node_status.items() if s != "complete"}
    claims = [c for c in claims if c.get("source_node") not in superseded]

    merged = merge_claims(claims, xref.get("symbols", {}))
    merged_claims = entail_claims(merged["claims"], extraction)
    contradictions = [c for c in merged_claims if c.get("verdict") == "contradicted"]
    entailment = summarize_entailment(merged_claims)
    coverage = _coverage(node_status, partition)

    # Failure propagates as a stated gap, never as silence (§3.5).
    for node in sorted(superseded):
        unknowns.append(
            {
                "question": "What does %s contain? Its scope was not successfully examined." % node,
                "why_unresolved": "Node status is '%s'%s."
                % (node_status[node], ": " + node_errors[node] if node in node_errors else ""),
                "source_node": node,
                "needs": "needs_human",
            }
        )

    scope_nodes = {s["node"] for s in (partition or {}).get("scopes", [])}
    def_fqns, edge_subjects, _edges_by_key = build_extraction_index(extraction)
    resolved_unknowns = discharge_unknowns(
        grandfather_needs(_dedupe_unknowns(unknowns)), merged_claims,
        def_fqns, edge_subjects, scope_nodes,
    )

    return {
        "schema_version": "1.0.0",
        "claims": merged_claims,
        "unknowns": cluster_unknowns(resolved_unknowns),
        "conflicts": merged["conflicts"],
        "near_misses": merged["near_misses"],
        "merge_stats": merged["stats"],
        "nodes": dict(sorted(node_status.items())),
        "node_errors": dict(sorted(node_errors.items())),
        "coverage": coverage,
        "verification": verification,
        "entailment": entailment,
        "contradictions": contradictions,
        "rollback": {"excluded_run_ids": sorted(excluded_run_ids)} if excluded_run_ids else None,
        "provenance": {
            "patch_count": len(raw_patches),
            "fold_hash": fold_hash(raw_patches, xref, partition, extraction),
        },
    }


def fold_hash(
    patches: Sequence[Dict], xref: Dict, partition: Optional[Dict], extraction: Optional[Dict] = None
) -> str:
    """A hash of the fold's *inputs*, order-independently.

    Patch hashes are sorted before combining so that the value is a property of
    the log's contents rather than of the order files happened to be read in.
    `extraction` is optional and appended last (Phase 4, M4.1: entailment reads
    it too) so every pre-existing 3-argument call site keeps hashing exactly
    what it always did.
    """
    parts = sorted(stable_hash(p) for p in patches)
    parts.append(stable_hash(xref.get("symbols", {})))
    parts.append(stable_hash([s["node"] for s in (partition or {}).get("scopes", [])]))
    if extraction is not None:
        parts.append(stable_hash({"io_edges": extraction.get("io_edges"), "defines": extraction.get("defines")}))
    return stable_hash(parts)


def _coverage(node_status: Dict[str, str], partition: Optional[Dict]) -> Dict:
    """Tracked files in `complete` scopes over tracked files in the inventory.

    The figure to watch. A 94%-coverage run that says so is useful; the same run
    presented as complete is worse than no run at all, because a map that does
    not mark its own holes will be trusted across them.
    """
    if not partition:
        return {"files_complete": 0, "files_total": 0, "fraction": 0.0, "incomplete_nodes": []}
    total = 0
    complete = 0
    incomplete: List[str] = []
    for scope in partition["scopes"]:
        total += scope["file_count"]
        if node_status.get(scope["node"]) == "complete":
            complete += scope["file_count"]
        else:
            incomplete.append(scope["node"])
    return {
        "files_complete": complete,
        "files_total": total,
        "fraction": round(complete / total, 4) if total else 0.0,
        "incomplete_nodes": sorted(incomplete),
    }


def _dedupe_unknowns(unknowns: Sequence[Dict]) -> List[Dict]:
    seen = set()
    out = []
    for row in sorted(unknowns, key=lambda u: (str(u.get("source_node", "")), str(u.get("question", "")))):
        key = (str(row.get("question")), str(row.get("source_node")))
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


# ------------------------------------------------------------- invariants


def check_fold(
    store: "WorkspaceStore",
    xref: Dict,
    partition: Optional[Dict] = None,
    repo: Optional[Path] = None,
    mode: str = STRICT,
) -> List[str]:
    """Recompute the fold and compare it to the materialised `state` artifact.

    Returns a list of violations. Any non-empty result means something wrote to
    the materialized view that the log does not support. This is also Phase
    7's `verify --full` mechanism: a full recompute against `repo` re-verifies
    every claim from the raw log rather than trusting the last materialisation.
    """
    if not store.has_artifact("state"):
        return ["state does not exist; nothing has been folded yet"]
    on_disk = store.read_artifact("state")
    # M3.7: a prior `rollback` excluded some run_ids from the materialised
    # state without deleting their patches (R5) -- recomputing from the raw
    # log without the same exclusion would flag every rolled-back claim's
    # absence as drift instead of confirming it.
    from .rollback import load_excluded_run_ids

    recomputed = fold(
        store.load_patches(), xref, partition, repo=repo, mode=mode,
        excluded_run_ids=load_excluded_run_ids(store),
        extraction=store.read_artifact("extract") if store.has_artifact("extract") else None,
    )
    problems = []
    if on_disk.get("provenance", {}).get("fold_hash") != recomputed["provenance"]["fold_hash"]:
        problems.append("fold_hash mismatch: the log has changed since state.json was written")
    for key in ("claims", "unknowns", "conflicts", "coverage", "entailment", "contradictions"):
        if stable_hash(on_disk.get(key)) != stable_hash(recomputed.get(key)):
            problems.append(
                "state.json/%s is not derivable from patches/ + xref.json "
                "(something wrote directly to the materialized view)" % key
            )
    return problems


def check_order_independence(patches: Sequence[Dict], xref: Dict, partition: Optional[Dict] = None) -> List[str]:
    """§5.5 requires order-independence of the merge operator; this tests it
    rather than asserting it.

    Order-based resolution would be *deterministic but arbitrary* across waves:
    it reproduces perfectly run over run, so §5.7 would score it 1.0 and certify
    a systematically wrong pipeline as flawlessly stable. A determinism
    measurement that a broken policy can pass is worse than no measurement,
    which is why this check exists separately from the harness.
    """
    if len(patches) < 2:
        return []
    baseline = fold(patches, xref, partition)
    problems = []
    for permutation in _permutations(list(patches)):
        candidate = fold(permutation, xref, partition)
        for key in ("claims", "conflicts", "unknowns"):
            if stable_hash(candidate[key]) != stable_hash(baseline[key]):
                problems.append("merge is order-dependent: %s differs under reordering" % key)
                return problems
    return problems


def _permutations(patches: List[Dict]) -> Iterable[List[Dict]]:
    """A few deterministic shuffles, not all n! of them.

    Reversal and rotations exercise every adjacency in the log, which is where
    a pairwise fold would show its order-dependence. Exhaustive permutation of a
    24-patch log is not a test, it is a hang.
    """
    yield list(reversed(patches))
    n = len(patches)
    for shift in (1, n // 2, n - 1):
        if 0 < shift < n:
            yield patches[shift:] + patches[:shift]
    yield sorted(patches, key=lambda p: stable_hash(p))
