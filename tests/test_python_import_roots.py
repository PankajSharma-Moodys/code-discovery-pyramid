"""Module-level Python imports are written against an import root (a `sys.path` entry), not
the repo root: `src/` layouts and PEP 420 namespace portions must still resolve."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from helpers import Pipeline
from test_java_resolution import inline_repo

from cdp.pytypes import _import_aliases


def cls(name):
    return f"class {name}:\n    pass\n"


FILES = {
    # src layout; `core` has no __init__.py (namespace portion inside a regular package)
    "src/app/__init__.py": "",
    "src/app/models.py": cls("Model"),
    "src/app/core/store.py": cls("Store"),
    "src/app/logging.py": cls("Shadow"),                 # same name as a stdlib module
    "src/app/sub/__init__.py": "",
    "src/app/sub/deep/inner.py": cls("Inner"),
    "src/app/main.py": (
        "from app.models import Model\nfrom app.core.store import Store\nfrom app.sub.deep import inner\n"
        "import logging\nimport logging.config\nfrom app import models\nimport requests.adapters\n"
        "from . import models as rel\nfrom .core.store import Store as S2\nimport nothere.thing\n"
    ),
    # pure namespace package, no __init__.py anywhere
    "libs/ns/part/thing.py": cls("Thing"),
    "libs/use.py": "from ns.part.thing import Thing\nimport ns.part.missing\n",
    # flat layout
    "flat/__init__.py": "",
    "flat/mod.py": cls("Flat"),
    "flat/user.py": "from flat.mod import Flat\n",
}


class ImportRootsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls_):
        cls_.tmp = tempfile.TemporaryDirectory()
        cls_.p = Pipeline(inline_repo(Path(cls_.tmp.name), FILES))
        cls_.rows = [r for r in cls_.p.xref["uses"] if r["from_file"].endswith(".py") and not r.get("kind")]

    @classmethod
    def tearDownClass(cls_):
        cls_.tmp.cleanup()

    def status(self, fqn, file):
        got = {r["resolved"] for r in self.rows if r["fqn"] == fqn and r["from_file"] == file}
        self.assertTrue(got, f"no row for {fqn}")
        return got

    def test_src_layout(self):
        for fqn in ("app.models",):
            self.assertLessEqual(self.status(fqn, "src/app/main.py"), {"local", "matched"}, fqn)

    def test_namespace_portion_inside_package(self):
        self.assertLessEqual(self.status("app.core.store", "src/app/main.py"), {"local", "matched"})
        self.assertLessEqual(self.status("app.sub.deep", "src/app/main.py"), {"local", "matched"})

    def test_pure_namespace_package(self):
        self.assertLessEqual(self.status("ns.part.thing", "libs/use.py"), {"local", "matched"})

    def test_relative_import_keeps_path_based_name(self):
        self.assertLessEqual(self.status("src.app.core.store", "src/app/main.py"), {"local", "matched"})

    def test_flat_layout_unchanged(self):
        self.assertLessEqual(self.status("flat.mod", "flat/user.py"), {"local", "matched"})

    def test_stdlib_name_equal_to_module_stays_third_party(self):
        self.assertEqual({"third_party"}, self.status("logging", "src/app/main.py"))
        self.assertNotIn("local", self.status("logging.config", "src/app/main.py"))

    def test_external_and_absent_names_do_not_resolve_locally(self):
        self.assertNotIn("local", self.status("requests.adapters", "src/app/main.py"))
        self.assertNotIn("local", self.status("nothere.thing", "src/app/main.py"))
        self.assertNotIn("local", self.status("ns.part.missing", "libs/use.py"))


class AliasTest(unittest.TestCase):
    def aliases(self, *paths):
        mods = {p[:-3].replace("/", ".").removesuffix(".__init__") for p in paths}
        return _import_aliases(mods, {}, list(paths))

    def test_root_is_directory_outside_any_package(self):
        a = self.aliases("src/pkg/__init__.py", "src/pkg/m.py", "src/pkg/ns/x.py")
        self.assertEqual("src.pkg.m", a["pkg.m"])
        self.assertEqual("src.pkg.ns.x", a["pkg.ns.x"])
        self.assertNotIn("m", a)                       # inside a package: not a root
        self.assertNotIn("ns.x", a)

    def test_regular_package_beats_namespace_portion(self):
        a = self.aliases("a/util/__init__.py", "a/util/f.py", "b/util/g.py")
        self.assertEqual("a.util.f", a["util.f"])
        self.assertNotIn("util.g", a)                  # `util` is the regular package in a/

    def test_two_regular_claims_are_ambiguous(self):
        a = self.aliases("a/util/__init__.py", "b/util/__init__.py", "a/util/f.py")
        self.assertNotIn("util.f", a)

    def test_stdlib_guard_uses_the_given_list(self):
        paths = ["src/zlibx/__init__.py", "src/zlibx/x.py"]
        mods = {"src.zlibx", "src.zlibx.x"}
        self.assertIn("zlibx.x", _import_aliases(mods, {}, paths, frozenset()))
        self.assertNotIn("zlibx.x", _import_aliases(mods, {}, paths, frozenset({"zlibx"})))

    def test_stdlib_top_level_never_aliased(self):
        a = self.aliases("src/json/__init__.py", "src/json/x.py")
        self.assertNotIn("json.x", a)

    def test_non_package_script_dir(self):
        a = self.aliases("tests/helpers.py")
        self.assertEqual("tests.helpers", a["helpers"])


if __name__ == "__main__":
    unittest.main()
