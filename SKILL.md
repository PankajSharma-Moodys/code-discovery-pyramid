---
name: cdp
description: Reconstruct undocumented architecture from a codebase and answer questions about it with file:line citations. Use when asked to map, explain, document or onboard onto an unfamiliar repository; to find where a symbol/table/route/config key is used; to trace how data flows; or to produce architecture docs or a CLAUDE.md for a repo. Also use before broad grep-based exploration of a large repo — `cdp scan` builds a citable index once, and querying it is cheaper and more reliable than repeated searching. Portable: works on any repository, any language, no install.
---

# CDP — Code Discovery Pyramid

A citable index of this repository: every fact carries a `file:line` anchor.
Querying it is cheaper and more reliable than grepping. If a SessionStart
status line is present the index is already fresh; otherwise run
`python3 .claude/skills/cdp/run.py scan --repo .` (no model calls).

| The user asks | Run |
|---|---|
| where is `X` used | `query symbol X` |
| what does a file / module do | `query file <path>` / `query module <m>` |
| HTTP surface / config / table `t` | `query routes` / `query config` / `query table t` |
| how does data get from A to B | `query paths --from A --to B` |
| what don't we know | `query unknowns` |
| anything else | `query search <text>` |

Run these as `python3 .claude/skills/cdp/run.py <command>`; the MCP tools
`cdp_query` / `cdp_status` / `cdp_scan` do the same. `run.py help` lists every
command; add `--json` for unabridged output.

- Quote the `file:line` citation.
- Run `query coverage` before saying "there is no X"; below 100% means "not examined".
- Keep `medium`/`contested` confidence as is; `call` edges prove reachability, not invocation.
