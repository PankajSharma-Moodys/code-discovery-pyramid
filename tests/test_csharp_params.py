"""X4: C# parameters on method/ctor/primary-constructor defines (EXTRACTION_METRICS G1).
Reference: ECMA-334 C# spec, "Methods > Method parameters" (value, ref, out, in, params; this on extension
methods; optional parameters with default values) and "Classes > Instance constructors" / records (primary
constructors, C# 12). Recalled from memory, not fetched in this session. Lambdas and local functions are
expressions/statements, not members, so they get no define and no params."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cdp.lang.base import ExtractContext
from cdp.lang.csharp import CSharpExtractor


def defs(src: str) -> dict:
    facts = CSharpExtractor().extract(ExtractContext(path="A.cs", lines=src.splitlines(), module="root"))
    return {d["fqn"]: d for d in facts.defines}


SRC = """namespace N;
public class C<T>
{
    public void Modifiers(ref int a, out string b, in long c, params object[] rest) { b = null; }
    public static int Ext(this string s, int n = 3, string d = "a,b", Dictionary<string, int> m = null) => n;
    public C(int x, [Required] string name, [A, B(1)] T value = default) { }
    public (int, string) Tuple((int a, int b) pair, List<(string, int)> items) => default;
    public void Generic<U>(U u, Func<U, T> f, int[] arr, int? maybe) { }
    public void None() { }
    public void Local(int k)
    {
        int Inner(int z) => z;
        Func<int, int> l = q => q;
    }
    public void Multi(
        int a,
        int b)
    { }
    public ref readonly int RefRo(scoped ref readonly int x, ref readonly int y) => ref y;
}
public record R(int Id, string Name = "n", [property: Key] long Tag = 0);
public class P(int size, string label) { }
public interface I { void Sig(string a, int b); }
"""


class ParamsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = defs(SRC)

    def params(self, fqn):
        return self.d[fqn]["params"]

    def test_modifiers(self):
        ps = self.params("N.C#Modifiers")
        self.assertEqual([p["name"] for p in ps], ["a", "b", "c", "rest"])
        self.assertEqual([p.get("modifier") for p in ps], ["ref", "out", "in", "params"])
        self.assertEqual(ps[3]["type"], "object[]")

    def test_extension_and_defaults(self):
        ps = self.params("N.C#Ext")
        self.assertEqual([p["name"] for p in ps], ["s", "n", "d", "m"])
        self.assertEqual(ps[0]["modifier"], "this")
        self.assertEqual(ps[1]["default"], "3")
        self.assertEqual(ps[2]["default"], '"a,b"')
        self.assertEqual(ps[3]["default"], "null")

    def test_ctor_parameter_attributes(self):
        ps = self.params("N.C#<init>")
        self.assertEqual([p["name"] for p in ps], ["x", "name", "value"])
        self.assertEqual([a["name"] for a in ps[1]["annotations"]], ["Required"])
        self.assertEqual([a["name"] for a in ps[2]["annotations"]], ["A", "B"])
        self.assertNotIn("annotations", ps[0])
        self.assertEqual(ps[2]["default"], "default")

    def test_tuples_generics_nullable(self):
        self.assertEqual([p["name"] for p in self.params("N.C#Tuple")], ["pair", "items"])
        ps = self.params("N.C#Generic")
        self.assertEqual([p["name"] for p in ps], ["u", "f", "arr", "maybe"])

    def test_no_params_key_without_parameters(self):
        self.assertNotIn("params", self.d["N.C#None"])

    def test_local_function_and_lambda_not_params(self):
        self.assertEqual([p["name"] for p in self.params("N.C#Local")], ["k"])

    def test_multiline_and_ref_readonly(self):
        self.assertEqual([p["name"] for p in self.params("N.C#Multi")], ["a", "b"])
        ps = self.params("N.C#RefRo")
        self.assertEqual([p["name"] for p in ps], ["x", "y"])
        self.assertEqual(ps[0]["modifier"], "scoped ref readonly")

    def test_primary_constructors(self):
        for fqn, names in (("N.R#<init>", ["Id", "Name", "Tag"]), ("N.P#<init>", ["size", "label"])):
            self.assertEqual([p["name"] for p in self.params(fqn)], names)
        self.assertEqual(self.params("N.R#<init>")[1]["default"], '"n"')
        self.assertEqual(self.params("N.R#<init>")[2]["annotations"][0]["name"], "Key")

    def test_interface_member(self):
        self.assertEqual([p["name"] for p in self.params("N.I#Sig")], ["a", "b"])


if __name__ == "__main__":
    unittest.main()
