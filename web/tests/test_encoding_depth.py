"""`MONOREPO_HIERARCHY.md`'s path-depth generalization of `encoding.package_of`,
`encoding.is_descendant` and `encoding.real_depths`. Pure unit tests -- no
`cdp scan` needed, since these are string functions over already-shaped ids
(`web/api/encoding.py`'s own stated contract)."""

from __future__ import annotations

import unittest

from web.api import encoding


class PackageOfDepthTest(unittest.TestCase):
    def test_depth_1_is_unchanged_from_the_original_single_arg_behaviour(self) -> None:
        self.assertEqual(encoding.package_of("cdp.store.sqlite_backend"), "cdp")
        self.assertEqual(encoding.package_of("cdp.store.sqlite_backend", 1), "cdp")

    def test_deeper_depth_takes_more_path_segments(self) -> None:
        raw = "projects.checkout.payments.order"
        self.assertEqual(encoding.package_of(raw, 1), "projects")
        self.assertEqual(encoding.package_of(raw, 2), "projects.checkout")
        self.assertEqual(encoding.package_of(raw, 3), "projects.checkout.payments")

    def test_prefixed_ids_ignore_depth_entirely(self) -> None:
        for depth in (1, 2, 5):
            self.assertEqual(encoding.package_of("table:churn_cache", depth), "Tables")
            self.assertEqual(encoding.package_of("route:GET /api/repos", depth), "Routes")

    def test_a_shallow_id_clamps_rather_than_erroring_past_its_own_depth(self) -> None:
        # A root-level module has one segment; asking for it at any deeper
        # depth should keep returning itself, not throw or return "".
        for depth in (1, 2, 3, 8):
            self.assertEqual(encoding.package_of("shared_utils", depth), "shared_utils")


class IsDescendantTest(unittest.TestCase):
    def test_bare_id_descends_from_its_own_ancestor_prefix(self) -> None:
        self.assertTrue(encoding.is_descendant("projects.checkout.payments.order", "projects.checkout"))
        self.assertTrue(encoding.is_descendant("projects.checkout.payments.order", "projects"))

    def test_bare_id_does_not_descend_from_an_unrelated_sibling(self) -> None:
        self.assertFalse(encoding.is_descendant("projects.search.index", "projects.checkout"))

    def test_bucket_ids_match_by_exact_bucket_name_only(self) -> None:
        self.assertTrue(encoding.is_descendant("table:churn_cache", "Tables"))
        self.assertFalse(encoding.is_descendant("table:churn_cache", "projects"))

    def test_bare_id_never_descends_from_a_bucket_name(self) -> None:
        self.assertFalse(encoding.is_descendant("projects.checkout.payments.order", "Tables"))


class RealDepthsTest(unittest.TestCase):
    def test_a_flat_repo_reports_only_depth_1(self) -> None:
        ids = ["cdp.cli", "cdp.store.sqlite_backend", "web.api.app"]
        self.assertEqual(encoding.real_depths(ids), [1])

    def test_prefixed_ids_never_influence_the_depth_decision(self) -> None:
        ids = ["cdp.cli", "table:churn_cache", "route:GET /api/repos"]
        self.assertEqual(encoding.real_depths(ids), [1])

    def test_a_large_uniform_top_bucket_with_a_real_fork_gains_a_second_rung(self) -> None:
        ids = [
            "projects.%s.mod%d" % (project, i)
            for project in ("checkout", "search", "billing", "inventory")
            for i in range(150)
        ]
        self.assertEqual(encoding.real_depths(ids), [1, 2])

    def test_a_small_repo_with_the_same_shape_does_not_bother_with_a_second_rung(self) -> None:
        """Rule 3: once a group is already small enough to read, don't force
        another click for no readability gain -- even though the *shape* of
        the tree has a real fork, a handful of nodes doesn't need it."""
        ids = [
            "projects.%s.mod%d" % (project, i)
            for project in ("checkout", "search")
            for i in range(3)
        ]
        self.assertEqual(encoding.real_depths(ids), [1])

    def test_a_root_level_file_does_not_spuriously_trigger_or_suppress_a_rung(self) -> None:
        ids = ["root_util"] + [
            "big.sub%d.leaf%d" % (i % 5, i) for i in range(400)
        ]
        self.assertIn(1, encoding.real_depths(ids))
        # The root-level id must still resolve sensibly at every depth found.
        for depth in encoding.real_depths(ids):
            self.assertEqual(encoding.package_of("root_util", depth), "root_util")


