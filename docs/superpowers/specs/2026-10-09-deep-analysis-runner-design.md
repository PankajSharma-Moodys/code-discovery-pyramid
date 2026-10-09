# Deep-analysis runner — design

Budget: ≤90 lines. Status: approved in chat 2026-10-09. Research basis:
deep-research report (official Claude Code headless / Agent SDK docs) plus a
local isolation test on Claude Code 2.1.289 (below).

## Goal

"Run deep analysis" in the web UI starts `cdp run` with no `--runner-cmd`, so
the FileRunner waits for patches nobody writes. Ship a built-in runner so the
button produces real leaf-agent results, safely and within a spending cap.

## Decisions (user-approved)

- Runner: headless Claude Code (`claude -p`) per scope, using the user's own
  Claude Code login (no API key; `--bare` is NOT used).
- Default model **sonnet**, switchable per run in the UI.
- Default caps: **$5 per run**, **$1.00 / 30 turns per scope**; **one scope at a time**
  (parallelism deferred: `cmd_run` holds an exclusive state-dir lock, cli.py:1533).
- A confirm step before starting; live cost shown as an estimate.

## Isolation (verified locally, 2026-10-09)

A throwaway repo with a `.claude/settings.json` hook and an `.mcp.json` server:
plain `claude -p` fired both hooks and started the MCP server; with
`--restricted --strict-mcp-config` neither ran, and the login still worked.
Both flags are mandatory for every runner call.

## Runner — `python -m cdp.runners.claude_code <prompt-path> <patch-path>`

Plugs into the existing `--runner-cmd` contract. Configuration via env vars set
by whoever starts `cdp run`: `CDP_RUNNER_REPO` (cwd), `CDP_RUNNER_MODEL`,
`CDP_RUNNER_SCOPE_BUDGET_USD`, `CDP_RUNNER_MAX_TURNS`, `CDP_RUNNER_RUN_BUDGET_USD`,
`CDP_RUNNER_LEDGER` (path to the spend ledger). Per call:

1. Refuse (non-zero exit, clear stderr) if `claude --version` < 2.1.259.
2. Lock the ledger (`fcntl.flock`); if recorded spend ≥ run budget, exit
   non-zero with "run budget exhausted" without calling Claude.
3. Run, with cwd = repo and the prompt file content on stdin:
   `claude -p --restricted --strict-mcp-config --model <m> --tools Read,Grep,Glob
   --permission-mode dontAsk --output-format json --json-schema <schema/patch-1.0.0.json>
   --max-turns <n> --max-budget-usd <x> --append-system-prompt <return the patch as structured
   output; you cannot write files>` (the leaf prompt says "Write your patch to …",
   prompts.py:488). Never pass `--add-dir`.
4. Parse the JSON result. Record `total_cost_usd` in the ledger (always, even on
   failure). Success = `is_error` false AND `structured_output` present → write it
   to the patch path. Otherwise exit non-zero with the result subtype/message
   (`error_max_turns`, `error_max_budget_usd`, missing structured_output, …).
5. No extra retries: Claude Code retries transient/429 itself; cdp's existing
   `--max-attempts` re-dispatch stays the outer safety net.

Ledger: one file per UI launch, `<state>/runner/spend-<launch id>.json` — `{"budget_usd", "spent_usd",
"calls": [{"prompt", "cost_usd", "ok", "subtype"}]}`.

## Web API / UI

- `POST /api/run` gains `use_claude_runner`, `model`, `run_budget_usd` (validated:
  model ∈ {sonnet, opus, haiku}; 0 < budget ≤ 100). With `use_claude_runner=true`
  (the UI's default) it passes `--runner-cmd "<python> -m cdp.runners.claude_code"
  --timeout 900`, sets the env vars, and uses the store's recorded repo path
  (`inventory.repo`) for `--repo`/cwd — the UI's default `repo="."` is the server's
  cwd, which `cdp run`'s repo-mismatch guard rejects. Otherwise unchanged.
- `GET /api/run/spend?job_id=` returns the ledger summary for that launch.
- Control Room Run panel: Claude toggle, model select, run cap; a confirm step
  ("≈ N scopes, cap $X"); live "$x.xx of $X (estimate)". Still behind the
  existing mutation token.

## Testing

- Runner unit tests with a fake `claude` on PATH: success writes the patch and
  records cost; budget exhausted skips the call; missing structured_output and
  `error_max_turns` fail; old version refused; argv contains both isolation flags
  and `--tools Read,Grep,Glob`.
- API tests: `use_claude_runner` passes the runner cmd, env and recorded repo;
  validation errors → 400; spend endpoint reflects the ledger.
- One real end-to-end run on a tiny fixture repo (≤2 scopes) before RDL.

## Out of scope

Running scopes in parallel; mid-run cancel beyond the existing stop; API-key / LiteLLM backends in the UI;
prompt-caching tuning; cost estimation from history.
