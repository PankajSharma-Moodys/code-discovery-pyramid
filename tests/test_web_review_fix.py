"""Web fixes found by the PENDING.md grounding pass: regex after `return`, and test files' `<Route>`."""

from __future__ import annotations

import unittest

from helpers import SKILL_ROOT  # noqa: F401  (sets sys.path)

from test_web import edges, facts_of


def _names(facts):
    return [d["fqn"] for d in facts.defines]


class RegexAfterKeywordTest(unittest.TestCase):
    def test_regex_after_return_keeps_later_members(self):
        src = "class Foo {\n  m() { return /[{]/.test('x') }\n  n() { return 1 }\n  o() { return 2 }\n}\n"
        self.assertEqual(_names(facts_of("c.js", src)), ["c.Foo", "c.Foo.m", "c.Foo.n", "c.Foo.o"])

    def test_regex_after_typeof_and_case(self):
        src = "class Foo {\n  m(x) { switch (x) { case /[{]/.test(x): return 1 } }\n  n() { return 1 }\n}\n"
        self.assertEqual(_names(facts_of("c.js", src)), ["c.Foo", "c.Foo.m", "c.Foo.n"])

    def test_division_is_still_division(self):
        src = "class Foo {\n  m(a, b) { return a / b / 2 }\n  n(a) { const half = a / 2; return half }\n  o() { return 1 }\n}\n"
        self.assertEqual(_names(facts_of("c.js", src)), ["c.Foo", "c.Foo.m", "c.Foo.n", "c.Foo.o"])


class TestFileRoutesTest(unittest.TestCase):
    ROUTE = "import {Route} from 'react-router-dom'\nexport const R = () => (<Route path=\"/a\" element={<A/>}/>)\n"

    def test_app_file_emits_ui_route(self):
        self.assertEqual([e["target"] for e in edges(facts_of("src/routes.js", self.ROUTE), "ui_route")], ["ui_route:/a"])

    def test_test_files_do_not(self):
        for path in ("src/a.test.js", "src/__tests__/a.js", "src/a.spec.tsx", "src/test/pages/A.test.js"):
            self.assertEqual(edges(facts_of(path, self.ROUTE), "ui_route"), [], path)


if __name__ == "__main__":
    unittest.main()
