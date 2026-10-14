"""Lambda params and `case` binders shadow outer names only inside their body."""

from __future__ import annotations

import unittest

from helpers import SKILL_ROOT  # noqa: F401  (sets sys.path)

from cdp.lang.base import ExtractContext
from cdp.lang.scala import ScalaExtractor

HEAD = "package p\nclass Foo { def bar(): Int = 1; def baz(): Int = 3 }\nclass Item { def bar(): Int = 2 }\nclass S {\n  val f: Foo = new Foo\n"
BAZ = ("a", "p.Foo#baz")


def calls(body: str):
    src = HEAD + body + "\n}\n"
    facts = ScalaExtractor().extract(ExtractContext("p/S.scala", src.splitlines(), "root"))
    return sorted((u["from_symbol"].split("#")[-1], u["fqn"]) for u in facts.uses if u.get("kind") == "call")


class LambdaScopeTest(unittest.TestCase):
    def test_paren_lambda_ends(self):
        self.assertEqual(calls("  def a(xs: List[Item]) = {\n    xs.map(f => f.bar())\n    f.baz()\n  }"),
                         [BAZ])

    def test_tuple_params_end(self):
        self.assertEqual(calls("  def a(xs: List[Item]) = {\n    xs.foldLeft(0)((f, g) => f)\n    f.baz()\n  }"),
                         [BAZ])

    def test_typed_param_ends_and_types(self):
        self.assertEqual(calls("  def a(xs: List[Item]) = {\n    xs.map((f: Item) => f.bar())\n    f.baz()\n  }"),
                         [("a", "p.Foo#baz"), ("a", "p.Item#bar")])

    def test_block_lambda_ends(self):
        self.assertEqual(calls("  def a(xs: List[Item]) = {\n    xs.map { f =>\n      f.bar()\n    }\n    f.baz()\n  }"),
                         [BAZ])

    def test_comma_ends_lambda(self):
        self.assertEqual(calls("  def a(xs: List[Item]) = {\n    xs.fold(g => g, f.baz())\n  }"), [BAZ])

    def test_lambda_shadows_inside(self):
        self.assertEqual(calls("  def a(xs: List[Item]) = xs.map(f => f.bar())"), [])


class CaseScopeTest(unittest.TestCase):
    def test_typed_case_ends(self):
        self.assertEqual(calls("  def a(x: Any) = {\n    x match { case f: Item => f.bar() }\n    f.baz()\n  }"),
                         [BAZ, ("a", "p.Item#bar")])

    def test_typed_case_is_typed(self):
        self.assertEqual(calls("  def a(x: Any) = x match { case f: Item => f.bar() }"), [("a", "p.Item#bar")])

    def test_extractor_case_ends(self):
        self.assertEqual(calls("  def a(x: Any) = {\n    x match { case Some(f) => f.bar() }\n    f.baz()\n  }"),
                         [BAZ])

    def test_at_binder_ends(self):
        self.assertEqual(calls("  def a(x: Any) = {\n    x match { case f @ Some(_) => f.bar() }\n    f.baz()\n  }"),
                         [BAZ])

    def test_alternatives_end(self):
        self.assertEqual(calls("  def a(x: Any) = {\n    x match { case 1 | 2 => 0 }\n    f.baz()\n  }"), [BAZ])

    def test_next_case_does_not_see_binder(self):
        self.assertEqual(calls("  def a(x: Any) = x match {\n    case f: Item => 1\n    case _ => f.baz()\n  }"),
                         [BAZ])

    def test_partial_function_lambda(self):
        self.assertEqual(calls("  def a(xs: List[Any]) = {\n    xs.map { case f: Item => f.bar() }\n    f.baz()\n  }"),
                         [("a", "p.Foo#baz"), ("a", "p.Item#bar")])


if __name__ == "__main__":
    unittest.main()
