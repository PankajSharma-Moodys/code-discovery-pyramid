"""M9.1 (0.17/0.18): the trajectory store -- a *separate* database at
`~/.cdp/trajectories.db` (override: `CDP_TRAJECTORY_DB`), cross-workspace and
cumulative. Separate so deleting or rebuilding a workspace's own `.cdp/`
directory can never destroy it (0.17's whole reason for a second file).

R4 binds this module: write-always; reading it is versioned and pinned
(Phase 9's later milestones), never live; leaves never construct or consult
this store directly -- only `cli.py`'s own commands do, after a run's outcome
is already decided.

Star schema (0.18): two facts sharing dimensions.
  fact_leaf_run   -- grain: one run x scope dispatch
  fact_run_event  -- grain: one run-level event (started/finished/aborted/
                     rolled_back(reason)/compacted)
  dim_model, dim_scope_shape, dim_template, dim_repo, dim_tier, dim_task_kind
"""
from __future__ import annotations

import datetime
import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Set

from .store.sqlite_backend import connect_raw

#: cadence for the "lessons available" nudge `cdp run` prints (user decision,
#: not the plan's own open "cut cadence" question -- cutting stays manual via
#: `cdp lessons cut`; this only surfaces that pending promotions exist).
LESSONS_HINT_EVERY = 5

SCHEMA = """
CREATE TABLE IF NOT EXISTS dim_model (id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL);
CREATE TABLE IF NOT EXISTS dim_scope_shape (id INTEGER PRIMARY KEY, key TEXT UNIQUE NOT NULL);
CREATE TABLE IF NOT EXISTS dim_template (id INTEGER PRIMARY KEY, version TEXT UNIQUE NOT NULL);
CREATE TABLE IF NOT EXISTS dim_repo (id INTEGER PRIMARY KEY, repo_id TEXT UNIQUE NOT NULL);
CREATE TABLE IF NOT EXISTS dim_tier (id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL);
CREATE TABLE IF NOT EXISTS dim_task_kind (id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL);

CREATE TABLE IF NOT EXISTS fact_leaf_run (
    id INTEGER PRIMARY KEY,
    run_id TEXT NOT NULL,
    node TEXT NOT NULL,
    scope_hash TEXT,
    repo_dim INTEGER NOT NULL REFERENCES dim_repo(id),
    model_dim INTEGER NOT NULL REFERENCES dim_model(id),
    scope_shape_dim INTEGER NOT NULL REFERENCES dim_scope_shape(id),
    template_dim INTEGER NOT NULL REFERENCES dim_template(id),
    tier_dim INTEGER NOT NULL REFERENCES dim_tier(id),
    task_kind_dim INTEGER NOT NULL REFERENCES dim_task_kind(id),
    state TEXT,
    attempts INTEGER,
    wall_ms INTEGER,
    patch_hash TEXT,
    claims_emitted INTEGER,
    unknowns_emitted INTEGER,
    created_at TEXT NOT NULL,
    rows_elided INTEGER,
    tokens_est INTEGER,
    digest_mode INTEGER,
    entailed INTEGER,
    consistent INTEGER,
    contradicted INTEGER,
    elision_regret INTEGER,
    sigma_claims INTEGER
);
CREATE INDEX IF NOT EXISTS idx_fact_leaf_run_shape ON fact_leaf_run(scope_shape_dim, task_kind_dim);
CREATE INDEX IF NOT EXISTS idx_fact_leaf_run_repo ON fact_leaf_run(repo_dim, run_id);

CREATE TABLE IF NOT EXISTS fact_run_event (
    id INTEGER PRIMARY KEY,
    run_id TEXT NOT NULL,
    repo_dim INTEGER NOT NULL REFERENCES dim_repo(id),
    event TEXT NOT NULL,
    reason TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_fact_run_event_run ON fact_run_event(run_id);

-- M9.3 (6.7): the durable corpus a lesson-set is cut from. A row lands here
-- the moment `cdp reflect` accepts a promotion (R10-validated already, by
-- `reflect.validate_promotion` -- this table only ever holds what passed
-- that gate) and sits with cut_version=NULL until `cdp lessons cut` assigns
-- it a version. Once assigned, a row's cut_version never changes again --
-- that immutability is what makes `--lessons vN` reproduce exactly.
CREATE TABLE IF NOT EXISTS lesson_promotion (
    id INTEGER PRIMARY KEY,
    run_id TEXT NOT NULL,
    node TEXT NOT NULL,
    kind TEXT NOT NULL,
    payload TEXT NOT NULL,
    cut_version INTEGER,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_lesson_promotion_cut ON lesson_promotion(cut_version);

-- M9.3 (6.8): a cut is not "latest" the moment it exists -- it becomes latest
-- only once `cdp holdout` has A/B'd it against a repo outside the corpus that
-- produced it and the promotion bar passed. `promoted=0` on creation
-- (`cut_lessons`); `promote_cut` is the only writer that ever flips it to 1.
CREATE TABLE IF NOT EXISTS lesson_cut (
    version INTEGER PRIMARY KEY,
    promoted INTEGER NOT NULL DEFAULT 0,
    holdout_repo TEXT,
    holdout_metric TEXT,
    created_at TEXT NOT NULL
);
"""

