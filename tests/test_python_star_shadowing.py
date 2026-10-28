"""A name bound locally never falls through to a `from X import *` name. Interpreter-version independent
(the sources are parsed, never run); `match` needs the Python >= 3.10 floor."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from helpers import Pipeline
from test_java_resolution import inline_repo

S = "from pkg.base import *\n\n"
FILES = {
    "pkg/__init__.py": "",
    "pkg/base.py": "class Plugin:\n    pass\n\ndef helper():\n    pass\n",
    # control: nothing shadows
    "pkg/ctl.py": S + "def go():\n    helper()\n",
    # (a) walrus inside comprehension / lambda binds in the enclosing function
    "pkg/walrus_comp.py": S + "def go(xs):\n    [helper for xs_ in xs if (helper := xs_)]\n    helper()\n",
    "pkg/walrus_lambda.py": S + "def go():\n    f = lambda: (helper := 1)\n    helper()\n",
    # (b) module-level with / except / walrus / match
    "pkg/m_with.py": S + "with open('f') as helper:\n    pass\n\ndef go():\n    helper()\n",
    "pkg/m_exc.py": S + "try:\n    pass\nexcept Exception as helper:\n    pass\n\ndef go():\n    helper()\n",
    "pkg/m_walrus.py": S + "if (helper := 1):\n    pass\n\ndef go():\n    helper()\n",
    "pkg/m_match.py": S + "match 1:\n    case [*helper]:\n        pass\n\ndef go():\n    helper()\n",
    # (c) match captures in a function
    "pkg/f_as.py": S + "def go(v):\n    match v:\n        case int() as helper:\n            helper()\n",
    "pkg/f_star.py": S + "def go(v):\n    match v:\n        case [1, *helper]:\n            helper()\n",
    "pkg/f_map.py": S + "def go(v):\n    match v:\n        case {'a': 1, **helper}:\n            helper()\n",
    # (d) global declared in a function
    "pkg/glob.py": S + "def setup():\n    global helper\n    helper = 1\n\ndef go():\n    helper()\n",
    # comprehension / genexp / lambda variables shadow only inside the expression
    "pkg/comp.py": S + "def go(xs):\n    [helper() for helper in xs]\n    helper()\n",
    "pkg/gen.py": S + "def go(xs):\n    list(helper() for helper in xs)\n    helper()\n",
    "pkg/lam.py": S + "def go():\n    f = lambda helper: helper()\n    helper()\n",
}


class StarShadowingTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.p = Pipeline(inline_repo(Path(cls.tmp.name), FILES))
        cls.rows = [r for r in cls.p.xref["uses"] if r.get("kind")]

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def hits(self, name, line=None):
        return [r for r in self.rows if r["from_file"] == "pkg/%s.py" % name
                and r["fqn"].endswith("pkg.base#helper") and (line is None or r["anchor"]["line"] == line)]

    def shadowed(self, name):
        self.assertEqual(self.hits(name), [], name)

    def test_control_resolves(self):
        self.assertTrue(self.hits("ctl"))

    def test_walrus_in_comprehension_and_lambda(self):
        self.shadowed("walrus_comp")
        # PEP 572: a walrus inside a lambda binds in the lambda, so the outer `helper()` stays the star name
        self.assertTrue(self.hits("walrus_lambda"))

    def test_module_level_binders(self):
        for n in ("m_with", "m_exc", "m_walrus", "m_match"):
            self.shadowed(n)

    def test_match_captures_in_functions(self):
        for n in ("f_as", "f_star", "f_map"):
            self.shadowed(n)

    def test_global_declared_in_function(self):
        self.shadowed("glob")

    def test_comprehension_genexp_lambda_do_not_leak(self):
        # inside: shadowed; the trailing `helper()` (line 5) is outside and still the star name
        self.assertTrue(self.hits("comp", 5))
        self.assertFalse(self.hits("comp", 4))
        self.assertTrue(self.hits("gen", 5))
        self.assertFalse(self.hits("gen", 4))
        self.assertTrue(self.hits("lam", 5))
        self.assertFalse(self.hits("lam", 4))


if __name__ == "__main__":
    unittest.main()