class ResolveOwnerFileTest(unittest.TestCase):
    """`WEB_REDESIGN_RESEARCH.md` §3.1's node -> owning-file resolution --
    the fix for `package_of`'s confirmed defect (it groups by the *id*
    string's own segments, which is empty/meaningless for bare class-name
    ids on a real C#/Java repo)."""

    def test_bare_id_resolves_through_its_own_xref_symbol(self) -> None:
        symbol_table = {"cdp.cli": {"sites": [{"file": "cdp/cli.py"}]}}
        self.assertEqual(encoding.resolve_owner_file("cdp.cli", symbol_table, []), "cdp/cli.py")

    def test_bare_id_with_no_symbol_resolves_to_none(self) -> None:
        self.assertIsNone(encoding.resolve_owner_file("cdp.cli", {}, []))

    def test_typed_id_resolves_through_its_owning_edge(self) -> None:
        symbol_table = {"cdp.store": {"sites": [{"file": "cdp/store.py"}]}}
        edges = [{"source": "cdp.store", "target": "table:churn_cache", "kind": "schema_own"}]
        self.assertEqual(
            encoding.resolve_owner_file("table:churn_cache", symbol_table, edges), "cdp/store.py"
        )

    def test_typed_id_with_no_owning_edge_resolves_to_none(self) -> None:
        edges = [{"source": "cdp.store", "target": "table:churn_cache", "kind": "call"}]
        self.assertIsNone(
            encoding.resolve_owner_file("table:churn_cache", {"cdp.store": {"sites": [{"file": "x.py"}]}}, edges)
        )

    def test_typed_id_owned_by_another_typed_id_does_not_resolve(self) -> None:
        edges = [{"source": "route:GET /x", "target": "table:churn_cache", "kind": "schema_own"}]
        self.assertIsNone(encoding.resolve_owner_file("table:churn_cache", {}, edges))

    def test_config_file_and_sql_prefixes_resolve_straight_from_their_own_suffix(self) -> None:
        """Real shapes off `unified-store`'s `dataflow` artifact: both
        prefixes carry the owning file directly in the id, verified by
        querying the real index (`WEB_REDESIGN_RESEARCH.md` follow-up) --
        neither backs an `xref` symbol, so the exact-lookup path never fires."""
        self.assertEqual(
            encoding.resolve_owner_file(
                "config-file:.github/workflows/feature_flag_check.yml", {}, []
            ),
            ".github/workflows/feature_flag_check.yml",
        )
        self.assertEqual(
            encoding.resolve_owner_file(
                "sql:ms-sql-java/downgrade-processor/src/main/resources/"
                "rollback-scripts/Rollback_V21_to_V18.sql",
                {},
                [],
            ),
            "ms-sql-java/downgrade-processor/src/main/resources/"
            "rollback-scripts/Rollback_V21_to_V18.sql",
        )

    def test_namespace_aggregate_id_falls_back_to_a_resolvable_descendant(self) -> None:
        """A C#-style namespace-aggregate id often has no `xref` symbol of its
        own, only its leaf members do -- previously always a singleton
        (`WEB_REDESIGN_RESEARCH.md`'s "372 stragglers" gap)."""
        symbol_table = {
            "RMS.UnifiedStore.Core.App.Startup": {"sites": [{"file": "core/App/Startup.cs"}]},
        }
        sorted_keys = sorted(symbol_table)
        self.assertEqual(
            encoding.resolve_owner_file(
                "RMS.UnifiedStore.Core.App", symbol_table, [], sorted_keys
            ),
            "core/App/Startup.cs",
        )

    def test_direct_descendant_probe_requires_a_dotted_boundary(self) -> None:
        """`bisect`'s prefix probe for `raw_id`'s own descendants requires the
        trailing `.` separator -- a plain string-prefix match that isn't a
        real dotted-segment descendant must not resolve, even when the
        ancestor fallback below also can't rescue it (no shared ancestor
        exists here at all -- the symbol lives under a wholly unrelated
        top-level namespace, so no ancestor of `raw_id` shares any dotted
        prefix with it either)."""
        symbol_table = {
            "Totally.Unrelated.AppSettings.Leaf": {"sites": [{"file": "other/AppSettings/Leaf.cs"}]},
        }
        sorted_keys = sorted(symbol_table)
        # "RMS.Other.App" is not a string-prefix of, nor a dotted-segment
        # ancestor of, "Totally.Unrelated.AppSettings.Leaf" at any level.
        self.assertIsNone(
            encoding.resolve_owner_file("RMS.Other.App", symbol_table, [], sorted_keys)
        )

    def test_ancestor_fallback_resolves_when_no_descendant_exists(self) -> None:
        """`WEB_REDESIGN_RESEARCH.md` follow-up: measured against the real
        `unified-store` index, 165 of 188 residual singleton namespace
        fragments (ids with no symbol of their own and no direct descendant
        either) resolve once the fallback also walks *up* the dotted id and
        retries the same two checks against each ancestor, closest first --
        e.g. `RMS.UnifiedStore.Service.Api.EdmMaintenance` has no members of
        its own, but its immediate parent `RMS.UnifiedStore.Service.Api`
        does. This intentionally widens `resolve_owner_file`'s contract from
        "this id's own subtree only" to "the nearest resolvable container"
        -- for the container-*grouping* use case that's the right trade-off
        (an orphaned namespace fragment lands in its real containing
        directory instead of becoming its own singleton group), even though
        it means two originally-unrelated *siblings* under a shared ancestor
        (like `Core.App` and `Core.AppSettings.Leaf` here) can now resolve
        to the same file when neither has more specific content of its own."""
        symbol_table = {
            "RMS.UnifiedStore.Core.AppSettings.Leaf": {"sites": [{"file": "core/AppSettings/Leaf.cs"}]},
        }
        sorted_keys = sorted(symbol_table)
        self.assertEqual(
            encoding.resolve_owner_file("RMS.UnifiedStore.Core.App", symbol_table, [], sorted_keys),
            "core/AppSettings/Leaf.cs",
        )

    def test_owner_edge_map_agrees_with_the_per_node_scan(self) -> None:
        """`build_owner_edge_map` is a precomputed O(edges) replacement for
        the typed-node fallback's O(edges)-per-node scan
        (`WEB_REDESIGN_RESEARCH.md` §5 -- found by profiling to be the actual
        dominant cost of `/api/graph`, not the artifact reads the doc named).
        Must produce identical answers to the un-precomputed scan for every
        typed id, including the negative cases above."""
        symbol_table = {
            "cdp.store": {"sites": [{"file": "cdp/store.py"}]},
            "route:GET /x": {"sites": [{"file": "should-not-be-used.py"}]},
        }
        edges = [
            {"source": "cdp.store", "target": "table:churn_cache", "kind": "schema_own"},
            {"source": "cdp.store", "target": "table:other", "kind": "call"},
            {"source": "route:GET /x", "target": "table:owned_by_typed", "kind": "schema_own"},
            {"source": "table:already_resolved", "target": "cdp.store", "kind": "schema_own"},
            {"source": "table:already_resolved", "target": "cdp.store", "kind": "http_in"},
        ]
        owner_edge_map = encoding.build_owner_edge_map(edges, symbol_table)
        for raw_id in (
            "table:churn_cache", "table:other", "table:owned_by_typed", "table:already_resolved",
            "table:never_mentioned",
        ):
            self.assertEqual(
                encoding.resolve_owner_file(raw_id, symbol_table, edges, owner_edge_map=owner_edge_map),
                encoding.resolve_owner_file(raw_id, symbol_table, edges),
                "mismatch for %r" % raw_id,
            )


