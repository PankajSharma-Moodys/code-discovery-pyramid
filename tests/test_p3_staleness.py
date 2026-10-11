"""P3: staleness is detected (C3) and failures are visible (L9, M3), coverage is honest (D6, K3)."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import repo_layouts as L
from repo_layouts import Cdp

from cdp import freshness

A = "a/src/main/java/com/example/a/Alpha.java"


def model_claim(cid, statement):
    return {"id": cid, "kind": "naming", "subject": "com.example.a.Alpha", "confidence": "high",
            "statement": statement, "evidence": [{"file": A, "line": 3, "anchor": "public class Alpha {"}]}


class CountClaimTest(unittest.TestCase):
    def test_what_counts_as_a_count_claim(self):
        yes = ["77 files declare a package path that matches the directory.", "Imported at 12 call sites.",
               "The module holds 3 entity classes.", "1,204 tests run in CI."]
        no = ["Alpha is the entry point.", "Targets Java 17.", "Returns HTTP 404 when absent.",
              "Version 2 of the API.", "Alpha#go delegates to Beta."]
        self.assertEqual([c for c in yes if not freshness.is_count_claim({"statement": c})], [])
        self.assertEqual([c for c in no if freshness.is_count_claim({"statement": c})], [])


@L.needs_git
class StaleCountClaimTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)

    def freshness(self, cdp):
        return json.loads(cdp.run("status", "--json").stdout)["freshness"]

    def test_c3_a_count_claim_goes_stale_when_any_file_in_its_scope_changes(self):
        repo = L.multi_module(self.tmp)
        cdp = Cdp(self.tmp, repo.path)
        cdp.scan()
        cdp.inject_model_patch("root/a", [model_claim("t.count", "2 files in module a belong to Alpha's package."),
                                          model_claim("t.plain", "Alpha is the entry point of module a.")])
        self.assertEqual(self.freshness(cdp)["stale"], 0)
        # a file of the scope that neither claim cites
        repo.write("a/pom.xml", repo.read("a/pom.xml") + "<!-- touched -->\n")
        repo.commit("touch the scope's pom")
        cdp.refresh()
        fresh = self.freshness(cdp)
        self.assertEqual(fresh["stale"], 1, "only the count claim: its evidence file is untouched")
        # a change in another scope leaves it alone
        cdp2 = Cdp(self.tmp, repo.path, home=cdp.home)
        repo.write("b/pom.xml", repo.read("b/pom.xml") + "<!-- other scope -->\n")
        repo.commit("touch another scope")
        cdp2.refresh()
        self.assertEqual(self.freshness(cdp)["stale"], 1)


FAILING = "import sys; sys.exit(3)"
HALF = """\
import json, sys
from pathlib import Path
patch = Path(sys.argv[2])
node = patch.stem.replace('__', '/')
if node.endswith('/a'):
    sys.exit(3)
patch.write_text(json.dumps({'schema_version': '1.0.0', 'node': node, 'run_id': 'x', 'status': 'complete',
    'claims': [], 'unknowns': [{'question': 'what is here?', 'why_unresolved': 'fake', 'needs': 'needs_human'}]}))
