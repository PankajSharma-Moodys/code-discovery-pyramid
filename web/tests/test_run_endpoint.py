"""`POST /api/run` -- token+Origin guarded (`web/api/auth.py`), spawns `cdp run`
via `web/api/jobs.py`'s single-flight registry. Auth/target-validation/success
shape is covered here; the single-flight join itself is covered by
`test_jobs_registry.py` against a mocked slow subprocess, since a real `cdp
run` against the tiny minirepo fixture finishes too fast to race reliably."""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
MINIREPO = REPO_ROOT / "tests" / "fixtures" / "minirepo"


class RunEndpointTest(unittest.TestCase):
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

    def _terminate_and_cleanup(self, job_id: str) -> None:
        """`cdp run --wave-all` blocks on real model config with no
        `--runner-cmd` given, so this test only needs to confirm the process
        spawned -- it must be killed, not waited on, or the test would hang
        on a live subprocess that's never going to finish on its own."""
        from web.api import jobs as jobs_mod
        job = jobs_mod.get_job(job_id)
        if job is not None:
            job.process.terminate()
            self.addCleanup(job.process.wait, timeout=10)

    def test_missing_token_is_rejected(self) -> None:
        resp = self._client().post("/api/run", params={
            "repo": str(MINIREPO), "state_dir": str(self.state_dir), "target": "wave-all",
        })
        self.assertEqual(resp.status_code, 403)

    def test_wrong_token_is_rejected(self) -> None:
        resp = self._client().post(
            "/api/run",
            params={"repo": str(MINIREPO), "state_dir": str(self.state_dir), "target": "wave-all"},
            headers={"X-CDP-Web-Token": "not-the-token"},
        )
        self.assertEqual(resp.status_code, 403)

    def test_mismatched_origin_is_rejected(self) -> None:
        resp = self._client().post(
            "/api/run",
            params={"repo": str(MINIREPO), "state_dir": str(self.state_dir), "target": "wave-all"},
            headers={"X-CDP-Web-Token": self._token(), "Origin": "http://evil.example"},
        )
        self.assertEqual(resp.status_code, 403)

    def test_unknown_target_400s(self) -> None:
        resp = self._client().post(
            "/api/run",
            params={"repo": str(MINIREPO), "state_dir": str(self.state_dir), "target": "bogus"},
            headers={"X-CDP-Web-Token": self._token()},
        )
        self.assertEqual(resp.status_code, 400)

    def test_valid_request_spawns_job(self) -> None:
        from web.api.models import JobResponse

        resp = self._client().post(
            "/api/run",
            params={"repo": str(MINIREPO), "state_dir": str(self.state_dir), "target": "wave-all"},
            headers={"X-CDP-Web-Token": self._token()},
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        payload = JobResponse(**resp.json())
        self.assertEqual(payload.status, "started")
        self.assertEqual(payload.kind, "run")
        self.assertGreater(payload.pid, 0)
        self._terminate_and_cleanup(payload.job_id)


if __name__ == "__main__":
    unittest.main()
