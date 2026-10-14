"""For-comprehension binders shadow outer names for the rest of the for expression only."""

from __future__ import annotations

import unittest

from helpers import SKILL_ROOT  # noqa: F401  (sets sys.path)

from cdp.lang.base import ExtractContext
from cdp.lang.scala import ScalaExtractor

HEAD = "package p\nclass Foo { def bar(): Int = 1 }\nclass Item { def bar(): Int = 2 }\nclass S {\n  val f: Foo = new Foo\n"


def calls(body: str):
    src = HEAD + body + "\n}\n"
    facts = ScalaExtractor().extract(ExtractContext("p/S.scala", src.splitlines(), "root"))
    return sorted((u["from_symbol"].split("#")[-1], u["fqn"]) for u in facts.uses if u.get("kind") == "call")


class ForShadowTest(unittest.TestCase):
    def test_brace_generator_shadows_in_yield(self):
        self.assertEqual(calls("  def a(xs: List[Item]) = for { f <- xs } yield f.bar()"), [])

    def test_paren_generator_shadows_in_yield(self):
        self.assertEqual(calls("  def a(xs: List[Item]) = for (f <- xs) yield f.bar()"), [])

    def test_binding_ends_with_the_for(self):
        self.assertEqual(calls("  def a(xs: List[Item]) = {\n    for (f <- xs) yield f.bar()\n    f.bar()\n  }"),
                         [("a", "p.Foo#bar")])

    def test_value_definition_shadows(self):
        self.assertEqual(calls("  def a(xs: List[Item]) = for {\n    x <- xs\n    f = x\n  } yield f.bar()"), [])

    def test_pattern_binding_shadows(self):
        self.assertEqual(calls("  def a(xs: List[(Int, Item)]) = for {\n    (n, f) <- xs\n  } yield f.bar()"), [])

    def test_earlier_generator_still_sees_outer_name(self):
        self.assertEqual(calls("  def a(xs: List[Item]) = for {\n    y <- f.bar() :: Nil\n    f <- xs\n  } yield f.bar()"),
                         [("a", "p.Foo#bar")])

    def test_unshadowed_outer_field_still_resolves(self):
        self.assertEqual(calls("  def a(xs: List[Item]) = for { x <- xs } yield f.bar()"), [("a", "p.Foo#bar")])

    def test_block_body_and_nesting(self):
        self.assertEqual(calls("  def a(xs: List[Item]) = {\n    for (f <- xs) yield {\n      f.bar()\n    }\n    f.bar()\n  }"),
                         [("a", "p.Foo#bar")])

    def test_guard_sees_the_generator_binder(self):
        self.assertEqual(calls("  def a(xs: List[Item]) = for (f <- xs if f.bar() > 0) yield 1"), [])


if __name__ == "__main__":
    unittest.main()
