"""Test-DSL glue (`when`, `should`, `in`, ...) produces no use rows; a file declaring the name keeps them."""

from __future__ import annotations

import unittest

from helpers import SKILL_ROOT  # noqa: F401  (sets sys.path)

from cdp.lang.base import ExtractContext
from cdp.lang.scala import ScalaExtractor


def calls(src: str):
    ctx = ExtractContext(path="a/X.scala", lines=src.splitlines(), module="root")
    return {u["fqn"] for u in ScalaExtractor().extract(ctx).uses if u.get("kind") == "call"}


class GlueTest(unittest.TestCase):
    SPEC = ("package p\nclass Repo { def save(x: Int) = 1 }\n"
            "class S extends FlatSpec {\n  val r = mock[Repo]\n"
            "  it should \"x\" in {\n    when(r.save(1)).thenReturn(2)\n    r.save(1) shouldBe 2\n  }\n}\n")

    def test_glue_dropped_real_call_kept(self) -> None:
        got = calls(self.SPEC)
        self.assertIn("p.Repo#save", got)
        for name in ("when", "in", "should", "shouldBe", "thenReturn"):
            self.assertFalse([f for f in got if f.endswith("#" + name)], (name, got))

    def test_declared_name_kept(self) -> None:
        src = "package p\nclass S { def when(x: Int) = 1\n def m() = when(2) }\n"
        self.assertIn("p.S#when", calls(src))


if __name__ == "__main__":
    unittest.main()
