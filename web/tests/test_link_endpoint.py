"""`GET /api/link?service=` -- thin wrapper over the pure `link.query_service`
(`cdp/link.py:217`). `link_edge` rows are written directly via
`SqliteStore.write_link_edges` (mirrors what `cdp link scan --db` would
persist) rather than driving a real cross-repo `link scan`, since the report
shape is what this endpoint cares about, not `link.scan_links`'s own matching
logic (covered by `tests/test_link.py`)."""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
MINIREPO = REPO_ROOT / "tests" / "fixtures" / "minirepo"


class LinkEndpointTest(unittest.TestCase):
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

    def test_service_a_sees_its_link_and_its_own_unmatched_call(self) -> None:
        from web.api.models import LinkQueryResponse

        resp = self._client().get("/api/link", params={
            "service": "service-a", "repo": str(MINIREPO), "state_dir": str(self.state_dir),
        })
        self.assertEqual(resp.status_code, 200)
        payload = LinkQueryResponse(**resp.json())
        self.assertEqual(payload.service, "service-a")
        self.assertEqual(len(payload.links), 1)
        self.assertEqual(payload.links[0]["caller"]["repo"], "service-a")
        self.assertEqual(len(payload.unmatched), 1)
        self.assertEqual(payload.unmatched[0]["outbound"]["repo"], "service-a")

    def test_unrelated_service_sees_nothing(self) -> None:
        from web.api.models import LinkQueryResponse

        resp = self._client().get("/api/link", params={
            "service": "service-z", "repo": str(MINIREPO), "state_dir": str(self.state_dir),
        })
        self.assertEqual(resp.status_code, 200)
        payload = LinkQueryResponse(**resp.json())
        self.assertEqual(payload.links, [])
        self.assertEqual(payload.unmatched, [])

    def test_never_scanned_state_dir_404s(self) -> None:
        empty_dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, empty_dir, ignore_errors=True)
        resp = self._client().get("/api/link", params={
            "service": "service-a", "repo": str(MINIREPO), "state_dir": str(empty_dir),
        })
        self.assertEqual(resp.status_code, 404)


if __name__ == "__main__":
    unittest.main()
