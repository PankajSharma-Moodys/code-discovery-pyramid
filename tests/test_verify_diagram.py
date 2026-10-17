"""`cdp verify-diagram`: Mermaid edges graded against the repo (cdp/diagram.py)."""

from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import FIXTURES, make_repo  # noqa: F401  (sets sys.path)

from cdp import diagram
from cdp.cli import main

DIAGRAMS = FIXTURES / "diagrams"


class VerifyDiagramTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        cls.repo = make_repo(Path(cls.tmp.name), "diagrams/repo")

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def run_cli(self, *argv, stdin: str = None):
        out = io.StringIO()
        old = sys.stdin
        if stdin is not None:
            sys.stdin = io.StringIO(stdin)
        try:
            with contextlib.redirect_stdout(out):
                rc = main(["verify-diagram", *argv, "--repo", str(self.repo)])
        finally:
            sys.stdin = old
        return rc, out.getvalue()

    def edges(self, name: str):
        rc, out = self.run_cli(str(DIAGRAMS / name), "--json")
        return rc, json.loads(out)["diagrams"][0]["edges"]

    def test_flowchart_statuses(self) -> None:
        rc, edges = self.edges("flow.mmd")
        self.assertEqual(rc, 3)
        got = [(e["from"], e["to"], e["status"]) for e in edges]
        self.assertEqual(got, [
            ("R", "S", "uncited"),           # citation-free solid edge
            ("S", "V", "correct"),           # validator.validate at :9
            ("S", "DB", "correct"),          # `A -- "label" --> B` form, full path
            ("S", "L", "inferred"),          # dashed, no cite: honest, not a failure
            ("S", "D", "wrong_citation"),    # :16 is the method signature
            ("S", "D", "wrong_citation"),    # :14 is a doc comment
            ("S", "U", "ambiguous"),         # two Util.java
            ("S", "M", "wrong_citation"),    # no such file
            ("S", "X", "wrong_citation"),    # past end of file
        ])
        self.assertEqual(edges[4]["cites"][0]["hint"], "svc/OrderService.java:21")
        self.assertEqual(edges[5]["cites"][0]["hint"], "svc/OrderService.java:21")
        self.assertIn("only svc/a/Util.java shows the edge", edges[6]["cites"][0]["detail"])
        self.assertTrue(edges[3]["inferred"] and edges[3]["dashed"])

    def test_state_diagram_rejects_doc_and_generic_lines(self) -> None:
        rc, edges = self.edges("state.mmd")
        self.assertEqual(rc, 3)
        self.assertEqual([e["status"] for e in edges],
                         ["unsupported", "correct", "correct", "wrong_citation"])
        self.assertEqual(edges[3]["cites"][0]["hint"], "svc/Orders.scala:11")
        self.assertEqual(len(edges), 4, "bare `X --> [*]` and block notes are not edges")

    def test_markdown_fences_and_exit_zero(self) -> None:
        rc, out = self.run_cli(str(DIAGRAMS / "good.md"))
        self.assertEqual(rc, 0, out)
        self.assertIn("2 correct, 1 inferred", out)
        self.assertIn("tip", out)

    def test_stdin_and_text_table(self) -> None:
        src = (DIAGRAMS / "flow.mmd").read_text()
        rc, out = self.run_cli("-", stdin=src)
        self.assertEqual(rc, 3)
        self.assertIn("wrong_citation", out)
        self.assertTrue(out.splitlines()[-1].startswith("next"))

    def test_parse_errors_exit_one(self) -> None:
        rc, out = self.run_cli("-", stdin="sequenceDiagram\n A->>B: hi\n")
        self.assertEqual(rc, 1)
        self.assertIn("error", out)
        note = "stateDiagram-v2\n  A --> B: x (svc/Orders.scala:7)\n  note right of B: see Orders.scala:7\n"
        rc, out = self.run_cli("-", "--json", stdin=note)
        self.assertEqual(rc, 1)
        self.assertIn("one-line note", json.loads(out)["diagrams"][0]["errors"][0])

    def test_bare_line_reuses_last_file(self) -> None:
        src = "stateDiagram-v2\n  NEW --> PAID: pay svc/Orders.scala:7\n  PAID --> SHIPPED: ship :11\n"
        rc, out = self.run_cli("-", "--json", stdin=src)
        edges = json.loads(out)["diagrams"][0]["edges"]
        self.assertEqual(rc, 0, out)
        self.assertEqual(edges[1]["cites"][0]["file"], "svc/Orders.scala")

    def test_resolve_hints_and_tests(self) -> None:
        files = ["svc/a/Util.java", "svc/b/Util.java", "svc/OrderService.java",
                 "svc/test/OrderService.java"]
        self.assertEqual(diagram.resolve("Util.java", ["b/"], files, ""), ["svc/b/Util.java"])
        self.assertEqual(diagram.resolve("OrderService.java", [], files, ""), ["svc/OrderService.java"])
        self.assertEqual(diagram.resolve("Service.java", [], files, "OrderService.placeOrder"),
                         ["svc/OrderService.java"])
        self.assertEqual(len(diagram.resolve("Util.java", [], files, "")), 2)

    def test_cite_regex_covers_source_extensions(self) -> None:
        for path in ("a/b.py", "x.go", "web/app.ts", "H.cs", "S.scala", "J.java", "q.sql", "K.kt"):
            cites, _ = diagram.find_cites("call (%s:12-14, :20)" % path, None)
            self.assertEqual(cites[0]["path"], path)
            self.assertEqual(cites[0]["spans"], [(12, 14), (20, 20)])


if __name__ == "__main__":
    unittest.main()
