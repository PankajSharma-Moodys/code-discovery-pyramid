# EXECUTION_RULES — how to run a phase without burning an hour

Written after Phase 1, which took ~45 minutes and ~120k tokens of context for a
six-milestone change. The work was correct; the execution was not efficient.
This file is the post-mortem and the rules that follow from it. Phase 2 onward
should open with `PHASE/EXECUTION_RULES.md` loaded.

## Where the time actually went

> **Superseded in part.** The dominant cost below was `$TARGET_REPO` scanning at
> 2m31s. `PHASE/FINDINGS.md` F6 fixed the quadratic anchor matcher that caused
> it: a scan is now **6.05s** and `make check TARGET_REPO=...` is **1m06s**, down
> from ~13 minutes. R-E2 and R-E3 still apply — they are good practice — but they
> are no longer the difference between a 10-minute phase and a 45-minute one.
> R-E1, R-E4, R-E5 and R-E8 (context cost) are now the binding constraints.

| Cost | Cause | Avoidable? |
|---|---|---|
| **~25 min** | Eight full scans of `$TARGET_REPO` at 2m31s each | Yes — four were duplicates, and the 2m31s was itself a bug (F6) |
| **~50k tokens** | Reading `cli.py`, `query.py`, `graph.py`, `resolve.py`, `dataflow.py` in full | Yes — the plan cites exact line ranges |
| **~5 min** | Target golden blessed *before* the last code change, invalidating it | Yes — freeze before verifying |
| **~8k tokens** | Three `WebFetch` calls for the hook contract, all truncated | Partly |
| **~5 min** | Three red-then-fix test cycles | Partly — one was a real bug |

The single biggest lever is the first row, and it is not a thinking problem. It
is a scheduling problem: `$TARGET_REPO` costs 2m31s per scan, the gates re-scan
it, and I ran them ad hoc as I went instead of once at the end.

## Rules

### R-E1 — Read the line ranges the plan cites, not the files

Every `phase_n_plan.md` cites exact locations (`inventory.py:104-126`,
`query.py:127`, `prompts.py:120`). Read with `offset`/`limit` around those. Open
a whole module only when about to restructure it. Phase 1 read ~4,000 lines to
change ~600.

**Verify the citations first** — one `grep -n` over all cited symbols at once
confirms the plan is still accurate for a few hundred tokens, and that check is
the "verify the task" step. It caught nothing wrong in Phase 1, which is the
point: it is cheap enough to be worth doing even when it passes.

### R-E2 — `$TARGET_REPO` is scanned **once**, at the end, in the background

Never scan the target to "check something". The rule:

1. Implement every milestone against the fixture. Fixture gates are ~10s.
2. Freeze the code. No further edits.
3. Launch `make check TARGET_REPO=...` **once**, in the background.
4. Write the docs/FINDINGS updates while it runs.

`make check TARGET_REPO=...` already runs determinism (2 scans), fold (1) and
golden (1). Anything scanned before it is a scan paid for twice.

If a milestone genuinely needs target output to be designed (M1.3's budget
default had to bind on a real repo), take **one** scan into a scratch state
directory early, and run every target query against that one directory.

### R-E3 — Freeze before you verify

Phase 1 blessed the target baseline and then changed `query.py`. The baseline
became a lie and the 2m31s×4 had to be repeated. A bless or a gate run is only
valid for the tree that produced it.

Corollary: the last code edit of a phase must precede the first gate run of that
phase. If a gate finds a defect, that is fine — fix it and re-run — but do not
*plan* to edit after launching.

### R-E4 — Batch independent commands into one call

Smoke-testing four CLI invocations is one `Bash` call with `;` between them, not
four. Same for `grep` verification sweeps. Phase 1 made roughly twice the tool
calls it needed.

> **Recurred in Phase 2.** Written down after Phase 1 and violated anyway —
> knowing the rule isn't enough friction. If a message is about to contain two
> or more independent read-only checks (grep, ls, cat), that is the signal to
> stop and combine them into one call before sending, not a thing to remember
> to do next time.

### R-E5 — Run the narrow test module while iterating, the suite once at the end

`python3 -m unittest test_budget` is 0.2s. `discover` is 11s and prints 185
lines. Use the narrow one until the milestone is green.

