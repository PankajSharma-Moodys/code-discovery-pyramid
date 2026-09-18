"""Phase 8 (M8.1): `link.scan_links` matches channel edges across snapshots.

Synthetic `dataflow.json`-shaped dicts (`cdp/dataflow.py`'s own edge shape),
not a scanned repo -- the matcher is pure and does not need a real pipeline
to exercise its logic; the real-target exercise is a separate scratch-scan
smoke test (see the plan's own real-input requirement, run manually this
session against two modules of $TARGET_REPO, not repeated here as a unit
test since it needs a live scan).
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT))

from cdp.link import (  # noqa: E402
    build_tasks,
    dispatch_link_task,
    fold_resolutions,
    link_task_shape_key,
    query_service,
    refresh_links,
    scan_links,
    summarise_query,
    validate_task_patch,
)


def _edge(source, target, channel, module="m", file="a.py", line=1):
    return {
        "source": source,
        "target": target,
        "channel": channel,
        "module": module,
        "anchor": {"file": file, "line": line},
        "confidence": "high",
    }


def _snapshot(repo, head, edges):
    return {"repo": repo, "head": head, "dataflow": {"edges": list(edges)}}


class ExactMatchTest(unittest.TestCase):
    def test_route_exact_match_across_two_snapshots(self):
        caller = _snapshot(
            "billing", "aaa",
            [_edge("BillingClient#charge", "http:https://orders.internal/orders/{id}",
                   "http_out", file="BillingClient.java", line=10)],
        )
        callee = _snapshot(
            "orders", "bbb",
            [_edge("OrderController#get", "route:GET /orders/{id}",
                   "http_in", file="OrderController.java", line=20)],
        )
        report = scan_links([caller, callee])
        self.assertEqual(report["totals"]["links"], 1)
        self.assertEqual(report["totals"]["unmatched"], 0)
        link = report["links"][0]
        self.assertEqual(link["match_kind"], "exact")
        self.assertFalse(link["self_link"])
        self.assertEqual(link["caller"]["repo"], "billing")
        self.assertEqual(link["callee"]["repo"], "orders")


class HeuristicMatchTest(unittest.TestCase):
    def test_different_param_syntax_is_heuristic_not_exact(self):
        caller = _snapshot("a", "1", [_edge("X", "http:https://h/widgets/:id", "http_out")])
        callee = _snapshot("b", "2", [_edge("Y", "route:GET /widgets/{id}", "http_in")])
        report = scan_links([caller, callee])
        self.assertEqual(len(report["links"]), 1)
        self.assertEqual(report["links"][0]["match_kind"], "heuristic")


class SelfLinkTest(unittest.TestCase):
    def test_a_module_persisting_to_its_own_owned_table_is_a_valid_self_link(self):
        snap = _snapshot(
            "monolith", "ccc",
            [
                _edge("OrderRepo#save", "table:orders", "persist", file="OrderRepo.java", line=5),
                _edge("orders_migration", "table:orders", "schema_own", file="V1__orders.sql", line=1),
            ],
        )
        report = scan_links([snap])
        self.assertEqual(report["totals"]["links"], 1)
        self.assertTrue(report["links"][0]["self_link"])
        self.assertEqual(report["totals"]["unmatched"], 0)


class UnmatchedTest(unittest.TestCase):
    def test_call_to_an_unregistered_service_is_a_named_unmatched_deliverable(self):
        caller = _snapshot(
            "billing", "aaa",
            [_edge("X", "http:https://vendor.example.com/v1/charge", "http_out",
                   file="Client.java", line=7)],
        )
        callee = _snapshot("orders", "bbb", [_edge("Y", "route:GET /orders", "http_in")])
        report = scan_links([caller, callee])
        self.assertEqual(report["totals"]["links"], 0)
        self.assertEqual(len(report["unmatched"]), 1)
        self.assertEqual(report["unmatched"][0]["outbound"]["anchor"]["file"], "Client.java")

    def test_second_repo_not_registered_is_unmatched_not_no_callers(self):
        # 5.7 stress test: repo B not registered at all -- every http_out to
        # it is unmatched (correct), not silently absent.
        caller = _snapshot("only_one", "aaa", [_edge("X", "http:https://b/orders", "http_out")])
        report = scan_links([caller])
        self.assertEqual(report["totals"]["links"], 0)
        self.assertEqual(len(report["unmatched"]), 1)


class LibraryExclusionTest(unittest.TestCase):
    def test_library_prefixed_targets_never_match(self):
        # base.py's package-fallback edges (e.g. "library:okhttp3") are not
        # a place data goes -- must not appear as either side of a link.
        caller = _snapshot("a", "1", [_edge("X", "library:okhttp3", "http_out")])
        callee = _snapshot("b", "2", [_edge("Y", "library:okhttp3", "http_in")])
        report = scan_links([caller, callee])
        self.assertEqual(report["totals"]["links"], 0)
        self.assertEqual(report["totals"]["unmatched"], 0)


class TablePrefixIsNotARouteParamTest(unittest.TestCase):
    def test_distinct_table_names_do_not_collapse_onto_one_key(self):
        # F-link1: `_ROUTE_PARAM_RE` (meant for a URL path param like
        # `/orders/:id`) also matches `table:Name`'s own `:name` separator --
        # applying it there collapsed every distinct table name onto one key,
        # found live against two real modules of $TARGET_REPO.
        caller = _snapshot("a", "1", [_edge("X", "table:dbo", "persist")])
        callee = _snapshot(
            "b", "2",
            [
                _edge("Y", "table:Address", "schema_own"),
                _edge("Z", "table:dbo", "schema_own"),
            ],
        )
        report = scan_links([caller, callee])
        self.assertEqual(len(report["links"]), 1)
        self.assertEqual(report["links"][0]["callee"]["target"], "table:dbo")


class ByModuleExplosionTest(unittest.TestCase):
    def test_two_modules_in_one_whole_repo_scan_link_and_are_not_self_links(self):
        # The actual scenario a monorepo scan needs: one `cdp scan --repo
        # <monorepo>` produces one dataflow.json pooling every module's
        # edges. `billing-service` persisting to a table `orders-schema`
        # owns must surface as a real cross-module link, not vanish because
        # both came from the same (repo, head) scan.
        one_scan = _snapshot(
            "monorepo", "zzz",
            [
                _edge("BillingRepo#save", "table:orders", "persist",
                      module="billing-service", file="BillingRepo.java", line=3),
                _edge("orders_migration", "table:orders", "schema_own",
                      module="orders-schema", file="V1__orders.sql", line=1),
            ],
        )
        report = scan_links([one_scan])
        self.assertEqual(report["totals"]["modules"], 2)
        self.assertEqual(len(report["links"]), 1)
        link = report["links"][0]
        self.assertFalse(link["self_link"])
        self.assertEqual(link["caller"]["module"], "billing-service")
        self.assertEqual(link["callee"]["module"], "orders-schema")

    def test_same_module_persisting_to_its_own_table_stays_a_self_link(self):
        one_scan = _snapshot(
            "monorepo", "zzz",
            [
                _edge("Repo#save", "table:t", "persist", module="svc"),
                _edge("migration", "table:t", "schema_own", module="svc"),
            ],
        )
        report = scan_links([one_scan])
        self.assertEqual(report["totals"]["modules"], 1)
        self.assertTrue(report["links"][0]["self_link"])


class NonEntanglementShapeTest(unittest.TestCase):
    def test_scan_links_reads_only_dataflow_and_never_touches_its_inputs(self):
        snap = _snapshot("a", "1", [_edge("X", "table:t", "persist"), _edge("Y", "table:t", "schema_own")])
        before = {"repo": snap["repo"], "head": snap["head"], "edges": list(snap["dataflow"]["edges"])}
        scan_links([snap])
        self.assertEqual(before["edges"], snap["dataflow"]["edges"])


class QueryServiceTest(unittest.TestCase):
    """M8.2 (5.6): `link query --service` reads the persisted rows shape
    (`{"kind": ..., "data": ...}`, `SqliteStore.read_link_edges`'s return
    value) and surfaces both directions plus the service's own unmatched
    calls as a named deliverable.
    """

    def _rows(self, report):
        return ([{"kind": "link", "data": l} for l in report["links"]]
                + [{"kind": "unmatched", "data": u} for u in report["unmatched"]])

    def test_service_as_caller_and_as_callee_both_surface(self):
        caller = _snapshot("billing", "aaa", [_edge("X", "http:https://o/orders/{id}", "http_out")])
        callee = _snapshot("orders", "bbb", [_edge("Y", "route:GET /orders/{id}", "http_in")])
        report = scan_links([caller, callee])
        rows = self._rows(report)

        as_caller = query_service(rows, "billing")
        self.assertEqual(len(as_caller["links"]), 1)
        self.assertEqual(as_caller["unmatched"], [])

        as_callee = query_service(rows, "orders")
        self.assertEqual(len(as_callee["links"]), 1)

        unrelated = query_service(rows, "nope")
        self.assertEqual(unrelated["links"], [])
        self.assertEqual(unrelated["unmatched"], [])

    def test_unmatched_outbound_call_surfaces_for_its_own_service_only(self):
        caller = _snapshot(
            "billing", "aaa",
            [_edge("X", "http:https://vendor.example.com/v1/charge", "http_out",
                   file="Client.java", line=7)],
        )
        report = scan_links([caller])
        rows = self._rows(report)

        result = query_service(rows, "billing")
        self.assertEqual(len(result["unmatched"]), 1)
        self.assertEqual(result["unmatched"][0]["outbound"]["anchor"]["file"], "Client.java")
        self.assertIn("unmatched 1 outbound call(s) from billing", "\n".join(summarise_query(result)))

        self.assertEqual(query_service(rows, "vendor.example.com")["unmatched"], [])


class LinkTaskTest(unittest.TestCase):
    def test_three_concatenated_call_sites_become_one_task(self):
        caller = _snapshot(
            "billing", "aaa",
            [
                _edge("A", "http:https://x/charge/{id}", "http_out", file="A.java", line=1),
                _edge("B", "http:https://x/charge/{id}", "http_out", file="B.java", line=2),
                _edge("C", "http:https://x/charge/{id}", "http_out", file="C.java", line=3),
            ],
        )
        callee = _snapshot(
            "svc", "bbb",
            [_edge("Handler", "route:POST /charge/:id", "http_in", file="H.java", line=9)],
        )
        report = scan_links([caller, callee])
        self.assertEqual(len(report["links"]), 3)
        self.assertTrue(all(l["match_kind"] == "heuristic" for l in report["links"]))

        tasks = build_tasks(report)
        self.assertEqual(len(tasks), 1)
        self.assertEqual(len(tasks[0]["candidates"]), 3)

    def test_valid_resolution_folds_and_leaves_match_kind_untouched(self):
        caller = _snapshot("billing", "aaa",
                            [_edge("A", "http:https://x/charge/{id}", "http_out", file="A.java", line=1)])
        callee = _snapshot("svc", "bbb",
                            [_edge("Handler", "route:POST /charge/:id", "http_in", file="H.java", line=9)])
        report = scan_links([caller, callee])
        tasks = build_tasks(report)
        task = tasks[0]
        link_id = task["candidates"][0]["link_id"]

        patch = {"task_id": task["task_id"], "resolutions": [
            {"link_id": link_id, "verdict": "match", "reason": "same charge endpoint",
             "anchor": {"file": "A.java", "line": 1}},
        ]}
        self.assertEqual(validate_task_patch(patch, task), [])
        n = fold_resolutions(report, task, patch, "run-1")
        self.assertEqual(n, 1)
        link = report["links"][0]
        self.assertEqual(link["match_kind"], "heuristic")
        self.assertEqual(link["resolution"]["verdict"], "match")
        self.assertEqual(link["resolution"]["author_kind"], "llm")

    def test_fabricated_citation_is_rejected(self):
        caller = _snapshot("billing", "aaa",
                            [_edge("A", "http:https://x/charge/{id}", "http_out", file="A.java", line=1)])
        callee = _snapshot("svc", "bbb",
                            [_edge("Handler", "route:POST /charge/:id", "http_in", file="H.java", line=9)])
        report = scan_links([caller, callee])
        task = build_tasks(report)[0]
        link_id = task["candidates"][0]["link_id"]

        patch = {"task_id": task["task_id"], "resolutions": [
            {"link_id": link_id, "verdict": "match", "reason": "trust me",
             "anchor": {"file": "Nonexistent.java", "line": 999}},
        ]}
        errors = validate_task_patch(patch, task)
        self.assertTrue(any("fabricated citation" in e for e in errors))

    def test_unknown_verdict_is_rejected(self):
        caller = _snapshot("billing", "aaa",
                            [_edge("A", "http:https://x/charge/{id}", "http_out", file="A.java", line=1)])
        callee = _snapshot("svc", "bbb",
                            [_edge("Handler", "route:POST /charge/:id", "http_in", file="H.java", line=9)])
        report = scan_links([caller, callee])
        task = build_tasks(report)[0]
        link_id = task["candidates"][0]["link_id"]

        patch = {"task_id": task["task_id"], "resolutions": [
            {"link_id": link_id, "verdict": "definitely", "reason": "x",
             "anchor": {"file": "A.java", "line": 1}},
        ]}
        errors = validate_task_patch(patch, task)
        self.assertTrue(any("/resolutions/0/verdict" in e for e in errors))

    def test_exact_matches_never_become_tasks(self):
        caller = _snapshot("billing", "aaa",
                            [_edge("A", "http:https://x/orders/1", "http_out", file="A.java", line=1)])
        callee = _snapshot("svc", "bbb",
                            [_edge("Handler", "route:GET /orders/1", "http_in", file="H.java", line=9)])
        report = scan_links([caller, callee])
        self.assertEqual(report["links"][0]["match_kind"], "exact")
        self.assertEqual(build_tasks(report), [])


class RefreshTest(unittest.TestCase):
    """M8.4 (5.3): a contract whose endpoint survives carries forward
    re-anchored; one whose endpoint vanished decays with a reason, and a
    repo not named in the refresh is left byte-identical (5.5)."""

    def _base(self):
        caller = _snapshot("billing", "aaa",
                            [_edge("A", "http:https://x/charge", "http_out", file="A.java", line=1)])
        callee = _snapshot("svc", "bbb",
                            [_edge("Handler", "route:POST /charge", "http_in", file="H.java", line=9)])
        return scan_links([caller, callee])

    def test_route_removed_from_caller_decays_the_link_with_a_reason(self):
        old_report = self._base()
        self.assertEqual(old_report["totals"]["links"], 1)

        # billing advances to a commit that removes the /charge call
        advanced_caller = _snapshot("billing", "ccc", [])
        report = refresh_links(old_report, [advanced_caller])

        self.assertEqual(len(report["links"]), 1)
        link = report["links"][0]
        self.assertEqual(link["status"], "decayed")
        self.assertIn("caller", link["decay_reason"])
        self.assertIn("billing", link["decay_reason"])
        # callee side (not refreshed) is untouched
        self.assertEqual(link["callee"]["repo"], "svc")
        self.assertEqual(link["callee"]["anchor"]["line"], 9)

    def test_endpoint_still_present_carries_forward_live_and_reanchors(self):
        old_report = self._base()
        # billing re-scanned at a new head, same call site moved one line
        advanced_caller = _snapshot(
            "billing", "ccc",
            [_edge("A", "http:https://x/charge", "http_out", file="A.java", line=2)],
        )
        report = refresh_links(old_report, [advanced_caller])
        self.assertEqual(len(report["links"]), 1)
        link = report["links"][0]
        self.assertEqual(link["status"], "live")
        self.assertEqual(link["caller"]["head"], "ccc")
        self.assertEqual(link["caller"]["anchor"]["line"], 2)

    def test_a_link_touching_neither_refreshed_repo_is_byte_identical(self):
        old_report = self._base()
        # refresh some unrelated third repo -- billing/svc's link must not move
        other = _snapshot("unrelated", "zzz", [])
        report = refresh_links(old_report, [other])
        self.assertEqual(report["links"], old_report["links"])

    def test_unmatched_call_from_a_non_refreshed_repo_is_left_alone(self):
        caller = _snapshot("billing", "aaa",
                            [_edge("A", "http:https://vendor.example/pay", "http_out", file="A.java", line=1)])
        old_report = scan_links([caller])
        self.assertEqual(len(old_report["unmatched"]), 1)
        other = _snapshot("unrelated", "zzz", [])
        report = refresh_links(old_report, [other])
        self.assertEqual(report["unmatched"], old_report["unmatched"])


class DispatchLinkTaskTest(unittest.TestCase):
    """Post-Phase-9 item 5: `dispatch_link_task` runs a link task through the
    same lease/retry machinery `supervisor.dispatch_scope` uses for scopes,
    against `link_task` (not `snapshot_task`, R3's non-entanglement)."""

    def setUp(self):
        import tempfile
        from cdp.store.sqlite_backend import SqliteStore

        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.backend = SqliteStore(Path(self.tmp.name) / "index.db")
        self.addCleanup(self.backend.close)
        self.prompts_dir = Path(self.tmp.name) / "prompts"
        self.prompts_dir.mkdir()

        caller = _snapshot("billing", "aaa",
                            [_edge("A", "http:https://x/charge/{id}", "http_out", file="A.java", line=1)])
        callee = _snapshot("svc", "bbb",
                            [_edge("Handler", "route:POST /charge/:id", "http_in", file="H.java", line=9)])
        self.report = scan_links([caller, callee])
        self.task = build_tasks(self.report)[0]

    def test_valid_patch_reaches_validated_and_writes_a_link_task_row(self):
        from test_supervisor import ScriptedRunner, _write
        link_id = self.task["candidates"][0]["link_id"]
        patch = {"task_id": self.task["task_id"], "resolutions": [
            {"link_id": link_id, "verdict": "match", "reason": "same endpoint",
             "anchor": {"file": "A.java", "line": 1}},
        ]}
        runner = ScriptedRunner([_write(patch)])
        row = dispatch_link_task(self.task, "run-1", runner, self.backend, self.prompts_dir)
        self.assertEqual(row["state"], "validated")
        self.assertEqual(row["attempts"], 1)
        states = self.backend.link_task_states("run-1")
        self.assertEqual(states[self.task["task_id"]]["state"], "validated")

    def test_a_fabricated_anchor_retries_then_abandons(self):
        from test_supervisor import ScriptedRunner, _write
        patch = {"task_id": self.task["task_id"], "resolutions": [
            {"link_id": "not-a-real-link", "verdict": "match", "reason": "x",
             "anchor": {"file": "A.java", "line": 1}},
        ]}
        runner = ScriptedRunner([_write(patch)])
        row = dispatch_link_task(self.task, "run-2", runner, self.backend, self.prompts_dir, max_attempts=2)
        self.assertEqual(row["state"], "abandoned")
        self.assertEqual(row["attempts"], 2)

    def test_second_supervisor_cannot_claim_a_held_lease(self):
        self.assertTrue(self.backend.acquire_link_lease("run-3", self.task["task_id"], 60))
        from test_supervisor import ScriptedRunner, _write
        runner = ScriptedRunner([_write({"task_id": self.task["task_id"], "resolutions": []})])
        row = dispatch_link_task(self.task, "run-3", runner, self.backend, self.prompts_dir)
        self.assertIsNone(row)


class LinkTaskShapeKeyTest(unittest.TestCase):
    def test_bucketed_on_protocol_and_candidate_count(self):
        task = {"protocol": "http_out", "candidates": [{}, {}, {}]}
        self.assertEqual(link_task_shape_key(task), "protocol=http_out|candidates<=4")


if __name__ == "__main__":
    unittest.main()
