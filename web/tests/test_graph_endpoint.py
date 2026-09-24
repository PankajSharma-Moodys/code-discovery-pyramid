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

    def _expected_file_of(self, dataflow: dict, xref: dict) -> dict:
        """Mirrors `app.py`'s `_dataflow_graph` file resolution exactly
        (`encoding.resolve_owner_file` over the same symbol table + edges),
        so these tests assert the corrected `WEB_REDESIGN_RESEARCH.md` §3.1
        contract (group by resolved file path) rather than the old,
        confirmed-wrong id-string grouping (`package_of` on a bare id)."""
        from web.api import encoding

        symbol_table = xref.get("symbols") or {}
        raw_ids = {end for e in dataflow["edges"] for end in (e["source"], e["target"])}
        edges = [{"source": e["source"], "target": e["target"], "kind": e.get("channel", "flow")}
                  for e in dataflow["edges"]]
        return {raw_id: encoding.resolve_owner_file(raw_id, symbol_table, edges) for raw_id in raw_ids}

    def test_l3_rolls_the_dataflow_graph_up_by_package(self) -> None:
        """L3 is the *rollup of the same typed graph L2 serves*
        (`ATLAS_REDESIGN.md` §2), not `graph.modules` any more -- pairing 7
        module nodes with 2 `declared`/`observed` edges is exactly the empty
        canvas that redesign was written about. `graph.levels`/`cycles`/
        `divergence` are still passed through untouched.

        Grouping itself is `WEB_REDESIGN_RESEARCH.md` §3.1's path-based
        container tree, not the old `package_of` id-string split -- confirmed
        wrong on a real C#/Java repo (`unified-store`), where bare class-name
        ids have no dots to split and every node became its own package."""
        from web.api import encoding
        from web.api.models import GraphResponse

        graph = self._read_artifact("graph")
        dataflow = self._read_artifact("dataflow")
        xref = self._read_artifact("xref")
        raw_ids = {end for e in dataflow["edges"] for end in (e["source"], e["target"])}
        file_of = self._expected_file_of(dataflow, xref)
        expected_groups = {encoding.container_group(raw_id, 1, file_of) for raw_id in raw_ids}

        client = self._client()
        resp = client.get("/api/graph", params={
            "level": "L3", "repo": str(MINIREPO), "state_dir": str(self.state_dir),
        })
        self.assertEqual(resp.status_code, 200)
        payload = GraphResponse(**resp.json())

        self.assertEqual({n.id for n in payload.nodes}, expected_groups)
        # Every L2 node lands in exactly one super-node's `members`.
        rolled = [m for n in payload.nodes for m in (n.members or [])]
        self.assertEqual(sorted(rolled), sorted(raw_ids))
        self.assertEqual(len(rolled), len(set(rolled)))

        self.assertEqual(payload.levels, graph["levels"])
        self.assertEqual(payload.cycles, graph["cycles"])
        self.assertEqual(payload.divergence, graph["divergence"])

    def test_l3_edges_aggregate_and_drop_intra_package(self) -> None:
        from web.api import encoding
        from web.api.models import GraphResponse

        dataflow = self._read_artifact("dataflow")
        xref = self._read_artifact("xref")
        file_of = self._expected_file_of(dataflow, xref)
        expected: dict = {}
        for edge in dataflow["edges"]:
            src = encoding.container_group(edge["source"], 1, file_of)
            tgt = encoding.container_group(edge["target"], 1, file_of)
            if src == tgt:
                continue
            key = (src, tgt, edge.get("channel", "flow"))
            expected[key] = expected.get(key, 0) + 1

        client = self._client()
        resp = client.get("/api/graph", params={
            "level": "L3", "repo": str(MINIREPO), "state_dir": str(self.state_dir),
        })
        payload = GraphResponse(**resp.json())

        got = {(e.source, e.target, e.kind): e.count for e in payload.edges}
        self.assertEqual(got, expected)

    # ---------------------------------------------------------------- L2

    def test_l2_nodes_are_the_typed_dataflow_graph(self) -> None:
        from web.api.models import GraphResponse

        dataflow = self._read_artifact("dataflow")
        raw_ids = {end for e in dataflow["edges"] for end in (e["source"], e["target"])}

        client = self._client()
        resp = client.get("/api/graph", params={
            "level": "L2", "repo": str(MINIREPO), "state_dir": str(self.state_dir),
        })
        self.assertEqual(resp.status_code, 200)
        payload = GraphResponse(**resp.json())

        self.assertEqual({n.id for n in payload.nodes}, raw_ids)
        self.assertEqual(len(payload.edges), len(dataflow["edges"]))
        # Every node carries the three encoding channels the canvas needs.
        for node in payload.nodes:
            self.assertIsNotNone(node.type)
            self.assertIn(node.family, ("code", "runtime", "state"))
            self.assertGreater(node.degree or 0, 0)

    def test_l2_scope_filter_descends_into_one_l3_package(self) -> None:
        from web.api import encoding
        from web.api.models import GraphResponse

        dataflow = self._read_artifact("dataflow")
        xref = self._read_artifact("xref")
        raw_ids = {end for e in dataflow["edges"] for end in (e["source"], e["target"])}
        file_of = self._expected_file_of(dataflow, xref)
        target = sorted({encoding.container_group(raw_id, 1, file_of) for raw_id in raw_ids})[0]
        members = {raw_id for raw_id in raw_ids if encoding.container_group(raw_id, 1, file_of) == target}

        client = self._client()
        resp = client.get("/api/graph", params={
            "level": "L2", "scope": target,
            "repo": str(MINIREPO), "state_dir": str(self.state_dir),
        })
        self.assertEqual(resp.status_code, 200)
        payload = GraphResponse(**resp.json())

        self.assertEqual(payload.scope, target)
        node_ids = {n.id for n in payload.nodes}
        self.assertTrue(members <= node_ids)
        self.assertLessEqual(len(node_ids), len(raw_ids))
        for edge in payload.edges:
            self.assertTrue(edge.source in members or edge.target in members)

    def test_l2_focus_restricts_without_changing_scope(self) -> None:
        """`focus=` (`WEB_REDESIGN_RESEARCH.md` §4's neighbourhood-focus
        toggle) narrows the rendered node set the same way `scope=` would,
        but the response's own `scope` field stays `None` -- unlike a real
        descent, this must not move the breadcrumb."""
        from web.api.models import GraphResponse

        client = self._client()
        params = {"repo": str(MINIREPO), "state_dir": str(self.state_dir)}
        unrestricted = GraphResponse(**client.get("/api/graph", params={"level": "L2", **params}).json())
        target = sorted(n.id for n in unrestricted.nodes)[0]

        resp = client.get("/api/graph", params={"level": "L2", "focus": target, **params})
        self.assertEqual(resp.status_code, 200)
        payload = GraphResponse(**resp.json())

        self.assertIsNone(payload.scope)
        self.assertIn(target, {n.id for n in payload.nodes})
        self.assertLessEqual(len(payload.nodes), len(unrestricted.nodes))

    def test_l2_too_large_returns_suggested_scopes_instead_of_the_full_graph(self) -> None:
        """`WEB_REDESIGN_RESEARCH.md` §3.1: unscoped L2 has no natural size
        bound and must not be allowed to reach the client uncapped. Forces
        the real ceiling down via monkeypatch (the minirepo fixture is far
        too small to hit `GRAPH_SIZE_CEILING` for real) so this exercises the
        actual code path, not a hand-simulated shape."""
        from web.api import app as app_module
        from web.api.models import GraphResponse

        client = self._client()
        params = {"level": "L2", "repo": str(MINIREPO), "state_dir": str(self.state_dir)}
        original = app_module.GRAPH_SIZE_CEILING
        app_module.GRAPH_SIZE_CEILING = 0
        try:
            resp = client.get("/api/graph", params=params)
        finally:
            app_module.GRAPH_SIZE_CEILING = original

        self.assertEqual(resp.status_code, 200)
        payload = GraphResponse(**resp.json())
        self.assertTrue(payload.too_large)
        self.assertEqual(payload.nodes, [])
        self.assertEqual(payload.edges, [])
        self.assertTrue(payload.suggested_scopes)

    def test_graph_response_is_gzip_compressed_when_large_enough(self) -> None:
        """`WEB_REDESIGN_RESEARCH.md` §5 item 2 -- verified, not assumed:
        no gzip middleware existed in this service before this pass."""
        client = self._client()
        resp = client.get(
            "/api/graph",
            params={"level": "L2", "repo": str(MINIREPO), "state_dir": str(self.state_dir)},
            headers={"Accept-Encoding": "gzip"},
        )
        self.assertEqual(resp.status_code, 200)
        # TestClient/httpx decodes transparently; the raw header is what
        # proves the server actually compressed it.
        self.assertEqual(resp.headers.get("content-encoding"), "gzip")
        self.assertIn("total;dur=", resp.headers.get("server-timing", ""))

    def test_l2_node_id_resolves_through_the_node_endpoint(self) -> None:
        """The inspector hands `node.node_id` straight to `/api/node/{id}`;
        if that mapping drifts, every peek card at L2 silently 404s."""
        from web.api.models import GraphResponse

        client = self._client()
        params = {"repo": str(MINIREPO), "state_dir": str(self.state_dir)}
        payload = GraphResponse(**client.get("/api/graph", params={"level": "L2", **params}).json())

        typed = [n for n in payload.nodes if n.type != "module"]
        self.assertTrue(typed, "fixture has no typed dataflow nodes to check")
        for node in typed[:10]:
            self.assertIsNotNone(node.node_id)
            resp = client.get("/api/node/%s" % node.node_id, params=params)
            self.assertEqual(resp.status_code, 200, "%s -> %s" % (node.node_id, resp.text))

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

    # ---------------------------------------------------------- rungs (P{n})

    def test_rungs_reports_exactly_l3_and_l2_for_a_repo_with_no_real_nesting(self) -> None:
        """`MONOREPO_HIERARCHY.md`'s compatibility invariant: a repo whose
        computed fork set is `{1}` -- true of this flat fixture -- must
        report exactly today's two-rung ladder, never a `P{n}` entry."""
        from web.api.models import GraphResponse

        client = self._client()
        resp = client.get("/api/graph", params={
            "level": "L3", "repo": str(MINIREPO), "state_dir": str(self.state_dir),
        })
        self.assertEqual(resp.status_code, 200)
        payload = GraphResponse(**resp.json())
        self.assertEqual(
            [(r.level, r.depth) for r in payload.rungs],
            [("L3", 1), ("L2", None)],
        )

    def test_p2_is_unsupported_on_a_repo_with_no_depth_2_fork(self) -> None:
        """`P2` only becomes a valid `level` once `encoding.real_depths`
        actually finds a fork past depth 1 -- this fixture doesn't have one,
        so the request must 501, naming the real ladder, not a stale one."""
        client = self._client()
        resp = client.get("/api/graph", params={
            "level": "P2", "repo": str(MINIREPO), "state_dir": str(self.state_dir),
        })
        self.assertEqual(resp.status_code, 501)
        detail = resp.json()["detail"]
        self.assertIn("levels available: L0, L1, L2, L3", detail)

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
