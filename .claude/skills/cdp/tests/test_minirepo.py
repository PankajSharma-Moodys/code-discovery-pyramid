"""Phase 2 golden tests — every trap the fixture was built to contain.

PLAN.md owns a specific risk here: with Python owning structure, a detector bug
becomes silent recall loss. Nothing downstream will notice a missing `@Entity`;
the module document will simply not mention it, and it will read fine. This file
is the guard, and each test names the failure it exists to catch.
"""

from __future__ import annotations

import unittest

from helpers import MiniRepoTest, have_git


class TestInventory(MiniRepoTest):
    def test_censuses_every_tracked_file(self):
        self.assertEqual(self.pipeline.inventory["counts"]["tracked"], 13)

    def test_prefers_git_over_a_filesystem_walk(self):
        expected = "git" if have_git() else "walk"
        self.assertEqual(self.pipeline.inventory["source"], expected)

    def test_finds_modules_from_build_manifests_not_from_layout(self):
        # The rule that makes module detection portable: a directory holding a
        # build manifest is a module, in every ecosystem. A root manifest does
        # not create one -- the root is the root scope.
        names = {m["name"] for m in self.pipeline.inventory["modules"]}
        self.assertEqual(names, {"core", "web", "(root)"})

    def test_root_scope_owns_the_files_no_module_claims(self):
        root = [m for m in self.pipeline.inventory["modules"] if m["name"] == "(root)"][0]
        paths = {
            f["path"] for f in self.pipeline.inventory["files"] if f["module"] == "(root)"
        }
        self.assertEqual(root["files"], 3)
        # settings.gradle carries `rootProject.name`. Under a partition with no
        # root scope, and the rule that parents never re-read source, no agent
        # in the pipeline would ever read this file.
        self.assertIn("settings.gradle", paths)
        self.assertIn("Dockerfile", paths)


class TestPackageFromSource(MiniRepoTest):
    def test_package_is_read_from_source_never_inferred_from_path(self):
        # The directory is COM/Example/mini/core; the declared package is
        # com.example.mini.core. Path inference produces `COM.Example...`,
        # which matches nothing -- and on a case-insensitive filesystem the
        # mistake is invisible.
        self.assertTrue(self.pipeline.defines("com.example.mini.core.Widget"))
        self.assertFalse(
            [d for d in self.pipeline.extraction["defines"] if "COM.Example" in d["fqn"]]
        )

    def test_the_case_divergence_is_reported_as_a_finding(self):
        notes = [
            n for notes in self.pipeline.extraction["module_notes"].values()
            for n in notes if n.startswith("package_path_divergence:case")
        ]
        self.assertTrue(notes)
        naming = self.pipeline.claims_of("naming")
        self.assertTrue(any("package" in c["subject"] for c in naming))

    def test_root_project_name_that_matches_no_directory_is_a_naming_claim(self):
        naming = self.pipeline.claims_of("naming")
        rows = [c for c in naming if c["subject"] == "build:rootProject.name"]
        self.assertEqual(len(rows), 1)
        self.assertIn("mini-svc", rows[0]["statement"])
        self.assertTrue(rows[0]["evidence"])


class TestPersistence(MiniRepoTest):
    def test_entity_and_table_are_extracted_together(self):
        edges = self.pipeline.edges(channel="persist", target="table:widget")
        self.assertTrue(edges)
        # The C7 span: the anchor must evidence the annotation that produced it.
        self.assertIn("@Entity", edges[0]["anchor"]["anchor"])

    def test_table_is_declared_as_a_symbol(self):
        self.assertTrue(self.pipeline.defines("table:widget"))

    def test_repository_names_its_entity(self):
        edges = self.pipeline.edges(target="entity:com.example.mini.core.WidgetEntity")
        self.assertTrue(edges)
        self.assertEqual({e["channel"] for e in edges}, {"persist", "read"})

    def test_migration_owns_the_schema(self):
        owned = self.pipeline.edges(channel="schema_own", target="table:widget")
        self.assertTrue(owned)
        self.assertTrue(owned[0]["file"].endswith("V001__create_widget.sql"))


