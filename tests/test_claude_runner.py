"""`cdp.runners.claude_code` (spec 2026-10-09-deep-analysis-runner-design.md)
against a fake `claude` executable -- the real CLI is never called."""
from __future__ import annotations

import json, os, shutil, stat, sys, tempfile, unittest
from pathlib import Path

from cdp.runners import claude_code

FAKE = r'''#!%s
import json, os, sys, time
if sys.argv[1:] == ["--version"]:
    print(os.environ.get("FAKE_VERSION", "2.1.289") + " (Claude Code)"); sys.exit(0)
with open(os.environ["FAKE_LOG"], "w") as fh:
    json.dump({"argv": sys.argv[1:], "cwd": os.getcwd(), "stdin": sys.stdin.read(),
               "env": [k for k in ("ANTHROPIC_API_KEY", "CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT", "PATH") if k in os.environ]}, fh)
if os.environ.get("FAKE_PIDFILE"):
    open(os.environ["FAKE_PIDFILE"], "w").write(str(os.getpid()))
if os.environ.get("FAKE_SLEEP"):
    time.sleep(float(os.environ["FAKE_SLEEP"]))
sys.stdout.write(os.environ.get("FAKE_OUTPUT", "")); sys.exit(int(os.environ.get("FAKE_RC", "0")))
'''


class RunnerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.repo = self.tmp / "repo"
        self.repo.mkdir()
        fake = self.tmp / "claude"
        fake.write_text(FAKE % sys.executable)
        fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
        self.prompt = self.tmp / "p.md"
        self.prompt.write_text("PROMPT BODY")
        self.patch = self.tmp / "inbox" / "p.json"
        self.ledger = self.tmp / "state" / "runner" / "spend-x.json"
        self.log = self.tmp / "log.json"
        self.env = {
            "CDP_RUNNER_REPO": str(self.repo), "CDP_RUNNER_MODEL": "sonnet",
            "CDP_RUNNER_SCOPE_BUDGET_USD": "1.00", "CDP_RUNNER_MAX_TURNS": "30",
            "CDP_RUNNER_RUN_BUDGET_USD": "5", "CDP_RUNNER_LEDGER": str(self.ledger),
            "CDP_RUNNER_CLAUDE": str(fake), "FAKE_LOG": str(self.log),
        }

    def run_with(self, output: dict | str, **extra) -> int:
        env = dict(os.environ, **self.env, **extra)
        env["FAKE_OUTPUT"] = output if isinstance(output, str) else json.dumps(output)
        return claude_code.run(self.prompt, self.patch, env)

    def ledger_data(self) -> dict:
        return json.loads(self.ledger.read_text())

    def test_success_writes_patch_records_cost_and_isolates(self) -> None:
        rc = self.run_with({"is_error": False, "subtype": "success", "total_cost_usd": 0.12,
                            "structured_output": {"node": "a"}})
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(self.patch.read_text()), {"node": "a"})
        self.assertAlmostEqual(self.ledger_data()["spent_usd"], 0.12)
        call = json.loads(self.log.read_text())
        argv = call["argv"]
        for flag in ("-p", "--restricted", "--strict-mcp-config"):
            self.assertIn(flag, argv)
        self.assertEqual(argv[argv.index("--tools") + 1], "Read,Grep,Glob")
        self.assertEqual(argv[argv.index("--permission-mode") + 1], "dontAsk")
        self.assertEqual(argv[argv.index("--model") + 1], "sonnet")
        self.assertEqual(argv[argv.index("--max-turns") + 1], "30")
        self.assertEqual(argv[argv.index("--max-budget-usd") + 1], "1.00")
        self.assertNotIn("--add-dir", argv)
        self.assertNotIn("--bare", argv)
        self.assertEqual(Path(call["cwd"]).resolve(), self.repo.resolve())
        self.assertEqual(call["stdin"], "PROMPT BODY")

    def test_budget_exhausted_skips_claude(self) -> None:
        self.ledger.parent.mkdir(parents=True)
        self.ledger.write_text(json.dumps({"budget_usd": 5.0, "spent_usd": 5.0, "calls": []}))
        rc = self.run_with({"is_error": False, "structured_output": {}})
        self.assertEqual(rc, 4)
        self.assertFalse(self.log.exists())
        self.assertFalse(self.patch.exists())

    def test_missing_structured_output_fails_but_records_cost(self) -> None:
        rc = self.run_with({"is_error": False, "subtype": "success", "total_cost_usd": 0.3})
        self.assertEqual(rc, 1)
        self.assertFalse(self.patch.exists())
        call = self.ledger_data()["calls"][0]
        self.assertEqual((call["ok"], call["cost_usd"]), (False, 0.3))

    def test_max_turns_error_fails(self) -> None:
        rc = self.run_with({"is_error": True, "subtype": "error_max_turns", "total_cost_usd": 0.5})
        self.assertEqual(rc, 1)
        self.assertEqual(self.ledger_data()["calls"][0]["subtype"], "error_max_turns")

    def test_non_json_output_fails_with_zero_cost(self) -> None:
        rc = self.run_with("Not logged in", FAKE_RC="1")
        self.assertEqual(rc, 1)
        self.assertEqual(self.ledger_data()["calls"][0]["cost_usd"], 0.0)

    def test_old_version_refused(self) -> None:
        rc = self.run_with({"structured_output": {}}, FAKE_VERSION="2.1.100")
        self.assertEqual(rc, 3)
        self.assertFalse(self.log.exists())

    def test_parse_version(self) -> None:
        self.assertEqual(claude_code.parse_version("2.1.289 (Claude Code)"), (2, 1, 289))
        self.assertIsNone(claude_code.parse_version("garbage"))


    def seed_ledger(self, spent: float) -> None:
        self.ledger.parent.mkdir(parents=True)
        self.ledger.write_text(json.dumps({"budget_usd": 5.0, "spent_usd": spent, "calls": []}))

    def test_per_call_budget_capped_by_remaining(self) -> None:
        self.seed_ledger(4.6)
        rc = self.run_with({"is_error": False, "subtype": "success", "total_cost_usd": 0.1,
                            "structured_output": {}})
        self.assertEqual(rc, 0)
        argv = json.loads(self.log.read_text())["argv"]
        self.assertEqual(argv[argv.index("--max-budget-usd") + 1], "0.40")

    def test_remaining_below_floor_exits_4(self) -> None:
        self.seed_ledger(4.97)
        rc = self.run_with({"is_error": False, "structured_output": {}})
        self.assertEqual(rc, 4)
        self.assertFalse(self.log.exists())

    def test_timeout_kills_process_group_and_charges_scope_budget(self) -> None:
        pidfile = self.tmp / "pid"
        rc = self.run_with({"structured_output": {}}, CDP_RUNNER_TIMEOUT_S="1", FAKE_SLEEP="30",
                           FAKE_PIDFILE=str(pidfile))
        self.assertEqual(rc, 1)
        call = self.ledger_data()["calls"][0]
        self.assertEqual((call["ok"], call["subtype"], call["cost_usd"]), (False, "timeout", 1.0))
        self.assertFalse(self.patch.exists())
        with self.assertRaises(ProcessLookupError):
            os.kill(int(pidfile.read_text()), 0)

    def test_child_env_strips_api_key_and_nesting_markers(self) -> None:
        rc = self.run_with({"is_error": False, "subtype": "success", "total_cost_usd": 0, "structured_output": {}},
                           ANTHROPIC_API_KEY="k", CLAUDECODE="1", CLAUDE_CODE_ENTRYPOINT="cli")
        self.assertEqual(rc, 0)
        seen = json.loads(self.log.read_text())["env"]
        self.assertEqual(seen, ["PATH"])

    def test_claude_schema_text_converts_to_draft_07(self) -> None:
        schema_text = claude_code.claude_schema_text()
        schema_obj = json.loads(schema_text)
        # Verify $schema is draft-07
        self.assertEqual(schema_obj["$schema"], "http://json-schema.org/draft-07/schema#")
        # Verify all top-level keys from original are present
        original_obj = json.loads(claude_code.SCHEMA_PATH.read_text(encoding="utf-8"))
        self.assertEqual(set(schema_obj.keys()), set(original_obj.keys()))

    def test_success_argv_schema_is_draft_07(self) -> None:
        rc = self.run_with({"is_error": False, "subtype": "success", "total_cost_usd": 0.12,
                            "structured_output": {"node": "a"}})
        self.assertEqual(rc, 0)
        call = json.loads(self.log.read_text())
        argv = call["argv"]
        schema_idx = argv.index("--json-schema")
        schema_text = argv[schema_idx + 1]
        schema_obj = json.loads(schema_text)
        self.assertEqual(schema_obj["$schema"], "http://json-schema.org/draft-07/schema#")
