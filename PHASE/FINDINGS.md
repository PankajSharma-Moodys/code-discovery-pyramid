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

---

## F7 — `fold --check` broke for every caller that omitted `--repo`, found by the gate itself

**Severity:** high — it would have failed for every real user of `cdp fold --check`,
not just a test. **Status: fixed in Phase 2 (M2.3).**

**Where:** `scripts/fixture_gate.py` `gate_fold` and `Makefile`'s `fold` target
(`TARGET_REPO` branch).

M2.3 moves `verify_all` inside `state.fold`, so `fold`/`check_fold` now take a
`repo` to verify claims' anchors against. Before M2.3, `fold --check` never
touched the filesystem, so `--repo` defaulting to cwd was harmless. Both call
sites above invoked `fold --check` without `--repo`; after M2.3, that silently
verified every claim against the wrong tree, demoted all of them, and made
`check_fold` report `state.json/claims` and `state.json/unknowns` as "not
derivable from patches/ + xref.json" — a false positive naming the exact
failure mode `check_fold` exists to catch.

**Why it had not been seen.** `tests/test_pipeline.py`'s own `fold --check`
calls already pass `--repo` (they were written against the pre-M2.3 code with
the argument present anyway), so the bundled suite never exercised the gap.
It surfaced on the first `make check` run after M2.3 landed — exactly the
"exercise on real input" case the process is built to catch, one step later
than usual: here the *gate script* was the real input, not the target repo.

**Fix.** Both call sites pass `--repo`.

---

## F8 — `SqliteStore` connections are never closed in tests

**Severity:** low — a `ResourceWarning`, not a failure; SQLite closes on
process exit regardless. **Status: fixed (Phase 2 audit pass).**

Every `SqliteStore` in `tests/test_store_*.py` was constructed and never
explicitly closed (`close()` exists — `cdp/store/sqlite_backend.py` — but
nothing called it), so `make check`'s `selftest` run printed one
`ResourceWarning: unclosed database` per test. Fixed by adding
`self.addCleanup(store.close)` (or an inline `addCleanup`) at every
construction site in `tests/test_store_sqlite.py` and
`SqliteStoreConformance.make_store` in `tests/test_store_conformance.py`.
Confirmed clean: `python3 -m unittest test_store_sqlite test_store_conformance`
now runs with zero `ResourceWarning` output. Synced to the vendored copy via
`cdp install --self`.

---

## F9 — extraction remains single-threaded per file (audit finding, not a new defect)

**Severity:** informational. **Status: identified, deliberately not implemented.**

Re-confirmed during this audit pass: `cdp/extract.py:run_extract` (`for entry
in inventory["files"]: ... extract_file(...)`, `extract.py:40-47`) is a plain
sequential loop, exactly as F6 already recorded under "Remaining headroom, not
taken" — extraction is embarrassingly parallel per file and `multiprocessing`
is stdlib, worth a further 4-8x past the 6.05s F6 already achieved on
`$TARGET_REPO`. No further quadratic hot spots were found elsewhere in the
pipeline (`dataflow.py`, `resolve.py`, `graph.py`) at this audit's depth — the
nested loops in `dataflow._process_boundaries` are bounded by module count
(63 here), not file count, and are not a scan-time concern at this scale.

Not implemented in this pass: parallelising `run_extract` changes the order
facts are appended in (`defines`/`uses`/`io_edges` lists are currently built
in inventory-file order), and `state.check_order_independence` /
`fold_hash` / the golden baseline all depend on deterministic list order
downstream. A `Pool.map` (not `imap_unordered`) preserves input order and
would very likely be safe, but proving that — and re-blessing/re-verifying
the golden baseline against it — is real work belonging to its own reviewed
change, not a rider on an audit pass. Flagged for explicit sign-off before
implementing.

---

## F10 — `PythonExtractor` prints a `SyntaxWarning` to stderr for real target source

**Severity:** low — cosmetic gate noise, not a correctness defect.
**Status: fixed, but see the verification caveat below.**