> **Recurred in Phase 2.** `discover` was run roughly six times across the
> session instead of once at the end, each one re-printing 240+ lines back
> into context. The forcing function: before running `discover`, name what new
> failure it could catch that the narrow module just run did not. If the
> answer is "none, I just want reassurance," don't run it.

### R-E6 — One fetch for an external contract; then design for the uncertainty

The hook output shape took three `WebFetch` calls and still ended unresolved.
The right move after the *first* truncated answer was the one eventually taken:
emit both the specific and the universal field, carry no `permissionDecision`,
and record in the docstring exactly what is verified and what is not. Do that
immediately rather than after two more fetches.

### R-E7 — Exercise on real input **per milestone**, not per phase

This is `PHASE/README.md`'s existing rule and it is not in tension with R-E2.
The cheap version: scan one *module* of the target (~5s), not the whole target.
Phase 1's F5 — `query trace` returning 1 file where the answer was 37 — was
invisible on the fixture and would have been caught in seconds by a single real
module. It was instead caught at the very end, after the baseline was blessed.

### R-E8 — Don't re-read a file you just edited

The Edit tool errors if the match fails. Re-reading to confirm is pure cost.

### R-E9 — Write the plan's FINDINGS/TARGET updates while gates run

They are pure prose and depend on nothing the gate produces except its verdict.
Dead time during a 10-minute gate is the only free time in a phase.

## Phase 2 postscript

Phase 2 (`phase_2_plan.md`, six milestones, run in one continuous pass) took
far longer than Phase 1 despite F6 already having fixed the scan-time
bottleneck that dominated Phase 1's cost. The cost centers were different this
time: not scan time, but scope held too large and rework caught too late.
Four rules follow, plus the two amendments above.

### R-E10 — One milestone per turn; checkpoint before the next

Six milestones with genuine unstated design forks in them (snapshot identity,
what "incremental fold" means, whether the CLI's default backend flips)
executed as one unbroken session is how a defect becomes a
caught-at-the-final-gate defect (F7) instead of a caught-at-its-own-milestone
defect. Post a one-line status — what shipped, what's next — after each
milestone, before starting the next, even under an instruction to run the
whole phase. It costs one message. It buys the option to stop, redirect, or
catch a problem while its blast radius is one milestone wide instead of six.

### R-E11 — Before declaring a milestone done, grep every caller of what it changed

F7: `state.fold`'s signature grew a required-for-real-verification `repo`
argument. Every test calling it already passed `--repo` (written that way from
the start), so the bundled suite stayed green throughout — but two real call
sites (`scripts/fixture_gate.py`, the `Makefile`) had not been touched, and
silently broke, surfacing only at the final gate. **"The test suite is green"
is not "every caller was checked."** After changing a function's contract,
`grep -rn` for every call site — scripts and Makefiles included, not only the
ones the test suite happens to exercise — before moving to the next milestone.

### R-E12 — New code gets a one-line comment; FINDINGS entries are bullet facts

Every new module in Phase 2 got a paragraph-length docstring in the project's
own literary register, and every FINDINGS/decision entry ran 150-300 words.
That register is right for the user-facing design documents
(`RESEARCH_GRAPHIFY.md`, `ARCHITECTURE.md`) and wrong to default to for
internal comments and process logs: none of that prose changes behavior, and
all of it is read back into context on every later turn of the same phase.
Default to CLAUDE.md's own house style (no comment unless the WHY is
non-obvious, one line when it is) even inside a codebase whose *existing* code
is written discursively. Reserve full-paragraph justification for the one or
two decisions per phase that genuinely need the argument spelled out.

### R-E13 — Surface a design fork before implementing it, not after

Phase 2's FINDINGS recorded seven decisions the plan had left open (does
`verdict` get a column and on which table, does the CLI's default backend
become SQLite, what "incremental" concretely means) — all resolved
unilaterally, mid-implementation, and written up only afterward. Writing the
justification after the fact costs the same tokens as asking before, but
forecloses the chance to be redirected while the work is still cheap to
redirect. When a plan names a feature without fully specifying its shape (a
column list with no owning table; a behavior word like "incremental" with no
stated algorithm), that is the moment to ask which of the 2-3 reasonable
readings is wanted — not the moment to pick one and defend it in the
retrospective.
