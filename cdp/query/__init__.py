"""The query layer.

RESEARCH.md §7.2 describes the knowledge graph as "the queryable substrate:
'what breaks if I change this table' is a graph query, not a grep." This module
is that substrate's interface, and it is the reason the whole pipeline is worth
running: documents go stale, a queryable index pinned to a commit does not.

Every answer carries `file:line` citations, and every answer is computed from
verified state — never from a model. `used-by` is the transpose of the import
table, `routes` come from constant-resolved annotations, `table` comes from
migration DDL. Asking a model "where is DServer used?" is asking a question it
answers confidently and wrongly; asking this module is asking for an inversion
of data that was checked.

The queries are deliberately the ones a joiner actually asks, in the order they
ask them: what are the entry points, who owns this table, where does this symbol
go, what is still unknown.

**Nothing here truncates silently.** Every list that can be cut is cut through
`Budget`, which counts the cut and reports it, and every response carries the
commit and state generation it was computed from. The reason is in
`SKILL.md:58-61`: *"Check coverage before saying 'there is no X'. If it is below
100%, absence of a fact means 'not examined', not 'not present'."* A renderer
that prints 6 of 47 config read-sites with no marker manufactures exactly the
false absence that rule exists to prevent — and unlike low coverage it is
invisible, because `coverage` still reads 100%.
"""

from __future__ import annotations

from typing import Callable, Dict, Optional, Sequence

from .budget import DEFAULT_BUDGET, UNBUDGETED, Budget
from .common import _as_of, _fair_split_budget, _role_index, _search_rank_key, cite
from .lookup import q_config, q_file, q_module, q_routes, q_symbol, q_table
from .render import render
from .search import q_claims, q_conflicts, q_search, q_unknowns
from .stats import q_coverage, q_stats
from .store import Store
from .trace import q_paths, q_trace


QUERIES: Dict[str, Callable] = {
    "symbol": q_symbol,
    "file": q_file,
    "module": q_module,
    "routes": q_routes,
    "table": q_table,
    "config": q_config,
    "paths": q_paths,
    "trace": q_trace,
    "search": q_search,
    "claims": q_claims,
    "unknowns": q_unknowns,
    "conflicts": q_conflicts,
    "stats": q_stats,
    "coverage": q_coverage,
}


def dispatch(
    store: Store,
    kind: str,
    term: Optional[str] = None,
    *,
    budget: Optional[int] = None,
    claim_kind: Optional[str] = None,
    module: Optional[str] = None,
    subject: Optional[str] = None,
    frm: Optional[str] = None,
    to: Optional[str] = None,
    max_hops: Optional[int] = None,
    exclude_role: Optional[Sequence[str]] = None,
) -> Dict:
    """One dispatch table for `kind` -> the right `QUERIES[kind]` call, shared
    by `cli.cmd_query` and `mcp_server` (7.1) so the MCP tool answers exactly
    what the CLI would, rather than a second, driftable copy of this `if`
    ladder."""
    fn = QUERIES[kind]
    unbudgeted = kind in UNBUDGETED
    if unbudgeted and budget is not None:
        raise ValueError(
            "`query %s` is never budgeted: it is the check meant to run "
            "before concluding that something is absent, and a budgeted "
            "guardrail cannot detect a budgeted answer." % kind
        )
    if unbudgeted and exclude_role:
        raise ValueError(
            "`query %s` does not support --exclude-role: it is a whole-repo "
            "census, and silently dropping rows would misreport it." % kind
        )
    b = None if unbudgeted else Budget(budget)

    if kind in ("symbol", "file", "search"):
        if not term:
            raise ValueError("`query %s` needs a term" % kind)
        return fn(store, term, budget=b, exclude_role=exclude_role)
    if kind == "module":
        if not term:
            raise ValueError("`query module` needs a term")
        return fn(store, term, budget=b)
    if kind == "trace":
        if not term:
            raise ValueError("`query trace` needs an entry point")
        kwargs = {} if max_hops is None else {"max_hops": max_hops}
        return fn(store, term, budget=b, exclude_role=exclude_role, **kwargs)
    if kind in ("routes", "table", "config", "unknowns"):
        return fn(store, term, budget=b, exclude_role=exclude_role)
    if kind == "paths":
        return fn(store, frm, to, budget=b)
    if kind == "claims":
        return fn(store, claim_kind or term, module, subject, budget=b, exclude_role=exclude_role)
    return fn(store)
