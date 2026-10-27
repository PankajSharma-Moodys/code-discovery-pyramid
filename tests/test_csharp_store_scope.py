"""The store settles C# type names exactly like the scan: `symbol_entries` (read from the stored,
unsettled extraction) must equal `build_xref`'s symbols (from `settle_extraction`) for hand-written
C# using aliases, `global using`, generic arity, inherited member types, file-scoped and nested
namespaces and `using static`. SQLite only here: Postgres reads through the same
`ObjectReadMixin._sig_scope`, but its test needs a server (CDP_TEST_POSTGRES_DSN)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import Pipeline
from test_overload_sigs import _repo

from cdp.query.store import Store
from cdp.store import SqliteStore

ROOT = Path(__file__).resolve().parent.parent

FILES = {
    "Lib/Types.cs": "namespace Co.Lib;\npublic class Widget {}\npublic class Box<T> {}\npublic class Pair<T> {}\n"
                    "public static class Helpers { public class Nested {} }\npublic class BaseSvc { public class Inner {} }\n",
    "Lib/Other.cs": "namespace Co.Other;\npublic class Widget {}\npublic class Gadget {}\npublic class Pair<K,V> {}\n",
    "App/Globals.cs": "global using Co.Lib;\n",
    "App/UsesGlobal.cs": "namespace Co.App;\npublic class G { public Widget W() { return null; } public Box<int> B() { return null; } }\n",
    "App/Alias.cs": "using Gd = Co.Other.Gadget;\nusing L = Co.Lib;\nnamespace Co.App\n{\n"
                    "    public class A { public Gd Make() { return null; } public Gadget Make2() { return null; } }\n}\n",
    "App/Arity.cs": "using Co.Lib;\nusing Co.Other;\nnamespace Co.App;\n"
                    "public class Ar { public Pair<int,int> Two() { return null; } public Pair<int> One() { return null; } }\n",
    "App/Bases.cs": "using Co.Lib;\nnamespace Co.App {\n  public class Derived : BaseSvc { public Inner Get() { return null; } }\n"
                    "  public class Deeper : Derived { public Inner Get2() { return null; } }\n}\n",
    "App/Static.cs": "using static Co.Lib.Helpers;\nnamespace Co.App { public class St { public Nested N() { return null; } } }\n",
    "App/Nested.cs": "namespace Co { namespace App { namespace Deep {\n"
                     "  public class Dp { public Widget W() { return null; } public Co.Other.Gadget G() { return null; } }\n} } }\n",
}


class StoreMatchesScanTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        repo = _repo(Path(cls.tmp.name) / "repo", FILES)
        cls.scan = Pipeline(repo).xref["symbols"]
        home = Path(cls.tmp.name) / "home"
        subprocess.run([sys.executable, str(ROOT / "run.py"), "scan", "--repo", str(repo), "--quiet", "--no-docs"],
                       check=True, capture_output=True, env=dict(os.environ, CDP_HOME=str(home)))
        cls.store = Store(SqliteStore(home / "index.db")).backend
        cls.got = cls.store.symbol_entries(sorted(cls.scan))

    def same(self, fqn):
        self.assertIn(fqn, self.got)
        self.assertEqual(json.dumps(self.got[fqn], sort_keys=True), json.dumps(self.scan[fqn], sort_keys=True))
        return self.got[fqn]

    def test_every_symbol(self):
        self.assertEqual([k for k in self.scan if self.got.get(k) != self.scan[k]], [])

    def test_global_using_from_another_file(self):
        self.assertEqual(self.same("Co.App.G#W")["ret"], "Co.Lib.Widget")

    def test_alias_imports_nothing_and_names_itself(self):
        self.same("Co.App.A#Make")
        self.same("Co.App.A#Make2")

    def test_generic_arity(self):
        self.assertEqual(self.same("Co.App.Ar#Two")["ret"], "Co.Other.Pair<int,int>")
        self.assertEqual(self.same("Co.App.Ar#One")["ret"], "Co.Lib.Pair<int>")

    def test_inherited_member_type(self):
        self.assertEqual(self.same("Co.App.Derived#Get")["ret"], "Co.Lib.BaseSvc.Inner")
        self.assertEqual(self.same("Co.App.Deeper#Get2")["ret"], "Co.Lib.BaseSvc.Inner")

    def test_using_static(self):
        self.same("Co.App.St#N")

    def test_nested_namespaces(self):
        self.same("Co.App.Deep.Dp#W")
        self.same("Co.App.Deep.Dp#G")

    def test_file_scoped_namespace(self):
        self.same("Co.App.Ar#One")


if __name__ == "__main__":
    unittest.main()
