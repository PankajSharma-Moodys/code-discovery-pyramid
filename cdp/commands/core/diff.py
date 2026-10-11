"""`cdp diff`."""

from __future__ import annotations

from .._common import Spec, locked, paths_from_args
from ... import diffs as diffs_mod, query as query_mod
from ...diffs import current_snapshot_sha, open_diff_side
from ...session import open_store
from ...store import registry as registry_mod
from ...util import CdpError, resolve_prefix
from pathlib import Path


SPEC = Spec(
    group='core',
    usage='diff <old_state> <new_state> | diff --old-sha A --new-sha B',
    what='Typed structural deltas between two scanned snapshots (an omitted side defaults to the current snapshot; git changes not yet re-scanned do not appear).',
    next='tip: `query symbol`/`query table <name>` for full context on a changed item.',
)


def register(add) -> None:
    df = add("diff", "typed structural deltas between two scanned snapshots")
    df.add_argument("old_state", nargs="?", default=None,
                     help="state directory of the earlier snapshot (pass together with "
                          "new_state); omit and use --old-sha/--new-sha instead")
    df.add_argument("new_state", nargs="?", default=None,
                     help="state directory of the later snapshot")
    df.add_argument("--old-sha", default=None, metavar="SHA",
                     help="diff --repo's earlier snapshot by commit sha instead of a "
                          "directory (default: --repo's current/latest scanned snapshot)")
    df.add_argument("--new-sha", default=None, metavar="SHA",
                     help="diff --repo's later snapshot by commit sha instead of a "
                          "directory (default: --repo's current/latest scanned snapshot)")
    df.add_argument("--json", action="store_true")
    df.set_defaults(func=cmd_diff)


def _files(store) -> dict:
    return {f["path"]: f for f in store.inventory["files"]}


@locked(shared=True)
def cmd_diff(args) -> int:
    dir_mode = args.old_state is not None or args.new_state is not None
    sha_mode = args.old_sha is not None or args.new_sha is not None
    if dir_mode and sha_mode:
        raise CdpError("pass either two state directories or --old-sha/--new-sha, not both")

    if dir_mode:
        if args.old_state is None or args.new_state is None:
            raise CdpError("directory mode needs both old_state and new_state")
        old = open_diff_side(Path(args.old_state))
        new = open_diff_side(Path(args.new_state))
        try:
            old_graph, old_xref, old_state = old.graph, old.xref, old.state
            new_graph, new_xref, new_state = new.graph, new.xref, new.state
            old_files, new_files = _files(old), _files(new)
        finally:
            old.close()
            new.close()
    else:
        if not sha_mode:
            raise CdpError("need either two state directories, or --old-sha/--new-sha")
        paths = paths_from_args(args)
        backend = open_store(paths)
        try:
            if not backend.supports_snapshot_history():
                raise CdpError(
                    "%s can't back `cdp diff --old-sha/--new-sha` -- it holds "
                    "exactly one snapshot per directory, with no commit-sha "
                    "lineage to select from. Use `cdp diff <old_dir> <new_dir>` "
                    "instead, or switch this repo's backend to sqlite/postgres."
                    % type(backend).__name__
                )
            repo_id = registry_mod.repo_identity(paths.repo)
            known = [s["commit_sha"] for s in backend.list_snapshots() if s["repo_id"] == repo_id]
            old_sha = (resolve_prefix(args.old_sha, known, "--old-sha") if args.old_sha
                       else current_snapshot_sha(backend, repo_id, paths.repo))
            new_sha = (resolve_prefix(args.new_sha, known, "--new-sha") if args.new_sha
                       else current_snapshot_sha(backend, repo_id, paths.repo))

            backend.use_snapshot(repo_id, old_sha)
            old_store = query_mod.Store(backend, use_latest=False)
            old_graph, old_xref, old_state = old_store.graph, old_store.xref, old_store.state
            old_files = _files(old_store)

            backend.use_snapshot(repo_id, new_sha)
            new_store = query_mod.Store(backend, use_latest=False)
            new_graph, new_xref, new_state = new_store.graph, new_store.xref, new_store.state
            new_files = _files(new_store)
        finally:
            backend.close()

    result = diffs_mod.diff_snapshots(old_graph, old_xref, old_state, new_graph, new_xref, new_state,
                                     old_files, new_files)
    if args.json:
        print(__import__("json").dumps(result, indent=2, sort_keys=True, ensure_ascii=False))
    else:
        print("\n".join(diffs_mod.summarise(result)))
        print("tip       cdp query symbol/table <name> for full context on a changed item above")
    return 0
