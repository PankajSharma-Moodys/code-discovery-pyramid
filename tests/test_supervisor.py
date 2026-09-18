"""Phase 5 (M5.2/M5.3) -- the task state machine and `cdp run`'s wave loop."""

from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

from helpers import SKILL_ROOT, Pipeline, make_repo

from cdp import query as query_mod
from cdp import supervisor as supervisor_mod
from cdp.runner import RunResult
from cdp.schema import Validator, schema_path
from cdp.store.sqlite_backend import SqliteStore

RUN_PY = SKILL_ROOT / "run.py"


class ScriptedRunner:
    """Test double for the runner protocol (`cdp/runner.py`): one `action`
    per attempt, the last one repeats if more attempts happen than actions."""

    def __init__(self, actions):
        self.actions = list(actions)
        self.calls = 0

    def run(self, prompt_path: Path, patch_path: Path) -> RunResult:
        action = self.actions[min(self.calls, len(self.actions) - 1)]
        self.calls += 1
        return action(patch_path)


def _fail(error: str):
    return lambda patch_path: RunResult(ok=False, wall_ms=1, error=error)


def _write(patch: dict):
    def action(patch_path: Path) -> RunResult:
        patch_path.write_text(json.dumps(patch))
        return RunResult(ok=True, wall_ms=1)
    return action


def _write_raw(text: str):
    def action(patch_path: Path) -> RunResult:
        patch_path.write_text(text)
        return RunResult(ok=True, wall_ms=1)
    return action


class SupervisorTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        cls.repo = make_repo(Path(cls.tmp.name))
        cls.pipeline = Pipeline(cls.repo)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def setUp(self) -> None:
        self.state_tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.state_tmp.cleanup)
        state_dir = Path(self.state_tmp.name)
        self.backend = SqliteStore(state_dir / "index.db")
        self.addCleanup(self.backend.close)
        self.backend.write_artifact("inventory", self.pipeline.inventory)
        self.backend.write_artifact("extract", self.pipeline.extraction)
        self.backend.write_artifact("partition", self.pipeline.partition)
        self.backend.write_artifact("xref", self.pipeline.xref)
        self.backend.write_artifact("schedule", self.pipeline.schedule)
        self.backend.write_artifact("manifest", {"run_id": "cdp-test"})
        self.backend.ensure_inbox()
        self.store = query_mod.Store(self.backend)
        self.validator = Validator.load(schema_path(SKILL_ROOT))
        self.prompts_dir = state_dir / "prompts"
        self.prompts_dir.mkdir()
        self.run_id = "cdp-test"
        self.backend.begin_run(self.run_id)

        self.scope = next(s for s in self.pipeline.partition["scopes"] if s["file_count"] > 0)
        self.node = self.scope["node"]
        claim = next(c for c in self.pipeline.claims if c.get("source_node") == self.node)
        self.claim = copy.deepcopy(claim)

    def _dispatch(self, runner) -> dict:
        history: list = []
        orig = self.backend.upsert_task

        def spy(run_id, scope_hash, **fields):
            history.append(dict(fields))
            return orig(run_id, scope_hash, **fields)

        self.backend.upsert_task = spy
        result = supervisor_mod.dispatch_scope(
            self.scope, self.store.inventory, self.store.extraction, self.store.xref,
            self.store._load("schedule"), [], self.run_id, runner, self.backend,
            self.prompts_dir, self.validator, self.repo,
        )
        result["_history"] = history
        return result

    def _valid_patch(self, claim: dict) -> dict:
        return {
            "schema_version": "1.0.0", "node": self.node, "run_id": self.run_id,
            "status": "complete", "claims": [claim], "unknowns": [],
        }

    def test_expired_invalid_empty_then_abandoned(self):
        runner = ScriptedRunner([
            _fail("timed out"),
            _write_raw("not valid json"),
            _write({"schema_version": "1.0.0", "node": self.node, "run_id": self.run_id,
                    "status": "complete", "claims": [], "unknowns": []}),
        ])
        result = self._dispatch(runner)
        self.assertEqual(result["state"], supervisor_mod.ABANDONED)
        self.assertEqual(result["attempts"], supervisor_mod.MAX_ATTEMPTS)
        states = [h["state"] for h in result["_history"] if "state" in h]
        for expected in (supervisor_mod.DISPATCHED, supervisor_mod.EXPIRED, supervisor_mod.RETURNED,
                         supervisor_mod.INVALID, supervisor_mod.EMPTY, supervisor_mod.ABANDONED):
            self.assertIn(expected, states, "expected %r reachable in %r" % (expected, states))

    def test_anchors_failed_then_recovers_to_validated_then_folded(self):
        fabricated = copy.deepcopy(self.claim)
        # STRICT mode demotes a claim the moment any one evidence anchor fails
        # to verify (`verify.py`: `survives = bool(good) and not failures`) --
        # corrupting the first is enough to force total demotion.
        fabricated["evidence"][0]["line"] = 999999
        runner = ScriptedRunner([
            _write(self._valid_patch(fabricated)),
            _write(self._valid_patch(self.claim)),
        ])
        result = self._dispatch(runner)
        self.assertEqual(result["state"], supervisor_mod.VALIDATED)
        self.assertEqual(result["attempts"], 2)
        self.assertIsNotNone(result["patch"])
        states = [h["state"] for h in result["_history"] if "state" in h]
        self.assertIn(supervisor_mod.ANCHORS_FAILED, states)
        self.assertIn(supervisor_mod.VALIDATED, states)

        supervisor_mod.mark_folded(self.backend, self.run_id, [result])
        rows = self.backend.task_states(self.run_id)
        self.assertEqual(rows[result["scope_hash"]]["state"], supervisor_mod.FOLDED)


