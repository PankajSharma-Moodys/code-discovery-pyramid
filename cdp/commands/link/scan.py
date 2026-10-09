"""`cdp link scan`."""

from __future__ import annotations

from .._common import Spec, locked, paths_from_args
from ... import link as link_mod
from ...link import snapshots_from_dirs
from ...session import open_store
from ...store import SqliteStore
from ...util import CdpError
from pathlib import Path


SPEC = Spec(
    group='link',
    usage='link scan <state_dir>... [--db]',
    what='Matches channel edges within/across scanned state directories (read-only).',
    next='next: `link query --service <name>`. tip (ambiguous matches found): `link prompts --out <dir>`.',
)


def register(lk_sub) -> None:
    lks = lk_sub.add_parser("scan", help="match channel edges within and across scanned "
                                          "state directories -- read-only, writes no snapshot")
    lks.add_argument("state_dirs", nargs="*", metavar="STATE_DIR",
                      help="with none, links every repo in the machine store at the latest "
                           "snapshot of each. Optionally, older stand-alone state "
                           "directories (each with its own index.db) to link instead. "
                           "Each is exploded by its edges' own `module` tag before "
                           "matching, so one whole-monorepo scan already surfaces "
                           "cross-module links; several snapshots additionally match "
                           "across repos (5.5: a link is between snapshots, not repos)")
    lks.add_argument("--json", action="store_true")
    lks.add_argument("--db", default=None,
                      help="also persist this scan's links/unmatched calls into the "
                           "link.* namespace of the store resolved the same way every "
                           "other command's does (the machine store, `CDP_HOME`) -- replaces "
                           "prior contents, since link "
                           "data is fully derived (R3). Pass an explicit path to persist "
                           "into a store other than the one this invocation resolves to")
    lks.set_defaults(func=cmd_link_scan)


@locked(shared=False, scope="links")
def cmd_link_scan(args) -> int:
    """M8.1: read-only across N already-scanned state directories -- N may be
    1, since `link.scan_links` explodes each state dir's pooled edges by
    their own `module` tag before matching, so a single whole-monorepo scan
    already yields cross-module links. R3 -- `link scan` never opens a store
    for writing and never touches `snapshot.*`/`claim.*`; it only reads each
    store's `dataflow.json` and `manifest.json` (for the `(repo, head)`
    identity 5.5 requires).
    """
    paths = paths_from_args(args)
    db_store = SqliteStore(Path(args.db).expanduser().resolve()) if args.db else open_store(paths)
    try:
        if not db_store.supports_link_edges():
            raise CdpError(
                "%s cannot back `cdp link scan` -- needs the sqlite backend "
                "(set `backend = \"sqlite\"` in CDP_HOME/config.toml)" % type(db_store).__name__
            )
        if args.state_dirs:
            snapshots = snapshots_from_dirs(args.state_dirs)
        else:
            snapshots = link_mod.snapshots_from_store(db_store)
            if not snapshots:
                raise CdpError("no scanned repos in %s -- run `cdp scan` in a repo first" % paths.state)
        report = link_mod.scan_links(snapshots)
        db_store.write_link_edges(report)
    finally:
        db_store.close()
    if args.json:
        print(__import__("json").dumps(report, indent=2, sort_keys=True, ensure_ascii=False))
    else:
        print("\n".join(link_mod.summarise(report)))
        print("next      cdp link query --service <name>")
        heuristic = report.get("totals", {}).get("heuristic", 0)
        if heuristic:
            print("tip       cdp link prompts --out <dir> to resolve the %d ambiguous match(es)"
                  % heuristic)
    return 0
