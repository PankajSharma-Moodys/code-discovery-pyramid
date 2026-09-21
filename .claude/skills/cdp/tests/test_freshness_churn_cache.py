"""`churn_cache` (SCHEMA_V8, `cdp/store/sqlite_backend.py`) -- persists
`freshness.file_churned_between`'s answer keyed by `(path, since_sha,
head_sha)` so a second `bucket_counts(..., store=backend)` call for the same
commit pair never re-shells to `git log`. Exercises the real git-log path
(`file_churned_between`), not a mocked churn answer."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from cdp import freshness
from cdp.store.sqlite_backend import SqliteStore


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


class ChurnCacheTest(unittest.TestCase):
    def setUp(self) -> None:
        self.repo = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.repo, ignore_errors=True)
        _git(self.repo, "init", "-q")
        _git(self.repo, "config", "user.email", "test@example.com")
        _git(self.repo, "config", "user.name", "test")
        (self.repo / "a.py").write_text("x = 1\n", encoding="utf-8")
        _git(self.repo, "add", "-A")
        _git(self.repo, "commit", "-q", "-m", "first")
        self.since_sha = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=self.repo, check=True, capture_output=True, text=True,
        ).stdout.strip()

        (self.repo / "a.py").write_text("x = 2\n", encoding="utf-8")
        _git(self.repo, "add", "-A")
        _git(self.repo, "commit", "-q", "-m", "second")
        self.head_sha = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=self.repo, check=True, capture_output=True, text=True,
        ).stdout.strip()

        self.db_dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.db_dir, ignore_errors=True)
        self.store = SqliteStore(self.db_dir / "index.db")
        self.addCleanup(self.store.close)

    def _claim(self) -> dict:
        return {
            "claim_reviewed_at": self.since_sha,
            "evidence": [{"file": "a.py", "line": 1}],
        }

    def test_first_call_populates_cache_and_reports_stale(self) -> None:
        buckets = freshness.bucket_counts([self._claim()], self.repo, self.head_sha, store=self.store)
        self.assertEqual(buckets[freshness.STALE], 1)

        hit, churned = self.store.churn_lookup("a.py", self.since_sha, self.head_sha)
        self.assertTrue(hit)
        self.assertTrue(churned)

    def test_second_call_never_shells_to_git(self) -> None:
        freshness.bucket_counts([self._claim()], self.repo, self.head_sha, store=self.store)

        with mock.patch.object(freshness, "file_churned_between") as fake:
            buckets = freshness.bucket_counts([self._claim()], self.repo, self.head_sha, store=self.store)
        fake.assert_not_called()
        self.assertEqual(buckets[freshness.STALE], 1)

    def test_web_layer_reads_cache_without_git(self) -> None:
        """The read-only side (`ReadOnlyConnection.churn_lookup`,
        `web/api/store_reader.py`) sees the same row a writable `SqliteStore`
        populated -- no separate cache, no git access from that connection."""
        freshness.bucket_counts([self._claim()], self.repo, self.head_sha, store=self.store)
        self.store._conn.commit()

        import sys
        web_root = Path(__file__).resolve().parents[1]
        if str(web_root) not in sys.path:
            sys.path.insert(0, str(web_root))
        from web.api.store_reader import ReadOnlyConnection

        conn = ReadOnlyConnection(self.db_dir / "index.db")
        try:
            hit, churned = conn.churn_lookup("a.py", self.since_sha, self.head_sha)
        finally:
            conn.close()
        self.assertTrue(hit)
        self.assertTrue(churned)


if __name__ == "__main__":
    unittest.main()
