"""Backend conformance suite (`PHASE/phase_2_plan.md` M2.1).

One set of tests every `WorkspaceStore` backend must pass. `FileStoreConformance`
is the only concrete case until M2.2 adds `SqliteStoreConformance` — the mixin
is what makes that addition a subclass rather than a second copy of these tests.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from cdp.store import FileStore, SqliteStore
from cdp.util import CdpError


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

    def test_report_is_write_only_but_does_not_raise(self):
        store = self.make_store()
        store.write_report("verify", {"claims_in": 3})  # must not raise

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


class FileStoreConformance(ConformanceMixin, unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)

    def make_store(self):
        return FileStore(Path(self._tmp.name) / ("store-%d" % id(object())))


class SqliteStoreConformance(ConformanceMixin, unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
