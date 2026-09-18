"""`PostgresStore` — `WorkspaceStore` over a shared Postgres database (Phase 7,
M7.6 — `PHASE/phase_7_plan.md` 2.6). Real justification: a multi-team shared
store, not scale for its own sake (`CDP_CLI_SCOPE.md §B`'s stated triggers:
>10M edge rows, or multi-writer).

Needs `psycopg2`, imported lazily so the base `cdp install` (zero dependencies,
`pyproject.toml`) is untouched for anyone not using this backend. Install with
`pip install cdp[postgres]`.

Namespaced by a Postgres **schema**, not a separate database, so many
independent stores can share one server — the conformance suite creates and
drops one schema per test store, the same isolation a fresh `index.db` file
gives `SqliteStore`.

Ports the full `WorkspaceStore` contract, including the run/task/lease/
retention tracking `cdp run`/`cdp gc` need (`WorkspaceStore`'s default
implementations refuse those on a backend that can't support them --
`FileStore` takes that default; this backend overrides it with the real
thing, same as `SqliteStore`). The lease/task claim below is exactly the real
multi-writer case this backend exists for: Postgres row-level locking under
an `UPDATE ... WHERE` gives the same "loser sees 0 rows affected" atomicity
SQLite's file lock gives a single writer.
"""

from __future__ import annotations

import datetime
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from . import WorkspaceStore
from ..util import CdpError, read_json, stable_hash

_VALID_SCHEMA = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")

# Same three tables `SqliteStore`'s M2.2-M2.3 needed to pass this suite,
# ported with JSONB payload columns and an expression index on `->>'node'`
# (0.14's stated mechanism) in place of sqlite's `json_extract`.
SCHEMA_V1 = """
CREATE TABLE IF NOT EXISTS snapshot_meta (
    id SERIAL PRIMARY KEY,
    repo_id TEXT,
    commit_sha TEXT,
    ephemeral BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TEXT NOT NULL,
    UNIQUE(repo_id, commit_sha)
);

CREATE TABLE IF NOT EXISTS snapshot_artifact (
    snapshot_id INTEGER NOT NULL REFERENCES snapshot_meta(id),
    name TEXT NOT NULL,
    payload JSONB NOT NULL,
    PRIMARY KEY (snapshot_id, name)
);

CREATE TABLE IF NOT EXISTS snapshot_report (
    snapshot_id INTEGER NOT NULL REFERENCES snapshot_meta(id),
    name TEXT NOT NULL,
    payload JSONB NOT NULL,
    PRIMARY KEY (snapshot_id, name)
);

CREATE TABLE IF NOT EXISTS claim_patch (
    id SERIAL PRIMARY KEY,
    snapshot_id INTEGER NOT NULL REFERENCES snapshot_meta(id),
    seq INTEGER NOT NULL,
    label TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    payload JSONB NOT NULL,
    is_derived BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TEXT NOT NULL,
    UNIQUE(snapshot_id, content_hash)
);
CREATE INDEX IF NOT EXISTS idx_claim_patch_snapshot_seq ON claim_patch(snapshot_id, seq);
CREATE INDEX IF NOT EXISTS idx_claim_patch_node ON claim_patch (((payload->>'node')));
"""

# Run/task/lease/retention tracking, ported from `SqliteStore`'s SCHEMA_V2-V5
# (`sqlite_backend.py:108-179`) in one additive migration -- no Postgres store
# has ever shipped without this, so there is no earlier version to stage
# through. `link_run`/`link_task` (Phase 8, cross-repo) are deliberately not
# ported: nothing reads them yet, same "created here, populated later"
# posture the plan already takes for the equivalent Sqlite tables.
SCHEMA_V2 = """
ALTER TABLE snapshot_meta ADD COLUMN pinned BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE snapshot_meta ADD COLUMN touch_seq INTEGER;

CREATE TABLE IF NOT EXISTS snapshot_run (
    run_id TEXT PRIMARY KEY,
    snapshot_id INTEGER NOT NULL REFERENCES snapshot_meta(id),
    partition_hash TEXT,
    status TEXT,
    started_at TEXT,
    finished_at TEXT,
    model TEXT,
    template_version TEXT,
    lessons_version TEXT
);

CREATE TABLE IF NOT EXISTS snapshot_task (
    run_id TEXT NOT NULL REFERENCES snapshot_run(run_id),
    scope_hash TEXT NOT NULL,
    state TEXT,
    attempts INTEGER NOT NULL DEFAULT 0,
    dispatched_at TEXT,
    lease_until TEXT,
    last_error TEXT,
    patch_hash TEXT,
    wall_ms INTEGER,
    PRIMARY KEY (run_id, scope_hash)
);
CREATE INDEX IF NOT EXISTS idx_snapshot_task_run_state ON snapshot_task(run_id, state);
"""

