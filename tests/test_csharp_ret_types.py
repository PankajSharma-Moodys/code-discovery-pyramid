"""C# `ret` / `ftype` per the C# spec (15.6.1 methods, 8.3 predefined types, 8.3.12 nullable, 12.7 tuples, 17.6 ref
returns, 15.11 constructors): every declared return and field type is emitted; `void` is the sentinel `<none>`,
constructors and destructors have no `ret`, and the sentinel / predefined types are terminal in chain inference."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from helpers import Pipeline
from test_overload_sigs import _repo

from cdp.cstypes import CsTypeIndex
from cdp.lang.java_types import NO_RETURN

FILES = {
    "src/Box.cs": (
        "using System;\nusing System.Threading.Tasks;\nusing System.Collections.Generic;\n"
        "namespace P {\n"
        "public class Box<T> {\n"
        "  private int count;\n  protected long[] ids;\n  public string Name;\n  public int? Maybe;\n"
        "  public (int A, string B) Pair;\n  public List<T> Items;\n  public Box Other;\n  public const string Tag = \"t\";\n"
        "  public Box() {}\n"
        "  private Box(int n) {}\n"
        "  ~Box() {}\n"
        "  public void Run() {}\n"
        "  public int Size() { return 0; }\n"
        "  public bool[] Flags() { return null; }\n"
        "  public string Label() => \"\";\n"
        "  public int? Opt() { return null; }\n"
        "  public (int, string) Tup() { return default; }\n"
        "  public async Task Go() { await Task.Delay(1); }\n"
        "  public async Task<int> GoN() { return 1; }\n"
        "  public ref int RefRet() { throw null; }\n"
        "  public unsafe int* Ptr() { return null; }\n"
        "  public T Pick(T t) { return t; }\n"
        "  public Box Self() { return this; }\n"
        "  public static Box operator +(Box a, Box b) { return a; }\n"
        "  partial void Hook();\n"
        "  public void Use() { Self().Run().X(); Self().Size().Y(); void Local() {} }\n"
        "}\n"
        "public record Rec(int Id, string Title);\n"
        "}\n"),
    "src/Api.cs": (
        "namespace P {\npublic interface Api {\n  void Ping();\n  int Count();\n  char C();\n}\n}\n"),
}


class CsRetTypesTest(unittest.TestCase):
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
        for f in ("P.Box#Run", "P.Api#Ping"):
            self.assertEqual(self.ret(f), NO_RETURN, f)
        self.assertNotRegex(NO_RETURN, r"^[A-Za-z_$]")

    def test_predefined_types_are_emitted(self):
        self.assertEqual(self.ret("P.Box#Size"), "int")
        self.assertEqual(self.ret("P.Api#Count"), "int")
        self.assertEqual(self.ret("P.Api#C"), "char")
        self.assertEqual(self.ret("P.Box#Flags"), "bool[]")
        self.assertEqual(self.ret("P.Box#Label"), "string")
        self.assertEqual(self.ret("P.Box#Opt"), "int")      # nullable annotation is not part of the name

    def test_other_return_forms(self):
        self.assertTrue(self.ret("P.Box#Go"), self.defs["P.Box#Go"])
        self.assertIn("Task", self.ret("P.Box#GoN"))
        self.assertTrue(self.ret("P.Box#Tup"))
        self.assertIn("int", self.ret("P.Box#RefRet"))
        self.assertEqual(self.ret("P.Box#Self"), "P.Box")

    def test_constructors_have_no_ret(self):
        for d in self.defs["P.Box#<init>"]:
            self.assertNotIn("ret", d)

    def test_field_types(self):
        f = lambda n: self.defs["P.Box." + n][0].get("ftype")
        self.assertEqual(f("count"), "int")
        self.assertEqual(f("ids"), "long[]")
        self.assertEqual(f("Name"), "string")
        self.assertEqual(f("Tag"), "string")
        self.assertEqual(f("Maybe"), "int")
        self.assertEqual(f("Other"), "P.Box")
        self.assertEqual(self.defs["P.Rec.Id"][0].get("ftype"), "int")

    def test_resolved_symbols_keep_sentinel_and_predefined(self):
        s = self.p.xref["symbols"]
        self.assertEqual(s["P.Box#Run"]["ret"], NO_RETURN)
        self.assertEqual(s["P.Box#Size"]["ret"], "int")
        self.assertEqual(s["P.Box.count"]["ftype"], "int")

    def test_no_phantom_symbols(self):
        names = set(self.p.xref["symbols"])
        for bad in ("P.none", "P.int", "P.void", "P.string", "P.bool", "P.<none>", "none", "int", "string"):
            self.assertNotIn(bad, names)

    def test_chain_terminates_on_sentinel_and_predefined(self):
        ti = CsTypeIndex(self.p.extraction, self.p.xref["symbols"])
        for t in (NO_RETURN, "int", "string", "decimal", "void", "bool[]"):
            self.assertIsNone(ti.step(t, "m:Run"), t)
            self.assertEqual(ti.canon(t, "src/Box.cs"), t)
        self.assertEqual(ti.step("P.Box", "m:Self"), "P.Box")
        self.assertEqual(ti.step("P.Box", "m:Run"), NO_RETURN)
        self.assertIsNone(ti.walk("P.Box", ["m:Run", "m:X"]))
        self.assertIsNone(ti.walk("P.Box", ["m:Size", "m:Y"]))


class SentinelClassNameTest(unittest.TestCase):
    def test_class_named_none_is_not_reached(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Pipeline(_repo(Path(tmp), {
                "src/none.cs": "namespace Q {\npublic class none { public int M() { return 1; } }\n}\n",
                "src/A.cs": "namespace Q {\npublic class A { public void V() {} public none N() { return null; } }\n}\n"}))
            ti = CsTypeIndex(p.extraction, p.xref["symbols"])
            self.assertEqual(ti.canon(NO_RETURN, "src/A.cs"), NO_RETURN)
            self.assertIsNone(ti.step(NO_RETURN, "m:M"))
            self.assertIsNone(ti.walk("Q.A", ["m:V", "m:M"]))
            self.assertEqual(ti.walk("Q.A", ["m:N", "m:M"]), "int")


if __name__ == "__main__":
    unittest.main()
