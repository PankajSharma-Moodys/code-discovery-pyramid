"""Backend conformance suite (`PHASE/phase_2_plan.md` M2.1).

One set of tests every `WorkspaceStore` backend must pass. `FileStoreConformance`
is the only concrete case until M2.2 adds `SqliteStoreConformance` — the mixin
is what makes that addition a subclass rather than a second copy of these tests.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from cdp.store import FileStore, SqliteStore
from cdp.util import CdpError

POSTGRES_DSN = os.environ.get("CDP_TEST_POSTGRES_DSN")


class ConformanceMixin:
    """Assertions every backend must satisfy. Mix into a `unittest.TestCase`
    that sets `self.make_store()` to a fresh, empty store per test."""

    def make_store(self):
        raise NotImplementedError

    def test_missing_artifact_without_default_raises(self):
        store = self.make_store()
        with self.assertRaises(CdpError):
            store.read_artifact("inventory")

    def test_missing_artifact_with_default_returns_it(self):
        store = self.make_store()
        self.assertEqual(store.read_artifact("state", {"claims": []}), {"claims": []})

    def test_has_artifact_before_and_after_write(self):
        store = self.make_store()
        self.assertFalse(store.has_artifact("inventory"))
        store.write_artifact("inventory", {"head": "abc"})
        self.assertTrue(store.has_artifact("inventory"))

    def test_written_artifact_round_trips(self):
        store = self.make_store()
        payload = {"a": 1, "b": [1, 2, 3], "c": {"nested": True}}
        store.write_artifact("graph", payload)
        self.assertEqual(store.read_artifact("graph"), payload)

    def test_exists_tracks_inventory_presence(self):
        store = self.make_store()
        self.assertFalse(store.exists())
        store.write_artifact("inventory", {"head": "abc"})
        self.assertTrue(store.exists())

    def test_missing_report_without_default_raises(self):
        store = self.make_store()
        with self.assertRaises(CdpError):
            store.read_report("verify")

    def test_missing_report_with_default_returns_it(self):
        store = self.make_store()
        self.assertEqual(store.read_report("verify", {}), {})

    def test_written_report_round_trips(self):
        store = self.make_store()
        store.write_report("verify", {"claims_in": 3})
        self.assertEqual(store.read_report("verify"), {"claims_in": 3})

    def test_empty_patch_log_is_an_empty_list(self):
        store = self.make_store()
        self.assertEqual(store.load_patches(), [])

    def test_append_patch_is_visible_to_load_patches(self):
        store = self.make_store()
        store.append_patch({"node": "a", "status": "complete"}, "a")
        store.append_patch({"node": "b", "status": "complete"}, "b")
        patches = store.load_patches()
        self.assertEqual(len(patches), 2)
        self.assertEqual({p["node"] for p in patches}, {"a", "b"})

    def test_load_patches_has_a_canonical_order(self):
        # Nothing downstream may *depend* on the order, but it must be
        # deterministic run over run -- state.check_order_independence tests
        # the fold's insensitivity to it separately.
        store = self.make_store()
        store.append_patch({"node": "a"}, "a")
        store.append_patch({"node": "b"}, "b")
        first = [p["node"] for p in store.load_patches()]
        second = [p["node"] for p in store.load_patches()]
        self.assertEqual(first, second)

    def test_write_derived_patch_is_idempotent_and_overwrites(self):
        store = self.make_store()
        store.write_derived_patch({"node": "root", "run_id": "1"})
        store.write_derived_patch({"node": "root", "run_id": "2"})
        patches = store.load_patches()
        self.assertEqual(len(patches), 1)
        self.assertEqual(patches[0]["run_id"], "2")

    def test_derived_patch_and_leaf_patches_coexist(self):
        store = self.make_store()
        store.write_derived_patch({"node": "root", "run_id": "1"})
        store.append_patch({"node": "leaf", "status": "complete"}, "leaf")
        self.assertEqual(len(store.load_patches()), 2)

    def test_inbox_starts_empty_after_ensure(self):
        store = self.make_store()
        store.ensure_inbox()
        self.assertEqual(store.read_inbox(), [])

    def test_reading_inbox_without_ensure_raises(self):
        store = self.make_store()
        with self.assertRaises(CdpError):
            store.read_inbox()

    def test_clear_inbox_is_a_no_op_when_absent(self):
        store = self.make_store()
        store.ensure_inbox()
        store.clear_inbox("no-such-node")  # must not raise

    def test_snapshot_calls_are_safe_on_every_backend(self):
        # Every backend accepts these (M2.4); only `SqliteStore` gives them
        # real multi-snapshot meaning (`test_store_sqlite.TestSnapshotLineage`).
        store = self.make_store()
        store.begin_snapshot("repo-a", "deadbeef", ephemeral=False)
        store.mark_durable()  # must not raise: not ephemeral
        store.write_artifact("inventory", {"head": "deadbeef"})
        self.assertEqual(store.read_artifact("inventory"), {"head": "deadbeef"})


class RunTaskLeaseMixin:
    """Run/task/lease/retention assertions every *multi-writer-capable*
    backend must satisfy identically -- ported from `test_store_sqlite.py`'s
    `TestSnapshotLineage`/`TestRetention`/`TestRunsAndTasks` so `SqliteStore`
    and `PostgresStore` are proven against the same behaviour, not just
    Sqlite. Deliberately not mixed into `FileStoreConformance`: `FileStore`
    inherits `WorkspaceStore`'s default refusal (`test_store_conformance.py`
    `FileStoreRefusesRunTracking`, below) instead of these."""

    def test_two_commits_produce_two_snapshots_and_both_stay_queryable(self):
        store = self.make_store()
        store.begin_snapshot("repo-a", "commit-1")
        store.append_patch({"node": "root", "status": "complete"}, "root")
        store.write_artifact("inventory", {"head": "commit-1"})

        store.begin_snapshot("repo-a", "commit-2")
        store.append_patch({"node": "root", "status": "complete"}, "root2")
        store.write_artifact("inventory", {"head": "commit-2"})

        store.begin_snapshot("repo-a", "commit-1")
        self.assertEqual(store.read_artifact("inventory"), {"head": "commit-1"})
        self.assertEqual(len(store.load_patches()), 1)

        store.begin_snapshot("repo-a", "commit-2")
        self.assertEqual(store.read_artifact("inventory"), {"head": "commit-2"})
        self.assertEqual(len(store.load_patches()), 1)

    def test_new_snapshot_is_unpinned_by_default(self):
        store = self.make_store()
        store.begin_snapshot("repo-a", "commit-1")
        rows = store.list_snapshots()
        self.assertEqual(len(rows), 1)
        self.assertFalse(rows[0]["pinned"])

    def test_set_pinned_round_trips(self):
        store = self.make_store()
        store.begin_snapshot("repo-a", "commit-1")
        store.set_pinned("commit-1", True)
        self.assertTrue(store.list_snapshots()[0]["pinned"])
        store.set_pinned("commit-1", False)
        self.assertFalse(store.list_snapshots()[0]["pinned"])

    def test_set_pinned_on_unknown_commit_raises(self):
        store = self.make_store()
        with self.assertRaises(CdpError):
            store.set_pinned("no-such-commit", True)

    def test_delete_snapshot_never_touches_a_sibling_snapshot(self):
        store = self.make_store()
        store.begin_snapshot("repo-a", "commit-1")
        store.append_patch({"node": "root", "status": "complete"}, "root")
        store.write_artifact("inventory", {"head": "commit-1"})
        [dropped] = [r for r in store.list_snapshots() if r["commit_sha"] == "commit-1"]

        store.begin_snapshot("repo-a", "commit-2")
        store.append_patch({"node": "root", "status": "complete"}, "root2")
        store.write_artifact("inventory", {"head": "commit-2"})

        store.delete_snapshot(dropped["id"])

        remaining = store.list_snapshots()
        self.assertEqual([r["commit_sha"] for r in remaining], ["commit-2"])
        store.begin_snapshot("repo-a", "commit-2")
        self.assertEqual(store.read_artifact("inventory"), {"head": "commit-2"})
        self.assertEqual(len(store.load_patches()), 1)

    def test_get_run_returns_none_then_the_row_once_begun(self):
        store = self.make_store()
        store.begin_snapshot("repo-a", "commit-1")
        self.assertIsNone(store.get_run("r1"))
        store.begin_run("r1", "hash-a")
        row = store.get_run("r1")
        self.assertEqual(row, {"run_id": "r1", "partition_hash": "hash-a", "status": "running",
                               "lessons_version": None})

    def test_reclaim_expired_moves_only_dispatched_past_lease(self):
        store = self.make_store()
        store.begin_snapshot("repo-a", "commit-1")
        store.begin_run("r1", "hash-a")
        store.upsert_task("r1", "h-dispatched-expired", state="dispatched",
                           lease_until="2000-01-01T00:00:00+00:00")
        store.upsert_task("r1", "h-dispatched-live", state="dispatched")
        store.acquire_lease("r1", "h-dispatched-live", 3600)  # live, far-future lease
        store.upsert_task("r1", "h-folded", state="folded")
        reclaimed = store.reclaim_expired("r1")
        self.assertEqual(reclaimed, ["h-dispatched-expired"])
        states = store.task_states("r1")
        self.assertEqual(states["h-dispatched-expired"]["state"], "expired")
        self.assertEqual(states["h-dispatched-live"]["state"], "dispatched")
        self.assertEqual(states["h-folded"]["state"], "folded")

    def test_copy_folded_tasks_only_copies_folded_rows(self):
        store = self.make_store()
        store.begin_snapshot("repo-a", "commit-1")
        store.begin_run("r1", "hash-a")
        store.upsert_task("r1", "h-folded", state="folded", attempts=2, last_error=None)
        store.upsert_task("r1", "h-abandoned", state="abandoned", attempts=3)
        store.begin_run("r2", "hash-b")
        store.copy_folded_tasks("r1", "r2", ["h-folded", "h-abandoned", "h-never-seen"])
        states = store.task_states("r2")
        self.assertEqual(set(states), {"h-folded"})
        self.assertEqual(states["h-folded"]["state"], "folded")
        self.assertEqual(states["h-folded"]["attempts"], 2)

    def test_acquire_lease_is_atomic_only_one_of_many_racers_wins(self):
        store = self.make_store()
        store.begin_snapshot("repo-a", "commit-1")
        store.begin_run("r1", "hash-a")
        wins = [store.acquire_lease("r1", "scope1", 30) for _ in range(5)]
        self.assertEqual(sum(wins), 1)

    def test_supports_run_tracking_is_true(self):
        self.assertTrue(self.make_store().supports_run_tracking())


class FileStoreConformance(ConformanceMixin, unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)

    def make_store(self):
        return FileStore(Path(self._tmp.name) / ("store-%d" % id(object())))


class FileStoreRefusesRunTracking(unittest.TestCase):
    """`FileStore` inherits `WorkspaceStore`'s default refusal for the
    write-side run/task/lease methods -- `cdp run`/`cdp gc` must fail with a
    clear `CdpError`, not an `AttributeError` deep in `supervisor.py`."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.store = FileStore(Path(self._tmp.name) / "store")

    def test_begin_run_raises_clearly(self):
        with self.assertRaises(CdpError):
            self.store.begin_run("r1")

    def test_acquire_lease_raises_clearly(self):
        with self.assertRaises(CdpError):
            self.store.acquire_lease("r1", "s1", 30)

    def test_read_side_defaults_are_honest_empties_not_raises(self):
        self.assertEqual(self.store.list_snapshots(), [])
        self.assertIsNone(self.store.get_run("r1"))
        self.assertEqual(self.store.task_states("r1"), {})
        self.store.copy_patches_from(1)  # no-op, must not raise

    def test_supports_run_tracking_is_false(self):
        self.assertFalse(self.store.supports_run_tracking())


class SqliteStoreConformance(ConformanceMixin, RunTaskLeaseMixin, unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self._n = 0

    def make_store(self):
        self._n += 1
        root = Path(self._tmp.name) / ("db-%d" % self._n)
        store = SqliteStore(root / "index.db")
        self.addCleanup(store.close)
        return store


@unittest.skipUnless(POSTGRES_DSN, "set CDP_TEST_POSTGRES_DSN to run the Postgres conformance suite")
class PostgresStoreConformance(ConformanceMixin, RunTaskLeaseMixin, unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self._n = 0
        self._stores = []
        self.addCleanup(self._drop_schemas)

    def _drop_schemas(self):
        for store in self._stores:
            store.drop_schema()
            store.close()

    def make_store(self):
        from cdp.store.postgres_backend import PostgresStore

        self._n += 1
        schema = "cdp_test_%d_%d" % (os.getpid(), self._n)
        store = PostgresStore(
            POSTGRES_DSN, schema, inbox_root=Path(self._tmp.name) / ("s%d" % self._n)
        )
        self._stores.append(store)
        return store


if __name__ == "__main__":
    unittest.main()
