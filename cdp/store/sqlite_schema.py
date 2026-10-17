"""`SqliteStore`'s forward-only schema scripts V1-V10 (moved out of `sqlite_backend.py`, which
re-exports them, to keep that module under the layering test's size bound). V11 lives in
`sqlite_archive.py`, V12 (the object store) in `objects.py`."""

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
