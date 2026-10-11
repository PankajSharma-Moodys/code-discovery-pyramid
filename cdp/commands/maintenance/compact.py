"""`cdp compact`."""

from __future__ import annotations

from .._common import Spec, locked, paths_from_args
from ... import query as query_mod
from ...session import fold_and_write, open_store
from ...store import SqliteStore
from ...util import CdpError, fraction, positive_int
from pathlib import Path


SPEC = Spec(
    group='maintenance',
    usage='compact [--keep-generations N] [--compact-threshold F]',
    what='Moves superseded `complete` patch generations to the cold archive.',
    next='tip (something moved): `export --format archive` to inspect it.',
)


def register(add) -> None:
    cp = add("compact", "move superseded patch generations to the cold archive")
    cp.add_argument("--db", default=None,
                     help="path to a SqliteStore index.db (default: the resolved store's)")
    cp.add_argument("--compact-threshold", type=fraction, default=0.30,
                     help="minimum fraction of superseded rows required to act (default 0.30)")
    cp.add_argument("--keep-generations", type=positive_int, default=1,
                     help="generations of each scope kept hot, at least 1 -- a performance knob, "
                          "not a retention decision: the live set never moves and nothing is lost, "
                          "only archived (default 1)")
    cp.add_argument("--dry-run", action="store_true", help="report what would move, move nothing")
    cp.set_defaults(func=cmd_compact)


@locked(shared=False)
def cmd_compact(args) -> int:
    """M7.3/2.4: move superseded `complete` generations to the cold archive.
    `--keep-generations` is a performance knob, never a retention decision --
    the archive is read by `verify --full` and `export --archive`, never
    silently dropped."""
    paths = paths_from_args(args)
    store = SqliteStore(Path(args.db).expanduser().resolve()) if args.db else open_store(paths)
    if not store.supports_compaction():
        raise CdpError(
            "%s cannot back `cdp compact` -- needs the sqlite backend" % type(store).__name__
        )
    try:
        result = store.compact(
            keep_generations=args.keep_generations,
            threshold=args.compact_threshold,
            dry_run=args.dry_run,
        )
        if not result["threshold_met"]:
            print("compact   %.0f%% superseded (< --compact-threshold %.0f%%) -- nothing moved"
                  % (result["eligible_ratio"] * 100, args.compact_threshold * 100))
        else:
            print("compact   moved %d superseded patch(es) to the archive, kept %d%s"
                  % (result["moved"], result["kept"], " [dry-run]" if args.dry_run else ""))
            if result["moved"] and not args.dry_run:
                if not args.db and store.has_artifact("state"):
                    view = query_mod.Store(store)
                    fold_and_write(store, view.xref, view.partition, repo=paths.repo)
                    print("folded    state re-derived from the compacted log (live claims unchanged)")
                print("tip       cdp export --format archive to inspect the cold archive")
    finally:
        store.close()
    return 0
