# BENCHMARKS — M6.2 graded benchmark, executed

Design: `PHASE/M6_2_BENCHMARK_DESIGN.md`. Harness: `benchmarks/run_benchmark.py`,
`benchmarks/questions.json`. Raw results: `benchmarks/results/run.json`.

**n = 25** questions, spanning `symbol · table · routes · paths · config ·
module · trace` (`RESEARCH_GRAPHIFY.md §7.2`'s stress test: 25–40, not 6).
Target repo: `$TARGET_REPO` (`/Users/sharmp49/git/code_scanner`, pinned commit
`7e10575adf69`, per `PHASE/TARGET.md`). Reader model: **haiku**. Judge model:
**sonnet** (different from the reader, per the plan's own stress test on
judge/reader confound). Two arms, same question set:

- **baseline** — `Read,Grep,Glob` only.
- **cdp** — `Read,Grep,Glob,Bash`, with `Bash` restricted to commands matching
  `*cdp.cli*` (`--allowedTools "Bash(*cdp.cli*)"`), against a real scan of the
  full target already on disk at `/tmp/m62_scratch` (`cdp scan --repo
  $TARGET_REPO --state-dir /tmp/m62_scratch`, 5.36s, 4,686 files, 170 scopes,
  1,860 claims — the `scan`+`query` path only, no leaf/pyramid claims: this
  benchmark does not measure the pyramid).

## Reproduction

```
cdp scan --repo $TARGET_REPO --state-dir /tmp/m62_scratch --quiet
python3 benchmarks/run_benchmark.py
```

Model/timestamp-sensitive: re-running will call live models and will not
reproduce byte-identical text, only similar coverage figures. `results/run.json`
is this run's actual artifact.

## The four numbers

| | baseline | cdp |
|---|---|---|
| **Coverage** | 0.765 | **0.838** (+7.3 points) |
| Tokens (avg/question, input+output+cache-read) | 76,026 | 156,505 |
| Cost (avg/question, USD) | $0.042 | $0.054 |
| Wall time (avg/question, s) | 18.9 | 24.3 |

**Coverage is the headline, per the plan's own guidance** (`RESEARCH_GRAPHIFY.md
§12` item 1: lead with correctness, not a token ratio). +7.3 points is in the
same direction and rough order as Graphify's own reported +11.2, on a
differently-scoped question set and a much smaller n.

**Citation validity**: of the 25 cdp-arm answers, only **4** contained a
`file:line` citation at all (haiku frequently answered in prose without
citing a location even when it had used `cdp query`, which does emit anchors).
Of those 4 answers' citations, **5/6 individual citations verified** (the
file exists and the line number is within range). This is a low sample and a
low base rate — reported honestly rather than rounded up to "citation
validity: 83%" as if it characterized the whole arm.

**Demotion rate** (`verify.py`'s own instrumentation, read directly from the
scratch scan's `snapshot_report` table, not recomputed): **0.0** — 1,864/1,864
claims kept, 0 demoted, `would_survive_lenient: 0`, 2,096/2,096 anchors ok.
Consistent with every prior session's full-target demotion numbers
(`TARGET.md`: "1,279/1,279 derived claims anchored, 0 demoted" at an earlier
claim count, before F2/F15 changed the census).

## Per-category coverage

| category | n | baseline | cdp |
|---|---|---|---|
| routes | 4 | 0.92 | 0.96 |
| trace | 2 | 0.50 | **0.90** |
| config | 3 | 0.56 | **0.81** |
| module | 3 | 0.77 | 0.80 |
| paths | 4 | 0.50 | 0.44 |
| symbol | 4 | 0.88 | 0.94 |
| table | 5 | 1.00 | 1.00 |

CDP's biggest wins are **trace** and **config** — exactly the categories
where the answer requires assembling information across files rather than
reading one. **paths** is the one category where cdp scored *worse*
(0.44 vs 0.50) — worth a second look before generalizing (see caveats).
**table** questions were answered perfectly by both arms; they were all
single-file lookups (a migration script or a `DbSet<T>` line), which grep
handles as well as anything.

## A real defect this run found and fixed, before reporting numbers

The first full run's `--allowedTools "Bash(python3 -m cdp.cli *)"` pattern
only matched a command whose Bash string started with exactly `python3 -m
cdp.cli` — every real invocation the model wrote was `cd
/Users/sharmp49/hackathon/code_scanner && python3 -m cdp.cli ...`, which does
not match a leading-literal pattern. Confirmed via `permission_denials` in
the raw JSON: `cdp` arm calls to `cdp.cli` were being silently denied, so the
"cdp" arm was, for most questions, indistinguishable from the baseline arm
(same tools, same behavior) — invalidating the comparison.

**Fixed**: `--allowedTools "Bash(*cdp.cli*)"` (substring match). Re-verified
with a direct smoke test before re-running (a `cd ... && cdp.cli query stats
...` call now succeeds with `permission_denials: []`). **The entire cdp arm
was re-run and re-judged** after the fix (`run_v1_broken_cdp_arm.json` kept
as the pre-fix artifact for comparison — coverage moved from 0.828 to 0.838
after the fix, a small change, meaning the first run's numbers were not
wildly wrong, but they were measuring the wrong thing methodologically).

**Even after the fix, the cdp arm did not reliably choose `cdp query` over
direct `Read`/`Grep`.** Spot-checking the raw answers: `q23` ("what's the
largest-file-count language") shows the model explicitly running `cdp.cli
query stats` and quoting its exact output (2,262 C# files, matching gold).
`q15` (`SqlInstancesController`'s base route) shows the model reading the
`.cs` file directly instead — a narrow file:line lookup where grep is just as
fast, so a haiku-tier reader had no incentive to reach for the CLI tool. This
is a real, reportable finding, not a harness bug: **cdp's value in this
benchmark concentrates in cross-file aggregate questions (trace, config,
stats), not single-file point lookups**, and a small model does not reliably
self-select the right tool for the question without stronger prompting or a
tool-choice policy — a design lever for a future session, not fixed here.

## Crossover repo size

Located for **`scan`+`query`** only this session (the pyramid's crossover —
leaf dispatch cost vs. reading source directly — needs a live per-scope
model-cost sweep, out of this session's budget; see Caveats):

| files scanned | `cdp scan` wall time |
|---|---|
| 44 (`automation/`) | 0.29s |
| 477 (`sql-pool/`) | 0.83s |
| 4,686 (full `$TARGET_REPO`) | 5.36s |

A single reader-arm model call in this benchmark averaged **~19–24s**. Even a
full-repo scan (5.36s) is cheaper than one model turn, so **CDP's
`scan`+`query` crossover point is effectively immediate** — lower than
Graphify's own stated ~50-file crossover, consistent with the plan's own
prediction that "`scan` is free, so CDP's crossover is lower than the peer's."
The pyramid's crossover is expected much higher (leaf dispatch is itself
model-costly) but is not measured live here; the one directional data point
available is Phase 5's measured ~378 tokens/leaf prompt overhead
(`TARGET.md` M5.6), which bounds the pyramid's *minimum* per-scope cost but
says nothing about where it crosses grep-baseline.

## Caveats

- **n = 25**, the low end of the plan's stated 25–40 range, not the high end —
  a real budget constraint of this session, not a claim that 25 is sufficient
  evidence on its own.
- **Reader = haiku, judge = sonnet**, fixed for this run. Not repeated across
  a capability range (the plan's `doctor`-side stress test, not this one) —
  a single reader/judge pair, so these numbers characterize this pair, not
  "CDP vs. grep" in general.
- **`table` category (5 questions) skews toward single-file lookups** (a
  migration script's `CREATE TABLE` line, an EF Core `DbSet<T>` declaration) —
  both arms hit 1.00 coverage, which is a ceiling effect, not evidence CDP
  and grep are equivalent on harder table questions (e.g. cross-schema FK
  relationships) that this question set does not contain.
- **`trace` has only 2 questions**, short of the 3–5 the design document
  aimed for per category — the two available were the ones this session
  could ground in already-human-verified facts within budget; a future
  session should add more before treating the trace-category coverage gap
  (0.50 → 0.90) as a stable finding rather than a promising one.
- **The expected-failure question (`q25`, DI/reflection)** did not show CDP
  scoring worse, contrary to the design's hypothesis. On inspection, one of
  its two gold facts is a meta-statement about CDP's expected limitation
  rather than a codebase fact ("CDP is expected to score worse here per
  SKILL.md's own stated limitation") — that fact cannot be "covered" by
  either arm's answer in a meaningful way, so `q25`'s coverage numbers should
  be read as noise, not as evidence CDP handles DI-based dispatch fine. A
  cleaner expected-failure question (asking the model to name every caller of
  a DI-registered interface, then checking the answer against a real,
  human-enumerated caller list) is needed to actually test this and was not
  built this session.
- **`paths` scored cdp *below* baseline** (0.44 vs 0.50, n=4) — the one
  category moving the wrong direction. Not investigated further this
  session; flagged rather than silently averaged away.
- **Citation validity's sample is tiny** (4 of 25 cdp answers cited a
  `file:line` at all) — reported as 5/6 rather than rounded to a percentage,
  because a rate over 4 data points is not a rate.
- **Pyramid crossover not measured live** — see above.
- **Judge is not independently cross-checked against a second judge** —
  Graphify reports 90.6% inter-judge agreement / κ=0.81 from a second
  independent judge pass; this run has one judge (sonnet) only. Not done here
  for budget reasons — a real gap against the design's own aspiration, not an
  oversight to gloss over.
- **Tokens/cost include prompt-cache overhead from this being run inside an
  interactive CLI's cache-warming behavior** (`cache_creation_input_tokens`
  dominates both arms' totals — 18k–30k per call even for a one-line
  question). This inflates the absolute token numbers for both arms
  similarly, so the **coverage** comparison is unaffected, but the raw token
  numbers should not be read as "CDP costs 2x baseline in production" without
  accounting for this run's own cache-cold-start overhead, which a real
  agent session would amortize across many questions rather than pay once
  per question as this harness does.

## Second run — reader=sonnet, judge=opus

Same 25 questions, same scratch scan (`/tmp/m62_scratch`, rebuilt fresh before
this run — 5.98s, matching the first run's 5.36s within noise), same two arms
and harness (`benchmarks/run_benchmark.py`, only `READER_MODEL`/`JUDGE_MODEL`
changed). Raw artifact: `benchmarks/results/run.json`; the haiku/sonnet run
above is archived at `benchmarks/results/run_haiku_reader_sonnet_judge.json`
rather than overwritten, so both are auditable.

**Not a clean single-variable swap, stated up front.** The design's own
reader-≠-judge rule means the judge had to change too (sonnet can't judge
sonnet) — so this compares "haiku reads, sonnet judges" against "sonnet
reads, opus judges," not "sonnet reads, sonnet judges" against the original.
A stronger judge may grade slightly differently than sonnet did; this run
cannot isolate reader-model effect from judge-model effect. The closest
honest comparison the constraint allows, not a controlled A/B.

| | haiku/sonnet-judge | sonnet/opus-judge |
|---|---|---|
| Coverage — baseline | 0.765 | 0.799 |
| Coverage — cdp | 0.838 | **0.857** |
| **Δ (cdp − baseline)** | **+7.3 pts** | **+5.9 pts** |
| Tokens/question (cdp) | 156,505 | 207,668 |
| Cost/question (cdp) | $0.054 | $0.137 |
| Wall time/question (cdp) | 24.3s | 23.8s |

**Both arms improved with a stronger reader, and cdp's own uplift narrowed
slightly (7.3 → 5.9 points).** Read as evidence, not disappointment: a
stronger model is already better at extracting facts from raw source with
grep/read alone, so there is less headroom left for the structural index to
add on top. This is consistent with, not contradictory to, the first run's
finding — cdp's value is concentrated where synthesis across files is
required, and a stronger reader needs less help doing that synthesis itself.

### Per-category, both runs side by side

| category | n | baseline (haiku) | cdp (haiku) | baseline (sonnet) | cdp (sonnet) |
|---|---|---|---|---|---|
| config | 3 | 0.56 | 0.81 | 0.56 | **0.94** |
| trace | 2 | 0.50 | 0.90 | 0.90 | 0.90 |
| paths | 4 | 0.50 | 0.44 | 0.50 | 0.50 |
| module | 3 | 0.77 | 0.80 | 0.83 | 0.93 |
| symbol | 4 | 0.88 | 0.94 | 0.75 | 0.75 |
| routes | 4 | 0.92 | 0.96 | 1.00 | 1.00 |
| table | 5 | 1.00 | 1.00 | 1.00 | 1.00 |

`config` is cdp's clearest win in this run (0.94 vs. 0.56 baseline) — a
stronger reader with grep alone still misses config facts scattered across
files; cdp closes nearly the whole gap. `trace`'s gap **collapsed to zero**:
sonnet's baseline arm reasoned its way to a near-complete call chain from
source reading alone (0.90, matching cdp exactly), where haiku's baseline
needed cdp to get there (0.50 → 0.90) — the clearest single data point for
"cdp helps more, the weaker the reader." `paths` again showed no cdp benefit,
consistent across both runs. `symbol` moved *down* for both arms versus the
haiku run (0.88/0.94 → 0.75/0.75) — not investigated further; plausibly
judge-strictness (opus vs. sonnet) rather than a reader-quality regression,
since baseline and cdp moved by the same amount together.

**A real, new finding: sonnet hit more Bash/sandbox friction than haiku
did, though it never produced a wrong answer from it.** 10 of 25 cdp-arm
questions logged at least one denied `Bash` call this run, versus 2 of 25 for
haiku. Inspecting the denials directly (not assumed): this is **not** a
repeat of the earlier `--allowedTools` bug — the same `Bash(*cdp.cli*)`
substring pattern is in place and still matches every `cdp.cli` invocation
tried. What's different is behavioral: sonnet is more exploratory (`--help`,
piped `| grep` variants, a `PYTHONPATH=...` variant, and in one case
explicitly reaching for `dangerouslyDisableSandbox: true` after being
blocked), and several of the denials look like the Bash tool's own
filesystem sandbox reacting to the `cd` into a directory outside the scan
target (`/Users/sharmp49/hackathon/code_scanner`), not the permission
pattern. Every affected question still recovered and used real `cdp.cli`
output in its final answer (spot-checked: `q23`'s C#/Java file-count answer
matches the real census exactly). Flagged as a real harness friction point a
stronger, more adventurous model surfaces more of — not fixed this session.

**Citation validity**: 6 of 25 cdp answers cited a `file:line` (vs. 4/25 for
haiku), of which 5/9 individual citations verified. Same caveat as the first
run: too small a sample to report as a percentage.

**Not done this run, same gaps as before:** no second independent judge pass;
pyramid crossover not measured; `paths`'s below-baseline result still not
investigated.
