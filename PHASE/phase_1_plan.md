# Phase 1 — Correctness & honest output

**Goal.** Fix the bug that was hit in the field, stop the index from silently
lying about completeness, make the tool explain itself, and turn the "prefer the
index over grep" instruction from prose into enforcement. Everything here is
file-backed — no store required — and every item is small.

When this phase is done, an answer from CDP either carries its full evidence or
says exactly how much it dropped, and a rescan visibly produces something.

## Scope items

| id | Item | Source |
|---|---|---|
| 1.1 | Module detection at scan root | `CDP_CLI_SCOPE.md §C` |
| 1.2 | `scan` renders docs by default | `CDP_CLI_SCOPE.md §C` |
| 1.3 | Budget + truncation honesty | `CDP_CLI_SCOPE.md §C`, `RESEARCH_GRAPHIFY.md §7.3, §10` |
| 1.4 | `cdp help`, `--json` | `CDP_CLI_SCOPE.md §C` |
| 1.6 | `query trace <entrypoint> --budget N` | `CDP_CLI_SCOPE.md §C` |
| 6.2 | PreToolUse hook (partial — `--in-repo` only) | `CDP_CLI_SCOPE.md §H`, `RESEARCH_GRAPHIFY.md §7.1` |

## Preconditions

Phase 0 complete. The golden baseline is what proves 1.1 and 1.3 changed only
what they meant to.

## Milestones

### M1.1 — Root-with-manifest is one named module (1.1)

`inventory.py:104-126` `_module_roots` deliberately excludes the repository root:
*"A manifest at the repository root does not create a module; the root is the root
scope (§3.3)."* That reasoning holds for a monorepo whose root manifest is an
aggregator. It fails for the case actually hit — pointing `--repo` at a single
module. The fallback at `inventory.py:121-125` then invents a module per
top-level directory, producing a bogus `src`, zero declared edges and zero
observed edges.

Fix: when a manifest exists at the scan root **and** no sub-manifests exist, the
root is one module named from the manifest (artifactId / name / module path),
not from the directory. When sub-manifests exist, preserve today's behaviour —
the root stays the root scope.

Degrade honestly: if the manifest cannot be named, emit a structural unknown
saying module identity was not readable, rather than guessing.

**Acceptance.** Fixture: a single-module Maven project. Before: ≥1 bogus module,
0 declared edges. After: exactly 1 module, named from `<artifactId>`, and
`query stats` shows a non-empty declared edge set where one exists. The
multi-module fixture's golden output is unchanged — this is the regression that
matters, since the fix touches the shared path.

### M1.2 — `scan` renders docs (1.2)

Add `docs` rendering to the end of `cmd_scan` (`cli.py:185-288`) with `--no-docs`
to opt out. `cmd_docs` stays as a standalone command.

Watch the interaction with Phase 0's determinism gate: `docs.py` output must be
deterministic too, and it is currently unmeasured. Add it to the gate in this
milestone rather than discovering it in Phase 3.

**Acceptance.** `cdp scan` writes `<state>/docs/`. `--no-docs` skips it. Two
scans produce byte-identical docs. `cli.py`'s `next` hint drops `cdp docs`.

### M1.3 — One budget, ranked elision, stated elision (1.3)

Eleven truncation sites, verified in source. Ten are silent:

| Site | Cut | Marker |
|---|---|---|
| `query.py:127` | `claims[:6]` | none |
| `query.py:138` | `files[:10]` | none |
| `query.py:159` | `defines[:40]` | none |
| `query.py:163` | `edges[:40]` | none |
| `query.py:165` | `claims[:20]` | none |
| `query.py:258` | `migrations[:12]` | none |
| `query.py:261` | `evidence[:8]` | none |
| `query.py:381` | `near_misses[:20]` | none |
| `query.py:504,508,510` | `defines[:20]`, `io_edges[:20]`, `claims[:10]` | none |
| `query.py:534` | `claims[:25]` | none |
| `query.py:555,561,568,569` | `migrations[:6]`, `evidence[:6]`, `declared[:4]`, `read[:6]` | none |
| `query.py:481-484` | `used_by[:12]` | ✅ `"... %d more"` |

Generalise the last one. Three rules:

1. **`--budget N` on every query**, honoured by both the JSON path and the
   renderer. A budget is a row/character allowance, not a per-list constant.
2. **Ranked truncation** — drop lowest-evidence rows first, reusing the policy
   at `prompts.py:120` (`sort by -len(evidence), then subject`). Using CDP's own
   existing idiom keeps the system internally consistent and means the ranking
   has one definition, not two.
3. **Mandatory `elided: N`** in every response, plus `as of commit X, state vY`
   on every response. Carry `budget_fired` / `elided_*` instrumentation forward
   from `prompts.py:68-69` so we learn whether the default ever binds.

**`stats` and `coverage` are never budgeted.** They are the epistemic safety
rails that `SKILL.md:58-61` tells the model to check before saying "there is no
X"; budgeting them would compromise the check that detects compromised answers.

**Acceptance.** No renderer truncates without a marker — enforced by a test that
greps `query.py` for slice literals on result lists and fails on a new one.
`q_table` and `q_config` on `$TARGET_REPO` report `elided: N` where N > 0.
`query stats --budget 1` still returns complete stats.

### M1.4 — `cdp help` with `--json` (1.4)

