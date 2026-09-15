# Phase 6 — Measurement, digest-first & tiering

**Goal.** Build the instrument first, then make the change it exists to measure.
`doctor` and a graded benchmark come before digest-first leaves, because
`CDP_CLI_SCOPE.md §F` calls `doctor` *"the gate on works with any LLM"* and names
the failure mode as **yield collapse, not corruption** — 17 leaves in, 3 claims
out, 14 nodes of unknowns. That failure is invisible without an instrument, and
digest-first is exactly the change most likely to cause it.

This phase also answers the question `RESEARCH_GRAPHIFY.md §3` raises and CDP
cannot currently answer: does the index actually buy anything, and how much?

## Scope items

| id | Item |
|---|---|
| 4.10 | `cdp doctor` — model conformance harness |
| — | Graded benchmark (`RESEARCH_GRAPHIFY.md §7.2`) |
| 4.2 | Digest-first leaves |
| 4.8 | Tiering v1 — a rule, not a score |

## Preconditions

Phase 5 (runner protocol — `doctor` qualifies models *through* it) and Phase 4
(entailment — `doctor` scores entailment rate and false-unknown rate).

## Reordering note

`CDP_CLI_SCOPE.md §F` lists 4.2 before 4.10. This plan inverts them. The
justification is the scope document's own sentence about yield collapse: shipping
digest-first without the instrument means shipping the highest-risk change blind.
The cost of inverting is one phase of delay on a cost saving; the cost of not
inverting is an undetectable recall regression across the whole corpus.

## Milestones

### M6.1 — `cdp doctor` (4.10)

Extend the `minirepo` golden test (`tests/test_minirepo.py`) into model
qualification. Five metrics:

| Metric | |
|---|---|
| Schema validity | does the model emit a valid patch at all |
| Anchor survival | do its citations verify |
| Entailment rate | `entailed` / `consistent` / `contradicted` split (Phase 4) |
| Recall vs golden | did it find what the golden set says is there |
| **False-unknown rate** | unknowns emitted where the golden set has an answer |

That last one is not optional. **Recall alone is not enough: a model that answers
"unknown" to everything scores perfectly on precision.** Combined with Phase 4's
`needs_*` requirement, this is the countermeasure to compliance bias.

Publish a compatibility table.

**Acceptance.** `cdp doctor --runner X --model Y` produces all five metrics. Run
it against at least three models spanning a capability range (a frontier model, a
mid model, a local ~8B). At least one must fail on false-unknown rate while
passing on recall — if none does, the metric is not discriminating and the golden
set is too easy.

### M6.2 — The graded benchmark

`doctor` measures *leaf* quality. This measures whether the whole thing helps an
agent answer a question, which is the founding claim.

Run the agent **out of session** (`claude -p`), which dissolves the measurability
objection recorded at `cli.py:274-276` and `schedule.py:89-93`. Fix the model,
cap the turns, define the question set over `$TARGET_REPO`, and run two arms:
grep/read/list baseline vs. baseline + CDP.

Design constraints taken from the peer system's own candour
(`RESEARCH_GRAPHIFY.md §7.2`):

- **25–40 questions**, spanning `symbol` · `table` · `routes` · `paths` ·
  `config` · `module` · `trace`. A harness that only tests "where is X used"
  validates one query and certifies thirteen. The peer shipped n=6 and said so.
- **Grade with a different model than answers.** Judge-and-reader sharing a model
  is a real confound the peer acknowledges.
- **Gold atomic facts**, coverage = `(covered + 0.5·partial) / total`, every
  verdict citing a verbatim quote from the answer.
- **Publish the caveats section**, including anything that fails to reproduce.

Report four numbers, two of which the peer system structurally cannot produce:

1. Coverage (the defensible headline — the peer's own measured result was
   +11.2 points of coverage, *not* a token ratio)
2. Tokens
3. **Citation validity** — re-open every `file:line` CDP emitted and check it
4. **Demotion rate** — already instrumented at `verify.py:62-74`, including
   `would_survive_lenient`, the number that decides whether strict anchoring is
   buying correctness or costing recall

Also locate CDP's **crossover repo size** — separately for `scan`+`query` and for
the pyramid. `scan` is free, so CDP's crossover is lower than the peer's ~50
files; the pyramid's is much higher. Publishing both is more honest than
publishing a ratio.

