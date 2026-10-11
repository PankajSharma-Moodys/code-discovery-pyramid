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
import fcntl
import json
import sqlite3
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from . import WorkspaceStore
from .sqlite_archive import ArchiveMixin, EphemeralMixin
from ..util import CdpError, read_json, stable_hash

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

# M3.6 (0.10): additive column for the retention rule's "pinned" branch --
# nothing yet sets it automatically (no feature writes it besides `cdp gc
# --pin`), but the rule cannot be expressed without a place to record it.
SCHEMA_V3 = """
ALTER TABLE snapshot_meta ADD COLUMN pinned INTEGER NOT NULL DEFAULT 0;
"""

# M5.4: leases are held by the supervisor, not the leaf (`phase_5_plan.md`
# M5.4) -- a slow frontier model's runner never sees this column. `wall_ms`
# records every task's own dispatch time from day one, so the tier-derived
# ceiling M5.4 defers (no p99 exists until Phase 9's star) has real data to
# replace the v1 constant with later, rather than starting from nothing.
SCHEMA_V5 = """
ALTER TABLE snapshot_task ADD COLUMN wall_ms INTEGER;
"""

# M7.4 (2.5): lets `verify --full` detect a corrupted archive row by content,
# not only by the aggregate fold mismatch it would eventually cause.
SCHEMA_V6 = """
ALTER TABLE claim_patches_archive ADD COLUMN content_hash TEXT;
"""

# M3.8: `id DESC` is creation order, not "most recently selected" -- `refresh`
# moving *back* to an earlier commit (e.g. a branch checkout) reuses that
# commit's existing, lower-numbered row (`begin_snapshot`'s reuse branch), so
# picking the highest id would keep pointing at a newer, untouched snapshot
# instead. A monotonic counter, not a timestamp (D8's own argument against
# wall-clock ordering applies here too: two `begin_snapshot` calls a second
# apart -- routine for a `post-commit` immediately followed by a
# `post-checkout` in a test or a fast CI step -- would tie under
# second-precision `_now()`). Bumped on every `begin_snapshot`, including a
# reuse; `NULL` for any row written before this migration, so
# `use_latest_snapshot` falls back to `id` for those.
SCHEMA_V4 = """
ALTER TABLE snapshot_meta ADD COLUMN touch_seq INTEGER;
"""

# Post-Phase-9 item 5: `link_task` gets the same lease/state columns
# `snapshot_task` already has, so a link task (M8.3's ambiguous-caller-target
# question) can be dispatched through the same lease/retry machinery as a
# scope, keeping trajectory learning's `dim_task_kind=link` no longer blind to
# link work. `scope_hash` (the column link_task already had, M2.5) holds a
# link task's `task_id` here -- same column name so the generic lease/task
# helpers below work unmodified against either table.
SCHEMA_V7 = """
ALTER TABLE link_task ADD COLUMN state TEXT;
ALTER TABLE link_task ADD COLUMN attempts INTEGER NOT NULL DEFAULT 0;
ALTER TABLE link_task ADD COLUMN dispatched_at TEXT;
ALTER TABLE link_task ADD COLUMN lease_until TEXT;
ALTER TABLE link_task ADD COLUMN last_error TEXT;
ALTER TABLE link_task ADD COLUMN patch_hash TEXT;
ALTER TABLE link_task ADD COLUMN wall_ms INTEGER;
"""

# This cycle's web layer: `/api/status`'s freshness bucketing was shelling
# out to `git log` on every request (`freshness.file_churned_between`, one
# process per anchored file). This table persists that answer keyed by
# exactly the three things it depends on -- `(path, since_sha, head_sha)` is
# fully determined, so a hit never goes stale for a commit pair already
# computed. `churned` is nullable: `NULL` records `file_churned_between`
# returning `None` (unwalkable range) as a cached fact too, so a request
# handler never re-shells to find that out either.
SCHEMA_V8 = """
CREATE TABLE IF NOT EXISTS churn_cache (
    path TEXT NOT NULL,
    since_sha TEXT NOT NULL,
    head_sha TEXT NOT NULL,
    churned INTEGER,
    PRIMARY KEY (path, since_sha, head_sha)
);
"""

# A model's verdict on a link, kept apart from `link_edge` (which a re-scan replaces) and
# saved one row at a time, so neither a re-scan nor a concurrent `link run` can lose one.
SCHEMA_V9 = """
CREATE TABLE IF NOT EXISTS link_resolution (
    link_id TEXT PRIMARY KEY,
    payload TEXT NOT NULL
);
"""

