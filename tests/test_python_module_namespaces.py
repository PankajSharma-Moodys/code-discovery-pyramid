"""Every Python module is an importable namespace, whatever it defines; a miss on a module
name never settles on a parent package. Hand-written fixtures only."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from cdp.graph import build_symbol_index, owners_of
from helpers import Pipeline
from test_java_resolution import inline_repo


def extraction(files, defines=(), imports=()):
    """`files`: path -> module; defines/imports: (file, module, fqn[, kind])."""
    return {
        "files": {f: {"language": "python"} for f in files},
        "defines": [{"file": f, "module": m, "fqn": q, "kind": (k[0] if k else "function")}
                    for f, m, q, *k in defines],
        "imports": [{"file": f, "module": m, "fqn": q} for f, m, q in imports],
    }


class IndexTest(unittest.TestCase):
    def owners(self, ex, fqn):
        s, n = build_symbol_index(ex)
        return owners_of(fqn, s, n)

    def test_function_only_module(self):
        ex = extraction(["pkg/svc.py"], [("pkg/svc.py", "m1", "pkg.svc#get")])
        self.assertEqual(["m1"], self.owners(ex, "pkg.svc"))

    def test_constants_only_module(self):
        ex = extraction(["pkg/consts.py"], [("pkg/consts.py", "m1", "pkg.consts.LIMIT", "constant")])
        self.assertEqual(["m1"], self.owners(ex, "pkg.consts"))

    def test_class_module_unchanged(self):
        ex = extraction(["pkg/a.py"], [("pkg/a.py", "m1", "pkg.a.A", "class")])
        self.assertEqual(["m1"], self.owners(ex, "pkg.a"))
        self.assertEqual(["m1"], self.owners(ex, "pkg.a.A"))

    def test_package_init_with_only_imports(self):
        ex = extraction(["pkg/__init__.py", "pkg/x.py"], [("pkg/x.py", "m1", "pkg.x#f")],
                        [("pkg/__init__.py", "m2", "pkg.x")])
        self.assertEqual(["m2"], self.owners(ex, "pkg"))

    def test_empty_init_takes_directory_modules(self):
        ex = extraction(["pkg/__init__.py", "pkg/x.py"], [("pkg/x.py", "m1", "pkg.x#f")])
        self.assertEqual(["m1"], self.owners(ex, "pkg"))

    def test_empty_module_alone_in_directory_is_left_out(self):
        ex = extraction(["solo/__init__.py", "pkg/x.py"], [("pkg/x.py", "m1", "pkg.x#f")])
        self.assertEqual([], self.owners(ex, "solo"))

    def test_non_py_build_file_named_setup_is_a_module(self):
        ex = extraction(["pkg/setup.py", "pkg/x.py"], [("pkg/x.py", "m1", "pkg.x#f")])
        ex["files"]["pkg/setup.py"]["language"] = "build"
        self.assertEqual(["m1"], self.owners(ex, "pkg.setup"))

    def test_missing_module_does_not_attach_to_parent(self):
        ex = extraction(["pkg/svc.py"], [("pkg/svc.py", "m1", "pkg.svc#get")])
        self.assertEqual([], self.owners(ex, "pkg.svc.missing"))
        self.assertEqual([], self.owners(ex, "pkg.missing"))

    def test_parent_not_a_python_module_still_trims(self):
        # a Python class namespace that is not itself a module keeps the old trim
        ex = extraction(["pkg/a.py"], [("pkg/a.py", "m1", "pkg.a.Outer.Inner", "class")])
        self.assertEqual(["m1"], self.owners(ex, "pkg.a.Outer.Missing"))

    def test_symbol_exact_wins_over_module(self):
        # `pkg#helper` is a function of the parent; `pkg.helper` is not a module: no hit
        ex = extraction(["pkg/__init__.py"], [("pkg/__init__.py", "m1", "pkg#helper")])
        s, n = build_symbol_index(ex)
        self.assertEqual(["m1"], owners_of("pkg#helper", s, n))
        self.assertEqual([], owners_of("pkg.helper", s, n))
        self.assertEqual(["m1"], owners_of("pkg", s, n))

    def test_other_languages_keep_trim_and_class_namespaces(self):
        ex = {"files": {}, "defines": [
            {"file": "A.java", "module": "j", "fqn": "acme.Outer", "kind": "class"},
            {"file": "B.cs", "module": "c", "fqn": "Co.Ns.Thing", "kind": "class"}], "imports": []}
        s, n = build_symbol_index(ex)
        self.assertEqual(["j"], owners_of("acme.Outer.Inner", s, n))
        self.assertEqual(["j"], owners_of("acme.*", s, n))
        self.assertEqual(["c"], owners_of("Co.Ns.Other", s, n))

    def test_path_shaped_names_keep_trim(self):
        ex = extraction(["web/__init__.py"], [("web/__init__.py", "m1", "web#f")])
        s, n = build_symbol_index(ex)
        self.assertEqual(["m1"], owners_of("web/missing", s, n))

    def test_index_is_a_plain_dict_for_callers(self):
        _, n = build_symbol_index(extraction(["a.py"], [("a.py", "m", "a#f")]))
        self.assertIsInstance(n, dict)
        self.assertEqual({"a": ["m"]}, dict(n))


FILES = {
    "pkg/__init__.py": "from . import util\nfrom .svc import get\n",
    "pkg/svc.py": "def get():\n    return 1\n",
    "pkg/consts.py": "LIMIT = 3\n",
    "pkg/util.py": "def helper():\n    return 2\n",
    "pkg/sub/__init__.py": "",
    "pkg/sub/leaf.py": "def leaf():\n    return 0\n",
    "pkg/sub/use.py": "from .leaf import leaf\nfrom .. import consts\nfrom ..svc import get\n"
                       "from ..nothing import x\nimport pkg.svc.nope\n",
}


class EndToEndTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.p = Pipeline(inline_repo(Path(cls.tmp.name), FILES))
        cls.rows = {(r["from_file"], r["anchor"]["line"]): r for r in cls.p.xref["uses"]
                    if r.get("kind") is None and r["from_file"].endswith(".py")}

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def outcome(self, file, line):
        r = self.rows[(file, line)]
        return r["fqn"], r["resolved"]

    def test_relative_imports_of_function_and_constant_modules_resolve(self):
        self.assertEqual(("pkg.sub.leaf", "local"), self.outcome("pkg/sub/use.py", 1))
        self.assertEqual(("pkg.svc", "local"), self.outcome("pkg/sub/use.py", 3))
        self.assertEqual(("pkg.svc", "local"), self.outcome("pkg/__init__.py", 2))

    def test_from_dot_import_module(self):
        self.assertEqual(("pkg", "local"), self.outcome("pkg/__init__.py", 1))
        self.assertEqual(("pkg", "local"), self.outcome("pkg/sub/use.py", 2))

    def test_misses_do_not_resolve_to_the_parent(self):
        self.assertEqual("unresolved", self.outcome("pkg/sub/use.py", 4)[1])
        self.assertEqual("unresolved", self.outcome("pkg/sub/use.py", 5)[1])


if __name__ == "__main__":
    unittest.main()
