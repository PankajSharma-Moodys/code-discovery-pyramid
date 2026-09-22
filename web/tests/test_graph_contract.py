"""`ATLAS_REDESIGN.md` §2's acceptance gate, as a test.

The redesign's finding was not "the canvas is ugly" -- it was that at every
altitude almost no edge had *both* endpoints in the node set the same
response shipped, so a force layout had nothing to lay out:

| altitude | edges | renderable | before |
|---|---|---|---|
| L0 | 371 | 2 | 0.5% |
| L1 | 2 | 2 | (2 edges over 413 files) |
| L2 | 1 | 1 | (1 edge over 20 scopes) |
| L3 | 2 | 2 | (2 edges over 7 modules) |

Two things went wrong and each gets its own assertion below. `renderable /
total >= 0.95` catches the namespace mix (L0's symbol nodes vs module edges).
A separate floor on the altitudes the UI actually ships catches the other
half, which a ratio alone cannot see: a graph of 2 edges scores a perfect
1.0 and still draws nothing.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
MINIREPO = REPO_ROOT / "tests" / "fixtures" / "minirepo"

#: §2's acceptance number.
MIN_RENDERABLE_RATIO = 0.95

#: The altitudes the Atlas ladder offers (`store/atlasStore.ts`'s `ALTITUDES`).
#: L0/L1 stay reachable through the API -- the ask bar's symbol typeahead
#: reads L0 -- but §7 found the file graph has no import edges to draw, so
#: they are cut from the canvas rather than styled, and are held to the
#: ratio only.
SHIPPED_ALTITUDES = ("L3", "L2")


class GraphContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.state_dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.state_dir, ignore_errors=True)
        subprocess.run(
            [sys.executable, "-m", "cdp", "scan", "--repo", str(MINIREPO),
             "--state-dir", str(self.state_dir)],
            cwd=REPO_ROOT, check=True, capture_output=True, text=True,
        )

    def _graph(self, level: str, scope: str | None = None) -> dict:
        from fastapi.testclient import TestClient
        from web.api.app import app

        params = {"level": level, "repo": str(MINIREPO), "state_dir": str(self.state_dir)}
        if scope is not None:
            params["scope"] = scope
        resp = TestClient(app).get("/api/graph", params=params)
        self.assertEqual(resp.status_code, 200, resp.text)
        return resp.json()

    @staticmethod
    def _renderable(graph: dict) -> "tuple[int, int]":
        ids = {n["id"] for n in graph["nodes"]}
        renderable = sum(
            1 for e in graph["edges"] if e["source"] in ids and e["target"] in ids
        )
        return renderable, len(graph["edges"])

    def test_every_altitude_renders_at_least_95_percent_of_its_edges(self) -> None:
        for level in ("L0", "L1", "L2", "L3"):
            with self.subTest(level=level):
                renderable, total = self._renderable(self._graph(level))
                if total == 0:
                    continue  # nothing to dangle; the floor test below covers this
                self.assertGreaterEqual(
                    renderable / total, MIN_RENDERABLE_RATIO,
                    "%s: %d/%d edges have both endpoints in the node set -- "
                    "node and edge namespaces have drifted apart again"
                    % (level, renderable, total),
                )

    def test_shipped_altitudes_have_a_graph_to_draw(self) -> None:
        for level in SHIPPED_ALTITUDES:
            with self.subTest(level=level):
                graph = self._graph(level)
                self.assertGreater(len(graph["nodes"]), 1, "%s has no nodes" % level)
                self.assertGreater(len(graph["edges"]), 0, "%s has no edges" % level)

    def test_no_node_is_isolated_at_the_shipped_altitudes(self) -> None:
        """A force layout on isolated nodes produces the scattered star-field
        §1 measured; the typed graph has no isolated node by construction
        (its node set *is* the endpoints of its edges) and this pins that."""
        for level in SHIPPED_ALTITUDES:
            with self.subTest(level=level):
                graph = self._graph(level)
                on_an_edge = {e["source"] for e in graph["edges"]}
                on_an_edge |= {e["target"] for e in graph["edges"]}
                isolated = [n["id"] for n in graph["nodes"] if n["id"] not in on_an_edge]
                self.assertEqual(isolated, [], "%s isolated nodes: %s" % (level, isolated[:5]))

    def test_scope_filter_preserves_the_contract(self) -> None:
        """Drilling from an L3 package into L2 must not reintroduce dangling
        edges at the boundary -- the filter has to pull in the far endpoint of
        every edge it keeps, not just the members."""
        l3 = self._graph("L3")
        for node in l3["nodes"][:5]:
            with self.subTest(scope=node["id"]):
                renderable, total = self._renderable(self._graph("L2", scope=node["id"]))
                if total == 0:
                    continue
                self.assertGreaterEqual(renderable / total, MIN_RENDERABLE_RATIO)

    def test_every_node_carries_the_encoding_channels(self) -> None:
        """`ATLAS_REDESIGN.md` §3 assigns shape/fill/size to `type`, `family`
        and `degree`. A node missing any of them falls back to Sigma's grey
        default -- the other half of why the canvas read as dead."""
        for level in SHIPPED_ALTITUDES:
            graph = self._graph(level)
            for node in graph["nodes"]:
                with self.subTest(level=level, node=node["id"]):
                    self.assertIsNotNone(node.get("type"))
                    self.assertIn(node.get("family"), ("code", "runtime", "state"))
                    self.assertIsNotNone(node.get("degree"))

    def test_legend_matches_what_is_on_the_canvas(self) -> None:
        for level in SHIPPED_ALTITUDES:
            graph = self._graph(level)
            legend_types = {row["type"] for row in graph["legend"]}
            node_types = {n["type"] for n in graph["nodes"]}
            with self.subTest(level=level):
                self.assertEqual(legend_types, node_types)


if __name__ == "__main__":
    unittest.main()