# Which checkout (worktree) last scanned an uncommitted-changes snapshot: lets a scan
# drop the dirty snapshots it supersedes without touching another worktree's.
SCHEMA_V10 = """
CREATE TABLE IF NOT EXISTS snapshot_checkout (
    snapshot_id INTEGER NOT NULL,
    checkout TEXT NOT NULL,
    seq INTEGER NOT NULL,
    PRIMARY KEY (snapshot_id, checkout)
);
"""

#: Forward-only migrations, one script per version. Adding a version is
#: appending here, never editing an earlier entry.
MIGRATIONS: Tuple[str, ...] = (
    SCHEMA_V1, SCHEMA_V2, SCHEMA_V3, SCHEMA_V4, SCHEMA_V5, SCHEMA_V6, SCHEMA_V7, SCHEMA_V8, SCHEMA_V9, SCHEMA_V10,
)


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def _lease_ts(seconds: float = 0.0) -> str:
    """A lease deadline, `seconds` from now, at millisecond precision --
    always this precision, never `_now()`'s second precision, so lexicographic
    SQL string comparison between two `_lease_ts` values agrees with wall-clock
    order even at the short lease durations tests use (a real 90s lease and a
    test's 0.05s lease both need sub-second resolution to compare correctly)."""
    when = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=seconds)
    return when.isoformat(timespec="milliseconds")


def connect_raw(db_path, *, check_same_thread: bool = True) -> sqlite3.Connection:
    """A plain `sqlite3.connect` (foreign keys on), exposed for callers
    outside `store/` that need their own, separate sqlite database -- Phase
    9's trajectory store is not a `WorkspaceStore` backend and shares no
    schema with `index.db`, but `tests/test_store_sqlite.py`'s import-boundary
    test still requires `sqlite3` be imported nowhere else, so this is the one
    crossing point."""
    conn = sqlite3.connect(str(db_path), check_same_thread=check_same_thread)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


