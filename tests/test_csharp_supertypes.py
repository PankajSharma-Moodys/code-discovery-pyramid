"""X3: C# type defines emit `supertypes` (EXTRACTION_METRICS R1), shaped like Java/Scala: source order,
names resolved through usings/namespace like other C# type refs, type arguments kept.
Spec basis: C# language specification, class/struct/interface/record base lists; cited from memory, not fetched.
All inputs are inline snippets."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cdp.lang.base import ExtractContext
from cdp.lang.csharp import CSharpExtractor


def sup(src: str) -> dict:
    facts = CSharpExtractor().extract(ExtractContext(path="A.cs", lines=src.splitlines(), module="root"))
    return {d["fqn"]: d.get("supertypes") for d in facts.defines if d["kind"] in ("class", "interface", "struct", "record", "enum")}


class SupertypesTest(unittest.TestCase):
    def test_forms(self):
        r = sup("namespace N;\nclass A : B { }\nclass A2 : B, I1, I2 { }\nclass A3 : I1 { }\n"
                "struct S : I { }\ninterface J : I1, I2 { }\nrecord R : B;\nrecord R2(int X) : B(X);\n"
                "record struct RS(int X) : I;\nclass C(int x) : Base(x) { }\nrecord class RC : B { }\n")
        self.assertEqual(r["N.A"], ["N.B"])
        self.assertEqual(r["N.A2"], ["N.B", "N.I1", "N.I2"])
        self.assertEqual(r["N.A3"], ["N.I1"])
        self.assertEqual(r["N.S"], ["N.I"])
        self.assertEqual(r["N.J"], ["N.I1", "N.I2"])
        self.assertEqual(r["N.R"], ["N.B"])
        self.assertEqual(r["N.R2"], ["N.B"])
        self.assertEqual(r["N.RS"], ["N.I"])
        self.assertEqual(r["N.C"], ["N.Base"])
        self.assertEqual(r["N.RC"], ["N.B"])

    def test_generics(self):
        r = sup("namespace N { class Repo<T> : Base<T>, IRepo<T> where T : class { } }")
        self.assertEqual(r["N.Repo"], ["N.Base<~T>", "N.IRepo<~T>"])  # `~T`: type-variable marker, as Java emits

    def test_qualified_and_using(self):
        r = sup("using Lib;\nnamespace N;\nclass A : Ns.Base { }\nclass B : global::Ns.Base { }\nclass C : Thing { }\n")
        self.assertEqual(r["N.A"], ["N.Ns.Base"])   # relative name: namespace-qualified like other C# type refs
        self.assertEqual(r["N.B"], ["Ns.Base"])
        self.assertEqual(r["N.C"], ["N.Thing"])   # unresolved simple name falls to the enclosing namespace, as for fields

    def test_layout_comments_attributes(self):
        r = sup("namespace N;\n[Serializable]\npublic class A /* c */\n    : B, // x\n      /* y */ I\n{\n}\n")
        self.assertEqual(r["N.A"], ["N.B", "N.I"])

    def test_nested_and_partial(self):
        r = sup("namespace N { public partial class P : B { class In : I { } }\npartial class P : J { }\npartial class P { } }")
        self.assertEqual(r["N.P.In"], ["N.I"])
        # one define per part, each carrying only what that part declares
        facts = CSharpExtractor().extract(ExtractContext(path="A.cs", lines=[
            "namespace N { public partial class P : B { }", "partial class P : J { }", "partial class P { } }"], module="root"))
        self.assertEqual([d.get("supertypes") for d in facts.defines if d["fqn"] == "N.P"], [["N.B"], ["N.J"], None])

    def test_not_supertypes(self):
        r = sup("namespace N;\nenum E : byte { A }\nclass A<T> where T : IFoo { A() : base() { } int x = a ? b : c; }\n"
                "delegate void D(int x);\nclass U { [field: X] int y; void M() { F(x: 1); switch (k) { case 1: break; } } }\n")
        for k in ("N.E", "N.A", "N.U"):
            self.assertIsNone(r[k], k)

    def test_none_without_base(self):
        self.assertIsNone(sup("class A { }")["A"])


if __name__ == "__main__":
    unittest.main()
