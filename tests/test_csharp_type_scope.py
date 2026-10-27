"""A C# type name outside a base list is settled by the language's name lookup, in every
type-bearing field: return, field and parameter types, call argument types, the caller signature
and call receivers (cdp/lang/csharp_scope.py `CsSigScope`, run by `jtypes.settle_extraction`).

Part one drives the lookup with a declared-type table (every order and edge case of the rule);
part two runs hand-written C# through the real extractor and resolve phase.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from helpers import Pipeline
from test_overload_sigs import _repo

from cdp.jtypes import settle_extraction
from cdp.lang.csharp_scope import CsSigScope, arity_of, rewrite


def scope(ns, declared, usings=(), guessed=(), arity=None, bases=None):
    """A `CsSigScope` for one file in `ns`; `declared` the repository's classes."""
    declared = set(declared)
    return CsSigScope(lambda f: (ns, list(usings), frozenset(guessed)),
                      lambda c: declared.intersection(c), arity=arity, bases=bases)


def row(fqn, text, field="ret"):
    return {"file": "a.cs", "kind": "method", "fqn": fqn, "module": "m", field: text}


class LookupOrderTest(unittest.TestCase):
    NS = "Co.App.Jobs"
    OWNER = "Co.App.Jobs.Svc"

    def one(self, name, declared, usings=(), owner=None, inside=True, **kw):
        sc = scope(self.NS, declared, usings, [name], **{k: kw.pop(k) for k in ("arity", "bases") if k in kw})
        fix = sc.settle([name], "a.cs", owner or self.OWNER, inside, **kw)
        return fix.get((name, 0), name)

    def test_own_namespace(self):
        self.assertEqual(self.one("Co.App.Jobs.Foo", ["Co.App.Jobs.Foo", "Co.Core.Foo"], ["Co.Core"]), "Co.App.Jobs.Foo")

    def test_enclosing_namespaces_innermost_first(self):
        d = ["Co.App.Foo", "Co.Foo", "Foo"]
        self.assertEqual(self.one("Co.App.Jobs.Foo", d), "Co.App.Foo")
        self.assertEqual(self.one("Co.App.Jobs.Foo", ["Co.Foo", "Foo"]), "Co.Foo")
        self.assertEqual(self.one("Co.App.Jobs.Foo", ["Foo"]), "Foo")        # the global namespace

    def test_inner_namespace_type_shadows_an_outer_one(self):
        self.assertEqual(self.one("Co.App.Jobs.Foo", ["Co.App.Jobs.Foo", "Co.App.Foo", "Co.Foo"]), "Co.App.Jobs.Foo")

    def test_enclosing_type_member_beats_namespaces_and_usings(self):
        d = ["Co.App.Jobs.Svc.Foo", "Co.App.Jobs.Foo", "Lib.Foo"]
        self.assertEqual(self.one("Co.App.Jobs.Foo", d, ["Lib"]), "Co.App.Jobs.Svc.Foo")

    def test_outer_enclosing_type_member(self):
        d = ["Co.App.Jobs.Svc.Foo", "Lib.Foo"]
        self.assertEqual(self.one("Co.App.Jobs.Foo", d, ["Lib"], owner="Co.App.Jobs.Svc.Inner"), "Co.App.Jobs.Svc.Foo")

    def test_a_base_list_does_not_see_the_types_own_members(self):
        d = ["Co.App.Jobs.Svc.Foo", "Lib.Foo"]
        self.assertEqual(self.one("Co.App.Jobs.Foo", d, ["Lib"], inside=False), "Lib.Foo")

    def test_inherited_member_type(self):
        d = ["Co.App.Jobs.Base.Item", "Lib.Item", "Co.App.Jobs.Svc"]
        sc = scope(self.NS, d, ["Lib"], ["Co.App.Jobs.Item"], bases={"Co.App.Jobs.Svc": ["Co.App.Jobs.Base"]}.get)
        self.assertEqual(sc.settle(["Co.App.Jobs.Item"], "a.cs", self.OWNER)[("Co.App.Jobs.Item", 0)], "Co.App.Jobs.Base.Item")
        sc = scope(self.NS, d, ["Lib"], ["Co.App.Jobs.Item"], bases={"Co.App.Jobs.Svc": ["Co.App.Jobs.Mid"],
                                                                      "Co.App.Jobs.Mid": ["Co.App.Jobs.Base"]}.get)
        self.assertEqual(sc.settle(["Co.App.Jobs.Item"], "a.cs", self.OWNER)[("Co.App.Jobs.Item", 0)], "Co.App.Jobs.Base.Item")

    def test_base_cycle_terminates(self):
        sc = scope(self.NS, ["Lib.Item"], ["Lib"], ["Co.App.Jobs.Item"],
                   bases={"Co.App.Jobs.Svc": ["Co.App.Jobs.Svc", "Co.App.Jobs.B"], "Co.App.Jobs.B": ["Co.App.Jobs.Svc"]}.get)
        self.assertEqual(sc.settle(["Co.App.Jobs.Item"], "a.cs", self.OWNER)[("Co.App.Jobs.Item", 0)], "Lib.Item")

    def test_single_using_owner(self):
        self.assertEqual(self.one("Co.App.Jobs.Foo", ["Co.Core.Foo"], ["Co.Core", "System"]), "Co.Core.Foo")

    def test_two_using_owners_stay_as_guessed(self):
        self.assertEqual(self.one("Co.App.Jobs.Foo", ["Co.A.Foo", "Co.B.Foo"], ["Co.A", "Co.B"]), "Co.App.Jobs.Foo")

    def test_one_type_reached_by_two_usings_is_one_owner(self):
        self.assertEqual(self.one("Co.App.Jobs.Foo", ["Co.A.Holder.Foo"], ["Co.A.Holder", "Co.A.Holder"]), "Co.A.Holder.Foo")

    def test_using_static_imports_nested_types(self):
        self.assertEqual(self.one("Co.App.Jobs.Inner", ["Co.Core.Holder", "Co.Core.Holder.Inner"], ["Co.Core.Holder"]),
                         "Co.Core.Holder.Inner")

    def test_alias_imports_nothing(self):
        rows = [{"fqn": "Co.Core", "module": "m", "anchor": {"anchor": "using C = Co.Core;"}}]
        self.assertEqual(self.one("Co.App.Jobs.Foo", ["Co.Core.Foo"], rows), "Foo")
        rows = [{"fqn": "Co.Core", "module": "m", "anchor": {"anchor": "using C = Co.Core; using Co.Core;"}}]
        self.assertEqual(self.one("Co.App.Jobs.Foo", ["Co.Core.Foo"], rows), "Co.Core.Foo")

    def test_a_using_imports_types_not_namespaces(self):
        # `Sub.Foo` through `using Co.Core;` needs a type `Co.Core.Sub`; a namespace `Co.Core.Sub` does not count
        self.assertEqual(self.one("Sub.Foo", ["Co.Core.Sub.Foo"], ["Co.Core"]), "Sub.Foo")
        self.assertEqual(self.one("Sub.Foo", ["Co.Core.Sub", "Co.Core.Sub.Foo"], ["Co.Core"]), "Co.Core.Sub.Foo")

    def test_relative_dotted_name_through_an_enclosing_namespace(self):
        self.assertEqual(self.one("Sub.Foo", ["Co.Sub.Foo"]), "Co.Sub.Foo")
        self.assertEqual(self.one("Sub.Foo", ["Co.App.Sub.Foo", "Co.Sub.Foo"]), "Co.App.Sub.Foo")
        self.assertEqual(self.one("Sub.Foo", ["Elsewhere.Sub.Foo"]), "Sub.Foo")   # not an owner: as written

    def test_member_access_on_a_type_keeps_the_rest(self):
        self.assertEqual(self.one("Co.App.Jobs.Foo.Make", ["Co.Core.Foo"], ["Co.Core"]), "Co.Core.Foo.Make")

    def test_member_type_wins_over_a_namespace_of_the_same_name(self):
        d = ["Co.App.Jobs.Svc.Util", "Co.App.Jobs.Util.Deep"]
        self.assertEqual(self.one("Co.App.Jobs.Util", d), "Co.App.Jobs.Svc.Util")

    def test_outer_namespace_and_a_using_both_owning_is_left_alone(self):
        # a `using` inside the namespace body would win, one at the top would not: the file does not say
        self.assertEqual(self.one("Co.App.Jobs.Foo", ["Co.Foo", "Lib.Foo"], ["Lib"]), "Co.App.Jobs.Foo")

    def test_own_namespace_beats_a_using_either_way(self):
        self.assertEqual(self.one("Co.App.Jobs.Foo", ["Co.App.Jobs.Foo", "Lib.Foo"], ["Lib"]), "Co.App.Jobs.Foo")

    def test_no_owner_is_the_name_as_written(self):
        self.assertEqual(self.one("Co.App.Jobs.Widget", ["Co.Core.Foo"], ["Co.Core"]), "Widget")

    def test_generic_arity_selects_the_declared_type(self):
        ar = {"Co.App.Jobs.Box": frozenset([1]), "Co.Core.Box": frozenset([0])}.get
        sc = scope(self.NS, ["Co.App.Jobs.Box", "Co.Core.Box"], ["Co.Core"], ["Co.App.Jobs.Box"], arity=ar)
        self.assertEqual(sc.settle(["Co.App.Jobs.Box"], "a.cs", self.OWNER)[("Co.App.Jobs.Box", 0)], "Co.Core.Box")
        self.assertNotIn(("Co.App.Jobs.Box", 1), sc.settle(["Co.App.Jobs.Box<int>"], "a.cs", self.OWNER))
        self.assertEqual(sc.settle(["Co.App.Jobs.Box<int>"], "a.cs", self.OWNER), {})
        self.assertEqual(sc.settle(["Co.App.Jobs.Box<int>"], "a.cs", self.OWNER, exact=False), {})

    def test_arity_unknown_when_type_arguments_are_erased(self):
        ar = {"Co.Core.Box": frozenset([1])}.get
        sc = scope(self.NS, ["Co.Core.Box"], ["Co.Core"], ["Co.App.Jobs.Box"], arity=ar)
        self.assertEqual(sc.settle(["Co.App.Jobs.Box"], "a.cs", self.OWNER, exact=False)[("Co.App.Jobs.Box", None)], "Co.Core.Box")
        self.assertEqual(sc.settle(["Co.App.Jobs.Box"], "a.cs", self.OWNER), {("Co.App.Jobs.Box", 0): "Box"})

    def test_attribute_suffix(self):
        d = ["Co.Core.RouteAttribute"]
        self.assertEqual(self.one("Co.App.Jobs.Route", d, ["Co.Core"], attribute=True), "Co.Core.RouteAttribute")
        self.assertEqual(self.one("Co.App.Jobs.Route", d, ["Co.Core"]), "Route")        # not an attribute context
        both = ["Co.Core.Route", "Co.Core.RouteAttribute"]
        self.assertEqual(self.one("Co.App.Jobs.Route", both, ["Co.Core"], attribute=True), "Co.App.Jobs.Route")   # ambiguous

    def test_a_name_the_extractor_did_not_guess_is_never_touched(self):
        sc = scope(self.NS, ["Co.Core.Foo"], ["Co.Core"], [])
        self.assertEqual(sc.settle(["Co.App.Jobs.Foo"], "a.cs", self.OWNER), {})

    def test_owner_in_another_namespace_block_is_left_alone(self):
        sc = scope(self.NS, ["Co.Core.Foo"], ["Co.Core"], ["Co.App.Jobs.Foo"])
        self.assertEqual(sc.settle(["Co.App.Jobs.Foo"], "a.cs", "Other.Ns.Svc"), {})

    def test_file_without_namespace_is_untouched(self):
        sc = CsSigScope(lambda f: ("", ["Co.Core"], frozenset(["Foo"])), lambda c: set(c))
        self.assertEqual(sc.settle(["Foo"], "a.cs", "Svc"), {})

    def test_arity_and_rewrite_helpers(self):
        self.assertEqual([arity_of(t, 3) for t in ("Foo", "Foo<A>", "Foo<A,B<C,D>>", "Foo<>", "Foo<,>")], [0, 1, 2, 1, 2])
        fix = {("Co.A", 1): "Lib.A", ("Co.B", 0): "Lib.B"}
        self.assertEqual(rewrite("Dict<Co.A<Co.B>, Co.B, Co.A>", fix), "Dict<Lib.A<Lib.B>, Lib.B, Co.A>")
        self.assertEqual(rewrite("Co.B Co.B2", fix), "Lib.B Co.B2")

    def test_fix_row_keeps_the_row_when_nothing_changes_and_settles_every_field(self):
        sc = scope(self.NS, ["Co.Core.Foo"], ["Co.Core"], ["Co.App.Jobs.Foo"])
        plain = row("Co.App.Jobs.Svc#M", "int")
        self.assertIs(sc.fix_row(plain), plain)
        r = {"file": "a.cs", "kind": "method", "fqn": "Co.App.Jobs.Svc#M", "ret": "List<Co.App.Jobs.Foo>",
             "params": [{"name": "a", "type": "Co.App.Jobs.Foo"}], "sig": "Co.App.Jobs.Svc#M(Co.App.Jobs.Foo)"}
        out = sc.fix_row(r)
        self.assertEqual(out["ret"], "List<Co.Core.Foo>")
        self.assertEqual(out["params"], [{"name": "a", "type": "Co.Core.Foo"}])
        self.assertEqual(out["sig"], "Co.App.Jobs.Svc#M(Co.Core.Foo)")
        self.assertEqual(r["ret"], "List<Co.App.Jobs.Foo>")        # the input row is never mutated
        use = {"file": "a.cs", "kind": "call", "fqn": "X#Y", "from_symbol": "Co.App.Jobs.Svc#Run", "recv": "Co.App.Jobs.Foo",
               "argt": ["Co.App.Jobs.Foo", "string"], "from_sig": "Co.App.Jobs.Svc#Run(Co.App.Jobs.Foo)"}
        out = sc.fix_row(use)
        self.assertEqual((out["recv"], out["argt"], out["from_sig"]),
                         ("Co.Core.Foo", ["Co.Core.Foo", "string"], "Co.App.Jobs.Svc#Run(Co.Core.Foo)"))
        self.assertEqual(out["fqn"], "X#Y")


