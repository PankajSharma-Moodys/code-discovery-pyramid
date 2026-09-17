# M6.2 — graded benchmark, design only

**Status: design, not implemented.** `phase_6_plan.md` M6.2's own acceptance
criterion (25–40 questions, two arms, an independent judge, four reported
numbers, a crossover sweep) is dozens of live model invocations — structurally
incompatible with a 20-minute/60k-token session, and has been deferred twice
before for that reason (`PHASE/TARGET.md` M6.3/M6.4 entries). This document is
the design so a future session can execute without re-deriving it. No code, no
model calls.

## 1. Question set — schema and a grounded starter set

25–40 questions, spanning `symbol · table · routes · paths · config · module ·
trace` (`RESEARCH_GRAPHIFY.md §7.2`, `phase_6_plan.md` M6.2). Each question is:

```
{id, category, question_text, gold_facts: [atomic_fact, ...], gold_source: "file:line (human-verified)"}
```

**Gold facts must come from a human reading source, not from CDP's own
output** (plan's own stress-test row: "Golden set is written from CDP's own
output → circular"). The facts below are safe to reuse because they were
already established that way, by prior sessions reading real files directly —
not by trusting a CDP run:

| # | category | question | gold fact | source |
|---|---|---|---|---|
| 1 | routes | What HTTP route and method does `AdminDataController#ArchiveSecurableAsync` handle? | `POST securables/{securableId}/archive` | `FINDINGS.md` F2(revisited): verified against the real file at the cited line |
| 2 | trace | What does `GET /v1/servers` touch, end to end? | 37 files: `ServerResource → ServerService → EServer → ServerMapper`, each via a justifying edge | `FINDINGS.md` F5 |
| 3 | config | Where is `logging.type` read from, and what kind of edge is it? | `config_read` at `src/main/resources/dropwizard-service-config.yml:21` | `TARGET.md` M4.2 exercise |
| 4 | module | Does `$TARGET_REPO`'s root contain a build manifest CDP recognises? | No — root has `Directory.Build.props`/`global.json`/`nuget.config`, none in `MANIFEST_NAMES`; 63 modules found via the normal (non-manifest-rooted) path | `TARGET.md` Finding T2 |
| 5 | paths | Is the pinned baseline commit an ancestor of the repo's current tip? | No — `git merge-base --is-ancestor` fails both directions; history was rewritten in the ~8-month gap | `TARGET.md` Phase 3 (M3.1-M3.3) |
| 6 | symbol | What extractor owns `.cs` files, and what did it originally emit? | Fell through to `GenericExtractor`: 0 defines/imports/io_edges across 264,497 LOC, before F2 shipped a real C# extractor | `TARGET.md` Finding T1 |

Questions 7–40 are **not fabricated here** — they need a human to read fresh
source in `$TARGET_REPO` at execution time, per the anti-circularity rule.
Remaining category quota to fill in that session:

| category | filled | still needed |
|---|---|---|
| symbol | 1 | 3–5 |
| table | 0 | 4–6 (none available — no SQL-table fact has been human-verified yet; `$TARGET_REPO` has 497 SQL files / 669k LOC, unexplored) |
| routes | 1 | 3–5 |
| paths | 1 | 3–5 |
| config | 1 | 3–5 |
| module | 1 | 3–5 |
| trace | 1 | 3–5 |

**Include expected-failure questions**, per the plan's own stress test ("a
harness with no expected failures is a harness measuring itself"): at least 2-3
questions targeting dynamic dispatch, reflection, or runtime DI
(`SKILL.md:198-210`'s own list) that CDP is expected to score worse on. Do not
cherry-pick the question set after seeing what CDP answers well — write it
first (plan's own stress-test row on this exact failure mode).

## 2. Harness contract

Run **out of session** via `claude -p`, matching Graphify's mechanism and
dissolving the measurability objection recorded at `cli.py:274-276` /
`schedule.py:89-93`.

- **Fixed reader model**, capped turns (Graphify used 14 — reuse unless a
  reason emerges not to).
- **Two arms**, same question set, same turn cap:
  - **Baseline**: grep/read/list tools only, no CDP.
  - **CDP-assisted**: baseline tools + `cdp query`/`cdp docs`/`SKILL.md`
    available.
- **Judge model must differ from the reader model** (plan's own stress test:
  "judge-and-reader sharing a model is a real confound the peer acknowledges").
  Concretely: if the reader arms run on model A, grading runs on model B, for
  both arms, by the same judge, blind to which arm produced which answer where
  feasible.
- Each judged verdict must cite **a verbatim quote from the answer** being
  graded (Graphify's own practice, adopted directly) — this is what makes a
  verdict auditable rather than a bare score.

## 3. Grading

```
coverage = (covered + 0.5 * partial) / total
```

against the gold atomic facts listed per question (not the whole gold_facts
list scored as one blob — each atomic fact inside a question's gold_facts is
graded and rolled up, so partial credit is possible within one question).

## 4. Four reported numbers

1. **Coverage** — the headline (Graphify's own comparable number was +11.2
   points, not a token ratio — lead with this, not tokens, per
   `RESEARCH_GRAPHIFY.md §12` item 1's open question about what CDP's
   strongest defensible claim is).
2. **Tokens** — real count from the out-of-session `claude -p` invocation,
   not `source_loc_scheduled`'s proxy.
3. **Citation validity** — re-open every `file:line` the CDP arm emitted and
   check it resolves to real content at that location. CDP-only; the baseline
   arm has no structured citations to check.
4. **Demotion rate** — already instrumented (`verify.py:62-74`), including
   `would_survive_lenient` — reused as-is, not re-derived.

## 5. Crossover repo size

Located **separately** for two paths, not as one ratio (plan: "publishing
both is more honest than publishing a ratio"):

- **`scan`+`query`** — expected lower than Graphify's ~50 files, because
  `scan` itself is free (no model calls). Sweep: pick N repo sizes (e.g. 1,
  10, 50, 200, 1000 files) from real or synthetic repos, measure wall time and
  token cost of `scan`+`query` vs. grep-baseline at each size, find where CDP
  crosses under.
- **The pyramid** (leaf dispatch) — expected much higher, since leaf calls are
  themselves model-costly. Same sweep shape, using `cdp run` cost instead of
  `scan`+`query` cost.

## 6. Caveats section (mandatory in the eventual `BENCHMARKS.md`)

Must state explicitly, following Graphify's own candour that
`RESEARCH_GRAPHIFY.md §7.2` praises:

- The stated **n** (25–40, whatever the final count is) and that it is small.
- Any question that fails to reproduce on a second run (Graphify's own
  45.3%-headline-vs-43.3%-reproduced gap is the model for how to report this
  honestly, not hide it).
- Judge/reader model identities, explicitly, so the non-shared-model claim is
  checkable.
- F2's finding that C#/Scala extraction was added *after* the target's
  original baseline — if any gold fact touches C#/Scala code, note whether it
  predates or postdates that extractor, since recall on that code has a known
  step-change in this repo's own history.
- The table-category gap above (0 human-verified gold facts yet) if it is not
  closed before execution.

## 7. Execution-time checklist (not done here)

1. Read fresh source in `$TARGET_REPO` to fill the remaining ~19–34 questions
   and the empty `table` category.
2. Wire the `claude -p` two-arm harness (`benchmarks/`, out of core per the
   plan's "Modules touched" — must not become a core dependency).
3. Run both arms, judge, compute the four numbers.
4. Run the crossover sweep.
5. Write `BENCHMARKS.md` with a reproduction command that actually reproduces.
6. Budget this as its own session(s) — not a rider on another milestone.