MIGRATIONS: Tuple[str, ...] = (SCHEMA_V1, SCHEMA_V2)


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def _lease_ts(seconds: float = 0.0) -> str:
    """A lease deadline, `seconds` from now, at millisecond precision -- same
    contract as `sqlite_backend._lease_ts`, so lexicographic comparison
    between two values agrees with wall-clock order even at test-scale
    (sub-second) lease durations."""
    when = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=seconds)
    return when.isoformat(timespec="milliseconds")


class PostgresStore(WorkspaceStore):
    def __init__(self, dsn: str, schema: str, inbox_root: "Path | None" = None) -> None:
        try:
            import psycopg2
            import psycopg2.extras
        except ImportError as exc:
            raise CdpError(
                "PostgresStore needs psycopg2 -- install with `pip install cdp[postgres]`"
            ) from exc
        if not _VALID_SCHEMA.match(schema):
            raise CdpError("invalid Postgres schema name %r" % schema)
        self._Json = psycopg2.extras.Json
        self._schema = schema
        self._conn = psycopg2.connect(dsn)
        self._conn.autocommit = False
        # A session-level advisory lock, keyed by the schema name, serialises
        # first-time `CREATE SCHEMA`/`CREATE TABLE IF NOT EXISTS` across
        # concurrent constructions of the same schema -- found live: 20
        # threads constructing `PostgresStore` against a not-yet-existing
        # schema simultaneously threw `UniqueViolation` on Postgres's own
        # catalog (`pg_type`), because "IF NOT EXISTS" DDL is not safe under
        # true concurrency without one. The lock is held only around this
        # one-time setup, never around a request in steady state, so it costs
        # nothing once the schema exists.
        with self._conn.cursor() as cur:
            cur.execute("SELECT pg_advisory_lock(hashtext(%s))", (schema,))
            try:
                cur.execute('CREATE SCHEMA IF NOT EXISTS "%s"' % schema)
                self._conn.commit()
                self._migrate()
            finally:
                cur.execute("SELECT pg_advisory_unlock(hashtext(%s))", (schema,))
                self._conn.commit()
        self._inbox_root = Path(inbox_root if inbox_root is not None else Path("."))
        self._snapshot: "int | None" = None

    def _cur(self):
        cur = self._conn.cursor()
        cur.execute('SET search_path TO "%s"' % self._schema)
        return cur

    def _inbox_dir(self) -> Path:
        return self._inbox_root / "patches" / "inbox"

    # ----------------------------------------------------------- snapshots

    def _next_touch_seq(self, cur) -> int:
        cur.execute("SELECT COALESCE(MAX(touch_seq), 0) + 1 FROM snapshot_meta")
        return cur.fetchone()[0]

    def begin_snapshot(self, repo_id: str, commit_sha: str, ephemeral: bool = False) -> None:
        """Bumps `touch_seq` on every call, including a reuse -- `F12`'s fix
        (`sqlite_backend.py:232-250`), ported literally: `use_latest_snapshot`
        must order by "most recently *selected*", not "most recently
        *created*", or moving back to an earlier, already-scanned commit
        would not be recognised as the current one."""
        cur = self._cur()
        cur.execute(
            "SELECT id FROM snapshot_meta WHERE repo_id=%s AND commit_sha=%s",
            (repo_id, commit_sha),
        )
        row = cur.fetchone()
        if row is not None:
            self._snapshot = row[0]
            cur.execute(
                "UPDATE snapshot_meta SET touch_seq=%s WHERE id=%s",
                (self._next_touch_seq(cur), row[0]),
            )
            self._conn.commit()
            return
        cur.execute(
            "INSERT INTO snapshot_meta (repo_id, commit_sha, ephemeral, created_at, touch_seq) "
            "VALUES (%s, %s, %s, %s, %s) RETURNING id",
            (repo_id, commit_sha, ephemeral, _now(), self._next_touch_seq(cur)),
        )
        self._snapshot = cur.fetchone()[0]
        self._conn.commit()

    def mark_durable(self) -> None:
        cur = self._cur()
        cur.execute("SELECT ephemeral FROM snapshot_meta WHERE id=%s", (self._snapshot_id(),))
        row = cur.fetchone()
        self._conn.commit()
        if row and row[0]:
            raise CdpError(
                "snapshot %s is ephemeral (a dirty tree's identity is not reproducible) "
                "and cannot anchor a durable claim" % self._snapshot
            )

    # ---------------------------------------------------------------- schema

    def _migrate(self) -> None:
        cur = self._cur()
        cur.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)")
        cur.execute("SELECT MAX(version) FROM schema_version")
        row = cur.fetchone()
        current = row[0] if row and row[0] is not None else 0
        for version, script in enumerate(MIGRATIONS, start=1):
            if version <= current:
                continue
            cur.execute(script)
            cur.execute("INSERT INTO schema_version (version) VALUES (%s)", (version,))
        self._conn.commit()

    def _snapshot_id(self) -> int:
        """Lazily-created default (`id=1`, ephemeral), same contract as
        `SqliteStore._snapshot_id`. The explicit `id=1` insert must also push
        the `SERIAL` sequence past 1, or the next real `begin_snapshot` insert
        (which lets the sequence assign the id) would collide with it."""
        if self._snapshot is not None:
            return self._snapshot
        cur = self._cur()
        cur.execute("SELECT 1 FROM snapshot_meta WHERE id=1")
        if cur.fetchone() is None:
            cur.execute(
                "INSERT INTO snapshot_meta (id, ephemeral, created_at) VALUES (1, TRUE, %s) "
                "ON CONFLICT (id) DO NOTHING",
                (_now(),),
            )
            cur.execute(
                "SELECT setval(pg_get_serial_sequence('snapshot_meta', 'id'), "
                "GREATEST((SELECT MAX(id) FROM snapshot_meta), 1))"
            )
        self._conn.commit()
        self._snapshot = 1
        return 1

    # ------------------------------------------------------------ artifacts

    def read_artifact(self, name: str, default: Any = None) -> Any:
        cur = self._cur()
        cur.execute(
            "SELECT payload FROM snapshot_artifact WHERE snapshot_id=%s AND name=%s",
            (self._snapshot_id(), name),
        )
        row = cur.fetchone()
        self._conn.commit()
        if row is None:
            if default is None:
                raise CdpError("missing artifact %r in schema %r -- run `scan` first" % (name, self._schema))
            return default
        return row[0]

    def write_artifact(self, name: str, data: Any) -> None:
        cur = self._cur()
        cur.execute(
            "INSERT INTO snapshot_artifact (snapshot_id, name, payload) VALUES (%s, %s, %s) "
            "ON CONFLICT (snapshot_id, name) DO UPDATE SET payload=excluded.payload",
            (self._snapshot_id(), name, self._Json(data)),
        )
        self._conn.commit()

    def has_artifact(self, name: str) -> bool:
        cur = self._cur()
        cur.execute(
            "SELECT 1 FROM snapshot_artifact WHERE snapshot_id=%s AND name=%s",
            (self._snapshot_id(), name),
        )
        row = cur.fetchone()
        self._conn.commit()
        return row is not None

    # -------------------------------------------------------------- reports

    def write_report(self, name: str, data: Any) -> None:
        cur = self._cur()
        cur.execute(
            "INSERT INTO snapshot_report (snapshot_id, name, payload) VALUES (%s, %s, %s) "
            "ON CONFLICT (snapshot_id, name) DO UPDATE SET payload=excluded.payload",
            (self._snapshot_id(), name, self._Json(data)),
        )
        self._conn.commit()

    def read_report(self, name: str, default: Any = None) -> Any:
        cur = self._cur()
        cur.execute(
            "SELECT payload FROM snapshot_report WHERE snapshot_id=%s AND name=%s",
            (self._snapshot_id(), name),
        )
        row = cur.fetchone()
        self._conn.commit()
        if row is None:
            if default is None:
                raise CdpError("missing report %r in schema %r" % (name, self._schema))
            return default
        return row[0]

    # ------------------------------------------------------------ patch log

    def load_patches(self) -> List[Dict]:
        cur = self._cur()
        cur.execute(
            "SELECT payload FROM claim_patch WHERE snapshot_id=%s ORDER BY seq ASC",
            (self._snapshot_id(),),
        )
        rows = cur.fetchall()
        self._conn.commit()
        return [r[0] for r in rows]

    def append_patch(self, patch: Dict, label: str) -> str:
        snapshot_id = self._snapshot_id()
        content_hash = stable_hash(patch)
        cur = self._cur()
        cur.execute(
            "SELECT id FROM claim_patch WHERE snapshot_id=%s AND content_hash=%s AND is_derived=FALSE",
            (snapshot_id, content_hash),
        )
        existing = cur.fetchone()
        if existing is not None:
            self._conn.commit()
            return str(existing[0])
        cur.execute(
            "SELECT COALESCE(MAX(seq), 0) + 1 FROM claim_patch WHERE snapshot_id=%s AND is_derived=FALSE",
            (snapshot_id,),
        )
        seq = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO claim_patch "
            "(snapshot_id, seq, label, content_hash, payload, is_derived, created_at) "
            "VALUES (%s, %s, %s, %s, %s, FALSE, %s) RETURNING id",
            (snapshot_id, seq, label, content_hash, self._Json(patch), _now()),
        )
        new_id = cur.fetchone()[0]
        self._conn.commit()
        return str(new_id)

    def write_derived_patch(self, patch: Dict) -> None:
        snapshot_id = self._snapshot_id()
        cur = self._cur()
        cur.execute("DELETE FROM claim_patch WHERE snapshot_id=%s AND is_derived=TRUE", (snapshot_id,))
        cur.execute(
            "INSERT INTO claim_patch "
            "(snapshot_id, seq, label, content_hash, payload, is_derived, created_at) "
            "VALUES (%s, 0, 'derived', %s, %s, TRUE, %s)",
            (snapshot_id, stable_hash(patch), self._Json(patch), _now()),
        )
        self._conn.commit()

    # ---------------------------------------------------------------- inbox
    # (filesystem handoff with the agent session, same as every backend --
    # see `store/__init__.py`'s module docstring.)

    def ensure_inbox(self) -> None:
        self._inbox_dir().mkdir(parents=True, exist_ok=True)

    def read_inbox(self) -> List[Tuple[str, Any]]:
        inbox = self._inbox_dir()
        if not inbox.is_dir():
            raise CdpError("no inbox at %s -- run `cdp prompts` first" % inbox)
        out: List[Tuple[str, Any]] = []
        for path in sorted(inbox.glob("*.json")):
            try:
                out.append((path.name, read_json(path)))
            except ValueError as exc:
                out.append((path.name, exc))
        return out

    def clear_inbox(self, node: str) -> None:
        (self._inbox_dir() / (node.replace("/", "__") + ".json")).unlink(missing_ok=True)

    def close(self) -> None:
        self._conn.close()

    def supports_run_tracking(self) -> bool:
        return True

    # ------------------------------------------------------- retention (gc)

    def list_snapshots(self) -> List[Dict]:
        cur = self._cur()
        cur.execute(
            "SELECT id, repo_id, commit_sha, ephemeral, pinned, created_at "
            "FROM snapshot_meta ORDER BY id"
        )
        rows = cur.fetchall()
        self._conn.commit()
        return [
            {"id": r[0], "repo_id": r[1], "commit_sha": r[2], "ephemeral": bool(r[3]),
             "pinned": bool(r[4]), "created_at": r[5]}
            for r in rows
        ]

    def set_pinned(self, commit_sha: str, pinned: bool) -> None:
        cur = self._cur()
        cur.execute(
            "UPDATE snapshot_meta SET pinned=%s WHERE commit_sha=%s", (pinned, commit_sha)
        )
        rowcount = cur.rowcount
        self._conn.commit()
        if rowcount == 0:
            raise CdpError("no snapshot for commit %s in schema %r" % (commit_sha, self._schema))

    def delete_snapshot(self, snapshot_id: int) -> None:
        cur = self._cur()
        cur.execute("DELETE FROM claim_patch WHERE snapshot_id=%s", (snapshot_id,))
        cur.execute("DELETE FROM snapshot_artifact WHERE snapshot_id=%s", (snapshot_id,))
        cur.execute("DELETE FROM snapshot_report WHERE snapshot_id=%s", (snapshot_id,))
        cur.execute("DELETE FROM snapshot_meta WHERE id=%s", (snapshot_id,))
        self._conn.commit()

    # --------------------------------------------------------- runs (cdp run)

    def begin_run(self, run_id: str, partition_hash: Optional[str] = None) -> None:
        cur = self._cur()
        cur.execute("SELECT run_id FROM snapshot_run WHERE run_id=%s", (run_id,))
        row = cur.fetchone()
        if row is None:
            cur.execute(
                "INSERT INTO snapshot_run (run_id, snapshot_id, partition_hash, status, started_at) "
                "VALUES (%s, %s, %s, %s, %s)",
                (run_id, self._snapshot_id(), partition_hash, "running", _now()),
            )
        self._conn.commit()

    def finish_run(self, run_id: str, status: str) -> None:
        cur = self._cur()
        cur.execute(
            "UPDATE snapshot_run SET status=%s, finished_at=%s WHERE run_id=%s",
            (status, _now(), run_id),
        )
        self._conn.commit()

    def set_run_lessons_version(self, run_id: str, lessons_version: Optional[int]) -> None:
        cur = self._cur()
        cur.execute(
            "UPDATE snapshot_run SET lessons_version=%s WHERE run_id=%s",
            (None if lessons_version is None else str(lessons_version), run_id),
        )
        self._conn.commit()

    def get_run(self, run_id: str) -> Optional[Dict]:
        cur = self._cur()
        cur.execute(
            "SELECT run_id, partition_hash, status, lessons_version FROM snapshot_run WHERE run_id=%s",
            (run_id,),
        )
        row = cur.fetchone()
        self._conn.commit()
        if row is None:
            return None
        return {"run_id": row[0], "partition_hash": row[1], "status": row[2], "lessons_version": row[3]}

    def upsert_task(self, run_id: str, scope_hash: str, **fields: Any) -> None:
        cur = self._cur()
        cur.execute(
            "SELECT 1 FROM snapshot_task WHERE run_id=%s AND scope_hash=%s", (run_id, scope_hash)
        )
        existing = cur.fetchone()
        if existing is None:
            cols = ["run_id", "scope_hash"] + list(fields.keys())
            placeholders = ", ".join(["%s"] * len(cols))
            cur.execute(
                "INSERT INTO snapshot_task (%s) VALUES (%s)" % (", ".join(cols), placeholders),
                [run_id, scope_hash] + list(fields.values()),
            )
        else:
            cur.execute(
                "UPDATE snapshot_task SET %s WHERE run_id=%%s AND scope_hash=%%s"
                % ", ".join("%s=%%s" % k for k in fields),
                list(fields.values()) + [run_id, scope_hash],
            )
        self._conn.commit()

    def task_states(self, run_id: str) -> Dict[str, Dict]:
        cur = self._cur()
        cur.execute(
            "SELECT scope_hash, state, attempts FROM snapshot_task WHERE run_id=%s", (run_id,)
        )
        rows = cur.fetchall()
        self._conn.commit()
        return {r[0]: {"state": r[1], "attempts": r[2]} for r in rows}

    def task_rows(self, run_id: str) -> List[Dict]:
        cur = self._cur()
        cur.execute(
            "SELECT scope_hash, state, attempts, dispatched_at, lease_until, last_error, "
            "patch_hash, wall_ms FROM snapshot_task WHERE run_id=%s ORDER BY scope_hash",
            (run_id,),
        )
        rows = cur.fetchall()
        self._conn.commit()
        return [
            {"scope_hash": r[0], "state": r[1], "attempts": r[2], "dispatched_at": r[3],
             "lease_until": r[4], "last_error": r[5], "patch_hash": r[6], "wall_ms": r[7]}
            for r in rows
        ]

    # ------------------------------------------------------------- leases

    def acquire_lease(self, run_id: str, scope_hash: str, lease_seconds: float) -> bool:
        now = _lease_ts()
        until = _lease_ts(lease_seconds)
        cur = self._cur()
        cur.execute(
            "UPDATE snapshot_task SET lease_until=%s "
            "WHERE run_id=%s AND scope_hash=%s AND (lease_until IS NULL OR lease_until < %s)",
            (until, run_id, scope_hash, now),
        )
        if cur.rowcount:
            self._conn.commit()
            return True
        cur.execute(
            "SELECT 1 FROM snapshot_task WHERE run_id=%s AND scope_hash=%s", (run_id, scope_hash)
        )
        exists = cur.fetchone()
        if exists is not None:
            self._conn.commit()  # row exists, held by a live lease -- not ours
            return False
        cur.execute(
            "INSERT INTO snapshot_task (run_id, scope_hash, state, attempts, lease_until) "
            "VALUES (%s, %s, 'pending', 0, %s) ON CONFLICT (run_id, scope_hash) DO NOTHING",
            (run_id, scope_hash, until),
        )
        won = cur.rowcount > 0
        self._conn.commit()
        return won

    def heartbeat_lease(self, run_id: str, scope_hash: str, lease_seconds: float) -> None:
        cur = self._cur()
        cur.execute(
            "UPDATE snapshot_task SET lease_until=%s WHERE run_id=%s AND scope_hash=%s",
            (_lease_ts(lease_seconds), run_id, scope_hash),
        )
        self._conn.commit()

    def release_lease(self, run_id: str, scope_hash: str) -> None:
        cur = self._cur()
        cur.execute(
            "UPDATE snapshot_task SET lease_until=NULL WHERE run_id=%s AND scope_hash=%s",
            (run_id, scope_hash),
        )
        self._conn.commit()

    def reclaim_expired(self, run_id: str) -> List[str]:
        now = _lease_ts()
        cur = self._cur()
        cur.execute(
            "SELECT scope_hash FROM snapshot_task WHERE run_id=%s AND state=%s "
            "AND (lease_until IS NULL OR lease_until < %s)",
            (run_id, "dispatched", now),
        )
        hashes = [r[0] for r in cur.fetchall()]
        if hashes:
            cur.executemany(
                "UPDATE snapshot_task SET state='expired', lease_until=NULL "
                "WHERE run_id=%s AND scope_hash=%s",
                [(run_id, h) for h in hashes],
            )
            self._conn.commit()
        else:
            self._conn.commit()
        return hashes

    def copy_folded_tasks(self, old_run_id: str, new_run_id: str, scope_hashes) -> None:
        cur = self._cur()
        for scope_hash in scope_hashes:
            cur.execute(
                "SELECT attempts, dispatched_at, last_error, patch_hash, wall_ms "
                "FROM snapshot_task WHERE run_id=%s AND scope_hash=%s AND state='folded'",
                (old_run_id, scope_hash),
            )
            row = cur.fetchone()
            if row is None:
                continue
            cur.execute(
                "INSERT INTO snapshot_task "
                "(run_id, scope_hash, state, attempts, dispatched_at, last_error, patch_hash, wall_ms) "
                "VALUES (%s, %s, 'folded', %s, %s, %s, %s, %s)",
                (new_run_id, scope_hash) + row,
            )
        self._conn.commit()

    # --------------------------------------------------- snapshot lineage

    def snapshot_id(self) -> int:
        return self._snapshot_id()

    def use_latest_snapshot(self) -> None:
        cur = self._cur()
        cur.execute(
            "SELECT id FROM snapshot_meta ORDER BY COALESCE(touch_seq, id) DESC LIMIT 1"
        )
        row = cur.fetchone()
        self._conn.commit()
        if row is not None:
            self._snapshot = row[0]

    def copy_patches_from(self, source_snapshot_id: int) -> None:
        dest = self._snapshot_id()
        cur = self._cur()
        cur.execute(
            "SELECT seq, label, content_hash, payload, is_derived FROM claim_patch "
            "WHERE snapshot_id=%s ORDER BY seq ASC",
            (source_snapshot_id,),
        )
        rows = cur.fetchall()
        for seq, label, content_hash, payload, is_derived in rows:
            cur.execute(
                "INSERT INTO claim_patch "
                "(snapshot_id, seq, label, content_hash, payload, is_derived, created_at) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (dest, seq, label, content_hash, self._Json(payload), is_derived, _now()),
            )
        self._conn.commit()

    def drop_schema(self) -> None:
        """Test/teardown helper -- drops this store's schema and everything in
        it. Never called by production code paths (there is no `cdp` command
        that destroys a shared team store)."""
        with self._conn.cursor() as cur:
            cur.execute('DROP SCHEMA IF EXISTS "%s" CASCADE' % self._schema)
        self._conn.commit()
