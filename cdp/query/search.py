"""Search, claims, unknowns and conflicts."""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence

from .budget import Budget
from .common import cite, _claim_module, _fair_split_budget, _finish, _matches, _role_index, _search_rank_key
from .store import Store


SEARCHED = "claim subjects and statements, symbol names, constant values, unknown questions, file paths"


def q_search(store: Store, text: str, budget: Optional[Budget] = None,
             exclude_role: Optional[Sequence[str]] = None) -> Dict:
    budget = budget or Budget()
    claims = [
        c for c in store.state["claims"]
        if _matches(c.get("subject", ""), text) or _matches(c.get("statement", ""), text)
    ]
    symbols = sorted(
        (k for k in store.xref["symbols"] if _matches(k, text)),
        key=lambda s: _search_rank_key(s, text),
    )
    unknowns = [u for u in store.state["unknowns"] if _matches(u.get("question", ""), text)]
    # A constant is found by its value too (`"X-Request-Id"`), not only its name.
    named = set(symbols)
    constants = sorted(
        ("%s = %s  %s" % (k, e["value"], cite(e["sites"][0]["anchor"]) if e["sites"] else "-")
         for k, e in store.xref["symbols"].items()
         if k not in named and e.get("value") is not None and _matches(e["value"], text)),
    )
    files = sorted(
        (
            f["path"] for f in store.inventory["files"]
            if _matches(f["path"], text) and not (exclude_role and f["role"] in exclude_role)
        ),
        key=lambda f: _search_rank_key(f, text),
    )
    # Fair-split, not a single shared budget spent in construction order --
    # see `_fair_split_budget`'s docstring for the real-repo failure mode
    # this replaced.
    claims_room, symbols_room, unknowns_room, files_room, constants_room = _fair_split_budget(
        budget.limit, [len(claims), len(symbols), len(unknowns), len(files), len(constants)]
    )
    constants_budget = Budget(constants_room)
    kept_constants = constants_budget.take(constants)
    claims_budget = Budget(claims_room)
    symbols_budget = Budget(symbols_room)
    unknowns_budget = Budget(unknowns_room)
    files_budget = Budget(files_room)
    kept_claims = claims_budget.take(claims)
    kept_symbols = symbols_budget.take(symbols)
    kept_unknowns = unknowns_budget.take(unknowns)
    kept_files = files_budget.take(files)
    budget.spent = (
        claims_budget.spent + symbols_budget.spent
        + unknowns_budget.spent + files_budget.spent + constants_budget.spent
    )
    budget.elided = (
        claims_budget.elided + symbols_budget.elided
        + unknowns_budget.elided + files_budget.elided + constants_budget.elided
    )
    return _finish(
        {
            "query": "search",
            "text": text,
            "counts": {
                "claims": len(claims), "symbols": len(symbols),
                "unknowns": len(unknowns), "files": len(files),
                "constants": len(constants),
            },
            "searched": SEARCHED,
            "not_searched": "file contents (use grep for text inside a file)",
            "claims": kept_claims,
            "symbols": kept_symbols,
            "unknowns": kept_unknowns,
            "files": kept_files,
            "constants": kept_constants,
        },
        store,
        budget,
    )


def q_claims(
    store: Store,
    kind: Optional[str] = None,
    module: Optional[str] = None,
    subject: Optional[str] = None,
    budget: Optional[Budget] = None,
    exclude_role: Optional[Sequence[str]] = None,
) -> Dict:
    budget = budget or Budget()
    claims = store.state["claims"]
    if kind:
        claims = [c for c in claims if c.get("kind") == kind]
    if subject:
        claims = [c for c in claims if _matches(c.get("subject", ""), subject)]
    if module:
        claims = [c for c in claims if _matches(_claim_module(c, store) or "", module)]
    if exclude_role:
        roles = _role_index(store)
        # Dropped only if every evidence anchor is excluded-role.
        claims = [
            c for c in claims
            if any(roles.get(a.get("file")) not in exclude_role for a in c.get("evidence", []))
        ]
    return _finish(
        {"query": "claims", "count": len(claims), "claims": budget.take(claims)},
        store, budget,
    )


def q_unknowns(store: Store, module: Optional[str] = None,
               budget: Optional[Budget] = None,
               exclude_role: Optional[Sequence[str]] = None) -> Dict:
    budget = budget or Budget()
    unknowns = store.state["unknowns"]
    if module:
        unknowns = [u for u in unknowns if _matches(str(u.get("source_node", "")), module)]
    if exclude_role:
        roles = _role_index(store)
        unknowns = [
            u for u in unknowns
            if roles.get((u.get("anchor") or {}).get("file")) not in exclude_role
        ]
    grouped: Dict[str, List[Dict]] = {}
    for row in budget.take(unknowns):
        grouped.setdefault(str(row.get("source_node", "(unattributed)")), []).append(row)
    return _finish(
        {
            "query": "unknowns",
            "count": len(unknowns),
            "by_node": {k: grouped[k] for k in sorted(grouped)},
        },
        store, budget,
    )


def q_conflicts(store: Store, budget: Optional[Budget] = None) -> Dict:
    budget = budget or Budget()
    state = store.state
    return _finish(
        {
            "query": "conflicts",
            "count": len(state.get("conflicts", [])),
            "near_miss_count": len(state.get("near_misses", [])),
            "conflicts": budget.take(state.get("conflicts", [])),
            "near_misses": budget.take(state.get("near_misses", [])),
        },
        store, budget,
    )
