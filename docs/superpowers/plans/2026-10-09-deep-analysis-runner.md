# Deep-Analysis Runner Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

Budget: ≤560 lines (most of it is the full test + implementation code each task carries).

**Goal:** "Run deep analysis" in the web UI runs real leaf agents through headless Claude Code, isolated from the analysed repo and capped at a per-run budget.

**Architecture:** A new `--runner-cmd` program `python -m cdp.runners.claude_code` runs one `claude -p` per scope with read-only, repo-confined tools and records cost in a file-locked JSON ledger. `POST /api/run` gains a `use_claude_runner` mode that wires the runner, env vars and the store's recorded repo path into the existing `cdp run` job; `GET /api/run/spend` reads the ledger; the Control Room adds model/budget controls, a confirm step and live spend.

**Tech Stack:** Python 3 stdlib (subprocess, fcntl, json), FastAPI, unittest; React 19 + TanStack Query, vitest.

**Spec:** `docs/superpowers/specs/2026-10-09-deep-analysis-runner-design.md`

## Global Constraints

- Every `claude` call includes `--restricted --strict-mcp-config` (verified to stop the analysed repo's hooks and MCP servers) and `--tools Read,Grep,Glob --permission-mode dontAsk`; never `--add-dir`, never `--bare`.
- Defaults: model `sonnet`; per scope `--max-turns 30 --max-budget-usd 1.00`; per run budget `$5`; one scope at a time (single `cdp run` process). Allowed models: `sonnet`, `opus`, `haiku`; `0 < run_budget_usd ≤ 100`.
- Minimum Claude Code version `2.1.259`; older → runner exits 3 with a clear message.
- Runner exit codes: 0 success, 1 claude failure / no structured output, 3 version too old, 4 run budget exhausted.
- Env vars: `CDP_RUNNER_REPO`, `CDP_RUNNER_MODEL`, `CDP_RUNNER_SCOPE_BUDGET_USD`, `CDP_RUNNER_MAX_TURNS`, `CDP_RUNNER_RUN_BUDGET_USD`, `CDP_RUNNER_LEDGER`, optional `CDP_RUNNER_CLAUDE` (path to `claude`, for tests).
- Ledger JSON: `{"budget_usd": float, "spent_usd": float, "calls": [{"prompt": str, "cost_usd": float, "ok": bool, "subtype": str}]}`; cost is recorded even for failed calls.
- No new dependencies. Backend tests: `.venv/bin/python -m unittest discover -s web/tests -t .` and `.venv/bin/python -m unittest discover -s tests -t . -p 'test_claude_runner*.py'`. Frontend in `web/frontend`: `npm run build`, `npm run lint`, `npm test`.
- Tests never call the real `claude` and never write the real `~/.cdp/config.toml`.
- Never hand-edit `web/client/schema.ts`; regenerate: `cd web/client && PATH=<repo>/.venv/bin:$PATH npm run generate`.
- Commit messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. `claude` prints non-JSON (crash, auth expired) → runner exits 1, records cost 0, writes no patch, stderr says why. (Task 1 test.)
2. Run budget reached mid-run → later scopes exit 4 without calling Claude; spend endpoint shows the cap reached. (Task 1 + Task 2 tests.)
3. UI default selection (`repo="."`) with `use_claude_runner` → the job's `--repo` is the store's recorded repo, not the server cwd. (Task 2 test.)
4. `use_claude_runner=false` (CLI-style call) → `/api/run` behaves exactly as before (no runner cmd, no env). (Task 2 test.)
5. Spend endpoint reading the ledger while the runner rewrites it → never a 500 from a half-written file. (Task 2: shared flock read.)

---

### Task 1: The runner program

**Files:** Create `cdp/runners/__init__.py` (one-line docstring), `cdp/runners/claude_code.py` (run as `-m cdp.runners.claude_code`); Test: `tests/test_claude_runner.py`.

**Interfaces:**
- Produces: CLI `python -m cdp.runners.claude_code <prompt-path> <patch-path>`; functions `parse_version(text) -> Optional[tuple]`, `build_argv(claude, model, max_turns, scope_budget, schema_text) -> List[str]`, `run(prompt_path, patch_path, env) -> int`.

- [ ] **Step 1: Failing tests** `tests/test_claude_runner.py`:

```python
"""`cdp.runners.claude_code` (spec 2026-10-09-deep-analysis-runner-design.md)
against a fake `claude` executable -- the real CLI is never called."""
from __future__ import annotations

import json, os, shutil, stat, sys, tempfile, unittest
from pathlib import Path

from cdp.runners import claude_code

FAKE = r'''#!%s
import json, os, sys
if sys.argv[1:] == ["--version"]:
    print(os.environ.get("FAKE_VERSION", "2.1.289") + " (Claude Code)"); sys.exit(0)
with open(os.environ["FAKE_LOG"], "w") as fh:
    json.dump({"argv": sys.argv[1:], "cwd": os.getcwd(), "stdin": sys.stdin.read()}, fh)
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
```

- [ ] **Step 2: Run, expect failure** — `.venv/bin/python -m unittest tests.test_claude_runner` → `ModuleNotFoundError: cdp.runners`.
- [ ] **Step 3: Implement** `cdp/runners/__init__.py` with a one-line docstring, and `cdp/runners/claude_code.py`:

```python
"""Built-in `--runner-cmd` for `cdp run`: one headless Claude Code call per
scope (spec `docs/superpowers/specs/2026-10-09-deep-analysis-runner-design.md`).

    python -m cdp.runners.claude_code <prompt-path> <patch-path>

Configured by `CDP_RUNNER_*` env vars. `--restricted --strict-mcp-config`
stop the analysed repo's own `.claude` hooks and `.mcp.json` servers from
running (verified against Claude Code 2.1.289); tools are read-only and
confined to the repo. Cost goes to a file-locked per-launch ledger so the
run budget holds across scopes."""
from __future__ import annotations

import fcntl
import json
import os
import re
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, List, Mapping, Optional, Tuple

MIN_VERSION = (2, 1, 259)
SCHEMA_PATH = Path(__file__).resolve().parents[2] / "schema" / "patch-1.0.0.json"
APPEND_PROMPT = (
    "You cannot write files in this session. Ignore any instruction to write the patch "
    "to a file: return that exact patch object as your structured output instead."
)


def parse_version(text: str) -> Optional[Tuple[int, int, int]]:
    match = re.search(r"(\d+)\.(\d+)\.(\d+)", text or "")
    return tuple(int(x) for x in match.groups()) if match else None  # type: ignore[return-value]


def build_argv(claude: str, model: str, max_turns: int, scope_budget: float, schema_text: str) -> List[str]:
    return [
        claude, "-p", "--restricted", "--strict-mcp-config",
        "--model", model, "--tools", "Read,Grep,Glob", "--permission-mode", "dontAsk",
        "--output-format", "json", "--json-schema", schema_text,
        "--append-system-prompt", APPEND_PROMPT,
        "--max-turns", str(max_turns), "--max-budget-usd", "%.2f" % scope_budget,
    ]


@contextmanager
def locked_ledger(path: Path, budget: float) -> Iterator[dict]:
    """Exclusive read-modify-write of the ledger; the caller mutates the dict."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a+", encoding="utf-8") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        fh.seek(0)
        raw = fh.read()
        data = json.loads(raw) if raw.strip() else {"budget_usd": budget, "spent_usd": 0.0, "calls": []}
        yield data
        fh.seek(0)
        fh.truncate()
        json.dump(data, fh, indent=2)
        fh.flush()


def run(prompt_path: Path, patch_path: Path, env: Mapping[str, str]) -> int:
    claude = env.get("CDP_RUNNER_CLAUDE", "claude")
    ledger = Path(env["CDP_RUNNER_LEDGER"])
    run_budget = float(env.get("CDP_RUNNER_RUN_BUDGET_USD", "5"))

    version = subprocess.run([claude, "--version"], capture_output=True, text=True, env=dict(env))
    found = parse_version(version.stdout)
    if found is None or found < MIN_VERSION:
        print("claude runner: Claude Code >= %s required, found %r"
              % (".".join(map(str, MIN_VERSION)), version.stdout.strip()), file=sys.stderr)
        return 3

    with locked_ledger(ledger, run_budget) as data:
        if data["spent_usd"] >= run_budget:
            print("claude runner: run budget exhausted ($%.2f of $%.2f)" % (data["spent_usd"], run_budget),
                  file=sys.stderr)
            return 4

    argv = build_argv(
        claude, env.get("CDP_RUNNER_MODEL", "sonnet"), int(env.get("CDP_RUNNER_MAX_TURNS", "30")),
        float(env.get("CDP_RUNNER_SCOPE_BUDGET_USD", "1.00")), SCHEMA_PATH.read_text(encoding="utf-8"),
    )
    proc = subprocess.run(argv, input=Path(prompt_path).read_text(encoding="utf-8"), capture_output=True,
                          text=True, cwd=env["CDP_RUNNER_REPO"], env=dict(env))
    try:
        result = json.loads(proc.stdout)
    except ValueError:
        result = {}
    if not isinstance(result, dict):
        result = {}
    cost = float(result.get("total_cost_usd") or 0.0)
    output = result.get("structured_output")
    ok = proc.returncode == 0 and not result.get("is_error") and output is not None
    if ok:
        subtype = "success"
    elif result.get("subtype") == "success" and output is None:
        subtype = "missing structured_output"
    else:
        subtype = str(result.get("subtype") or "no-json")

    with locked_ledger(ledger, run_budget) as data:
        data["spent_usd"] = round(data["spent_usd"] + cost, 6)
        data["calls"].append({"prompt": Path(prompt_path).name, "cost_usd": cost, "ok": ok, "subtype": subtype})

    if not ok:
        detail = result.get("result") or proc.stderr or proc.stdout
        print("claude runner: %s: %s" % (subtype, str(detail)[:500]), file=sys.stderr)
        return 1
    Path(patch_path).parent.mkdir(parents=True, exist_ok=True)
    Path(patch_path).write_text(json.dumps(output, indent=2), encoding="utf-8")
    return 0


def main(argv: List[str]) -> int:
    if len(argv) != 2:
        print("usage: python -m cdp.runners.claude_code <prompt-path> <patch-path>", file=sys.stderr)
        return 2
    return run(Path(argv[0]), Path(argv[1]), os.environ)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
```


- [ ] **Step 4: Run** the tests → all pass. **Step 5: Commit** `cdp/runners/__init__.py cdp/runners/claude_code.py tests/test_claude_runner.py` — `cdp: built-in Claude Code runner for cdp run`.

---

### Task 2: Backend wiring — `POST /api/run` runner mode + `GET /api/run/spend`

**Files:** Modify `web/api/jobs.py`, `web/api/app.py`, `web/api/models.py`; Create `web/tests/test_run_runner.py`; regenerate `web/openapi.json`, `web/client/schema.ts`.

**Interfaces:**
- Consumes: Task 1 CLI and env contract.
- Produces: `POST /api/run?use_claude_runner=true&model=sonnet&run_budget_usd=5` (+ existing params) → `JobResponse`; `GET /api/run/spend?job_id=` → `RunSpendResponse {budget_usd: float, spent_usd: float, calls: int, ok: int, failed: int, running: bool}`; `jobs.spawn_or_join(kind, repo, state_dir, extra_args, env=None)`; `Job.env: Dict[str, str]`.

- [ ] **Step 1: Failing tests** `web/tests/test_run_runner.py`:

```python
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
```

- [ ] **Step 2: Run** `.venv/bin/python -m unittest web.tests.test_run_runner` → fails (unknown params / route missing).
- [ ] **Step 3: `web/api/jobs.py`** — add `import os`; `Job.__init__` gains `env: Optional[Dict[str, str]] = None` stored as `self.env = dict(env or {})`; `spawn_or_join(kind, repo, state_dir, extra_args, env: Optional[Dict[str, str]] = None)` passes `env={**os.environ, **env} if env else None` to `Popen` and `env=env` to `Job`. Update its docstring line about env.
- [ ] **Step 4: Model** in `web/api/models.py`:

```python
class RunSpendResponse(BaseModel):
    """`GET /api/run/spend`: the Claude runner's per-launch ledger
    (`cdp/runners/claude_code.py`), costs are client-side estimates."""
    budget_usd: float
    spent_usd: float
    calls: int
    ok: int
    failed: int
    running: bool
```

- [ ] **Step 5: `post_run`** in `web/api/app.py` — add params and branch (keep the existing docstring, append one paragraph on runner mode); add `import fcntl`, `import shlex`, `import uuid` if missing:

```python
    use_claude_runner: bool = Query(False, description="run leaf agents through headless Claude Code"),
    model: str = Query("sonnet", description="Claude runner model: sonnet | opus | haiku"),
    run_budget_usd: float = Query(5.0, description="Claude runner spend cap for this launch (USD, estimate)"),
) -> JobResponse:
    resolved_state_dir = str(resolve_state_dir(Path(repo), state_dir))
    extra_args = _run_extra_args(target, resume)
    run_repo, env = repo, None
    if use_claude_runner:
        if model not in _RUNNER_MODELS:
            raise HTTPException(status_code=400, detail="model must be one of %s" % sorted(_RUNNER_MODELS))
        if not 0 < run_budget_usd <= 100:
            raise HTTPException(status_code=400, detail="run_budget_usd must be > 0 and <= 100")
        run_repo = _recorded_repo(Path(resolved_state_dir))
        ledger = Path(resolved_state_dir) / "runner" / ("spend-%s.json" % uuid.uuid4().hex[:12])
        extra_args += ["--runner-cmd", "%s -m cdp.runners.claude_code" % shlex.quote(sys.executable),
                       "--timeout", "900"]
        env = {
            "CDP_RUNNER_REPO": run_repo, "CDP_RUNNER_MODEL": model,
            "CDP_RUNNER_SCOPE_BUDGET_USD": "1.00", "CDP_RUNNER_MAX_TURNS": "30",
            "CDP_RUNNER_RUN_BUDGET_USD": str(run_budget_usd), "CDP_RUNNER_LEDGER": str(ledger),
        }
    job, joined = jobs_mod.spawn_or_join("run", run_repo, resolved_state_dir, extra_args, env=env)
```

(keep the existing return statement, using `run_repo` for `repo=`). Module-level helpers next to `_run_extra_args`:

```python
_RUNNER_MODELS = {"sonnet", "opus", "haiku"}


def _recorded_repo(state_dir: Path) -> str:
    """The repo path the store's scan recorded (`inventory.repo`). The UI's
    default `repo="."` is the server's cwd, which `cdp run`'s repo-mismatch
    guard rejects, so runner mode always uses the recorded path."""
    try:
        conn = ReadOnlyConnection(state_dir / "index.db")
        inventory = conn.read_artifact(conn.latest_pinned_snapshot(), "inventory", default={})
    except StoreUnavailable as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except StoreLocked as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    repo = (inventory or {}).get("repo")
    if not repo or not Path(repo).is_dir():
        raise HTTPException(status_code=409, detail="this store has no usable recorded repo path (%r)" % repo)
    return str(repo)
```

- [ ] **Step 6: Spend route** after `post_run`:

```python
@app.get("/api/run/spend", response_model=RunSpendResponse)
def get_run_spend(job_id: str = Query(..., description="job id returned by POST /api/run")) -> RunSpendResponse:
    """Live cost of a Claude-runner launch, read under a shared lock so a
    ledger mid-rewrite is never parsed half-written."""
    job = jobs_mod.get_job(job_id)
    ledger = (getattr(job, "env", None) or {}).get("CDP_RUNNER_LEDGER") if job else None
    if job is None or not ledger:
        raise HTTPException(status_code=404, detail="no Claude-runner launch with job_id %r" % job_id)
    budget = float(job.env.get("CDP_RUNNER_RUN_BUDGET_USD", "0"))
    data = {"budget_usd": budget, "spent_usd": 0.0, "calls": []}
    path = Path(ledger)
    if path.is_file():
        with open(path, encoding="utf-8") as fh:
            fcntl.flock(fh, fcntl.LOCK_SH)
            raw = fh.read()
        if raw.strip():
            data = json.loads(raw)
    calls = data.get("calls", [])
    ok = sum(1 for c in calls if c.get("ok"))
    return RunSpendResponse(budget_usd=float(data.get("budget_usd", budget)), spent_usd=float(data.get("spent_usd", 0.0)),
                            calls=len(calls), ok=ok, failed=len(calls) - ok, running=job.is_running())
```

- [ ] **Step 7: Run** the new tests, then the full backend suite once → OK. **Step 8: Regenerate** the client. **Step 9: Commit** — `web: POST /api/run Claude-runner mode + GET /api/run/spend`.

---

### Task 3: Control Room UI — runner controls, confirm, live spend

**Files:** Modify `web/frontend/src/api/controlRoomHooks.ts`, `web/frontend/src/panels/control-room/RunConsole.tsx`; Create `web/frontend/src/panels/control-room/runEstimate.ts` (+ `.test.ts`).

**Interfaces:**
- Consumes: `POST /api/run` new query params; `GET /api/run/spend?job_id=` → `{budget_usd, spent_usd, calls, ok, failed, running}`; status payload `waves: [{done, total, ...}]`.
- Produces: `remainingScopes(waves: {done: number; total: number}[]): number`; `formatSpend(spent: number, budget: number): string`; `useRunSpend(jobId: string | null)`.

- [ ] **Step 1: Failing test** `runEstimate.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { formatSpend, remainingScopes } from "./runEstimate.ts";

describe("runEstimate", () => {
  it("counts scopes not yet done across waves", () => {
    expect(remainingScopes([{ done: 2, total: 5 }, { done: 0, total: 3 }])).toBe(6);
    expect(remainingScopes([])).toBe(0);
    expect(remainingScopes([{ done: 4, total: 3 }])).toBe(0);
  });
  it("formats spend as an estimate against the cap", () => {
    expect(formatSpend(1.234, 5)).toBe("$1.23 of $5.00 (estimate)");
  });
});
```

- [ ] **Step 2: Run** `npx vitest run src/panels/control-room/runEstimate.test.ts` → fails. **Step 3: Implement** `runEstimate.ts`:

```ts
/** Pure helpers for the Control Room's Claude-runner confirm step and spend line. */
export function remainingScopes(waves: { done: number; total: number }[]): number {
  return waves.reduce((sum, w) => sum + Math.max(0, w.total - w.done), 0);
}

export function formatSpend(spent: number, budget: number): string {
  return `$${spent.toFixed(2)} of $${budget.toFixed(2)} (estimate)`;
}
```

- [ ] **Step 4: Hooks** in `controlRoomHooks.ts`: `useRunMutation`'s vars gain optional `claude?: { model: "sonnet" | "opus" | "haiku"; budgetUsd: number }`; when present add `use_claude_runner: true, model, run_budget_usd: budgetUsd` to the query. Add:

```ts
export function useRunSpend(jobId: string | null) {
  return useQuery({
    queryKey: ["run-spend", jobId],
    enabled: jobId !== null,
    refetchInterval: (q) => (q.state.data && !q.state.data.running ? false : 2000),
    queryFn: async ({ signal }) => {
      const { data, error } = await cdp.GET("/api/run/spend", { params: { query: { job_id: jobId! } }, signal });
      if (error) throw error;
      return data;
    },
  });
}
```

(import `cdp` from `./client.ts` if the file doesn't already).

- [ ] **Step 5: RunConsole** (match the file's existing style):
  - New state: `useClaude` (default `true`), `model` (default `"sonnet"`), `budget` (default `5`), `confirming` (bool), `jobId` (string | null).
  - Controls above the Run button: a checkbox "Use Claude Code", a `<select>` sonnet/opus/haiku and a number input "Cap $" (min 0.5, max 100, step 0.5), the last two disabled when `useClaude` is off.
  - Clicking Run with `useClaude` on sets `confirming` instead of dispatching, and shows an inline confirm row: `≈ {remainingScopes(status.waves)} scopes left · cap ${budget} · {model} · one scope at a time` with **Start** (dispatch with `claude: { model, budgetUsd: budget }`, then `setJobId(result.job_id)`) and **Cancel**. With `useClaude` off, Run dispatches exactly as today.
  - While `jobId` is set, show `formatSpend(spend.spent_usd, spend.budget_usd)` plus `· {ok} ok · {failed} failed`; when `spent_usd >= budget_usd`, add "budget reached — remaining scopes skipped".
- [ ] **Step 6: Verify** `npm run build`, `npm run lint` (no new warnings), `npm test`. **Step 7: Commit** — `web: Control Room Claude-runner controls, confirm and live spend`.
