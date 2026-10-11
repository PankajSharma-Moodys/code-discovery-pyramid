"""`cdp link refresh`."""

from __future__ import annotations

import json

from .._common import Spec, locked, open_link_store, paths_from_args
from ... import link as link_mod
from ...link import read_link_report, snapshots_from_dirs
from ...util import CdpError
from pathlib import Path


SPEC = Spec(
    group='link',
    usage='link refresh <state_dir>... --db',
    what="Re-verifies a prior `link scan --db`'s contracts against freshly scanned state.",
    next='next: `link query --service <name>`.',
)


def register(lk_sub) -> None:
    lkr = lk_sub.add_parser("refresh", help="re-verify a prior `link scan --db`'s contracts "
                                             "against freshly scanned state directories (M8.4, 5.3)")
    lkr.add_argument("state_dirs", nargs="*", metavar="STATE_DIR",
                      help="with none, re-verifies against every repo in the machine store at "
                           "its latest snapshot; or freshly scanned stand-alone state "
                           "directories -- a repo not named here is left byte-identical in "
                           "the persisted report")
    lkr.add_argument("--json", action="store_true")
    lkr.add_argument("--db", default=None,
                      help="the store holding the prior `link scan --db` to refresh (default: the machine store)")
    lkr.set_defaults(func=cmd_link_refresh)


@locked(shared=False, scope="links")
def cmd_link_refresh(args) -> int:
    """M8.4 (5.3): re-verify a prior `link scan --db`'s contracts against
    freshly scanned state directories for the repo(s) named here, mirroring
    Phase 3's refresh semantics (D10) -- an endpoint that still exists
    carries forward re-anchored; one that vanished decays with a stated
    reason. R3 still holds: nothing here touches `snapshot.*`/`claim.*`, and
    a repo not named in `state_dirs` is left byte-identical in the persisted
    report (5.5).
    """
    paths = paths_from_args(args)
    db_store = open_link_store(args, paths, "refresh", writable=True)
    try:
        snapshots = (snapshots_from_dirs(args.state_dirs) if args.state_dirs
                     else link_mod.snapshots_from_store(db_store))
        old_report = read_link_report(db_store)
        report = link_mod.refresh_links(old_report, snapshots)
        db_store.write_link_edges(report)
    finally:
        db_store.close()
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False))
    else:
        print("\n".join(link_mod.summarise_refresh(report)))
        print("next      cdp link query --service <name>")
    return 0
