"""`GET /api/doctor` -- reads `<state>/doctor/*.json` straight off disk, no
`index.db` involved (`cli.py:1858,1885` is the write side this mirrors). The
doctor pipeline itself (running a real model runner) is exercised by
`tests/test_doctor.py`; this test only needs report files on disk, so they're
written directly rather than driving a real `cdp doctor` subprocess."""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from cdp.util import write_json

REPO_ROOT = Path(__file__).resolve().parents[2]
MINIREPO = REPO_ROOT / "tests" / "fixtures" / "minirepo"


class DoctorEndpointTest(unittest.TestCase):
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

    def test_no_doctor_dir_404s(self) -> None:
        resp = self._client().get("/api/doctor", params={
            "repo": str(MINIREPO), "state_dir": str(self.state_dir),
        })
        self.assertEqual(resp.status_code, 404)

    def test_single_model_report_returned_with_no_table(self) -> None:
        doctor_dir = self.state_dir / "doctor"
        doctor_dir.mkdir(parents=True, exist_ok=True)
        agg = {
            "model": "model-a", "scopes": 2, "schema_validity_rate": 1.0,
            "yield_collapse_rate": 0.0, "entailment_counts": {}, "recall": None,
            "false_unknown_rate": None, "golden_total": 0,
        }
        write_json(doctor_dir / "model-a.json", agg)

        from web.api.models import DoctorResponse

        resp = self._client().get("/api/doctor", params={
            "repo": str(MINIREPO), "state_dir": str(self.state_dir),
        })
        self.assertEqual(resp.status_code, 200)
        payload = DoctorResponse(**resp.json())
        self.assertEqual(set(payload.models), {"model-a"})
        self.assertIsNone(payload.table)

    def test_multi_model_report_includes_compatibility_table(self) -> None:
        doctor_dir = self.state_dir / "doctor"
        doctor_dir.mkdir(parents=True, exist_ok=True)
        for name in ("model-a", "model-b"):
            write_json(doctor_dir / ("%s.json" % name), {
                "model": name, "scopes": 1, "schema_validity_rate": 1.0,
                "yield_collapse_rate": 0.0, "entailment_counts": {}, "recall": None,
                "false_unknown_rate": None, "golden_total": 0,
            })

        from web.api.models import DoctorResponse

        resp = self._client().get("/api/doctor", params={
            "repo": str(MINIREPO), "state_dir": str(self.state_dir),
        })
        self.assertEqual(resp.status_code, 200)
        payload = DoctorResponse(**resp.json())
        self.assertEqual(set(payload.models), {"model-a", "model-b"})
        self.assertIsNotNone(payload.table)
        self.assertIn("model-a", payload.table)
        self.assertIn("model-b", payload.table)


if __name__ == "__main__":
    unittest.main()
