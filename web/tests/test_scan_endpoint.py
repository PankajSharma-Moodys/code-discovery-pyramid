"""`POST /api/scan`: scans a user-chosen folder into `<folder>/.cdp`.

Safety property under test: the scan must never be routed through the
server's `CDP_STORE` (the live dev server points that at another repo's store),
so the test sets `CDP_STORE` to an empty dir and asserts it stays empty. The
registry is patched to a temp file so the real `~/.cdp/config.toml` is untouched."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[2]
MINIREPO = REPO_ROOT / "tests" / "fixtures" / "minirepo"


class ScanEndpointTest(unittest.TestCase):
    def setUp(self) -> None:
        tmp = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        self.repo = tmp / "minirepo"
        shutil.copytree(MINIREPO, self.repo, ignore=shutil.ignore_patterns(".gradle", "bin", ".cdp"))
        git = ["git", "-c", "user.email=t@t", "-c", "user.name=t"]
        subprocess.run(git + ["init", "-q"], cwd=self.repo, check=True)
        subprocess.run(git + ["add", "-A"], cwd=self.repo, check=True)
        subprocess.run(git + ["commit", "-q", "-m", "init"], cwd=self.repo, check=True)

        self.store = tmp / "server-store"
        self.store.mkdir()
        env = mock.patch.dict(os.environ, {"CDP_STORE": str(self.store)})
        env.start()
        self.addCleanup(env.stop)

        from cdp.store import registry as registry_mod

        reg = mock.patch.object(registry_mod, "REGISTRY_PATH", tmp / "home" / "config.toml")
        reg.start()
        self.addCleanup(reg.stop)

        from fastapi.testclient import TestClient
        from web.api import auth as auth_mod
        from web.api.app import app

        self.client = TestClient(app)
        self.headers = {"X-CDP-Web-Token": auth_mod.WEB_TOKEN}

    def test_scan_writes_into_folder_and_registers(self) -> None:
        resp = self.client.post("/api/scan", params={"repo": str(self.repo)}, headers=self.headers)
        self.assertEqual(resp.status_code, 200, resp.text)
        job_id = resp.json()["job_id"]

        deadline = time.time() + 120
        while True:
            job = self.client.get("/api/job/%s" % job_id).json()
            if not job["running"]:
                break
            self.assertLess(time.time(), deadline, "scan did not finish")
            self.assertIsNone(job["log_tail"])
            time.sleep(0.5)

        self.assertEqual(Path(job["state_dir"]), self.repo / ".cdp")
        self.assertEqual(job["returncode"], 0, job["log_tail"])
        self.assertTrue((self.repo / ".cdp" / "index.db").is_file())
        self.assertEqual(list(self.store.iterdir()), [])
        self.assertTrue(job["log_tail"])

        rows = [
            r for r in self.client.get("/api/repos").json()["repos"]
            if Path(r["state_dir"]) == (self.repo / ".cdp").resolve()
        ]
        self.assertEqual(len(rows), 1)
        self.assertIsNone(rows[0]["error"])

    def test_missing_token_is_403(self) -> None:
        resp = self.client.post("/api/scan", params={"repo": str(self.repo)})
        self.assertEqual(resp.status_code, 403)

    def test_non_directory_is_404(self) -> None:
        resp = self.client.post(
            "/api/scan", params={"repo": str(self.repo / "nope")}, headers=self.headers
        )
        self.assertEqual(resp.status_code, 404)


if __name__ == "__main__":
    unittest.main()
