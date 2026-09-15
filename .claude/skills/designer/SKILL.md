---
name: designer
description: Create and manage persistent markdown planning files for structured task execution. Use when the user asks to "create a design”, "track progress", "start a research project", or when a task requires more than 5 tool calls and needs structured phase tracking to stay focused and avoid goal drift.
---

# Researching
Solve the execution problem -- staying focused during complex, multi-step tasks. Uses persistent markdown files to track goals, findings, and progress so you never lose context.

## When to Use

- Multi-step tasks (3+ steps)
- Research projects
- Building features requiring >5 tool calls
- Any task where you might lose track of the goal

## The 3-File Pattern
Create in `./docs_dev/`

| File | Purpose | Update When |
|------|---------|-------------|
| `task_plan.md` | Goals, phases, decisions, errors | After each phase |
| `findings.md` | Research, discoveries, resources | During research |
| `progress.md` | Session log, test results | Throughout session |

These three are **deliverable artifacts scoped to one task**. They are not a memory system. See
"State, not memory" below.

## State, not memory

**Never create or append to `MEMORY.md`, or to any other cross-session, append-only memory file.**
Append-only memory grows without bound, carries stale entries into unrelated tasks, and gets
consulted as if it were current fact. This project has already been misled once by an entry that
was true for a previous iteration and false for this one.