"""
GOOD = HALF.replace("node.endswith('/a')", "False")


@L.needs_git
class ExitCodesTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.repo = L.multi_module(self.tmp)
        self.cdp = Cdp(self.tmp, self.repo.path)
        self.cdp.scan()

    def run_with(self, source, *extra):
        script = self.tmp / "runner.py"
        script.write_text(source)
        import sys
        return self.cdp.run("run", "--wave-all", "--max-attempts", "1", "--runner-cmd",
                            "%s %s" % (sys.executable, script), *extra, check=False)

    def test_l9_run_exits_1_when_every_scope_fails(self):
        proc = self.run_with(FAILING)
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("0 accepted", proc.stdout)

    def test_l9_run_exits_3_when_some_scopes_fail_and_0_when_none(self):
        proc = self.run_with(HALF)
        self.assertEqual(proc.returncode, 3, proc.stdout + proc.stderr)
        self.assertRegex(proc.stdout, r"\d+ accepted, \d+ abandoned or rejected")
        self.assertEqual(self.run_with(GOOD, "--resume").returncode, 0)

    def test_l9_doctor_exits_1_when_the_runner_always_crashes(self):
        import sys
        script = self.tmp / "crash.py"
        script.write_text(FAILING)
        proc = self.cdp.run("doctor", "--model", "crashy", "--runner-cmd", "%s %s" % (sys.executable, script),
                            check=False)
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("runner failure", proc.stdout)


@L.needs_git
class ModelReviewedCoverageTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)

    def test_k3_d6_a_bare_scan_has_no_model_review_and_root_is_not_complete(self):
        from cdp.state import model_reviewed_coverage
        repo = L.multi_module(self.tmp)
        cdp = Cdp(self.tmp, repo.path)
        cdp.scan()
        status = json.loads(cdp.run("status", "--json").stdout)
        self.assertEqual(status["coverage"]["fraction"], 0.0)
        self.assertIsNone(status["coverage"]["model_reviewed_fraction"])
        self.assertIsNone(model_reviewed_coverage(cdp.artifacts(("manifest",)) and
                                                  json.loads(cdp.run("query", "coverage", "--json").stdout)["coverage"]))
        nodes = json.loads(cdp.run("query", "coverage", "--json").stdout)["nodes"]
        self.assertNotIn("complete", nodes.values())
        cdp.inject_model_patch("root/a", [model_claim("t.a", "Alpha is the entry point of module a.")])
        status = json.loads(cdp.run("status", "--json").stdout)
        self.assertGreater(status["coverage"]["model_reviewed_fraction"], 0)


@L.needs_git
class ClaimScreenTest(unittest.TestCase):
    """L4, L15, K2: a bad claim costs only itself."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)

    def test_bad_claims_are_rejected_alone_and_the_good_one_is_kept(self):
        repo = L.multi_module(self.tmp)
        repo.write("a/src/test/java/com/example/a/AlphaTest.java",
                   "package com.example.a;\n\npublic class AlphaTest {\n    void t() { new Alpha(); }\n}\n")
        repo.commit("add a test")
        cdp = Cdp(self.tmp, repo.path)
        cdp.scan()
        cdp.run("prompts")
        backend, store = cdp.open()
        run_id = store.manifest["run_id"]
        backend.ensure_inbox()
        inbox = backend._inbox_dir()
        backend.close()
        good = model_claim("t.good", "Alpha is the entry point of module a.")
        long_ = model_claim("t.long", "x" * 512)
        outside = model_claim("t.outside", "Beta is described from the wrong scope.")
        outside["subject"] = "com.example.b.Beta"
        outside["evidence"] = [{"file": "b/src/main/java/com/example/b/Beta.java", "line": 3,
                                "anchor": "public class Beta {"}]
        ghost = model_claim("t.ghost", "A class that is not anywhere in this repo.")
        ghost["subject"] = "com.example.a.Nonexistent"
        from_test = model_claim("t.test", "Alpha is constructed by production code paths.")
        from_test["evidence"] = [{"file": "a/src/test/java/com/example/a/AlphaTest.java", "line": 3,
                                  "anchor": "public class AlphaTest {"}]
        patch = {"schema_version": "1.0.0", "node": "root/a", "run_id": run_id, "status": "complete",
                 "unknowns": [], "claims": [good, long_, outside, ghost, from_test]}
        (inbox / "root__a.json").write_text(json.dumps(patch))
        out = cdp.run("collect").stdout
        for cid in ("t.long", "t.outside", "t.ghost", "t.test"):
            self.assertIn("REJECTED claim %s" % cid, out)
        self.assertIn("accepted  1", out)
        backend, _ = cdp.open()
        ids = {c["id"] for c in backend.read_artifact("state")["claims"]}
        backend.close()
        self.assertIn("t.good", ids)
        self.assertEqual(ids & {"t.long", "t.outside", "t.ghost", "t.test"}, set())


