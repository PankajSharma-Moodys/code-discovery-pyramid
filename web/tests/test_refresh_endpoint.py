"""`POST /api/refresh` -- same auth guard as `/api/run` (`web/api/auth.py`),
shells out to `cdp refresh --mode` via `web/api/jobs.py`."""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
MINIREPO = REPO_ROOT / "tests" / "fixtures" / "minirepo"


class RefreshEndpointTest(unittest.TestCase):
    def setUp(self) -> None:
        self.state_dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.state_dir, ignore_errors=True)
        subprocess.run(
            [sys.executable, "-m", "cdp", "scan", "--repo", str(MINIREPO),
             "--state-dir", str(self.state_dir)],
            cwd=REPO_ROOT, check=True, capture_output=True, text=True,
        )

    def _client(self):
        from fastapi.testclient import TestClient
        from web.api.app import app
        return TestClient(app)

    def _token(self) -> str:
        from web.api import auth as auth_mod
        return auth_mod.WEB_TOKEN

    def test_missing_token_is_rejected(self) -> None:
        resp = self._client().post("/api/refresh", params={
            "repo": str(MINIREPO), "state_dir": str(self.state_dir),
        })
        self.assertEqual(resp.status_code, 403)

    def test_valid_request_spawns_job(self) -> None:
        from web.api import jobs as jobs_mod
        from web.api.models import JobResponse

        resp = self._client().post(
            "/api/refresh",
            params={"repo": str(MINIREPO), "state_dir": str(self.state_dir), "mode": "strict"},
            headers={"X-CDP-Web-Token": self._token()},
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        payload = JobResponse(**resp.json())
        self.assertEqual(payload.status, "started")
        self.assertEqual(payload.kind, "refresh")
        self.assertGreater(payload.pid, 0)

        job = jobs_mod.get_job(payload.job_id)
        self.assertIsNotNone(job)
        self.addCleanup(job.process.wait, timeout=30)


if __name__ == "__main__":
    unittest.main()
