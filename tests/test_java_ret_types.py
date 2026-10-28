"""Java `ret` / `ftype` per JLS 8.4.5 (void is no type), 4.2 (primitives), 10 (arrays), 8.4.4 (generic methods):
every declared return and field type is emitted; `void` is the sentinel `<none>`, constructors have no `ret`,
and the sentinel / primitives are terminal in chain inference."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from helpers import Pipeline
from test_overload_sigs import _repo

from cdp.jtypes import TypeIndex
from cdp.lang.java_types import NO_RETURN

FILES = {
    "src/p/Box.java": (
        "package p;\nimport java.util.List;\n"
        "public class Box<T> {\n"
        "  private int count;\n  protected long[] ids;\n  String name;\n  List<T> items;\n  Box other;\n"
        "  public Box() {}\n"
        "  private Box(int n) {}\n"
        "  public void run() {}\n"
        "  public int size() { return 0; }\n"
        "  public boolean[] flags() { return null; }\n"
        "  public String label() { return \"\"; }\n"
        "  public <U> U pick(U u) { return u; }\n"
        "  public <U extends Box> List<U> all() { return null; }\n"
        "  public Box self() { return this; }\n"
        "  public void many(String... xs) {}\n"
        "  public @Deprecated int old() { return 1; }\n"
        "  public void use() { self().run().x(); self().size().y(); }\n"
        "}\n"),
    "src/p/Api.java": (
        "package p;\npublic interface Api {\n"
        "  void ping();\n  int count();\n  default void hello() {}\n  static char c() { return 'c'; }\n}\n"),
    "src/p/Abs.java": "package p;\npublic abstract class Abs { abstract void go(); abstract double d(); }\n",
}


class JavaRetTypesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        cls.p = Pipeline(_repo(Path(cls.tmp.name), FILES))
        cls.defs = {}
        for d in cls.p.extraction["defines"]:
            cls.defs.setdefault(d["fqn"], []).append(d)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def ret(self, fqn):
        return self.defs[fqn][0].get("ret")

    def test_void_is_sentinel(self):
        for f in ("p.Box#run", "p.Box#many", "p.Api#ping", "p.Api#hello", "p.Abs#go"):
            self.assertEqual(self.ret(f), NO_RETURN, f)
        self.assertNotRegex(NO_RETURN, r"^[A-Za-z_$]")

    def test_primitives_and_builtins_are_emitted(self):
        self.assertEqual(self.ret("p.Box#size"), "int")
        self.assertEqual(self.ret("p.Api#count"), "int")
        self.assertEqual(self.ret("p.Api#c"), "char")
        self.assertEqual(self.ret("p.Abs#d"), "double")
        self.assertEqual(self.ret("p.Box#flags"), "boolean[]")
        self.assertEqual(self.ret("p.Box#old"), "int")
        self.assertTrue(self.ret("p.Box#label").endswith("String"), self.ret("p.Box#label"))

    def test_generic_and_class_returns(self):
        self.assertEqual(self.ret("p.Box#pick"), "~U")
        self.assertEqual(self.ret("p.Box#all"), "List<~U>")
        self.assertEqual(self.ret("p.Box#self"), "p.Box")

    def test_constructors_have_no_ret(self):
        for d in self.defs["p.Box#<init>"]:
            self.assertNotIn("ret", d)

    def test_field_types(self):
        f = lambda n: self.defs["p.Box." + n][0].get("ftype")
        self.assertEqual(f("count"), "int")
        self.assertEqual(f("ids"), "long[]")
        self.assertTrue(f("name").endswith("String"))
        self.assertEqual(f("items"), "List<~T>")
        self.assertEqual(f("other"), "p.Box")

    def test_resolved_symbols_keep_sentinel_and_primitives(self):
        s = self.p.xref["symbols"]
        self.assertEqual(s["p.Box#run"]["ret"], NO_RETURN)
        self.assertEqual(s["p.Box#size"]["ret"], "int")
        self.assertEqual(s["p.Box.count"]["ftype"], "int")

    def test_no_phantom_symbols(self):
        names = set(self.p.xref["symbols"])
        for bad in ("p.none", "p.int", "p.void", "p.boolean", "p.<none>", "none", "int"):
            self.assertNotIn(bad, names)

    def test_chain_terminates_on_sentinel_and_primitive(self):
        # a repo class named like the sentinel's letters must not be reached through `<none>`
        ti = TypeIndex(self.p.extraction, self.p.xref["symbols"])
        for t in (NO_RETURN, "int", "boolean[]", "void"):
            self.assertIsNone(ti.step(t, "m:run"), t)
            self.assertEqual(ti.canon(t, "src/p/Box.java"), t)
        self.assertEqual(ti.step("p.Box", "m:self"), "p.Box")
        self.assertEqual(ti.step("p.Box", "m:run"), NO_RETURN)
        self.assertIsNone(ti.walk("p.Box", ["m:run", "m:x"]))
        self.assertIsNone(ti.walk("p.Box", ["m:size", "m:y"]))
        self.assertIsNone(ti.field_type("p.Box", "count") and ti.step(ti.field_type("p.Box", "count"), "m:z"))


class SentinelClassNameTest(unittest.TestCase):
    def test_class_named_none_is_not_reached(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Pipeline(_repo(Path(tmp), {
                "src/q/none.java": "package q;\npublic class none { public int m() { return 1; } }\n",
                "src/q/A.java": "package q;\npublic class A { public void v() {} public none n() { return null; } }\n"}))
            ti = TypeIndex(p.extraction, p.xref["symbols"])
            self.assertEqual(ti.canon(NO_RETURN, "src/q/A.java"), NO_RETURN)
            self.assertIsNone(ti.step(NO_RETURN, "m:m"))
            self.assertIsNone(ti.walk("q.A", ["m:v", "m:m"]))
            self.assertEqual(ti.walk("q.A", ["m:n", "m:m"]), "int")
