"""Phase 6 (M6.4) — tiering v1: a rule, not a score.

Tiers: T0 structure / T1 derived characterisation (both free, already computed
by `scan`) -> T2 label from digest (cheap, local model) -> T3 semantic read
(frontier, residue only). `phase_6_plan.md` M6.4 is explicit that v1 ships a
rule, not the residue score (`CDP_CLI_SCOPE.md §N`, deferred): everything
gets T2; escalate to T3 only when the scope has an unresolved import
(pre-dispatch, free — reused from `graph.py`'s own symbol index) or the leaf
itself escalated (post-dispatch, from the `escalated: true` claim flag M6.3
already emits). That is the entire rule.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Set, Tuple

from .graph import build_symbol_index, owners_of, _looks_third_party

T2 = "T2"
T3 = "T3"

UNRESOLVED_IMPORTS = "unresolved_imports"
LEAF_ESCALATED = "leaf_escalated"


def build_symbol_index_for_tiering(extraction: Dict) -> Tuple[Dict[str, List[str]], Dict[str, List[str]]]:
    """One symbol index, built once per scan/prompts run and passed to every
    scope's `compute_tier` call — `build_symbol_index` scans all of
    `extraction`, so per-scope re-building would be quadratic in scope count."""
    return build_symbol_index(extraction)


def scope_unresolved_imports(
    scope: Dict,
    extraction: Dict,
    module_set: Set[str],
    symbol_owner: Dict[str, List[str]],
    namespace_owner: Dict[str, List[str]],
) -> int:
    """Count of this scope's own import rows that resolve to no internal
    module and are not third-party/stdlib-shaped — the same
    internal/external split `graph.build_graph` uses, just scoped to one
    scope's files rather than the whole repository."""
    module = scope["module"]
    files = set(scope["files"])
    count = 0
    for row in extraction["imports"]:
        if row["module"] != module or row["file"] not in files:
            continue
        owners = owners_of(row["fqn"], symbol_owner, namespace_owner)
        internal = [o for o in owners if o in module_set and o != module]
        if internal:
            continue
        if owners:
            continue
        if _looks_third_party(row["fqn"]):
            continue
        count += 1
    return count


def compute_tier(
    scope: Dict,
    extraction: Dict,
    module_set: Set[str],
    symbol_owner: Dict[str, List[str]],
    namespace_owner: Dict[str, List[str]],
) -> Dict:
    """The v1 rule's pre-dispatch half: T3 iff this scope has an unresolved
    import, else T2. The post-dispatch half (a T2 leaf that escalates) is
    applied afterward by `apply_leaf_escalation`, once a patch actually
    exists to read `escalated` from."""
    unresolved = scope_unresolved_imports(scope, extraction, module_set, symbol_owner, namespace_owner)
    if unresolved:
        return {"tier": T3, "reason": UNRESOLVED_IMPORTS, "unresolved_imports": unresolved}
    return {"tier": T2, "reason": None, "unresolved_imports": 0}


def apply_leaf_escalation(tiering: Dict[str, Dict], node: str, claims: List[Dict]) -> bool:
    """A T2 leaf's own claims may self-report `escalated: true` (M6.3). If any
    did, the scope's tier record is upgraded to T3 in place, reason
    `leaf_escalated`, without touching an already-T3 (unresolved_imports)
    record — that reason fired first and is not overwritten by a later one.
    Returns whether an upgrade happened."""
    if not any(c.get("escalated") for c in claims):
        return False
    row = tiering.setdefault(node, {"tier": T2, "reason": None, "unresolved_imports": 0})
    if row["tier"] == T3:
        return False
    row["tier"] = T3
    row["reason"] = LEAF_ESCALATED
    return True
