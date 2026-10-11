"""Which patches of a log are live: the one rule `state.fold` and `compact` share.

* **Derived** patches (`author_kind` python) are the scan's own facts, regenerated on every
  scan and refresh. They are never a generation: nothing supersedes them.
* **Leaf** patches: the latest *accepted* (`complete`) generation per scope. A failed, invalid
  or abandoned attempt creates no generation and supersedes nothing.
* **Answers** (`author_kind` human) accumulate: one replaces another only for the same
  `(subject, kind)`.
"""

from __future__ import annotations

from typing import Dict, List, Sequence, Set, Tuple

from .util import stable_hash

DERIVED = "python"
HUMAN = "human"


def is_derived(patch: Dict) -> bool:
    return patch.get("author_kind") == DERIVED


def is_answer(patch: Dict) -> bool:
    return patch.get("author_kind") == HUMAN


def is_complete(patch: Dict) -> bool:
    return str(patch.get("status", "pending")) == "complete"


def newer(a: Dict, b: Dict) -> bool:
    """`a` outranks `b`: higher generation, ties broken by content (order-independent)."""
    ga, gb = int(a.get("generation") or 1), int(b.get("generation") or 1)
    return ga > gb or (ga == gb and stable_hash(a) > stable_hash(b))


def live_leaf_patches(patches: Sequence[Dict]) -> Dict[str, Dict]:
    best: Dict[str, Dict] = {}
    for patch in patches:
        if is_derived(patch) or is_answer(patch) or not is_complete(patch):
            continue
        node = str(patch.get("node", "?"))
        if node not in best or newer(patch, best[node]):
            best[node] = patch
    return best


def live_answer_claims(patches: Sequence[Dict]) -> Dict[Tuple[str, str], Tuple[Dict, Dict]]:
    """`(subject, kind) -> (patch, claim)` for the newest answer on each."""
    best: Dict[Tuple[str, str], Tuple[Dict, Dict]] = {}
    for patch in patches:
        if not is_answer(patch) or not is_complete(patch):
            continue
        for claim in patch.get("claims") or []:
            key = (str(claim.get("subject")), str(claim.get("kind")))
            if key not in best or newer(patch, best[key][0]):
                best[key] = (patch, claim)
    return best


def _unknown_keys(patch: Dict) -> Set[Tuple[str, str]]:
    node = str(patch.get("node", "?"))
    return {(str(u.get("question")), str(u.get("source_node", node))) for u in patch.get("unknowns") or []}


def superseded_indexes(patches: Sequence[Dict], keep_generations: int = 1) -> List[int]:
    """Positions of the patches a fold no longer reads, and that nothing else needs:
    compacting exactly these leaves the folded state unchanged. A superseded patch is
    kept while it is the only holder of an unknown (unknowns are sticky across generations),
    and `keep_generations` most recent leaf generations of each scope stay hot regardless."""
    live_leaf = {id(p) for p in live_leaf_patches(patches).values()}
    live_answers = {id(p) for p, _ in live_answer_claims(patches).values()}
    by_node: Dict[str, List[Dict]] = {}
    for patch in patches:
        if not is_derived(patch) and not is_answer(patch) and is_complete(patch):
            by_node.setdefault(str(patch.get("node", "?")), []).append(patch)
    hot = set(live_leaf)
    for group in by_node.values():
        group.sort(key=lambda p: (int(p.get("generation") or 1), stable_hash(p)), reverse=True)
        hot.update(id(p) for p in group[:max(1, keep_generations)])
    holders: Dict[Tuple[str, str], int] = {}
    for patch in patches:
        if is_complete(patch) and (id(patch) in hot or id(patch) in live_answers):
            for key in _unknown_keys(patch):
                holders[key] = holders.get(key, 0) + 1
    out: List[int] = []
    for i, patch in enumerate(patches):
        if is_derived(patch) or not is_complete(patch) or id(patch) in hot:
            continue
        if is_answer(patch) and id(patch) in live_answers:
            continue
        if any(key not in holders for key in _unknown_keys(patch)):
            continue
        out.append(i)
    return out
