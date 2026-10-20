"""Bug C (PLAN.md M3): statements in a class/object/trait template body -- ScalaTest DSL closures,
bare calls, `before { .. }` -- are scanned and their rows attributed to the type's initialiser."""

from __future__ import annotations

import unittest

from helpers import SKILL_ROOT  # noqa: F401  (sets sys.path)

from cdp.lang.base import ExtractContext
from cdp.lang.scala import ScalaExtractor

SPEC = """package p

import q.Engine

class EngineSpec extends AnyFlatSpec {
  behavior of "Engine"

  before {
    Engine.reset()
  }

  it should "start" in {
    val e = new Engine()
    e.start()
  }

  "an engine" should "stop" in {
    Engine.halt(1)
  }

  test("runs") {
    Engine.run()
  }

  type Alias = Engine
}

object Boot {
  Engine.boot()
}
"""


def calls(src: str):
    ctx = ExtractContext(path="src/test/scala/p/EngineSpec.scala", lines=src.splitlines(), module="root")
    facts = ScalaExtractor().extract(ctx)
    return facts, [u for u in facts.uses if u.get("kind") == "call"]


class TemplateBodyTest(unittest.TestCase):
    def test_dsl_closures_yield_calls_from_the_initialiser(self) -> None:
        _, rows = calls(SPEC)
        got = {(u["fqn"], u["anchor"]["line"]): u["from_symbol"] for u in rows if u["fqn"].startswith("q.")}
        self.assertEqual(got.get(("q.Engine#reset", 9)), "p.EngineSpec#<init>")      # before { .. }
        self.assertEqual(got.get(("q.Engine#start", 14)), "p.EngineSpec#<init>")     # it should .. in { .. }
        self.assertEqual(got.get(("q.Engine#<init>", 13)), "p.EngineSpec#<init>")    # new inside the closure
        self.assertEqual(got.get(("q.Engine#halt", 18)), "p.EngineSpec#<init>")      # "x" should "y" in { .. }
        self.assertEqual(got.get(("q.Engine#run", 22)), "p.EngineSpec#<init>")       # test("..") { .. }

    def test_object_body_statement_is_static_initialiser(self) -> None:
        _, rows = calls(SPEC)
        self.assertIn(("q.Engine#boot", "p.Boot#<clinit>"),
                      {(u["fqn"], u["from_symbol"]) for u in rows})

    def test_no_define_rows_for_statements(self) -> None:
        facts, _ = calls(SPEC)       # only the implicit primary constructor, on the class line
        self.assertEqual([(d["fqn"], d["anchor"]["line"]) for d in facts.defines if "#" in d["fqn"]],
                         [("p.EngineSpec#<init>", 5)])

    def test_type_alias_is_not_scanned(self) -> None:
        _, rows = calls(SPEC)
        self.assertFalse([u for u in rows if u["anchor"]["line"] == 25])


if __name__ == "__main__":
    unittest.main()
