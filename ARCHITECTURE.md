# CDP Architecture

Two parts: **how it works today**, and **how it works after `CDP_CLI_SCOPE.md` lands**.
Both walk the same simulated run so you can diff them.

Running example throughout: `acme-payments`, a Java/Maven monorepo — 391 tracked files,
9 modules, HEAD at `a1b2c3d`.

---

# Part 1 — Today

## The model

```
   TIER 1  deterministic        TIER 2  attested
   ─────────────────────        ─────────────────────
   Python reads source          LLM reads what Tier 1 produced
   structure: defines,          meaning: claims with anchors
   uses, io_edges, graph        + unknowns
   zero tokens                  one agent per scope
   reproducible                 verified independently, demotable
```

The dividing line is absolute: **leaf agents never emit structure, Python never emits meaning.**

## Module map

| File | Owns |
|---|---|
| `cli.py` | argparse, `_paths`, every `cmd_*` entry point |
| `util.py` | canonical JSON IO, git shell-outs, text handling |
| `inventory.py` | census via `git ls-files`, module roots from build manifests, role classification |
| `lang/*.py` | per-language extractors (8 + generic fallback) |
| `lang/base.py` | `FileFacts`, channel hints, third-party prefixes, comment stripping |
| `extract.py` | drives extractors over the inventory → `defines/uses/io_edges/imports` |
| `graph.py` | dual-source module DAG: declared (manifests) vs observed (imports), layering, cycles |
| `partition.py` | cut the tree into leaf scopes under 40-file / 6000-LOC budgets |
| `schedule.py` | topological waves from the module DAG |
| `resolve.py` | global symbol table, `used_by` transpose, unresolved routes |
| `dataflow.py` | typed channel paths, process boundaries |
| `derive.py` | structural claims Python can assert on its own |
| `anchor.py` | build + verify anchors (≥12 chars, ≤3 matches/file, ±5 line window) |
| `verify.py` | re-open every cited file, demote failures |
| `merge.py` | order-independent set-wise merge, conflict → `contested` |
| `state.py` | the fold: `state = fold(merge, patches, xref)` |
| `prompts.py` | one leaf prompt per scope, inherited sigma, ranked elision |
| `query.py` | 13 typed queries + render |
| `docs.py` | overview, `modules/*.md`, `dataflow.md`, `unknowns.md`, `CLAUDE.md` |
| `schema.py` | patch validation |

## Simulated run — `cdp scan`

```bash
cdp scan --repo ~/src/acme-payments
```

One command, eleven phases, all in-process:

| # | Phase | Module | Reads | Writes |
|---|---|---|---|---|
| 1 | inventory | `inventory.py` | `git ls-files`, `git rev-parse HEAD` | `inventory.json` |
| 2 | extract | `extract.py` + `lang/*` | 391 files from disk | `extract.json` |
| 3 | graph | `graph.py` | `extract.json` | `graph.json` |
| 4 | partition | `partition.py` | `inventory.json`, `graph.json` | `partition.json` |
| 5 | schedule | `schedule.py` | `graph.json`, `partition.json` | `schedule.json` |
| 6 | xref | `resolve.py` | `extract.json` | `xref.json` |
| 7 | dataflow | `dataflow.py` | `xref.json`, `extract.json` | `dataflow.json` |
| 8 | derive | `derive.py` | everything above | `patches/0000-derived.json` |
| 9 | verify | `verify.py` + `anchor.py` | the derived patch + source files | `reports/verify.json` |
| 10 | fold | `state.py` + `merge.py` | `patches/*`, `xref.json` | `state.json`, `reports/conflicts.json` |
| 11 | manifest | `cli.py` | — | `manifest.json` |

Cost: **zero tokens**, a few seconds.

State directory afterwards (`./.cdp/` — note: `cwd`, not the repo):

```
.cdp/
├── inventory.json      391 files, 9 modules, role per file
├── extract.json        2,847 defines · 6,113 uses · 412 io_edges
├── graph.json          declared: 4 edges   observed: 31 edges   5 levels
├── partition.json      17 scopes, exactly-once proven
├── schedule.json       5 waves
├── xref.json           symbol table, used_by, unresolved
├── dataflow.json       channel paths, process boundaries
├── state.json          fold result — structural claims only
├── manifest.json       commit, versions, phase hashes
├── patches/
│   └── 0000-derived.json
└── reports/
    ├── verify.json
    └── conflicts.json
```

