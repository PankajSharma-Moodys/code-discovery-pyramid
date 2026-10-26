"""X2: C# attribute `args` (EXTRACTION_METRICS M2) and `fqn` (M3), in the shape Java and Scala use.
Spec basis: ECMA-334 "Attributes" (positional and named arguments); cited from memory, not fetched.
All inputs are inline snippets."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cdp.lang.base import ExtractContext
from cdp.lang.csharp import CSharpExtractor


def anns(src: str, owner: str = None) -> list:
    facts = CSharpExtractor().extract(ExtractContext(path="A.cs", lines=src.splitlines(), module="root"))
    out = []
    for d in facts.defines:
        if owner is None or d["fqn"] == owner:
            out.extend(d.get("annotations", []))
    return out


def one(attr: str, header: str = "") -> dict:
    return anns("%snamespace N;\n%s\npublic class C { }\n" % (header, attr), "N.C")[0]


def args(attr: str) -> dict:
    return one(attr)["args"]


class ArgsTest(unittest.TestCase):
    def test_no_parens_has_no_args(self):
        self.assertNotIn("args", one("[Serializable]"))

    def test_empty_parens_is_empty_dict(self):
        self.assertEqual(args("[Foo()]"), {})
        self.assertEqual(args("[Foo(  )]"), {})

    def test_positional_and_named(self):
        self.assertEqual(args('[Route("a/b")]'), {"value": "a/b"})
        self.assertEqual(args('[Foo(Name = "x", Count = 3)]'), {"Name": "x", "Count": 3})
        self.assertEqual(args('[Foo("a", 2, Flag = true)]'), {"value": "a", "value_2": 2, "Flag": True})
        self.assertEqual(args('[Foo(name: "x", 1)]'), {"name": "x", "value": 1})

    def test_strings(self):
        self.assertEqual(args('[Foo(@"C:\\dir ""q"" (x)")]'), {"value": 'C:\\dir "q" (x)'})
        self.assertEqual(args('[Foo("a, (b) [c] \\"d\\" \\u0041\\x42")]'), {"value": 'a, (b) [c] "d" AB'})
        self.assertEqual(args('[Foo($"x{y}")]'), {"value": {"text": '$"x{y}"'}})
        self.assertEqual(args('[Foo($"plain {{x}}")]'), {"value": "plain {x}"})
        self.assertEqual(args('[Foo("""raw "q" (x)""")]'), {"value": 'raw "q" (x)'})
        self.assertEqual(args("[Foo('a', '\\n', '\\'')]"), {"value": "a", "value_2": "\n", "value_3": "'"})

    def test_raw_string_multiline_indent(self):
        got = args('[Foo("""\n    line1\n      line2\n    """)]')
        self.assertEqual(got, {"value": "line1\n  line2"})

    def test_numbers_bool_null(self):
        got = args("[Foo(1_000, 0x1F, 0b101, -2, 2.5f, 10UL, 1.5m, true, false, null)]")
        self.assertEqual(got, {"value": 1000, "value_2": 31, "value_3": 5, "value_4": -2, "value_5": 2.5,
                               "value_6": 10, "value_7": 1.5, "value_8": True, "value_9": False,
                               "value_10": {"text": "null"}})

    def test_typeof_nameof(self):
        self.assertEqual(args("[Foo(typeof(Bar))]"), {"value": {"class": "Bar"}})
        self.assertEqual(args("[Foo(typeof(Dictionary<string, int>), T = typeof(Ns.Baz))]"),
                         {"value": {"class": "Dictionary<string,int>"}, "T": {"class": "Ns.Baz"}})
        self.assertEqual(args("[Foo(nameof(Bar))]"), {"value": "Bar"})
        self.assertEqual(args("[Foo(nameof(Ns.Bar.Prop))]"), {"value": "Prop"})

    def test_constants_and_enums(self):
        self.assertEqual(args("[Foo(Consts.Max)]"), {"value": {"ref": "Consts.Max"}})
        self.assertEqual(args("[Foo(E.A | E.B)]"), {"value": {"text": "E.A|E.B"}})
        self.assertEqual(args('[Foo("a" + "b" + 1)]'), {"value": "ab1"})
        self.assertEqual(args('[Foo(Base + "/x")]'), {"value": {"concat": [{"ref": "Base"}, "/x"]}})
        self.assertEqual(args('[Foo(("a" + "b"))]'), {"value": "ab"})
        self.assertEqual(args("[Foo(default(int), (int)x)]"),
                         {"value": {"text": "default(int)"}, "value_2": {"text": "(int)x"}})

    def test_arrays_and_collection_expressions(self):
        self.assertEqual(args('[Foo(new[] { "a", "b" })]'), {"value": ["a", "b"]})
        self.assertEqual(args('[Foo(Tags = new string[] { "a", Ns.B })]'), {"Tags": ["a", {"ref": "Ns.B"}]})
        self.assertEqual(args("[Foo(new int[2] { 1, 2 })]"), {"value": [1, 2]})
        self.assertEqual(args("[Foo(new[] { })]"), {"value": []})
        self.assertEqual(args('[Foo(Names = ["a", "b,c"], N = [1, [2, 3]])]'),
                         {"Names": ["a", "b,c"], "N": [1, [2, 3]]})

    def test_multiline_and_nested_parens(self):
        got = args('[Foo(\n    "a",\n    Name = (1 + (2)),\n    T = typeof(List<(int, string)>)\n)]')
        self.assertEqual(got["value"], "a")
        self.assertEqual(got["Name"], {"text": "1+(2)"} if got["Name"] != 3 else 3)
        self.assertEqual(got["T"], {"class": "List<(int,string)>"})
        self.assertEqual(one('[Foo(\n"a",\nB = 1)]')["end_line"], 4)

    def test_targets_lists_generics_suffix(self):
        a = anns("namespace N;\npublic class C {\n  [field: JsonIgnore, Foo(1)]\n  [return: NotNull(\"x\")]\n"
                 "  public int M() => 1;\n}\n")
        self.assertEqual([(x["name"], x.get("args")) for x in a], [("JsonIgnore", None), ("Foo", {"value": 1}),
                                                                   ("NotNull", {"value": "x"})])
        self.assertEqual(args("[Foo<int>(1, Name = 2)]"), {"value": 1, "Name": 2})
        self.assertEqual(args("[Foo<Dictionary<int, string>>(1)]"), {"value": 1})
        a = anns("namespace N;\n[Foo<int, string>(1), Bar]\npublic class C { }\n", "N.C")
        self.assertEqual([(x["name"], x.get("args")) for x in a], [("Foo", {"value": 1}), ("Bar", None)])
        self.assertEqual(args('[RouteAttribute("a")]'), {"value": "a"})
        self.assertEqual(one('[RouteAttribute("a")]')["name"], "Route")
        self.assertEqual(args('[global::System.Foo("a")]'), {"value": "a"})
        self.assertEqual(one('[global::System.Foo("a")]')["name"], "Foo")

    def test_on_members_and_text_unchanged(self):
        a = anns('namespace N;\npublic class C {\n  [Foo(1)] public int P { get; set; }\n  [Bar()] public void M() {}\n}\n')
        self.assertEqual([x["args"] for x in a], [{"value": 1}, {}])
        self.assertEqual(a[0]["text"], "Foo(1)")

    def test_malformed_does_not_raise(self):
        for src in ('[Foo(,)]', '[Foo(=1)]', '[Foo(A =)]', '[Foo(new[] { 1 )]', '[Foo<>(1)]'):
            anns("namespace N;\n%s\npublic class C { }\n" % src)


class FqnTest(unittest.TestCase):
    def test_declared_in_file_and_suffix(self):
        src = ("namespace N.M;\npublic class MarkAttribute : System.Attribute { }\n"
               "[Mark, MarkAttribute, Unknown]\npublic class C { }\n")
        got = {a["name"]: a.get("fqn") for a in anns(src, "N.M.C")}
        self.assertEqual(got, {"Mark": "N.M.MarkAttribute", "Unknown": None})

    def test_alias_using(self):
        src = "using J = Lib.Json.PropAttribute;\nnamespace N;\n[J(\"x\")]\npublic class C { }\n"
        self.assertEqual(anns(src, "N.C")[0]["fqn"], "Lib.Json.PropAttribute")

    def test_dotted_and_global(self):
        src = "namespace N;\n[System.Foo, global::Lib.Bar(1), Outer.Inner]\npublic class C { }\npublic class Outer { }\n"
        got = {a["name"]: a.get("fqn") for a in anns(src, "N.C")}
        self.assertEqual(got, {"Foo": "System.Foo", "Bar": "Lib.Bar", "Inner": "N.Outer.Inner"})

    def test_namespace_using_alone_does_not_resolve(self):
        src = "using Lib.Web;\nnamespace N;\n[HttpGet(\"x\")]\npublic class C { }\n"
        self.assertNotIn("fqn", anns(src, "N.C")[0])

    def test_member_attribute_resolves(self):
        src = "namespace N;\npublic class MarkAttribute { }\npublic class C {\n  [Mark] public int P;\n}\n"
        self.assertEqual(anns(src, "N.C.P")[0]["fqn"], "N.MarkAttribute")


if __name__ == "__main__":
    unittest.main()
