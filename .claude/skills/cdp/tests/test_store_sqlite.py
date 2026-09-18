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


class TestRetention(unittest.TestCase):
    """M3.6/0.10: `list_snapshots`/`set_pinned`/`delete_snapshot`, the
    primitives `cdp gc` builds on. The retention *decision* itself is
    `snapshot.snapshots_to_keep` (`tests/test_snapshot.py`) -- these assert the
    storage operations it is applied against are correct."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.store = SqliteStore(Path(self._tmp.name) / "index.db")
        self.addCleanup(self.store.close)

    def test_new_snapshot_is_unpinned_by_default(self):
        self.store.begin_snapshot("repo-a", "commit-1")
        rows = self.store.list_snapshots()
        self.assertEqual(len(rows), 1)
        self.assertFalse(rows[0]["pinned"])

    def test_set_pinned_round_trips(self):
        self.store.begin_snapshot("repo-a", "commit-1")
        self.store.set_pinned("commit-1", True)
        self.assertTrue(self.store.list_snapshots()[0]["pinned"])
        self.store.set_pinned("commit-1", False)
        self.assertFalse(self.store.list_snapshots()[0]["pinned"])

    def test_set_pinned_on_unknown_commit_raises(self):
        with self.assertRaises(CdpError):
            self.store.set_pinned("no-such-commit", True)

    def test_delete_snapshot_never_touches_a_sibling_snapshot(self):
        self.store.begin_snapshot("repo-a", "commit-1")
        self.store.append_patch({"node": "root", "status": "complete"}, "root")
        self.store.write_artifact("inventory", {"head": "commit-1"})
        [dropped] = [r for r in self.store.list_snapshots() if r["commit_sha"] == "commit-1"]

        self.store.begin_snapshot("repo-a", "commit-2")
        self.store.append_patch({"node": "root", "status": "complete"}, "root2")
        self.store.write_artifact("inventory", {"head": "commit-2"})

        self.store.delete_snapshot(dropped["id"])

        remaining = self.store.list_snapshots()
        self.assertEqual([r["commit_sha"] for r in remaining], ["commit-2"])
        self.store.begin_snapshot("repo-a", "commit-2")
        self.assertEqual(self.store.read_artifact("inventory"), {"head": "commit-2"})
        self.assertEqual(len(self.store.load_patches()), 1)


class TestCompaction(unittest.TestCase):
    """Phase 7, M7.3/2.4: `cdp compact` moves superseded `complete` generations
    to `claim_patches_archive`, never deletes (R5)."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.store = SqliteStore(Path(self._tmp.name) / "index.db")
        self.addCleanup(self.store.close)
        self.store.begin_snapshot("repo-a", "commit-1")

    def _append(self, generation, claim_text):
        self.store.append_patch(
            {"node": "root/a", "status": "complete", "run_id": "run-%d" % generation,
             "generation": generation, "claims": [{"claim": claim_text}]},
            "root/a-%d" % generation,
        )

    def test_below_threshold_moves_nothing(self):
        self._append(1, "first")
        result = self.store.compact(keep_generations=1, threshold=0.30)
        self.assertFalse(result["threshold_met"])
        self.assertEqual(result["moved"], 0)
        self.assertEqual(len(self.store.load_patches()), 1)

    def test_five_generations_keep_one_moves_four(self):
        for gen in range(1, 6):
            self._append(gen, "claim-%d" % gen)
        result = self.store.compact(keep_generations=1, threshold=0.30)
        self.assertTrue(result["threshold_met"])
        self.assertEqual(result["moved"], 4)
        self.assertEqual(result["kept"], 1)
        remaining = self.store.load_patches()
        self.assertEqual(len(remaining), 1)
        self.assertEqual(remaining[0]["generation"], 5)

    def test_archived_rows_are_never_deleted_only_relocated(self):
        for gen in range(1, 6):
            self._append(gen, "claim-%d" % gen)
        self.store.compact(keep_generations=1, threshold=0.30)
        archived = self.store._conn.execute(
            "SELECT run_id, payload FROM claim_patches_archive"
        ).fetchall()
        self.assertEqual(len(archived), 4)
        archived_run_ids = {r[0] for r in archived}
        self.assertEqual(archived_run_ids, {"run-1", "run-2", "run-3", "run-4"})

    def test_dry_run_moves_nothing(self):
        for gen in range(1, 6):
            self._append(gen, "claim-%d" % gen)
        result = self.store.compact(keep_generations=1, threshold=0.30, dry_run=True)
        self.assertEqual(result["moved"], 4)
        self.assertEqual(len(self.store.load_patches()), 5)
        archived = self.store._conn.execute(
            "SELECT 1 FROM claim_patches_archive"
        ).fetchall()
        self.assertEqual(archived, [])

    def test_hot_query_after_compaction_still_sees_the_kept_generation(self):
        for gen in range(1, 6):
            self._append(gen, "claim-%d" % gen)
        self.store.compact(keep_generations=1, threshold=0.30)
        remaining = self.store.load_patches()
        self.assertEqual(len(remaining), 1)
        self.assertEqual(remaining[0]["claims"], [{"claim": "claim-5"}])

    def test_pending_patches_are_not_generations_and_are_never_archived(self):
        self._append(1, "first")
        self.store.append_patch(
            {"node": "root/a", "status": "pending", "run_id": "run-pending"},
            "root/a-pending",
        )
        result = self.store.compact(keep_generations=1, threshold=0.0)
        self.assertEqual(result["moved"], 0)
        self.assertEqual(len(self.store.load_patches()), 2)


