"""Bare `when(..)` chains are cut only in files importing a test framework; explicit-receiver calls stay."""

from __future__ import annotations

import unittest

from helpers import SKILL_ROOT  # noqa: F401  (sets sys.path)

from cdp.lang.base import ExtractContext
from cdp.lang.scala import ScalaExtractor


def calls(src: str):
    ctx = ExtractContext(path="a/X.scala", lines=src.splitlines(), module="root")
    return {u["fqn"] for u in ScalaExtractor().extract(ctx).uses if u.get("kind") == "call"}


STUB = "package p\nclass Repo { def save(x: Int) = 1 }\nclass S {\n  val r = mock[Repo]\n  def m() = {\n    when(r.save(1)).thenReturn(2)\n  }\n}\n"


class GlueTest(unittest.TestCase):
    def test_framework_import_cuts_chain(self) -> None:
        got = calls("import org.mockito.Mockito._\n" + STUB)
        self.assertIn("p.Repo#save", got)
        self.assertFalse([f for f in got if f.endswith("#thenReturn")], got)

    def test_no_import_keeps_chain(self) -> None:
        self.assertTrue([f for f in calls(STUB) if f.endswith("#thenReturn")])

    def test_other_file_method_with_glue_name_kept(self) -> None:
        src = "package p\nimport org.scalatest.FlatSpec\nclass U { def go(m: Matrix) = m.times(2) }\n"
        self.assertIn("p.Matrix#times", calls(src))

    def test_declared_name_not_cut(self) -> None:
        src = ("package p\nimport org.mockito.Mockito._\nclass R { def foo() = 1 }\n"
               "class S { def when(x: Int): R = new R\n def m() = when(2).foo() }\n")
        self.assertIn("p.S#foo", calls(src))   # chain kept, typed later from S#when


if __name__ == "__main__":
    unittest.main()
