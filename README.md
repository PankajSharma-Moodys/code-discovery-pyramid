# CDP — Code Discovery Pyramid

Reconstructs architecture from a codebase by giving each agent one tightly
bounded scope, forcing every claim to carry a `file:line` anchor, and
stitching breadth back together deterministically in Python.

Bundled and dependency-free (stdlib Python 3.9+). See `SKILL.md` for the
narrative walkthrough of the core `scan` → `query` → `run` flow. This file is
the full command reference: every `cdp` subcommand, what it does, what to run
next, and the flags worth knowing.

```bash
python3 -m cdp.cli --help          # or: python3 .claude/skills/cdp/run.py --help
python3 -m cdp.cli help            # guidance: order, workflows, what's next
python3 -m cdp.cli help <command>  # one command's flags, straight from argparse
```

`cdp help`/`cdp help --json` is generated from the live argument parser, so it
can never drift from the CLI. This table can — if a command's flags look off,
trust `cdp help <command>` over this file.

Every command that changes state now also prints its own `next`/`tip` line
after it runs, telling you what to run next and which flag matters — the
table below is that same guidance, gathered in one place.

## Command reference

### Core loop

| Command | What it does | Next / useful flags |
|---|---|---|
| `scan --repo <path>` | Every deterministic phase (extract, graph, partition, dataflow, verify, docs) — no model calls, writes `.cdp/`. Start here, always. | next: `query stats`, `query trace <entrypoint>`, or `prompts`. Flags: `--workers N`, `--exclude DIR`, `--no-docs`, `--quiet`. |
| `query <kind> [term]` | Ask the index a question (`stats coverage symbol file module routes table config paths search claims unknowns conflicts trace`). Never budgeted for `stats`/`coverage` — check those before saying "there is no X". | tip (when rows were elided): `--budget <bigger N>`. Flags: `--json`, `--kind`, `--as-of <sha>`. |
| `docs [--out DIR]` | Renders `00-overview.md`, `modules/<module>.md`, `dataflow.md`, `unknowns.md`, `CLAUDE.md`. | next: open `<out>/00-overview.md`, or `query stats`. |
| `prompts` | Writes one leaf prompt per scope for the wave loop. | next: hand each prompt to a leaf, then `collect`. Flags: `--digest` (full-file prompts instead of citations), `--wave N`, `--node X`, `--lessons vN`/`--no-lessons`. |
| `collect` | Validates, verifies and appends leaf patches sitting in the inbox. | next: `fold --check`. |
| `fold [--check]` | Recomputes `state.json` from `patches/` + `xref.json`. `--check` verifies the invariant instead of writing. | next (no `--check`): `query stats`. On `--check` failure: `rollback` the offending run, or `fold` again. |
| `verify [--full]` | Recomputes the fold from the log and diffs it against `state.json`; `--full` also proves the archive. | On `FAIL`: `rollback --to-run <run>`, then `fold`. On `ok` without `--full`: tip — `verify --full` (needs `compact` first). |
| `refresh` | Re-verifies every live claim against HEAD, zero model calls, incremental extraction. | next: `query stats`. Flags: `--quiet`. No-ops cleanly when HEAD is unchanged. |

### The wave loop (leaf agents)

| Command | What it does | Next / useful flags |
|---|---|---|
| `run --wave N \| --wave-all \| --stale-only \| --scope X` | Dispatch → collect → adjudicate → fold, wave by wave, supervised (leases, retries, resume). | next: `query stats`, or `fold --check`. tip (on partial failure): `run --resume --run-id <id>`. Flags: `--runner-cmd`, `--max-attempts`, `--resume`, `--lessons vN`/`--no-lessons`. |
| `status` | Waves, per-node statuses, coverage, freshness, and the current run's task table. | tip (stale/unreviewed scopes exist): `run --stale-only`. next (incomplete tasks): `run --resume --run-id <id>`. |
| `reflect` | One real model call per outlier scope from a run's trajectory corpus; keeps only well-formed promotions. | next (promotions accepted): `lessons cut`, then `holdout --lessons vN <held-out-repo>` before trusting it. |
| `lessons cut \| unpromote \| show` | Cut and inspect numbered, pinned lesson-sets (`cdp run --lessons vN` pins one; default is always the latest cut, never the live corpus). | `cut` → next: `run --lessons vN`, or `holdout` to A/B first. `unpromote` → next: default `run` resolution now uses the new fallback (`--no-lessons` to opt out). `show` → tip: `lessons cut` / `lessons unpromote --version N`. |
| `holdout --lessons vN <repo>` | A/B a lesson-set cut against a repo outside its own learning corpus; promotes to latest only if it doesn't regress. | On promote: next — `run --lessons vN` (or omit `--lessons`; it's now the latest cut). |
| `doctor --runner-cmd <cmd>` | Cross-model conformance harness: schema validity, anchor survival, entailment, recall, false-unknown rate against a golden set. Writes `<state>/doctor/<model>.json`. | next (only one model report so far): `doctor --model <other>` to build the compatibility table. |

