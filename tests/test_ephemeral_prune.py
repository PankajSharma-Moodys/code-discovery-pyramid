"""Store garbage: a scan drops the uncommitted-changes snapshots it supersedes, per checkout."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import repo_layouts as L
from repo_layouts import Cdp
from test_layouts import BASE


def rows(cdp):
    backend, _ = cdp.open()
    try:
        return backend.list_snapshots()
    finally:
        backend.close()


def dirty_rows(cdp):
    return [s for s in rows(cdp) if s["ephemeral"]]


@L.needs_git
class EphemeralPruneTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)

    def test_five_dirty_scans_then_a_commit_leave_one_clean_snapshot(self):
        repo = L.java_inheritance(self.tmp)
        cdp = Cdp(self.tmp, repo.path)
        for i in range(5):
            L.dirty(repo, BASE, "\n// wip %d\n" % i)
            cdp.scan()
            self.assertEqual(len(dirty_rows(cdp)), 1, "a checkout keeps only its newest dirty snapshot")
        repo.commit("land it")
        cdp.scan()
        left = [s for s in rows(cdp) if s["repo_id"]]
        self.assertEqual([s["ephemeral"] for s in left], [False])
        self.assertEqual(left[0]["commit_sha"], repo.head())

    def test_reverting_and_scanning_clean_drops_the_dirty_row(self):
        repo = L.java_inheritance(self.tmp)
        cdp = Cdp(self.tmp, repo.path)
        cdp.scan()
        L.dirty(repo, BASE, "\n// wip\n")
        cdp.scan()
        self.assertEqual(len(dirty_rows(cdp)), 1)
        repo.git("checkout", "--", BASE)
        cdp.scan()
        self.assertEqual(dirty_rows(cdp), [])

    def test_two_worktrees_each_keep_their_own_dirty_snapshot(self):
        repo = L.java_inheritance(self.tmp)
        cdp = Cdp(self.tmp, repo.path)
        cdp.scan()
        wt = L.add_worktree(repo, "feature")
        other = Cdp(self.tmp, wt.path, home=cdp.home)
        L.dirty(repo, BASE, "\n// main wip\n")
        L.dirty(wt, BASE, "\n// feature wip\n")
        cdp.scan()
        other.scan()
        self.assertEqual(len(dirty_rows(cdp)), 2)
        L.dirty(wt, BASE, "// more feature wip\n")
        other.scan()
        mine = {s["commit_sha"] for s in dirty_rows(cdp)}
        self.assertEqual(len(mine), 2, "the worktree replaced its own row and left the other's")
        self.assertIn(cdp.answering_snapshot()["commit_sha"], mine)

    def test_a_row_another_checkout_still_stands_on_survives(self):
        repo = L.java_inheritance(self.tmp)
        cdp = Cdp(self.tmp, repo.path)
        cdp.scan()
        wt = L.add_worktree(repo, "feature")
        other = Cdp(self.tmp, wt.path, home=cdp.home)
        for r in (repo, wt):
            L.dirty(r, BASE, "\n// same edit\n")
        cdp.scan()
        other.scan()
        self.assertEqual(len(dirty_rows(cdp)), 1, "identical dirty trees share one row")
        L.dirty(wt, BASE, "// then it moved on\n")
        other.scan()
        self.assertEqual(len(dirty_rows(cdp)), 2, "the shared row stays for the checkout still on it")

    def test_a_pinned_dirty_snapshot_is_never_dropped(self):
        repo = L.java_inheritance(self.tmp)
        cdp = Cdp(self.tmp, repo.path)
        L.dirty(repo, BASE, "\n// wip\n")
        cdp.scan()
        backend, _ = cdp.open()
        try:
            sha = dirty_rows(cdp)[0]["commit_sha"]
            backend.set_pinned(sha, True, dirty_rows(cdp)[0]["repo_id"])
        finally:
            backend.close()
        L.dirty(repo, BASE, "// next\n")
        cdp.scan()
        self.assertEqual(len(dirty_rows(cdp)), 2)

    def test_gc_dry_run_lists_dirty_rows_separately(self):
        repo = L.java_inheritance(self.tmp)
        cdp = Cdp(self.tmp, repo.path)
        L.dirty(repo, BASE, "\n// wip\n")
        cdp.scan()
        wt = L.add_worktree(repo, "feature")  # a clean scan elsewhere gives gc a HEAD snapshot
        Cdp(self.tmp, wt.path, home=cdp.home).scan()
        out = cdp.run("gc", "--dry-run").stdout
        self.assertIn("(1 uncommitted-changes)", out)
        self.assertRegex(out, r"drop uncommitted-changes snapshot \S+\+dirty:\S+ \[dry-run\]")
        self.assertEqual(len(dirty_rows(cdp)), 1, "a dry run drops nothing")


if __name__ == "__main__":
    unittest.main()