**Acceptance.** A `BENCHMARKS.md` with a reproduction command that actually
reproduces, its own caveats, and a stated n. If coverage does not improve, that
result ships too.

### M6.3 — Digest-first leaves (4.2)

The digest becomes the leaf's input; reading source becomes an explicit, logged
**escalation**. Three wins from one build:

- **Portability** — leaf is text-in / JSON-out, no tools, no filesystem, any
  model including local
- **Determinism** — anchors become *references into the digest* rather than
  strings a model types, making fabrication structurally impossible rather than
  merely detectable
- **Cost**

New metric: **escalation rate**.

Ship it behind a flag, run `doctor` and the M6.2 benchmark in both modes, and
promote to default only if recall and false-unknown rate hold. That gate is the
entire reason this milestone is third and not first.

**Acceptance.** Digest mode passes `doctor` on at least a mid-tier model.
Escalation rate measured on `$TARGET_REPO`. Benchmark coverage in digest mode is
within a stated tolerance of source-reading mode, or the default does not change
and the finding is recorded.

### M6.4 — Tiering v1: a rule, not a score (4.8)

Tiers: T0 structure (free) → T1 derived characterisation (free) → T2 label from
digest (cheap, local model) → T3 semantic read (frontier, residue only).

**v1 ships a rule.** Everything gets T2; escalate to T3 only when the leaf
escalates or the scope has unresolved imports. That is it.

The *residue score* — "how much of this scope can Python already explain by
itself?" — is deliberately deferred (`CDP_CLI_SCOPE.md §N`). Its inputs are
decided; its coefficients are not, and guessing them would put an unvalidated
number on the critical path. The v2 step is to run **a sample of scopes at both
T2 and T3** and measure the delta in *novel* claims (surviving, non-entailed) —
delta ≈ 0 means that scope never needed T3. This phase produces those labelled
pairs as a by-product of M6.2; it does not fit a model.

Tiering doubles as the privacy story: local for T2, escalate nothing sensitive.

**Acceptance.** The rule is implemented and its escalation decisions are logged
with the triggering signal. A T2/T3 sample is run and the novel-claim delta is
recorded per scope — the labelled data Phase 9 needs, collected now because
collecting it later means re-running the models.

## Modules touched

`doctor.py` (new), `prompts.py` (digest builder, input fingerprint, tier
selection), `runner.py` (escalation signalling), `benchmarks/` (new, out of
core — the harness must not become a core dependency), `store/` (escalation and
tier columns on `tasks`).

## Stress tests

| Case | Expectation |
|---|---|
| Golden set is too easy | Every model passes; the harness certifies nothing. The M6.1 acceptance criterion is written to catch this. |
| Golden set is written from CDP's own output | Circular. Gold facts must be established by a human reading source, not by blessing a CDP run. |
| Benchmark questions favour CDP by construction | Have the question set written before looking at what CDP answers well, and include questions CDP is expected to fail (dynamic dispatch, reflection, runtime DI — `SKILL.md:198-210` lists them). A harness with no expected failures is a harness measuring itself. |
| Digest omits the one line the claim needed | This is elision regret (6.4, Phase 9). Instrument it here even if nothing consumes it yet — the signal is free at digest-build time and unrecoverable afterwards. |
| Local 8B collapses to all-unknowns | Exactly the failure mode `doctor` exists to catch. Verify `doctor` catches it and names it, rather than reporting high precision. |
| Escalation rate is ~100% | Digest-first bought nothing. A real possible outcome; report it rather than tuning until it looks good. |
| T3 escalation on unresolved imports fires everywhere | On a repo with many third-party imports the rule may escalate every scope. Check the rate on `$TARGET_REPO` before shipping the rule as default. |

## Exit criteria

- `doctor` produces five metrics across three models, with a published compatibility table, and discriminates on false-unknown rate.
- `BENCHMARKS.md` exists with 25–40 questions, an independent judge, four reported numbers, a stated n, a reproducible command, and its own caveats.
- Crossover repo size located for both `scan`+`query` and the pyramid.
- Digest-first shipped behind a flag and promoted only on measured evidence — or not promoted, with the evidence recorded.
- Tiering v1 rule live; T2/T3 labelled sample collected.

## Out of scope

The residue score itself (§N v3/v4 — logistic regression over a few hundred
labels, deferred until calibrated, and a neural net is explicitly wrong here
because the coefficients must be readable). Lesson-sets and routing priors
(Phase 9). Anything that would put an unvalidated number on the critical path.
