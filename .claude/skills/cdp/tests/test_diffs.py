"""`cdp diff` (3.2, M3.5): typed structural deltas between two snapshots'
already-computed views. Synthetic `graph`/`xref`/`state` dicts, matching the
real shapes (`cdp/graph.py:build_graph`, `cdp/query.py:Store`), not a scanned
repo -- the delta logic is pure and does not need a real pipeline to exercise.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT))

from cdp.diffs import diff_snapshots  # noqa: E402


def _graph(modules, declared=(), observed=(), observed_not_declared=()):
    return {
        "modules": list(modules),
        "declared": [{"from": a, "to": b} for a, b in declared],
        "observed": [{"from": a, "to": b} for a, b in observed],
        "divergence": {
            "observed_not_declared": [{"from": a, "to": b} for a, b in observed_not_declared],
            "declared_not_observed": [],
        },
    }


def _xref(routes=()):
    return {"routes": [{"verb": v, "route": r} for v, r in routes], "unresolved_routes": []}


def _state(claims=(), coverage=1.0):
    return {"claims": list(claims), "coverage": {"fraction": coverage}}


def _claim(cid, file="a.py", line=1):
    return {"id": cid, "kind": "k", "subject": cid, "evidence": [{"file": file, "line": line}]}


class DiffSnapshotsTest(unittest.TestCase):
    def test_module_added_and_removed(self):
        old = _graph(["a", "b"])
        new = _graph(["b", "c"])
        result = diff_snapshots(old, _xref(), _state(), new, _xref(), _state())
        self.assertEqual(result["modules"], {"added": ["c"], "removed": ["a"]})

    def test_declared_and_observed_edges(self):
        old = _graph(["a", "b"], declared=[("a", "b")], observed=[("a", "b")])
        new = _graph(["a", "b"], declared=[("a", "b")], observed=[("a", "b"), ("b", "a")])
        result = diff_snapshots(old, _xref(), _state(), new, _xref(), _state())
        self.assertEqual(result["declared_edges"], {"added": [], "removed": []})
        self.assertEqual(result["observed_edges"], {"added": [("b", "a")], "removed": []})

    def test_undeclared_dependency_appearing_is_a_finding(self):
        old = _graph(["a", "b"], observed_not_declared=[])
        new = _graph(["a", "b"], observed_not_declared=[("a", "b")])
        result = diff_snapshots(old, _xref(), _state(), new, _xref(), _state())
        self.assertEqual(result["undeclared_dependencies"]["appeared"], [("a", "b")])
        self.assertIn(
            "a now imports b, and that edge is not declared in any manifest", result["findings"]
        )

    def test_route_added_and_removed(self):
        old = _xref(routes=[("GET", "/v1/old")])
        new = _xref(routes=[("GET", "/v1/new")])
        result = diff_snapshots(_graph([]), old, _state(), _graph([]), new, _state())
        self.assertEqual(result["routes"], {"added": [("GET", "/v1/new")], "removed": [("GET", "/v1/old")]})
        self.assertIn("route added: GET /v1/new", result["findings"])
        self.assertIn("route removed: GET /v1/old", result["findings"])

    def test_claim_added_removed_and_anchor_moved(self):
        old_state = _state(claims=[_claim("kept", line=10), _claim("removed")])
        new_state = _state(claims=[_claim("kept", line=20), _claim("added")])
        result = diff_snapshots(_graph([]), _xref(), old_state, _graph([]), _xref(), new_state)
        self.assertEqual(result["claims"]["added"], ["added"])
        self.assertEqual(result["claims"]["removed"], ["removed"])
        self.assertEqual(len(result["claims"]["anchor_moved"]), 1)
        self.assertEqual(result["claims"]["anchor_moved"][0]["id"], "kept")

    def test_coverage_regression_is_a_finding(self):
        result = diff_snapshots(
            _graph([]), _xref(), _state(coverage=0.9),
            _graph([]), _xref(), _state(coverage=0.5),
        )
        self.assertTrue(result["coverage"]["regressed"])
        self.assertTrue(any("coverage regressed" in f for f in result["findings"]))

    def test_coverage_improvement_is_not_a_regression(self):
        result = diff_snapshots(
            _graph([]), _xref(), _state(coverage=0.5),
            _graph([]), _xref(), _state(coverage=0.9),
        )
        self.assertFalse(result["coverage"]["regressed"])

    def test_no_change_yields_empty_deltas(self):
        graph = _graph(["a"], declared=[], observed=[])
        xref = _xref()
        state = _state(claims=[_claim("x")])
        result = diff_snapshots(graph, xref, state, graph, xref, state)
        self.assertEqual(result["modules"], {"added": [], "removed": []})
        self.assertEqual(result["claims"], {"added": [], "removed": [], "anchor_moved": []})
        self.assertEqual(result["findings"], [])


if __name__ == "__main__":
    unittest.main()