class PathGroupOfTest(unittest.TestCase):
    def test_depth_1_is_the_top_directory(self) -> None:
        self.assertEqual(encoding.path_group_of("service-api/Controllers/Foo.cs", 1), "service-api")

    def test_deeper_depth_takes_more_directory_segments(self) -> None:
        path = "service-api/Controllers/Sub/Foo.cs"
        self.assertEqual(encoding.path_group_of(path, 1), "service-api")
        self.assertEqual(encoding.path_group_of(path, 2), "service-api/Controllers")
        self.assertEqual(encoding.path_group_of(path, 3), "service-api/Controllers/Sub")

    def test_shallow_path_clamps_rather_than_erroring(self) -> None:
        for depth in (1, 2, 5):
            self.assertEqual(encoding.path_group_of("core/Foo.cs", depth), "core")

    def test_root_level_file_joins_the_shared_root_group_at_every_depth(self) -> None:
        for depth in (1, 2, 5):
            self.assertEqual(encoding.path_group_of("shared_utils.py", depth), encoding.ROOT_GROUP)


class ContainerGroupTest(unittest.TestCase):
    def test_resolved_id_groups_by_its_owning_directory(self) -> None:
        file_of = {"cdp.cli": "cdp/cli.py"}
        self.assertEqual(encoding.container_group("cdp.cli", 1, file_of), "cdp")

    def test_unresolved_typed_id_falls_back_to_the_global_bucket(self) -> None:
        self.assertEqual(encoding.container_group("table:churn_cache", 1, {}), "Tables")

    def test_typed_id_with_a_resolved_owner_groups_under_it_not_the_bucket(self) -> None:
        """The point of §3.1: a `table:`/`route:` id becomes a *child* of the
        container that owns it once resolvable, not a global peer bucket."""
        file_of = {"table:churn_cache": "sql-pool/store.py"}
        self.assertEqual(encoding.container_group("table:churn_cache", 1, file_of), "sql-pool")

    def test_unresolved_bare_id_falls_back_to_a_singleton_of_itself(self) -> None:
        self.assertEqual(encoding.container_group("orphan_module", 1, {}), "orphan_module")


