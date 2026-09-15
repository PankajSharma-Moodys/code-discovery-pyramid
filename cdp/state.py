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
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from .merge import merge_claims
from .util import CdpError, read_json, stable_hash, write_json

PATCH_GLOB = "*.json"

# Status precedence for retry supersession. A successful attempt outranks a
# failed one whichever order they were written in; nothing below `complete`
# contributes claims, so ranking the failure modes only decides what the gap is
# *reported* as.
STATUS_RANK = {"pending": 1, "failed": 2, "invalid": 3, "complete": 4}


def patches_dir(state_dir: Path) -> Path:
    return Path(state_dir) / "patches"


def load_patches(state_dir: Path) -> List[Dict]:
    """Read the append-only patch log.

    Sorted by filename so the log has a canonical reading order, but nothing
    downstream may depend on that order: `fold` must produce the same result
    under any permutation, and `check_order_independence` proves it does.
    """
    directory = patches_dir(state_dir)
    if not directory.is_dir():
        return []
    out = []
    for path in sorted(directory.glob(PATCH_GLOB)):
        try:
            out.append(read_json(path))
        except ValueError as exc:
            raise CdpError("corrupt patch %s: %s" % (path, exc))
    return out


DERIVED_PATCH = "0000-derived.json"


def append_patch(state_dir: Path, patch: Dict, label: str) -> Path:
    """Append one patch. Never rewrites an existing file.

    The log is the audit trail: for any fact in a final document you can trace
    which agent asserted it, in which patch, citing what. Compaction would
    destroy that, so there is deliberately no compaction path here.

    Numbering is `max existing index + 1` rather than `count`, so that removing
    or overwriting slot 0000 cannot make a later append collide with a patch
    that already exists.
    """
    directory = patches_dir(state_dir)
    directory.mkdir(parents=True, exist_ok=True)
    used = []
    for path in directory.glob(PATCH_GLOB):
        head = path.name.split("-", 1)[0]
        if head.isdigit():
            used.append(int(head))
    index = max(used) + 1 if used else 1
    safe = label.replace("/", "__").replace(" ", "_")
    return write_json(directory / ("%04d-%s.json" % (index, safe)), patch)


def write_derived_patch(state_dir: Path, patch: Dict) -> Path:
    """Write the deterministic claims into the log's reserved first slot.

    `scan` is re-runnable, and re-running it must not destroy work: an earlier
    version cleared `patches/` wholesale, which discarded every leaf patch
    already collected and every prompt result waiting in the inbox. Since the
    derived claims are a pure function of the commit, overwriting one fixed slot
    is both correct and idempotent — the log keeps its audit trail and a rescan
    costs nothing.
    """
    directory = patches_dir(state_dir)
    directory.mkdir(parents=True, exist_ok=True)
    return write_json(directory / DERIVED_PATCH, patch)


def fold(patches: Sequence[Dict], xref: Dict, partition: Optional[Dict] = None) -> Dict:
    """The whole of state derivation. Pure: same inputs, same bytes out."""
    claims: List[Dict] = []
    unknowns: List[Dict] = []
    node_status: Dict[str, str] = {}
    node_errors: Dict[str, str] = {}

    for patch in patches:
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
        if status != "complete":
            continue
        for claim in patch.get("claims") or []:
            row = dict(claim)
            row.setdefault("source_node", node)
            claims.append(row)
        for unknown in patch.get("unknowns") or []:
            row = dict(unknown)
            row.setdefault("source_node", node)
            unknowns.append(row)

    superseded = {n for n, s in node_status.items() if s != "complete"}
    claims = [c for c in claims if c.get("source_node") not in superseded]

    merged = merge_claims(claims, xref.get("symbols", {}))
    coverage = _coverage(node_status, partition)

    # Failure propagates as a stated gap, never as silence (§3.5).
    for node in sorted(superseded):
        unknowns.append(
            {
                "question": "What does %s contain? Its scope was not successfully examined." % node,
                "why_unresolved": "Node status is '%s'%s."
                % (node_status[node], ": " + node_errors[node] if node in node_errors else ""),
                "source_node": node,
            }
        )

    return {
        "schema_version": "1.0.0",
        "claims": merged["claims"],
        "unknowns": _dedupe_unknowns(unknowns),
        "conflicts": merged["conflicts"],
        "near_misses": merged["near_misses"],
        "merge_stats": merged["stats"],
        "nodes": dict(sorted(node_status.items())),
        "node_errors": dict(sorted(node_errors.items())),
        "coverage": coverage,
        "provenance": {
            "patch_count": len(patches),
            "fold_hash": fold_hash(patches, xref, partition),
        },
    }


def fold_hash(patches: Sequence[Dict], xref: Dict, partition: Optional[Dict]) -> str:
    """A hash of the fold's *inputs*, order-independently.

    Patch hashes are sorted before combining so that the value is a property of
    the log's contents rather than of the order files happened to be read in.
    """
    parts = sorted(stable_hash(p) for p in patches)
    parts.append(stable_hash(xref.get("symbols", {})))
    parts.append(stable_hash([s["node"] for s in (partition or {}).get("scopes", [])]))
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


def check_fold(state_dir: Path, xref: Dict, partition: Optional[Dict] = None) -> List[str]:
    """Recompute the fold and compare it to `state.json` on disk.

    Returns a list of violations. Any non-empty result means something wrote to
    the materialized view that the log does not support.
    """
    path = Path(state_dir) / "state.json"
    if not path.exists():
        return ["state.json does not exist; nothing has been folded yet"]
    on_disk = read_json(path)
    recomputed = fold(load_patches(state_dir), xref, partition)
    problems = []
    if on_disk.get("provenance", {}).get("fold_hash") != recomputed["provenance"]["fold_hash"]:
        problems.append("fold_hash mismatch: the log has changed since state.json was written")
    for key in ("claims", "unknowns", "conflicts", "coverage"):
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