FILES = {
    "src/Core/Decl.cs": (
        "namespace Alpha.Core {\n  public class Foo { public static Foo Make() { return null; } public void Go(Foo f) {} }\n"
        "  public interface IMarker {}\n  public class Gen<T> {}\n  public class Box {}\n  public class Item {}\n"
        "  public class Holder { public class Inner {} }\n}\n"),
    "src/Root.cs": "namespace Alpha {\n  public class RootType {}\n}\n",
    "src/Jobs/Sib.cs": "namespace Alpha.App.Jobs {\n  public class Sibling {}\n  public class Box<T> {}\n}\n",
    "src/Jobs/Base.cs": "namespace Alpha.App.Jobs {\n  public class Base { public class Item {} }\n}\n",
    "src/Jobs/Part1.cs": "namespace Alpha.App.Jobs {\n  public partial class Part { public class Foo {} }\n}\n",
    "src/Jobs/Use.cs": (
        "using System;\nusing Alpha.Core;\nusing static Alpha.Core.Holder;\nusing CoreAlias = Alpha.Core;\n"
        "namespace Alpha.App.Jobs {\n"
        "  public class Svc {\n"
        "    public Foo UsingField;\n"
        "    public Sibling SameNs;\n"
        "    public RootType Parent;\n"
        "    public Inner Static;\n"
        "    public CoreAlias.Foo Aliased;\n"
        "    public Gen<Foo> Generic;\n"
        "    public Widget Library;\n"
        "    public Box Plain;\n"
        "    public Box<int> Open;\n"
        "    public Foo Make(IMarker m, Sibling s) { return new Foo(); }\n"
        "    public Foo Make(Foo f) { return f; }\n"
        "    public void Run(Foo foo) {}\n"
        "    public void Run(Foo foo, Widget w) { foo.Go(foo); Foo.Make().Go(foo); Helper.Do(foo, s: w); Foo.Make().ToString(); }\n"
        "  }\n"
        "  public class Derived : Base { public Item Mine; }\n"
        "  public partial class Part { public Foo Member; }\n"
        "}\n"),
    "src/Jobs/Scoped.cs": (
        "using Alpha.Core;\nnamespace Alpha.App.Scoped;\n"
        "public class ScopedSvc { public Foo F; public Sibling Lost; public IMarker Make(Foo f) { return null; } }\n"),
    "src/Jobs/Nested.cs": (
        "namespace Alpha.App {\n  public class Thing {}\n  namespace Deep {\n"
        "    public class D { public Thing T; public Alpha.App.Deep.Gone G; }\n  }\n}\n"),
    "src/Shadow/Dup.cs": "namespace Alpha.Shadow { public class Dup {} }\n",
    "src/Shadow/Root.cs": "namespace Alpha { public class Dup {} }\n",
    "src/Shadow/Use.cs": "namespace Alpha.Shadow.Inner {\n  public class U { public Dup D; }\n}\n",
    "src/Amb/A.cs": "namespace Alpha.A { public class Same {} public class Pivot {} }\n",
    "src/Amb/Pivot.cs": "namespace Alpha.Amb { public class Pivot {} }\n",
    "src/Amb/B.cs": "namespace Alpha.B { public class Same {} }\n",
    "src/Amb/Use.cs": "using Alpha.A;\nusing Alpha.B;\nnamespace Alpha.Amb {\n  public class U { public Same S; }\n}\n",
    "src/Outer/Use.cs": (
        "using Alpha.A;\nnamespace Alpha.Amb.Deeper {\n  public class U { public Same S; public Pivot P; }\n}\n"),
    "src/Rel/Contracts.cs": "namespace Alpha.Contracts { public class Dto { public static int N; } }\n",
    "src/Rel/Use.cs": "namespace Alpha.App.Rel {\n  public class U { public int Go(Contracts.Dto d) { return Contracts.Dto.N; } }\n}\n",
    "src/Glob/GlobalUsings.cs": "global using Alpha.Core;\n",
    "src/Glob/Use.cs": "namespace Alpha.Glob {\n  public class U { public Foo F; }\n}\n",
}


class CsTypeScopeFixtureTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        cls.p = Pipeline(_repo(Path(cls.tmp.name), FILES))
        cls.ex = settle_extraction(cls.p.extraction)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def d(self, fqn, key="ret"):
        rows = [r for r in self.ex["defines"] if r["fqn"] == fqn]
        self.assertEqual(len(rows), 1, fqn)
        return rows[0].get(key) if key != "ftype|ret" else rows[0].get("ftype") or rows[0].get("ret")

    def f(self, fqn):
        return self.d(fqn, "ftype")

    def test_extractor_marks_the_guess_in_every_field_kind(self):
        raw = [r for r in self.p.extraction["defines"] if r["fqn"] == "Alpha.App.Jobs.Svc.UsingField"][0]
        self.assertEqual(raw["ftype"], "Alpha.App.Jobs.Foo")
        sig = self.p.extraction["files"]["src/Jobs/Use.cs"]["signals"]
        for name in ("Foo", "Widget", "IMarker", "Sibling", "Inner"):
            self.assertIn("guess:Alpha.App.Jobs." + name, sig)
        self.assertNotIn("guess:Alpha.App.Jobs.CoreAlias", sig)

    def test_field_types(self):
        j = "Alpha.App.Jobs.Svc."
        self.assertEqual(self.f(j + "UsingField"), "Alpha.Core.Foo")
        self.assertEqual(self.f(j + "SameNs"), "Alpha.App.Jobs.Sibling")
        self.assertEqual(self.f(j + "Parent"), "Alpha.RootType")
        self.assertEqual(self.f(j + "Static"), "Alpha.Core.Holder.Inner")
        self.assertEqual(self.f(j + "Aliased"), "Alpha.Core.Foo")
        self.assertEqual(self.f(j + "Generic"), "Alpha.Core.Gen<Alpha.Core.Foo>")
        self.assertEqual(self.f(j + "Library"), "Widget")

    def test_return_and_parameter_types(self):
        make = [r for r in self.ex["defines"] if r["fqn"] == "Alpha.App.Jobs.Svc#Make" and len(r["params"]) == 2][0]
        self.assertEqual(make["ret"], "Alpha.Core.Foo")
        self.assertEqual([p["type"] for p in make["params"]], ["Alpha.Core.IMarker", "Alpha.App.Jobs.Sibling"])
        self.assertEqual(make["sig"], "Alpha.App.Jobs.Svc#Make(Alpha.Core.IMarker,Alpha.App.Jobs.Sibling)")

    def test_generic_arity_picks_the_type_with_that_arity(self):
        j = "Alpha.App.Jobs.Svc."
        self.assertEqual(self.f(j + "Plain"), "Alpha.Core.Box")                 # own namespace has only Box<T>
        self.assertEqual(self.f(j + "Open"), "Alpha.App.Jobs.Box<int>")

    def test_inherited_and_partial_member_types_beat_a_using(self):
        self.assertEqual(self.f("Alpha.App.Jobs.Derived.Mine"), "Alpha.App.Jobs.Base.Item")
        self.assertEqual(self.f("Alpha.App.Jobs.Part.Member"), "Alpha.App.Jobs.Part.Foo")

    def test_call_uses(self):
        calls = [u for u in self.ex["uses"] if u["file"] == "src/Jobs/Use.cs" and u.get("kind") == "call"
                 and u.get("from_symbol") == "Alpha.App.Jobs.Svc#Run"]
        self.assertTrue(calls)
        for u in calls:
            for t in (u.get("argt") or []) + [u.get("recv") or "", u.get("from_sig") or ""]:
                self.assertNotIn("Alpha.App.Jobs.Foo", t)
                self.assertNotIn("Alpha.App.Jobs.Widget", t)
        go = [u for u in calls if u["fqn"].endswith("#Go")][0]
        self.assertEqual(go["argt"], ["Alpha.Core.Foo"])
        self.assertEqual(go["from_sig"], "Alpha.App.Jobs.Svc#Run(Alpha.Core.Foo,Widget)")
        self.assertTrue(any(u.get("recv") == "Alpha.Core.Foo" for u in calls))
        self.assertEqual(sorted({u["fqn"] for u in calls}),
                         ["Alpha.Core.Foo#Go", "Alpha.Core.Foo#Make", "Alpha.Core.Foo#ToString", "Helper#Do"])

    def test_file_scoped_namespace(self):
        s = "Alpha.App.Scoped.ScopedSvc"
        self.assertEqual(self.f(s + ".F"), "Alpha.Core.Foo")
        self.assertEqual(self.f(s + ".Lost"), "Sibling")      # the sibling lives in another namespace: no owner in scope
        self.assertEqual(self.d(s + "#Make"), "Alpha.Core.IMarker")

    def test_nested_namespace_blocks(self):
        self.assertEqual(self.f("Alpha.App.Deep.D.T"), "Alpha.App.Thing")
        self.assertEqual(self.f("Alpha.App.Deep.D.G"), "Alpha.App.Deep.Gone")      # written qualified: kept

    def test_innermost_enclosing_namespace_shadows_outer(self):
        self.assertEqual(self.f("Alpha.Shadow.Inner.U.D"), "Alpha.Shadow.Dup")

    def test_two_using_namespaces_owning_a_name_stays_as_guessed(self):
        self.assertEqual(self.f("Alpha.Amb.U.S"), "Alpha.Amb.Same")

    def test_a_using_owner_when_no_enclosing_namespace_owns(self):
        self.assertEqual(self.f("Alpha.Amb.Deeper.U.S"), "Alpha.A.Same")

    def test_enclosing_namespace_and_using_both_owning_stays_as_guessed(self):
        self.assertEqual(self.f("Alpha.Amb.Deeper.U.P"), "Alpha.Amb.Deeper.Pivot")

    def test_relative_dotted_name(self):
        m = [r for r in self.ex["defines"] if r["fqn"] == "Alpha.App.Rel.U#Go"][0]
        self.assertEqual([p["type"] for p in m["params"]], ["Alpha.Contracts.Dto"])
        use = [u for u in self.ex["uses"] if u["file"] == "src/Rel/Use.cs" and u.get("from_symbol") == "Alpha.App.Rel.U#Go"]
        for u in use:
            self.assertNotIn("Contracts.Dto", (u.get("recv") or "").replace("Alpha.Contracts.Dto", ""))

    def test_global_using_of_another_file(self):
        self.assertEqual(self.f("Alpha.Glob.U.F"), "Alpha.Core.Foo")

    def test_the_input_extraction_is_not_mutated(self):
        raw = [r for r in self.p.extraction["defines"] if r["fqn"] == "Alpha.App.Jobs.Svc.UsingField"][0]
        self.assertEqual(raw["ftype"], "Alpha.App.Jobs.Foo")


if __name__ == "__main__":
    unittest.main()