> **Note:** `scan` does **not** write `docs/`. That's `cdp docs`, a separate command.
> This is the most common surprise.

## Simulated run — the wave loop

Structure is done. Meaning is opt-in and costs money.

```bash
cdp prompts --wave 0        # prompts.py → 4 prompt files
```

Each prompt carries: the scope's file list, a structure table (capped at 120 rows,
ranked by evidence count), and inherited sigma from parent scopes.

```
    supervisor = your Claude Code session, following SKILL.md by hand
         │
         ├─ spawn cdp-leaf  →  scope root/common        ─┐
         ├─ spawn cdp-leaf  →  scope root/ledger        ─┤  reads the listed
         ├─ spawn cdp-leaf  →  scope root/gateway       ─┤  files, emits
         └─ spawn cdp-leaf  →  scope root/notify        ─┘  claims[] + unknowns[]
                                                             ↓
                                                        inbox/*.json
```

```bash
cdp collect                 # cli.py → schema.py → verify.py → state.py
```

`collect` does three things in order, and the order matters:

```
validate (schema.py)  →  verify anchors (verify.py + anchor.py)  →  append + fold (state.py)
     ↓ reject              ↓ demote to unknowns[]                      ↓
  bad JSON               anchor didn't resolve                   state.json updated
```

Repeat for waves 1–4. Then:

```bash
cdp docs                    # docs.py → docs/00-overview.md, modules/*.md, CLAUDE.md
cdp query module ledger     # query.py
```

## Sharp edges in the current design

| Issue | Where | Effect |
|---|---|---|
| `scan` never renders docs | `cli.py cmd_scan` | A rescan appears to produce nothing |
| Manifest at scan root creates no module | `inventory.py _module_roots` | `--repo <submodule>` → bogus `src` module, zero edges |
| State defaults to `cwd/.cdp` | `cli.py _paths` | Second scan silently clobbers the first |
| Re-running a scope accumulates | `state.py fold` | Both patches are `complete`; neither supersedes |
| Fold reads every patch ever | `state.py fold` | O(history) — fine at 17 scopes, a wall at 2,000 |
| ~10 silent truncations | `query.py` | Clipped lists with no "N more" marker |
| Verification baked into append | `cli.py cmd_collect` | Can't re-verify later ⇒ no refresh, no decay |

---

# Part 2 — After the roadmap

## What actually changes

| | Today | After |
|---|---|---|
| Persistence | 7 JSON files + patch directory | SQLite store, patches as a table, provenance as columns |
| Scope of an index | one commit, overwritten | N snapshots coexist, keyed `(repo_id, commit)` |
| Supervisor | your Claude Code session | `cdp run`, a real component |
| Leaf input | structure table **+ read the files** | **digest only**, source read is a logged escalation |
| Leaf requirement | tool use + filesystem | text in, JSON out — any model |
| Verification | once, at append | re-runnable inside `fold` ⇒ decay works |
| Failure | invisible gap | a row in `tasks` with a state and a reason |
| Unknowns | an array nobody checks | four deterministic gates; `needs_*` makes them routable |
| Human knowledge | lives in Confluence and rots | `cdp answer` — anchored, decays like any claim |
| Answering a question | compose 3 queries by hand | `query trace` returns the cited reading list |

## New modules

| File | Owns |
|---|---|
| `store/` | **all** SQL. Nothing else imports sqlite3. |
| `snapshot.py` | snapshot identity, retention, incremental extract via `git diff` |
| `runner.py` | the protocol: prompt → [any LLM] → patch JSON |
| `supervisor.py` | `cdp run` — dispatch, lease, retry, resume |
| `refresh.py` | re-verify + relocate + demote |
| `diffs.py` | snapshot-to-snapshot structural diff |
| `link/` | cross-repo scan/prompts/collect/refresh/query |
| `reflect.py` | trajectory writes, elision regret, routing prior |
| `doctor.py` | model conformance harness |
| `helpdoc.py` | `cdp help`, `--json` for front-ends |

`verify.py` moves inside the fold and gains the unknown gates. `prompts.py` gains the digest
builder and the input fingerprint. `query.py` gains `trace`. `cli.py` gains `answer`, which
reuses the existing pipeline wholesale. Everything else in Tier 1 is untouched.

