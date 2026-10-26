"""X1: C# attributes become `annotations` on defines (EXTRACTION_METRICS M1).
Reference: ECMA-334 C# language specification, "Attributes" chapter (attribute sections,
attribute targets, attribute lists): https://learn.microsoft.com/dotnet/csharp/language-reference/language-specification/attributes"""
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


def names(d, key):
    return [a["name"] for a in d[key].get("annotations", [])]


SRC = """namespace N;
[assembly: AsmAttr]
[Serializable]
public class C
{
    [Obsolete("x")]
    public void M() { }

    [A, B(1)]
    [Cc]
    public int P { get; set; }

    [field: NonSerialized]
    public int F;

    [return: NotNull]
    public string R() => "";

    [Multi(
        1,
        2)]
    public C() { }

    [Plain]
    int g, h;

    [property: JsonIgnore] public int Q { get; }
}
[X] public struct S { }
[X]
public interface I { [Op] void Do(); }
[E1]
public enum En { [Member] One, Two }
[Rec] public record Rr(int A);
public class NoAttr { public int Z; }
"""


class CSharpAnnotations(unittest.TestCase):
    def setUp(self):
        self.d = defs(SRC)

    def test_types(self):
        d = self.d
        self.assertEqual(names(d, "N.C"), ["Serializable"])   # assembly-targeted list has no declaration
        for k, n in (("N.S", "X"), ("N.I", "X"), ("N.En", "E1"), ("N.Rr", "Rec")):
            self.assertEqual(names(d, k), [n], k)
        self.assertNotIn("annotations", d["N.NoAttr"])
        self.assertNotIn("annotations", d["N.NoAttr.Z"])

    def test_members(self):
        d = self.d
        self.assertEqual(names(d, "N.C#M"), ["Obsolete"])
        self.assertEqual(d["N.C#M"]["annotations"][0]["text"], 'Obsolete("x")')
        self.assertEqual(names(d, "N.C.P"), ["A", "B", "Cc"])
        self.assertEqual(names(d, "N.C.F"), ["NonSerialized"])
        self.assertEqual(names(d, "N.C#R"), ["NotNull"])
        self.assertEqual(names(d, "N.C#<init>"), ["Multi"])
        self.assertEqual(names(d, "N.C.Q"), ["JsonIgnore"])
        self.assertEqual(names(d, "N.C.g"), ["Plain"])
        self.assertEqual(names(d, "N.C.h"), ["Plain"])
        self.assertEqual(names(d, "N.I#Do"), ["Op"])
        self.assertEqual(names(d, "N.En.One"), ["Member"])

    def test_lines(self):
        a = self.d["N.C#<init>"]["annotations"][0]
        self.assertEqual((a["line"], a["end_line"]), (19, 21))
        a = self.d["N.C.P"]["annotations"]
        self.assertEqual([(x["line"], x["end_line"]) for x in a], [(9, 9), (9, 9), (10, 10)])


if __name__ == "__main__":
    unittest.main()
