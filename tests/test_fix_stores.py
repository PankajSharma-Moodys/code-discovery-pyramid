"""Read-only commands create nothing in a never-scanned state dir; `--as-of` rejects non-prefixes."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

RUN_PY = Path(__file__).resolve().parent.parent / "run.py"


def _git(repo: Path, *args: str) -> str:
    env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")
    return subprocess.run(["git", *args], cwd=repo, env=env, check=True, capture_output=True, text=True).stdout.strip()


class FixStoresTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        tmp = Path(self._tmp.name)
        self.repo, self.state = tmp / "repo", tmp / "state"
        self.repo.mkdir()
        _git(self.repo, "init", "-q")
        (self.repo / "a.py").write_text("x = 1\n")
        _git(self.repo, "add", ".")
        _git(self.repo, "commit", "-qm", "init")
        self.sha = _git(self.repo, "rev-parse", "HEAD")
        self.env = dict(os.environ, HOME=str(tmp / "home"), CDP_HOME=str(tmp / "home" / "cdp"),
                        CDP_TRAJECTORY_DB=str(tmp / "traj.db"))

    def cdp(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(RUN_PY), *args, "--repo", str(self.repo), "--state-dir", str(self.state)],
                              env=self.env, capture_output=True, text=True)

    def test_readers_do_not_create_the_store(self) -> None:
        self.state.mkdir()
        for cmd in (["query", "stats"], ["status"], ["fold"], ["verify"], ["docs"], ["rollback", "--undo"]):
            r = self.cdp(*cmd)
            self.assertIn("scan needed", r.stdout + r.stderr, cmd)
            left = sorted(p.name for p in self.state.iterdir() if p.name != "locks")  # locks/ belongs to lock.py
            self.assertEqual(left, [], cmd)

    def test_scan_still_creates_the_store(self) -> None:
        r = self.cdp("scan", "--quiet")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue((self.state / "index.db").is_file())

    def test_as_of_needs_a_real_prefix(self) -> None:
        self.assertEqual(self.cdp("scan", "--quiet").returncode, 0)
        for ok in (self.sha, self.sha[:8], self.sha[:12]):
            self.assertEqual(self.cdp("query", "stats", "--as-of", ok).returncode, 0, ok)
        for bad in (self.sha + "abc", self.sha[:12] + "abc", "601475302d04abc"):
            self.assertNotEqual(self.cdp("query", "stats", "--as-of", bad).returncode, 0, bad)


if __name__ == "__main__":
    unittest.main()
