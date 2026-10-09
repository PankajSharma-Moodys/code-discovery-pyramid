"""`cdp link query`."""

from __future__ import annotations

from .._common import Spec, locked, paths_from_args
from ... import link as link_mod
from ...session import open_store
from ...store import SqliteStore
from ...util import CdpError
from pathlib import Path


SPEC = Spec(
    group='link',
    usage='link query --service <name> --db',
    what='Who calls a service / what it calls that went unmatched.',
    next='—',
)


def register(lk_sub) -> None:
    lkq = lk_sub.add_parser("query", help="who calls a service / what it calls that "
                                           "is not registered anywhere -- from the last "
                                           "persisted `link scan --db`")
    lkq.add_argument("--db", default=None,
                      help="read from this SqliteStore's link.* namespace instead of "
                           "the one this invocation resolves to (same default-resolution "
                           "rule as every other command: the machine store)")
    lkq.add_argument("--service", required=True, help="repo name/identifier to query, "
                                                        "as it appears in a scanned manifest's `repo` field")
    lkq.add_argument("--json", action="store_true")
    lkq.set_defaults(func=cmd_link_query)


@locked(shared=True, scope="links")
def cmd_link_query(args) -> int:
    """M8.2 (5.6): reads back the `link.*` rows a prior `link scan --db`
    persisted and renders what touches one service -- links either direction,
    and that service's own unmatched outbound calls as a named deliverable
    rather than an absence.
    """
    paths = paths_from_args(args)
    store = SqliteStore(Path(args.db).expanduser().resolve()) if args.db else open_store(paths)
    try:
        if not store.supports_link_edges():
            raise CdpError(
                "%s cannot back `cdp link query` -- needs the sqlite backend "
                "(pass --db, or set `backend = \"sqlite\"` in CDP_HOME/config.toml)" % type(store).__name__
            )
        edges = store.read_link_edges()
    finally:
        store.close()
    result = link_mod.query_service(edges, args.service)
    if args.json:
        print(__import__("json").dumps(result, indent=2, sort_keys=True, ensure_ascii=False))
    else:
        print("\n".join(link_mod.summarise_query(result)))
    return 0