Use the `SKILL.state` method instead ([arXiv:2608.26263v2](https://arxiv.org/html/2608.26263v2)):
carry a single **mutable, fixed-schema state object** rather than an accumulating history.

**The file.** One `docs_dev/state.json`. Compact JSON. Nothing else persists between steps.

**Fixed schema, authored once per project — not per task.** For design/research work:

```json
{
  "goal":        "one sentence: the deliverable",
  "phase":       "current phase name",
  "constraints": {"key": "hard limit the user or the machine imposed"},
  "verified":    {"claim": "result + date it was checked"},
  "decisions":   {"key": "what was decided -> because <one line>"},
  "open":        {"q1": "question -> current working answer"},
  "attempts":    {"what was tried": "outcome -> what it rules out"},
  "pending":     {"observed thing": "not yet known to matter; carried, not acted on"},
  "next":        ["ordered remaining actions"]
}
```

Each field earns its place against a specific failure the paper documents:

| Field | Answers | Why it exists |
|---|---|---|
| `goal`, `phase`, `next` | where am I, what's left | replaces re-reading the transcript to re-derive the plan |
| `constraints` | what may I not do | user instructions and machine limits must outlive the step that found them |
| `verified` | what do I actually know | separates checked fact from assumption; carries the date so it can go stale |
| `decisions` | what did I settle, and why | this is the **projection of the reasoning trace** — the conclusion survives, the trace does not |
| `open` | what is still undecided | each carries a working default so work is never blocked on it |
| `attempts` | what have I already tried | the `cmd_summary` role: stop re-running what already failed |
| `pending` | what did I see that might matter | the one hedge against failure mode 2 (below) |

**Three things that deliberately do NOT go in the state**, and where they go instead:

1. **Chain of thought.** Reason fully within the step, then let the trace go. Persisting it
   reintroduces the quadratic growth the method exists to remove. Write the *conclusion* into
   `decisions` with a one-line "because"; that is all of it that has downstream value.
2. **The current observation.** It is an input, not state — tool output, a file you just read, the
   user's latest message. Commit its consequence to the state *in the same step*, because it will
   not be re-presented. The paper's failure mode 2 is exactly this: relevance recognised too late.
   Two hedges, both required: the `pending` field for "saw it, don't yet know if it matters", and
   `findings.md` as a **raw side-log** — the full observation, unsummarised, retrievable later.
   `state.json` is the sufficient statistic; `findings.md` is the escape hatch when it wasn't.
3. **The trajectory.** When "how did we get here" is itself part of the deliverable — audit trail,
   provenance, a decision log for a reviewer — that is the paper's failure mode 3. It goes in
   `progress.md` as a task artifact. Never in the state, and still never in a memory file.

**The per-step process.**

1. **Read** `state.json` before doing anything that will change it. Do not patch from recall.
2. **Act** — one tool call or one unit of work. Its output is the observation.
3. **Project** the observation: which of the seven fields does it change? If it changes none and
   might still matter, it goes to `pending` plus the `findings.md` side-log. If it changes none
   and cannot matter, drop it.
4. **Patch, never rewrite.** Emit a dictionary merge with null-deletion — setting a key to `null`
   deletes it. Superseded facts are **deleted, not annotated**; that is what an append-only file
   structurally cannot do.

   ```json
   {"state_patch": {"verified":    {"kuzu_wheel": "no cp314 wheel, source build fails, 2026-09-09"},
                    "constraints": {"scope": "this repo only, per user 2026-09-09"},
                    "open":        {"q1": null},
                    "pending":     {"apsw_bundles_own_sqlite": null},
                    "phase":       "design"}}
   ```
   (The two nulls: `q1` got answered; the pending observation was promoted into `verified`.)
5. **Self-validate** before writing. The paper's dominant error mode — 68% of small-model failures
   — is *premature state overwrite or deletion*: replacing a nested object instead of merging into
   it. Check that every key you are not deliberately deleting still survives the patch.
6. **Prune at each phase boundary.** Growth in the state object is a smell. `attempts` and
   `pending` are the ones that bloat; collapse them into `decisions` or `verified`, or delete.

**Honest limits of doing this here.** In the paper a deterministic runtime owns the schema, so a
bad patch triggers rollback and history is genuinely unavailable to the model. This harness is
transcript-based — history cannot actually be discarded, and nothing validates the patch but me.
So what is achievable is narrower, and worth stating plainly: `state.json` is the **canonical**
record, it is what survives compaction and session boundaries, and **when the transcript and the
state disagree, the state wins.** Also note the paper's own result that this is a *long-horizon*
intervention — it lost at T=25 on the software-repo task and only pulled ahead later. Do not
impose it on short tasks; it matches this skill's existing ">5 tool calls" trigger.

## Quick Start

```bash
PLAN_DIR=“docs_dev”
mkdir -p "$PLAN_DIR"
```

Then create `task_plan.md` with:
```markdown
# Task: [Goal]

## Phases
- [ ] Phase 1: Research
- [ ] Phase 2: Design

## Decisions
| Decision | Rationale | Date |
|----------|-----------|------|

## Errors Encountered
| Error | Attempt | Resolution |
|-------|---------|------------|
```

## The 7 Rules

1. **Create plan first** -- Never start complex work without `task_plan.md`
2. **Read before decide** -- Re-read the plan before any major decision
3. **Update after act** -- Mark phases complete, log what changed
4. **2-action rule** -- After every 2 search/browse operations, save findings to `findings.md`
5. **Log all errors** -- Every error goes in the plan with attempt number and resolution
6. **Never repeat failures** -- If an action failed, change your approach
7. **Stay inside this repo** -- Never read, list, measure, or reference any other repository or
   directory on this machine until the user explicitly names it and asks for it. This includes
   "just checking" a sibling project for a realistic example, and includes paths recalled from
   memory or from earlier sessions -- a target that was in scope before is **not** in scope now.
   If outside data would genuinely improve the work, ask first and wait for an answer.

## The 3-Strike Protocol

| Strike | Action |
|--------|--------|
| 1 | Try a different approach entirely |
| 2 | Question assumptions, search for similar issues |
| 3 | Escalate to user with all attempts documented |

## The 5-Question Reboot

Lost? Answer these from your planning files:

1. Where am I? (current phase in `task_plan.md`)
2. Where am I going? (remaining phases)
3. What's the goal? (goal section)
4. What have I learned? (`findings.md`)
5. What have I done? (`progress.md`)