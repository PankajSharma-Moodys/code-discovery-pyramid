"""`GET /api/snapshots` -- ordered scanned-commit history for the time
scrubber's timeline. Needs real commits scanned into one shared
`--state-dir`, same fixture pattern as `test_diff_endpoint.py`."""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True,
    )
    return result.stdout.strip()


class SnapshotsEndpointTest(unittest.TestCase):
    def setUp(self) -> None:
        self.repo_dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.repo_dir, ignore_errors=True)
        self.state_dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.state_dir, ignore_errors=True)

        _git(self.repo_dir, "init", "-q")
        _git(self.repo_dir, "config", "user.email", "test@example.com")
        _git(self.repo_dir, "config", "user.name", "test")

        (self.repo_dir / "a.py").write_text("def f():\n    return 1\n", encoding="utf-8")
        _git(self.repo_dir, "add", "-A")
        _git(self.repo_dir, "commit", "-q", "-m", "first")
        self.old_sha = _git(self.repo_dir, "rev-parse", "HEAD")
        subprocess.run(
            [sys.executable, "-m", "cdp", "scan", "--repo", str(self.repo_dir),
             "--state-dir", str(self.state_dir)],
            cwd=REPO_ROOT, check=True, capture_output=True, text=True,
        )

        (self.repo_dir / "b.py").write_text("def g():\n    return 2\n", encoding="utf-8")
        _git(self.repo_dir, "add", "-A")
        _git(self.repo_dir, "commit", "-q", "-m", "second")
        self.new_sha = _git(self.repo_dir, "rev-parse", "HEAD")
        subprocess.run(
            [sys.executable, "-m", "cdp", "scan", "--repo", str(self.repo_dir),
             "--state-dir", str(self.state_dir)],
            cwd=REPO_ROOT, check=True, capture_output=True, text=True,
        )

    def _client(self):
        from fastapi.testclient import TestClient
        from web.api.app import app
        return TestClient(app)

    def test_lists_scanned_commits_oldest_first(self) -> None:
        from web.api.models import SnapshotsResponse

        resp = self._client().get("/api/snapshots", params={
            "repo": str(self.repo_dir), "state_dir": str(self.state_dir),
        })
        self.assertEqual(resp.status_code, 200, resp.text)
        payload = SnapshotsResponse(**resp.json())
        shas = [s.commit_sha for s in payload.snapshots]
        self.assertEqual(shas, [self.old_sha, self.new_sha])
        self.assertTrue(all(s.created_at for s in payload.snapshots))

    def test_never_scanned_state_dir_returns_empty_list(self) -> None:
        empty_dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, empty_dir, ignore_errors=True)
        resp = self._client().get("/api/snapshots", params={
            "repo": str(self.repo_dir), "state_dir": str(empty_dir),
        })
        self.assertEqual(resp.status_code, 200, resp.text)
        from web.api.models import SnapshotsResponse

        payload = SnapshotsResponse(**resp.json())
        self.assertEqual(payload.snapshots, [])


if __name__ == "__main__":
    unittest.main()