class NegationConflictTest(unittest.TestCase):
    def claim(self, cid, statement, node):
        return {"id": cid, "kind": "naming", "subject": "com.example.Server", "confidence": "high",
                "statement": statement, "source_node": node,
                "evidence": [{"file": "S.java", "line": 3, "anchor": "public class Server {"}]}

    def test_k1_a_denial_and_an_assertion_about_one_subject_are_a_conflict(self):
        from cdp.merge import merge_claims
        denies = self.claim("a.one", "The Server entity states no table name.", "root/a")
        asserts = self.claim("b.one", "The Server entity maps to the table name server.", "root/b")
        merged = merge_claims([denies, asserts], {})
        self.assertEqual(len(merged["conflicts"]), 1)
        self.assertEqual(merged["conflicts"][0]["reason"], "negation")

    def test_k1_agreeing_or_unrelated_statements_are_not_conflicts(self):
        from cdp.merge import merge_claims
        one = self.claim("a.one", "The Server entity maps to the table name server.", "root/a")
        two = self.claim("b.one", "The Server entity is mapped onto the table name server too.", "root/b")
        three = self.claim("c.one", "There is no retry logic anywhere.", "root/c")
        self.assertEqual(merge_claims([one, two, three], {})["conflicts"], [])


@L.needs_git
class ResumeAfterKillTest(unittest.TestCase):
    def test_l6_resume_reruns_a_scope_a_killed_run_left_dispatched(self):
        import sys
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        tmp = Path(tmp.name)
        repo = L.multi_module(tmp)
        cdp = Cdp(tmp, repo.path)
        cdp.scan()
        script = tmp / "runner.py"
        script.write_text(GOOD)
        cmd = ["run", "--wave-all", "--runner-cmd", "%s %s" % (sys.executable, script)]
        cdp.run(*cmd)
        backend, store = cdp.open()
        run_id = store.manifest["run_id"]
        victim = next(s for s in store.partition["scopes"] if s["node"] == "root/a")["scope_hash"]
        backend.upsert_task(run_id, victim, state="dispatched")
        self.assertTrue(backend.acquire_lease(run_id, victim, 90))   # the dead run's lease, still unexpired
        backend.close()
        out = cdp.run(*cmd, "--resume").stdout
        self.assertIn("reclaimed 1 task(s)", out)
        backend, _ = cdp.open()
        states = backend.task_states(run_id)
        backend.close()
        self.assertEqual(states[victim]["state"], "folded")


