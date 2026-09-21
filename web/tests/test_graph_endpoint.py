"""`GET /api/graph?level=&scope=` against a real scanned repo -- same
convention as `test_status_contract.py`/`test_query_store.py`: real `cdp scan`
in `setUp`, no hand-built fixtures. Node/edge counts and divergence tagging
are asserted against the artifacts read directly out of the scanned state
dir, not against hand-picked expected values."""

from __future__ import annotations

import json
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
MINIREPO = REPO_ROOT / "tests" / "fixtures" / "minirepo"


class GraphEndpointTest(unittest.TestCase):
    def setUp(self) -> None:
        self.state_dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.state_dir, ignore_errors=True)
        subprocess.run(
            [sys.executable, "-m", "cdp", "scan", "--repo", str(MINIREPO),
             "--state-dir", str(self.state_dir)],
            cwd=REPO_ROOT, check=True, capture_output=True, text=True,
        )

    def _read_artifact(self, name: str) -> dict:
        conn = sqlite3.connect(str(self.state_dir / "index.db"))
        try:
            snapshot_id = conn.execute(
                "SELECT s.id FROM snapshot_meta s "
                "JOIN snapshot_artifact a ON a.snapshot_id = s.id AND a.name = 'manifest' "
                "ORDER BY COALESCE(s.touch_seq, s.id) DESC LIMIT 1"
            ).fetchone()[0]
            row = conn.execute(
                "SELECT payload FROM snapshot_artifact WHERE snapshot_id=? AND name=?",
                (snapshot_id, name),
            ).fetchone()
            return json.loads(row[0])
        finally:
            conn.close()

    def _client(self):
        from fastapi.testclient import TestClient
        from web.api.app import app
        return TestClient(app)

    # ---------------------------------------------------------------- L3

    def test_l3_node_count_matches_graph_artifact(self) -> None:
        from web.api.models import GraphResponse

        graph = self._read_artifact("graph")
        client = self._client()
        resp = client.get("/api/graph", params={
            "level": "L3", "repo": str(MINIREPO), "state_dir": str(self.state_dir),
        })
        self.assertEqual(resp.status_code, 200)
        payload = GraphResponse(**resp.json())

        self.assertEqual(len(payload.nodes), len(graph["modules"]))
        self.assertEqual({n.id for n in payload.nodes}, set(graph["modules"]))
        # levels passed through as-is, per WEB_RESEARCH.md sec 3
        self.assertEqual(payload.levels, graph["levels"])
        self.assertEqual(payload.cycles, graph["cycles"])
        self.assertEqual(payload.divergence, graph["divergence"])

    def test_l3_edges_are_tagged_declared_observed_both(self) -> None:
        from web.api.models import GraphResponse

        graph = self._read_artifact("graph")
        declared_pairs = {(e["from"], e["to"]) for e in graph["declared"]}
        observed_pairs = {(e["from"], e["to"]) for e in graph["observed"]}

        client = self._client()
        resp = client.get("/api/graph", params={
            "level": "L3", "repo": str(MINIREPO), "state_dir": str(self.state_dir),
        })
        payload = GraphResponse(**resp.json())

        by_pair = {(e.source, e.target): e.kind for e in payload.edges}
        self.assertEqual(set(by_pair), declared_pairs | observed_pairs)

        for pair, kind in by_pair.items():
            in_declared = pair in declared_pairs
            in_observed = pair in observed_pairs
            if in_declared and in_observed:
                self.assertEqual(kind, "both")
            elif in_declared:
                self.assertEqual(kind, "declared")
            else:
                self.assertEqual(kind, "observed")

        # The minirepo fixture has no divergence (declared == observed), so
        # assert the "both" case is at least reachable rather than skipped.
        if declared_pairs & observed_pairs:
            self.assertIn("both", by_pair.values())

    # ---------------------------------------------------------------- L2

    def test_l2_scope_count_matches_partition_artifact(self) -> None:
        from web.api.models import GraphResponse

        partition = self._read_artifact("partition")
        client = self._client()
        resp = client.get("/api/graph", params={
            "level": "L2", "repo": str(MINIREPO), "state_dir": str(self.state_dir),
        })
        self.assertEqual(resp.status_code, 200)
        payload = GraphResponse(**resp.json())

        self.assertEqual(len(payload.nodes), len(partition["scopes"]))
        self.assertEqual(
            {n.id for n in payload.nodes},
            {s["node"] for s in partition["scopes"]},
        )

    def test_l2_scope_filter_returns_neighborhood_only(self) -> None:
        from web.api.models import GraphResponse

        partition = self._read_artifact("partition")
        scopes = partition["scopes"]
        target = scopes[0]["node"]

        client = self._client()
        resp = client.get("/api/graph", params={
            "level": "L2", "scope": target,
            "repo": str(MINIREPO), "state_dir": str(self.state_dir),
        })
        self.assertEqual(resp.status_code, 200)
        payload = GraphResponse(**resp.json())

        self.assertEqual(payload.scope, target)
        node_ids = {n.id for n in payload.nodes}
        self.assertIn(target, node_ids)
        self.assertLessEqual(len(node_ids), len(scopes))
        for edge in payload.edges:
            self.assertTrue(edge.source == target or edge.target == target)

    # ---------------------------------------------------------------- L0

    def test_l0_node_count_matches_xref_symbols(self) -> None:
        from web.api.models import GraphResponse

        xref = self._read_artifact("xref")
        client = self._client()
        resp = client.get("/api/graph", params={
            "level": "L0", "repo": str(MINIREPO), "state_dir": str(self.state_dir),
        })
        self.assertEqual(resp.status_code, 200)
        payload = GraphResponse(**resp.json())
        self.assertEqual({n.id for n in payload.nodes}, set(xref["symbols"]))

    def test_l0_scope_filter_narrows_to_symbols_in_module(self) -> None:
        from web.api.models import GraphResponse

        xref = self._read_artifact("xref")
        symbols = xref["symbols"]
        some_fqn = next(iter(symbols))
        module = symbols[some_fqn]["modules"][0]

        client = self._client()
        resp = client.get("/api/graph", params={
            "level": "L0", "scope": module,
            "repo": str(MINIREPO), "state_dir": str(self.state_dir),
        })
        self.assertEqual(resp.status_code, 200)
        payload = GraphResponse(**resp.json())
        for node in payload.nodes:
            self.assertIn(module, symbols[node.id]["modules"])
        self.assertLessEqual(len(payload.nodes), len(symbols))

    # ---------------------------------------------------------------- L1

    def test_l1_node_count_matches_partition_files(self) -> None:
        from web.api.models import GraphResponse

        partition = self._read_artifact("partition")
        all_files = {f for s in partition["scopes"] for f in s["files"]}

        client = self._client()
        resp = client.get("/api/graph", params={
            "level": "L1", "repo": str(MINIREPO), "state_dir": str(self.state_dir),
        })
        self.assertEqual(resp.status_code, 200)
        payload = GraphResponse(**resp.json())
        self.assertEqual({n.id for n in payload.nodes}, all_files)

    def test_l1_scope_filter_returns_neighborhood_only(self) -> None:
        from web.api.models import GraphResponse

        partition = self._read_artifact("partition")
        target_scope = partition["scopes"][0]
        target_files = set(target_scope["files"])

        client = self._client()
        resp = client.get("/api/graph", params={
            "level": "L1", "scope": target_scope["node"],
            "repo": str(MINIREPO), "state_dir": str(self.state_dir),
        })
        self.assertEqual(resp.status_code, 200)
        payload = GraphResponse(**resp.json())
        node_ids = {n.id for n in payload.nodes}
        self.assertTrue(target_files <= node_ids)
        for edge in payload.edges:
            self.assertTrue(edge.source in target_files or edge.target in target_files)

    # ---------------------------------------------------------------- errors

    def test_unknown_level_returns_501(self) -> None:
        client = self._client()
        for level in ("L4", "bogus"):
            resp = client.get("/api/graph", params={
                "level": level, "repo": str(MINIREPO), "state_dir": str(self.state_dir),
            })
            self.assertEqual(resp.status_code, 501, level)
            self.assertIn("L2", resp.json()["detail"])
            self.assertIn("L3", resp.json()["detail"])

    def test_never_scanned_state_dir_404s(self) -> None:
        empty_dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, empty_dir, ignore_errors=True)
        client = self._client()
        resp = client.get("/api/graph", params={
            "level": "L3", "repo": str(MINIREPO), "state_dir": str(empty_dir),
        })
        self.assertEqual(resp.status_code, 404)


if __name__ == "__main__":
    unittest.main()
