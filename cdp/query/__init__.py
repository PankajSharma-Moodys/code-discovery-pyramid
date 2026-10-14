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

from ..guide_kinds import APPLIES, CLAIM_KINDS, MATCHES, PARAMS, ROLES
from .budget import DEFAULT_BUDGET, UNBUDGETED, Budget
from .common import _as_of, _fair_split_budget, _role_index, _search_rank_key, cite
from .lookup import q_config, q_file, q_module, q_routes, q_symbol, q_table
from .render import render
from .search import q_claims, q_conflicts, q_search, q_unknowns
from .stats import q_coverage, q_stats
from .store import Store
from .suggest import annotate
from .trace import q_paths, q_trace
from . import views


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


def _reject_unused(kind: str, **given) -> None:
    """A parameter the kind ignores is an error, not a silent no-op (E8): the caller
    believes it filtered or scoped the answer when it did not."""
    unused = [p for p, v in given.items() if v not in (None, "", [], ()) and p not in APPLIES[kind]]
    if not unused:
        return
    hints = []
    for p in unused:
        takers = [k for k in QUERIES if p in APPLIES[k]]
        hints.append("`%s` (%s) is used by: %s" % (p, PARAMS[p][0], ", ".join(takers)))
    raise ValueError("`query %s` does not use %s. It takes: %s. %s" % (
        kind, ", ".join("`%s`" % p for p in unused), ", ".join(APPLIES[kind]) or "no parameters",
        "; ".join(hints)))


def _dispatch(
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
    exact: bool = False,
    include_tests: bool = False,
    include_library: bool = False,
    match: Optional[str] = None,
) -> Dict:
    """One dispatch table for `kind` -> the right `QUERIES[kind]` call, shared
    by `cli.cmd_query` and `mcp_server` (7.1) so the MCP tool answers exactly
    what the CLI would, rather than a second, driftable copy of this `if`
    ladder."""
    fn = QUERIES[kind]
    unbudgeted = kind in UNBUDGETED
    for role in exclude_role or ():
        if role not in ROLES:
            raise ValueError("unknown role %r for exclude_role -- one of %s" % (role, ", ".join(ROLES)))
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
    if match is not None and match not in MATCHES:
        raise ValueError("match must be one of %s, got %r" % (", ".join(MATCHES), match))
    if exact and match not in (None, "exact"):
        raise ValueError("`exact` means match=exact; it conflicts with match=%s" % match)
    _reject_unused(kind, term=term, budget=budget, exclude_role=exclude_role, claim_kind=claim_kind,
                   module=module, subject=subject, frm=frm, to=to, max_hops=max_hops, exact=exact or None,
                   include_tests=include_tests or None, include_library=include_library or None, match=match)
    mode = "exact" if exact or match == "exact" else match or "substring"
    exact, regex = mode == "exact", mode == "regex"
    # Noise is off by default: test files (and, for claims, third-party `library:` subjects) are dropped
    # unless the caller opts in. `file` is an explicit path lookup, so it is never filtered by default.
    if "include_tests" in APPLIES[kind] and not include_tests and kind != "file":
        exclude_role = list(dict.fromkeys(list(exclude_role or ()) + ["test"]))
    if kind == "claims" and term and claim_kind and term != claim_kind:
        raise ValueError("`query claims` got term %r and kind %r: pass one (term is shorthand "
                         "for claim_kind)" % (term, claim_kind))
    wanted = claim_kind or (term if kind == "claims" else None)
    if wanted and kind == "claims" and mode != "regex" and wanted not in CLAIM_KINDS:
        raise ValueError("unknown claim kind %r (the term of `query claims` is a claim kind); one of: %s. "
                         "To search subjects use subject=<text>" % (wanted, ", ".join(CLAIM_KINDS)))
    b = None if unbudgeted else Budget(budget)

    if kind in ("symbol", "file", "search"):
        if not term:
            raise ValueError("`query %s` needs a term" % kind)
        if kind == "search":
            return fn(store, term, budget=b, exclude_role=exclude_role, regex=regex)
        return fn(store, term, budget=b, exclude_role=exclude_role, exact=exact, regex=regex)
    if kind == "module":
        if not term:
            raise ValueError("`query module` needs a term")
        return fn(store, term, budget=b, match=mode)
    if kind == "trace":
        if not term:
            raise ValueError("`query trace` needs an entry point")
        kwargs = {} if max_hops is None else {"max_hops": max_hops}
        return fn(store, term, budget=b, exclude_role=exclude_role, match=mode, **kwargs)
    if kind == "unknowns":
        return fn(store, term, budget=b, exclude_role=exclude_role, match=mode)
    if kind in ("routes", "table", "config"):
        return fn(store, term, budget=b, exclude_role=exclude_role, exact=exact, regex=regex)
    if kind == "paths":
        return fn(store, frm, to, budget=b, match=mode)
    if kind == "claims":
        return fn(store, claim_kind or term, module, subject, budget=b, exclude_role=exclude_role,
                  include_library=include_library, match=mode)
    return fn(store)


