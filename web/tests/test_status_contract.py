"""The Phase-0 acceptance test from `PLAN.md`: `cdp status --json` and
`GET /api/status` must validate against the same Pydantic model, against a
real scanned repo -- divergence between the two surfaces is a trust bug,
so it fails CI here rather than surfacing in a demo."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
MINIREPO = REPO_ROOT / "tests" / "fixtures" / "minirepo"


class StatusContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.state_dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.state_dir, ignore_errors=True)
        subprocess.run(
            [sys.executable, "-m", "cdp", "scan", "--repo", str(MINIREPO),
             "--state-dir", str(self.state_dir)],
            cwd=REPO_ROOT, check=True, capture_output=True, text=True,
        )

    def test_cli_json_validates_against_model(self) -> None:
        from web.api.models import StatusResponse

        proc = subprocess.run(
            [sys.executable, "-m", "cdp", "status", "--repo", str(MINIREPO),
             "--state-dir", str(self.state_dir), "--json"],
            cwd=REPO_ROOT, check=True, capture_output=True, text=True,
        )
        payload = json.loads(proc.stdout)
        StatusResponse(**payload)  # raises on schema mismatch

    def test_api_status_validates_against_model_and_matches_cli(self) -> None:
        from fastapi.testclient import TestClient

        from web.api.app import app
        from web.api.models import StatusResponse

        proc = subprocess.run(
            [sys.executable, "-m", "cdp", "status", "--repo", str(MINIREPO),
             "--state-dir", str(self.state_dir), "--json"],
            cwd=REPO_ROOT, check=True, capture_output=True, text=True,
        )
        cli_payload = json.loads(proc.stdout)

        client = TestClient(app)
        resp = client.get("/api/status", params={
            "repo": str(MINIREPO), "state_dir": str(self.state_dir),
        })
        self.assertEqual(resp.status_code, 200)
        api_payload = resp.json()

        StatusResponse(**cli_payload)
        StatusResponse(**api_payload)
        self.assertEqual(
            StatusResponse(**cli_payload), StatusResponse(**api_payload),
        )

    def test_status_404s_when_never_scanned(self) -> None:
        from fastapi.testclient import TestClient

        from web.api.app import app

        empty_dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, empty_dir, ignore_errors=True)
        client = TestClient(app)
        resp = client.get("/api/status", params={
            "repo": str(MINIREPO), "state_dir": str(empty_dir),
        })
        self.assertEqual(resp.status_code, 404)


if __name__ == "__main__":
    unittest.main()
