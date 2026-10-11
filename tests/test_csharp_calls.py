"""B8 for C#: call sites (`used_by`) resolved through declared types, `var`, `await`, LINQ,
extension methods, target-typed `new()`, `: base()` and method groups. The real-repository
measure against Roslyn is `scripts/csharp_benchmark.py`."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from helpers import Pipeline, make_repo

C = "Shop.Core."
S = "Shop.App.Service#Run"


class CSharpCallsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.p = Pipeline(make_repo(Path(cls.tmp.name), "csharpcalls"))
        cls.used = cls.p.xref["used_by"]

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def lines(self, key):
        return sorted(u["anchor"]["line"] for u in self.used.get(key, []) if u["file"].endswith("Service.cs"))

    def test_member_call_through_field_and_await(self):
        self.assertTrue(any(13 <= x <= 16 for x in self.lines(C + "IStore#FindAsync")))

    def test_var_from_await_types_later_calls_and_interpolation_holes(self):
        lab = self.lines(C + "Widget#Label")
        self.assertTrue(any(15 <= x <= 18 for x in lab), lab)      # `{w.Label()}` inside `$"..."`
        self.assertTrue(any(x >= 22 for x in lab), lab)            # `made.Label()` / `other.Label()` (target-typed new)

    def test_lambda_parameter_typed_from_collection(self):
        self.assertTrue(self.lines(C + "Widget#Label"))

    def test_extension_method_resolves_to_static_class(self):
        self.assertTrue(self.lines(C + "WidgetExtensions#Shout"))

    def test_new_and_target_typed_new(self):
        self.assertTrue(self.lines(C + "Widget#<init>"))
        self.assertTrue(self.lines(C + "Plain"))            # implicit default ctor: the class itself

    def test_base_initializer_and_inherited_call(self):
        self.assertTrue(self.lines(C + "Base#<init>"))
        self.assertTrue(self.lines(C + "Base#Greet"))

    def test_static_call_and_method_group(self):
        self.assertTrue(self.lines(C + "Widget#Make"))
        self.assertTrue(self.lines("Shop.App.Service#Convert"))

    def test_verbatim_interpolated_string_does_not_swallow_following_members(self):
        from cdp.lang.base import ExtractContext
        from cdp.lang.csharp import CSharpExtractor
        src = ('namespace N;\npublic class A\n{\n    string F(object[] xs) => @$"a {string.Join(",", xs)} b";\n'
               '    private int G() { return 1; }\n}\n')
        facts = CSharpExtractor().extract(ExtractContext(path="A.cs", lines=src.splitlines(), module="m"))
        self.assertIn("N.A#G", {d["fqn"] for d in facts.defines})


if __name__ == "__main__":
    unittest.main()
