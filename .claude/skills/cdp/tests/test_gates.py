"""Phase 4 (M4.2) -- the four unknown gates, unit-level and end-to-end."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

from helpers import SKILL_ROOT, make_repo

from cdp.gates import (
    ABANDONED,
    UNEXAMINED,
    UNKNOWN,
    build_extraction_index,
    cluster_unknowns,
    discharge_unknowns,
    gate_negative_entailment,
    gate_needs_valid,
    gate_patch_unknowns,
    gate_subject_exists,
    grandfather_needs,
    provenance_state,
)
from cdp.store.sqlite_backend import SqliteStore

import unittest

RUN_PY = SKILL_ROOT / "run.py"

EXTRACTION = {
    "defines": [{"fqn": "com.example.Widget", "kind": "class", "visibility": "public",
                 "anchor": {"file": "Widget.java", "line": 1}}],
    "io_edges": [{"source": "com.example.WidgetDao", "target": "widget", "channel": "persist",
                  "anchor": {"file": "WidgetDao.java", "line": 12}}],
}


class SubjectExistsTest(unittest.TestCase):
    def test_no_subject_passes_unconditionally(self):
        idx = build_extraction_index(EXTRACTION)
        self.assertIsNone(gate_subject_exists({"question": "q"}, "core", *idx[:2], {"core"}))

    def test_subject_in_defines_passes(self):
        idx = build_extraction_index(EXTRACTION)
        u = {"question": "q", "subject": "com.example.Widget"}
        self.assertIsNone(gate_subject_exists(u, "core", *idx[:2], {"core"}))

    def test_subject_in_io_edge_passes(self):
        idx = build_extraction_index(EXTRACTION)
        u = {"question": "q", "subject": "com.example.WidgetDao"}
        self.assertIsNone(gate_subject_exists(u, "core", *idx[:2], {"core"}))

    def test_subject_equal_to_scope_node_passes(self):
        """Stress test: 'why is there no retry here' about the scope itself,
        not a symbol -- the real false-positive class the plan calls out."""
        idx = build_extraction_index(EXTRACTION)
        u = {"question": "q", "subject": "core"}
        self.assertIsNone(gate_subject_exists(u, "core", *idx[:2], {"core"}))

    def test_bogus_subject_is_rejected(self):
        idx = build_extraction_index(EXTRACTION)
        u = {"question": "q", "subject": "com.example.NoSuchThing"}
        reason = gate_subject_exists(u, "core", *idx[:2], {"core"})
        self.assertIsNotNone(reason)
        self.assertIn("com.example.NoSuchThing", reason)


class NegativeEntailmentTest(unittest.TestCase):
    def test_no_subject_or_channel_passes(self):
        _, _, edges_by_key = build_extraction_index(EXTRACTION)
        self.assertIsNone(gate_negative_entailment({"question": "q"}, edges_by_key))

    def test_answered_question_is_rejected_with_the_edge_cited(self):
        _, _, edges_by_key = build_extraction_index(EXTRACTION)
        u = {"question": "what table does this write?",
             "subject": "com.example.WidgetDao", "channel": "persist"}
        reason = gate_negative_entailment(u, edges_by_key)
        self.assertIsNotNone(reason)
        self.assertIn("widget", reason)
        self.assertIn("WidgetDao.java:12", reason)

    def test_unanswered_question_passes(self):
        _, _, edges_by_key = build_extraction_index(EXTRACTION)
        u = {"question": "what does this read?",
             "subject": "com.example.WidgetDao", "channel": "read"}
        self.assertIsNone(gate_negative_entailment(u, edges_by_key))


class ProvenanceStateTest(unittest.TestCase):
    def test_no_task_row_is_unexamined(self):
        self.assertEqual(provenance_state("core", {}), UNEXAMINED)

    def test_complete_task_is_unknown(self):
        rows = {"core": {"state": "complete", "attempts": 1}}
        self.assertEqual(provenance_state("core", rows), UNKNOWN)

    def test_three_failed_attempts_is_abandoned(self):
        rows = {"core": {"state": "failed", "attempts": 3}}
        self.assertEqual(provenance_state("core", rows), ABANDONED)


class GatePatchUnknownsTest(unittest.TestCase):
    def test_mixed_batch_splits_kept_and_rejected(self):
        def_fqns, edge_subjects, edges_by_key = build_extraction_index(EXTRACTION)
        unknowns = [
            {"question": "why is there no retry here?", "why_unresolved": "no policy found",
             "subject": "core", "needs": "needs_human"},
            {"question": "what table does this write?", "why_unresolved": "agent unsure",
             "subject": "com.example.WidgetDao", "channel": "persist"},
            {"question": "what is this about?", "why_unresolved": "agent unsure",
             "subject": "com.example.Nothing"},
        ]
        kept, rejected = gate_patch_unknowns(
            unknowns, "core", def_fqns, edge_subjects, edges_by_key, {"core"},
        )
        self.assertEqual(len(kept), 1)
        self.assertEqual(kept[0]["question"], "why is there no retry here?")
        self.assertEqual(kept[0]["provenance_state"], UNEXAMINED)
        self.assertEqual(len(rejected), 2)


class NeedsGateTest(unittest.TestCase):
    def test_valid_needs_passes(self):
        self.assertIsNone(gate_needs_valid({"needs": "needs_human"}))

    def test_missing_needs_is_rejected(self):
        reason = gate_needs_valid({"question": "q"})
        self.assertIsNotNone(reason)
        self.assertIn("needs_human", reason)

    def test_bogus_needs_is_rejected(self):
        reason = gate_needs_valid({"needs": "needs_a_pony"})
        self.assertIsNotNone(reason)
        self.assertIn("needs_a_pony", reason)


class GrandfatherNeedsTest(unittest.TestCase):
    def test_missing_needs_becomes_needs_human_with_marker(self):
        rows = grandfather_needs([{"question": "q", "why_unresolved": "w"}])
        self.assertEqual(rows[0]["needs"], "needs_human")
        self.assertTrue(rows[0]["needs_migrated"])

    def test_already_valid_needs_is_untouched(self):
        rows = grandfather_needs([{"question": "q", "needs": "needs_runtime"}])
        self.assertEqual(rows[0]["needs"], "needs_runtime")
        self.assertNotIn("needs_migrated", rows[0])


class DischargeUnknownsTest(unittest.TestCase):
    """R12: an adjudicated claim discharges (`resolved`); a subject that
    stops existing is `moot`, a different outcome; silence changes nothing."""

    def test_scope_level_unknown_always_stays_open(self):
        rows = discharge_unknowns([{"question": "q", "why_unresolved": "w"}],
                                   [], set(), set(), {"core"})
        self.assertEqual(rows[0]["status"], "open")

    def test_subject_gone_is_moot_not_resolved(self):
        rows = discharge_unknowns(
            [{"question": "q", "why_unresolved": "w", "subject": "com.example.Deleted"}],
            [], set(), set(), {"core"},
        )
        self.assertEqual(rows[0]["status"], "moot")

    def test_matching_claim_resolves_with_attribution(self):
        claims = [{"id": "c1", "subject": "com.example.Widget", "channel": "persist",
                   "author_kind": "human", "claim_reviewed_at": "abc123"}]
        rows = discharge_unknowns(
            [{"question": "q", "why_unresolved": "w",
              "subject": "com.example.Widget", "channel": "persist"}],
            claims, {"com.example.Widget"}, set(), set(),
        )
        self.assertEqual(rows[0]["status"], "resolved")
        self.assertEqual(rows[0]["resolved_by"],
                          {"claim_id": "c1", "author_kind": "human", "at_snapshot": "abc123"})

    def test_contradicted_claim_does_not_resolve(self):
        claims = [{"id": "c1", "subject": "com.example.Widget", "channel": "persist",
                   "verdict": "contradicted"}]
        rows = discharge_unknowns(
            [{"question": "q", "why_unresolved": "w",
              "subject": "com.example.Widget", "channel": "persist"}],
            claims, {"com.example.Widget"}, set(), set(),
        )
        self.assertEqual(rows[0]["status"], "open")

    def test_no_matching_claim_stays_open_when_subject_still_exists(self):
        rows = discharge_unknowns(
            [{"question": "q", "why_unresolved": "w", "subject": "com.example.Widget"}],
            [], {"com.example.Widget"}, set(), set(),
        )
        self.assertEqual(rows[0]["status"], "open")


class ClusterUnknownsTest(unittest.TestCase):
    def test_matching_question_and_reason_cluster(self):
        rows = [
            {"question": "what does this endpoint call downstream?",
             "why_unresolved": "no dataflow edge found", "source_node": "a"},
            {"question": "what does this endpoint call downstream?",
             "why_unresolved": "no dataflow edge found", "source_node": "b"},
        ]
        out = cluster_unknowns(rows)
        self.assertEqual(out[0]["cluster_id"], out[1]["cluster_id"])
        self.assertEqual(out[0]["cluster_size"], 2)

    def test_shared_phrasing_with_different_reasons_does_not_cluster(self):
        """The plan's stress test: 40 legitimately distinct 'why is there no
        retry here' unknowns must not collapse into one finding."""
        rows = [
            {"question": "why is there no retry here?",
             "why_unresolved": "no RetryPolicy near PaymentClient.execute", "source_node": "a"},
            {"question": "why is there no retry here?",
             "why_unresolved": "no RetryPolicy near InventoryClient.reserve", "source_node": "b"},
        ]
        out = cluster_unknowns(rows)
        self.assertNotIn("cluster_id", out[0])
        self.assertNotIn("cluster_id", out[1])

    def test_singleton_gets_no_cluster_id(self):
        rows = [{"question": "why is there no retry here?", "why_unresolved": "x"}]
        out = cluster_unknowns(rows)
        self.assertNotIn("cluster_id", out[0])