class TestRoutes(MiniRepoTest):
    def test_route_constants_are_resolved_with_both_anchors(self):
        # §6.3: a route claim arriving with only the annotation anchor is not
        # published. `@Path(ApiPaths.WIDGETS)` must reach the output as
        # `/v1/widgets` carrying the annotation site *and* the constant site.
        routes = {(r["verb"], r["route"]) for r in self.pipeline.xref["routes"]}
        self.assertIn(("GET", "/v1/widgets"), routes)
        self.assertIn(("GET", "/v1/widgets/{id}"), routes)
        for route in self.pipeline.xref["routes"]:
            self.assertEqual(len(route["evidence"]), 2, route)
            files = {a["file"] for a in route["evidence"]}
            self.assertTrue(any(f.endswith("ApiPaths.java") for f in files))

    def test_the_leaf_never_resolved_the_constant_itself(self):
        # The extractor must emit the symbolic form; resolution is a separate,
        # global pass. Otherwise a constant in another module silently deletes
        # the entire route inventory, with every step behaving as specified.
        raw = [
            e for e in self.pipeline.extraction["io_edges"]
            if e["channel"] == "http_in" and e["target"].startswith("route:")
        ]
        self.assertTrue(raw)
        self.assertTrue(all("${ApiPaths.WIDGETS}" in e["target"] for e in raw))

    def test_no_route_is_left_unresolved(self):
        self.assertEqual(self.pipeline.xref["unresolved_routes"], [])


class TestGraph(MiniRepoTest):
    def test_declared_and_observed_are_built_separately(self):
        declared = {(e["from"], e["to"]) for e in self.pipeline.graph["declared"]}
        observed = {(e["from"], e["to"]) for e in self.pipeline.graph["observed"]}
        self.assertEqual(declared, {("web", "core")})
        self.assertEqual(observed, {("web", "core")})

    def test_gradle_project_dependencies_survive_a_space_before_the_paren(self):
        # `implementation project (':core')` -- with a space. A grep for
        # `project(':` misses it, which is how a declared graph gets reported
        # as near-empty when it is not.
        self.assertIn("core", self.pipeline.extraction["declared_deps"].get("web", []))

    def test_dependency_levels_put_the_shared_module_first(self):
        levels = self.pipeline.graph["levels"]
        self.assertIn("core", levels[0])
        self.assertIn("web", levels[1])


class TestCollisions(MiniRepoTest):
    def test_duplicate_fqn_records_every_site_and_picks_no_winner(self):
        entry = self.pipeline.xref["symbols"]["com.example.mini.core.Widget"]
        self.assertTrue(entry["collision"])
        self.assertEqual(len(entry["sites"]), 2)
        files = sorted(s["file"] for s in entry["sites"])
        self.assertTrue(any("/main/" in f for f in files))
        self.assertTrue(any("/test/" in f for f in files))

    def test_a_main_vs_test_duplicate_is_not_reported_as_cross_module(self):
        rows = [
            c for c in self.pipeline.xref["collisions"]
            if c["fqn"] == "com.example.mini.core.Widget"
        ]
        self.assertEqual(len(rows), 1)
        self.assertFalse(rows[0]["cross_module"])

    def test_a_use_resolves_against_the_definition_in_its_own_module(self):
        uses = [
            u for u in self.pipeline.xref["uses"]
            if u["fqn"] == "com.example.mini.core.Widget"
        ]
        self.assertTrue(uses)
        self.assertNotIn("ambiguous", {u["resolved"] for u in uses})


class TestCrossModule(MiniRepoTest):
    def test_the_cross_module_import_becomes_a_used_by_entry(self):
        users = self.pipeline.xref["used_by"]["com.example.mini.core.Widget"]
        self.assertTrue(any(u["module"] == "web" for u in users))

    def test_entrypoints_and_deployables_are_found(self):
        entry = self.pipeline.claims_of("entrypoint")
        self.assertTrue(any("WebApplication" in c["subject"] for c in entry))
        self.assertTrue(self.pipeline.claims_of("deployable"))


class TestClaimsAreWellFormed(MiniRepoTest):
    def test_every_derived_claim_carries_evidence(self):
        for claim in self.pipeline.claims:
            self.assertTrue(claim["evidence"], claim["id"])
            self.assertGreaterEqual(len(claim["statement"]), 12, claim["id"])

    def test_every_claim_id_matches_the_schema_pattern(self):
        import re

        pattern = re.compile(r"^[a-z0-9_]+(\.[a-z0-9_]+)+$")
        for claim in self.pipeline.claims:
            self.assertRegex(claim["id"], pattern)


if __name__ == "__main__":
    unittest.main()
