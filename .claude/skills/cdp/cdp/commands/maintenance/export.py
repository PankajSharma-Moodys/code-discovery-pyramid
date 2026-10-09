"""`cdp export`."""

from __future__ import annotations

from .._common import Spec, locked, paths_from_args
from ... import export as export_mod
from ...session import open_store
from ...store import SqliteStore
from ...util import CdpError
from pathlib import Path


SPEC = Spec(
    group='maintenance',
    usage='export --format {json,patches,archive,anonymized} --out DIR',
    what='Canonical JSON / reviewable patches / archive dump / anonymised corpus.',
    next='tip (`json` format): `--format patches` for a reviewable dump, `--format archive` to include the cold archive.',
)


def register(add) -> None:
    ex = add("export", "canonical JSON / reviewable patches / archive dump / anonymised corpus")
    ex.add_argument("--format", choices=["json", "patches", "archive", "anonymized"],
                     default="json")
    ex.add_argument("--out", required=True, metavar="DIR", help="destination directory")
    ex.add_argument("--db", default=None,
                     help="path to a SqliteStore index.db (default: the resolved store's)")
    ex.set_defaults(func=cmd_export)


@locked(shared=True)
def cmd_export(args) -> int:
    """M7.5 (0.19): four fixed output shapes -- `cdp/export.py` has the full
    account of each."""
    paths = paths_from_args(args)
    store = SqliteStore(Path(args.db).expanduser().resolve()) if args.db else open_store(paths)
    dest = Path(args.out).expanduser().resolve()
    try:
        if args.format == "json":
            written = export_mod.export_json(store, dest)
            print("export    json      %d artifact(s)/report(s) -> %s" % (len(written), dest))
            print("tip       --format patches for a reviewable dump, "
                  "--format archive to include the cold archive")
        elif args.format == "patches":
            n = export_mod.export_patches(store, dest)
            print("export    patches   %d patch(es) -> %s" % (n, dest))
        elif args.format == "archive":
            if not store.supports_compaction():
                raise CdpError(
                    "%s has no cold archive -- `cdp export --format archive` needs "
                    "the sqlite backend" % type(store).__name__
                )
            n = export_mod.export_archive(store, dest)
            print("export    archive   %d row(s) -> %s" % (n, dest))
        else:
            counts = export_mod.export_anonymized(store, dest)
            print("export    anonymized  %d claim(s), %d unknown(s), %d conflict(s) -> %s"
                  % (counts["claims"], counts["unknowns"], counts["conflicts"], dest))
    finally:
        store.close()
    return 0
