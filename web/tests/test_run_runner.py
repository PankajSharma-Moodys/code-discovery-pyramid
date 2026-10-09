"""`POST /api/run` Claude-runner mode and `GET /api/run/spend` (spec
2026-10-09-deep-analysis-runner-design.md). `spawn_or_join` is mocked: these
tests check what would be launched, never launch `cdp run` or `claude`."""
from __future__ import annotations

import json, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[2]
MINIREPO = REPO_ROOT / "tests" / "fixtures" / "minirepo"


class RunRunnerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.state_dir = Path(tempfile.mkdtemp())
        subprocess.run([sys.executable, "-m", "cdp", "scan", "--repo", str(MINIREPO), "--state-dir", str(cls.state_dir)],
                       cwd=REPO_ROOT, check=True, capture_output=True, text=True)

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.state_dir, ignore_errors=True)

    def client(self):
        from fastapi.testclient import TestClient
        from web.api.app import app
        return TestClient(app)

    def post(self, **params):
        from web.api import auth as auth_mod
        fake_job = mock.Mock(job_id="j1", pid=1, kind="run")
        with mock.patch("web.api.jobs.spawn_or_join", return_value=(fake_job, False)) as spawn:
            resp = self.client().post("/api/run", params={"repo": ".", "state_dir": str(self.state_dir), **params},
                                      headers={"X-CDP-Web-Token": auth_mod.WEB_TOKEN})
        return resp, spawn

    def test_runner_mode_wires_cmd_env_and_recorded_repo(self) -> None:
        resp, spawn = self.post(use_claude_runner="true", model="haiku", run_budget_usd="2.5")
        self.assertEqual(resp.status_code, 200, resp.text)
        args, kwargs = spawn.call_args
        kind, repo, state_dir, extra = args
        self.assertEqual((kind, Path(repo).resolve()), ("run", MINIREPO.resolve()))
        runner_cmd = extra[extra.index("--runner-cmd") + 1]
        self.assertTrue(runner_cmd.endswith("-m cdp.runners.claude_code"), runner_cmd)
        self.assertEqual(extra[extra.index("--timeout") + 1], "900")
        self.assertEqual(extra[extra.index("--max-attempts") + 1], "2")
        env = kwargs["env"]
        self.assertEqual(Path(env["CDP_RUNNER_REPO"]).resolve(), MINIREPO.resolve())
        self.assertEqual((env["CDP_RUNNER_MODEL"], env["CDP_RUNNER_RUN_BUDGET_USD"]), ("haiku", "2.5"))
        self.assertEqual((env["CDP_RUNNER_SCOPE_BUDGET_USD"], env["CDP_RUNNER_MAX_TURNS"]), ("1.00", "30"))
        self.assertEqual(Path(env["CDP_RUNNER_LEDGER"]).parent, (self.state_dir / "runner").resolve())

    def test_runner_mode_defaults(self) -> None:
        _, spawn = self.post(use_claude_runner="true")
        env = spawn.call_args.kwargs["env"]
        self.assertEqual((env["CDP_RUNNER_MODEL"], env["CDP_RUNNER_RUN_BUDGET_USD"]), ("sonnet", "5.0"))

    def test_plain_run_unchanged(self) -> None:
        _, spawn = self.post()
        args, kwargs = spawn.call_args
        self.assertNotIn("--runner-cmd", args[3])
        self.assertNotIn("--max-attempts", args[3])
        self.assertIsNone(kwargs.get("env"))
        self.assertEqual(args[1], ".")

    def test_validation(self) -> None:
        for bad in ({"model": "gpt-4"}, {"run_budget_usd": "0"}, {"run_budget_usd": "101"}):
            resp, spawn = self.post(use_claude_runner="true", **bad)
            self.assertEqual(resp.status_code, 400, bad)
            spawn.assert_not_called()

    def test_spend_endpoint(self) -> None:
        from web.api import jobs as jobs_mod
        ledger = Path(tempfile.mkdtemp()) / "spend.json"
        self.addCleanup(shutil.rmtree, ledger.parent, ignore_errors=True)
        ledger.write_text(json.dumps({"budget_usd": 5.0, "spent_usd": 1.25, "calls": [
            {"prompt": "a", "cost_usd": 1.0, "ok": True, "subtype": "success"},
            {"prompt": "b", "cost_usd": 0.25, "ok": False, "subtype": "error_max_turns"}]}))
        job = mock.Mock(job_id="spend1", env={"CDP_RUNNER_LEDGER": str(ledger), "CDP_RUNNER_RUN_BUDGET_USD": "5"})
        job.is_running.return_value = False
        with mock.patch.object(jobs_mod, "get_job", side_effect=lambda jid: job if jid == "spend1" else None):
            body = self.client().get("/api/run/spend", params={"job_id": "spend1"}).json()
            missing = self.client().get("/api/run/spend", params={"job_id": "nope"})
        self.assertEqual(body, {"budget_usd": 5.0, "spent_usd": 1.25, "calls": 2, "ok": 1, "failed": 1, "running": False})
        self.assertEqual(missing.status_code, 404)
