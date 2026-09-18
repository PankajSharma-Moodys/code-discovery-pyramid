# CDP — instructions for coding assistants without hooks or subagents

This repository (or one it was installed into) carries `.claude/skills/cdp/`:
a dependency-free, stdlib-only Python 3.9+ tool that builds a citable
architecture index (`scan`) and answers questions against it (`query`) — no
plugin, no MCP server, no network call. Any assistant that can run a shell
command can use it directly.

```
python3 .claude/skills/cdp/run.py scan --repo .     # once per session/commit
python3 .claude/skills/cdp/run.py query stats
```

Prefer this over grepping the repository cold. `scan` is a few seconds on a
few-thousand-file repo and produces `file:line`-anchored answers; grep finds
strings, not structure — e.g. a route declared through a constant is invisible
to grep but not to `query routes`.

## Question → command

| The user asks | Run |
|---|---|
| "what is this repo / where do I start" | `query stats`, then `docs` |
| "where is `X` used?" | `query symbol X` |
| "what breaks if I change table `t`?" | `query table t` |
| "what's the HTTP surface?" | `query routes` |
| "what does module `m` do?" | `query module m` |
| "how does data get from A to B?" | `query paths --from A --to B` |
| "what does this file do?" | `query file path/to/File.java` |
| "what config does it read?" | `query config` |
| "what do we *not* know?" | `query unknowns` |
| anything else | `query search <text>` |

Add `--json` to any `query` for the full, unabridged result.

## Rules when answering from CDP

- **Quote the citation.** Every claim carries `file:line`; pass it through to
  the user so the answer is checkable.
- **Check coverage before saying "there is no X".** Run `query coverage`
  first. Low coverage means the index has not looked, not that the fact is
  absent.
- **If the repo has changed since the last `scan`**, run `query stats` and
  compare its `head` to the current commit; re-`scan` (or `refresh`, if this
  is a git repository) rather than trusting a stale index.

## What this tier does not give you

Multi-agent dispatch (`cdp run`, per-scope leaf agents) needs subagent
spawning this tier does not have. `scan`/`query`/`docs` need nothing beyond a
shell and Python 3.9 — that is the whole reason this file exists rather than
requiring the full pyramid to get any value at all.