class ContainerDescendantTest(unittest.TestCase):
    def test_resolved_id_descends_from_its_directory_ancestor(self) -> None:
        file_of = {"x": "service-api/Controllers/Foo.cs"}
        self.assertTrue(encoding.container_descendant("x", "service-api", file_of))
        self.assertTrue(encoding.container_descendant("x", "service-api/Controllers", file_of))

    def test_resolved_id_does_not_descend_from_an_unrelated_sibling(self) -> None:
        file_of = {"x": "service-api/Controllers/Foo.cs"}
        self.assertFalse(encoding.container_descendant("x", "sql-pool", file_of))

    def test_bucket_fallback_matches_by_exact_bucket_name_only(self) -> None:
        self.assertTrue(encoding.container_descendant("table:churn_cache", "Tables", {}))
        self.assertFalse(encoding.container_descendant("table:churn_cache", "service-api", {}))


class RealContainerDepthsTest(unittest.TestCase):
    def test_a_flat_repo_reports_only_depth_1(self) -> None:
        id_to_path = {"a": "core/a.py", "b": "core/b.py", "c": "web/c.py"}
        self.assertEqual(encoding.real_container_depths(id_to_path), [1])

    def test_a_large_uniform_top_directory_with_a_real_fork_gains_a_second_rung(self) -> None:
        id_to_path = {
            "%s_id%d" % (project, i): "projects/%s/mod%d.py" % (project, i)
            for project in ("checkout", "search", "billing", "inventory")
            for i in range(150)
        }
        self.assertEqual(encoding.real_container_depths(id_to_path), [1, 2])

    def test_a_root_level_file_does_not_spuriously_trigger_or_suppress_a_rung(self) -> None:
        id_to_path = {"root_util": "root_util.py"}
        id_to_path.update({
            "id%d" % i: "big/sub%d/leaf%d.py" % (i % 5, i) for i in range(400)
        })
        depths = encoding.real_container_depths(id_to_path)
        self.assertIn(1, depths)
        self.assertEqual(encoding.path_group_of(id_to_path["root_util"], depths[0]), encoding.ROOT_GROUP)


if __name__ == "__main__":
    unittest.main()
