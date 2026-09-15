# FINDINGS — defects found while building the Phase 0 baseline

`PHASE/phase_0_plan.md` is explicit that Phase 0 fixes nothing: *"If a bug is
found while building the baseline, record it in Phase 1 rather than fixing it
here — a baseline captured mid-fix describes nothing."* This file is that
record. Nothing here is fixed; each entry names the phase that should own it.

---

## F1 — `_declared_edges` resolves module basenames from a `set`

**Severity:** high — it is a *non-determinism*, so it silently produces a
different architecture on different runs of the same commit.

**Where:** `cdp/graph.py:180`

```python
by_basename = {m.rsplit("/", 1)[-1]: m for m in module_set}
```

`module_set` is a `set` (`cdp/graph.py:28`). When two modules share a basename
the dict comprehension keeps whichever the set yields last, and set iteration
order over strings varies with `PYTHONHASHSEED`. Two scans of one commit then
disagree about which module a manifest-declared dependency points at.

**Confirmed, not inferred:**

```
$ PYTHONHASHSEED=1 …  core -> .claude/skills/cdp/tests/fixtures/minirepo/core
$ PYTHONHASHSEED=5 …  core -> tests/fixtures/minirepo/core
```

and end to end, six consecutive runs of the reproducibility gate on this
repository: `2 2 0 0 0 0` (2 = differences found). The divergence propagates
from `graph.json` into `patches/`, `state.json` (changing `fold_hash`) and the
rendered `docs/00-overview.md`, and flips claim `confidence` between `high` and
`medium` — because the "NOT declared in the build manifest" test compares the
observed edge against a declared edge that moved.

**Why it had not been seen.** It requires two modules with the same basename.
M0.1 created exactly that in this repository by vendoring a second copy of
`tests/fixtures/minirepo` into `.claude/skills/cdp/`. It is not an artifact of
vendoring, though: `core`, `api`, `common` and `web` are among the most common
module names in any monorepo, and the first target that has two of them will hit
this. `$TARGET_REPO` happens to have no duplicate basenames across its 63
modules, which is why its baseline is stable.

**Also wrong, independently of the ordering.** `owners_of`
(`cdp/graph.py:88-109`) documents the opposite policy for the *observed* graph:
*"Returning a list rather than a winner is deliberate: §6.4 forbids the resolver
from picking when an FQN is declared in more than one place."* The declared
graph picks a single winner under exactly that ambiguity. Making it
deterministic by sorting would fix the flapping baseline while leaving CDP
quietly asserting one of two equally-supported edges — which `merge.py:186-188`
calls out as the thing not to do: *"a merge operator that always produces an
answer is a merge operator that fabricates under contention."*

The fix is therefore not `sorted(module_set)`. An ambiguous basename should
either resolve to all candidates, or become an `unknown` (R6: *a failed scope
becomes an `unknown`, never a silent gap*).

**Owner:** Phase 1 (correctness band). It is a bug hit in the field, of the same
family as scope item 1.1, and Phase 1 is where honest degradation lives.

**Consequence until fixed:** this repository cannot be a golden or determinism
target for itself. `make check` uses `$TARGET_REPO` and the `minirepo` fixture,
both of which have unique module basenames. `make check-self` exists to
demonstrate the failure and is not part of the gate.

---

## F2 — no C# or Scala extractor; 48% of `$TARGET_REPO` yields nothing

**Severity:** high for measurement, zero for correctness — CDP does not make
wrong claims about C#, it makes none.

2,262 `.cs` files (264,497 LOC) and 73 `.scala` files (11,850 LOC) produce zero
defines, zero imports and zero io_edges. Full numbers and the argument in
`PHASE/TARGET.md` Finding T1.

**Owner:** a language-extractor decision, informed by `RESEARCH_GRAPHIFY.md §9`
item 4. It should be settled *before* Phase 6's graded benchmark, because recall
measured over a corpus where half the code is invisible measures the extractor
set rather than the repository.

---

## F3 — `cdp selftest` reported success on an empty suite

**Severity:** medium. **Status: fixed in Phase 0 (M0.5), recorded for
completeness because the fix is the milestone.**

`cli.py:592-599` already documented one round of this failure: in-process
discovery "silently found zero tests instead of saying so", fixed by running a
subprocess. But `unittest discover` exits 0 when it discovers nothing, so the
original failure mode survived the fix. M0.5 adds a floor (`MIN_TESTS`) and a
parse of the `Ran N tests` line, and fails when the count cannot be determined
at all rather than assuming success.

---

## F4 — `python3 -m cdp.cli` exited silently

**Severity:** low. **Status: fixed in Phase 0 (M0.1).**

`cdp/cli.py` had no `__main__` guard, so the invocation named in Phase 0's own
M0.1 acceptance criterion produced no output and returned 0. Added a guard plus
`cdp/__main__.py`. Worth recording only because an acceptance criterion asserted
behaviour that did not exist, which is the failure mode Phase 0 is built to
prevent.
