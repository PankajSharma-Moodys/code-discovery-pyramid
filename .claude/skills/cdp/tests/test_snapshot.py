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

from cdp.snapshot import is_dirty, resolve_snapshot, snapshots_to_keep  # noqa: E402


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


class TestSnapshotsToKeep(unittest.TestCase):
    """M3.6/0.10: kept iff HEAD, pinned, or cited by a live claim."""

    def setUp(self):
        self.snapshots = [
            {"id": 1, "repo_id": "r", "commit_sha": "a", "pinned": False},
            {"id": 2, "repo_id": "r", "commit_sha": "b", "pinned": False},
            {"id": 3, "repo_id": "r", "commit_sha": "c", "pinned": True},
            {"id": 4, "repo_id": "r", "commit_sha": "d", "pinned": False},
            {"id": 5, "repo_id": "r", "commit_sha": "e", "pinned": False},
        ]

    def test_five_snapshots_claims_citing_two_keeps_head_plus_those_two(self):
        # The plan's own acceptance line, reproduced literally: HEAD is "e",
        # two others ("b", "d") are cited by a live claim's last-verified sha.
        # "c" is also kept, independently, because it is pinned (setUp).
        keep = snapshots_to_keep(self.snapshots, "r", "e", {"b", "d"})
        self.assertEqual(keep, {5, 2, 3, 4})

    def test_pinned_snapshot_survives_with_no_citation_and_not_head(self):
        keep = snapshots_to_keep(self.snapshots, "r", "e", set())
        self.assertIn(3, keep)

    def test_uncited_unpinned_non_head_snapshot_is_dropped(self):
        keep = snapshots_to_keep(self.snapshots, "r", "e", set())
        self.assertNotIn(1, keep)
        self.assertNotIn(2, keep)

    def test_other_repo_ids_are_never_kept(self):
        other = self.snapshots + [{"id": 6, "repo_id": "other", "commit_sha": "e", "pinned": False}]
        keep = snapshots_to_keep(other, "r", "e", set())
        self.assertNotIn(6, keep)


if __name__ == "__main__":
    unittest.main()
