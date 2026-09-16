"""Snapshot identity resolution (`PHASE/phase_2_plan.md` M2.4)."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import make_repo

SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT))

from cdp.snapshot import is_dirty, resolve_snapshot  # noqa: E402


class TestResolveSnapshot(unittest.TestCase):
    def test_clean_tree_is_not_ephemeral(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(Path(tmp))
            repo_id, commit_sha, ephemeral = resolve_snapshot(repo, "abc123")
            self.assertFalse(ephemeral)
            self.assertEqual(commit_sha, "abc123")
            # M2.6: identity is never the filesystem path.
            self.assertNotEqual(repo_id, str(repo.resolve()))
            self.assertEqual(repo_id, resolve_snapshot(repo, "abc123")[0])

    def test_dirty_tree_is_ephemeral_with_a_distinct_commit_sha(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(Path(tmp))
            self.assertFalse(is_dirty(repo))
            _, clean_sha, clean_ephemeral = resolve_snapshot(repo, "abc123")
            self.assertFalse(clean_ephemeral)

            (repo / "README.md").write_text("changed\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True, capture_output=True)
            self.assertTrue(is_dirty(repo))
            _, dirty_sha, ephemeral = resolve_snapshot(repo, "abc123")
            self.assertTrue(ephemeral)
            self.assertNotEqual(dirty_sha, clean_sha)
            self.assertNotEqual(dirty_sha, "abc123")

    def test_unpinned_is_always_ephemeral(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo_id, commit_sha, ephemeral = resolve_snapshot(Path(tmp), "unpinned")
            self.assertTrue(ephemeral)
            self.assertTrue(commit_sha.startswith("unpinned:"))

    def test_two_different_repos_get_different_identities(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = make_repo(Path(tmp), fixture="minirepo")
            b = make_repo(Path(tmp), fixture="solorepo")
            id_a, _, _ = resolve_snapshot(a, "abc123")
            id_b, _, _ = resolve_snapshot(b, "abc123")
            self.assertNotEqual(id_a, id_b)


if __name__ == "__main__":
    unittest.main()