class TestVerifyFull(unittest.TestCase):
    """Phase 7, M7.4/2.5: `verify --full` re-folds from the archive too."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.store = SqliteStore(Path(self._tmp.name) / "index.db")
        self.addCleanup(self.store.close)
        self.store.begin_snapshot("repo-a", "commit-1")
        for gen in range(1, 4):
            self.store.append_patch(
                {"node": "root/a", "status": "complete", "run_id": "run-%d" % gen,
                 "generation": gen, "claims": [{"claim": "claim-%d" % gen}]},
                "root/a-%d" % gen,
            )

    def test_load_patches_full_includes_archived_generations(self):
        before = len(self.store.load_patches_full())
        self.store.compact(keep_generations=1, threshold=0.0)
        after_hot = self.store.load_patches()
        after_full = self.store.load_patches_full()
        self.assertEqual(len(after_hot), 1)
        self.assertEqual(len(after_full), before)

    def test_verify_archive_integrity_clean_after_compaction(self):
        self.store.compact(keep_generations=1, threshold=0.0)
        self.assertEqual(self.store.verify_archive_integrity(), [])

    def test_verify_archive_integrity_names_a_corrupted_row(self):
        self.store.compact(keep_generations=1, threshold=0.0)
        rowid = self.store._conn.execute(
            "SELECT rowid FROM claim_patches_archive LIMIT 1"
        ).fetchone()[0]
        self.store._conn.execute(
            "UPDATE claim_patches_archive SET payload = "
            "json_set(payload, '$.claims[0].claim', 'tampered') WHERE rowid=?",
            (rowid,),
        )
        self.store._conn.commit()
        problems = self.store.verify_archive_integrity()
        self.assertEqual(len(problems), 1)
        self.assertIn("rowid %d" % rowid, problems[0])

    def test_uncompacted_store_has_nothing_for_full_to_add(self):
        self.assertEqual(self.store.load_patches_full(), self.store.load_patches())
        self.assertEqual(self.store.verify_archive_integrity(), [])


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

    def test_get_run_returns_none_then_the_row_once_begun(self):
        self.assertIsNone(self.store.get_run("r1"))
        self.store.begin_run("r1", "hash-a")
        row = self.store.get_run("r1")
        self.assertEqual(row, {"run_id": "r1", "partition_hash": "hash-a", "status": "running",
                               "lessons_version": None})

    def test_reclaim_expired_moves_only_dispatched_past_lease(self):
        self.store.begin_run("r1", "hash-a")
        self.store.upsert_task("r1", "h-dispatched-expired", state="dispatched",
                                lease_until="2000-01-01T00:00:00+00:00")
        self.store.upsert_task("r1", "h-dispatched-live", state="dispatched")
        self.store.acquire_lease("r1", "h-dispatched-live", 3600)  # live, far-future lease
        self.store.upsert_task("r1", "h-folded", state="folded")
        reclaimed = self.store.reclaim_expired("r1")
        self.assertEqual(reclaimed, ["h-dispatched-expired"])
        states = self.store.task_states("r1")
        self.assertEqual(states["h-dispatched-expired"]["state"], "expired")
        self.assertEqual(states["h-dispatched-live"]["state"], "dispatched")
        self.assertEqual(states["h-folded"]["state"], "folded")

    def test_copy_folded_tasks_only_copies_folded_rows(self):
        self.store.begin_run("r1", "hash-a")
        self.store.upsert_task("r1", "h-folded", state="folded", attempts=2, last_error=None)
        self.store.upsert_task("r1", "h-abandoned", state="abandoned", attempts=3)
        self.store.begin_run("r2", "hash-b")
        self.store.copy_folded_tasks("r1", "r2", ["h-folded", "h-abandoned", "h-never-seen"])
        states = self.store.task_states("r2")
        self.assertEqual(set(states), {"h-folded"})
        self.assertEqual(states["h-folded"]["state"], "folded")
        self.assertEqual(states["h-folded"]["attempts"], 2)


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


class TestLinkEdgePersistence(unittest.TestCase):
    """M8.2: `link_edge` round-trips a `link scan --db`'s links/unmatched
    calls, and a second `write_link_edges` fully replaces the first rather
    than accumulating -- `link.*` is fully re-derived on every scan (R3),
    there is no history to append to.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.store = SqliteStore(Path(self._tmp.name) / "index.db")
        self.addCleanup(self.store.close)

    def test_write_then_read_round_trips(self):
        report = {
            "links": [{"protocol": "http_out", "match_kind": "exact", "self_link": False,
                       "caller": {"repo": "billing", "target": "x"},
                       "callee": {"repo": "orders", "target": "y"}}],
            "unmatched": [{"protocol": "http_out", "outbound": {"repo": "billing", "target": "z"}}],
        }
        self.store.write_link_edges(report)
        rows = self.store.read_link_edges()
        self.assertEqual(len(rows), 2)
        kinds = sorted(r["kind"] for r in rows)
        self.assertEqual(kinds, ["link", "unmatched"])

    def test_second_write_replaces_the_first(self):
        self.store.write_link_edges({"links": [{"a": 1}], "unmatched": []})
        self.store.write_link_edges({"links": [], "unmatched": [{"b": 2}]})
        rows = self.store.read_link_edges()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["kind"], "unmatched")


if __name__ == "__main__":
    unittest.main()
