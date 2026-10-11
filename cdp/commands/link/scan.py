"""`cdp link scan`."""

from __future__ import annotations

from .._common import Spec, locked, open_link_store, paths_from_args
from ... import link as link_mod
from ...link import snapshots_from_dirs
from ...util import CdpError


SPEC = Spec(
    group='link',
    usage='link scan <state_dir>... [--db [PATH]]',
    what='Matches channel edges across every scanned repo (does not modify the index unless `--db`; the only files it touches are the one empty lock `locks/links-*.lock`, reused, and SQLite\'s `index.db-shm`).',
    next='next: `link query --service <name>`. tip (ambiguous matches found): `link prompts --out <dir>`.',
)


def register(lk_sub) -> None:
    lks = lk_sub.add_parser("scan", help="match channel edges within and across scanned "
                                          "state directories -- does not modify the index (only the one reused "
                                          "locks/links-*.lock file and SQLite's index.db-shm are touched)")
    lks.add_argument("state_dirs", nargs="*", metavar="STATE_DIR",
                      help="with none, links every repo in the machine store at the latest "
                           "snapshot of each. Optionally, older stand-alone state "
                           "directories (each with its own index.db) to link instead. "
                           "Each is exploded by its edges' own `module` tag before "
                           "matching, so one whole-monorepo scan already surfaces "
                           "cross-module links; several snapshots additionally match "
                           "across repos (5.5: a link is between snapshots, not repos)")
    lks.add_argument("--json", action="store_true")
    lks.add_argument("--db", nargs="?", const="", default=None, metavar="PATH",
                      help="persist this scan's links/unmatched calls (replacing prior ones; "
                           "verdicts on them are kept) so `link query`/`prompts`/`run` can use "
                           "them. Bare `--db` persists into the machine store (`CDP_HOME`); "
                           "`--db PATH` into that existing index.db. Without it the scan "
                           "does not modify the index")
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
    persist = args.db is not None
    if args.db == "":
        args.db = None  # bare --db: the machine store
    db_store = open_link_store(args, paths, "scan", writable=persist)
    try:
        if args.state_dirs:
            snapshots = snapshots_from_dirs(args.state_dirs)
        else:
            snapshots = link_mod.snapshots_from_store(db_store)
            if not snapshots:
                raise CdpError("no scanned repos in %s -- run `cdp scan` in a repo first" % paths.state)
        names = link_mod.repo_names(db_store)
        report = link_mod.scan_links(snapshots)
        if persist:
            db_store.write_link_edges(report)  # replaces the links; verdicts on them are kept
    finally:
        db_store.close()
    if args.json:
        print(__import__("json").dumps(report, indent=2, sort_keys=True, ensure_ascii=False))
    else:
        print("\n".join(link_mod.summarise(report, names)))
        print("next      cdp link scan --db to save these, then cdp link query --service <name>"
              if not persist else "next      cdp link query --service <name>")
        heuristic = report.get("totals", {}).get("heuristic", 0)
        if heuristic and persist:
            print("tip       cdp link prompts --out <dir> to resolve the %d ambiguous match(es)"
                  % heuristic)
    return 0
