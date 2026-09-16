"""`SqliteStore` — `WorkspaceStore` over one SQLite file (`PHASE/phase_2_plan.md`
M2.2 - M2.5). **The only module that imports `sqlite3`** — enforced by
`tests/test_store_sqlite.py`. Three namespaces, one file:

    snapshot_*   structure. Immutable, disposable, per-commit.
    claim_*      claims, patches, lineage. Precious, spans snapshots.
    link_*       cross-repo, derived. Created here, populated in Phase 8.

(SQLite has no schemas without `ATTACH`, so the namespace is the table-name
prefix rather than a SQL schema.)

`claim_patch` is append-only, immutable and **content-addressed**: the row key
is `(snapshot_id, content_hash)` where `content_hash = stable_hash(patch)` over
the *whole* patch dict, including `run_id` — so a patch that differs only in
`run_id` is a different row, never silently merged into an earlier attempt
(the stress test `PHASE/phase_2_plan.md` names: "content-addressing must not
drop a differing run_id needed for audit").

**Snapshots (M2.4, 0.6/0.7).** `snapshot_meta` is keyed by `(repo_id,
commit_sha)`; `begin_snapshot` selects or creates a row and every subsequent
call applies to it, so N snapshots coexist in one file and an old one's
artifacts/patches stay queryable after a new one is created. A caller that
never calls `begin_snapshot` gets a lazily-created default (`id=1`) — every
M2.2/M2.3 conformance test, and any use of this backend before M2.4.

**Runs/tasks (M2.5, 0.12/0.13) are schema only** — "created here, driven in
Phase 5" per the plan. `snapshot_run`/`snapshot_task` are not exposed through
`WorkspaceStore`: there is nothing to populate yet, and `FileStore` has no
equivalent to conform to (the same reasoning as `claim_patches_archive` and
`link_edge` below). `link_run`/`link_task` are the `link.*` counterparts,
kept structurally separate per R3 (`tests/test_store_sqlite.py`
`test_dropping_every_link_row_leaves_snapshot_and_claim_untouched`).

**Deferred index.** 0.14/0.15 ask for expression indexes on `$.subject` and
`$.kind` — those are per-*claim* fields, and claims are still nested inside
patch payloads (unnesting them into their own rows is bigger than any single
remaining milestone in this phase). Indexing those two fields now would index
a path nothing queries yet. `$.node` is indexed instead, since it is a
patch-level field queried by `load_patches`/`collect` today.
"""

from __future__ import annotations

import datetime
import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Tuple

from . import WorkspaceStore
from .file_backend import FileStore
from ..util import CdpError, stable_hash

SCHEMA_V1 = """
CREATE TABLE IF NOT EXISTS snapshot_meta (
    id INTEGER PRIMARY KEY,
    repo_id TEXT,
    commit_sha TEXT,
    ephemeral INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    UNIQUE(repo_id, commit_sha)
);

CREATE TABLE IF NOT EXISTS snapshot_artifact (
    snapshot_id INTEGER NOT NULL REFERENCES snapshot_meta(id),
    name TEXT NOT NULL,
    payload TEXT NOT NULL,
    PRIMARY KEY (snapshot_id, name)
);

CREATE TABLE IF NOT EXISTS snapshot_report (
    snapshot_id INTEGER NOT NULL REFERENCES snapshot_meta(id),
    name TEXT NOT NULL,
    payload TEXT NOT NULL,
    PRIMARY KEY (snapshot_id, name)
);

CREATE TABLE IF NOT EXISTS claim_patch (
    id INTEGER PRIMARY KEY,
    snapshot_id INTEGER NOT NULL REFERENCES snapshot_meta(id),
    seq INTEGER NOT NULL,
    label TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    payload TEXT NOT NULL,
    is_derived INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    UNIQUE(snapshot_id, content_hash)
);
CREATE INDEX IF NOT EXISTS idx_claim_patch_snapshot_seq ON claim_patch(snapshot_id, seq);
CREATE INDEX IF NOT EXISTS idx_claim_patch_node ON claim_patch(json_extract(payload, '$.node'));

-- 0.16: created now, filled by Phase 7's `compact`.
CREATE TABLE IF NOT EXISTS claim_patches_archive (
    scope_hash TEXT,
    run_id TEXT,
    payload TEXT
);
CREATE INDEX IF NOT EXISTS idx_patches_archive ON claim_patches_archive(scope_hash, run_id);

-- link.*: created here, populated in Phase 8.
CREATE TABLE IF NOT EXISTS link_edge (
    id INTEGER PRIMARY KEY,
    payload TEXT
);
"""

