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

**Status: fixed in Phase 1.** `_declared_edges` now builds `{basename: [modules]}`
and draws an edge only when exactly one candidate survives. An ambiguous
basename yields **no edge** and is returned in a new `graph.declared_ambiguous`
list, which `cmd_scan` turns into a structural unknown naming the dependency and
every candidate. That is the option this entry argued for: `sorted(module_set)`
would have made the flapping stop while leaving CDP asserting one of two
equally-supported edges, which is exactly what `merge.py:186-188` forbids.

`make check-self` should now pass; it is kept as a regression demonstration
rather than removed, since the condition it exercises (two modules named `core`)
is not reproduced by either gate target.

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

---

## F5 — `query trace` resolved entry points to a key the edge graph does not hold

**Severity:** high for the feature, and invisible on the fixture.
**Status: fixed in Phase 1 (M1.5), found by running the milestone on
`$TARGET_REPO` rather than only on `tests/fixtures/minirepo`.**

A route handler is recorded as `Class#method` (`resolve.py` takes it from the
`io_edge` source), while `dataflow.py` keys its adjacency on the file's *primary
symbol*. Walking from the raw handler string found no adjacency and returned a
one-file trace — which renders identically to a genuinely leaf endpoint, i.e.
*"this endpoint touches nothing"*.

The fixture did not show it: `minirepo`'s handler reaches the same files through
the `defines` fallback, so the trace looked plausible. The first real endpoint
traced on the validation target returned one file where the correct answer is
37 (`GET /v1/servers` → `ServerResource` → `ServerService` → `EServer` →
`ServerMapper`, each with its justifying edge).

Two fixes, both kept: `_resolve_entry` resolves a route to its file's primary
symbol, and `_pivot` retries the owning class and then the primary symbol for
any entry point whose node has no outgoing edges, recording `pivoted_from` so
the substitution is stated rather than applied silently.

**The lesson is `PHASE/README.md`'s existing rule, not a new one:** *every
milestone is exercised on real non-fixture input*. This is the second Phase 1
defect — with F1 — that only a real target exposed.

---

## F6 — `find_matches` re-normalised the whole file once per anchor

**Severity:** high for usability, zero for correctness — it computed the right
answer, 25x slower than necessary. **Status: fixed in Phase 1.**

**Where:** `cdp/anchor.py` `find_matches`.

The naive form joined up to `max_span` lines at every start line, normalised the
join, and tested the needle — so it re-normalised the entire file once per span
width **per anchor**. `cProfile` over a 477-file scan:

| | share of total | calls |
|---|---|---|
| `extract_file` | 93% | 475 |
| └ `anchor.find_matches` | **83%** | 6,476 |
| └── `util.normalise_ws` | 51% | **7,168,250** |

1,107 normalisations per anchor, nearly all of lines already normalised for the
previous anchor. It degrades quadratically in file length, which is why the
effect was far worse on the full target (497 SQL files, 669k LOC) than on a
small module.

**Fix.** Normalise each file *once* into a single string plus a char-offset →
line-number index, and locate anchors with `str.find`, which searches in C. Same
computation, redundancy removed.

**Measured:**

| | before | after | |
|---|---|---|---|
| `sql-pool` (477 files) | 3.6s | **0.84s** | 4.3x |
| `$TARGET_REPO` (4,728 files, 1.42M LOC) | 2m31s | **6.05s** | **25x** |
| `make check TARGET_REPO=...` (4 scans) | ~13m | **1m06s** | 12x |

**Why this is believable and not merely asserted.** Anchoring is CDP's trust
boundary: every published claim is anchored here, and an off-by-one does not
crash, it silently cites the wrong line. Three independent checks, all green:

1. **The golden baselines hold byte-identical** — both the fixture's and
   `$TARGET_REPO`'s, the latter blessed from the *pre-fix* code. No claim, no
   anchor, no line number moved.
2. **A differential oracle test** (`tests/test_anchor.py`
   `IndexedMatchingEquivalenceTest`) keeps the naive implementation alive and
   asserts the two agree over every `cdp/**/*.py` file, across real anchors,
   blank-line-straddling multi-line spans, short fragments and absent needles,
   at four span widths — 9,000+ comparisons, 0 mismatches. It is a permanent
   test, not a one-off script, so the equivalence is enforced going forward.
3. **`verify` is unchanged on the target:** 1,279/1,279 derived claims anchored,
   0 demoted.

**The one subtlety, pinned by its own test.** Span width is counted in *source*
lines, including blank ones, because the naive version joined blank lines and
they consumed span width while contributing no text. An index built only over
non-blank lines would accept matches the scan rejected.
`test_span_width_counts_blank_lines` is that assertion.

**Remaining headroom, not taken.** Extraction is embarrassingly parallel per
file and `multiprocessing` is stdlib, which is worth a further 4-8x. It is not
in Phase 1's scope and 6s is no longer the bottleneck for anyone.
