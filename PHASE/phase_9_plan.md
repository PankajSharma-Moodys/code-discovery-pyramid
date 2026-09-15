# Phase 9 — Learning & distribution

**Goal.** Two things that both belong last, for the same reason: they need a
system that already works. Learning needs a corpus of real runs to learn from;
distribution needs a surface stable enough to be worth adapting to.

The learning half is governed by R10: **learning may steer routing, never claim
content. Verification stays downstream of every decision it makes.** That one
rule is what makes the whole mechanism safe, and it is why the peer system's
agent-authored memory layer was reshaped rather than adopted
(`RESEARCH_GRAPHIFY.md §7.12`).

## Scope items

| id | Item |
|---|---|
| 0.17 | Trajectory store — separate DB |
| 0.18 | Trajectory constellation schema |
| 6.3 | Trajectory corpus |
| 6.4 | Elision regret |
| 6.5 | Routing prior |
| 6.6 | Outlier reflection |
| 6.7 | Lesson-sets — cut, versioned, on by default from run 2 |
| 6.8 | Holdout benchmark |
| 7.1 | MCP server |
| 7.2 | LiteLLM adapter |
| 7.3 | Claude Code skill |
| 7.4 | LangGraph / ADK adapters |
| — | Strict mode, gated on coverage (`RESEARCH_GRAPHIFY.md §7.8`) |
| — | Tier-0 `AGENTS.md` portability (§7.9) |

## Preconditions

Phase 6 (entailment verdicts, `doctor`, benchmark, escalation and tier signals —
all of which are what a trajectory row records) and Phase 5 (`tasks`, which
shares the corpus's grain).

## Caveat on detail

Fewer milestones here than in Phases 0–5, and deliberately so. The lesson-set
cadence (6.7), the promotion bar for a cut (6.8) and the residue-score
coefficients (§N) are **open decisions** that the scope document declines to
settle in advance. This plan names them as open rather than inventing numbers
that would read as considered.

## Milestones

### M9.1 — Trajectory store and star schema (0.17, 0.18)

A **separate database** at `~/.cdp/trajectories.db`. Cross-workspace, cumulative,
irreplaceable — separate so a workspace rebuild can never destroy it. That is the
whole reason for the second file.

Two facts sharing dimensions:

- `fact_leaf_run` — grain: one run × scope dispatch
- `fact_run_event` — grain: one run-level event (`started`, `finished`,
  `aborted`, `rolled_back(reason)`, `compacted`)

Dimensions: `dim_model` · `dim_scope_shape` · `dim_template` · `dim_repo` ·
`dim_tier` · `dim_task_kind` (`scope` | `link`).

**Build it as a star from day one.** Retrofitting a star after 50k rows is
miserable, and the rows are being generated from Phase 5 onward whether or not
the schema is ready for them.

R4 binds: the corpus is **write-always**; reading it is versioned and pinned,
never live; **leaves never consult it.**

Phase 3's `rollback` writes `fact_run_event(rolled_back, reason)` here — the run
still happened, nothing is retracted.

**Acceptance.** Star exists; both facts populate from real Phase 5 runs.
Deleting the workspace store leaves the trajectory DB intact — tested.

### M9.2 — Corpus, regret, routing prior (6.3, 6.4, 6.5)

Joined on `scope_hash`. Two halves:

- **Input fingerprint** (written at `prompts`): template version, rows
  included/elided, sigma claims, prompt tokens by section, tier, digest-vs-source
- **Output scorecard** (written at `collect`): tokens, retries, escalations,
  claims emitted/surviving, entailed/consistent/contradicted, unknowns, wall time

Same grain as `tasks` — one writes for recovery, the other for learning.

**Elision regret (6.4)** is the highest-value item here. When a leaf escalates or
emits an unknown: *was the answer in a row the budget elided?* That grades the
ranking function in `prompts.py:120`, which is today an unvalidated guess that
decides what every leaf on every repo gets to see. Phase 6 M6.3's stress table
already requires instrumenting this at digest-build time; this milestone consumes
it.

**Routing prior (6.5)** is nearest-neighbour on scope **shape**, not identity. It
falls out as a `GROUP BY` over `dim_scope_shape` — the star makes it nearly free,
it is deterministic, and no model is involved. Works for `link` too via
`dim_task_kind`.

**Acceptance.** Regret measurable on a real run and non-trivially non-zero or
provably zero. Routing prior is a SQL query, not a model call.

### M9.3 — Outlier reflection and lesson-sets (6.6, 6.7, 6.8)

**Reflection (6.6)** is an LLM call **only** on high-spend/low-yield or
high-contradiction scopes — a handful per run. Its output must be a
**deterministic promotion**: a new `IMPORT_CHANNEL_HINTS` entry, a prompt fix, a
budget change. Not a vague lesson in a store. If a reflection cannot be cashed
out as a deterministic change, it is not a lesson.

**Lesson-sets (6.7)**: the corpus accrues continuously, but a lesson-set is **cut
and numbered** at intervals. A run pins `lessons: v7` in its manifest, and
re-running with `--lessons v7` reproduces exactly. Default is *latest cut*, never
*live corpus* — a live corpus makes every run unreproducible. Off for run #1 (no
corpus), auto-on thereafter, `--no-lessons` to opt out.

Safe **because of R10**: lessons steer routing, never claim content, and
verification stays downstream.

