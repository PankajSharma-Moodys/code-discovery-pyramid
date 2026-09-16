"""SQLite-specific store assertions (`PHASE/phase_2_plan.md` M2.2).

Conformance is covered by `test_store_conformance.SqliteStoreConformance`;
these are the properties unique to the backend swap: single-module `sqlite3`
import, content-addressing, and migration bookkeeping.
"""

from __future__ import annotations

import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import MiniRepoTest

SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT))

from cdp import state as state_mod  # noqa: E402
from cdp.store import FileStore, SqliteStore  # noqa: E402
from cdp.store.sqlite_backend import MIGRATIONS  # noqa: E402
from cdp.util import CdpError  # noqa: E402


class TestSqliteImportBoundary(unittest.TestCase):
    def test_sqlite3_is_imported_in_exactly_one_module(self):
        hits = []
        for path in sorted((SKILL_ROOT / "cdp").rglob("*.py")):
            text = path.read_text(encoding="utf-8")
            if re.search(r"^\s*import sqlite3\b", text, re.MULTILINE):
                hits.append(str(path.relative_to(SKILL_ROOT)))
        self.assertEqual(hits, ["cdp/store/sqlite_backend.py"])


class TestContentAddressing(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.store = SqliteStore(Path(self._tmp.name) / "index.db")
        self.addCleanup(self.store.close)

    def test_identical_patch_reappending_is_a_no_op(self):
        patch = {"node": "a", "run_id": "r1", "status": "complete", "claims": []}
        first = self.store.append_patch(patch, "a")
        second = self.store.append_patch(patch, "a")
        self.assertEqual(first, second)
        self.assertEqual(len(self.store.load_patches()), 1)

    def test_same_claims_different_run_id_is_not_collapsed(self):
        # The stress test this guards: content-addressing must not silently
        # drop a differing run_id needed for audit.
        a = {"node": "a", "run_id": "r1", "status": "complete", "claims": []}
        b = {"node": "a", "run_id": "r2", "status": "complete", "claims": []}
        self.store.append_patch(a, "a")
        self.store.append_patch(b, "a")
        patches = self.store.load_patches()
        self.assertEqual(len(patches), 2)
        self.assertEqual({p["run_id"] for p in patches}, {"r1", "r2"})


class TestMigrations(unittest.TestCase):
    def test_schema_version_row_exists_after_first_use(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = SqliteStore(Path(tmp) / "index.db")
            self.addCleanup(store.close)
            store.write_artifact("inventory", {"head": "abc"})
            version = store._conn.execute("SELECT MAX(version) FROM schema_version").fetchone()[0]
            self.assertEqual(version, len(MIGRATIONS))

    def test_reopening_an_existing_db_does_not_recreate_or_lose_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "index.db"
            first = SqliteStore(db)
            self.addCleanup(first.close)
            first.write_artifact("inventory", {"head": "abc"})
            reopened = SqliteStore(db)
            self.addCleanup(reopened.close)
            self.assertEqual(reopened.read_artifact("inventory"), {"head": "abc"})


class TestSnapshotLineage(unittest.TestCase):
    """M2.4 (0.6/0.7): `(repo_id, commit_sha)` identity, N snapshots coexisting,
    and the ephemeral/durable distinction — the properties only `SqliteStore`
    can hold, since `FileStore` is one directory per store instance."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.store = SqliteStore(Path(self._tmp.name) / "index.db")
        self.addCleanup(self.store.close)

    def test_two_commits_produce_two_snapshots_and_both_stay_queryable(self):
        self.store.begin_snapshot("repo-a", "commit-1")
        self.store.append_patch({"node": "root", "status": "complete"}, "root")
        self.store.write_artifact("inventory", {"head": "commit-1"})

        self.store.begin_snapshot("repo-a", "commit-2")
        self.store.append_patch({"node": "root", "status": "complete"}, "root2")
        self.store.write_artifact("inventory", {"head": "commit-2"})

        self.store.begin_snapshot("repo-a", "commit-1")
        self.assertEqual(self.store.read_artifact("inventory"), {"head": "commit-1"})
        self.assertEqual(len(self.store.load_patches()), 1)

        self.store.begin_snapshot("repo-a", "commit-2")
        self.assertEqual(self.store.read_artifact("inventory"), {"head": "commit-2"})
        self.assertEqual(len(self.store.load_patches()), 1)

    def test_reselecting_the_same_commit_reuses_the_snapshot(self):
        self.store.begin_snapshot("repo-a", "commit-1")
        self.store.write_artifact("inventory", {"head": "commit-1"})
        self.store.begin_snapshot("repo-a", "commit-1")  # same coordinate again
        self.assertEqual(self.store.read_artifact("inventory"), {"head": "commit-1"})

    def test_a_dirty_tree_snapshot_refuses_to_mark_durable(self):
        self.store.begin_snapshot("repo-a", "commit-1+dirty:abc123", ephemeral=True)
        with self.assertRaises(CdpError):
            self.store.mark_durable()

    def test_a_clean_snapshot_marks_durable(self):
        self.store.begin_snapshot("repo-a", "commit-1", ephemeral=False)
        self.store.mark_durable()  # must not raise


class TestRunsAndTasks(unittest.TestCase):
    """M2.5 (0.12/0.13): schema only, driven in Phase 5."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.store = SqliteStore(Path(self._tmp.name) / "index.db")
        self.addCleanup(self.store.close)
        self.store.begin_snapshot("repo-a", "commit-1")

    def _tables(self):
        rows = self.store._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        return {r[0] for r in rows}

    def test_run_and_task_tables_exist(self):
        tables = self._tables()
        for name in ("snapshot_run", "snapshot_task", "link_run", "link_task"):
            self.assertIn(name, tables)

    def test_run_state_index_exists(self):
        rows = self.store._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='snapshot_task'"
        ).fetchall()
        self.assertIn("idx_snapshot_task_run_state", {r[0] for r in rows})

    def test_dropping_every_link_row_leaves_snapshot_and_claim_untouched(self):
        conn = self.store._conn
        conn.execute(
            "INSERT INTO snapshot_run (run_id, snapshot_id, status) VALUES ('r1', 1, 'complete')"
        )
        conn.execute(
            "INSERT INTO snapshot_task (run_id, scope_hash, state) VALUES ('r1', 'h1', 'complete')"
        )
        conn.execute("INSERT INTO link_run (run_id, payload) VALUES ('r1', '{}')")
        conn.execute("INSERT INTO link_task (run_id, scope_hash, payload) VALUES ('r1', 'h1', '{}')")
        conn.execute("INSERT INTO link_edge (payload) VALUES ('{}')")
        conn.commit()

        before = {
            "runs": conn.execute("SELECT * FROM snapshot_run").fetchall(),
            "tasks": conn.execute("SELECT * FROM snapshot_task").fetchall(),
            "artifacts": conn.execute("SELECT * FROM snapshot_artifact").fetchall(),
            "patches": conn.execute("SELECT * FROM claim_patch").fetchall(),
        }
        conn.execute("DELETE FROM link_run")
        conn.execute("DELETE FROM link_task")
        conn.execute("DELETE FROM link_edge")
        conn.commit()
        after = {
            "runs": conn.execute("SELECT * FROM snapshot_run").fetchall(),
            "tasks": conn.execute("SELECT * FROM snapshot_task").fetchall(),
            "artifacts": conn.execute("SELECT * FROM snapshot_artifact").fetchall(),
            "patches": conn.execute("SELECT * FROM claim_patch").fetchall(),
        }
        self.assertEqual(before, after)


class TestBackendEquivalence(MiniRepoTest):
    """M2.2's golden-diff acceptance, without a full `cdp scan` subprocess:
    the same patch log and artifacts, folded through either backend, produce
    byte-identical canonical JSON. Export tooling that reproduces `FileStore`'s
    exact filename scheme from an arbitrary backend is deferred to M2.6, when a
    non-file backend can actually be the CLI's default (`PHASE/FINDINGS.md`)."""

    def _patches(self):
        return [
            {
                "schema_version": "1.0.0", "node": s["node"], "run_id": "t",
                "status": "complete",
                "claims": [c for c in self.pipeline.claims if c.get("source_node") == s["node"]],
                "unknowns": [],
            }
            for s in self.pipeline.partition["scopes"]
        ]

    def test_fold_over_either_backend_is_byte_identical(self):
        with tempfile.TemporaryDirectory() as tmp:
            file_store = FileStore(Path(tmp) / "files")
            sqlite_store = SqliteStore(Path(tmp) / "db" / "index.db")
            self.addCleanup(sqlite_store.close)
            for store in (file_store, sqlite_store):
                store.write_artifact("xref", self.pipeline.xref)
                store.write_artifact("partition", self.pipeline.partition)
                for patch in self._patches():
                    store.append_patch(patch, patch["node"])

            file_state = state_mod.fold(
                file_store.load_patches(), file_store.read_artifact("xref"),
                file_store.read_artifact("partition"),
            )
            sqlite_state = state_mod.fold(
                sqlite_store.load_patches(), sqlite_store.read_artifact("xref"),
                sqlite_store.read_artifact("partition"),
            )
            self.assertEqual(
                json.dumps(file_state, sort_keys=True),
                json.dumps(sqlite_state, sort_keys=True),
            )


if __name__ == "__main__":
    unittest.main()