## Simulated run — first scan

```bash
cdp scan --repo ~/src/acme-payments
```

```
resolve store        store/          ~/.cdp/config.toml → acme.db
create snapshot      snapshot.py     snap_01  (acme-payments @ a1b2c3d)
phases 1-7           unchanged       → snapshot.* tables, not JSON files
derive               derive.py       → patches table (author_kind=python)
verify + fold        verify/state    → state, materialised incrementally
docs                 docs.py         → docs/  ← now automatic
manifest             cli.py          → run row
```

Same eleven phases, same modules. Two differences: rows instead of files, and `docs`
runs without being asked.

## Simulated run — the wave loop, now a command

```bash
cdp run --wave-all
```

```
supervisor.py
    │
    ├── reads schedule → 17 tasks, state=pending
    │
    ├── wave 0 ─┬─ task root/common   ── runner.py ──→ [LiteLLM → local 8B]  T2
    │           ├─ task root/ledger   ── runner.py ──→ [LiteLLM → Opus]      T3 (escalated)
    │           ├─ task root/gateway  ── runner.py ──→ [LiteLLM → local 8B]  T2
    │           └─ task root/notify   ── runner.py ──→ [LiteLLM → local 8B]  T2
    │                                                        ↓
    │           each leaf gets a DIGEST, not files. No tool use. No filesystem.
    │                                                        ↓
    │           validate → verify anchors → ADJUDICATE → fold
    │                                          │
    │                   claims[] ──────────────┤
    │                     entailed   Python already knew it — you paid for a paraphrase
    │                     consistent no opinion — normal for intent
    │                     contradicted ✗ rejected + logged (agent error or extractor gap)
    │                                          │
    │                   unknowns[] ────────────┘
    │                     subject not in defines[]        ✗ about nothing
    │                     answerable from xref            ✗ negative entailment
    │                     no needs_* tag                  ✗ malformed
    │                     otherwise → stored, STICKY until an adjudicated claim discharges it
    │                                  and routed: needs_wider_scope → escalate tier
    │                                              needs_other_repo  → link task
    │
    ├── heartbeat every 30s, lease 90s on every dispatched task
    ├── writes fact_leaf_run per task  (input fingerprint + output scorecard)
    └── waves 1-4 …
```

`prompts` and `collect` still exist and still work standalone — `cdp run` just drives
them. That's the runner protocol: anything that can turn a prompt into patch JSON is a
valid backend.

## Simulated run — a week later, `refresh`

This is the flow that has no equivalent today.

```bash
cdp refresh
```

```
snapshot.py    HEAD moved a1b2c3d → f9e8d7c
               git diff --name-status -M  →  6 changed, 1 renamed
               re-extract those 7 files only; carry 384 forward
               recompute graph/resolve/dataflow (always)
               → snap_02

refresh.py     re-verify all 143 claims against snap_02
               ┌ anchor resolved, same line      → carry forward
               ├ anchor resolved, moved 12 lines → relocate, bump anchor_verified_at
               ├ file renamed @100%, no edit     → relocate, review STANDS
               ├ file edited                     → relocate, review INVALIDATED
               └ anchor gone                     → demote → unknown
                                                    "code changed at f9e8d7c"

state.py       fold → 138 live, 5 demoted, 11 anchored-but-unreviewed

cdp status     shows the 11 as their own bucket
cdp run --stale-only    re-reviews just those 11 scopes
```

**Cost of a refresh: 11 leaf calls, not 17.** That's the entire point.

## Simulated run — the supervisor dies mid-run

```bash
cdp run --wave-all
# ... machine sleeps at wave 2, 3 tasks in flight
```

```
tasks table at the moment of death
  root/common     folded
  root/ledger     folded
  root/gateway    dispatched   lease_until = 14:32:10
  root/notify     dispatched   lease_until = 14:32:10
  root/audit      pending
```

```bash
cdp run --resume
```

```
supervisor.py  partition_hash matches → true resume
               2 tasks past lease → reclaim, state=expired → re-dispatch
               1 pending → dispatch
               13 folded → untouched, not re-paid for
```

