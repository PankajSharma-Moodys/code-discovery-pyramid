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
from typing import Any, Dict, Optional

from cdp.store import ARTIFACTS
from cdp.store import registry as registry_mod
from cdp.util import CdpError

#: Artifacts safe to cache in-process, keyed by `(db_path, snapshot_id, name)`
#: -- `WEB_REDESIGN_RESEARCH.md` §5 item 3 ("the index is immutable per
#: snapshot"), verified rather than assumed: `cdp/store/sqlite_backend.py`'s
#: `write_artifact` does an upsert keyed on `(snapshot_id, name)`, and
#: `cdp run`'s wave loop (`cdp/cli.py:_fold_and_write`) calls it repeatedly
#: against the *same* snapshot_id for exactly one artifact -- `state` -- to
#: fold in newly-emitted claims wave by wave. `state` is therefore excluded:
#: a request during an in-flight `cdp run` must see each wave's fresh claims,
#: not a cached snapshot from an earlier wave. `manifest` is the pin marker
#: itself (`ReadOnlyConnection.latest_pinned_snapshot`'s presence check) and
#: is tiny, so it's left uncached too rather than reasoning about pin timing.
#: Every other artifact here is written once per scan/refresh, before
#: `manifest` marks that snapshot pinned-and-readable, so a snapshot_id only
#: ever presents one immutable value for any of them.
_CACHEABLE_ARTIFACTS = frozenset(ARTIFACTS) - {"state", "manifest"}
_artifact_cache: Dict["tuple[str, int, str]", Any] = {}
_artifact_cache_lock = threading.Lock()


class StoreUnavailable(CdpError):
    """No scan has ever completed against this state dir (no manifest-pinned
    snapshot exists yet). The app layer turns this into 404, not an
    empty-but-200 graph."""


class StoreLocked(CdpError):
    """The db file is exclusively locked by a concurrent `cdp compact`
    (`VACUUM`) or a crashed writer left a hot journal. The app layer turns
    this into 503 with a message pointing at recovery, never a stack trace
    (§7.0's residual/accepted cases)."""


class StateDirRejected(CdpError):
    """A request named a store other than this machine's one `CDP_HOME` store."""


