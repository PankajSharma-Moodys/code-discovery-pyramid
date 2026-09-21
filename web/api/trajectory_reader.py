"""Genuinely read-only access to `~/.cdp/trajectories.db`.

Same problem `store_reader.py` solves for `index.db`, one level over:
`TrajectoryStore.__init__` (`cdp/trajectory.py:167-174`) always
`executescript(SCHEMA)` + `commit()` on open, which fails against a
`mode=ro` connection even when every table already exists. So this module
never constructs a `TrajectoryStore` -- it opens the file directly, read-only,
and runs plain `SELECT`s against the star schema `cdp/trajectory.py` defines
(`fact_leaf_run` + `dim_scope_shape`/`dim_repo`/`dim_model`/`dim_tier`/
`dim_task_kind`).

`/api/trajectory` is the only consumer; there is no existing query method on
`TrajectoryStore` to wrap (it's write-only per R4, `cdp/trajectory.py`'s
module docstring) -- this is new read logic, not a wrapper.
"""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Optional

from cdp.trajectory import trajectory_db_path
from cdp.util import CdpError


class TrajectoryUnavailable(CdpError):
    """No `trajectories.db` exists yet -- no leaf has ever run anywhere on
    this machine. The route turns this into 404, not an empty-but-200 list."""


class TrajectoryLocked(CdpError):
    """Same posture as `store_reader.StoreLocked` -- a concurrent writer (any
    `cdp run`, on any repo, since this db is shared) has it open."""


class ReadOnlyTrajectoryConnection:
    def __init__(self, path: Optional[Path] = None) -> None:
        self.db_path = path if path is not None else trajectory_db_path()
        self._local = threading.local()

    def _conn(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            if not self.db_path.is_file():
                raise TrajectoryUnavailable(
                    "no trajectory corpus at %s -- no `cdp run` has recorded "
                    "a leaf outcome yet" % self.db_path
                )
            uri = "file:%s?mode=ro" % self.db_path
            try:
                conn = sqlite3.connect(uri, uri=True, check_same_thread=False)
            except sqlite3.OperationalError as exc:
                raise TrajectoryLocked(
                    "cannot open %s read-only (%s)" % (self.db_path, exc)
                ) from exc
            self._local.conn = conn
        return conn

    def query_leaf_runs(
        self, shape: Optional[str] = None, budget: int = 100,
    ) -> list:
        """One row per `fact_leaf_run`, dims resolved to their names, newest
        first. `shape=` filters to one `scope_shape_key` (`cdp/trajectory.py:141`)
        exactly -- callers compute the key the same way a run did, this never
        does fuzzy matching."""
        sql = (
            "SELECT f.run_id, f.node, dr.repo_id, dm.name AS model, "
            "ds.key AS scope_shape, dtier.name AS tier, dtk.name AS task_kind, "
            "f.state, f.attempts, f.wall_ms, f.claims_emitted, f.unknowns_emitted, "
            "f.elision_regret, f.entailed, f.consistent, f.contradicted, f.created_at "
            "FROM fact_leaf_run f "
            "JOIN dim_repo dr ON dr.id = f.repo_dim "
            "JOIN dim_model dm ON dm.id = f.model_dim "
            "JOIN dim_scope_shape ds ON ds.id = f.scope_shape_dim "
            "JOIN dim_tier dtier ON dtier.id = f.tier_dim "
            "JOIN dim_task_kind dtk ON dtk.id = f.task_kind_dim "
        )
        params: list = []
        if shape is not None:
            sql += "WHERE ds.key = ? "
            params.append(shape)
        sql += "ORDER BY f.id DESC LIMIT ?"
        params.append(max(1, min(budget, 1000)))
        try:
            rows = self._conn().execute(sql, params).fetchall()
        except sqlite3.OperationalError as exc:
            raise TrajectoryLocked(
                "%s is locked (%s)" % (self.db_path, exc)
            ) from exc
        cols = [
            "run_id", "node", "repo_id", "model", "scope_shape", "tier", "task_kind",
            "state", "attempts", "wall_ms", "claims_emitted", "unknowns_emitted",
            "elision_regret", "entailed", "consistent", "contradicted", "created_at",
        ]
        return [dict(zip(cols, row)) for row in rows]

    def close(self) -> None:
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
            self._local.conn = None
