"""`val t = new T(..)` (field or local, incl. anonymous `new T {..}`) is typed T; other initializers are not guessed."""

from __future__ import annotations

import unittest

from helpers import SKILL_ROOT  # noqa: F401  (sets sys.path)

from cdp.lang.base import ExtractContext
from cdp.lang.scala import ScalaExtractor


def calls(src: str):
    ctx = ExtractContext(path="a/X.scala", lines=src.splitlines(), module="root")
    return {u["fqn"] for u in ScalaExtractor().extract(ctx).uses if u.get("kind") == "call"}


class NewFieldTest(unittest.TestCase):
    def test_field_forms(self) -> None:
        for init in ("new T(1)", "new T", "new T() { def x = 2 }", "new T {\n    def x = 2\n  }"):
            for kw in ("val", "var", "lazy val"):
                src = f"class T {{ def go() = 1 }}\nclass A {{\n  {kw} t = {init}\n  def m() = t.go()\n}}\n"
                self.assertIn("T#go", calls(src), (kw, init))

    def test_local_anonymous(self) -> None:
        src = "class T { def go() = 1 }\nclass A { def m() = { val t = new T(1) { def x = 2 }; t.go() } }\n"
        self.assertIn("T#go", calls(src))

    def test_generic_and_package(self) -> None:
        src = "package p\nclass T[X] { def go() = 1 }\nclass A { val t = new T[Int](1); def m() = t.go() }\n"
        self.assertIn("p.T#go", calls(src))

    def test_not_guessed(self) -> None:
        for init in ("new T(1).other()", "T(1)", "mk()", "new T(1) with U", "new T(1).x"):
            src = f"class T {{ def go() = 1 }}\nclass A {{ val t = {init}; def m() = t.go() }}\n"
            self.assertNotIn("T#go", calls(src), init)


class BuilderChainTest(unittest.TestCase):
    """A leading-dot continuation line makes the value the chain's result, not the `new` type."""

    DEFS = "class B { def setA(i: Int) = this; def build() = new C() }\nclass C { def run() = 1 }\n"

    @staticmethod
    def bare(src: str):
        """Call rows with no pending chain: their fqn is final. A row that has a chain is settled later by the
        resolve phase (the fqn there is only the base type)."""
        ctx = ExtractContext(path="a/X.scala", lines=src.splitlines(), module="root")
        return {u["fqn"] for u in ScalaExtractor().extract(ctx).uses if u.get("kind") == "call" and not u.get("chain")}

    def test_local_builder_chain_is_not_typed_as_builder(self) -> None:
        src = self.DEFS + "class A {\n  def m() = {\n    val x = new B()\n      .setA(1)\n      .build()\n    x.run()\n  }\n}\n"
        self.assertNotIn("B#run", self.bare(src))

    def test_field_builder_chain_is_not_typed_as_builder(self) -> None:
        src = self.DEFS + "class A {\n  val x = new B()\n    .build()\n  def m() = x.run()\n}\n"
        self.assertNotIn("B#run", self.bare(src))

    def test_plain_new_on_its_own_line_still_typed(self) -> None:
        src = self.DEFS + "class A {\n  def m() = {\n    val x = new C\n    x.run()\n  }\n}\n"
        self.assertIn("C#run", calls(src))


if __name__ == "__main__":
    unittest.main()
