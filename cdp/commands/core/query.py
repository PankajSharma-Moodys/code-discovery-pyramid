"""`cdp query`."""

from __future__ import annotations

from .._common import Spec, locked, paths_from_args
from ... import query as query_mod
from ...query import suggest as suggest_mod
from ...session import apply_as_of, open_store, route_path
from ...util import CdpError, non_negative_int


SPEC = Spec(
    group='core',
    usage='query <kind> [term]',
    what='Ask the index a question (`stats coverage symbol file module routes table config paths search claims unknowns conflicts trace`). Never budgeted for `stats`/`coverage` — check those before saying "there is no X".',
    next='tip (when rows were elided): `--budget <bigger N>`. Flags: `--json`, `--kind`, `--as-of <sha>`.',
)


def register(add) -> None:
    q = add("query", "ask the extracted state a question")
    q.add_argument("kind", choices=sorted(query_mod.QUERIES))
    q.add_argument("term", nargs="?", default=None)
    q.add_argument("--json", action="store_true", help="emit the full result as JSON")
    q.add_argument("--kind", dest="claim_kind", default=None, help="filter claims by kind")
    q.add_argument("--module", default=None)
    q.add_argument("--subject", default=None)
    q.add_argument("--exclude-role", action="append", default=None, metavar="ROLE",
                   help="drop rows whose file has this role (test, build, ci, "
                        "config, docs, asset, schema, source); repeatable. "
                        "Not supported for `stats`/`coverage`.")
    q.add_argument("--exact", action="store_true",
                   help="`symbol`/`file`/`routes`/`table`/`config`: match the whole name, not a substring")
    q.add_argument("--from", dest="frm", default=None)
    q.add_argument("--to", dest="to", default=None)
    # One knob, not seven. `--limit` used to sit beside eleven unrelated
    # hard-coded caps inside `query.py`; both are now `--budget`, which is
    # counted and reported rather than applied silently.
    q.add_argument("--budget", type=non_negative_int, default=None,
                   help="rows this answer may emit, across every list in it "
                        "(default %d; `stats` and `coverage` are never budgeted)"
                        % query_mod.DEFAULT_BUDGET)
    q.add_argument("--max-hops", type=non_negative_int, default=None,
                   help="`query trace` only: how far to walk from the entry point")
    q.add_argument("--as-of", dest="as_of", default=None, metavar="COMMIT",
                   help="replay the claim log up to this commit's run, against "
                        "the current structural view (M3.7). A commit only -- "
                        "patches carry no timestamp (D8), so a wall-clock cut "
                        "is not supported")
    q.set_defaults(func=cmd_query)


@locked(shared=True)
def cmd_query(args) -> int:
    paths, term, routed = (route_path(paths_from_args(args), args.term) if args.kind == "file"
                           else (paths_from_args(args), args.term, None))
    store = query_mod.Store(open_store(paths))
    if getattr(args, "as_of", None):
        apply_as_of(store, args.as_of)
    # Dispatch itself lives in `query.dispatch` -- shared with `mcp_server`'s
    # `cdp_query` tool (Phase 9, 7.1) so both answer from one `if` ladder.
    try:
        result = query_mod.dispatch(
            store, args.kind, term, budget=args.budget,
            claim_kind=args.claim_kind, module=args.module, subject=args.subject,
            frm=args.frm, to=args.to, max_hops=args.max_hops,
            exclude_role=args.exclude_role, exact=args.exact,
        )
    except ValueError as exc:
        raise CdpError(str(exc))

    if routed:
        result.setdefault("as_of", {})["routed"] = routed
    if args.json:
        print(__import__("json").dumps(result, indent=2, sort_keys=True, ensure_ascii=False))
    else:
        print(query_mod.render(result))
        if result.get("elided", 0) > 0 and not result.get("budget_note"):
            print("tip       --budget <bigger N> to see the rest (%d row(s) elided)"
                  % result["elided"])
        if result.get("not_found"):
            print(suggest_mod.describe(result))
    store.close()
    return 1 if result.get("not_found") else 0