Guidance, not flags: when to use what, in what order, what comes next.
`cdp help workflows` ships named recipes — onboard a repo · refresh after a
sprint · investigate a bug · review a PR. `--json` emits the machine-readable
surface so a LangGraph/ADK front-end discovers commands without a hand-written
adapter (this is what Phase 9's 7.4 is bootstrapped from).

New module `helpdoc.py`. The command list must be **derived from the argparse
tree**, not a parallel hand-maintained table — a help text that drifts from the
CLI is worse than none.

**Acceptance.** `cdp help` and `cdp help workflows` render. `cdp help --json`
validates against a schema committed alongside it. A test asserts every
subparser in `_parser()` appears in `--json` output.

### M1.5 — `cdp query trace <entrypoint> --budget N` (1.6)

The bundle operation an L4 consumer reaches for first: the minimal cited file set
needed to answer a question about an entry point. Composes `dataflow.py`
traversal + `resolve.py`'s `used_by` transpose (`resolve.py:216-228`) + M1.3's
budget work. Output shape is specified in `ARCHITECTURE.md` — each file carries
the edge that justified its inclusion, unknowns on the path are surfaced, and
`elided: N` is explicit.

**It must not over-claim.** `ARCHITECTURE.md` states it plainly: CDP does not
answer the question, it collapses a 40-file grep into a 6-file read whose
completeness is either guaranteed or explicitly qualified. The renderer says so.
Carry `dataflow.py:16-19`'s caveat: an import proves reachability, not invocation.

**Acceptance.** On `$TARGET_REPO`, `query trace` on a known HTTP entry point
returns a file set that a human agrees is sufficient, each with a justifying
edge. Budget 0 returns the entry point and `elided: N`, never an empty set with
no explanation.

### M1.6 — PreToolUse hook, soft nudge (6.2, partial)

Fires on `Read`/`Grep`/`Glob` against a path whose `inventory.json` role is
`source`. Injects: *".cdp/ indexes this repo at `<sha>`. `cdp query symbol X` /
`query file <path>` returns the same fact with citations at a fraction of the
cost. If you still need the source, Read only the cited lines."*

Role scoping is the advantage over the peer system, which fires on any read
(`RESEARCH_GRAPHIFY.md §7.1`): `role == "docs"` means editing a README never
triggers it.

**Three hard no-ops, all mandatory:**
- `.cdp/` missing
- `inventory.head != git HEAD` — a hook nagging about an index that does not
  describe the working tree is worse than no hook
- state not resolvable from the target repo

That third one is why this milestone is `--in-repo` only. The default state
location is `cwd/.cdp` (`cli.py:147-156`), outside the analysed repo by
deliberate design (`cli.py:14-17`). A hook installed in the target cannot find
it. Phase 2's store resolution (2.3) dissolves this; until then, `cdp install`
must state the constraint rather than installing a hook that silently never fires.

Strict mode is **not** in this milestone — it blocks reads, and blocking against
an index below its coverage threshold is actively harmful (`RESEARCH_GRAPHIFY.md
§7.8`). It lands in Phase 9 gated on `state.coverage.fraction`.

**Acceptance.** Hook fires once on a source read in an `--in-repo` install; does
not fire on a README edit; no-ops silently after `git commit` moves HEAD. A test
asserts each no-op condition independently.

## Modules touched

`inventory.py` (M1.1), `cli.py` (M1.2, budget plumbing, help, trace subcommand),
`query.py` (M1.3, M1.5 — the largest diff), `dataflow.py` + `resolve.py`
(read-only consumers for trace), `docs.py` (determinism), `helpdoc.py` (new),
hook script + `install` (M1.6).

## Stress tests

| Case | Expectation |
|---|---|
| Repo with a root manifest **and** sub-manifests | Today's behaviour preserved — root stays the root scope. This is the regression M1.1 is most likely to cause. |
| Root manifest with no readable name | Structural unknown, not a guessed name. |
| `--budget` smaller than one row | Return zero rows plus `elided: N` and a note that the budget admits nothing. Never return a row over budget, never return nothing silently. |
| Budget interacts with ranked elision on ties | Tie-break must be total and deterministic (`-len(evidence)`, then `subject`, then `id`) or the determinism gate fails intermittently — the worst failure mode to debug. |
| `query trace` on an entry point inside a cycle | `dataflow.py`'s `--max-hops` (default 8) bounds it; report hops exhausted as `elided`, not as completion. |
| `query trace` on a symbol with no dataflow edges | Return the defining file and say why the trail stops. Empty output would read as "nothing calls this". |
| Hook fires inside CDP's own repo | Role scoping does not save us — CDP's own `.py` files are `role == "source"`. Verify the no-op conditions cover developing CDP itself, or the hook makes this repo unpleasant to work in. |
| Hook + dirty working tree | HEAD matches but files are edited. The index is stale in a way the HEAD check cannot see. Decide: nudge with a "working tree is dirty" qualifier. Record the decision; Phase 2's ephemeral snapshots (0.6) make it precise. |

## Exit criteria

- `make check` green, golden diff explained line by line — every change intentional.
- Zero unmarked truncations in `query.py`, enforced by test.
- `cdp scan` on `$TARGET_REPO` produces docs; a rescan visibly produces output.
- Single-module scan produces exactly one correctly-named module.
- `cdp help --json` validates; `query trace` demonstrated on a real entry point.
- Hook demonstrated firing, and demonstrated no-opping in all three conditions.

## Out of scope

No store, no SQLite, no snapshots, no `refresh`. No strict mode. No `cdp answer`
— it needs the entailment gate (Phase 4). `query hubs` and deterministic
file-purpose claims from leading comments (`RESEARCH_GRAPHIFY.md §7.5, §7.6`)
are **not in `CDP_CLI_SCOPE.md`** and are deferred to a backlog decision rather
than smuggled in here; both are cheap and both are defensible, but neither
survived into the scope document and this plan does not overrule it silently.
