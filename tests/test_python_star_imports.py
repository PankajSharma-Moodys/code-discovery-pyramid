"""`from X import *` in Python: a name the importer does not bind itself is looked up in X when X is a
module of the repository (its `__all__`, else its public names). Outside modules, a literal-free
`__all__`, or two suppliers settle nothing. Interpreter-independent: no stdlib module is star-imported."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from helpers import Pipeline
from test_java_resolution import inline_repo

FILES = {
    "pkg/__init__.py": "from pkg.base import *\n\nown = 1\n",
    "pkg/base.py": (
        "import json\n\nclass Plugin:\n    def run(self):\n        pass\n\n"
        "class _Hidden:\n    pass\n\ndef helper():\n    pass\n"
    ),
    "pkg/listed.py": "__all__ = ['Shown']\n\nclass Shown:\n    pass\n\nclass NotListed:\n    pass\n",
    "pkg/dyn.py": "__all__ = ['A'] + ['B']\n\nclass A:\n    pass\n",
    "pkg/one.py": "class Dup:\n    pass\n\nclass OnlyOne:\n    pass\n",
    "pkg/two.py": "class Dup:\n    pass\n",
    "pkg/chain.py": "from pkg.base import *\n",
    "pkg/user.py": (
        "from pkg.base import *\nfrom pkg.listed import *\n\n"
        "class Sub(Plugin):\n    pass\n\ndef go():\n    helper()\n    NotListed()\n    _Hidden()\n    Shown()\n"
    ),
    "pkg/viaouter.py": "from pkg.chain import *\n\ndef go():\n    helper()\n",
    "pkg/consumer.py": "from pkg import Plugin\n\nclass C(Plugin):\n    pass\n",
    "pkg/dupuser.py": "from pkg.one import *\nfrom pkg.two import *\n\ndef go():\n    Dup()\n    OnlyOne()\n",
    "pkg/dynuser.py": "from pkg.dyn import *\n\ndef go():\n    A()\n",
    "pkg/extuser.py": "from pkg.base import *\nfrom somelib import *\n\ndef go():\n    helper()\n",
    "pkg/shadow.py": "from pkg.base import *\n\ndef helper():\n    pass\n\ndef go():\n    helper()\n",
    "pkg/local.py": "from pkg.base import *\n\ndef go(Plugin):\n    Plugin()\n",
    "pkg/cycle_a.py": "from pkg.cycle_b import *\n\nclass CA:\n    pass\n",
    "pkg/cycle_b.py": "from pkg.cycle_a import *\n\nclass CB:\n    pass\n\ndef go():\n    CA()\n    Missing()\n",
}


class StarImportsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.p = Pipeline(inline_repo(Path(cls.tmp.name), FILES))
        cls.rows = [r for r in cls.p.xref["uses"] if r.get("kind")]

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def targets(self, file, line=None):
        return {r["fqn"] for r in self.rows if r["from_file"] == file and (line is None or r["anchor"]["line"] == line)}

    def test_local_star_name_resolves_to_its_definition(self):
        got = self.targets("pkg/user.py", 4)
        self.assertTrue(any(f.endswith("pkg.base.Plugin") for f in got), got)

    def test_function_and_all_filter(self):
        got = self.targets("pkg/user.py")
        self.assertTrue(any(f.endswith("pkg.base#helper") for f in got), got)
        self.assertTrue(any(f.endswith("pkg.listed.Shown") for f in got), got)
        self.assertFalse(any(f.endswith("NotListed") for f in got), got)    # outside __all__
        self.assertFalse(any(f.endswith("_Hidden") for f in got), got)      # underscore, no __all__

    def test_reexport_through_a_starring_package(self):
        got = self.targets("pkg/consumer.py")
        self.assertTrue(any(f.endswith("pkg.base.Plugin") for f in got), got)

    def test_chained_star(self):
        self.assertTrue(any(f.endswith("pkg.base#helper") for f in self.targets("pkg/viaouter.py")))

    def test_two_suppliers_settle_nothing_but_unique_name_resolves(self):
        got = self.targets("pkg/dupuser.py")
        self.assertFalse(any("Dup" in f for f in got), got)
        self.assertTrue(any(f.endswith("OnlyOne") for f in got), got)

    def test_dynamic_all_settles_nothing(self):
        self.assertFalse(any(f.endswith(".A") for f in self.targets("pkg/dynuser.py")))

    def test_external_star_blocks_every_name(self):
        self.assertFalse(any("helper" in f for f in self.targets("pkg/extuser.py")))

    def test_own_binding_wins(self):
        got = self.targets("pkg/shadow.py")
        self.assertTrue(any(f.endswith("pkg.shadow#helper") for f in got), got)
        self.assertFalse(any(f.endswith("pkg.base#helper") for f in got), got)

    def test_parameter_shadows_star(self):
        self.assertFalse(any(f.endswith("pkg.base.Plugin") for f in self.targets("pkg/local.py", 4)))

    def test_star_cycle_terminates(self):
        got = self.targets("pkg/cycle_b.py")
        self.assertTrue(any(f.endswith("cycle_a.CA") for f in got), got)
        self.assertFalse(any("Missing" in f for f in got), got)


if __name__ == "__main__":
    unittest.main()