#: Post-Phase-9 follow-up ("cdp lessons unpromote"): a revert path for a cut
#: that later shows harm. R4's write-always posture applies here exactly as
#: it does to `fact_run_event(rolled_back, reason)` -- `unpromote_cut` flips
#: `promoted` back to 0 but never clears `holdout_repo`/`holdout_metric` (the
#: promotion still happened; nothing is retracted), and records when and why
#: on top rather than overwriting the promotion record in place.
_LESSON_CUT_MIGRATION_COLUMNS = (
    ("unpromoted_at", "TEXT"), ("unpromote_reason", "TEXT"),
)

#: M9.2 (6.3): columns added after `fact_leaf_run` first shipped (M9.1) --
#: a pre-existing `trajectories.db` (R4: write-always, never destroyed) needs
#: these added in place, since `CREATE TABLE IF NOT EXISTS` is a no-op against
#: a table that already exists without them.
_LEAF_RUN_MIGRATION_COLUMNS = (
    ("rows_elided", "INTEGER"), ("tokens_est", "INTEGER"), ("digest_mode", "INTEGER"),
    ("entailed", "INTEGER"), ("consistent", "INTEGER"), ("contradicted", "INTEGER"),
    ("elision_regret", "INTEGER"), ("sigma_claims", "INTEGER"),
)

#: R10/R4: a fact row never carries claim content, only routing-shaped
#: metadata -- enforced here by construction (no column can hold a claim
#: string) rather than by convention.
_TASK_KINDS = ("scope", "link")


def trajectory_db_path() -> Path:
    override = os.environ.get("CDP_TRAJECTORY_DB")
    return Path(override) if override else Path.home() / ".cdp" / "trajectories.db"


def scope_shape_key(scope: Dict) -> str:
    """Bucketed, not identity-keyed (0.18): file-count power-of-two plus the
    scope's language/role composition. Coarse on purpose -- M9.2's routing
    prior groups on this to find shape-alike neighbours across repos, which
    only works if the key generalises rather than fingerprinting one scope."""
    n = scope.get("file_count", 0) or 0
    bucket = 1
    while bucket < max(n, 1):
        bucket *= 2
    langs = ",".join(sorted((scope.get("by_language") or {}).keys()))
    roles = ",".join(sorted((scope.get("by_role") or {}).keys()))
    return "files<=%d|langs=%s|roles=%s" % (bucket, langs, roles)


def elision_regret(elided_subjects, unknown_subjects) -> bool:
    """6.4: did this leaf ask about (as an unknown) a subject the prompt's
    own budget had already elided as a prior claim? A pure set intersection,
    kept as a named function so it is unit-testable independent of `cli.py`'s
    wave-result plumbing."""
    return bool(set(elided_subjects or []) & set(unknown_subjects or []))


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


