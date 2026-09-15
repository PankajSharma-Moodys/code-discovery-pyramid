"""Partition, fold, verification, reproducibility — the invariants.

These are the properties that have to hold from the first commit because they
cannot be retrofitted: a partition that drops files produces a coverage figure
that lies, and a fold that was never pure cannot be made pure afterwards.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import SKILL_ROOT, MiniRepoTest, Pipeline, make_repo

from cdp.partition import assert_partition, partition
from cdp.state import check_order_independence, fold, fold_hash
from cdp.util import CdpError, stable_hash
from cdp.verify import LENIENT, STRICT, verify_all

RUN_PY = SKILL_ROOT / "run.py"


class TestPartition(MiniRepoTest):
    def test_every_tracked_file_lands_in_exactly_one_scope(self):
        assert_partition(self.pipeline.inventory, self.pipeline.partition["scopes"])
        seen = [p for s in self.pipeline.partition["scopes"] for p in s["files"]]
        self.assertEqual(len(seen), len(set(seen)))
        self.assertEqual(len(seen), self.pipeline.inventory["counts"]["tracked"])

    def test_a_partition_that_drops_a_file_is_rejected(self):
        scopes = json.loads(json.dumps(self.pipeline.partition["scopes"]))
        scopes[0]["files"] = scopes[0]["files"][1:]
        with self.assertRaises(CdpError):
            assert_partition(self.pipeline.inventory, scopes)

    def test_a_partition_that_claims_a_file_twice_is_rejected(self):
        scopes = json.loads(json.dumps(self.pipeline.partition["scopes"]))
        scopes.append(dict(scopes[0], node="duplicate"))
        with self.assertRaises(CdpError):
            assert_partition(self.pipeline.inventory, scopes)

    def test_a_tight_budget_forces_a_split_and_still_partitions(self):
        tight = partition(self.pipeline.inventory, max_files=2, max_loc=40)
        self.assertGreater(tight["totals"]["scopes"], self.pipeline.partition["totals"]["scopes"])
        assert_partition(self.pipeline.inventory, tight["scopes"])

    def test_a_scope_never_spans_two_modules(self):
        # A scope carries one module's DAG level into the scheduler; a mixed
        # scope would schedule the deeper module before its dependencies.
        by_path = {f["path"]: f["module"] for f in self.pipeline.inventory["files"]}
        for scope in self.pipeline.partition["scopes"]:
            self.assertEqual(len({by_path[p] for p in scope["files"]}), 1, scope["node"])

    def test_scheduling_respects_the_dependency_dag(self):
        wave_of = self.pipeline.schedule["node_wave"]
        level = self.pipeline.schedule["module_level"]
        for scope in self.pipeline.partition["scopes"]:
            if scope["module"] == "web":
                core_waves = [
                    wave_of[s["node"]] for s in self.pipeline.partition["scopes"]
                    if s["module"] == "core"
                ]
                self.assertTrue(all(wave_of[scope["node"]] > w for w in core_waves))
        self.assertLess(level["core"], level["web"])


class TestFold(MiniRepoTest):
    def _patches(self):
        return [
            {
                "schema_version": "1.0.0", "node": s["node"], "run_id": "t",
                "status": "complete",
                "claims": [c for c in self.pipeline.claims if c.get("source_node") == s["node"]],
                "unknowns": [],
            }
            for s in self.pipeline.partition["scopes"]
        ]

    def test_folding_the_same_log_twice_is_bit_identical(self):
        # Merge variance must be zero. Anything else is a defect in the
        # operator, not a low stability score.
        patches = self._patches()
        a = fold(patches, self.pipeline.xref, self.pipeline.partition)
        b = fold(patches, self.pipeline.xref, self.pipeline.partition)
        self.assertEqual(stable_hash(a), stable_hash(b))

    def test_folding_a_shuffled_log_gives_the_identical_result(self):
        self.assertEqual(
            check_order_independence(self._patches(), self.pipeline.xref, self.pipeline.partition),
            [],
        )

    def test_the_fold_hash_ignores_log_order_but_not_log_contents(self):
        patches = self._patches()
        self.assertEqual(
            fold_hash(patches, self.pipeline.xref, self.pipeline.partition),
            fold_hash(list(reversed(patches)), self.pipeline.xref, self.pipeline.partition),
        )
        changed = json.loads(json.dumps(patches))
        changed[0]["status"] = "failed"
        self.assertNotEqual(
            fold_hash(changed, self.pipeline.xref, self.pipeline.partition),
            fold_hash(patches, self.pipeline.xref, self.pipeline.partition),
        )

    def test_a_retry_supersedes_its_failed_attempt_in_either_log_order(self):
        # §3.5 retries a node in a following wave, so a node routinely has an
        # `invalid` attempt and a `complete` one. Resolving that by log position
        # is the order-dependence §5.5 forbids — and it is the worst kind,
        # because it reproduces perfectly run over run and would score 1.0 on
        # the determinism harness while silently discarding a successful retry.
        node = self.pipeline.partition["scopes"][0]["node"]
        claims = [c for c in self.pipeline.claims if c.get("source_node") == node]
        attempt = {"schema_version": "1.0.0", "node": node, "run_id": "t",
                   "status": "invalid", "error": "statement too long", "claims": []}
        retry = {"schema_version": "1.0.0", "node": node, "run_id": "t",
                 "status": "complete", "claims": claims, "unknowns": []}

        forwards = fold([attempt, retry], self.pipeline.xref, self.pipeline.partition)
        backwards = fold([retry, attempt], self.pipeline.xref, self.pipeline.partition)
        self.assertEqual(stable_hash(forwards), stable_hash(backwards))
        self.assertEqual(forwards["nodes"][node], "complete")
        self.assertNotIn(node, forwards["coverage"]["incomplete_nodes"])
        self.assertEqual(
            check_order_independence([attempt, retry], self.pipeline.xref, self.pipeline.partition),
            [],
        )

    def test_a_failed_node_becomes_a_stated_gap_not_silence(self):
        patches = self._patches()
        patches[0] = dict(patches[0], status="failed", error="context exhausted", claims=[])
        result = fold(patches, self.pipeline.xref, self.pipeline.partition)
        self.assertIn(patches[0]["node"], result["coverage"]["incomplete_nodes"])
        self.assertLess(result["coverage"]["fraction"], 1.0)
        self.assertTrue(
            any(patches[0]["node"] in u["question"] for u in result["unknowns"]),
            "a failed node must raise an unknown naming the unexamined scope",
        )

    def test_coverage_is_files_in_complete_scopes_over_tracked_files(self):
        result = fold(self._patches(), self.pipeline.xref, self.pipeline.partition)
        self.assertEqual(result["coverage"]["files_total"], 13)
        self.assertEqual(result["coverage"]["fraction"], 1.0)


class TestVerify(MiniRepoTest):
    def _patch(self, claims):
        return {"schema_version": "1.0.0", "node": "root", "run_id": "t",
                "status": "complete", "claims": claims, "unknowns": []}

    def test_real_anchors_survive(self):
        _, stats = verify_all(self.repo, [self._patch(self.pipeline.claims)], STRICT)
        self.assertEqual(stats["claims_demoted"], 0, stats["reasons"])
        self.assertEqual(stats["demotion_rate"], 0.0)

    def test_an_invented_location_for_a_true_fact_is_demoted(self):
        # The most common failure mode of a code-reading model is not
        # fabricating a fact, it is fabricating a *location* for a true fact.
        claim = json.loads(json.dumps(self.pipeline.claims[0]))
        claim["evidence"] = [{"file": claim["evidence"][0]["file"], "line": 900,
                              "anchor": "public class TotallyInvented"}]
        verified, stats = verify_all(self.repo, [self._patch([claim])], STRICT)
        self.assertEqual(stats["claims_demoted"], 1)
        self.assertEqual(stats["reasons"], {"anchor_not_found": 1})
        # Demoted, never deleted: an explicit unknown is useful output.
        self.assertEqual(verified[0]["claims"], [])
        self.assertEqual(verified[0]["unknowns"][0]["demoted_from"], claim["id"])

    def test_line_drift_inside_the_window_is_accepted_and_rewritten(self):
        claim = json.loads(json.dumps(self.pipeline.claims[0]))
        true_line = claim["evidence"][0]["line"]
        claim["evidence"][0]["line"] = true_line + 3
        verified, stats = verify_all(self.repo, [self._patch([claim])], STRICT)
        self.assertEqual(stats["claims_kept"], 1)
        self.assertEqual(verified[0]["claims"][0]["evidence"][0]["line"], true_line)
        self.assertEqual(stats["anchors_relocated"], 1)

    def test_strict_and_lenient_differ_only_on_partially_anchored_claims(self):
        claim = json.loads(json.dumps(self.pipeline.claims[0]))
        good = claim["evidence"][0]
        claim["evidence"] = [good, {"file": good["file"], "line": 1, "anchor": "not present at all"}]
        _, strict = verify_all(self.repo, [self._patch([claim])], STRICT)
        _, lenient = verify_all(self.repo, [self._patch([claim])], LENIENT)
        self.assertEqual(strict["claims_demoted"], 1)
        self.assertEqual(lenient["claims_kept"], 1)
        # PLAN.md C1: the instrumentation that makes the choice measurable
        # rather than a matter of taste.
        self.assertEqual(strict["would_survive_lenient"], 1)


class TestReproducible(unittest.TestCase):
    """The reproducibility gate: run the deterministic phases twice at the same
    commit and assert byte-identical output. Drift is a bug, not a low score."""

    def test_two_scans_of_one_commit_are_byte_identical(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(Path(tmp))
            digests = []
            for run in ("a", "b"):
                state = Path(tmp) / run
                subprocess.run(
                    [sys.executable, str(RUN_PY), "scan", "--repo", str(repo),
                     "--state-dir", str(state), "--quiet"],
                    check=True, capture_output=True,
                )
                # manifest.json is the only state file carrying wall-clock and
                # is excluded for exactly that reason.
                digests.append({
                    p.name: p.read_bytes()
                    for p in sorted(state.rglob("*.json"))
                    if p.name != "manifest.json"
                })
            self.assertEqual(sorted(digests[0]), sorted(digests[1]))
            for name in digests[0]:
                self.assertEqual(digests[0][name], digests[1][name],
                                 "%s differs between two runs at the same commit" % name)

    def test_fold_check_passes_on_a_fresh_scan(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(Path(tmp))
            state = Path(tmp) / "state"
            subprocess.run(
                [sys.executable, str(RUN_PY), "scan", "--repo", str(repo),
                 "--state-dir", str(state), "--quiet"], check=True, capture_output=True)
            proc = subprocess.run(
                [sys.executable, str(RUN_PY), "fold", "--check", "--repo", str(repo),
                 "--state-dir", str(state)], capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def test_a_hand_edit_to_state_json_is_detected(self):
        # Nothing may enter state.json that is not derivable from the log.
        # Silent divergence between a fact and its provenance is the exact
        # failure this project is organised against.
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(Path(tmp))
            state = Path(tmp) / "state"
            subprocess.run(
                [sys.executable, str(RUN_PY), "scan", "--repo", str(repo),
                 "--state-dir", str(state), "--quiet"], check=True, capture_output=True)
            path = state / "state.json"
            doc = json.loads(path.read_text())
            doc["claims"].append({"id": "hand.patched", "kind": "naming",
                                  "subject": "x", "statement": "Written by hand.",
                                  "evidence": [], "confidence": "high"})
            path.write_text(json.dumps(doc, indent=2, sort_keys=True))
            proc = subprocess.run(
                [sys.executable, str(RUN_PY), "fold", "--check", "--repo", str(repo),
                 "--state-dir", str(state)], capture_output=True, text=True)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("not derivable", proc.stdout)


class TestCli(unittest.TestCase):
    def test_query_answers_from_a_fresh_scan(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(Path(tmp))
            state = Path(tmp) / "state"
            subprocess.run(
                [sys.executable, str(RUN_PY), "scan", "--repo", str(repo),
                 "--state-dir", str(state), "--quiet"], check=True, capture_output=True)

            def query(*args):
                proc = subprocess.run(
                    [sys.executable, str(RUN_PY), "query", *args, "--repo", str(repo),
                     "--state-dir", str(state)], capture_output=True, text=True, check=True)
                return proc.stdout

            self.assertIn("/v1/widgets", query("routes"))
            self.assertIn("widget", query("table"))
            self.assertIn("com.example.mini.core.Widget", query("symbol", "Widget"))
            self.assertIn("core", query("module", "core"))
            self.assertIn("mini-svc", query("stats"))
            # Every answer carries citations.
            self.assertIn("WidgetResource.java:", query("routes"))

    def test_docs_render_without_an_agent_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(Path(tmp))
            state = Path(tmp) / "state"
            for cmd in (["scan", "--quiet"], ["docs"]):
                subprocess.run(
                    [sys.executable, str(RUN_PY)] + cmd + ["--repo", str(repo),
                     "--state-dir", str(state)], check=True, capture_output=True)
            overview = (state / "docs" / "00-overview.md").read_text()
            self.assertIn("mini-svc", overview)
            self.assertIn("/v1/widgets", overview)
            self.assertTrue((state / "docs" / "unknowns.md").exists())
            self.assertTrue((state / "docs" / "CLAUDE.md").exists())
            self.assertTrue((state / "docs" / "modules" / "core.md").exists())

    def test_prompts_are_written_for_every_scope(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(Path(tmp))
            state = Path(tmp) / "state"
            for cmd in (["scan", "--quiet"], ["prompts"]):
                subprocess.run(
                    [sys.executable, str(RUN_PY)] + cmd + ["--repo", str(repo),
                     "--state-dir", str(state)], check=True, capture_output=True)
            prompts = sorted((state / "prompts").glob("*.md"))
            scopes = json.loads((state / "partition.json").read_text())["scopes"]
            self.assertEqual(len(prompts), len(scopes))
            text = prompts[0].read_text()
            self.assertIn("read these files and only these files", text)
            self.assertIn("Structure already extracted", text)


if __name__ == "__main__":
    unittest.main()
