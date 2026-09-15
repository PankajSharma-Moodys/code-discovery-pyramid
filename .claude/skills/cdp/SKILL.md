---
name: cdp
description: Reconstruct undocumented architecture from a codebase and answer questions about it with file:line citations. Use when asked to map, explain, document or onboard onto an unfamiliar repository; to find where a symbol/table/route/config key is used; to trace how data flows; or to produce architecture docs or a CLAUDE.md for a repo. Also use before broad grep-based exploration of a large repo — `cdp scan` builds a citable index once, and querying it is cheaper and more reliable than repeated searching. Portable: works on any repository, any language, no install.
---

# CDP — Code Discovery Pyramid

Reconstructs architecture from a codebase by giving each agent one tightly
bounded scope, forcing every claim to carry a `file:line` anchor, and stitching
breadth back together deterministically in Python.

**Bundled and dependency-free.** Stdlib Python 3.9+. Copy
`.claude/skills/cdp/` into any repository and it works.

```
CDP="$(dirname "$0")"            # or: .claude/skills/cdp
python3 .claude/skills/cdp/run.py --help
```

---

## Start here: `scan`, then `query`

Most requests need only these two. `scan` is deterministic — no model calls, no
tokens, a couple of seconds on a 400-file repo — and it produces a queryable
index in which every answer carries a citation.

```bash
python3 .claude/skills/cdp/run.py scan --repo <path>     # writes ./.cdp/
python3 .claude/skills/cdp/run.py query stats
```

Then answer from the index rather than from grep:

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

Add `--json` for the full, unabridged result.

**Prefer the index over grep for these questions.** `query symbol` is the
transpose of the resolved import table; grep finds the string. On the validation
target the HTTP routes are declared through constants, so grepping for
`/v1/servers` finds the constant definition and none of the six handlers —
`query routes` finds all of them with both anchors.

### Rules when answering from CDP

- **Quote the citation.** Every claim in the index carries `file:line`. Pass it
  through to the user; it is what makes the answer checkable.
- **Check coverage before saying "there is no X".** Run `query coverage`. If it
  is below 100%, absence of a fact means "not examined", not "not present". Say
  which.
- **Do not launder confidence.** A claim marked `medium` or `contested` stays
  that way in your answer. `call` edges are derived from imports and prove
  reachability, not invocation.
- **Re-scan when the working tree has moved.** State is pinned to a commit;
  `query stats` prints the SHA.

---

## `docs` — the written artifacts

```bash
python3 .claude/skills/cdp/run.py docs           # -> .cdp/docs/
python3 .claude/skills/cdp/run.py docs --out docs/architecture
```

Produces `00-overview.md`, `modules/<module>.md`, `dataflow.md`, `unknowns.md`
and a generated `CLAUDE.md`. Read `unknowns.md` first: it is the list of what
the run could *not* establish, which is the thing worth taking to the incumbent
team.

---

## The full pyramid: adding leaf agents

`scan` gives structure. Leaf agents add meaning — why a module exists, what a
type is *for*, which representation is authoritative, what a test reveals about
intended behaviour. Run this when the user asks for a real architecture
reconstruction rather than a lookup.

**Only run this when the user has asked for it.** It spawns one agent per scope
(17 on a 391-file repo) and reads the whole codebase. `scan` is free; this is
not.

### The wave loop

The pyramid lives in the state directory, not in the agent call stack. Every
agent runs at nesting depth 1; a later wave reads what an earlier wave wrote and
exited. That is what lets pyramid depth exceed the subagent nesting cap, and it
is what makes the run resumable.

```
1.  scan                     (deterministic; already done)
2.  prompts --wave N         write one prompt per scope in wave N
3.  spawn wave N's agents    ALL IN ONE MESSAGE, one Task per scope
4.  collect                  validate + verify + append + fold
5.  status                   confirm, then N += 1 and repeat
```

Concretely:

```bash
python3 .claude/skills/cdp/run.py status          # how many waves, which nodes
python3 .claude/skills/cdp/run.py prompts --wave 0
```

`prompts` writes `.cdp/prompts/<node>.md`. For each one, spawn a `cdp-leaf`
subagent — **all of a wave's agents in a single message**, so they run
concurrently — with a prompt of exactly this shape:

> Read `.cdp/prompts/<node>.md` and follow it. Read only the files it lists.
> Write your patch to `.cdp/patches/inbox/<node-with-slashes-as-__>.json`.

Then:

```bash
python3 .claude/skills/cdp/run.py collect
python3 .claude/skills/cdp/run.py prompts --wave 1
```

...and so on. Waves must run in order: wave *N+1* inherits the verified facts
wave *N* established, which is the whole reason `sql-pool-common` is scheduled
before the eight modules that import it.

### Handling failures

`collect` reports rejected patches with the specific schema violation. Per §3.5
you may hand a violation back to the agent **up to three times**; its only legal
moves are to correct the value or move the observation to `unknowns[]`. After
the third failure leave the node `invalid` and advance — a wave does not block
on a failed node, and the coverage figure records the gap.

Never hand-edit `.cdp/state.json`. It is a materialized view over the patch log;
`fold --check` will catch you, and a fact that is not derivable from its
provenance is exactly what this tool exists to prevent.

---

## Installing into another repository

```bash
python3 .claude/skills/cdp/run.py install /path/to/other/repo
```

Copies the skill and the `cdp-leaf` agent definition. Then, from that repo:

```bash
python3 .claude/skills/cdp/run.py scan --in-repo
```

`--in-repo` writes state to `<repo>/.cdp` and adds the gitignore entry. Without
it, state is written to `./.cdp` in the current directory and the target
repository is left untouched — which is the default, because the repository
being analysed is usually not yours.

### Adding a language

Extractors live in `cdp/lang/`. Java, Python, JS/TS, Go, SQL, Dockerfiles and
build manifests (gradle/maven/npm/go/cargo/poetry) are supported; everything
else is censused but not parsed. To add one, write an `Extractor` subclass and
register it in `cdp/lang/__init__.py`. Nothing else changes: the channel
vocabulary, the schema, verification, merge and every query are defined over the
output shape, not over any language.

---

## Reference

| Command | |
|---|---|
| `scan` | every deterministic phase; writes `.cdp/` |
| `query <kind> [term]` | `stats coverage symbol file module routes table config paths search claims unknowns conflicts` |
| `docs [--out DIR]` | markdown artifacts |
| `prompts [--wave N] [--node X]` | leaf prompts for the wave loop |
| `collect [--mode strict\|lenient]` | validate, verify, append, fold |
| `fold [--check]` | recompute state, or assert the fold invariant |
| `status` | waves, node statuses, coverage |
| `validate <patch.json>` | schema-check one patch |
| `install <repo>` | copy the skill into another repository |
| `selftest` | run the bundled tests |

Budgets: `--max-leaf-files` (40), `--max-leaf-loc` (6000), `--max-concurrent`
(12), `--max-hops` (8).

### What CDP will not tell you

Stated here so you do not over-claim on its behalf:

- **The runtime DI graph.** The object graph assembled at startup is decided
  from types, not imports. CDP reports declared wiring and says so.
- **Dynamic dispatch.** A call through an interface is an edge to the interface.
- **Reflection and string-keyed lookup.** A risk marker, never traced through.
- **Generated code.** Excluded by the git-based inventory and described by its
  build contract.
- **What the data means.** CDP maps where data goes, not what it is.
- **Whether a citation supports its statement.** Verification confirms the cited
  text exists where the claim says it does. Entailment is not checked, and a
  claim with a real anchor and a wrong reading of it looks exactly like a good
  claim.
