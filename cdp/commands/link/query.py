"""`cdp link query`."""

from __future__ import annotations

from .._common import Spec, locked, open_link_store, paths_from_args
from ... import link as link_mod
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
    store = open_link_store(args, paths, "query", writable=False)
    try:
        edges = store.read_link_edges()
        repos = [row["repo_id"] for row in store.latest_snapshots() if row.get("repo_id")]
    finally:
        store.close()
    link_mod.require_known_service(edges, args.service, repos)
    result = link_mod.query_service(edges, args.service, repos)
    if args.json:
        print(__import__("json").dumps(result, indent=2, sort_keys=True, ensure_ascii=False))
    else:
        print("\n".join(link_mod.summarise_query(result)))
    return 0