# M2.5 (0.12/0.13): created here, driven in Phase 5. Schema only -- see the
# module docstring for why these are not part of `WorkspaceStore`.
SCHEMA_V2 = """
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
    PRIMARY KEY (run_id, scope_hash)
);
CREATE INDEX IF NOT EXISTS idx_snapshot_task_run_state ON snapshot_task(run_id, state);

-- link.* counterparts (0.13): structurally separate from snapshot_run/task so
-- R3's non-entanglement test can drop every link.* row and prove
-- snapshot.*/claim.* are untouched.
CREATE TABLE IF NOT EXISTS link_run (
    run_id TEXT PRIMARY KEY,
    payload TEXT
);

CREATE TABLE IF NOT EXISTS link_task (
    run_id TEXT NOT NULL,
    scope_hash TEXT NOT NULL,
    payload TEXT,
    PRIMARY KEY (run_id, scope_hash)
);
"""

#: Forward-only migrations, one script per version. Adding a version is
#: appending here, never editing an earlier entry.
MIGRATIONS: Tuple[str, ...] = (SCHEMA_V1, SCHEMA_V2)


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


class SqliteStore(WorkspaceStore):
    def __init__(self, db_path: Path, inbox_root: "Path | None" = None) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._migrate()
        # The inbox is a filesystem handoff with the agent session regardless
        # of backend (module docstring in `store/__init__.py`); reuse
        # `FileStore` for that slice rather than reimplementing it.
        self._inbox = FileStore(inbox_root if inbox_root is not None else self.db_path.parent)
        self._snapshot: "int | None" = None

    # ----------------------------------------------------------- snapshots

    def begin_snapshot(self, repo_id: str, commit_sha: str, ephemeral: bool = False) -> None:
        row = self._conn.execute(
            "SELECT id FROM snapshot_meta WHERE repo_id=? AND commit_sha=?",
            (repo_id, commit_sha),
        ).fetchone()
        if row is not None:
            self._snapshot = row[0]
            return
        cur = self._conn.execute(
            "INSERT INTO snapshot_meta (repo_id, commit_sha, ephemeral, created_at) "
            "VALUES (?, ?, ?, ?)",
            (repo_id, commit_sha, int(ephemeral), _now()),
        )
        self._conn.commit()
        self._snapshot = cur.lastrowid

    def mark_durable(self) -> None:
        row = self._conn.execute(
            "SELECT ephemeral FROM snapshot_meta WHERE id=?", (self._snapshot_id(),)
        ).fetchone()
        if row and row[0]:
            raise CdpError(
                "snapshot %s is ephemeral (a dirty tree's identity is not reproducible) "
                "and cannot anchor a durable claim" % self._snapshot
            )

    # ---------------------------------------------------------------- schema

    def _migrate(self) -> None:
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)"
        )
        row = self._conn.execute("SELECT MAX(version) FROM schema_version").fetchone()
        current = row[0] if row and row[0] is not None else 0
        for version, script in enumerate(MIGRATIONS, start=1):
            if version <= current:
                continue
            self._conn.executescript(script)
            self._conn.execute("INSERT INTO schema_version (version) VALUES (?)", (version,))
        self._conn.commit()

    def _snapshot_id(self) -> int:
        """The snapshot `begin_snapshot` selected, or a lazily-created default
        (`id=1`, ephemeral) for a caller that never calls it -- every M2.2/M2.3
        conformance test, and any use of this backend before M2.4."""
        if self._snapshot is not None:
            return self._snapshot
        self._conn.execute(
            "INSERT OR IGNORE INTO snapshot_meta (id, ephemeral, created_at) VALUES (1, 1, ?)",
            (_now(),),
        )
        self._conn.commit()
        self._snapshot = 1
        return 1

    # ------------------------------------------------------------ artifacts

    def read_artifact(self, name: str, default: Any = None) -> Any:
        row = self._conn.execute(
            "SELECT payload FROM snapshot_artifact WHERE snapshot_id=? AND name=?",
            (self._snapshot_id(), name),
        ).fetchone()
        if row is None:
            if default is None:
                raise CdpError("missing artifact %r in %s — run `scan` first" % (name, self.db_path))
            return default
        return json.loads(row[0])

    def write_artifact(self, name: str, data: Any) -> None:
        self._conn.execute(
            "INSERT INTO snapshot_artifact (snapshot_id, name, payload) VALUES (?, ?, ?) "
            "ON CONFLICT(snapshot_id, name) DO UPDATE SET payload=excluded.payload",
            (self._snapshot_id(), name, json.dumps(data, sort_keys=True)),
        )
        self._conn.commit()

    def has_artifact(self, name: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM snapshot_artifact WHERE snapshot_id=? AND name=?",
            (self._snapshot_id(), name),
        ).fetchone()
        return row is not None

    # -------------------------------------------------------------- reports

    def write_report(self, name: str, data: Any) -> None:
        self._conn.execute(
            "INSERT INTO snapshot_report (snapshot_id, name, payload) VALUES (?, ?, ?) "
            "ON CONFLICT(snapshot_id, name) DO UPDATE SET payload=excluded.payload",
            (self._snapshot_id(), name, json.dumps(data, sort_keys=True)),
        )
        self._conn.commit()

    # ------------------------------------------------------------ patch log

    def load_patches(self) -> List[Dict]:
        rows = self._conn.execute(
            "SELECT payload FROM claim_patch WHERE snapshot_id=? ORDER BY seq ASC",
            (self._snapshot_id(),),
        ).fetchall()
        return [json.loads(r[0]) for r in rows]

    def append_patch(self, patch: Dict, label: str) -> str:
        snapshot_id = self._snapshot_id()
        content_hash = stable_hash(patch)
        existing = self._conn.execute(
            "SELECT id FROM claim_patch WHERE snapshot_id=? AND content_hash=? AND is_derived=0",
            (snapshot_id, content_hash),
        ).fetchone()
        if existing is not None:
            return str(existing[0])
        seq = self._conn.execute(
            "SELECT COALESCE(MAX(seq), 0) + 1 FROM claim_patch WHERE snapshot_id=? AND is_derived=0",
            (snapshot_id,),
        ).fetchone()[0]
        cur = self._conn.execute(
            "INSERT INTO claim_patch "
            "(snapshot_id, seq, label, content_hash, payload, is_derived, created_at) "
            "VALUES (?, ?, ?, ?, ?, 0, ?)",
            (snapshot_id, seq, label, content_hash, json.dumps(patch, sort_keys=True), _now()),
        )
        self._conn.commit()
        return str(cur.lastrowid)

    def write_derived_patch(self, patch: Dict) -> None:
        """Overwrite the reserved derived slot (`seq=0`, `is_derived=1`).

        Mirrors `FileStore`'s fixed `0000-derived.json` slot: idempotent by
        construction rather than by content hash, because a rescan's derived
        claims must replace the previous scan's, not accumulate beside them.
        """
        snapshot_id = self._snapshot_id()
        self._conn.execute(
            "DELETE FROM claim_patch WHERE snapshot_id=? AND is_derived=1", (snapshot_id,)
        )
        self._conn.execute(
            "INSERT INTO claim_patch "
            "(snapshot_id, seq, label, content_hash, payload, is_derived, created_at) "
            "VALUES (?, 0, 'derived', ?, ?, 1, ?)",
            (snapshot_id, stable_hash(patch), json.dumps(patch, sort_keys=True), _now()),
        )
        self._conn.commit()

    # ---------------------------------------------------------------- inbox

    def ensure_inbox(self) -> None:
        self._inbox.ensure_inbox()

    def read_inbox(self) -> List[Tuple[str, Any]]:
        return self._inbox.read_inbox()

    def clear_inbox(self, node: str) -> None:
        self._inbox.clear_inbox(node)

    def close(self) -> None:
        self._conn.close()
