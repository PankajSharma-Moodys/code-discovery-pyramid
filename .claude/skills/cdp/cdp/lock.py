"""Per-repo mutual exclusion around every command that touches a store.

This is deliberately pessimistic (mutual exclusion), not optimistic
(compare-and-swap). Several of the hazards this closes are not "two writers
raced on one row" -- they are semantic exclusivity requirements that a
version check cannot express: `compact`'s `VACUUM` cannot run while another
connection holds an open write transaction; `refresh` moves the shared
"current snapshot" pointer (`snapshot_meta.touch_seq`), and any command that
reads mid-move gets a torn, cross-commit view with no error raised. A retry-
on-conflict scheme would need to version nearly every table this codebase
has and still wouldn't cover `VACUUM` -- that is reinventing a lock the hard
way. A real lock is simpler and correct.

Scope is per-repo, not global: one lock file per repo identity under
`CDP_HOME/locks/`, even though every repo now shares one `index.db`. Two
processes naming the same repo contend; scans of two different repos run at
once, and SQLite's WAL serialises their short writes.

Postgres is the one case with no shared local directory to lock -- that
backend exists specifically so multiple machines share one server -- so it
takes a session-scoped advisory lock keyed by repo identity instead of a
file lock.

Exclusive (`shared=False`) is for any command that appends a patch, writes
an artifact, moves the snapshot pointer, or touches task/rollback state.
Shared (`shared=True`) is for a command that only needs a torn-write-free
multi-artifact *read* (`query`, `docs`, `status`, `diff`, `export`, `verify`,
`doctor`) -- it blocks a concurrent writer without blocking another reader.
"""

from __future__ import annotations

import fcntl
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, Iterator, Optional

from .util import CdpError, stable_hash

DEFAULT_TIMEOUT_S = 60.0
_POLL_S = 0.2


@contextmanager
def repo_lock(
    paths: "object",
    kind: str,
    pg: Optional[Dict[str, str]],
    shared: bool = False,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    scope: Optional[str] = None,
) -> Iterator[None]:
    """Hold the per-repo lock for the duration of the `with` block.

    `paths` is `cli.Paths` (only `.state`/`.repo` are used, kept untyped here
    to avoid an import cycle with `cli.py`). `kind`/`pg` are `_resolve_backend`'s
    own return value -- this module never re-derives backend config.

    `scope` names a lock that is not one repo's: the `link` commands read many
    repos and replace the one shared link table, so they take `links`.
    """
    key = scope or paths.repo_id
    if kind == "postgres":
        if not pg or not pg.get("dsn"):
            raise CdpError("postgres backend selected but no dsn was resolved -- cannot take the repo lock")
        with _postgres_lock(pg["dsn"], key, shared, timeout_s):
            yield
    else:
        # One lock file per repo, under the machine home: two scans of two
        # different repos run at once (SQLite's WAL serialises their short
        # writes), two commands on the same repo still exclude each other.
        from .store import registry as registry_mod

        lock_dir = Path(paths.state) / "locks"
        with _file_lock(lock_dir, registry_mod.repo_slug(key) + ".lock", shared, timeout_s):
            yield


@contextmanager
def _file_lock(state_dir: Path, name: str, shared: bool, timeout_s: float) -> Iterator[None]:
    state_dir = Path(state_dir).resolve()
    state_dir.mkdir(parents=True, exist_ok=True)
    lock_path = state_dir / name
    fh = open(lock_path, "a+")
    mode = fcntl.LOCK_SH if shared else fcntl.LOCK_EX
    deadline = time.monotonic() + timeout_s
    try:
        while True:
            try:
                fcntl.flock(fh.fileno(), mode | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise CdpError(
                        "another cdp process is already %s this repo in the store (%s) -- waited "
                        "%.0fs. If that process crashed instead of exiting cleanly, "
                        "delete %s and retry."
                        % ("writing to" if not shared else "using", state_dir, timeout_s, lock_path)
                    )
                time.sleep(_POLL_S)
        yield
    finally:
        fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        fh.close()


def _advisory_key(repo_id: str) -> int:
    """A stable signed-bigint key Postgres' advisory-lock functions accept,
    derived from repo identity, not the filesystem path: two checkouts of the
    same repo must contend, and one checkout used from two paths must not slip
    through as "different repos"."""
    digest = stable_hash(repo_id)
    return int(digest[:16], 16) & 0x7FFFFFFFFFFFFFFF


@contextmanager
def _postgres_lock(dsn: str, repo_id: str, shared: bool, timeout_s: float) -> Iterator[None]:
    """A session-scoped advisory lock on a throwaway connection, independent
    of whatever connection the command's own `WorkspaceStore` opens -- an
    advisory lock only needs *some* session to hold it for the duration, so
    this does not need to share a connection with the backend to be correct.
    """
    import psycopg2

    key = _advisory_key(repo_id)
    try_fn = "pg_try_advisory_lock_shared" if shared else "pg_try_advisory_lock"
    unlock_fn = "pg_advisory_unlock_shared" if shared else "pg_advisory_unlock"
    conn = psycopg2.connect(dsn)
    conn.autocommit = True
    deadline = time.monotonic() + timeout_s
    try:
        with conn.cursor() as cur:
            while True:
                cur.execute("SELECT %s(%%s)" % try_fn, (key,))
                if cur.fetchone()[0]:
                    break
                if time.monotonic() >= deadline:
                    raise CdpError(
                        "another cdp process holds the lock for repo %s on this Postgres "
                        "backend -- waited %.0fs" % (repo_id, timeout_s)
                    )
                time.sleep(_POLL_S)
        yield
    finally:
        with conn.cursor() as cur:
            cur.execute("SELECT %s(%%s)" % unlock_fn, (key,))
        conn.close()
