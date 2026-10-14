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

Answers are sized by the question; work like grep, with small calls, and pull more only when needed:
1. A broad question gets the default `--view list`: one line per row, ending in a repo-relative
   `file:line` that opens directly with Read.
2. One row in depth: `--view compact` with that row's name as the term (`--match exact` for exactly it).
   `trace`, `symbol`, `file` and `paths` answer in compact already.
3. Read only the cited lines.

- `--view count` gives true numbers only; `--view detail` the full result; `--json` structured output.
- A cut answer ends with `count`, `shown` and `next:` giving the `--offset` to continue. Page on only if the
  question needs the rest; otherwise narrow the term. A row too big for the cap names
  `--offset N --max-tokens 0` for that row alone.
- `--match regex` is `grep -E` (case-sensitive), also on names: `query routes '^/v1/(servers|pools)' --match regex`.
- `--filter REGEX` (list/count) keeps matching rows before the cap, with true counts (`matched: N of M`):
  `query config --filter 'S3_|metadata'`. For one known name use the term instead.
- `--max-tokens` sets the cap (default 3000); `.cdp.toml` `[query]` sets this repo's defaults.

## Rules when answering from CDP

- **Quote the citation.** Every claim carries `file:line`; pass it through to
  the user so the answer is checkable.
- **Check coverage before saying "there is no X".** Run `query coverage`
  first. Low coverage means the index has not looked, not that the fact is
  absent.
- **Follow every fork before you answer.** When a result branches (several
  handlers, callers, implementations, readers or writers, `elided: N`, or a
  path that stops short), run `query` for each branch to its end first. Never
  answer from the first branch; if you stop early, say which you did not follow.
- **Noise is off by default.** Tests and third-party `library:` rows are
  dropped from answers; pass `include_tests` / `include_library` only when the
  question is about them or cannot be answered without them. Use the kind built
  for the question (`routes`, `trace`, `module`, `table`, `config`) rather than
  raw `claims`, which carry full provenance per row.
- **Know the tool before you query.** The session-start message carries the
  `cdp_help` digest (kinds, parameters, defaults); read it first, and call
  `cdp_help` when a kind or flag is still unclear.
- **If the repo has changed since the last `scan`**, run `query stats` and
  compare its `head` to the current commit; re-`scan` (or `refresh`, if this
  is a git repository) rather than trusting a stale index.

## What this tier does not give you

Multi-agent dispatch (`cdp run`, per-scope leaf agents) needs subagent
spawning this tier does not have. `scan`/`query`/`docs` need nothing beyond a
shell and Python 3.9 — that is the whole reason this file exists rather than
requiring the full pyramid to get any value at all.
