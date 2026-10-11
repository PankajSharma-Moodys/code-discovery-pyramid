"""F2 -- the C# extractor. New code with real risk (no prior extractor for
this language), so it gets direct tests rather than relying solely on the
real-target exercise recorded in PHASE/TARGET.md."""

from __future__ import annotations

import unittest

from helpers import SKILL_ROOT  # noqa: F401  (sets sys.path)

from cdp.lang.base import ExtractContext
from cdp.lang.csharp import CSharpExtractor


def extract(src: str, path: str = "Controllers/WidgetController.cs"):
    ctx = ExtractContext(path=path, lines=src.splitlines(), module="root")
    return CSharpExtractor().extract(ctx)


class NamespaceAndImportsTest(unittest.TestCase):
    def test_file_scoped_namespace(self) -> None:
        facts = extract("namespace RMS.UnifiedStore.Core;\n\nusing System;\n")
        self.assertEqual(facts.package, "RMS.UnifiedStore.Core")

    def test_using_directive_is_an_import(self) -> None:
        facts = extract(
            "namespace N;\n\nusing System;\nusing Microsoft.AspNetCore.Mvc;\n"
        )
        self.assertEqual([i["fqn"] for i in facts.imports],
                          ["System", "Microsoft.AspNetCore.Mvc"])

    def test_using_declaration_is_not_an_import(self) -> None:
        """The actual bug shape a naive regex hits: C# 8's inline `using`
        *declaration* (`using IServiceScope x = ...;`) looks like a `using`
        directive at a glance but is a variable declaration, not an import."""
        facts = extract(
            "namespace N;\n\n"
            "using System;\n"
            "using IServiceScope serviceScope = _serviceProvider.CreateScope();\n"
        )
        self.assertEqual([i["fqn"] for i in facts.imports], ["System"])


class DeclarationsTest(unittest.TestCase):
    def test_allman_brace_class_and_method(self) -> None:
        """Real target style: the opening brace is on its own line, not on
        the class header's line. A same-line assumption pops the class
        before anything inside it is read -- this is the regression test
        for that bug."""
        src = (
            "namespace N;\n\n"
            "public class WidgetController\n"
            "{\n"
            "    public IActionResult GetJob(string jobId)\n"
            "    {\n"
            "        return Ok();\n"
            "    }\n"
            "}\n"
        )
        facts = extract(src)
        fqns = [d["fqn"] for d in facts.defines]
        self.assertIn("N.WidgetController", fqns)
        self.assertIn("N.WidgetController#GetJob", fqns)

    def test_bodyless_record_does_not_swallow_the_next_declaration(self) -> None:
        src = (
            "namespace N;\n\n"
            "public record WidgetDto(int Id, string Name);\n\n"
            "public class AppDbContext : DbContext\n"
            "{\n"
            "    public DbSet<Widget> Widgets { get; set; }\n"
            "}\n"
        )
        facts = extract(src)
        fqns = [d["fqn"] for d in facts.defines]
        self.assertIn("N.WidgetDto", fqns)
        self.assertIn("N.AppDbContext", fqns)


class RoutesAndEfCoreTest(unittest.TestCase):
    def test_http_route_owned_by_the_method_not_a_later_class(self) -> None:
        src = (
            "namespace N;\n\n"
            "[ApiController]\n"
            "[Route(\"v1/[controller]\")]\n"
            "public class WidgetController\n"
            "{\n"
            "    [HttpGet(\"{jobId}\")]\n"
            "    public IActionResult GetJob(string jobId)\n"
            "    {\n"
            "        return Ok();\n"
            "    }\n"
            "}\n\n"
            "public class AppDbContext : DbContext\n"
            "{\n"
            "    public DbSet<Widget> Widgets { get; set; }\n"
            "}\n"
        )
        facts = extract(src)
        self.assertIn("api_controller", facts.signals)
        route_edges = [e for e in facts.io_edges if e["channel"] == "http_in"]
        self.assertEqual(len(route_edges), 1)
        self.assertEqual(route_edges[0]["source"], "N.WidgetController#GetJob")
        # the handler's own template; the class's `[Route]` is joined by the resolve phase
        self.assertEqual(route_edges[0]["target"], "route:GET {jobId}")
        self.assertEqual(route_edges[0]["route_class"], "N.WidgetController")
        self.assertIsNotNone(route_edges[0]["anchor"])

    def test_dbset_produces_a_persist_edge_to_the_entity(self) -> None:
        src = (
            "namespace N;\n\n"
            "public class AppDbContext : DbContext\n"
            "{\n"
            "    public DbSet<Widget> Widgets { get; set; }\n"
            "}\n"
        )
        facts = extract(src)
        self.assertIn("ef_dbcontext", facts.signals)
        persist_edges = [e for e in facts.io_edges if e["channel"] == "persist" and e["target"].startswith("entity:")]
        self.assertEqual(len(persist_edges), 1)
        self.assertEqual(persist_edges[0]["target"], "entity:Widget")


