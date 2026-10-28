"""`wildcard:<source>` file signals (only when a name was left unsettled by a wildcard) and the
`query symbol` not-found note built from them."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from helpers import Pipeline
from cdp.query.common import visible_signals
from test_java_resolution import inline_repo

FILES = {
    "pkg/__init__.py": "",
    "pkg/base.py": "def helper():\n    pass\n",
    "pkg/ok.py": "from pkg.base import *\n\ndef go():\n    helper()\n    print(1)\n",
    "pkg/ext.py": "from pkg.base import *\nfrom outside import *\n\ndef go():\n    helper()\n",
    "pkg/ext_unused.py": "from outside import *\n\ndef go():\n    len([])\n",
    "pkg/dyn.py": "from pkg.dynsrc import *\n\ndef go():\n    A()\n",
    "pkg/dynsrc.py": "__all__ = ['A'] + ['B']\n\nclass A:\n    pass\n",
    "pkg/one.py": "class Dup:\n    pass\n",
    "pkg/two.py": "class Dup:\n    pass\n",
    "pkg/dup.py": "from pkg.one import *\nfrom pkg.two import *\n\ndef go():\n    Dup()\n",
    "src/main/java/c/Other.java": "package c;\npublic class Other {}\n",
    "src/main/java/a/Use.java": ("package a;\nimport c.*;\nimport java.util.*;\npublic class Use {\n"
                                 "  void go(){ Missing m = new Missing(); m.run(); Other o = null; o.x(); }\n}\n"),
    "src/main/java/a/Fine.java": "package a;\nimport c.*;\npublic class Fine {\n  void go(){ Other o = null; o.x(); }\n}\n",
}


class WildcardSignalsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.p = Pipeline(inline_repo(Path(cls.tmp.name), FILES))
        cls.files = cls.p.extraction["files"]

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def sig(self, rel):
        return sorted(s for s in self.files[rel]["signals"] if s.startswith("wildcard:"))

    def test_python_only_when_a_name_was_left_unsettled(self):
        self.assertEqual(self.sig("pkg/ok.py"), [])                    # settled; `print` is a builtin
        self.assertEqual(self.sig("pkg/ext.py"), ["wildcard:outside"])
        self.assertEqual(self.sig("pkg/ext_unused.py"), [])            # only builtins used
        self.assertEqual(self.sig("pkg/dyn.py"), ["wildcard:pkg.dynsrc"])
        self.assertEqual(self.sig("pkg/dup.py"), ["wildcard:pkg.one", "wildcard:pkg.two"])

    def test_java_unmatched_name_marks_repo_wildcard_only(self):
        self.assertEqual(self.sig("src/main/java/a/Use.java"), ["wildcard:c"])    # not java.util
        self.assertEqual(self.sig("src/main/java/a/Fine.java"), [])

    def test_signal_stays_visible(self):
        self.assertEqual(visible_signals(["guess:x", "wildcard:c"]), ["wildcard:c"])


if __name__ == "__main__":
    unittest.main()