If code had changed in between, `partition_hash` would differ and it would instead open a
**new run**, inheriting the scopes whose own hash is unchanged. No stale work folded
against a changed partition.

## Simulated run — cross-repo

`link` reads snapshots and writes only `link.*`. Drop every link row and no snapshot moves.

```bash
cdp link scan                  # across acme-payments@f9e8d7c + acme-ledger@3c4d5e6
```

```
link/           gather http_out / http_in / event_publish / event_subscribe
                        persist / schema_own  across both snapshots
                match on path · topic · table
                ├ POST /v1/settle        → exact       payments → ledger
                ├ topic "pay.settled"    → exact       payments → ledger
                ├ ${BILLING_URL}/charge  → AMBIGUOUS   → LLM tier
                └ https://vendor.io/…    → UNMATCHED   ← a deliverable, not an error

cdp link prompts / collect     # only the ambiguous ones
cdp link query --service ledger
```

## Simulated run — someone asks a question

*"What happens if I call `POST /v1/settle` with `amount=0`?"*

```bash
cdp query trace /v1/settle --budget 20000
```

```
query.py + dataflow.py + resolve.py
    entry  SettlementResource.settle        api/.../SettlementResource.java:47   http_in
    ├─ LedgerService.post                   ledger/.../LedgerService.java:112    call
    ├─ settlements                          ledger/.../Settlement.java:23        persist
    ├─ billing-svc /v1/charge               gateway/.../BillingClient.java:64    http_out
    │     └─ link.* → billing-svc@7a8b9c0/.../ChargeResource.java:31   ← P5 continues the trail
    └─ pay.settled                          notify/.../SettledEvent.java:19      event_publish

    unknowns on this path:
      RetryPolicy.execute — why 5 attempts?   needs_human
    elided: 0
    as of acme-payments@f9e8d7c, state v14
```

Six files, each justified by a cited edge. The agent reads those and reasons about `amount=0`.

**CDP does not answer the question.** It has no parameter or branch model — `amount=0` is not
in the index and never will be. What it does is collapse a 40-file grep into a 6-file read
whose completeness is either guaranteed or explicitly qualified by `elided: N`.

## Simulated run — a human answers an unknown

The trace above surfaced one. A engineer who knows the history responds:

```bash
cdp answer root/gateway \
  --subject RetryPolicy.execute --kind rationale \
  --claim "5 attempts because the vendor rate-limits at 5rps; fewer drops legitimate traffic" \
  --anchor payments/.../RetryPolicy.java:88
```

```
cli.py → the same pipeline, no bypass
    schema.py    validate                       ok
    verify.py    anchor resolves at :88         ok
    entail       no io_edge contradicts it      consistent
    state.py     fold  → claim stored, author_kind=human
                        unknown discharged, resolved_by(claim_id, human, snap_02)
```

Three months later the retry loop is rewritten:

```
cdp refresh  →  RetryPolicy.java changed  →  review INVALIDATED (R9)
                the human claim lands in "anchored but unreviewed"
```

That is the whole point. The engineer who wrote it may have left; their note does not quietly
go stale in a wiki. It expires, visibly, and asks to be re-confirmed.

**Note what is *not* bypassed:** `author_kind=human` changes merge precedence — humans outrank
models on interpretation — but not the gate. A human claim contradicted by extraction is
`contested`, not accepted (R11).

## Command reference — old vs new

| You want to | Today | After |
|---|---|---|
| Index a repo | `scan` | `scan` (docs included) |
| Add meaning | `prompts` → spawn agents by hand → `collect` × 5 waves | `cdp run` |
| Update after code changes | rescan everything, claims accumulate | `refresh` → `run --stale-only` |
| Recover from a crash | start over | `run --resume` |
| Undo a bad run | — | `rollback --to-run R` |
| See past state | — | `query --as-of <commit>` |
| Cross-repo | — | `link scan` / `link query` |
| Use a different model | — | `--runner litellm --model …` |
| Know if a model is good enough | — | `doctor` |
| Learn the tool | read `SKILL.md` | `cdp help workflows` |
| Get the reading list for a question | compose `route` + `symbol` + `flow` by hand | `query trace <entrypoint> --budget N` |
| Record what only a human knows | — | `cdp answer` — anchored, and it decays |
| Trust an unknown | it's an unchecked array | four gates + `needs_*` routing |