#: Narrowing parameters beyond term/match that change which rows an answer has: `next` repeats them.
_CARRIED_PARAMS = ("claim_kind", "module", "subject", "frm", "to", "max_hops", "exclude_role",
                   "include_tests", "include_library")


def _carried(term: Optional[str], params: Dict) -> Dict[str, str]:
    """Every parameter that changes the rows a call gave, repeated in a cut answer's `next` so that following
    it asks the same question (an `exact` flag is carried as `match=exact`; roles are comma-joined)."""
    out = {}
    if term:
        out["term"] = term
    match = params.get("match") or ("exact" if params.get("exact") else None)
    if match:
        out["match"] = match
    for name in _CARRIED_PARAMS:
        value = params.get(name)
        if value in (None, "", False, [], ()):
            continue
        out[name] = ",".join(value) if isinstance(value, (list, tuple)) else "true" if value is True else str(value)
    return out


def dispatch(store: Store, kind: str, term: Optional[str] = None, *, view: Optional[str] = None,
             format: Optional[str] = None, offset: Optional[int] = None, max_tokens: Optional[int] = None,
             filter: Optional[str] = None, query_config: Optional[Dict] = None, as_of_extra: Optional[Dict] = None, **params) -> Dict:
    """`_dispatch`, plus `not_found: {term, did_you_mean}` when a name lookup matched nothing (H8), then the
    answer projected to `view`/`format` under the size cap (`views.py`). `query_config` is the repo's
    `.cdp.toml` `[query]`; a call's own `view`, `format` and `max_tokens` override it. `as_of_extra` is
    merged into the answer's `as_of` before projection."""
    for name, value in (("offset", offset), ("max_tokens", max_tokens)):
        if value is not None and (isinstance(value, bool) or not isinstance(value, int) or value < 0):
            raise ValueError("%s must be a non-negative integer, got %r" % (name, value))
    _reject_unused(kind, view=view, format=format, offset=offset or None, max_tokens=max_tokens,
                   filter=filter)
    if filter:
        if view in ("compact", "detail"):
            raise ValueError("filter narrows wide list answers; for one row use term=<name> match=exact")
        view = view or "list"
        if params.get("budget") is not None:
            raise ValueError("budget cuts rows before filter, hiding matches; drop budget (max_tokens and offset "
                             "page a filtered answer)")
    projected = kind not in views.UNPROJECTED
    if projected:
        shape, fmt, cap = views.resolve(kind, view, format, max_tokens, query_config)
        explicit_budget = params.get("budget") is not None
        if not explicit_budget:  # every view is cut by the size cap and paged by `offset`, never pre-cut
            params["budget"] = views.UNLIMITED_ROWS
    result = annotate(store, kind, term, _dispatch(store, kind, term, **params))
    if "include_tests" in APPLIES[kind] and kind != "file":
        dropped = [] if params.get("include_tests") else ["tests"]
        if kind == "claims" and not params.get("include_library"):
            dropped.append("library")
        if dropped:
            result["default_filters"] = ("dropped by default: %s; pass %s to keep them"
                                         % (", ".join(dropped), ", ".join("include_" + d for d in dropped)
                                            .replace("include_tests", "include_tests=true")
                                            .replace("include_library", "include_library=true")))
    if as_of_extra:
        result.setdefault("as_of", {}).update(as_of_extra)
    if not projected:
        return result
    return views.apply(kind, result, view=shape, fmt=fmt, max_tokens=cap, offset=offset or 0,
                       cfg=query_config, explicit_budget=explicit_budget, filter=filter or None,
                       carry=_carried(term, params))
