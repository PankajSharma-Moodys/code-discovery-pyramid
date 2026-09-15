# PHASE — execution plan for the `cdp` CLI

Derived from `RESEARCH_GRAPHIFY.md` (peer analysis), `CDP_CLI_SCOPE.md` (scope to
completion, the authority on *what*) and `ARCHITECTURE.md` (today vs. after, the
authority on *shape*). Current implementation: `.claude/skills/cdp/` — 20 modules
+ 8 language extractors, ~8.9k LOC, stdlib only, file-backed `.cdp/` state.

Each `phase_n_plan.md` is self-contained: goal, scope items traced to their id in
`CDP_CLI_SCOPE.md`, preconditions, milestones with acceptance criteria, modules
touched, adversarial stress tests, exit criteria, and what is explicitly *not* in
it.

## The phases

| # | Phase | Ships | Scope ids |
|---|---|---|---|
| [0](phase_0_plan.md) | Baseline & guardrails | repo layout, determinism harness, target repos | — |
| [1](phase_1_plan.md) | Correctness & honest output | the field bug, budgets, `help`, `query trace`, the hook | 1.1–1.4, 1.6, 6.2 |
| [2](phase_2_plan.md) | Store & schema | store boundary, SQLite, snapshots, runs/tasks | 0.1–0.7, 0.12–0.16, 2.3 |
| [3](phase_3_plan.md) | Freshness & history | `refresh`, `diff`, `rollback`, `--as-of`, `gc` | 0.8–0.11, 3.1–3.7 |
| [4](phase_4_plan.md) | Trust gates & human knowledge | entailment, unknown discipline, `answer` | 6.1, 6.1b, 1.5, R12 |
| [5](phase_5_plan.md) | Runner & supervisor | runner protocol, `cdp run`, leases, resume | 4.1, 4.3–4.7, 4.9 |
| [6](phase_6_plan.md) | Measurement, digest-first, tiering | `doctor`, graded benchmark, digests, T2/T3 rule | 4.10, 4.2, 4.8 |
| [7](phase_7_plan.md) | Scale & durability | scope selector, `compact`, `verify --full`, `export` | 2.1, 2.2, 2.4–2.6, 0.19 |
| [8](phase_8_plan.md) | Cross-repo link | `link scan/prompts/collect/refresh/query` | 5.1–5.7 |
| [9](phase_9_plan.md) | Learning & distribution | trajectory star, lesson cuts, MCP, LiteLLM | 0.17–0.18, 6.3–6.8, 7.1–7.4 |

## Sequencing rationale, and where it departs from `CDP_CLI_SCOPE.md §K`

The scope document's P0–P7 are *priority bands*, not an execution order. Four
deliberate re-orderings:

1. **`2.3` store resolution moves forward into Phase 2.** §K draws it as an
   independent branch, but it is config resolution and it belongs with the store
   it resolves. Pulling it forward unblocks git hooks (3.7) and the PreToolUse
   hook (6.2) far earlier than the "Scale" band implies.
2. **`6.2` PreToolUse hook moves back into Phase 1.** `RESEARCH_GRAPHIFY.md §7.1`
   ranks it the single largest token lever at the lowest cost. Its only blocker
   is state location, and Phase 1 ships it `--in-repo`-only with a hard no-op when
   state is absent or `inventory.head != git HEAD` — exactly the stress-tested
   form in §7.1. Phase 2's store resolution then widens it.
3. **`4.10 doctor` and the graded benchmark precede `4.2 digest-first`.** The
   scope document itself calls `doctor` "the gate on *works with any LLM*" and
   names yield collapse as the failure mode. Shipping digest-first before the
   instrument that would detect a recall regression means shipping it blind.
4. **`1.5 cdp answer` moves out of P1 into Phase 4.** Its stated pipeline is
   `validate → verify anchor → entail → fold`, and `entail` is 6.1. It cannot
   ship in the "small, ships first" band without the gate it depends on.

Everything else follows §K's dependency graph.

## Rules that apply to every phase

- **R1–R12 in `CDP_CLI_SCOPE.md` are binding.** Any milestone that appears to
  need an exception has found a design error, not an exception.
- **The Tier 1 / Tier 2 line is absolute** (`ARCHITECTURE.md`): leaf agents never
  emit structure, Python never emits meaning.
- **Stdlib only.** A third-party dependency in core defeats the distribution
  property `RESEARCH_GRAPHIFY.md §8.7` identifies as CDP's real advantage.
- **Every milestone is exercised on real non-fixture input**, not only on
  `tests/fixtures/minirepo`. Green tests on a 12-file fixture are not evidence
  about a 391-file repo.
- **Determinism gate** (Phase 0): two scans of one commit produce byte-identical
  canonical output, `manifest.json` excepted. Every phase re-runs it.
- **`fold --check` and `check_order_independence` must pass after every phase.**

## Detail gradient — stated, not hidden

Phases 0–5 are planned to milestone-and-acceptance-criteria depth; the decisions
they rest on are made. Phases 6–9 carry the same structure but fewer milestones,
because genuinely fewer decisions are settled — `CDP_CLI_SCOPE.md §N` defers the
residue score's coefficients on purpose, and the lesson-set cadence (6.7) and
Postgres trigger (2.6) are similarly open. Those plans name the open decision
rather than inventing a number for it.

## Validation target

`$TARGET_REPO` — a private repository, to be named and pinned to a commit at
Phase 0 M0.3. Until then it is a placeholder. The determinism baseline, the
module-detection fix (1.1), the benchmark question set (Phase 6) and every
"exercise on real input" acceptance criterion resolve against it.
