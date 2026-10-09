"""`cdp compact`."""

from __future__ import annotations

from .._common import Spec, locked, paths_from_args
from ...session import open_store
from ...store import SqliteStore
from ...util import CdpError
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
    cp.add_argument("--compact-threshold", type=float, default=0.30,
                     help="minimum fraction of superseded rows required to act (default 0.30)")
    cp.add_argument("--keep-generations", type=int, default=1,
                     help="generations kept hot per (snapshot, node) -- a performance knob, "
                          "not a retention decision: nothing is lost, only archived (default 1)")
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
                print("tip       cdp export --format archive to inspect the cold archive")
    finally:
        store.close()
    return 0