class LeaseTest(unittest.TestCase):
    """M5.4 (4.5) -- leases are held by the supervisor, not the leaf. All
    lease durations here are milliseconds, not `LEASE_SECONDS`/
    `HEARTBEAT_SECONDS`'s real 90s/30s -- the mechanism is the same at any
    duration, and the stress tests need to run in a fraction of a second."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db_path = Path(self.tmp.name) / "index.db"
        self.backend = SqliteStore(self.db_path)
        self.addCleanup(self.backend.close)
        self.backend.begin_run("run-a")

    def test_acquisition_is_atomic_two_supervisors_second_takes_nothing(self):
        self.assertTrue(self.backend.acquire_lease("run-a", "scope-1", 60))
        second = SqliteStore(self.db_path)
        self.addCleanup(second.close)
        self.assertFalse(second.acquire_lease("run-a", "scope-1", 60))

    def test_release_lets_a_second_supervisor_take_it_immediately(self):
        self.assertTrue(self.backend.acquire_lease("run-a", "scope-1", 60))
        self.backend.release_lease("run-a", "scope-1")
        self.assertTrue(self.backend.acquire_lease("run-a", "scope-1", 60))

    def test_expired_lease_is_reclaimable_supervisor_death_detected(self):
        # No release, no heartbeat: this simulates the supervisor holding the
        # lease having died outright.
        self.assertTrue(self.backend.acquire_lease("run-a", "scope-1", 0.05))
        time.sleep(0.15)
        self.assertTrue(self.backend.acquire_lease("run-a", "scope-1", 60))

    def test_heartbeat_keeps_a_live_holders_lease_from_being_reclaimed(self):
        self.assertTrue(self.backend.acquire_lease("run-a", "scope-1", 0.15))
        second = SqliteStore(self.db_path)
        self.addCleanup(second.close)
        heartbeat = supervisor_mod._LeaseHeartbeat(
            lambda: self.backend.heartbeat_lease("run-a", "scope-1", 0.15), 0.05
        ).start()
        try:
            time.sleep(0.3)  # longer than the original lease -- only survives via renewal
            self.assertFalse(second.acquire_lease("run-a", "scope-1", 60))
        finally:
            heartbeat.stop()
        time.sleep(0.25)  # heartbeats stopped -- the lease now expires like any dead process'
        self.assertTrue(second.acquire_lease("run-a", "scope-1", 60))


class HangingRunnerLeaseTest(unittest.TestCase):
    """The stress test named by name in `phase_5_plan.md`: 'Runner hangs
    forever. Lease expiry is the only thing that saves the run.' Drives real
    `dispatch_scope` with a runner that blocks for longer than one lease
    period, and confirms via a second, independent `SqliteStore` connection
    that the scope stays un-reclaimable throughout -- proving the heartbeat
    thread, not just the initial acquisition, is what keeps a genuinely long
    call safe from being double-dispatched by another supervisor."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        cls.repo = make_repo(Path(cls.tmp.name))
        cls.pipeline = Pipeline(cls.repo)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def setUp(self) -> None:
        self.state_tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.state_tmp.cleanup)
        self.state_dir = Path(self.state_tmp.name)
        self.db_path = self.state_dir / "index.db"
        self.backend = SqliteStore(self.db_path)
        self.addCleanup(self.backend.close)
        for name, artifact in (
            ("inventory", self.pipeline.inventory), ("extract", self.pipeline.extraction),
            ("partition", self.pipeline.partition), ("xref", self.pipeline.xref),
            ("schedule", self.pipeline.schedule),
        ):
            self.backend.write_artifact(name, artifact)
        self.backend.write_artifact("manifest", {"run_id": "cdp-test"})
        self.backend.ensure_inbox()
        self.store = query_mod.Store(self.backend)
        self.validator = Validator.load(schema_path(SKILL_ROOT))
        self.prompts_dir = self.state_dir / "prompts"
        self.prompts_dir.mkdir()
        self.run_id = "cdp-test"
        self.backend.begin_run(self.run_id)
        self.scope = next(s for s in self.pipeline.partition["scopes"] if s["file_count"] > 0)
        self.scope_hash = self.scope.get("scope_hash") or self.scope["node"]
        claim = next(c for c in self.pipeline.claims if c.get("source_node") == self.scope["node"])
        self.claim = copy.deepcopy(claim)

    def test_lease_survives_a_slow_runner_and_frees_immediately_after(self):
        node, run_id, claim = self.scope["node"], self.run_id, self.claim

        class SlowRunner:
            def run(self, prompt_path: Path, patch_path: Path) -> RunResult:
                time.sleep(0.35)
                patch_path.write_text(json.dumps({
                    "schema_version": "1.0.0", "node": node, "run_id": run_id,
                    "status": "complete", "claims": [claim], "unknowns": [],
                }))
                return RunResult(ok=True, wall_ms=350)

        probe = SqliteStore(self.db_path)
        self.addCleanup(probe.close)
        held_at_midpoint = {}

        def worker():
            held_at_midpoint["result"] = supervisor_mod.dispatch_scope(
                self.scope, self.store.inventory, self.store.extraction, self.store.xref,
                self.store._load("schedule"), [], self.run_id, SlowRunner(), self.backend,
                self.prompts_dir, self.validator, self.repo,
                lease_seconds=0.15, heartbeat_seconds=0.05,
            )

        thread = threading.Thread(target=worker)
        thread.start()
        time.sleep(0.25)  # after the first lease period would have expired unrenewed
        self.assertFalse(probe.acquire_lease(self.run_id, self.scope_hash, 60),
                          "a second supervisor must not be able to steal a scope a live "
                          "process is still (heartbeat-)holding the lease for")
        thread.join(timeout=5)
        self.assertFalse(thread.is_alive())
        self.assertEqual(held_at_midpoint["result"]["state"], supervisor_mod.VALIDATED)
        # Lease released on terminal outcome -- a second supervisor picking up
        # the *next* scope should not have to wait out the rest of the period.
        self.assertTrue(probe.acquire_lease(self.run_id, self.scope_hash, 60))