class TrajectoryStore:
    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = Path(path) if path is not None else trajectory_db_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = connect_raw(self.path)
        self._conn.executescript(SCHEMA)
        self._migrate_leaf_run_columns()
        self._migrate_lesson_cut_columns()
        self._conn.commit()

    def _migrate_leaf_run_columns(self) -> None:
        existing = {row[1] for row in self._conn.execute("PRAGMA table_info(fact_leaf_run)").fetchall()}
        for name, sqltype in _LEAF_RUN_MIGRATION_COLUMNS:
            if name not in existing:
                self._conn.execute("ALTER TABLE fact_leaf_run ADD COLUMN %s %s" % (name, sqltype))

    def _migrate_lesson_cut_columns(self) -> None:
        existing = {row[1] for row in self._conn.execute("PRAGMA table_info(lesson_cut)").fetchall()}
        for name, sqltype in _LESSON_CUT_MIGRATION_COLUMNS:
            if name not in existing:
                self._conn.execute("ALTER TABLE lesson_cut ADD COLUMN %s %s" % (name, sqltype))

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "TrajectoryStore":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def _dim_id(self, table: str, column: str, value: str) -> int:
        row = self._conn.execute(
            "SELECT id FROM %s WHERE %s=?" % (table, column), (value,)
        ).fetchone()
        if row is not None:
            return row[0]
        cur = self._conn.execute(
            "INSERT INTO %s (%s) VALUES (?)" % (table, column), (value,)
        )
        self._conn.commit()
        return cur.lastrowid

    def dim_repo(self, repo_id: str) -> int:
        return self._dim_id("dim_repo", "repo_id", repo_id)

    def dim_model(self, name: Optional[str]) -> int:
        return self._dim_id("dim_model", "name", name or "unknown")

    def dim_scope_shape(self, key: str) -> int:
        return self._dim_id("dim_scope_shape", "key", key)

    def dim_template(self, version: Optional[str]) -> int:
        return self._dim_id("dim_template", "version", version or "unversioned")

    def dim_tier(self, name: Optional[str]) -> int:
        return self._dim_id("dim_tier", "name", name or "unset")

    def dim_task_kind(self, name: str) -> int:
        if name not in _TASK_KINDS:
            raise ValueError("dim_task_kind is closed: %s, got %r" % (_TASK_KINDS, name))
        return self._dim_id("dim_task_kind", "name", name)

    def record_leaf_run(
        self, *, run_id: str, node: str, scope_hash: Optional[str], repo_id: str,
        model: Optional[str], scope_shape_key: str, template_version: Optional[str],
        tier: Optional[str], task_kind: str, state: str, attempts: Optional[int] = None,
        wall_ms: Optional[int] = None, patch_hash: Optional[str] = None,
        claims_emitted: Optional[int] = None, unknowns_emitted: Optional[int] = None,
        rows_elided: Optional[int] = None, tokens_est: Optional[int] = None,
        digest_mode: Optional[bool] = None, entailed: Optional[int] = None,
        consistent: Optional[int] = None, contradicted: Optional[int] = None,
        elision_regret: Optional[bool] = None, sigma_claims: Optional[int] = None,
    ) -> None:
        """M9.2 (6.3): `rows_elided`/`tokens_est`/`digest_mode`/`sigma_claims` are
        the input fingerprint (written from `prompts.build_prompt`'s own stats,
        at dispatch time); `entailed`/`consistent`/`contradicted`/`elision_regret`
        are the output scorecard (written once the leaf's patch is folded).
        Both halves join on `scope_hash`, this row's own grain."""
        self._conn.execute(
            "INSERT INTO fact_leaf_run (run_id, node, scope_hash, repo_dim, model_dim, "
            "scope_shape_dim, template_dim, tier_dim, task_kind_dim, state, attempts, "
            "wall_ms, patch_hash, claims_emitted, unknowns_emitted, created_at, "
            "rows_elided, tokens_est, digest_mode, entailed, consistent, contradicted, "
            "elision_regret, sigma_claims) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (run_id, node, scope_hash, self.dim_repo(repo_id), self.dim_model(model),
             self.dim_scope_shape(scope_shape_key), self.dim_template(template_version),
             self.dim_tier(tier), self.dim_task_kind(task_kind), state, attempts, wall_ms,
             patch_hash, claims_emitted, unknowns_emitted, _now(),
             rows_elided, tokens_est, None if digest_mode is None else int(digest_mode),
             entailed, consistent, contradicted,
             None if elision_regret is None else int(elision_regret), sigma_claims),
        )
        self._conn.commit()

    def routing_prior(self, scope_shape_key: str, task_kind: str) -> Dict:
        """6.5: nearest-neighbour on scope **shape**, not identity -- a
        `GROUP BY` over the star's own dimensions, deterministic, no model
        call. Returns the corpus's own aggregate outcome for every prior run
        of a shape-alike scope, which is what a router uses as a prior for a
        *new* scope of the same shape (this scope need not have run before)."""
        row = self._conn.execute(
            "SELECT COUNT(*), AVG(claims_emitted), AVG(unknowns_emitted), "
            "AVG(tokens_est), SUM(CASE WHEN state='validated' THEN 1 ELSE 0 END), "
            "AVG(elision_regret) "
            "FROM fact_leaf_run f "
            "JOIN dim_scope_shape s ON f.scope_shape_dim = s.id "
            "JOIN dim_task_kind k ON f.task_kind_dim = k.id "
            "WHERE s.key = ? AND k.name = ?",
            (scope_shape_key, task_kind),
        ).fetchone()
        n = row[0] or 0
        return {
            "n": n,
            "avg_claims_emitted": row[1],
            "avg_unknowns_emitted": row[2],
            "avg_tokens_est": row[3],
            "validated_rate": (row[4] / n) if n else None,
            "avg_elision_regret": row[5],
        }

    def record_run_event(self, *, run_id: str, repo_id: str, event: str, reason: Optional[str] = None) -> None:
        self._conn.execute(
            "INSERT INTO fact_run_event (run_id, repo_dim, event, reason, created_at) "
            "VALUES (?,?,?,?,?)",
            (run_id, self.dim_repo(repo_id), event, reason, _now()),
        )
        self._conn.commit()

    def leaf_runs_for(self, run_id: str):
        rows = self._conn.execute(
            "SELECT node, state, attempts, wall_ms, claims_emitted, unknowns_emitted, "
            "rows_elided, tokens_est, entailed, consistent, contradicted, elision_regret, "
            "sigma_claims "
            "FROM fact_leaf_run WHERE run_id=? ORDER BY id",
            (run_id,),
        ).fetchall()
        return [
            {"node": r[0], "state": r[1], "attempts": r[2], "wall_ms": r[3],
             "claims_emitted": r[4], "unknowns_emitted": r[5],
             "rows_elided": r[6], "tokens_est": r[7], "entailed": r[8],
             "consistent": r[9], "contradicted": r[10], "elision_regret": r[11],
             "sigma_claims": r[12]}
            for r in rows
        ]

    def finished_run_count(self) -> int:
        """Global (cross-repo) count of `finished` run events -- the cadence
        clock for the lessons hint (`cdp run` nudges every LESSONS_HINT_EVERY
        finished runs), not per-repo: the corpus itself is cross-workspace
        (M9.1), so the cadence that governs it is too."""
        row = self._conn.execute(
            "SELECT COUNT(*) FROM fact_run_event WHERE event='finished'"
        ).fetchone()
        return row[0] or 0

    def events_for(self, run_id: str):
        rows = self._conn.execute(
            "SELECT event, reason, created_at FROM fact_run_event WHERE run_id=? ORDER BY id",
            (run_id,),
        ).fetchall()
        return [{"event": r[0], "reason": r[1], "created_at": r[2]} for r in rows]

    # ------------------------------------------------------- lesson-sets (M9.3, 6.7)

    def record_promotion(self, *, run_id: str, node: str, promotion: Dict) -> None:
        """Persist one R10-validated promotion (`reflect.validate_promotion`
        already passed it) into the durable corpus, unassigned to any cut
        yet. `payload` is the promotion dict verbatim -- kind plus its own
        closed field set, never claim-shaped, by construction upstream."""
        self._conn.execute(
            "INSERT INTO lesson_promotion (run_id, node, kind, payload, cut_version, created_at) "
            "VALUES (?, ?, ?, ?, NULL, ?)",
            (run_id, node, promotion["promotion"], json.dumps(promotion), _now()),
        )
        self._conn.commit()

    def pending_promotion_count(self) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) FROM lesson_promotion WHERE cut_version IS NULL"
        ).fetchone()
        return row[0] or 0

    def latest_lesson_version(self) -> Optional[int]:
        """`None` when no cut has ever happened, or none is *promoted* yet
        (6.7's "off for run #1", extended by 6.8: a cut awaiting its holdout
        A/B is not "latest" -- `--lessons vN` can still pin it explicitly)."""
        row = self._conn.execute(
            "SELECT MAX(version) FROM lesson_cut WHERE promoted=1"
        ).fetchone()
        return row[0]

    def _next_cut_version(self) -> int:
        row = self._conn.execute("SELECT MAX(version) FROM lesson_cut").fetchone()
        return (row[0] or 0) + 1

    def cut_lessons(self) -> Optional[int]:
        """Numbers and freezes every currently-pending promotion into a new
        cut. Once assigned, `cut_version` is never rewritten -- `load_lessons`
        against that version therefore always returns the same rows, which is
        what 6.7's "reproduces exactly" acceptance line requires. Returns the
        new version, or `None` if there was nothing pending to cut (an empty
        cut would just be a version number with no content). Unpromoted until
        `promote_cut` (6.8) says otherwise."""
        if self.pending_promotion_count() == 0:
            return None
        version = self._next_cut_version()
        self._conn.execute(
            "UPDATE lesson_promotion SET cut_version=? WHERE cut_version IS NULL", (version,)
        )
        self._conn.execute(
            "INSERT INTO lesson_cut (version, promoted, created_at) VALUES (?, 0, ?)",
            (version, _now()),
        )
        self._conn.commit()
        return version

    def cut_promoted(self, version: int) -> bool:
        row = self._conn.execute(
            "SELECT promoted FROM lesson_cut WHERE version=?", (version,)
        ).fetchone()
        return bool(row and row[0])

    def learned_repos_for_cut(self, version: int) -> Set[str]:
        """6.8's own stress test ("verify the split is real"): every distinct
        `dim_repo.repo_id` a promotion in this cut's corpus was actually
        learned from, via `lesson_promotion.run_id -> fact_leaf_run.run_id ->
        dim_repo`. `cdp holdout` refuses to A/B a cut against a repo that
        appears in this set."""
        rows = self._conn.execute(
            "SELECT DISTINCT d.repo_id FROM lesson_promotion lp "
            "JOIN fact_leaf_run f ON f.run_id = lp.run_id "
            "JOIN dim_repo d ON d.id = f.repo_dim "
            "WHERE lp.cut_version = ?",
            (version,),
        ).fetchall()
        return {r[0] for r in rows}

    def promote_cut(self, version: int, repo_id: str, metric: Dict) -> None:
        """The only writer of `promoted=1` (6.8): called by `cdp holdout`
        after a real A/B against a repo outside `learned_repos_for_cut`
        passes the promotion bar. Idempotent -- re-running a passing holdout
        just re-records the same verdict."""
        self._conn.execute(
            "UPDATE lesson_cut SET promoted=1, holdout_repo=?, holdout_metric=? WHERE version=?",
            (repo_id, json.dumps(metric), version),
        )
        self._conn.commit()

    def unpromote_cut(self, version: int, reason: Optional[str] = None) -> bool:
        """Reverts a promoted cut that later showed harm. Only flips
        `promoted` back to 0 -- `holdout_repo`/`holdout_metric` are left
        exactly as `promote_cut` wrote them (R4: the promotion still
        happened, nothing is retracted), with `unpromoted_at`/
        `unpromote_reason` recording this decision on top, not overwriting
        the promotion record.

        Fallback after this call: `latest_lesson_version()` re-queries
        `MAX(version) FROM lesson_cut WHERE promoted=1` fresh on every call
        (no caching), so the very next resolution -- the next `cdp run`
        that does not pass `--lessons` explicitly -- falls back to whichever
        *other* promoted cut has the highest version number, or to no
        lesson-set at all (the same cold-start state as before any cut was
        ever promoted) if none remain promoted. A run already mid-flight is
        unaffected either way: `cmd_run` resolves and pins its own
        `lessons_version` once, at the start of that run, so unpromoting
        only changes what a *future* resolution sees -- it can never
        retroactively alter a run already under way. An explicit `--lessons
        vN` pin is unaffected regardless: it never consults `promoted` at
        all, only the implicit "no flag given" default does.

        Returns `False`, changing nothing, if `version` is not currently
        promoted (already unpromoted, or never was) -- the caller decides
        whether that is worth surfacing as an error."""
        if not self.cut_promoted(version):
            return False
        self._conn.execute(
            "UPDATE lesson_cut SET promoted=0, unpromoted_at=?, unpromote_reason=? WHERE version=?",
            (_now(), reason, version),
        )
        self._conn.commit()
        return True

    def load_lessons(self, version: int) -> List[Dict]:
        """The pinned, immutable content of one cut -- ordered by `id` (append
        order, not wall-clock) for determinism across processes/platforms."""
        rows = self._conn.execute(
            "SELECT node, kind, payload FROM lesson_promotion WHERE cut_version=? ORDER BY id",
            (version,),
        ).fetchall()
        return [{"node": r[0], "kind": r[1], "payload": json.loads(r[2])} for r in rows]
