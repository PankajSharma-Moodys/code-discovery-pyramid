"""`refresh` freezes the heap around its fold (T3b) and always unfreezes it, exceptions included."""

from __future__ import annotations

import gc
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from helpers import have_git, make_repo

from cdp import state as state_mod
from cdp.cli import main
from test_hook import _OwnHome
from test_refresh import _commit_all


@unittest.skipUnless(have_git(), "refresh needs a real git repository")
class RefreshGcFreezeTest(_OwnHome, unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.make_home()
        self.repo = make_repo(Path(self.tmp.name))
        main(["scan", "--repo", str(self.repo), "--quiet"])
        (self.repo / "NOTES.md").write_text("changed\n")
        _commit_all(self.repo, "move HEAD")
        self.assertEqual(gc.get_freeze_count(), 0)

    def _fold_spy(self, fail: bool):
        real = state_mod.fold
        seen = []

        def spy(*args, **kwargs):
            seen.append(gc.get_freeze_count())
            if fail:
                raise RuntimeError("fold failed")
            return real(*args, **kwargs)
        return spy, seen

    def test_fold_runs_frozen_and_heap_is_unfrozen_after(self) -> None:
        spy, seen = self._fold_spy(fail=False)
        with mock.patch.object(state_mod, "fold", spy):
            main(["refresh", "--repo", str(self.repo), "--quiet"])
        self.assertEqual(len(seen), 1)
        self.assertGreater(seen[0], 0)
        self.assertEqual(gc.get_freeze_count(), 0)

    def test_heap_is_unfrozen_when_the_fold_raises(self) -> None:
        spy, seen = self._fold_spy(fail=True)
        with mock.patch.object(state_mod, "fold", spy):
            with self.assertRaises(RuntimeError):
                main(["refresh", "--repo", str(self.repo), "--quiet"])
        self.assertGreater(seen[0], 0)
        self.assertEqual(gc.get_freeze_count(), 0)


if __name__ == "__main__":
    unittest.main()
