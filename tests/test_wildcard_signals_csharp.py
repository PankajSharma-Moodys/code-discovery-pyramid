"""C# `wildcard:<namespace>` file signals: a type name no declared type owns, in a file that `using`s a
namespace the repository does not declare and the framework list does not cover."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from helpers import Pipeline
from test_java_resolution import inline_repo

D = "src/App/"
G = "src/Glob/"       # its own project: a `global using` reaches only the files of its module
PROJ = "<Project Sdk=\"Microsoft.NET.Sdk\"></Project>\n"
FILES = {
    D + "App.csproj": PROJ,
    G + "Glob.csproj": PROJ,
    D + "Core.cs": "namespace Acme.Core;\npublic class Order { }\npublic class Widget { }\n",
    D + "Other.cs": "namespace Acme.Other;\npublic class Gadget { }\n",
    # unsettled IFlagProvider + a namespace nobody in the repository declares -> flagged
    D + "Svc.cs": ("using System;\nusing Acme.Core;\nusing Vendor.Flags;\nnamespace Acme.App;\n"
                   "public class Svc { IFlagProvider f; Order o; }\n"),
    # every name settled -> nothing to flag
    D + "Fine.cs": "using Acme.Core;\nusing Vendor.Flags;\nnamespace Acme.App;\npublic class Fine { Order o; Widget w; }\n",
    # unsettled name, but only ubiquitous framework namespaces and a repo namespace
    D + "Sys.cs": ("using System;\nusing System.Collections.Generic;\nusing System.Linq;\nusing Acme.Other;\n"
                   "namespace Acme.App;\npublic class Sys { Mystery m; }\n"),
    # a library type seen where no unknown namespace could supply it is a framework type everywhere
    D + "Ctl.cs": "using Xunit;\nnamespace Acme.App;\npublic class Ctl { Assert a; }\n",
    D + "Tst.cs": "using Xunit;\nusing Vendor.Flags;\nnamespace Acme.App;\npublic class Tst { Assert a; }\n",
    # global using applies to the other files of the module
    G + "Glob.cs": "global using Vendor.Rules;\n",
    G + "UsesGlob.cs": "namespace Acme.App;\npublic class UsesGlob { IRuleEngine e; }\n",
    # a nested type of a declared class is a member type, not an unsettled name
    D + "Nest.cs": ("using Vendor.Flags;\nnamespace Acme.App;\npublic class Outer { public class Inner { } }\n"
                    "public class UsesNest { Inner i; Outer o; }\n"),
}


class WildcardSignalsCsharpTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.p = Pipeline(inline_repo(Path(cls.tmp.name), FILES))
        cls.files = cls.p.extraction["files"]

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def sig(self, name):
        return sorted(s for s in self.files[D + name]["signals"] if s.startswith("wildcard:"))

    def test_unsettled_name_marks_unknown_namespace(self):
        self.assertEqual(self.sig("Svc.cs"), ["wildcard:Vendor.Flags"])

    def test_no_signal_when_names_settled(self):
        self.assertEqual(self.sig("Fine.cs"), [])
        self.assertEqual(self.sig("Nest.cs"), [])

    def test_no_signal_for_framework_or_repo_namespaces_alone(self):
        self.assertEqual(self.sig("Sys.cs"), [])
        self.assertEqual(self.sig("Ctl.cs"), [])

    def test_name_seen_without_unknown_namespace_is_a_framework_type(self):
        self.assertEqual(self.sig("Tst.cs"), [])

    def test_global_using_counts(self):
        self.assertEqual(sorted(s for s in self.files[G + "UsesGlob.cs"]["signals"] if s.startswith("wildcard:")),
                         ["wildcard:Vendor.Rules"])


if __name__ == "__main__":
    unittest.main()
