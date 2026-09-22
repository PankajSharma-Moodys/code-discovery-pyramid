"""`GET /api/sources` -- there is no `kind=sources` in `cdp.query.QUERIES`
(only `trace`/`paths` consume `dataflow.sources[]`, internally), so this
endpoint reads the artifact directly, same posture as `get_link`/`get_doctor`
(`web/api/app.py:get_sources`)."""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
MINIREPO = REPO_ROOT / "tests" / "fixtures" / "minirepo"


class SourcesEndpointTest(unittest.TestCase):
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

    def test_lists_dataflow_sources_with_anchors(self) -> None:
        from web.api.models import SourcesResponse

        resp = self._client().get("/api/sources", params={
            "repo": str(MINIREPO), "state_dir": str(self.state_dir),
        })
        self.assertEqual(resp.status_code, 200)
        payload = SourcesResponse(**resp.json())
        self.assertEqual(payload.count, len(payload.sources))
        self.assertGreater(payload.count, 0)
        for entry in payload.sources:
            self.assertTrue(entry.node)
            self.assertTrue(entry.channel)
            if entry.anchor is not None:
                self.assertTrue(entry.anchor.file)
                self.assertGreaterEqual(entry.anchor.line, 1)

    def test_never_scanned_state_dir_404s(self) -> None:
        empty_dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, empty_dir, ignore_errors=True)
        resp = self._client().get("/api/sources", params={
            "repo": str(MINIREPO), "state_dir": str(empty_dir),
        })
        self.assertEqual(resp.status_code, 404)


if __name__ == "__main__":
    unittest.main()