@L.needs_git
class StatusDuringRunTest(unittest.TestCase):
    def test_l12_status_works_while_a_run_is_in_flight(self):
        import subprocess, sys, time
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        tmp = Path(tmp.name)
        repo = L.multi_module(tmp)
        cdp = Cdp(tmp, repo.path)
        cdp.scan()
        script = tmp / "slow.py"
        script.write_text("import time\ntime.sleep(4)\n" + GOOD)
        from repo_layouts import RUN_PY
        import os
        proc = subprocess.Popen(
            [sys.executable, str(RUN_PY), "run", "--wave-all", "--repo", str(repo.path), "--state-dir", str(cdp.home),
             "--runner-cmd", "%s %s" % (sys.executable, script)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=dict(os.environ, CDP_HOME=str(cdp.home)))
        self.addCleanup(proc.kill)
        time.sleep(1.5)
        started = time.monotonic()
        status = cdp.run("status", check=False)
        self.assertEqual(status.returncode, 0, status.stderr)
        self.assertLess(time.monotonic() - started, 3.5, "status waited for the run")
        self.assertIsNone(proc.poll(), "the run should still be going")
        out, err = proc.communicate(timeout=120)
        self.assertEqual(proc.returncode, 0, out.decode() + err.decode())


USAGE_RUNNER = GOOD + """
Path(sys.argv[2]).with_suffix('.usage').write_text(json.dumps(
    {'total_cost_usd': 0.25, 'duration_ms': 1234, 'usage': {'input_tokens': 100, 'output_tokens': 40}}))
"""


@L.needs_git
class LeafCostTest(unittest.TestCase):
    def test_l14_the_trajectory_records_wall_time_and_the_cost_a_runner_reports(self):
        import os, sys
        from unittest import mock
        from cdp.trajectory import TrajectoryStore
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        tmp = Path(tmp.name)
        repo = L.multi_module(tmp)
        cdp = Cdp(tmp, repo.path)
        cdp.scan()
        script = tmp / "runner.py"
        script.write_text(USAGE_RUNNER)
        cdp.run("run", "--wave-all", "--runner-cmd", "%s %s" % (sys.executable, script))
        run_id = cdp.artifacts(("manifest",))["manifest"]["run_id"]
        with mock.patch.dict(os.environ, {"CDP_HOME": str(cdp.home)}):
            with TrajectoryStore() as store:
                rows = store.leaf_runs_for(run_id)
        self.assertTrue(rows)
        self.assertTrue(all(r["wall_ms"] is not None for r in rows), rows)
        self.assertEqual({r["cost_usd"] for r in rows}, {0.25})
        self.assertFalse(list(cdp.home.rglob("*.usage")), "the usage file is not left in the inbox")


@L.needs_git
class StaleOnlyConvergesTest(unittest.TestCase):
    def test_l7_a_second_stale_only_run_finds_nothing_to_do(self):
        import sys
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        tmp = Path(tmp.name)
        repo = L.multi_module(tmp)
        cdp = Cdp(tmp, repo.path)
        cdp.scan()
        script = tmp / "runner.py"
        script.write_text(GOOD)
        runner = "%s %s" % (sys.executable, script)
        cdp.run("run", "--wave-all", "--runner-cmd", runner)
        cdp.inject_model_patch("root/a", [model_claim("t.count", "2 files in module a belong to Alpha's package.")])
        repo.write("a/pom.xml", repo.read("a/pom.xml") + "<!-- touched -->\n")
        repo.commit("touch the scope")
        cdp.refresh()
        first = cdp.run("run", "--stale-only", "--runner-cmd", runner).stdout
        self.assertNotIn("zero scopes need review", first)
        second = cdp.run("run", "--stale-only", "--runner-cmd", runner).stdout
        self.assertIn("zero scopes need review", second)


class LessonBoundsTest(unittest.TestCase):
    def test_l10_absurd_promotions_are_rejected(self):
        from cdp.reflect import validate_promotion
        self.assertIn("outside the sane range", validate_promotion(
            {"promotion": "budget_change", "parameter": "max_inherited", "new_value": -999999}))
        self.assertIn("too broad", validate_promotion(
            {"promotion": "import_channel_hint", "pattern": "*", "channel": "db"}))
        self.assertIsNone(validate_promotion(
            {"promotion": "budget_change", "parameter": "max_inherited", "new_value": 150}))
        self.assertIsNone(validate_promotion(
            {"promotion": "import_channel_hint", "pattern": "org.acme.driver", "channel": "db"}))

    def test_l10_a_cut_applies_by_default_only_to_the_repos_it_learned_from_or_was_validated_on(self):
        from cdp.trajectory import TrajectoryStore
        with tempfile.TemporaryDirectory() as tmp:
            with TrajectoryStore(Path(tmp) / "t.db") as store:
                store.record_leaf_run(run_id="r1", node="root/a", scope_hash="h", repo_id="repo-A", model="m",
                                      scope_shape_key="k", template_version=None, tier=None, task_kind="scope",
                                      state="validated")
                store.record_promotion(run_id="r1", node="root/a", promotion={
                    "promotion": "import_channel_hint", "pattern": "org.acme.driver", "channel": "db"})
                version = store.cut_lessons()
                store.promote_cut(version, "repo-B", {})
                self.assertEqual(store.latest_lesson_version("repo-A"), version)
                self.assertEqual(store.latest_lesson_version("repo-B"), version)
                self.assertIsNone(store.latest_lesson_version("repo-C"))
