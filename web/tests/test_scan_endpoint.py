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

    def _wait(self, job_id: str) -> dict:
        deadline = time.time() + 120
        while True:
            job = self.client.get("/api/job/%s" % job_id).json()
            if not job["running"]:
                return job
            self.assertLess(time.time(), deadline, "scan did not finish")
            time.sleep(0.5)

    def test_served_store_is_409_and_not_spawned(self) -> None:
        with mock.patch.dict(os.environ, {"CDP_STORE": str(self.repo / ".cdp")}):
            with mock.patch("web.api.app.jobs_mod.spawn_or_join") as spawn:
                resp = self.client.post("/api/scan", params={"repo": str(self.repo)}, headers=self.headers)
        self.assertEqual(resp.status_code, 409, resp.text)
        spawn.assert_not_called()

    def test_non_git_rescan_registers_once(self) -> None:
        shutil.rmtree(self.repo / ".git")
        for _ in range(2):
            resp = self.client.post("/api/scan", params={"repo": str(self.repo)}, headers=self.headers)
            self.assertEqual(resp.status_code, 200, resp.text)
            self._wait(resp.json()["job_id"])
        from web.api.app import _all_registry_entries

        target = (self.repo / ".cdp").resolve()
        hits = [v for v in _all_registry_entries().values() if Path(v).resolve() == target]
        self.assertEqual(len(hits), 1, _all_registry_entries())

    def test_non_git_registered_id_matches_snapshot_repo_id(self) -> None:
        shutil.rmtree(self.repo / ".git")
        resp = self.client.post("/api/scan", params={"repo": str(self.repo)}, headers=self.headers)
        self.assertEqual(resp.status_code, 200, resp.text)
        job = self._wait(resp.json()["job_id"])
        self.assertEqual(job["returncode"], 0, job["log_tail"])
        from web.api.app import _all_registry_entries
        from web.api.store_reader import ReadOnlyConnection

        conn = ReadOnlyConnection(self.repo / ".cdp" / "index.db")
        try:
            snapshot_repo_id = conn.snapshot_repo_id(conn.latest_pinned_snapshot())
        finally:
            conn.close()
        target = (self.repo / ".cdp").resolve()
        ids = [k for k, v in _all_registry_entries().items() if Path(v).resolve() == target]
        self.assertEqual(ids, [snapshot_repo_id])

    def test_home_is_400(self) -> None:
        with mock.patch.object(Path, "home", return_value=self.repo):
            with mock.patch("web.api.app.jobs_mod.spawn_or_join") as spawn:
                resp = self.client.post("/api/scan", params={"repo": str(self.repo)}, headers=self.headers)
        self.assertEqual(resp.status_code, 400, resp.text)
        spawn.assert_not_called()

    def test_root_is_400(self) -> None:
        resp = self.client.post("/api/scan", params={"repo": "/"}, headers=self.headers)
        self.assertEqual(resp.status_code, 400, resp.text)


if __name__ == "__main__":
    unittest.main()
