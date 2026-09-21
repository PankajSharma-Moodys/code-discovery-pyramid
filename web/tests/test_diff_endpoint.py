"""`GET /api/diff?old=&new=` -- sha-mode only, delegating to the pure
`diffs_mod.diff_snapshots` (`cdp/diffs.py:30`) the same way `cdp diff
--old-sha/--new-sha` does. Needs two real commits of one repo, each scanned
into the same `--state-dir` so both land in the same `index.db`'s
`snapshot_meta` -- built from a throwaway git fixture, not this checkout's own
history."""

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


class DiffEndpointTest(unittest.TestCase):
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

    def test_diff_between_two_scanned_commits(self) -> None:
        from web.api.models import DiffResponse

        resp = self._client().get("/api/diff", params={
            "old": self.old_sha, "new": self.new_sha,
            "repo": str(self.repo_dir), "state_dir": str(self.state_dir),
        })
        self.assertEqual(resp.status_code, 200, resp.text)
        payload = DiffResponse(**resp.json())
        self.assertEqual(payload.old_sha, self.old_sha)
        self.assertEqual(payload.new_sha, self.new_sha)
        self.assertIn("modules", payload.diff)
        self.assertIn("added", payload.diff["modules"])

    def test_unknown_sha_400s_with_known_shas_listed(self) -> None:
        resp = self._client().get("/api/diff", params={
            "old": "deadbeef", "new": self.new_sha,
            "repo": str(self.repo_dir), "state_dir": str(self.state_dir),
        })
        self.assertEqual(resp.status_code, 400)
        self.assertIn(self.old_sha, resp.json()["detail"])


if __name__ == "__main__":
    unittest.main()
