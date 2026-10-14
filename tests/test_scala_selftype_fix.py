"""Self-type clauses at the start of a template body must not swallow the members."""

from __future__ import annotations

import unittest

from helpers import SKILL_ROOT  # noqa: F401  (sets sys.path)

from cdp.lang.base import ExtractContext
from cdp.lang.scala import ScalaExtractor


def names(src: str):
    ctx = ExtractContext(path="a/X.scala", lines=src.splitlines(), module="root")
    return sorted(d["fqn"] for d in ScalaExtractor().extract(ctx).defines)


class SelfTypeTest(unittest.TestCase):
    def check(self, head: str, one_line: bool = False) -> None:
        sep = " " if one_line else "\n  "
        src = f"package p\ntrait T {{ {head}{sep}def a = 1{'; ' if one_line else chr(10) + '  '}val b = 2\n}}\n"
        self.assertEqual(names(src), ["p.T", "p.T#a", "p.T.b"], head)

    def test_forms(self) -> None:
        for h in ("self: Foo =>", "self: Foo with Bar =>", "this: Foo =>", "self =>", "self: Foo[A] =>",
                  "self: a.b.Foo[A, B] with Bar =>"):
            self.check(h)
            self.check(h, one_line=True)

    def test_lambda_and_case_not_self_type(self) -> None:
        # not self-types: parsed as an ordinary statement, as before the fix
        for first in ("x => foo(x)", "case x => 1"):
            src = f"package p\ntrait T {{\n  {first}\n  def a = 1\n}}\n"
            self.assertEqual(names(src), names(src.replace(first, "foo(1)")), first)


if __name__ == "__main__":
    unittest.main()
