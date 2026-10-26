"""A C# base type is a declared repository type, the name as written for a type outside the
repository, or an explicitly qualified name -- never a guess into the file's own namespace
(cdp/lang/csharp_scope.py `CsSigScope`, the C# half of `jtypes.SigScope`)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from helpers import Pipeline
from test_overload_sigs import _repo

FILES = {
    "src/Core/Decl.cs": (
        "namespace Alpha.Core {\n  public class Foo {}\n  public interface IMarker {}\n"
        "  public class Gen<T> {}\n  public class Dup {}\n  public class Holder { public class Inner {} }\n}\n"),
    "src/Beta/Dup.cs": "namespace Beta.Core {\n  public class Dup {}\n}\n",
    "src/Root.cs": "namespace Alpha {\n  public class Root {}\n}\n",
    "src/Jobs/Sib.cs": "namespace Alpha.App.Jobs {\n  public class SibBase {}\n}\n",
    "src/Own/Foo.cs": "namespace Alpha.App.Own {\n  public class Foo {}\n  public class OwnUser : Foo {}\n}\n",
    "src/Own/Pick.cs": "using Alpha.Core;\nnamespace Alpha.App.Own {\n  public class Pick : Foo {}\n}\n",
    "src/Jobs/Use.cs": (
        "using System;\nusing Microsoft.EntityFrameworkCore;\nusing Microsoft.Extensions.Hosting;\n"
        "using Alpha.Core;\nusing static Alpha.Core.Holder;\nusing Core2 = Alpha.Core;\n"
        "namespace Alpha.App.Jobs {\n"
        "  public class FromUsing : Foo, IMarker {}\n"
        "  public class SameNs : SibBase {}\n"
        "  public class Parent : Root {}\n"
        "  public class Static : Inner {}\n"
        "  public class Aliased : Core2.Foo {}\n"
        "  public class Explicit : Alpha.Core.Foo {}\n"
        "  public class Global : global::Alpha.Core.Foo {}\n"
        "  public class Generic : Gen<Foo> {}\n"
        "  public class ExtGeneric : ExtBase<Foo> {}\n"
        "  public class Known : DbContext {}\n"
        "  public class Err : Exception {}\n"
        "  public class Hosted : BackgroundService {}\n"
        "  public class Outer { public class In1 : In2 {} public class In2 {} }\n"
        "  public partial class Part : Foo {}\n"
        "  public partial class Part : IMarker {}\n"
        "  public partial class Split { public class Child : Helper {} }\n"
        "}\n"),
    "src/Jobs/Split2.cs": "namespace Alpha.App.Jobs {\n  public partial class Split { public class Helper {} }\n}\n",
    "src/Jobs/Amb.cs": (
        "using Alpha.Core;\nusing Beta.Core;\nnamespace Alpha.App.Jobs {\n  public class Amb : Dup {}\n}\n"),
}


class CsSupertypeScopeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        cls.p = Pipeline(_repo(Path(cls.tmp.name), FILES))

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def sup(self, name):
        sites = self.p.xref["symbols"]["Alpha.App.Jobs." + name]["sites"]
        return [s for site in sites for s in site.get("supertypes", ())]

    def test_extract_stays_per_file_and_marks_the_guess(self):
        raw = [d for d in self.p.extraction["defines"] if d["fqn"] == "Alpha.App.Jobs.FromUsing"][0]
        self.assertEqual(raw["supertypes"], ["Alpha.App.Jobs.Foo", "Alpha.App.Jobs.IMarker"])
        sig = self.p.extraction["files"]["src/Jobs/Use.cs"]["signals"]
        self.assertIn("guess:Alpha.App.Jobs.Foo", sig)

    def test_using_namespace_not_in_the_table(self):
        self.assertEqual(self.sup("FromUsing"), ["Alpha.Core.Foo", "Alpha.Core.IMarker"])

    def test_declared_in_another_file_of_the_same_namespace(self):
        self.assertEqual(self.sup("SameNs"), ["Alpha.App.Jobs.SibBase"])

    def test_enclosing_namespace(self):
        self.assertEqual(self.sup("Parent"), ["Alpha.Root"])

    def test_using_static_and_alias(self):
        self.assertEqual(self.sup("Static"), ["Alpha.Core.Holder.Inner"])
        self.assertEqual(self.sup("Aliased"), ["Alpha.Core.Foo"])

    def test_explicit_names_are_kept(self):
        self.assertEqual(self.sup("Explicit"), ["Alpha.Core.Foo"])
        self.assertEqual(self.sup("Global"), ["Alpha.Core.Foo"])

    def test_generic_bases(self):
        self.assertEqual(self.sup("Generic"), ["Alpha.Core.Gen<Alpha.Core.Foo>"])
        self.assertEqual(self.sup("ExtGeneric"), ["ExtBase<Alpha.Core.Foo>"])

    def test_known_framework_types_unchanged(self):
        self.assertEqual(self.sup("Known"), ["Microsoft.EntityFrameworkCore.DbContext"])
        self.assertEqual(self.sup("Err"), ["System.Exception"])

    def test_unresolvable_external_base_is_the_bare_name(self):
        self.assertEqual(self.sup("Hosted"), ["BackgroundService"])

    def test_nested_and_partial(self):
        self.assertEqual(self.sup("Outer.In1"), ["Alpha.App.Jobs.Outer.In2"])
        self.assertEqual(sorted(self.sup("Part")), ["Alpha.Core.Foo", "Alpha.Core.IMarker"])
        self.assertEqual(self.sup("Split.Child"), ["Alpha.App.Jobs.Split.Helper"])

    def test_own_namespace_beats_a_using(self):
        sym = self.p.xref["symbols"]
        self.assertEqual(sym["Alpha.App.Own.OwnUser"]["sites"][0]["supertypes"], ["Alpha.App.Own.Foo"])
        self.assertEqual(sym["Alpha.App.Own.Pick"]["sites"][0]["supertypes"], ["Alpha.App.Own.Foo"])

    def test_name_in_two_using_namespaces_stays_as_guessed(self):
        self.assertEqual(self.sup("Amb"), ["Alpha.App.Jobs.Dup"])


if __name__ == "__main__":
    unittest.main()
