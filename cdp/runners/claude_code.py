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
