"""Genuinely read-only access to a scanned repo's `index.db`.

Why this exists instead of reusing `cdp.store.sqlite_backend.SqliteStore`:
`SqliteStore.__init__` always writes on open -- `_migrate()` runs
`CREATE TABLE IF NOT EXISTS` + `commit()` even with nothing pending, and
`_snapshot_id()` lazily `INSERT OR IGNORE`s a default snapshot row. Both of
those raise `sqlite3.OperationalError: attempt to write a readonly database`
against a `mode=ro` connection, so a web request handler cannot open one --
found while building this module, not assumed from the design doc.

`WEB_RESEARCH.md` §7.0/§7.2.3 is the source of the two invariants this module
enforces: reads never take the CLI's per-repo lock, and reads select the
*manifest-pinned* latest snapshot rather than `SqliteStore.use_latest_snapshot`'s
`touch_seq`-only ordering, so a `refresh` in flight (which bumps `touch_seq`
before `state` is written) never surfaces a fully-structured graph with zero
claims.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any, Optional

from cdp.store import ARTIFACTS
from cdp.store import registry as registry_mod
from cdp.util import CdpError


class StoreUnavailable(CdpError):
    """No scan has ever completed against this state dir (no manifest-pinned
    snapshot exists yet). The app layer turns this into 404, not an
    empty-but-200 graph."""


class StoreLocked(CdpError):
    """The db file is exclusively locked by a concurrent `cdp compact`
    (`VACUUM`) or a crashed writer left a hot journal. The app layer turns
    this into 503 with a message pointing at recovery, never a stack trace
    (§7.0's residual/accepted cases)."""


def resolve_state_dir(repo: Path, state_dir: Optional[str] = None) -> Path:
    """Mirrors `cdp.cli._paths`'s fallback chain, minus the `--in-repo`/
    argparse-`Namespace` shape that function needs: an explicit `state_dir`
    wins outright, otherwise `CDP_STORE` -> `.cdp.toml` -> registry -> `cwd/.cdp`.
    """
    repo = repo.expanduser().resolve()
    if state_dir:
        return Path(state_dir).expanduser().resolve()
    import os
    return registry_mod.resolve_store(repo, env=os.environ.get("CDP_STORE"))


class ReadOnlyConnection:
    """One `mode=ro` sqlite3 connection, thread-local: FastAPI's sync `def`
    handlers run in a threadpool, and sqlite3 connections are not safe to
    share across threads without `check_same_thread=False` plus external
    synchronization neither of which this needs -- one connection per
    request thread is simpler and each is genuinely read-only."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._local = threading.local()

    def _conn(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            if not self.db_path.is_file():
                raise StoreUnavailable(
                    "no index.db at %s -- run `cdp scan` first" % self.db_path
                )
            uri = "file:%s?mode=ro" % self.db_path
            try:
                conn = sqlite3.connect(uri, uri=True, check_same_thread=False)
            except sqlite3.OperationalError as exc:
                raise StoreLocked(
                    "cannot open %s read-only (%s) -- run any `cdp` command "
                    "to recover state, or wait for a running `cdp compact` "
                    "to finish" % (self.db_path, exc)
                ) from exc
            self._local.conn = conn
        return conn

    def latest_pinned_snapshot(self) -> int:
        """The latest snapshot (by `touch_seq`) that has a `manifest`
        artifact row. `manifest` is written last in both the scan and
        refresh write paths (`cdp/cli.py:746`, `:1379`), so its presence is
        already a commit marker -- an in-flight `refresh` has bumped
        `touch_seq` for its new snapshot but not yet written `manifest`
        there, so that snapshot is correctly invisible here."""
        try:
            row = self._conn().execute(
                "SELECT s.id FROM snapshot_meta s "
                "JOIN snapshot_artifact a ON a.snapshot_id = s.id AND a.name = 'manifest' "
                "ORDER BY COALESCE(s.touch_seq, s.id) DESC LIMIT 1"
            ).fetchone()
        except sqlite3.OperationalError as exc:
            raise StoreLocked(
                "%s is locked (%s) -- a `cdp compact` may be running" % (self.db_path, exc)
            ) from exc
        if row is None:
            raise StoreUnavailable(
                "no completed scan in %s yet -- run `cdp scan` first" % self.db_path
            )
        return row[0]

    def read_artifact(self, snapshot_id: int, name: str, default: Any = None) -> Any:
        if name not in ARTIFACTS:
            raise ValueError("unknown artifact %r -- one of %s" % (name, ARTIFACTS))
        row = self._conn().execute(
            "SELECT payload FROM snapshot_artifact WHERE snapshot_id=? AND name=?",
            (snapshot_id, name),
        ).fetchone()
        if row is None:
            if default is None:
                raise StoreUnavailable(
                    "missing artifact %r for snapshot %d in %s" % (name, snapshot_id, self.db_path)
                )
            return default
        return json.loads(row[0])

    def task_rows(self, run_id: str) -> list:
        rows = self._conn().execute(
            "SELECT scope_hash, state, attempts, last_error FROM snapshot_task WHERE run_id=?",
            (run_id,),
        ).fetchall()
        return [
            {"scope_hash": r[0], "state": r[1], "attempts": r[2], "last_error": r[3]}
            for r in rows
        ]

    def read_link_edges(self) -> list:
        """Same query as `SqliteStore.read_link_edges`
        (`cdp/store/sqlite_backend.py:356`) -- `link_edge` is a plain
        payload-blob table, no manifest-pinning concern (link data is fully
        replaced on every `link scan`, per that method's own docstring)."""
        try:
            rows = self._conn().execute(
                "SELECT payload FROM link_edge ORDER BY id"
            ).fetchall()
        except sqlite3.OperationalError as exc:
            raise StoreLocked(
                "%s is locked (%s) -- a `cdp compact` may be running" % (self.db_path, exc)
            ) from exc
        return [json.loads(r[0]) for r in rows]

    def snapshot_id_for_sha(self, repo_id: str, commit_sha: str) -> Optional[int]:
        """`snapshot_meta` is keyed `(repo_id, commit_sha)`
        (`cdp/store/sqlite_backend.py:54-60`) -- the same lookup
        `SqliteStore.use_snapshot` does, read-only. Returns `None` rather than
        raising when the sha was never scanned, so `/api/diff` can 400 with
        the list of shas that *do* exist instead of a bare 404."""
        row = self._conn().execute(
            "SELECT id FROM snapshot_meta WHERE repo_id=? AND commit_sha=?",
            (repo_id, commit_sha),
        ).fetchone()
        return row[0] if row is not None else None

    def known_shas(self, repo_id: str) -> list:
        rows = self._conn().execute(
            "SELECT commit_sha FROM snapshot_meta WHERE repo_id=? ORDER BY id", (repo_id,),
        ).fetchall()
        return [r[0] for r in rows]

    def churn_lookup(self, path: str, since_sha: str, head_sha: str) -> "tuple[bool, Optional[bool]]":
        """Read-only lookup against `churn_cache` (`SCHEMA_V8`,
        `cdp/store/sqlite_backend.py`) -- never shells to `git log`. Returns
        `(hit, churned)`: a request handler that gets `hit=False` must treat
        the claim as `unknown_churn` rather than computing the answer itself
        (`web/api/app.py`'s `_build_status` is the only caller)."""
        try:
            row = self._conn().execute(
                "SELECT churned FROM churn_cache WHERE path=? AND since_sha=? AND head_sha=?",
                (path, since_sha, head_sha),
            ).fetchone()
        except sqlite3.OperationalError as exc:
            if "no such table" in str(exc):
                return False, None
            raise StoreLocked(
                "%s is locked (%s) -- a `cdp compact` may be running" % (self.db_path, exc)
            ) from exc
        if row is None:
            return False, None
        return True, (None if row[0] is None else bool(row[0]))

    def run_status(self, run_id: str) -> Optional[str]:
        """`snapshot_run.status` for `run_id` -- `None` if this run was never
        recorded (a snapshot with no `cdp run` against it yet)."""
        row = self._conn().execute(
            "SELECT status FROM snapshot_run WHERE run_id=?", (run_id,),
        ).fetchone()
        return row[0] if row is not None else None

    def close(self) -> None:
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
            self._local.conn = None