**Holdout (6.8)**: A/B on a pinned snapshot, `--lessons none` vs `--lessons vN`.
**Learn on repos A–E, benchmark on F**, or you are measuring memorisation. This
gates whether a cut is promoted to latest.

**Open decisions to make here, not before:** cut cadence, the promotion bar, and
what a regression on the holdout triggers.

**Acceptance.** A cut is produced, pinned, and reproduces byte-identically on
re-run. The holdout A/B runs on a repo outside the learning set. No lesson
mechanism can alter claim content — enforced by test, not by convention.

### M9.4 — Distribution (7.1–7.4, strict mode, `AGENTS.md`)

**MCP server (7.1): three tools, not thirteen** — `cdp_query` with a typed `kind`
parameter, `cdp_scan`, `cdp_status`. The reference point is damning: `idea` +
`pycharm` MCP servers consume **49.2k tokens permanently** in a live session. A
token-reduction product must not cost tokens at rest. Phase 1's budget work
(1.3) is the prerequisite.

`RESEARCH_GRAPHIFY.md §7.11` recommended *against* MCP on the grounds that it
changes transport, not token count. The three-tool constraint is the answer to
that objection, and the objection stands if the tool count grows.

**LiteLLM adapter (7.2)**: one adapter ≈ 100 providers plus local via
Ollama/vLLM. Highest coverage per unit of work. Lives outside core — core imports
no framework, ever (4.1).

**Claude Code skill (7.3)**: keep it. Best UX today. It is only lock-in if it is
the *only* front-end, which by this point it is not. Rewrite `SKILL.md` for the
post-`cdp run` world — the hand-driven wave loop it documents today is superseded.

**LangGraph / ADK (7.4)**: on demand, bootstrapped by `cdp help --json` (Phase 1
M1.4). These earn their place at L4 consumers (RCA, reviewer agents), not in core.

**Strict mode**, deferred from Phase 1: blocks the first raw source read of a
session, then degrades to the soft nudge — "triggers at most once per session,
never gets stuck", copied verbatim because that constraint is the whole reason it
is safe. **Gated on `state.coverage.fraction`**: blocking a read against a
62%-coverage index denies the model the source *and* leaves the index unable to
answer. CDP has that number (`state.py:194-217`); the peer system has no
equivalent and therefore cannot make this check.

**Tier-0 `AGENTS.md`**: `scan` and `query` need nothing but a shell and Python
3.9. Ship instruction-file guidance for assistants without hooks (Cursor, Codex,
Copilot, Aider). Three tiers: Tier 0 any assistant · Tier 1 hook-capable ·
Tier 2 subagent-capable.

**Acceptance.** MCP server at 3 tools with a measured at-rest token cost.
LiteLLM runner passes the Phase 5 conformance suite and `doctor`. Strict mode
refuses to engage below the coverage threshold and says why. `AGENTS.md` path
demonstrated in one non-Claude assistant.

## Modules touched

`reflect.py` (new), trajectory store (new, separate DB), `prompts.py` (input
fingerprint consumption, lesson-pinned routing), `mcp/` (new, outside core),
adapters (outside core), hook scripts (strict mode), `SKILL.md` (rewrite),
`AGENTS.md` (new).

## Stress tests

| Case | Expectation |
|---|---|
| A lesson changes claim content | R10 violation. Must be structurally impossible, not merely discouraged — enforced by test. |
| Lesson-set trained and benchmarked on the same repos | Measures memorisation. 6.8's A–E / F split is the countermeasure; verify the split is real. |
| Corpus has 3 runs | Far too few to learn from. Define a minimum before lessons auto-enable, or run #2 ships a prior fitted to noise. |
| Reflection produces an unactionable lesson | Discard it. A store of vague lessons is the peer system's failure mode, explicitly reshaped away from. |
| MCP tool count grows to 13 | The token-at-rest objection returns in full. Cap it and write down why. |
| Strict mode at 100% coverage but stale index | Coverage is not freshness (R8, two dates). Gate on **both** coverage and HEAD match. Easy to miss; it is the same conflation R8 exists to prevent. |
| LiteLLM to a local 8B that collapses | `doctor` (Phase 6) catches it. Verify the adapter surfaces `doctor`'s verdict before a full run, not after. |
| Trajectory DB deleted | Irreplaceable by construction. `export --corpus` (Phase 7 M7.5) is the backup path; confirm it covers the star. |

## Exit criteria

- Trajectory star populated from real runs; survives a workspace rebuild.
- Elision regret measured — the ranking function in `prompts.py` is no longer an unvalidated guess.
- Routing prior is deterministic SQL.
- A lesson-set is cut, pinned, reproduces exactly, and passes a holdout A/B on a repo outside the learning set.
- No mechanism can alter claim content — enforced by test.
- MCP at 3 tools with a measured at-rest cost; LiteLLM passes conformance and `doctor`.
- Strict mode gated on coverage **and** HEAD; `AGENTS.md` tier-0 path works.
- `SKILL.md` rewritten for the post-`cdp run` world.

## Out of scope

The residue score's coefficients (§N v3/v4) — still deferred until the labelled
corpus from Phase 6 M6.4 is large enough, and still logistic regression rather
than a neural net, because in a product built on explainability the coefficients
must be readable. Hosted service, telemetry, PR triage
(`RESEARCH_GRAPHIFY.md §9.5`). Embeddings — neither system uses them and "no
vector store" is the shared baseline, not a differentiator.
