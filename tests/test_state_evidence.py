"""State evidence on enum-value uses: `access` (write|guard|read), `value`, and `from` on an explicit
transition, carried from the extractors through resolve into `used_by` -- and nowhere else."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from helpers import Pipeline, SKILL_ROOT  # noqa: F401  (sets sys.path)
from test_java_resolution import inline_repo

from cdp.lang.base import ExtractContext, mk_use
from cdp.lang.csharp import CSharpExtractor
from cdp.lang.java import JavaExtractor
from cdp.lang.scala import ScalaExtractor


def marked(extractor, path: str, src: str):
    """`(line, value name, access)` of every annotated row."""
    facts = extractor.extract(ExtractContext(path=path, lines=src.splitlines(), module="m"))
    return sorted((u["anchor"]["line"], u["value"].rsplit(".", 1)[1], u["access"]) for u in facts.uses if "access" in u)


class ExtractTest(unittest.TestCase):
    def test_java(self) -> None:
        src = ("package p;\nenum St { A, B }\nclass X {\n  St s;\n  void m(St t) {\n"
               "    if (s == St.A) { s = St.B; }\n"          # 6
               "    setStatus(St.A);\n"                       # 7
               "    St local = St.B;\n"                       # 8
               "    foo(St.A);\n"                             # 9
               "    if (Set.of(St.A, St.B).contains(t)) {}\n"  # 10
               "    if (St.B.equals(t)) {}\n  }\n}\n")       # 11
        self.assertEqual(marked(JavaExtractor(), "p/X.java", src), [
            (6, "A", "guard"), (6, "B", "write"), (7, "A", "write"), (8, "B", "read"), (9, "A", "read"),
            (10, "A", "guard"), (10, "B", "guard"), (11, "B", "guard")])

    def test_scala(self) -> None:
        src = ("package p\nobject St extends Enumeration { val A, B = Value }\nclass X {\n  def m(s: String) = {\n"
               "    if (s == St.A.toString) {}\n"                  # 5
               "    val c = x.copy(status = St.A.toString)\n"      # 6
               "    b.withStatus(St.B.toString)\n"                 # 7
               "    val q = St.B.toString\n"                       # 8
               "    !List(St.A, St.B).contains(s)\n"               # 9
               "    new StatusIn(List(St.A).map(_.toString))\n  }\n}\n")   # 10
        self.assertEqual(marked(ScalaExtractor(), "p/X.scala", src), [
            (5, "A", "guard"), (6, "A", "write"), (7, "B", "write"), (8, "B", "read"),
            (9, "A", "guard"), (9, "B", "guard"), (10, "A", "guard")])

    def test_csharp(self) -> None:
        src = ("namespace N {\n  enum St { A, B }\n  class X {\n    St S;\n    void M(string v) {\n"
               "      if (S == St.A) { S = St.B; }\n"                 # 6
               "      var r = new R { State = St.A };\n"              # 7
               "      UpdateEdmStateAsync(1, St.B);\n"                # 8
               "      if (S is St.A or St.B) {}\n"                    # 9
               "      if (v != nameof(St.A)) {}\n"                    # 10
               "      d[\"status\"] = nameof(St.B);\n"                # 11
               "      switch (S) { case St.A: break; }\n    }\n  }\n}\n")   # 12
        self.assertEqual(marked(CSharpExtractor(), "N/X.cs", src), [
            (6, "A", "guard"), (6, "B", "write"), (7, "A", "write"), (8, "B", "write"), (9, "A", "guard"),
            (9, "B", "guard"), (10, "A", "guard"), (11, "B", "read"), (12, "A", "guard")])

    def test_rows_without_evidence_are_unchanged(self) -> None:
        self.assertEqual(mk_use("a.B", {"line": 1}), {"fqn": "a.B", "resolved": "external", "via_import": False,
                                                      "anchor": {"line": 1}})
        src = "package p;\nclass X {\n  void m() { Other.run(); int n = Other.count; }\n}\n"
        facts = JavaExtractor().extract(ExtractContext(path="p/X.java", lines=src.splitlines(), module="m"))
        self.assertFalse([u for u in facts.uses if "access" in u or "value" in u])


class ResolveTest(unittest.TestCase):
    """Through every phase: only a use of an enum's value keeps the fields, and `used_by` carries them."""

    FILES = {
        "build.sbt": "name := \"m\"\n",
        "src/main/scala/p/St.scala": "package p\nobject St extends Enumeration {\n  val QUEUED, RUNNING, DONE = Value\n}\n",
        "src/main/scala/p/Conf.scala": "package p\nobject Conf {\n  final val LIMIT = 3\n}\n",
        "src/main/scala/p/Ev.scala": "package p\ncase class Ev(id: Int, newStatus: St.Value, oldStatus: St.Value)\n",
        "src/main/scala/p/Svc.scala": (
            "package p\nclass Svc {\n  def go(s: St.Value): Unit = {\n"
            "    if (s == St.QUEUED) post(Ev(1, St.RUNNING, St.QUEUED))\n"    # 4
            "    post(Ev(2, St.DONE, s))\n"                                   # 5
            "    val n = Conf.LIMIT\n  }\n  def post(e: Ev): Unit = ()\n}\n"),  # 6
    }

    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        cls.p = Pipeline(inline_repo(Path(cls.tmp.name), cls.FILES))

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def test_used_by_carries_access_value_and_transition(self) -> None:
        got = sorted((u["anchor"]["line"], u["value"].rsplit(".", 1)[1], u["access"], u.get("from", ""))
                     for u in self.p.xref["used_by"]["p.St"] if "access" in u)
        self.assertEqual(got, [(4, "QUEUED", "guard", ""), (4, "QUEUED", "read", ""),
                               (4, "RUNNING", "write", "p.St.QUEUED"), (5, "DONE", "write", "")])

    def test_non_enum_constant_gets_no_fields(self) -> None:
        rows = [u for u in self.p.xref["uses"] if u["fqn"] == "p.Conf"]
        self.assertTrue(rows)
        self.assertFalse([u for u in rows if "access" in u or "value" in u])
        self.assertFalse([u for u in self.p.xref["used_by"].get("p.Conf", []) if "access" in u])


if __name__ == "__main__":
    unittest.main()