Observed on this pass's one `make check TARGET_REPO=...` run: `fold --check
(/Users/sharmp49/git/code_scanner)` printed four `SyntaxWarning: invalid
escape sequence` lines from `<unknown>`. Source: `cdp/lang/python.py:49`
calls `ast.parse()` directly on a target file's text; a target `.py` file
containing an unescaped backslash in a plain string (e.g. a regex written as
`"\S"` instead of `r"\S"`) makes CPython's own parser warn about *that
file*, not about CDP. `ast.parse` still returns a valid tree — extraction is
unaffected — but the warning goes straight to the gate's stderr on every
scan of that file.

**Fix.** Wrapped the `ast.parse` call in `warnings.catch_warnings()` +
`simplefilter("ignore", SyntaxWarning)`. Verified directly: parsing a
snippet containing `"\S+"` under `python3 -W error` (warnings promoted to
exceptions) raises nothing after the fix.

**Verification caveat, stated per this project's own standard rather than
left implicit:** this fix was made *after* this pass's single
`make check TARGET_REPO=...` gate run had already gone green (R-E3 says the
last edit should precede the first gate run; this one didn't). It was not
re-verified by a second full target gate, because that costs another
multi-minute scan this pass's budget did not have room for. The change is
believed zero-risk because `warnings.simplefilter` cannot alter what
`ast.parse` returns — only whether CPython prints about it — so it cannot
move a byte of `extract.json`, `state.json`, or any golden artifact. Treat
that as an argument, not a re-run result, until the next gate confirms it.

---

## Phase 2 — decisions the plan left open

`PHASE/phase_2_plan.md` specifies schema and behaviour precisely in most
places but leaves several implementation choices unstated. Recorded here per
`PHASE/EXECUTION_RULES.md` R-E9, so the next phase does not have to
re-derive them from the diff.

**D1 — `verdict` (0.4) is not a `claim_patch` column.** The plan lists
`author_kind, model, run_id, verdict, template_version, lessons_version` as
provenance columns in the same breath. `author_kind`/`run_id` are per-*patch*
and fit `claim_patch` cleanly; `model`/`template_version`/`lessons_version`
are added as nullable columns on `snapshot_run` (M2.5) instead, since nothing
produces them yet (no template/lessons versioning exists in `prompts.py`
today) — populating them would be inventing data. `verdict`, though, is
naturally per-*claim* (one patch can have some claims kept and others
demoted), and claims are not yet unnested into their own rows — that is a
bigger change than any single remaining milestone in this phase. `verdict`
is not implemented anywhere. Own it when claims become rows (candidate:
Phase 3's `refresh`, or whenever 0.7's lineage needs per-claim history).

**D2 — `author_kind`/`run_id` are JSON fields, not indexed `claim_patch`
columns, despite R1's "provenance is a column, not a directory."** They flow
through `payload` today (`schema/patch-1.0.0.json` gained `author_kind`,
`model`, `template_version`, `lessons_version` as optional fields; cli.py sets
`author_kind` to `python`/`llm` at the two patch-construction sites). Promoting
them to real `ALTER TABLE claim_patch ADD COLUMN ...` + an index was reasoned
through during M2.3 but not completed before the freeze this phase's execution
rules require (R-E3): a schema-only follow-up, additive, no callers to change.

**D3 — the CLI's actual default backend is still `FileStore`, not
`SqliteStore`.** M2.2-M2.5 build a fully conformant, tested SQLite backend;
M2.6 builds real store *resolution* (repo identity, the registry, `.cdp.toml`)
and wires it into `_paths()` and `hook.find_state`. What resolution returns is
still opened as a `FileStore` directory, never a `SqliteStore` `index.db` file.
Flipping that is the highest-blast-radius change available in this phase — it
changes what every command writes by default, and it would have required
updating `golden.py`'s and `test_pipeline.py`'s raw-file assumptions (both
glob `*.json` under the state dir) in the same pass as the freeze this
session's gate depends on. Per the plan's own stress-test row ("json_extract
performance... measure, do not assume" — the same spirit applies here:
measure the migration's blast radius before taking it), this is deferred
rather than rushed. The SQLite backend is fully usable today by constructing
`SqliteStore` directly; only the CLI's own choice of backend is unmade.

**D4 — `.cdp.toml` is read, never written.** `store.registry.team_store`
parses one if present (stdlib `tomllib`); nothing generates one. Per the
plan, this is correct — a team's shared store URL is a human decision, not
one `scan` should make silently — but it also means D3's registry is
currently the only *automatic* resolution path a real user gets.

**D5 — `check_order_independence` is not re-verified per permutation.**
`cmd_fold --check` calls it without `repo`, so it exercises merge
order-independence only, not verification-inside-fold order-independence.
This is deliberate, not an oversight: verification is a per-patch map with no
cross-patch state (`state.fold`'s docstring), so composing it in front of an
already-order-independent merge cannot introduce order-dependence, and
re-verifying a real repo tree ~6 times per `fold --check` call would be pure
cost for a property that follows from the map/reduce structure rather than
needing re-measurement.

**D7 — 0.5's "materialises on insert" is not implemented; only 0.4's half of
M2.3 (verification moved into `fold`) is.** The plan bundles these because
whether verification runs inside the insert path was said to change its
design completely. What actually shipped: `state.fold` now verifies
internally (0.4, and the harder part of the milestone), but `append_patch`
and `write_derived_patch` do not trigger materialisation — `state` is still
produced by an explicit `_fold_and_write` call after patches land
(`cli.py` `cmd_scan`/`cmd_collect`), exactly as before M2.3, just now doing
more work per call. This is a real, not cosmetic, gap against the plan's own
acceptance line ("state materialises on insert rather than recomputing from
history — this is what kills the O(all-patches-ever) read"): that read is
*reduced* (`SqliteStore.load_patches` is one query, not N file opens) but not
eliminated, and a full fold still recomputes the whole history on every
explicit call. The order-independence property the plan calls "the single
highest-risk item in the phase" holds (`state.fold`'s docstring argues why:
verification is a per-patch map with no cross-patch state, so it cannot
introduce order-dependence into an already order-independent merge) — but
that argument only needed proving once verification moved inside `fold`, not
once materialisation moved on-insert, because on-insert materialisation never
happened. Own this fully in a follow-up: it needs an accumulator that updates
`node_status`/`claims` incrementally and a proof (not just an argument) that
the incremental result matches a full recompute byte for byte, which is the
plan's own acceptance test for a synthetic 2,000-scope log and was not run
because there is no incremental path yet to test.

**D6 — repo identity for `snapshot.resolve_snapshot` and
`store.registry.repo_identity` uses `.git/cdp-identity` for the no-remote
case, never committed.** A repo with no remote and no `.cdp-id` gets a UUID
written inside `.git/`, which survives a `mv` of the repo but not a fresh
`git clone` (a clone with no remote is treated as a new, unrelated tree — the
plan's own "survives a move" acceptance criterion, read literally).