class RunCommandEndToEndTest(unittest.TestCase):
    """M5.3's own acceptance line, driven through the real `cdp run` CLI."""

    FAKE_RUNNER = (
        "import json, sys\n"
        "from pathlib import Path\n"
        "patch_path = Path(sys.argv[2])\n"
        "node = patch_path.stem.replace('__', '/')\n"
        "patch = {'schema_version': '1.0.0', 'node': node, 'run_id': 'test-run',\n"
        "         'status': 'complete', 'claims': [],\n"
        "         'unknowns': [{'question': 'what is here?',\n"
        "                       'why_unresolved': 'fake runner never knows',\n"
        "                       'needs': 'needs_human'}]}\n"
        "patch_path.write_text(json.dumps(patch))\n"
    )

    def test_wave_dispatch_folds_and_marks_tasks_folded(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(Path(tmp))
            state = Path(tmp) / "state"
            subprocess.run(
                [sys.executable, str(RUN_PY), "scan", "--repo", str(repo),
                 "--state-dir", str(state), "--quiet"], check=True, capture_output=True)
            script = Path(tmp) / "fake_runner.py"
            script.write_text(self.FAKE_RUNNER)

            subprocess.run(
                [sys.executable, str(RUN_PY), "run", "--repo", str(repo), "--state-dir", str(state),
                 "--wave", "0", "--runner-cmd", "%s %s" % (sys.executable, script)],
                check=True, capture_output=True, text=True,
            )

            backend = SqliteStore(state / "index.db")
            run_id = backend.read_artifact("manifest").get("run_id")
            rows = backend.task_rows(run_id)
            state_json = backend.read_artifact("state")
            backend.close()

            self.assertTrue(rows, "expected wave 0 to dispatch at least one scope")
            self.assertTrue(all(r["state"] == "folded" for r in rows), rows)
            self.assertGreaterEqual(len(state_json["unknowns"]), 1)

    def test_resume_reclaims_expired_and_leaves_folded_alone(self):
        """M5.5's crash-and-resume acceptance line at fixture scale: a scope
        already `folded` stays untouched by `--resume`, and one whose lease
        lapsed mid-dispatch (simulated crash) is reclaimed and re-dispatched
        under the *same* run, because the partition has not moved."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(Path(tmp))
            state = Path(tmp) / "state"
            subprocess.run(
                [sys.executable, str(RUN_PY), "scan", "--repo", str(repo),
                 "--state-dir", str(state), "--quiet"], check=True, capture_output=True)
            script = Path(tmp) / "fake_runner.py"
            script.write_text(self.FAKE_RUNNER)
            runner_cmd = "%s %s" % (sys.executable, script)

            subprocess.run(
                [sys.executable, str(RUN_PY), "run", "--repo", str(repo), "--state-dir", str(state),
                 "--wave-all", "--runner-cmd", runner_cmd],
                check=True, capture_output=True, text=True,
            )

            backend = SqliteStore(state / "index.db")
            run_id = backend.read_artifact("manifest").get("run_id")
            folded_before = {r["scope_hash"] for r in backend.task_rows(run_id) if r["state"] == "folded"}
            self.assertTrue(folded_before, "expected at least one folded scope after the first run")
            simulated_crash_hash = next(iter(folded_before))
            # Simulate a crash mid-dispatch: one already-folded scope is force-set
            # back to `dispatched` with a lapsed lease, standing in for a task the
            # first run genuinely left in flight when its supervisor died.
            backend.upsert_task(run_id, simulated_crash_hash, state="dispatched",
                                 lease_until="2000-01-01T00:00:00+00:00")
            backend.close()

            result = subprocess.run(
                [sys.executable, str(RUN_PY), "run", "--repo", str(repo), "--state-dir", str(state),
                 "--wave-all", "--runner-cmd", runner_cmd, "--resume"],
                check=True, capture_output=True, text=True,
            )
            self.assertIn("reclaimed 1 task(s) past lease", result.stdout)

            backend = SqliteStore(state / "index.db")
            rows = backend.task_rows(run_id)
            backend.close()
            self.assertTrue(all(r["state"] == "folded" for r in rows), rows)

    def test_resume_with_changed_partition_opens_a_new_run_inheriting_unchanged_scopes(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(Path(tmp))
            state = Path(tmp) / "state"
            subprocess.run(
                [sys.executable, str(RUN_PY), "scan", "--repo", str(repo),
                 "--state-dir", str(state), "--quiet"], check=True, capture_output=True)
            script = Path(tmp) / "fake_runner.py"
            script.write_text(self.FAKE_RUNNER)
            runner_cmd = "%s %s" % (sys.executable, script)

            subprocess.run(
                [sys.executable, str(RUN_PY), "run", "--repo", str(repo), "--state-dir", str(state),
                 "--wave-all", "--runner-cmd", runner_cmd],
                check=True, capture_output=True, text=True,
            )
            backend = SqliteStore(state / "index.db")
            old_run_id = backend.read_artifact("manifest").get("run_id")
            old_folded = {r["scope_hash"] for r in backend.task_rows(old_run_id) if r["state"] == "folded"}
            backend.close()

            # A real content change: append to one file the pipeline already
            # scanned, then re-scan (as `refresh`/a fresh `scan` would) so the
            # partition's scope_hash for the touched scope moves.
            touched = next(repo.rglob("*.java"))
            touched.write_text(touched.read_text() + "\n// touched for M5.5's drift guard\n")
            subprocess.run(
                [sys.executable, str(RUN_PY), "scan", "--repo", str(repo),
                 "--state-dir", str(state), "--quiet"], check=True, capture_output=True)

            result = subprocess.run(
                [sys.executable, str(RUN_PY), "run", "--repo", str(repo), "--state-dir", str(state),
                 "--wave-all", "--runner-cmd", runner_cmd, "--resume"],
                check=True, capture_output=True, text=True,
            )
            self.assertIn("partition changed since run %s -- opened new run" % old_run_id, result.stdout)

            backend = SqliteStore(state / "index.db")
            new_run_id = "%s-r2" % old_run_id
            new_rows = {r["scope_hash"]: r["state"] for r in backend.task_rows(new_run_id)}
            backend.close()
            self.assertTrue(old_folded, "expected at least one folded scope from the first run")
            for scope_hash in old_folded:
                if scope_hash in new_rows:  # a scope whose content did not move
                    self.assertEqual(new_rows[scope_hash], "folded")

    def test_stale_only_with_nothing_stale_exits_cleanly(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(Path(tmp))
            state = Path(tmp) / "state"
            subprocess.run(
                [sys.executable, str(RUN_PY), "scan", "--repo", str(repo),
                 "--state-dir", str(state), "--quiet"], check=True, capture_output=True)
            result = subprocess.run(
                [sys.executable, str(RUN_PY), "run", "--repo", str(repo), "--state-dir", str(state),
                 "--stale-only"],
                check=True, capture_output=True, text=True,
            )
            self.assertIn("zero scopes need review", result.stdout)


if __name__ == "__main__":
    unittest.main()
