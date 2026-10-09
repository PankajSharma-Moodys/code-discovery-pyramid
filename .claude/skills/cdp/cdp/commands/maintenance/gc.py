"""`cdp gc`."""

from __future__ import annotations

from .._common import Spec, locked, paths_from_args
from ... import snapshot as snapshot_mod
from ...session import git_head_or_raise, open_store
from ...store import SqliteStore, registry as registry_mod
from ...util import CdpError
from pathlib import Path


SPEC = Spec(
    group='maintenance',
    usage='gc [--pin SHA] [--unpin SHA] [--dry-run]',
    what='Drops snapshots not kept by the retention rule (HEAD, pinned, or cited by a live claim).',
    next='tip (something dropped): `compact` to also fold superseded patches into the cold archive.',
)


def register(add) -> None:
    gc = add("gc", "drop snapshots not kept by the retention rule")
    gc.add_argument("--db", default=None,
                     help="path to a SqliteStore index.db (default: the resolved store's)")
    gc.add_argument("--head-sha", default=None,
                    help="commit sha to treat as HEAD (default: `git -C --repo` HEAD)")
    gc.add_argument("--pin", action="append", default=[], metavar="SHA",
                    help="mark a commit's snapshot pinned before computing retention (repeatable)")
    gc.add_argument("--unpin", action="append", default=[], metavar="SHA")
    gc.add_argument("--dry-run", action="store_true", help="report what would be dropped, drop nothing")
    gc.set_defaults(func=cmd_gc)


@locked(shared=False)
def cmd_gc(args) -> int:
    """M3.6/0.10: a snapshot is kept iff HEAD, pinned, or cited by a live
    claim's `anchor_verified_at`/`claim_reviewed_at`.

    `--db` is an explicit escape hatch straight to a `SqliteStore` file --
    for retention against a store `paths_from_args()`/`.cdp.toml` would not resolve to
    on its own. Without it, `gc` resolves the backend the same way every
    other command does (`open_store`), so it now genuinely works against a
    `.cdp.toml`-configured Postgres backend too, not just the sqlite default.
    """
    paths = paths_from_args(args)
    store = SqliteStore(Path(args.db).expanduser().resolve()) if args.db else open_store(paths)
    if not store.supports_run_tracking():
        raise CdpError(
            "%s has no run/task tracking -- `cdp gc` needs the sqlite or "
            "postgres backend" % type(store).__name__
        )
    try:
        repo = paths.repo
        repo_id = registry_mod.repo_identity(repo)
        for sha in args.pin:
            store.set_pinned(sha, True, repo_id)
        for sha in args.unpin:
            store.set_pinned(sha, False, repo_id)
        head_sha = args.head_sha or git_head_or_raise(repo)
        snapshots = [s for s in store.list_snapshots() if s["repo_id"] == repo_id]
        if not any(s["commit_sha"] == head_sha for s in snapshots):
            raise CdpError("no snapshot for HEAD (%s) in this store -- run `cdp scan` against it first"
                            % head_sha[:12])
        store.begin_snapshot(repo_id, head_sha)
        head_claims = store.read_artifact("state", {}).get("claims", [])
        cited = {c.get("anchor_verified_at") for c in head_claims} | {c.get("claim_reviewed_at") for c in head_claims}
        cited.discard(None)
        keep_ids = snapshot_mod.snapshots_to_keep(snapshots, repo_id, head_sha, cited)
        drop = [s for s in snapshots if s["id"] not in keep_ids]
        print("gc        keeping %d/%d snapshot(s) (head + pinned + cited), dropping %d"
              % (len(snapshots) - len(drop), len(snapshots), len(drop)))
        for s in drop:
            print("          drop %s%s" % ((s["commit_sha"] or "?")[:12], " [dry-run]" if args.dry_run else ""))
            if not args.dry_run:
                store.delete_snapshot(s["id"])
        if drop and not args.dry_run:
            print("tip       cdp compact to also fold superseded patches into the cold archive")
    finally:
        store.close()
    return 0