def resolve_state_dir(repo: Path, state_dir: Optional[str] = None) -> Path:
    """The machine home (`CDP_HOME`, else `~/.cdp`). `state_dir` is accepted only
    as an echo of that same directory (the frontend sends back what `/api/repos`
    reported); any other value is rejected, so a request can never point the
    server at an arbitrary store on disk. `repo` selects rows of the one store."""
    home = registry_mod.cdp_home()
    if state_dir and Path(state_dir).expanduser().resolve() != Path(home).resolve():
        raise StateDirRejected(
            "state_dir must be omitted or equal this server's CDP_HOME store")
    return home


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

    def snapshots(self, repo_id: str) -> list:
        """`repo_id`'s manifest-pinned snapshots, as `snapshot.choose_snapshot` reads them."""
        try:
            rows = self._conn().execute(
                "SELECT s.id, s.repo_id, s.commit_sha, s.ephemeral, s.pinned FROM snapshot_meta s "
                "JOIN snapshot_artifact a ON a.snapshot_id = s.id AND a.name = 'manifest' "
                "WHERE s.repo_id = ? ORDER BY s.id", (repo_id,)).fetchall()
        except sqlite3.OperationalError as exc:
            raise StoreLocked(
                "%s is locked (%s) -- a `cdp compact` may be running" % (self.db_path, exc)
            ) from exc
        return [{"id": r[0], "repo_id": r[1], "commit_sha": r[2], "ephemeral": bool(r[3]),
                 "pinned": bool(r[4])} for r in rows]

    def current_snapshot(self, repo, repo_id: str) -> "tuple[int, Any]":
        """`(snapshot id, Choice)` by the one shared rule (`snapshot.choose_snapshot`):
        HEAD's own, else the nearest clean ancestor, else "scan needed"."""
        from cdp import snapshot as snapshot_mod

        choice = snapshot_mod.choose_snapshot(Path(repo).expanduser().resolve(), repo_id, self.snapshots(repo_id))
        if choice.scan_needed:
            raise StoreUnavailable("scan needed for %s in %s: %s" % (repo_id, self.db_path, choice.reason))
        return choice.row["id"], choice

    def latest_pinned_snapshot(self, repo_id: Optional[str] = None, repo=None) -> int:
        """With `repo`, the snapshot the shared rule picks for that tree (see `current_snapshot`);
        without it, the latest pinned one of `repo_id` (any repo if none is named)."""
        if repo is not None and repo_id:
            return self.current_snapshot(repo, repo_id)[0]
        return self._latest_pinned(repo_id)

    def _latest_pinned(self, repo_id: Optional[str] = None) -> int:
        """The latest snapshot (by `touch_seq`) of `repo_id` -- of any repo if
        none is named -- that has a `manifest` artifact row. `manifest` is written last in both the scan and
        refresh write paths (`cdp/cli.py:746`, `:1379`), so its presence is
        already a commit marker -- an in-flight `refresh` has bumped
        `touch_seq` for its new snapshot but not yet written `manifest`
        there, so that snapshot is correctly invisible here."""
        try:
            row = self._conn().execute(
                "SELECT s.id FROM snapshot_meta s "
                "JOIN snapshot_artifact a ON a.snapshot_id = s.id AND a.name = 'manifest' "
                + ("WHERE s.repo_id = ? " if repo_id else "")
                + "ORDER BY COALESCE(s.touch_seq, s.id) DESC LIMIT 1",
                (repo_id,) if repo_id else (),
            ).fetchone()
        except sqlite3.OperationalError as exc:
            raise StoreLocked(
                "%s is locked (%s) -- a `cdp compact` may be running" % (self.db_path, exc)
            ) from exc
        if row is None:
            raise StoreUnavailable(
                "no completed scan of %s in %s yet -- run `cdp scan` in that repo first"
                % (repo_id or "any repo", self.db_path)
            )
        return row[0]

    def read_artifact(self, snapshot_id: int, name: str, default: Any = None) -> Any:
        if name not in ARTIFACTS:
            raise ValueError("unknown artifact %r -- one of %s" % (name, ARTIFACTS))

        cacheable = name in _CACHEABLE_ARTIFACTS
        cache_key = (str(self.db_path), snapshot_id, name)
        if cacheable:
            with _artifact_cache_lock:
                if cache_key in _artifact_cache:
                    return _artifact_cache[cache_key]

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

        payload = json.loads(row[0])
        if cacheable:
            # Every caller in `web/api/app.py` treats artifacts as read-only
            # (indexing/`.get`/comprehensions, never in-place mutation --
            # checked, not assumed) so handing out the same cached object to
            # concurrent requests is safe.
            with _artifact_cache_lock:
                _artifact_cache[cache_key] = payload
        return payload

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
            try:
                resolutions = {r[0]: json.loads(r[1]) for r in self._conn().execute(
                    "SELECT link_id, payload FROM link_resolution").fetchall()}
            except sqlite3.OperationalError:  # a store from before verdicts had their own table
                resolutions = {}
        except sqlite3.OperationalError as exc:
            raise StoreLocked(
                "%s is locked (%s) -- a `cdp compact` may be running" % (self.db_path, exc)
            ) from exc
        from cdp.linkid import link_id, reanchor

        out = [json.loads(r[0]) for r in rows]
        for entry in out:
            if entry["kind"] == "link" and link_id(entry["data"]) in resolutions:
                entry["data"]["resolution"] = reanchor(entry["data"], resolutions[link_id(entry["data"])])
        return out

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

    def snapshot_history(self, repo_id: str) -> list:
        """Like `known_shas`, plus `created_at` for the time scrubber's
        timeline display. Skips the empty-sha placeholder row a fresh
        `.cdp` directory starts with (never a valid `/api/diff` argument)."""
        rows = self._conn().execute(
            "SELECT commit_sha, created_at FROM snapshot_meta "
            "WHERE repo_id=? AND commit_sha != '' ORDER BY id",
            (repo_id,),
        ).fetchall()
        return [{"commit_sha": r[0], "created_at": r[1]} for r in rows]

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