### Diagnostics & history

| Command | What it does | Next / useful flags |
|---|---|---|
| `diff <old_state> <new_state>` (or `--old-sha`/`--new-sha`) | Typed structural deltas between two scanned snapshots. | tip: `query symbol`/`query table <name>` for full context on a changed item. |
| `answer --scope S --subject X --claim "..." --anchor FILE:LINE` | Records a human claim against an unknown — same validate/verify/entail/fold pipeline as a leaf patch, `author_kind=human`. | next: `query unknowns` to see what's still open. |
| `rollback --to-run R \| --to-snapshot S` | Excludes a run's patches from the fold without deleting them (append-only ledger). | next: `query stats` to confirm the exclusion took effect. tip: `--reason "..."` to record why. |
| `validate <patch.json>` | Validates a patch file against the schema. | — |

### Cross-repo link (Phase 8)

| Command | What it does | Next / useful flags |
|---|---|---|
| `link scan <state_dir>... [--db]` | Matches channel edges within/across scanned state directories (read-only). | next: `link query --service <name>`. tip (ambiguous matches found): `link prompts --out <dir>`. |
| `link prompts --db --out DIR` | Writes one prompt per ambiguous (heuristic) caller target. | next (no `--runner-cmd`): hand each prompt to a leaf, drop its patch in `<out>/inbox`, then `link collect --in <out>`. |
| `link collect --db --in DIR` | Validates → verifies → entails → folds every patch from a prior `link prompts --out`. | next: `link query --service <name>`. |
| `link run --db` | Dispatches every ambiguous task through the same lease/retry machine `run` uses for scopes. | next: `link query --service <name>`. Flags: `--runner-cmd`, `--max-attempts`. |
| `link refresh <state_dir>... --db` | Re-verifies a prior `link scan --db`'s contracts against freshly scanned state. | next: `link query --service <name>`. |
| `link query --service <name> --db` | Who calls a service / what it calls that went unmatched. | — |

### Maintenance

| Command | What it does | Next / useful flags |
|---|---|---|
| `gc [--pin SHA] [--unpin SHA] [--dry-run]` | Drops snapshots not kept by the retention rule (HEAD, pinned, or cited by a live claim). | tip (something dropped): `compact` to also fold superseded patches into the cold archive. |
| `compact [--keep-generations N] [--compact-threshold F]` | Moves superseded `complete` patch generations to the cold archive. | tip (something moved): `export --format archive` to inspect it. |
| `export --format {json,patches,archive,anonymized} --out DIR` | Canonical JSON / reviewable patches / archive dump / anonymised corpus. | tip (`json` format): `--format patches` for a reviewable dump, `--format archive` to include the cold archive. |
| `githook install \| uninstall` | Installs/uninstalls git `post-commit`/`post-checkout` hooks that auto-run `cdp refresh`. | — |

### Setup & self-check

| Command | What it does | Next / useful flags |
|---|---|---|
| `install <repo> [--self] [--framework {claude-code,langgraph,adk,none}] [--hook]` | Copies the skill into another repository (and, by default, the `cdp-leaf` Claude Code agent). | next: `scan --repo <target>` (printed for you). tip: `--hook` to auto-refresh on every commit, `--framework {langgraph,adk}` for non-Claude-Code leaves. |
| `selftest [--determinism <repo>] [--golden] [--min-tests N]` | Runs the bundled test suite (or the reproducibility/golden gates). | — |
| `help [<command> \| workflows] [--json]` | When to use what, in what order, and what comes next — derived from the live parser, never hand-maintained. | — |

## What CDP will not tell you

See `SKILL.md`'s "What CDP will not tell you" section — the runtime DI graph,
dynamic dispatch, reflection, generated code, data semantics, and entailment
of a citation's *reading* are all out of scope by design, not oversight.
