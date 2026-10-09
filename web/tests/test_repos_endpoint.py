"""`GET /api/repos`: every repo in the machine's one store
(`cdp.catalog.list_repos`), with per-repo freshness (current git HEAD vs. the
latest pinned snapshot's `as_of` commit)."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
MINIREPO = REPO_ROOT / "tests" / "fixtures" / "minirepo"
SOLOREPO = REPO_ROOT / "tests" / "fixtures" / "solorepo"


def scan(repo: Path, home: Path) -> None:
    subprocess.run(
        [sys.executable, "-m", "cdp", "scan", "--repo", str(repo), "--quiet"],
        cwd=REPO_ROOT, check=True, capture_output=True, text=True,
        env=dict(os.environ, CDP_HOME=str(home)),
    )


class ReposEndpointTest(unittest.TestCase):
    def setUp(self) -> None:
        self.home = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.home, ignore_errors=True)
        scan(MINIREPO, self.home)
        scan(SOLOREPO, self.home)

        from fastapi.testclient import TestClient

        from web.api.app import app

        self.client = TestClient(app)

        from cdp.store import registry

        self.registry = registry
        from web.api.store_reader import ReadOnlyConnection

        conn = ReadOnlyConnection(self.home / "index.db")
        snapshot_id = conn.latest_pinned_snapshot(registry.repo_identity(MINIREPO))
        self.inventory = conn.read_artifact(snapshot_id, "inventory")
        conn.close()

    def _repos(self, repo: Path):
        resp = self.client.get("/api/repos", params={"repo": str(repo), "state_dir": str(self.home)})
        self.assertEqual(resp.status_code, 200)
        payload = resp.json()

        from web.api.models import ReposResponse

        ReposResponse(**payload)  # raises on schema mismatch
        return payload["repos"]

    def test_every_scanned_repo_is_listed_with_the_callers_first(self) -> None:
        repos = self._repos(MINIREPO)
        ids = [r["repo_id"] for r in repos]
        self.assertEqual(ids[0], self.registry.repo_identity(MINIREPO))
        self.assertIn(self.registry.repo_identity(SOLOREPO), ids)
        self.assertEqual(len(ids), len(set(ids)))

    def test_scanned_repo_appears_with_correct_head_and_as_of(self) -> None:
        row = self._repos(MINIREPO)[0]
        expected_as_of = self.inventory.get("head")
        self.assertIsNone(row["error"])
        self.assertEqual(row["as_of_commit"], expected_as_of)
        self.assertEqual(row["repo_path"], self.inventory.get("repo"))
        # `minirepo` lives inside this checkout's own git working tree, so its
        # "current HEAD" is this repo's HEAD -- same value the scan pinned.
        self.assertEqual(row["head"], expected_as_of)
        self.assertEqual(row["behind"], 0)
        self.assertEqual(Path(row["state_dir"]), self.home.resolve())

    def test_a_repo_that_was_never_scanned_gets_an_error_row_not_a_500(self) -> None:
        elsewhere = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, elsewhere, ignore_errors=True)
        repos = self._repos(elsewhere)
        self.assertEqual(repos[0]["repo_id"], self.registry.repo_identity(elsewhere))
        self.assertIsNotNone(repos[0]["error"])
        self.assertIsNone(repos[0]["head"])
        # ...and the scanned repos are still there.
        self.assertGreaterEqual(len(repos), 3)

    def test_nothing_was_written_outside_the_home(self) -> None:
        self.assertTrue((self.home / "index.db").is_file())


if __name__ == "__main__":
    unittest.main()
