"""Test-double factories (`mock[T]`, `spy[T]`, `stub[T]`, `mock(classOf[T])`) type the local or field as T."""

from __future__ import annotations

import unittest

from helpers import SKILL_ROOT  # noqa: F401  (sets sys.path)

from cdp.lang.base import ExtractContext
from cdp.lang.scala import ScalaExtractor

DEFS = "package p\nclass Repo { def save(x: Int) = 1 }\n"


def calls(src: str):
    ctx = ExtractContext(path="a/X.scala", lines=src.splitlines(), module="root")
    return {u["fqn"] for u in ScalaExtractor().extract(ctx).uses if u.get("kind") == "call"}


class MockFactoryTest(unittest.TestCase):
    INITS = ("mock[Repo]", "spy[Repo]", "stub[Repo]", "mock[Repo](withSettings().lenient())", "mock[Repo](\"n\")",
             "mock(classOf[Repo])", "Mockito.mock(classOf[Repo])", "MockitoSugar.mock[Repo]")

    def test_def_local(self) -> None:
        for init in self.INITS:
            for kw in ("val", "var", "lazy val"):
                src = DEFS + f"class A {{ def m() = {{ {kw} r = {init}\n r.save(1) }} }}\n"
                self.assertIn("p.Repo#save", calls(src), (kw, init))

    def test_field_used_in_later_block(self) -> None:
        for init in self.INITS:
            src = DEFS + f"class A {{\n  val r = {init}\n  it should \"x\" in {{\n    r.save(1)\n  }}\n}}\n"
            self.assertIn("p.Repo#save", calls(src), init)

    def test_template_level_local_in_closure(self) -> None:
        src = DEFS + "class A {\n  \"x\" should \"y\" in {\n    val r = mock[Repo]\n    r.save(1)\n  }\n}\n"
        self.assertIn("p.Repo#save", calls(src))

    def test_generic_arg(self) -> None:
        src = "package p\nclass Chain[X] { def run() = 1 }\nclass A { val c = mock[Chain[Int]]; def m() = c.run() }\n"
        self.assertIn("p.Chain#run", calls(src))

    def test_not_guessed(self) -> None:
        for init in ("mock", "mock[Repo].other()", "mockIt[Repo]", "mock(x)"):
            src = DEFS + f"class A {{ val r = {init}; def m() = r.save(1) }}\n"
            self.assertNotIn("p.Repo#save", calls(src), init)


if __name__ == "__main__":
    unittest.main()
