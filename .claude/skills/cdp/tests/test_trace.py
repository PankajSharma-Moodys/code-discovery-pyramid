"""`cdp query trace` — `PHASE/phase_1_plan.md` M1.5.

Two things are being tested, and the second matters more than the first: that
the trace returns a sufficient cited file set, and that **it does not
over-claim**. `ARCHITECTURE.md` states the limit plainly — CDP does not answer
the question, it collapses a wide grep into a small cited read whose
completeness is either guaranteed or explicitly qualified. Every assertion below
about a caveat, an `elided` count or a stated reason is testing that limit.
"""

from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from helpers import make_repo  # noqa: F401  (sets sys.path)

from cdp.cli import main
from cdp.query import Budget, Store, q_trace


class TraceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        cls.repo = make_repo(Path(cls.tmp.name))
        cls.state = Path(cls.tmp.name) / "state"
        main(["scan", "--repo", str(cls.repo), "--state-dir", str(cls.state),
              "--quiet"])
        cls.store = Store(cls.state)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.store.close()
        cls.tmp.cleanup()

    def run_cli(self, *argv) -> str:
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = main(list(argv) + ["--state-dir", str(self.state)])
        self.assertEqual(code, 0)
        return buf.getvalue()

    # ----------------------------------------------------- the reading list

    def test_an_http_entry_point_returns_a_cited_file_set(self) -> None:
        result = q_trace(self.store, "/v1/widgets")
        self.assertTrue(result["found"])
        self.assertEqual(result["resolved_as"]["channel"], "http_in")
        paths = {row["file"] for row in result["files"]}
        # The handler, the entity it persists and the repository that writes it
        # are all reachable from the route and all cited.
        self.assertIn("web/src/main/java/com/example/mini/web/WidgetResource.java", paths)
        self.assertIn("core/src/main/java/COM/Example/mini/core/WidgetRepository.java", paths)

    def test_every_file_carries_the_edge_that_justified_it(self) -> None:
        """A file with no justifying edge is not in the list, which is the only
        reason the list can be called minimal."""
        for row in q_trace(self.store, "/v1/widgets")["files"]:
            self.assertTrue(row["why"], row)
            self.assertTrue(row["at"], row)
            self.assertIn(row["confidence"], ("high", "medium"))

    def test_the_route_handler_resolves_to_a_walkable_node(self) -> None:
        """A route handler is `Class#method`; the dataflow graph is keyed on the
        file's primary symbol. Walking from the raw handler finds no adjacency
        and returns a one-file trace that reads as 'this endpoint touches
        nothing'."""
        result = q_trace(self.store, "/v1/widgets")
        self.assertNotIn("#", result["resolved_as"]["node"])
        self.assertGreater(len(result["files"]), 1)

    def test_a_symbol_entry_point_also_works(self) -> None:
        result = q_trace(self.store, "WidgetRepository")
        self.assertTrue(result["found"])
        self.assertEqual(result["resolved_as"]["kind"], "symbol")

    # ------------------------------------------------------- not over-claiming

    def test_the_caveat_is_always_present(self) -> None:
        self.assertIn("reading list, not an answer",
                      q_trace(self.store, "/v1/widgets")["caveat"])

    def test_the_import_caveat_is_carried(self) -> None:
        """`dataflow.py:16-19`: an import proves reachability, not invocation."""
        self.assertIn("not that it does", q_trace(self.store, "/v1/widgets")["caveat"])

    def test_budget_zero_returns_the_entry_point_and_a_count(self) -> None:
        """Never an empty set with no explanation."""
        result = q_trace(self.store, "/v1/widgets", budget=Budget(0))
        self.assertEqual(len(result["files"]), 1)
        self.assertEqual(result["files"][0]["why"][:5], "entry")
        self.assertGreater(result["elided"], 0)
        self.assertIn("admits no rows", result["budget_note"])

    def test_a_symbol_with_no_outgoing_edges_says_why_the_trail_stops(self) -> None:
        """Empty output would read as 'nothing calls this'."""
        result = q_trace(self.store, "com.example.mini.web.ApiPaths")
        self.assertTrue(result["found"])
        self.assertTrue(result["files"])
        self.assertIn("No dataflow edge leaves", result["trail"])
        self.assertIn("query coverage", result["trail"])

    def test_hops_exhausted_is_reported_as_elision_not_completion(self) -> None:
        """A walk bounded by --max-hops has not finished. Reporting it as
        completion is how a cycle becomes a confident wrong answer."""
        deep = q_trace(self.store, "/v1/widgets", max_hops=99)
        shallow = q_trace(self.store, "/v1/widgets", max_hops=1)
        self.assertFalse(deep["hops_exhausted"])
        self.assertTrue(shallow["hops_exhausted"])
        # And the renderer says so, rather than presenting a bounded walk as a
        # finished one.
        out = self.run_cli("query", "trace", "/v1/widgets", "--max-hops", "1")
        self.assertIn("the trail continues beyond this list", out)

    def test_an_unresolvable_entry_point_says_so(self) -> None:
        result = q_trace(self.store, "NoSuchThingAnywhere")
        self.assertFalse(result["found"])
        self.assertIn("coverage", result["why"])
        self.assertEqual(result["files"], [])

    # --------------------------------------------------------------- the CLI

    def test_cli_renders_and_carries_the_mandatory_footer(self) -> None:
        out = self.run_cli("query", "trace", "/v1/widgets")
        self.assertIn("entry  GET /v1/widgets", out)
        self.assertRegex(out, r"elided: \d+")
        self.assertRegex(out, r"as of \S+@\S+, state v\d+")

    def test_cli_json_shape(self) -> None:
        data = json.loads(self.run_cli("query", "trace", "/v1/widgets", "--json"))
        self.assertEqual(data["query"], "trace")
        self.assertIn("file_count", data)
        self.assertIn("as_of", data)

    def test_cli_requires_an_entry_point(self) -> None:
        self.assertEqual(main(["query", "trace", "--state-dir", str(self.state)]), 2)


if __name__ == "__main__":
    unittest.main()
