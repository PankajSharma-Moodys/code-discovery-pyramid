"""`GET /api/links` -- all persisted `link_edge` rows, unfiltered by service
(unlike `/api/link?service=`). `link_edge` rows are written directly via
`SqliteStore.write_link_edges` (mirrors what `cdp link scan --db` would
persist), same as `test_link_endpoint.py`."""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
MINIREPO = REPO_ROOT / "tests" / "fixtures" / "minirepo"


class LinksEndpointTest(unittest.TestCase):
    def setUp(self) -> None:
        self.state_dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.state_dir, ignore_errors=True)
        subprocess.run(
            [sys.executable, "-m", "cdp", "scan", "--repo", str(MINIREPO),
             "--state-dir", str(self.state_dir)],
            cwd=REPO_ROOT, check=True, capture_output=True, text=True,
        )

        from cdp.store.sqlite_backend import SqliteStore

        store = SqliteStore(self.state_dir / "index.db")
        try:
            report = {
                "links": [{
                    "protocol": "http_out", "match_kind": "exact",
                    "caller": {"repo": "service-a", "head": "aaa", "module": "m1",
                               "node": "n1", "target": "n2",
                               "anchor": {"file": "a.py", "line": 1}},
                    "callee": {"repo": "service-b", "head": "bbb", "module": "m2",
                               "node": "n2", "target": "n1",
                               "anchor": {"file": "b.py", "line": 2}},
                }],
                "unmatched": [{
                    "protocol": "event_publish",
                    "outbound": {"repo": "service-a", "head": "aaa", "module": "m1",
                                 "node": "n3", "target": "topic",
                                 "anchor": {"file": "a.py", "line": 5}},
                }],
            }
            store.write_link_edges(report)
        finally:
            store.close()

    def _client(self):
        from fastapi.testclient import TestClient
        from web.api.app import app
        return TestClient(app)

    def test_lists_all_links_and_unmatched_unfiltered(self) -> None:
        from web.api.models import LinksResponse

        resp = self._client().get("/api/links", params={
            "repo": str(MINIREPO), "state_dir": str(self.state_dir),
        })
        self.assertEqual(resp.status_code, 200, resp.text)
        payload = LinksResponse(**resp.json())
        self.assertEqual(len(payload.links), 1)
        self.assertEqual(payload.links[0]["caller"]["repo"], "service-a")
        self.assertEqual(payload.links[0]["callee"]["repo"], "service-b")
        self.assertEqual(len(payload.unmatched), 1)
        self.assertEqual(payload.unmatched[0]["outbound"]["repo"], "service-a")

    def test_never_scanned_state_dir_404s(self) -> None:
        empty_dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, empty_dir, ignore_errors=True)
        resp = self._client().get("/api/links", params={
            "repo": str(MINIREPO), "state_dir": str(empty_dir),
        })
        self.assertEqual(resp.status_code, 404)


if __name__ == "__main__":
    unittest.main()