class CollectGatesEndToEndTest(unittest.TestCase):
    """M4.2's own acceptance line: a hand-written unknown about a nonexistent
    subject is rejected, and one answerable from xref is rejected with the
    answering edge cited -- exercised through the real `collect` CLI, not the
    gate functions directly."""

    def test_collect_rejects_bad_unknowns_and_keeps_the_legitimate_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(Path(tmp))
            state = Path(tmp) / "state"
            subprocess.run(
                [sys.executable, str(RUN_PY), "scan", "--repo", str(repo),
                 "--state-dir", str(state), "--quiet"], check=True, capture_output=True)

            backend = SqliteStore(state / "index.db")
            partition = backend.read_artifact("partition")
            extraction = backend.read_artifact("extract")
            manifest = backend.read_artifact("manifest")
            scope = next(s for s in partition["scopes"] if s["file_count"] > 0)
            node = scope["node"]
            edge = extraction["io_edges"][0]
            backend.ensure_inbox()
            backend.close()

            patch = {
                "schema_version": "1.0.0",
                "node": node,
                "run_id": manifest.get("run_id", "test-run"),
                "status": "complete",
                "claims": [],
                "unknowns": [
                    {"question": "why is there no retry here?",
                     "why_unresolved": "no retry policy found near this scope",
                     "subject": node, "needs": "needs_human"},
                    {"question": "what does this already-known edge answer?",
                     "why_unresolved": "asked anyway, to prove gate 2 rejects it",
                     "subject": edge["source"], "channel": edge["channel"]},
                    {"question": "what is com.example.NoSuchSubject for?",
                     "why_unresolved": "hand-written, names nothing real",
                     "subject": "com.example.NoSuchSubject"},
                ],
            }
            (state / "patches" / "inbox" / (node.replace("/", "__") + ".json")).write_text(
                json.dumps(patch)
            )

            subprocess.run(
                [sys.executable, str(RUN_PY), "collect", "--repo", str(repo),
                 "--state-dir", str(state)], check=True, capture_output=True)

            backend = SqliteStore(state / "index.db")
            gate_report = backend.read_report("unknown_gates")
            live_state = backend.read_artifact("state")
            backend.close()

            reasons = "\n".join(r["reason"] for r in gate_report["rejected"])
            self.assertIn("com.example.NoSuchSubject", reasons)
            self.assertIn(edge["source"], reasons)
            self.assertIn(edge["channel"], reasons)
            self.assertEqual(len(gate_report["rejected"]), 2)

            kept = [u for u in live_state["unknowns"] if u.get("source_node") == node
                    and u["question"] == "why is there no retry here?"]
            self.assertEqual(len(kept), 1)
            self.assertEqual(kept[0]["provenance_state"], UNEXAMINED)


if __name__ == "__main__":
    unittest.main()
