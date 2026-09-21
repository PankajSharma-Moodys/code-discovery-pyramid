"""`GET /api/node/:id` against a real `cdp scan` of `tests/fixtures/minirepo`
-- same "verify against ground truth" posture as `test_nodeid.py` and
`test_status_contract.py`: no hand-built fixtures, ids are picked from the
actual scanned artifacts."""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
MINIREPO = REPO_ROOT / "tests" / "fixtures" / "minirepo"


class NodeEndpointTest(unittest.TestCase):
    def setUp(self) -> None:
        self.state_dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.state_dir, ignore_errors=True)
        subprocess.run(
            [sys.executable, "-m", "cdp", "scan", "--repo", str(MINIREPO),
             "--state-dir", str(self.state_dir)],
            cwd=REPO_ROOT, check=True, capture_output=True, text=True,
        )

        from web.api.store_reader import ReadOnlyConnection

        conn = ReadOnlyConnection(self.state_dir / "index.db")
        snapshot_id = conn.latest_pinned_snapshot()
        self.xref = conn.read_artifact(snapshot_id, "xref")
        self.partition = conn.read_artifact(snapshot_id, "partition")
        self.dataflow = conn.read_artifact(snapshot_id, "dataflow")
        conn.close()

        from fastapi.testclient import TestClient

        from web.api.app import app

        self.client = TestClient(app)

    def _get(self, node_id: str):
        return self.client.get(
            "/api/node/%s" % node_id,
            params={"repo": str(MINIREPO), "state_dir": str(self.state_dir)},
        )

    def test_malformed_id_is_400(self) -> None:
        resp = self._get("no-namespace-here")
        self.assertEqual(resp.status_code, 400)

    def test_wellformed_but_nonexistent_id_is_404(self) -> None:
        resp = self._get("sym:definitely_not_real_xyz")
        self.assertEqual(resp.status_code, 404)

    def test_real_symbol_id_resolves(self) -> None:
        from web.api import nodeid

        index = nodeid.SubjectIndex(self.xref, self.partition, self.dataflow)
        # Pick a symbol that a real claim's subject actually classifies to,
        # so the assertions below have something concrete to check.
        fqn = next(
            fqn for fqn in self.xref["symbols"]
            if index.classify(fqn) == nodeid.sym_id(fqn) and "." in fqn
        )
        node_id = nodeid.sym_id(fqn)
        resp = self._get(node_id)
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["node_id"], node_id)
        self.assertEqual(body["namespace"], "sym")
        self.assertIn("unknowns_count", body)
        self.assertEqual(body["unknowns_count"], 0)
        # At least one of claims/edges must be non-empty for a real,
        # referenced symbol -- an entirely empty body would mean the lookup
        # is broken, not that the node is unreferenced.
        self.assertTrue(body["claims"] or body["edges_in"] or body["edges_out"])

    def test_real_scope_id_resolves(self) -> None:
        from web.api import nodeid

        scope = self.partition["scopes"][0]
        node_id = nodeid.scope_id(scope["node"])
        resp = self._get(node_id)
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["node_id"], node_id)
        self.assertEqual(body["namespace"], "scope")
        self.assertIsNotNone(body["scope"])
        self.assertEqual(body["scope"]["node"], scope["node"])
        self.assertEqual(body["scope"]["file_count"], scope["file_count"])
        self.assertIn("unknowns_count", body)

    def test_real_route_id_resolves(self) -> None:
        from web.api import nodeid

        routes = self.xref.get("routes", [])
        self.assertTrue(routes, "fixture scan produced no routes")
        route = routes[0]["route"]
        node_id = nodeid.route_id(route)
        resp = self._get(node_id)
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["node_id"], node_id)
        self.assertEqual(body["namespace"], "route")
        self.assertIn("unknowns_count", body)
        self.assertEqual(body["unknowns_count"], 0)

    def test_real_file_id_resolves_to_owning_scope(self) -> None:
        from web.api import nodeid

        scope = next(s for s in self.partition["scopes"] if s["files"])
        path = scope["files"][0]
        node_id = nodeid.file_id(path)
        resp = self._get(node_id)
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["namespace"], "file")
        self.assertIsNotNone(body["scope"])
        self.assertEqual(body["scope"]["node"], scope["node"])


if __name__ == "__main__":
    unittest.main()