class SqliteStore(EphemeralMixin, ArchiveMixin, WorkspaceStore):
    def __init__(self, db_path: Path, inbox_root: "Path | None" = None,
                 readonly: bool = False, busy_timeout_ms: int = 60000) -> None:
        """`readonly`: a reader that must never wait on a writer or touch the
        schema (the PreToolUse hook): no directory creation, no migration, no
        journal-mode change, and a short `busy_timeout_ms`."""
        self.db_path = Path(db_path)
        if not readonly:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._busy_timeout_ms = int(busy_timeout_ms)
        self._local, self._opened, self._opened_lock = threading.local(), [], threading.Lock()
        self._closed = False
        if not readonly:
            self._conn.execute("PRAGMA journal_mode = WAL")
            self._migrate()
        # The inbox is a filesystem handoff with the agent session regardless
        # of backend (module docstring in `store/__init__.py`): a directory of
        # small JSON files an external process drops patches into, not state.
        self._inbox_root = Path(inbox_root if inbox_root is not None else self.db_path.parent)
        self._snapshot: "int | None" = None
        self._wanted_repo: "str | None" = None
        self._scan_needed = ""

    @property
    def _conn(self) -> sqlite3.Connection:
        """This thread's connection, opened on first use (a shared one crashes libsqlite3)."""
        conn = getattr(self._local, "conn", None)
        if conn is None:
            if self._closed:
                raise sqlite3.ProgrammingError("Cannot operate on a closed database.")
            conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA busy_timeout = %d" % self._busy_timeout_ms)
            self._local.conn = conn
            with self._opened_lock:  # close connections of finished threads (lease heartbeats)
                for thread, c in self._opened:
                    if not thread.is_alive():
                        c.close()
                self._opened = [(t, c) for t, c in self._opened if t.is_alive()]
                self._opened.append((threading.current_thread(), conn))
        return conn

    def _inbox_dir(self) -> Path:
        return self._inbox_root / "patches" / "inbox"

    # ----------------------------------------------------------- snapshots

    _TOUCH_SEQ = "(SELECT COALESCE(MAX(touch_seq), 0) + 1 FROM snapshot_meta)"

    def begin_snapshot(self, repo_id: str, commit_sha: str, ephemeral: bool = False,
                       checkout: str = "") -> None:
        """Select or create the snapshot, and in the same transaction drop the dirty
        snapshots this checkout's scan supersedes (`prune_ephemeral`)."""
        row = self._conn.execute(
            "SELECT id FROM snapshot_meta WHERE repo_id=? AND commit_sha=?",
            (repo_id, commit_sha),
        ).fetchone()
        if row is not None:
            snapshot_id = row[0]
            # The new sequence number is computed inside the statement, so two
            # processes touching snapshots at once cannot draw the same one.
            self._conn.execute(
                "UPDATE snapshot_meta SET touch_seq=%s WHERE id=?" % self._TOUCH_SEQ, (snapshot_id,)
            )
        else:
            snapshot_id = self._conn.execute(
                "INSERT INTO snapshot_meta (repo_id, commit_sha, ephemeral, created_at, touch_seq) "
                "VALUES (?, ?, ?, ?, %s)" % self._TOUCH_SEQ,
                (repo_id, commit_sha, int(ephemeral), _now()),
            ).lastrowid
        self._snapshot = snapshot_id
        self.prune_ephemeral(repo_id, snapshot_id, ephemeral, checkout)
        self._conn.commit()

    def supports_snapshot_history(self) -> bool:
        return True

    def use_snapshot(self, repo_id: str, commit_sha: str) -> None:
        row = self._conn.execute(
            "SELECT id FROM snapshot_meta WHERE repo_id=? AND commit_sha=?",
            (repo_id, commit_sha),
        ).fetchone()
        if row is None:
            available = [r["commit_sha"] for r in self.list_snapshots() if r["repo_id"] == repo_id]
            raise CdpError(
                "no scanned snapshot for %s@%s -- scanned commits for this repo: %s"
                % (repo_id, commit_sha, ", ".join(available) or "(none -- run `cdp scan`)")
            )
        self._snapshot = row[0]

    def mark_durable(self) -> None:
        row = self._conn.execute(
            "SELECT ephemeral FROM snapshot_meta WHERE id=?", (self._snapshot_id(),)
        ).fetchone()
        if row and row[0]:
            raise CdpError(
                "snapshot %s is ephemeral (a dirty tree's identity is not reproducible) "
                "and cannot anchor a durable claim" % self._snapshot
            )

    # ------------------------------------------------------- retention (M3.6)

    def list_snapshots(self) -> List[Dict]:
        rows = self._conn.execute(
            "SELECT id, repo_id, commit_sha, ephemeral, pinned, created_at FROM snapshot_meta ORDER BY id"
        ).fetchall()
        return [
            {"id": r[0], "repo_id": r[1], "commit_sha": r[2], "ephemeral": bool(r[3]),
             "pinned": bool(r[4]), "created_at": r[5]}
            for r in rows
        ]

    def set_pinned(self, commit_sha: str, pinned: bool, repo_id: Optional[str] = None) -> None:
        # `repo_id` matters on a machine-wide store: a folder and its parent
        # share a commit, and pinning one must not pin the other.
        cur = self._conn.execute(
            "UPDATE snapshot_meta SET pinned=? WHERE commit_sha=?"
            + (" AND repo_id=?" if repo_id else ""),
            (int(pinned), commit_sha) + ((repo_id,) if repo_id else ()),
        )
        self._conn.commit()
        if cur.rowcount == 0:
            raise CdpError("no snapshot for commit %s in %s" % (commit_sha, self.db_path))

    # ------------------------------------------------------- link.* (M8.2)

    def supports_link_edges(self) -> bool:
        return True

    def write_link_edges(self, report: Dict) -> None:
        """Replaces `link_edge`'s contents with one row per link and one per
        unmatched outbound call from `report` (`link.scan_links`'s return
        value). The links and calls are fully derived from a fresh `link scan`
        (R3: link data is disposable), but the verdicts on them are not: they
        live in `link_resolution` under the link's id, which a replace never
        touches. A resolution embedded in an older row, or in `report`, is moved there.
        """
        from ..linkid import link_id

        for row in self._conn.execute("SELECT payload FROM link_edge").fetchall():
            data = json.loads(row[0])
            if data.get("kind") == "link" and data["data"].get("resolution"):
                self._conn.execute("INSERT OR IGNORE INTO link_resolution (link_id, payload) VALUES (?, ?)",
                                   (link_id(data["data"]), json.dumps(data["data"]["resolution"], sort_keys=True)))
        self._conn.execute("DELETE FROM link_edge")
        entries = []
        for link in report["links"]:
            link = dict(link)
            resolution = link.pop("resolution", None)
            if resolution:
                self.save_link_resolution(link_id(link), resolution)
            entries.append({"kind": "link", "data": link})
        entries += [{"kind": "unmatched", "data": u} for u in report["unmatched"]]
        self._conn.executemany(
            "INSERT INTO link_edge (payload) VALUES (?)",
            [(json.dumps(e, sort_keys=True),) for e in entries],
        )
        self._conn.commit()

    def save_link_resolution(self, link_id: str, resolution: Dict) -> None:
        """One verdict, saved the moment it is validated (an atomic upsert)."""
        self._conn.execute("INSERT OR REPLACE INTO link_resolution (link_id, payload) VALUES (?, ?)",
                           (link_id, json.dumps(resolution, sort_keys=True)))
        self._conn.commit()

    def read_link_edges(self) -> List[Dict]:
        """Links and unmatched calls, each link carrying its `resolution` if one was saved."""
        from ..linkid import link_id, reanchor

        resolutions = {r[0]: json.loads(r[1]) for r in
                       self._conn.execute("SELECT link_id, payload FROM link_resolution").fetchall()}
        out = []
        for row in self._conn.execute("SELECT payload FROM link_edge ORDER BY id").fetchall():
            entry = json.loads(row[0])
            if entry["kind"] == "link" and link_id(entry["data"]) in resolutions:
                entry["data"]["resolution"] = reanchor(entry["data"], resolutions[link_id(entry["data"])])
            out.append(entry)
        return out

    # ------------------------------------------------------- churn cache

    def supports_churn_cache(self) -> bool:
        return True

    def churn_lookup(self, path: str, since_sha: str, head_sha: str) -> Tuple[bool, Optional[bool]]:
        """`(hit, churned)` -- `hit=False` means no cached answer exists yet
        (caller must decide whether to compute and populate one); `hit=True,
        churned=None` means a cached-but-unknown answer (an unwalkable range,
        `file_churned_between`'s own `None` case) rather than "no data"."""
        row = self._conn.execute(
            "SELECT churned FROM churn_cache WHERE path=? AND since_sha=? AND head_sha=?",
            (path, since_sha, head_sha),
        ).fetchone()
        if row is None:
            return False, None
        return True, (None if row[0] is None else bool(row[0]))

    def write_churn_cache(self, entries: List[Tuple[str, str, str, Optional[bool]]]) -> None:
        """`entries` are `(path, since_sha, head_sha, churned)` -- `churned`
        may be `None` (an unwalkable range, cached as a fact same as a real
        answer). `INSERT OR REPLACE`: a key is fully determined by its three
        column values, so a repeat write is always the same answer, never a
        conflicting one."""
        self._conn.executemany(
            "INSERT OR REPLACE INTO churn_cache (path, since_sha, head_sha, churned) VALUES (?, ?, ?, ?)",
            [(p, s, h, None if c is None else int(c)) for p, s, h, c in entries],
        )
        self._conn.commit()

    def delete_snapshot(self, snapshot_id: int) -> None:
        """Drops a snapshot and everything scoped to it. Never called for the
        snapshot `gc`'s own retention rule keeps (`snapshot.snapshots_to_keep`)."""
        self._delete_snapshot_rows(snapshot_id)
        self._conn.commit()

    # ---------------------------------------------------- tasks (M4.2 gate 3)

    def task_states(self, run_id: str) -> Dict[str, Dict]:
        """`snapshot_task` rows for `run_id`, keyed by `scope_hash`. Schema-only
        until Phase 5's dispatch loop writes to this table -- callers get `{}`
        today, honestly, rather than a fabricated state."""
        rows = self._conn.execute(
            "SELECT scope_hash, state, attempts FROM snapshot_task WHERE run_id=?", (run_id,)
        ).fetchall()
        return {r[0]: {"state": r[1], "attempts": r[2]} for r in rows}

    def link_task_states(self, run_id: str) -> Dict[str, Dict]:
        """`link_task` counterpart of `task_states` (post-Phase-9 item 5)."""
        rows = self._conn.execute(
            "SELECT scope_hash, state, attempts FROM link_task WHERE run_id=?", (run_id,)
        ).fetchall()
        return {r[0]: {"state": r[1], "attempts": r[2]} for r in rows}

    # ------------------------------------------------ runs/tasks (Phase 5, M5.2)

    def begin_run(self, run_id: str, partition_hash: Optional[str] = None) -> None:
        """Idempotent: resuming within one `cdp run` process (retrying a wave)
        reuses the existing row rather than erroring."""
        row = self._conn.execute("SELECT run_id FROM snapshot_run WHERE run_id=?", (run_id,)).fetchone()
        if row is None:
            self._conn.execute(
                "INSERT INTO snapshot_run (run_id, snapshot_id, partition_hash, status, started_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (run_id, self._snapshot_id(), partition_hash, "running", _now()),
            )
            self._conn.commit()

    def finish_run(self, run_id: str, status: str) -> None:
        self._conn.execute(
            "UPDATE snapshot_run SET status=?, finished_at=? WHERE run_id=?", (status, _now(), run_id)
        )
        self._conn.commit()

    def set_run_lessons_version(self, run_id: str, lessons_version: Optional[int]) -> None:
        self._conn.execute(
            "UPDATE snapshot_run SET lessons_version=? WHERE run_id=?",
            (None if lessons_version is None else str(lessons_version), run_id),
        )
        self._conn.commit()

    def _upsert_task(self, table: str, run_id: str, scope_hash: str, **fields: Any) -> None:
        """Insert-or-update one row of `table` (`snapshot_task` or
        `link_task` -- same column shape, post-Phase-9 item 5). `fields` are
        whichever columns changed -- callers pass only those, never the full
        row."""
        existing = self._conn.execute(
            "SELECT 1 FROM %s WHERE run_id=? AND scope_hash=?" % table, (run_id, scope_hash)
        ).fetchone()
        if existing is None:
            cols = ["run_id", "scope_hash"] + list(fields.keys())
            self._conn.execute(
                "INSERT INTO %s (%s) VALUES (%s)" % (table, ", ".join(cols), ", ".join("?" * len(cols))),
                [run_id, scope_hash] + list(fields.values()),
            )
        else:
            self._conn.execute(
                "UPDATE %s SET %s WHERE run_id=? AND scope_hash=?"
                % (table, ", ".join("%s=?" % k for k in fields)),
                list(fields.values()) + [run_id, scope_hash],
            )
        self._conn.commit()

    def upsert_task(self, run_id: str, scope_hash: str, **fields: Any) -> None:
        self._upsert_task("snapshot_task", run_id, scope_hash, **fields)

    def upsert_link_task(self, run_id: str, task_id: str, **fields: Any) -> None:
        self._upsert_task("link_task", run_id, task_id, **fields)

    def task_rows(self, run_id: str) -> List[Dict]:
        """Full `snapshot_task` rows for `run_id`, for `status`'s per-run task
        table (M5.2). `task_states` above stays the narrow `{state, attempts}`
        read `gates.py` gate 3 needs; this is the wider one `cmd_status` and
        `--resume` (M5.5) need."""
        rows = self._conn.execute(
            "SELECT scope_hash, state, attempts, dispatched_at, lease_until, last_error, patch_hash, wall_ms "
            "FROM snapshot_task WHERE run_id=? ORDER BY scope_hash",
            (run_id,),
        ).fetchall()
        return [
            {"scope_hash": r[0], "state": r[1], "attempts": r[2], "dispatched_at": r[3],
             "lease_until": r[4], "last_error": r[5], "patch_hash": r[6], "wall_ms": r[7]}
            for r in rows
        ]

    # ------------------------------------------------------- leases (M5.4)

    def _acquire_lease(self, table: str, run_id: str, scope_hash: str, lease_seconds: float) -> bool:
        """Atomically claim `scope_hash` for the calling process, for up to
        `lease_seconds`, in `table` (`snapshot_task` or `link_task`). One
        UPDATE (or, for a row never seen before, one INSERT into a row
        nothing else can be racing yet) is the whole critical section --
        SQLite serialises writers on the file itself, so the loser of a race
        between two supervisor processes sees `rowcount == 0` and takes
        nothing, never a partial claim. A row is claimable when it has no
        lease yet, or its lease has already expired (the supervisor that held
        it is presumed dead)."""
        now = _lease_ts()
        until = _lease_ts(lease_seconds)
        cur = self._conn.execute(
            "UPDATE %s SET lease_until=? "
            "WHERE run_id=? AND scope_hash=? AND (lease_until IS NULL OR lease_until < ?)" % table,
            (until, run_id, scope_hash, now),
        )
        if cur.rowcount:
            self._conn.commit()
            return True
        exists = self._conn.execute(
            "SELECT 1 FROM %s WHERE run_id=? AND scope_hash=?" % table, (run_id, scope_hash)
        ).fetchone()
        if exists is not None:
            self._conn.commit()  # row exists, held by a live lease -- not ours
            return False
        try:
            self._conn.execute(
                "INSERT INTO %s (run_id, scope_hash, state, attempts, lease_until) "
                "VALUES (?, ?, 'pending', 0, ?)" % table,
                (run_id, scope_hash, until),
            )
        except sqlite3.IntegrityError:
            self._conn.rollback()
            return False  # another process' INSERT for the same first claim won the race
        self._conn.commit()
        return True

    def acquire_lease(self, run_id: str, scope_hash: str, lease_seconds: float) -> bool:
        return self._acquire_lease("snapshot_task", run_id, scope_hash, lease_seconds)

    def acquire_link_lease(self, run_id: str, task_id: str, lease_seconds: float) -> bool:
        return self._acquire_lease("link_task", run_id, task_id, lease_seconds)

    def _heartbeat_lease(self, table: str, run_id: str, scope_hash: str, lease_seconds: float) -> None:
        """Renew a lease this process already holds. Called every
        `HEARTBEAT_SECONDS` while a runner call is in flight -- if the process
        dies, the heartbeats stop and the lease expires on its own within
        `lease_seconds` of the last one, which is the entire death-detection
        mechanism (no separate liveness channel)."""
        self._conn.execute(
            "UPDATE %s SET lease_until=? WHERE run_id=? AND scope_hash=?" % table,
            (_lease_ts(lease_seconds), run_id, scope_hash),
        )
        self._conn.commit()

    def heartbeat_lease(self, run_id: str, scope_hash: str, lease_seconds: float) -> None:
        self._heartbeat_lease("snapshot_task", run_id, scope_hash, lease_seconds)

    def heartbeat_link_lease(self, run_id: str, task_id: str, lease_seconds: float) -> None:
        self._heartbeat_lease("link_task", run_id, task_id, lease_seconds)

    def _release_lease(self, table: str, run_id: str, scope_hash: str) -> None:
        """Give up a held lease immediately once its task reaches a terminal
        (or retry-pending) outcome, rather than making the next dispatch wait
        out the full `lease_seconds`."""
        self._conn.execute(
            "UPDATE %s SET lease_until=NULL WHERE run_id=? AND scope_hash=?" % table,
            (run_id, scope_hash),
        )
        self._conn.commit()

    def release_lease(self, run_id: str, scope_hash: str) -> None:
        self._release_lease("snapshot_task", run_id, scope_hash)

    def release_link_lease(self, run_id: str, task_id: str) -> None:
        self._release_lease("link_task", run_id, task_id)

    # --------------------------------------------------- resume (M5.5, 4.6)

    def get_run(self, run_id: str) -> Optional[Dict]:
        """`snapshot_run` row for `run_id`, or `None` if this run was never
        begun -- what `--resume`'s partition-drift guard compares against."""
        row = self._conn.execute(
            "SELECT run_id, partition_hash, status, lessons_version FROM snapshot_run WHERE run_id=?",
            (run_id,),
        ).fetchone()
        if row is None:
            return None
        return {"run_id": row[0], "partition_hash": row[1], "status": row[2], "lessons_version": row[3]}

    def reclaim_expired(self, run_id: str, force: bool = False) -> List[str]:
        """`dispatched` tasks whose lease has already lapsed -- the supervisor
        that held them is presumed dead. `force` reclaims every `dispatched` task: the caller
        holds the exclusive repo lock, so no live supervisor can own one (L6). Moves each to `expired` (a
        `RETRY_STATE`, so the next dispatch re-attempts it) and returns the
        `scope_hash`es reclaimed, for the resume summary line."""
        now = _lease_ts()
        rows = self._conn.execute(
            "SELECT scope_hash FROM snapshot_task WHERE run_id=? AND state=? "
            "AND (? OR lease_until IS NULL OR lease_until < ?)",
            (run_id, "dispatched", int(force), now),
        ).fetchall()
        hashes = [r[0] for r in rows]
        if hashes:
            self._conn.executemany(
                "UPDATE snapshot_task SET state='expired', lease_until=NULL "
                "WHERE run_id=? AND scope_hash=?",
                [(run_id, h) for h in hashes],
            )
            self._conn.commit()
        return hashes

    def copy_folded_tasks(self, old_run_id: str, new_run_id: str, scope_hashes) -> None:
        """Carries a `folded` task row from `old_run_id` into `new_run_id`
        verbatim, for each `scope_hash` the partition-drift guard has decided
        is unchanged and therefore not owed a fresh dispatch. Only `folded`
        rows are ever copied -- an unfinished scope has nothing worth
        inheriting and is re-queued under the new run instead."""
        for scope_hash in scope_hashes:
            row = self._conn.execute(
                "SELECT attempts, dispatched_at, last_error, patch_hash, wall_ms "
                "FROM snapshot_task WHERE run_id=? AND scope_hash=? AND state='folded'",
                (old_run_id, scope_hash),
            ).fetchone()
            if row is None:
                continue
            self._conn.execute(
                "INSERT INTO snapshot_task "
                "(run_id, scope_hash, state, attempts, dispatched_at, last_error, patch_hash, wall_ms) "
                "VALUES (?, ?, 'folded', ?, ?, ?, ?, ?)",
                (new_run_id, scope_hash) + row,
            )
        self._conn.commit()

    # ---------------------------------------------------------------- schema

    def _migrate(self) -> None:
        """Bring the schema up to date. Two processes opening a fresh machine
        store at once would both read version 0 and both run migration 2's
        `ALTER TABLE`; the second fails with `duplicate column name`. A lock
        file serialises the check-then-apply, so the loser sees the new version."""
        with open(str(self.db_path) + ".migrate", "a") as fh:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
            try:
                self._migrate_locked()
            finally:
                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)

    def _migrate_locked(self) -> None:
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
        if self._snapshot == -1:
            raise CdpError(self._missing(""))
        if self._snapshot is not None:
            return self._snapshot
        self._conn.execute(
            "INSERT OR IGNORE INTO snapshot_meta (id, ephemeral, created_at) VALUES (1, 1, ?)",
            (_now(),),
        )
        self._conn.commit()
        self._snapshot = 1
        return 1

    def snapshot_id(self) -> int:
        """Public accessor. `refresh` (M3.3/M3.8) needs the *previous*
        snapshot's id before it moves the selection forward to the new
        commit, so it can carry the patch log across (see
        `copy_patches_from`)."""
        return self._snapshot_id()

    def has_selection(self) -> bool:
        return self._snapshot is not None

    def repo_ids(self) -> List[str]:
        rows = self._conn.execute(
            "SELECT DISTINCT repo_id FROM snapshot_meta WHERE repo_id IS NOT NULL ORDER BY repo_id"
        ).fetchall()
        return [r[0] for r in rows]

    def select_none(self, repo_id: str, reason: str = "", label: str = "") -> None:
        self._snapshot = -1
        self._wanted_repo = label or repo_id
        self._scan_needed = reason

    def latest_snapshots(self) -> List[Dict]:
        """One row per repo: its most recently touched snapshot."""
        rows = self._conn.execute(
            "SELECT m.id, m.repo_id, m.commit_sha, m.created_at FROM snapshot_meta m "
            "WHERE m.repo_id IS NOT NULL AND m.id = (SELECT id FROM snapshot_meta "
            "WHERE repo_id = m.repo_id ORDER BY COALESCE(touch_seq, id) DESC LIMIT 1) ORDER BY m.repo_id"
        ).fetchall()
        return [{"id": r[0], "repo_id": r[1], "commit_sha": r[2], "created_at": r[3]} for r in rows]

    def use_latest_snapshot(self) -> None:
        """Point subsequent reads at the most recently *touched* snapshot in
        this store, instead of `_snapshot_id()`'s lazy `id=1` default.

        `scan`/`refresh`/`rollback`/`gc` all resolve a specific `(repo_id,
        commit_sha)` themselves before reading or writing. Every read-only
        command that does not -- `query`, `status`, `docs`, `fold`, `collect`,
        `diff` (via `query.Store.__init__`, the one place this is called) --
        used to silently read snapshot 1 forever, even after a `refresh` had
        moved the repo on to a later one: found while exercising M3.8's git
        hooks against a real `scan` -> `refresh` -> `status` sequence in
        separate processes, the composition every real user and the new git
        hooks actually perform.

        Ordered by `touch_seq` (bumped by every `begin_snapshot`, including a
        reuse), not `id` (creation order): moving *back* to an earlier commit
        -- a branch checkout is the common case -- reuses that commit's
        already-existing, lower-numbered row, so the highest `id` would still
        point at whatever commit was scanned most recently, not whichever one
        is actually current. A store holding exactly one snapshot (the
        overwhelming common case) is unaffected either way."""
        row = self._conn.execute(
            "SELECT id FROM snapshot_meta ORDER BY COALESCE(touch_seq, id) DESC LIMIT 1"
        ).fetchone()
        if row is not None:
            self._snapshot = row[0]

    def copy_patches_from(self, source_snapshot_id: int) -> None:
        """Seed the *current* (just-selected, empty) snapshot's patch log
        with a verbatim copy of `source_snapshot_id`'s rows.

        M2.4's snapshot isolation is deliberate and tested
        (`tests/test_store_sqlite.py`
        `test_two_commits_produce_two_snapshots_and_both_stay_queryable`):
        two commits are two independent logs. But 0.7 also requires "claim
        lineage spans snapshots", and `refresh` (M3.3) re-verifies the
        *existing* log against a new commit without ever appending to it
        (D10, `PHASE/FINDINGS.md`) -- so a brand-new snapshot needs its own
        copy of the log to re-verify, not an empty one. `refresh` is the only
        caller: it takes this copy once, right after `begin_snapshot` selects
        the new commit's (until-now log-less) snapshot."""
        dest = self._snapshot_id()
        rows = self._conn.execute(
            "SELECT seq, label, content_hash, payload, is_derived FROM claim_patch "
            "WHERE snapshot_id=? ORDER BY seq ASC",
            (source_snapshot_id,),
        ).fetchall()
        for seq, label, content_hash, payload, is_derived in rows:
            self._conn.execute(
                "INSERT INTO claim_patch "
                "(snapshot_id, seq, label, content_hash, payload, is_derived, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (dest, seq, label, content_hash, payload, is_derived, _now()),
            )
        self._conn.commit()

    # ------------------------------------------------------------ artifacts

    def read_artifact(self, name: str, default: Any = None) -> Any:
        row = self._conn.execute(
            "SELECT payload FROM snapshot_artifact WHERE snapshot_id=? AND name=?",
            (self._snapshot_id(), name),
        ).fetchone()
        if row is None:
            if default is None:
                raise CdpError(self._missing(name))
            return default
        return json.loads(row[0])

    def _missing(self, name: str) -> str:
        if self._snapshot == -1:
            known = self.repo_ids()
            return (
                "scan needed for %s in %s: %s%s"
                % (self._wanted_repo, self.db_path, self._scan_needed or "no scan of this repo",
                   " (scanned here: " + ", ".join(self._describe_repo(r) for r in known) + ")" if known and "no scan of this repo" in (self._scan_needed or "no scan of this repo") else "")
            )
        return "missing artifact %r in %s — run `scan` first" % (name, self.db_path)

    def _describe_repo(self, repo_id: str) -> str:
        """A scanned repo as a person recognises it: its path, not a bare UUID."""
        row = self._conn.execute(
            "SELECT a.payload FROM snapshot_artifact a JOIN snapshot_meta m ON m.id = a.snapshot_id "
            "WHERE m.repo_id=? AND a.name='inventory' ORDER BY COALESCE(m.touch_seq, m.id) DESC LIMIT 1",
            (repo_id,)).fetchone()
        path = (json.loads(row[0]).get("repo") if row else None) or ""
        return path or repo_id

    def write_artifact(self, name: str, data: Any) -> None:
        self._conn.execute(
            "INSERT INTO snapshot_artifact (snapshot_id, name, payload) VALUES (?, ?, ?) "
            "ON CONFLICT(snapshot_id, name) DO UPDATE SET payload=excluded.payload",
            (self._snapshot_id(), name, json.dumps(data, sort_keys=True)),
        )
        self._conn.commit()

    def has_artifact(self, name: str) -> bool:
        if self._snapshot == -1:
            return False
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

    def read_report(self, name: str, default: Any = None) -> Any:
        row = self._conn.execute(
            "SELECT payload FROM snapshot_report WHERE snapshot_id=? AND name=?",
            (self._snapshot_id(), name),
        ).fetchone()
        if row is None:
            if default is None:
                raise CdpError("missing report %r in %s" % (name, self.db_path))
            return default
        return json.loads(row[0])

    # ------------------------------------------------------------ patch log

    def load_patches(self) -> List[Dict]:
        rows = self._conn.execute(
            "SELECT seq, payload FROM claim_patch WHERE snapshot_id=? ORDER BY seq ASC",
            (self._snapshot_id(),),
        ).fetchall()
        return [dict(json.loads(r[1]), patch_no=r[0]) for r in rows]

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
        self._inbox_dir().mkdir(parents=True, exist_ok=True)

    def read_inbox(self) -> List[Tuple[str, Any]]:
        inbox = self._inbox_dir()
        if not inbox.is_dir():
            raise CdpError("no inbox at %s — run `cdp prompts` first" % inbox)
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
        with self._opened_lock:
            self._closed = True
            for _, conn in self._opened:
                conn.close()
            self._opened = []
        self._local = threading.local()

    def supports_run_tracking(self) -> bool:
        return True