PKG = "Acme.Api."
CTRL = PKG + "Controllers.AdminController"


class CSharpDefectsTest(unittest.TestCase):
    """B9-B13 on `tests/fixtures/csharprepo`; `scripts/csharp_benchmark.py` measures the same
    things against Roslyn on a real repository."""

    @classmethod
    def setUpClass(cls):
        import tempfile
        from pathlib import Path
        from helpers import Pipeline, make_repo
        cls.tmp = tempfile.TemporaryDirectory()
        cls.p = Pipeline(make_repo(Path(cls.tmp.name), "csharprepo"))
        cls.symbols = cls.p.xref["symbols"]

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_b9_private_internal_protected_methods_are_indexed(self):
        self.assertEqual(self.symbols[CTRL + "#IsAllowed"]["visibility"], "private")
        self.assertEqual(self.symbols[CTRL + "#Weight"]["visibility"], "internal")
        self.assertEqual(self.symbols[CTRL + "#OnRebuilt"]["visibility"], "protected")

    def test_b10_long_primary_constructor_keeps_its_methods(self):
        self.assertIn(CTRL + "#List", self.symbols)
        self.assertIn(CTRL + "#<init>", self.symbols)
        self.assertEqual(self.symbols[PKG + "Controllers.AdminController"]["kind"], "class")

    def test_b10_generic_and_tuple_return_methods_are_indexed(self):
        self.assertIn(CTRL + "#Pair", self.symbols)
        self.assertIn(CTRL + "#Rebuild", self.symbols)

    def test_b11_partial_class_route_and_controller_token_are_applied(self):
        routes = {(r["verb"], r["route"]): r["handler"] for r in self.p.xref["routes"]}
        # [Route] sits in AdminController.cs, the handler in AdminController.Jobs.cs
        self.assertEqual(routes[("GET", "/v1/{tenantId}/Admin/jobs/{jobId}")], CTRL + "#GetJob")
        # a route-level `[HttpGet]` without a template is the class route
        self.assertEqual(routes[("GET", "/v1/{tenantId}/Admin")], CTRL + "#List")
        # an absolute template ignores the class route
        self.assertEqual(routes[("POST", "/internal/rebuild")], CTRL + "#Rebuild")

    def test_b12_ef_core_tables(self):
        tables = {d["fqn"] for d in self.p.extraction["defines"] if d["kind"] == "table"}
        self.assertTrue({"table:Widgets", "table:gadget_items", "table:Audits"} <= tables)
        self.assertNotIn("table:Ghosts", tables)       # ToView(null): not a table
        self.assertNotIn("table:Gadgets", tables)      # ToTable renamed it

    def test_b13_configuration_reads_and_appsettings_keys(self):
        from cdp.resolve import config_reads
        reads = {r["key"] for r in config_reads(self.p.extraction, self.p.xref["constants"])
                 if r["file"].endswith(".cs")}
        self.assertEqual(reads, {"Global:WidgetUrl", "Global:Retries", "WIDGET_REGION",
                                 "ConnectionStrings:Main", "Global"})
        declared = {d["fqn"] for d in self.p.extraction["defines"] if d["kind"] == "config_key"}
        self.assertTrue({"config:Global:WidgetUrl", "config:Global:Retries", "config:Serilog:Enrich:1"} <= declared)


if __name__ == "__main__":
    unittest.main()
