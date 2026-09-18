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

## F2 (revisited) — C# and Scala extractors, resolved

**Constraint corrected before implementing:** `tree-sitter` was the first
idea (Graphify's own mechanism, per `RESEARCH_GRAPHIFY.md`), retracted after
`pyproject.toml` was actually read -- zero dependencies is stated there as
deliberate and "load-bearing" for `cdp install`'s copy-a-directory
distribution. Both extractors are hand-rolled regex/brace-depth, the same
style as `java.py`/`go.py`/`web.py`, zero new dependencies.

**Ground-truthed, not guessed:** both extractors' regexes were designed
against real `.cs`/`.scala` files sampled from `$TARGET_REPO` (file-scoped
`namespace X.Y.Z;`, ASP.NET Core `[Route]`/`[HttpGet]` attributes, EF Core
`DbContext`/`DbSet<T>`, C# `using` directives vs. the unrelated C# 8 `using`
*declaration*; Scala flat `package`, brace-optional `case class`) before any
regex was written.

**Real bug caught by a smoke test before shipping, not assumed correct:**
the brace-depth nesting logic (based on `java.py`'s, tuned for Java's
K&R-leaning style: `public class Foo {`) silently orphaned every member of a
type when the opening brace was on its *own* line -- confirmed to be the
dominant real style in `$TARGET_REPO` (`Controllers/RoleNames.cs`:
`public static class RoleNames` then `{` on the next line). Under the
same-line assumption, the class was popped off the nesting stack before its
own body ever opened, and a route attribute's owner then silently resolved
to the *next* unrelated class instead. Fixed by holding a declaration
`pending` until its own opening brace is actually observed, rather than
pushing it immediately -- verified with a same-line/next-line/no-body-at-all
(`case class Foo(...)`, `public record Foo(...);`) test matrix in
`tests/test_csharp.py`/`tests/test_scala.py`, not just the one case that
happened to fail first.

**Explicitly out of scope, stated rather than silently dropped:** C# DI via
fluent `services.AddScoped<I,T>()` calls, AutoMapper profiles, MediatR
handlers (none are attribute-shaped, so none fit this extractor's detection
style); any Scala web-framework signal (nothing in the sampled 73 files
evidences one -- adding a signal with no real corpus support would be
exactly the "close a number gap, not a real demand" mistake
`RESEARCH_GRAPHIFY.md` §9 warns against).

**Verified on real, previously-unseen files, not only the synthetic test
snippets:** a scratch scan of `$TARGET_REPO/service-api` (a real C# module)
went from 0 to 3,000 symbols / 152 routes / 520 claims; spot-checking one
emitted route (`AdminDataController#ArchiveSecurableAsync`,
`[HttpPost("securables/{securableId}/archive")]`) against the real file
confirmed an exact line match. A scratch scan of
`$TARGET_REPO/exposure-snapshot/snapshot-sdk` (mixed Java/Scala) correctly
attributed Scala-only rows to the new extractor, including a real,
previously-unseen bodyless multi-line `case class CatalogDetails(...)` at
`DataCatalogServiceIT.scala:194` -- the same shape the pending-brace fix
above was built to handle, hit for real, not only in the test I wrote.

**Full target re-blessed, not fixture:** unlike F9/F10/F14 this session,
this is a deliberate recall increase, so the golden diff on `$TARGET_REPO`
was *expected*, inspected for plausibility, then blessed
(`cdp selftest --golden $TARGET_REPO --bless`) -- not treated as a red flag.
375 tests green; `make check TARGET_REPO=...` green afterward (determinism,
fold, golden -- fixture and target). New target totals: C# 7,718 defines /
15,926 imports / 1,007 io_edges (from 0); Scala 142 defines / 616 imports /
8 io_edges (from 0); repository-wide symbols 12,949 → 20,255, routes 43 →
565. Fixture golden untouched (`minirepo` has no `.cs`/`.scala` content).

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

## F9 (revisited) — implemented, with explicit sign-off, and verified rather
than re-blessed

**Sign-off:** given explicitly in session, with the fallback that this
repository's last commit before this change is a known-good state to revert
to if it goes wrong.

**Re-reading `run_extract` narrowed the risk this entry itself raised.**
Every list it returns already passes through `_sorted()` (`extract.py`, key
ending `(anchor.file, anchor.line)`) — a near-total order regardless of
input order. A tie in that key can only occur between two rows the *same
file's own* extraction produced (`file` is part of every sort key), and one
file's row order comes entirely from a single `extract_file()` call running
start to finish inside one worker — parallelism changes which files
interleave before the sort, never a file's own internal order.
`declared_deps`/`module_notes` were already `sorted(set(...))`-deduped.
Separately, `state.check_order_independence` turned out to test the
patch-*merge* stage's order-independence across nodes/waves — a different
gate entirely, not this one.

**What shipped.** `cdp/extract.py`: `run_extract` gained `workers:
Optional[int] = None`. Below `PARALLEL_MIN_FILES` (64) parseable files, or
with an explicit `workers<=1`, it runs the exact prior sequential loop
(refactored into a shared `_absorb()` helper, but behaviourally identical).
Above the threshold, `workers=None` auto-selects `min(cpu_count,
file_count)` and dispatches through `ProcessPoolExecutor.map()` — the code
comments explain concretely why `.map()`'s result order matches dispatch
order regardless of which worker finishes first (it yields `futures[i]`'s
result before `futures[i+1]`'s, blocking on `i` if needed), which is what
makes the assembly loop absorb results in the same order the sequential
branch would have, before the sort key removes any remaining ordering
question anyway. `cli.py`'s `cdp scan` gained `--workers` (default: auto; `1`
forces sequential).

**Verified, not assumed:**
- New differential test, `tests/test_extract_parallel.py`: `workers=1` vs an
  explicit `workers=4` override on `tests/fixtures/minirepo` hash identical
  (forces the parallel branch despite the fixture being far under the
  threshold); the auto-selected default matches explicit `workers=1` below
  the threshold (pins the auto behaviour so it can't silently start
  spawning processes for tiny repos); and, opt-in
  (`TARGET_REPO=... python3 -m unittest`, same convention as
  `test_determinism.py`), `workers=1` vs `workers=None` (real parallel, the
  target's 4,728 files clear the threshold) hash identical on
  `$TARGET_REPO`.
- **Measured on the real target:** `run_extract` alone, sequential 3.93-4.07s
  vs parallel(auto) 0.74-0.77s across two runs — **~5.2-5.3x**, in the range
  F9's own estimate named.
- **Full suite:** 362 tests green (up from 359 — the 3 new tests, one
  skipped without `TARGET_REPO`).
- **Full gate, both targets, no re-blessing:**
  `make check TARGET_REPO=/Users/sharmp49/git/code_scanner` — determinism
  (fixture and target, two independent scans of the target agree
  byte-for-byte), `fold --check` (fixture and target), and golden (fixture
  and target) all green against the *existing* blessed baselines. This is
  the actual proof, not the docstring's argument: if the ordering claim had
  been wrong, this would have failed rather than being re-blessed around.

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

## F12 — `refresh` writes into a snapshot no other command ever reads back

**Severity:** high — every one of `refresh`'s writes became invisible to a
fresh `query`/`status`/`docs`/`fold`/`collect`/`rollback` process the moment a
second snapshot existed. **Status: fixed, in the same session that found it
(Phase 3, M3.8).**

**Found by:** M3.8's own real-input exercise (`PHASE/EXECUTION_RULES.md`
R-E7) — a git hook running `cdp refresh`, then a *separate* `cdp status`
process reading the result, which is the exact composition the hooks exist
to automate and which no prior phase's exercises had performed (each trusted
`refresh`'s own printed summary rather than re-querying afterward).

**Root cause, in two parts, both introduced by the "D3 resolved" session
(`PHASE/FINDINGS.md`, the entry above `F12`) that made `SqliteStore` the
CLI's default — neither was exercised there because every check in that
session ran a single command against a store holding exactly one snapshot:**

1. `SqliteStore._snapshot_id()` lazily defaults to a hardcoded `id=1` unless
   something already called `begin_snapshot`. `scan`/`refresh`/`rollback`/`gc`
   all call it explicitly; `query`, `status`, `docs`, `fold`, `collect` never
   did, so once a `refresh` created a *second* snapshot row, those six
   commands kept reading snapshot 1 forever, in any later process.
2. `claim_patch` rows are correctly, deliberately scoped per-snapshot
   (`tests/test_store_sqlite.py`
   `test_two_commits_produce_two_snapshots_and_both_stay_queryable` --
   pre-existing, untouched, still green). `refresh` selects a brand-new
   snapshot for the new commit via `begin_snapshot`, which starts with an
   *empty* patch log -- so even once (1) is fixed, `state.fold` over that
   empty log produces zero claims, contradicting D10's account that refresh
   "re-verifies the *existing* patch log".

**Fix:**

- `SqliteStore.use_latest_snapshot()` (new) points the backend at the most
  recently *touched* snapshot. `query.Store.__init__` calls it whenever the
  backend supports it -- one choke point that covers `query`/`status`/`docs`/
  `fold`/`collect`/`rollback`/`diff`, all of which construct a `Store`.
  "Touched" is a new monotonic `snapshot_meta.touch_seq` column (`SCHEMA_V4`),
  bumped by every `begin_snapshot` call including a *reuse* -- not a
  timestamp: two `begin_snapshot` calls inside the same wall-clock second
  (routine for a `post-commit` immediately followed by a `post-checkout`)
  would tie under `_now()`'s second precision, and `id DESC` alone picks
  creation order, which is wrong the moment a checkout moves *back* to an
  earlier, already-scanned commit (reusing its lower-numbered row).
- `SqliteStore.copy_patches_from(source_snapshot_id)` (new): `cmd_refresh`
  captures the prior snapshot's id (via the new `snapshot_id()` public
  accessor) before calling `begin_snapshot` for the new commit, and if the
  new snapshot's log is empty, copies every patch row over verbatim
  (`seq`/`label`/`content_hash`/`payload`/`is_derived` preserved) -- keeping
  M2.4's per-snapshot isolation test intact while giving `refresh` a full
  log to re-verify, exactly D10's stated contract.
- Incidental second bug in the same function, same root cause: `cmd_refresh`'s
  `before_demoted` count read `store.state` *after* `begin_snapshot` had
  already moved the backend's selection to the new (not-yet-written)
  snapshot, always reading 0. Reordered to read before the switch.

**Verified:** the full fixture suite (296 tests, `unittest discover`) and the
new `tests/test_githooks.py` `RealHookFiringTest` -- real `git commit`/
`git checkout` subprocesses, not a direct `cdp refresh` call -- pass,
including the exact repro that found this (`cdp status` in a fresh process
correctly reporting a commit a hook-triggered `refresh` had already moved to,
and correctly reporting a checkout *back* to an earlier commit whose
snapshot already existed). `make check TARGET_REPO=...` is the target-scale
confirmation (see `PHASE/TARGET.md`).

**Not touched:** `cmd_gc` (already resolves its own snapshot explicitly, does
not use `query.Store`) and `cmd_scan` (calls `begin_snapshot` before any read,
so nothing to resolve).

---

## Phase 3 (M3.8) — git hooks, and the shared-hooks-directory caveat

Scoped to M3.8 only this session -- the last milestone in `phase_3_plan.md`;
M3.1-M3.7 were already complete (prior sessions, see the entries above).

**Design (`cdp/githooks.py`, new module; `cdp githook install|uninstall` in
`cli.py`).** `post-commit` always runs `cdp refresh --repo <repo> --quiet`;
`post-checkout` runs it only when git's own `$3` flag is `1` (a branch/ref
move) -- `git checkout -- <path>` (`$3=0`) is a file-level restore, not a
`HEAD` move, and must not fire (the plan's acceptance line, verified with real
`git checkout`/`git checkout -b`/`git checkout -- <path>` sequences in
`tests/test_githooks.py`, not a simulated flag). Both the interpreter
(`sys.executable`) and the repo path are embedded as absolute paths at
install time, per the plan (GUI git clients and CI often run hooks with an
unrelated `PATH`/cwd). Every installed script carries a `MARKER` comment;
`install` refuses to overwrite a hook lacking it (never clobbers a foreign
hook -- the operator is told to chain manually), and `uninstall` only removes
a file that has it, leaving a foreign hook untouched. The hook fails open
(always exits 0, on both a git-blocking and non-blocking hook name) --
neither `post-commit` nor `post-checkout` gates the operation it fires after,
so a nonzero exit buys nothing; `refresh`'s own `cdp: <message>` on stderr
(never scanned yet, dirty tree) is left unsuppressed rather than silenced,
unlike the PreToolUse hook (`hook.py`), because this one fires once per
commit/checkout, not once per file read.

**D19 -- a git hooks directory is shared across every worktree of a
repository; `cdp githook install` run inside one worktree installs into all
of them.** This is real git behaviour (`git rev-parse --git-path hooks`
resolves to the common `.git/hooks/`, not a per-worktree directory, unless
`core.hooksPath` is set), not a bug in `hooks_dir()` -- but it means a
`cdp githook install --repo <worktree>` is not scoped to that worktree the
way `--state-dir`/`--in-repo` are for state. **Confirmed live, and by
necessity carefully:** installing against a detached worktree of
`$TARGET_REPO` (`sql-pool/sql-pool-api`, pinned commit) placed the hooks in
`/Users/sharmp49/git/unified-store/.git/hooks/` -- the real target's actual
shared hooks directory, since this session's own working copy
(`/Users/sharmp49/git/code_scanner`) is itself a linked worktree of that same
repository (`git -C .../code_scanner rev-parse --git-path hooks` resolves to
the identical path). `cdp githook uninstall` against the same worktree path
was run immediately after and confirmed, by listing the directory afterward,
to have removed exactly those two files and nothing else -- `git status
--porcelain` on the real repo was empty before and after. Not documented
anywhere the user would see it before this session; worth a line in the
`githook install` output itself in a follow-up (not done here -- out of this
session's scope).

**Real-scale exercise (R-E7), scoped for safety by D19.** Given the shared-
directory finding above, the "hook actually fires and moves state" acceptance
criterion (commit triggers refresh; branch switch triggers refresh; file
checkout does not) is proven with real `git commit`/`git checkout`
subprocesses against the **fixture**, not `$TARGET_REPO` -- installing into a
worktree of the live target for a firing test would touch the same shared
hooks directory just confirmed above, for a real, currently-used repository.
What *was* exercised directly against `$TARGET_REPO`: `hooks_dir()`'s
worktree-aware resolution (`git rev-parse --git-path hooks`, correctly
following the shared common dir rather than assuming
`<repo>/.git/hooks`) and a full install/uninstall roundtrip leaving zero
trace, both described above.

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

---

## F11 — path-scoped `git log` reports a pure rename as churn

**Severity:** high for M3.1's staleness signal specifically — it would have
reported every `git mv` as a stale claim. **Status: fixed, in the same
milestone that introduced it (Phase 3, M3.1/`cdp/freshness.py`).**

Found by the fixture smoke test this milestone's own execution rules require
(`PHASE/EXECUTION_RULES.md` R-E7): `git log <since>..<head> --numstat -- path`,
run against a file's path *after* a pure `git mv`, shows one commit adding N
lines at that path — git's single-path history simplification does not apply
rename detection to its own path filter, so the rename commit looks identical
to a genuine N-line addition. `git log --follow -M100% ... -- path` fixes it:
the same commit's numstat line reads `0  0  {old => new}`, and it is the
*numstat numbers*, not "a commit exists", that `freshness.file_churned_between`
now checks — matching the plan's own wording ("computed from `git log
--numstat`") more literally than the first pass did.

---

## Phase 3 (M3.1-M3.3) — decisions the plan left open

**D8 — both freshness dates are commit shas, not timestamps**, despite the
plan's own wording ("two dates"). `cli.py`'s `_run_id` already established why:
*"a timestamp in the run id would leak into every patch and defeat the
reproducibility gate."* `claim_reviewed_at`/`anchor_verified_at` live inside
`claims[]`, which is neither `manifest.json` (the one file allowed a real
timestamp) nor covered by `VOLATILE_FIELDS`. A wall-clock value there would
make two scans of the same commit diverge in `state.json` and `fold_hash`.
Since this system's own notion of "when" is already `(repo_id, commit_sha)`
(`snapshot.py`), both fields hold a commit sha instead: free to compare, and
deterministic per commit by construction. See `cdp/freshness.py`'s docstring
for the full argument.

**D9 — incremental extract (M3.2) re-derives at module granularity, not file
granularity.** `declared_deps`/`module_notes` are aggregated per module in the
stored `extract.json` with no per-file attribution kept, so carrying a module
forward while re-deriving only one of its changed files would silently drop
whichever file's manifest-derived entries weren't re-run. Re-deriving every
file in a module that has at least one changed file makes
`incremental_extract`'s output provably equal to a full `run_extract` (the
milestone's acceptance test, `tests/test_refresh.py`
`IncrementalExtractEquivalenceTest`) at the cost of being incremental at
module rather than file granularity — still a large reduction for any commit
that does not touch most modules.

**D10 — `refresh` never appends a new derived-claims patch.** M3.4 (scope-hash
caching) is explicitly out of this session's scope (see below), and
`PHASE/FINDINGS.md`'s own account of the state (`state.py:44` docstring; the
plan's M3.4 section) is that re-running a node today *accumulates* rather than
replaces — two `complete` patches for the same node, neither superseding the
other. Appending a fresh structural-claims patch on every `refresh` would hit
that defect immediately. Instead `refresh` re-verifies the *existing* patch
log against the new commit (rename-aware, via `rename_map`/`edited_files`
threaded into `state.fold` -- `verify.py`) and rebuilds only the
non-claim-bearing views (`graph`/`xref`/`dataflow`/`partition`) fresh. This
matches the milestone table in `phase_3_plan.md` exactly (relocate / demote /
invalidate over the log that exists), and defers "what does a *new* structural
fact look like after a refresh" to M3.4, where supersession is actually solved.

**D11 — `check_fold`/`fold --check` does not thread `rename_map`/`edited_files`
through.** After a `refresh` that involved a rename, `fold --check` recomputes
without the rename map and would find `state.json`'s relocated anchors
"undeliverable from patches/ + xref.json" -- a false positive. Not fixed this
session: no scan-then-refresh sequence is on `make check`'s path (it runs one
scan of `$TARGET_REPO` at its pinned commit), so the gap is real but not
exercised by the gate. Owner: whichever phase makes `refresh` part of the
regular gate loop.

**D12 — `cmd_status`'s staleness bucket compares against the *last scanned*
head (`store.inventory["head"]`), not the repo's live git HEAD.** Deliberate:
`status` reports what CDP's own state currently reflects, and if a commit has
landed since the last `scan`/`refresh`, CDP does not yet know its content
exists (`graph`/`xref` are still built from the old tree) — `refresh` is the
operation that catches state up, not `status` inspecting the working tree on
the side.

**Real-scale exercise, not just the fixture (R-E7):** `cdp refresh` was run
against one worktree of `$TARGET_REPO`'s `sql-pool/sql-pool-api` module,
scanned at the pinned commit and refreshed to the live tip roughly eight months
later (544 files changed: 18 renamed, 527 edited, 17 added, 444 deleted) --
zero crashes, zero demotions, ~12s, zero model calls. Confirmed the pinned
commit is **not an ancestor** of the current tip (history was rewritten
somewhere in between); `git diff --name-status -M` between two arbitrary,
still-present commit shas works regardless of ancestry, so this did not
exercise the `HistoryUnavailable` fallback path -- that path is only proven at
fixture scale (`tests/test_determinism.py`-style: a synthetic sha that does not
exist). See `PHASE/TARGET.md` for the full readout.

**Out of scope this session, by explicit user choice:** M3.4 (scope-hash
caching / supersession), M3.5 (`cdp diff`), M3.6 (`gc`/retention), M3.7
(`rollback`/`--as-of`), M3.8 (git hooks). `phase_3_plan.md`'s stress-test row
for a shallow clone is covered by `freshness.file_churned_between` returning
`None` (never asserts "not stale" from missing data) but was exercised only by
reasoning about `run_git`'s failure mode, not a constructed shallow clone.

---

## Phase 3 (M3.4) — scope-hash caching and the supersession fix

Scoped to M3.4 only this session, by explicit user choice (M3.5–M3.8 remain
deferred; M3.8 in particular needs its own session — installing/firing real
git hooks is more invasive than the others).

**The confirmed defect** (`ARCHITECTURE.md`'s sharp-edges table, `state.py`):
`state.fold` accumulated claims from *every* `complete` patch for a node, so
re-running a node (e.g. a retried agent, or a future `refresh`-triggered
re-dispatch) produced two generations of claims side by side rather than the
second superseding the first. Confirmed live before fixing it: `state.py`'s
claim loop appended from each complete patch unconditionally; nothing kept
only the latest.

**Fix, in two parts:**

1. **`generation`** — a new optional integer field on `patch` (schema
   additive, `schema/patch-1.0.0.json`), stamped once at append time
   (`cli.py` `_next_generation`, called from both `cmd_scan`'s root patch and
   `cmd_collect`'s per-node accepted patches) as `1 + max(prior generations
   for that node already in the log)`. Because it is data on the patch and
   not a position in the list, `state.fold` can pick the highest-generation
   `complete` patch per node and remain order-independent by construction —
   the same argument that already justifies `node_status`'s STATUS_RANK
   precedence just above it in the same function. A tie (two complete
   patches, equal or absent generation) breaks on `stable_hash`, not
   insertion order, for the same reason. **Acceptance met**: re-running one
   node twice now yields exactly one generation's claims, verified both
   directly and under `check_order_independence`-style shuffles
   (`tests/test_scope_hash.py` `SupersessionTest`).

2. **`scope_hash`** (`cdp/refresh.py`) — a content fingerprint of a scope's
   file set (sorted `(path, lines)` pairs, `stable_hash`'d), stamped onto
   every scope in `partition.json` at both `scan` (`cmd_scan`) and `refresh`
   (`cmd_refresh`) via `annotate_scope_hashes`. `changed_scopes(old_partition,
   new_partition)` diffs two partitions' hashes by node and names exactly the
   scopes whose content moved; a node absent from the old partition counts as
   changed (nothing to reuse). `cdp refresh` now prints a `scopes N/M changed
   (dispatch needed for N, M-N reuse the prior claim)` line.

**Real-scale exercise (R-E7), not just the fixture:** scanned
`$TARGET_REPO`'s `sql-pool/sql-pool-api` (2 scopes) into a scratch state dir
via a detached worktree at the pinned commit, edited exactly one `.java` file
in the 38-file scope, committed, and ran `cdp refresh`:

    scopes    1/2 changed (dispatch needed for 1, 1 reuse the prior claim)

The untouched 11-file scope's hash did not move; the edited scope's did. This
is the concrete form of the milestone's own acceptance line ("a commit
touching 2 of 17 scopes dispatches 2 scopes, not 17") against real content,
not a synthetic count. Worktree removed after the exercise; main checkout's
`git status --porcelain` was empty before and after.

**What M3.4 does *not* wire up, and why.** The plan's other half — "skip the
agent" — is a dispatch-time decision that belongs to `cdp run`, which does not
exist in this codebase yet (Phase 4/5 territory: no orchestration loop spawns
per-scope agents here today). `scope_hash`/`changed_scopes` are the primitive
a future `run --stale-only` needs to make that decision; this session builds
and proves the primitive and wires it into the one place that already
computes both old and new partitions (`refresh`), rather than inventing a
dispatch loop to consume it.

**Golden baseline re-blessed, same as Phase 2's M2.3.** The first
`make check` run (after freeze, per R-E3) found 15 differing artifacts on
both the fixture and `$TARGET_REPO`, all `fold_hash`-only or the new
`scope_hash`/`generation` fields directly (`partition.json` gains
`scope_hash` per scope; `patches/0000-derived.json` gains `generation: 1`) --
an intended content change, not a regression. Re-blessed with
`python3 scripts/fixture_gate.py bless` and
`cdp selftest --golden $TARGET_REPO --bless`; `git diff` on the baseline
confirms the diff is confined to exactly those additions plus their
downstream `fold_hash`/`state.json` consequences. Second `make check` run,
after the re-bless, is the one reported green below.

**Cost, stated rather than assumed away.** `annotate_scope_hashes` re-reads
every scoped file's content once per `scan`/`refresh`, on top of the read
`extract_file` already does — roughly doubling file I/O (not re-normalisation;
`stable_hash` runs once per scope, not per anchor, so this is not F6's
quadratic shape). Not measured against the full `$TARGET_REPO` this session
(`make check` is the only full-target run this budget allows, launched after
freeze); flagged as headroom to revisit if a future full-target timing shows
it matters, the same posture F9 already takes toward `run_extract`'s single
threading.

---

## Phase 3 (M3.5-M3.6) — `cdp diff` and `cdp gc`, and the multi-snapshot gap they surface

Scoped to M3.5 (`cdp diff`) and M3.6 (retention/`gc`) only this session, by
explicit user choice (M3.7 rollback/`--as-of` and M3.8 git hooks remain
deferred — M3.8 in particular still needs its own session per the prior
entry).

**D13 — a real, pre-existing architectural gap, not a new defect: `FileStore`
cannot hold two snapshots, and the CLI never uses `SqliteStore`.** Both
milestones as the plan states them ("typed structural deltas between two
snapshots"; "a store with 5 snapshots") assume a store that keeps multiple
snapshots' artifacts around simultaneously. `store/__init__.py`'s own
docstring already says this plainly: `FileStore` no-ops `begin_snapshot`
because it is one directory, always overwritten (confirmed: `cmd_refresh`,
`cmd_scan` and every other command construct `FileStore(paths.state)`
directly — `grep -n "FileStore("` finds zero uses of `SqliteStore` anywhere in
`cli.py`, matching D3's account exactly). Only `SqliteStore`'s `snapshot_meta`
table actually holds N coexisting snapshots. Two consequences, both taken
rather than deferred:

- **`cdp diff`** takes two independently-scanned `FileStore` state
  *directories* as its two "snapshots" (positional `old_state`/`new_state`),
  not two commits of one store — the same shape the M3.1-M3.4 real-target
  exercises already used (two scratch dirs, or one worktree scanned twice).
  This sidesteps the gap rather than closing it: `cdp diff` never reads
  `SqliteStore` snapshot lineage, so it works today, on the backend the CLI
  actually uses.
- **`cdp gc`** cannot sidestep it the same way — retention is inherently a
  question about *one store holding several snapshots* — so it is wired
  directly to `SqliteStore` via a new `--db <path>` flag that bypasses
  `_paths()`/the registry entirely (per D3: "the SQLite backend is fully
  usable today by constructing `SqliteStore` directly; only the CLI's own
  choice of backend is unmade"). No `scan`/`refresh` path writes into a
  `SqliteStore` today, so `cdp gc` has no real corpus to operate on until that
  changes — proven this session by populating one directly (below), not by a
  scan.

**D14 — "pinned" is not an existing concept anywhere in this codebase; it had
to be added as a column before the retention rule could be expressed at all.**
`grep -rn "pinned"` before this session found the word only in prose (this
plan, `TARGET.md`, golden-baseline naming) — no schema column, no CLI verb.
Added `snapshot_meta.pinned` (`SCHEMA_V3`, additive migration,
`sqlite_backend.py`) plus `SqliteStore.set_pinned`/`list_snapshots`, and
`cdp gc --pin SHA`/`--unpin SHA` to set it before computing retention in the
same invocation. Nothing marks a snapshot pinned automatically — there is no
feature yet with an opinion about which commits are worth preserving forever
— so this is representable, not yet automatic, the same posture D4 already
takes toward `.cdp.toml`.

**D15 — the plan's retention rule names a `last_verified` field that does not
exist; `snapshots_to_keep` uses the two fields that actually do.** M3.1
(`freshness.py`) established `anchor_verified_at`/`claim_reviewed_at` as this
system's two real dates (D8) — there is no third `last_verified` field
anywhere in a claim. `cmd_gc` treats "cited" as the union of both: either one
naming an old commit is a real reason that snapshot cannot be dropped.
`snapshot.snapshots_to_keep(snapshots, repo_id, head_sha, cited_shas)` is the
one-sentence rule from the plan, reproduced literally
(`tests/test_snapshot.py` `TestSnapshotsToKeep`, including the plan's own "5
snapshots, claims citing 2, keeps HEAD + those 2" acceptance line verbatim).

**Real-scale exercise (R-E7), not just the fixture.** Same worktree pattern as
the M3.1-M3.4 exercises: `sql-pool/sql-pool-api` scanned at the pinned commit
and at the current tip (`bab4ea0dce85`, ~8 months later) into two separate
scratch `FileStore` dirs.

    cdp diff <old-scan-dir> <new-scan-dir>
    diff      0 module(s) added, 0 removed
              0 declared edge(s) +/-0/0, 0 observed edge(s) +/-0/0
              0 route(s) added, 0 removed
              0 claim(s) added, 0 removed, 0 anchor(s) moved

Zero deltas — consistent with, and a cross-check on, the M3.1-M3.3 finding
that this module's 41 structural claims all verified live across the same
commit range: a real diff of zero is the expected answer when nothing
structural moved, not a vacuous run. The eight positive cases (module/edge/
route/claim added-removed, anchor moved, undeclared-dependency-appeared,
coverage regression) are exercised on synthetic dicts shaped like the real
`graph`/`xref`/`state` schemas (`tests/test_diffs.py`) — real content never
produced any of those eight shapes in this pair, so they could not be
exercised on `$TARGET_REPO` within this session's budget without engineering a
commit pair that changes structure, which was not attempted.

For `cdp gc`, since no scan path populates a `SqliteStore`, one was built
directly, keyed by this target's real `repo_id`
(`github.com/moodys-ma-platform/unified-store`) and the two real commit shas
above: an old snapshot cited by a (synthetic) live claim's `claim_reviewed_at`,
an orphan snapshot cited by nothing, and a head snapshot. `cdp gc --db ...
--repo /tmp/diff_wt/sql-pool/sql-pool-api` (real CLI invocation, real
`repo_identity`/git-HEAD resolution) correctly dropped only the orphan and
kept the cited old snapshot and HEAD — verified by reading `list_snapshots()`
back, not by trusting the printed summary line. `--dry-run` reported the same
plan without deleting anything, checked first.

**Out of scope this session, unchanged from the prior entry:** M3.7
(`rollback`/`--as-of`) and M3.8 (git hooks).

---

## Phase 4 (M4.1) — entailment validation, and the `source_nodes` bug it found

Scoped to M4.1 only this session, by explicit user choice: the plan's four
milestones (entailment, unknown gates, `needs_*`/R12 ratchet, `cdp answer`)
were judged comparable in size to all of Phase 3, which ran as five separate
sessions. M4.2-M4.4 remain unimplemented.

**What shipped.** `cdp/entail.py` (new): `entail_claims(claims, extraction)`
assigns each claim a `verdict` -- `entailed` when an `io_edge` already states
the same `(subject, channel)` fact, `contradicted` when a `definition` for
the subject exists and disagrees on a discrete field (`visibility` is the
only one checked; no other claim field has a comparable structural
counterpart today), `consistent` otherwise. Matching is over structure only
(subject/channel/visibility), never the claim's own wording --
`test_no_statement_text_matching` pins this. `state.fold` gains an optional
`extraction` parameter (this commit's `io_edges`/`defines`, from
`store.extraction`/`store.read_artifact("extract")`) threaded through all 5
call sites in `cli.py` plus `check_fold`; `fold_hash` gains the same
parameter, appended last so every pre-existing 3-argument call (tests
included) hashes exactly what it always did. Folded state gains
`entailment` (counts, `rate_contradicted`, per-node `entailed_ratio` --
`CDP_CLI_SCOPE.md`'s tiering question) and `contradictions` (the full
contradicted claims, not just a count -- "the contradicted bucket is gold").
Contradicted claims are **not** removed from `claims[]`: the plan's own
stress-test row says measure the rate before rejecting, and this session
only measures it (see below). `schema/patch-1.0.0.json`'s claim gains an
optional `verdict` enum, documented as fold-assigned, never present on a
patch as authored.

**Deliberately narrow, and why.** The plan's stress-test table asks for
entailment "over structure, not strings" and warns against inventing a
scoring rule with no calibration. `visibility` is the only claim field
checked for contradiction because it is the only one with both (a) a
same-shape counterpart in `definitions[]` and (b) a closed enum, so a
mismatch is unambiguous. `channel`-only matching for `entailed` is
similarly conservative: it says "this fact is already structural," not
"this claim is fully correct." Extending contradiction detection to
`side_effect_type`, `kind`, or route/config claims is real, undone work for
whoever picks up M4.1's remainder or M4.2.

**Bug found and fixed in the same session, by exercising on real target
output (`PHASE/EXECUTION_RULES.md` R-E7), not the fixture.** The first
scratch scan of `$TARGET_REPO/sql-pool/sql-pool-api` showed every claim's
per-node entailment bucketed under the single key `"?"` -- `merge.py:225-226`
renames a claim's `source_node` (singular) to `source_nodes` (plural, a
list, set post-merge because one claim can be attributed to several
converging leaves) and pops the singular field. `entail.summarize` read the
now-absent singular field on every claim, so the per-scope ratio the plan
explicitly asks for ("emit the per-scope ratio now so Phase 6's tiering has
data to reason from") was silently non-functional from the first commit of
this milestone. Fixed to read `source_nodes` when present (falling back to
the pre-merge singular field for callers that fold a single patch's own
claims directly), counting a claim toward every node it is attributed to.
Re-verified on the same scratch scan: per-node ratios now key on real node
names (`root/(files+2)`, `root/src/main/java`), not `"?"`.

**Contradiction rate on `$TARGET_REPO`, measured as the plan's exit
criterion requires.** One module first (`sql-pool/sql-pool-api`'s 41 derived
claims): 2 `entailed`, 39 `consistent`, 0 `contradicted`. Then the full
target, read from the blessed golden `state.json` after `make check`
(1,278 derived claims, zero model calls): **1,243 `consistent`, 35
`entailed`, 0 `contradicted` -- `rate_contradicted: 0.0` at full scale**,
matching M4.1's acceptance line exactly. `entailed_ratio` per scope ranges
from 0.0 (most SQL-migration and C#-only scopes, which set no `channel`) to
1.0 (a handful of small scopes whose only claims are process-entrypoint/
config-read facts already backed by an `io_edge`); `sql-pool-manager`'s
0.74 is the highest non-trivial ratio, concentrated in a scope with several
side-effect claims. This is the residue signal `CDP_CLI_SCOPE.md §N` asks
for, not yet consumed by anything (Phase 6).

**Real-scale exercise (R-E7):** one scratch scan of
`$TARGET_REPO/sql-pool/sql-pool-api` (not the fixture) into
`/tmp/m41_scratch`, plus a `cdp fold` re-run after the `source_nodes` fix,
both read back through `sqlite3` directly against `index.db`'s
`snapshot_artifact` table rather than trusting a printed summary line.
Scratch directory is disposable, outside the repo.

**Second bug, found by the gate itself, same session.** The first
`make check TARGET_REPO=...` run (after the freeze above) failed
`test_check_fold_reads_the_ledger_so_a_rolled_back_state_still_verifies`:
`check_fold` and `_fold_and_write` read `store.read_artifact("extract", {})`
to get `extraction`, intending "`{}` when this store never wrote one." But
`WorkspaceStore.read_artifact`'s own contract (`file_backend.py:29-34`)
treats a `None` *default* as "raise if missing," and treats any other
default, including `{}`, as "return it if missing" -- so passing `{}`
silently succeeded where the original code's callers had never supplied a
default at all. The result: a store with no `extract` artifact (this test's
`FileStore` fixture, and read via `check_fold`) got `extraction={}`, while
the original `fold()` call that wrote `state.json` in the same test had been
called directly with no `extraction` argument at all (`extraction=None`,
the parameter's own default) -- and `fold_hash`'s `if extraction is not
None` guard means `{}` and `None` hash *differently*, so `check_fold`
reported a permanent, spurious `fold_hash mismatch` for any store that
never had extract data, independent of rollback. Fixed to
`store.read_artifact("extract") if store.has_artifact("extract") else None`
at both call sites (`cdp/state.py` `check_fold`, `cdp/cli.py`
`_fold_and_write`), so "no extract artifact" and "extraction argument
omitted" hash identically, restoring the property `fold_hash` already
promised (same bytes for the same logical inputs) rather than a promise
`fold_hash`'s signature made but two of its own callers broke. Re-verified:
`tests/test_rollback.py` (9 tests), `test_pipeline.py` (22),
`test_entail.py` (8) all green; vendored copy re-synced via
`cdp install --self` before the gate's second run.

**Test coverage.** `tests/test_entail.py` (new, 8 tests): matching io_edge is
`entailed`; no structural counterpart is `consistent`; visibility mismatch is
`contradicted`; matching visibility is not; a claim whose wording has nothing
to do with a matching edge still entails (the "no statement text matching"
stress test, directly); missing `extraction` degrades to all-`consistent`
rather than crashing; `summarize`'s counts and per-node ratio; and one
fold-level integration test asserting a contradicted claim survives in
`claims[]` and is mirrored into `contradictions[]`.

**Out of scope this session, unimplemented:** M4.2 (the four unknown gates:
subject-exists, negative entailment applied to unknowns, provenance state
via the `tasks` table, clustering), M4.3 (`needs_*` vocabulary, the R12
ratchet, the grandfathering migration decision for existing unknowns), M4.4
(`cdp answer`, R11's human-outranks-on-interpretation-never-on-structure
rule, the `RetryPolicy.execute` decay scenario). None of the plan's
`tasks`-table precondition work (Phase 2 left `snapshot_run`/`snapshot_task`
schema-only, "created here, driven in Phase 5") was touched -- M4.2's
"provenance state" gate has no data source yet and is real, undone work for
whoever picks this phase back up.

---

## Phase 3 (M3.7) — `rollback` and `query --as-of`

Scoped to M3.7 only this session, by explicit user choice (M3.8 git hooks
remains deferred — it needs its own session, per the standing note above).

**D16 — exclusion is a ledger, not a mutation.** R5 forbids rewriting or
deleting a patch. "Excluded patches are marked `superseded_by_rollback`,
never deleted" (`phase_3_plan.md` M3.7) is implemented as a new append-only
artifact, `rollback.json` (`cdp/rollback.py`), naming excluded `run_id`s.
`state.fold` gained an `excluded_run_ids` parameter that drops those patches
before anything else runs — as if never appended, without the patch file
itself ever being touched. `check_fold` reads the ledger so a rolled-back
state still verifies (the same class of gap D11 already named for
`rename_map`: recomputing from the raw log without the same exclusion would
flag a correct rollback as drift). `_fold_and_write` and `cmd_refresh` both
read the ledger too, so the exclusion holds across every future `scan` /
`collect` / `fold` / `refresh`, not just the rollback that created it.

**D17 — the ordering axis for `--to-snapshot` is log append order, not time.**
Patches carry no timestamp by construction (D8), so "up to S" is defined as
"through `S`'s run's last patch in the log's own append order"
(`FileStore.load_patches()`'s sorted-filename order). `--to-run R` is a
different, narrower operation: it excludes only `R`'s patches, wherever they
sit, leaving later runs untouched — a targeted undo of one bad run, not a
time-travel cut. Both accept either a bare commit sha or a `cdp-<sha12>` run
id (`rollback.resolve_run_id`), since a run's identity is already the commit
it examined (`cli._run_id`).

**D18 — `query --as-of` supports a commit, not a wall-clock time, and does not
re-verify anchors or rebuild `xref`/`graph`.** This is the finding the plan
itself anticipated: *"if it is not nearly free, the fold is not as pure as
Phase 2 believes."* A time-based cut would need a timestamp invented for this
feature alone, reopening exactly what D8 rejected for the reproducibility
gate. What `--as-of <commit>` does is cheap and exact: replay `fold` over the
patch log truncated to that commit's run, against the *current* `xref`/
`partition` (no repo checkout, no re-extraction) and with `repo=None` (no
anchor re-verification — that op belongs to `refresh`, which operates at a
tree, not a log position). `query`'s `as_of` block gains `patch_log_as_of`
when a cut was applied, naming that only the claim log is historical, not the
structural view.

**Real-scale exercise (R-E7), not just the fixture.** `sql-pool/sql-pool-api`
scanned into a scratch dir at the pinned commit (41 claims). A synthetic bad
run (`cdp-badbad000001`, node `root`, reusing a real anchor from the module's
own derived patch) was appended and folded — because it shared the derived
patch's node, M3.4's generation-based supersession picked one winner and the
fold showed **1** claim, not 42, which is itself the correct behavior under
that rule, not a rollback defect. `cdp rollback --to-run cdp-badbad000001`
excluded it and re-folded to exactly the original **41** claims; `fold --check`
passed against the ledger; `cdp query claims --as-of <root-run-id>` reproduced
the same 41-claim answer read-only, without touching `state.json` on disk.
Scratch directory removed after the exercise.

**Golden baseline re-blessed, same pattern as every prior Phase 3 milestone.**
`state.json` gained one field, `"rollback": null`, on both the fixture and
`$TARGET_REPO` baselines (present, and null, whenever no rollback has ever
been recorded) — an intended additive shape change, not a regression.
Re-blessed with `python3 scripts/fixture_gate.py bless` and
`cdp selftest --golden $TARGET_REPO --bless`; `make check` re-run clean
afterward.

**Out of scope this session, by explicit user choice:** M3.8 (git hooks) —
still needs its own session per the standing note in the M3.5-M3.6 entry
above.

---

## D3 resolved — `SqliteStore` is now the CLI's actual default backend

Scoped to closing D3 only this session (`PHASE/FINDINGS.md`'s own account:
"the CLI's actual default backend is still `FileStore`... this is deferred
rather than rushed"). The path convention was already decided
(`CDP_CLI_SCOPE.md` 2.3, `phase_2_plan.md`: `./.cdp/index.db`) and
`tests/test_store_conformance.py`'s `SqliteStoreConformance.make_store`
already used it — this session wires the CLI to actually construct that
backend, rather than inventing a new convention.

**What changed.** Every `FileStore(paths.state)` construction in `cli.py`
(`scan`, `prompts`, `collect`, `fold`, `refresh`, `docs`, `status`, `rollback`,
`query`) now goes through one helper, `_open_store(state_dir) ->
SqliteStore(state_dir / "index.db")`. `query.Store`'s bare-`Path` constructor
(used by `cdp diff`'s two positional state directories, and any external
caller) now auto-detects: `index.db` present -> `SqliteStore`, else the
legacy raw-JSON directory -> `FileStore`, so `cdp diff` needed no changes at
its own call site.

**D16's rollback ledger needed zero changes.** `cdp/rollback.py` already went
through `store.read_artifact("rollback", ...)` / `write_artifact(...)`
generically rather than touching the filesystem directly, so it became a row
in `snapshot_artifact` automatically the moment the CLI's default backend
flipped — exactly the outcome the user anticipated going into this session.

**Three real defects found while wiring this up, not anticipated by D3's own
text, all fixed:**

1. **The reproducibility gate (`check_determinism`) would have false-positived
   on every scan.** It compared two scans' state directories byte-for-byte
   including `index.db`. A SQLite file's on-disk bytes are not guaranteed
   stable across two independent writes of identical logical content (page
   allocation is not just a function of the rows inserted) — the gate that
   exists specifically to catch non-determinism would have flagged the
   sqlite file as differing on every run, a permanent false alarm. Fixed by
   splitting `check_determinism` in two: `_state_files` now excludes
   `index.db` and keeps comparing genuine filesystem output (`docs/`,
   `prompts/`) byte for byte as before; `_store_snapshot` reads `index.db`
   back through the store API and compares canonical JSON per
   artifact/report/the patch log, the same technique `collect_artifacts`
   (below) uses. Confirmed live: `test_minirepo_scans_reproducibly` (a real
   scan, not a stub) passes against the new default backend.

2. **`hook.find_state` would have littered a `.cdp/index.db` at every parent
   directory it probed, on every watched tool call.** The hook's existence
   check (`FileStore(state).has_artifact("inventory")`) is side-effect-free
   for `FileStore` (a plain `Path.is_file()` check) but constructing
   `SqliteStore` unconditionally creates its db file and parent directory as
   a side effect of merely opening it — and `find_state` walks every parent
   of every file a watched tool touches, the overwhelming majority of which
   were never scanned. Fixed with a new `store.has_scanned(state_dir)`, a
   pure filesystem check (`index.db` or legacy `inventory.json` present) that
   never constructs a backend. `install_hook`'s own "has this repo been
   scanned" check had the identical bug and got the identical fix.

3. **Golden capture (`collect_artifacts`) walked the state directory's raw
   bytes**, which is meaningless for a single binary `index.db`. Rewritten to
   read every `ARTIFACTS`/`REPORTS` name and the patch log back through the
   store API and re-serialise with `golden_mod.canonical`, so capture is a
   function of content, not of the backend's on-disk format (the same fix
   as #1, applied to the golden gate instead of the determinism gate).
   `WorkspaceStore` gained `read_report` (symmetric with `write_report`,
   implemented on both backends) to make this possible — reports were
   write-only before.

**Golden baseline shape changed, both targets re-blessed.**
`scan/patches/0000-derived.json` (one file per patch, `FileStore`'s own
naming) became a single `scan/patches.json` (the canonical patch list) —
unavoidable, since `SqliteStore` has no per-patch filename to name a golden
path after. Every entry in `REPORTS` (`verify`, `conflicts`, `prompts`,
`rejected`) is now always captured, defaulting to `{}` when a report was
never written (`cdp scan` alone never runs `collect`/`prompts`) — a
deliberate choice: a report name always present, `{}` or populated, over one
silently absent depending on which commands happened to run before capture.
Re-blessed with `python3 scripts/fixture_gate.py bless` (fixture) and `cdp
selftest --golden $TARGET_REPO --bless` (target, run as part of this
session's `make check`).

**Real-scale exercise (R-E7), not just the fixture.** `cdp scan` /
`query stats` / `fold --check` / `docs` / `prompts` / `status` all run
against one real module (`$TARGET_REPO/sql-pool/sql-pool-api`, scratch state
dir): `index.db` is a real, openable SQLite file (`file(1)` confirms), every
command reads it correctly, and no stray top-level `*.json` artifact is
written alongside it. `hook.find_state` against a freshly `git init`'d,
never-scanned scratch directory returns `None` and creates no `.cdp/` at all
(confirmed by `rglob`).

**Cost, stated rather than assumed away.** Two long-lived test fixtures
(`tests/test_budget.py`, `tests/test_trace.py`) construct one
`query.Store(state)` per test class and reuse it across every test method;
neither closed it, which was invisible under `FileStore` (no connection to
leak) and surfaced as a `ResourceWarning: unclosed database` under the new
default. Fixed with `cls.store.close()` in each `tearDownClass`, the same
fix F8 already applied to `tests/test_store_sqlite.py`/
`test_store_conformance.py`. Every CLI command that opens a store now closes
it on its success-path `return` (not wrapped in `try/finally` — an error
path aborts the process anyway, and this codebase's own `FileStore` has
never had a `close()` method at all, so strict resource discipline on every
exception path is not this codebase's existing convention).

### Follow-up in the same session — every remaining `FileStore` fallback removed

The above left three dual-path fallbacks in place for backward compatibility
with the pre-flip, raw-JSON layout: `query.Store`'s bare-`Path` constructor,
`hook.decide`'s backend selection, and `SqliteStore`'s internal reuse of
`FileStore` for the inbox directory. Told explicitly to remove all of them —
*"everything go via db... nothing shall point to filestore"* — so:

- **`query.Store.__init__`** no longer falls back to `FileStore` for a bare
  directory. It requires `<dir>/index.db`; anything else is "no CDP state at
  <path>", the same message as before, just no longer trying a second
  backend. `cdp diff`'s two positional state directories needed no change —
  both are always produced by `cdp scan --state-dir`, which always writes
  `index.db` now.
- **`hook.decide`** always constructs `SqliteStore(state / "index.db")`
  directly (no ternary). Safe because `find_state` already confirmed
  `has_scanned(state)` — i.e. `index.db` exists — before `decide` ever opens
  it, so this never hits the side-effecting "file doesn't exist yet" case
  `has_scanned` exists to avoid (previous entry, point 2).
- **`SqliteStore`'s inbox** no longer constructs a `FileStore` internally.
  `ensure_inbox`/`read_inbox`/`clear_inbox` are inlined directly against
  `<db_path's dir>/patches/inbox/`, the exact same layout, same behaviour —
  this was pure code reuse, not a second backend, so inlining it changes
  nothing observable, it just means `FileStore` is never constructed by any
  path this session's D3 work touches.
- **`cdp gc --db` is now optional**, defaulting to `_paths(args).state /
  "index.db"` — the same resolved store every other command already writes
  to by default. Before this, `gc` was the one command that could not use
  the default resolution at all (it needed `SqliteStore` back when nothing
  else produced one); now that every command does, `gc` needs no special
  setup step for the common case. `--db` remains as an explicit override.

`FileStore` the class is unchanged and still exported from `store/`: it
remains the reference implementation the backend-conformance suite
(`tests/test_store_conformance.py`) checks `SqliteStore` against, and
`test_store_sqlite.TestBackendEquivalence` still folds identically over
either backend. Deleting it would remove that cross-check for no
behavioural gain — a `grep -rn "FileStore(" cdp/` after this pass finds it
constructed nowhere outside `cdp/store/file_backend.py` itself.

**Re-verified:** full `make check TARGET_REPO=...` re-run green after this
follow-up (both golden baselines already re-blessed under the prior entry
needed no further re-bless — this pass changed backend *selection*, not
`state.json`/`partition.json`/any artifact's content).

---

## Phase 4 (M4.2) — the four unknown gates

Scoped to M4.2 only this session, by explicit user choice: `phase_4_plan.md`'s
own remaining milestones (M4.2-M4.4) were judged comparable in size to all of
Phase 3 (five separate sessions), the same account M4.1's entry above already
gives. M4.3 (`needs_*`/R12 ratchet) and M4.4 (`cdp answer`) remain
unimplemented.

**What shipped.** `cdp/gates.py` (new): `build_extraction_index(extraction)`
reuses the same structural index `entail.py` builds for claims (defined fqns,
io_edge subjects, `(subject, channel) -> edge`). Four gates:

- **Gate 1, subject exists** (`gate_subject_exists`) — an unknown's optional
  `subject` field must resolve to a `defines[]` fqn, an io_edge source/target,
  or a real scope node. No `subject` at all passes unconditionally (see D20
  below).
- **Gate 2, negative entailment** (`gate_negative_entailment`) — requires
  both `subject` and `channel`; if `(subject, channel)` already matches an
  io_edge, the unknown is rejected citing that edge's file:line.
- **Gate 3, provenance state** (`provenance_state`) — reads `snapshot_task`
  (0.12) rows, keyed by scope hash, to assign `unexamined` / `unknown` /
  `abandoned`. See D21: this table has no writer yet, so every real call
  today resolves `unexamined`.
- **Gate 4, clustering** (`cluster_unknowns`) — annotates (never rejects or
  merges) `cluster_id`/`cluster_size` on unknowns whose `question` *and*
  `why_unresolved` both match another's, exactly.

Gates 1-3 run in `cmd_collect`, per accepted patch, before its `unknowns[]`
is appended to the log — the same point schema validation already runs at,
and for the same reason: a rejection needs a specific, cited reason attached,
not a silent drop. Rejected unknowns never enter the log; they are recorded
in a new `reports/unknown_gates.json` (`REPORTS` gained this name) alongside
the existing `rejected` report for schema-invalid patches. Gate 4 runs inside
`state.fold`, over the fully deduped `unknowns[]`, because cluster membership
is a property of the *whole current set* and must stay current as unknowns
come and go across folds — it needs no ledger entry since it only annotates.
`schema/patch-1.0.0.json`'s `unknown` def gained five optional fields:
`subject`, `channel` (author-suppliable, checked by gates 1/2),
`provenance_state`, `cluster_id`, `cluster_size` (gate-assigned, never
present on a patch as authored — the same posture `verdict` already has on
`claim`).

**D20 — `subject`/`channel` are optional on `unknown`, not required.** The
plan's gate 1 wording ("names a subject present in `defines[]`/`io_edges`")
reads as if every unknown must name one, but requiring it would break every
existing unknown producer with no migration path: `_structural_unknowns`'s
module-naming question, the "node not successfully examined" gap `state.fold`
emits for a superseded node, and any already-collected historical patch. That
is the exact shape of problem M4.3 is scoped to solve properly for `needs_*`
(schema change + required + grandfathering decision) — inventing a second,
smaller version of that migration inside M4.2 would preempt M4.3's own design
work. Chosen instead: `subject` absent means "this is a scope-level gap," and
gates 1/2 pass it unconditionally. This is also the plan's own stress-test
answer ("allow a scope-level subject") generalised one step further: a
*missing* subject is the limit case of a scope-level one.

**D21 — gate 3's data source does not exist yet; the read path is wired, not
the writer.** `snapshot_task` (`sqlite_backend.py:121-132`) was created
schema-only in Phase 2, "driven in Phase 5" per its own comment — no dispatch
loop in this codebase writes to it. Added `SqliteStore.task_states(run_id)`
(a plain `SELECT ... WHERE run_id=?`, keyed by `scope_hash`) as the minimal
read primitive gate 3 needs; `cmd_collect` calls it once per distinct
`run_id` in a batch (cached) and looks up each patch's node via
`partition.json`'s `scope_hash` (M3.4). Until Phase 5 populates the table,
every real call returns `{}` and every node's `provenance_state` is
`unexamined` — an honest gap, verified directly (below), not assumed.

**Real-scale exercise (R-E7), not just the fixture.** `sql-pool/sql-pool-api`
scanned fresh into `/tmp/m42_scratch`. A hand-written inbox patch for its one
non-empty scope (`root/(files+2)`) carried three unknowns: a legitimate
scope-level one ("why is there no retry here?", `subject` = the scope node
itself), one already answered by a real `config_read` io_edge in that scope
(`subject`/`channel` set to match it), and one naming a fabricated subject.
`cdp collect` against that scratch state:

```
gates     2 unknown(s) rejected
  REJECTED unknown (root/(files+2)): already answered by io_edge config-file:.../dropwizard-service-config.yml -> config:logging.type (config_read) at src/main/resources/dropwizard-service-config.yml:21
  REJECTED unknown (root/(files+2)): subject 'Nonexistent.FakeSubject' names nothing in defines[]/io_edges and is not a scope
```

Both real defects M4.2's acceptance criteria name are demonstrated with a
cited reason on real target data; the legitimate scope-level unknown survived
into `state.json` with `provenance_state: "unexamined"` (D21's expected
answer, given no task writer exists). Scratch directory outside the repo,
removed after the exercise.

**Test coverage.** `tests/test_gates.py` (new, 16 tests): each gate in
isolation (subject in `defines`/io_edges/scope-node passes; no subject passes;
a bogus subject is rejected; an answered `(subject, channel)` is rejected
citing the edge; an unanswered one passes; all three `provenance_state`
outcomes; a mixed batch splitting kept/rejected correctly), the clustering
stress test from the plan's own table (identical question+reason clusters;
*shared phrasing with different reasons does not* — the 40-distinct-unknowns
false-positive class named explicitly), and one end-to-end test driving the
real `collect` CLI against a freshly scanned fixture repo with a hand-written
inbox patch, asserting the rejection reasons and the surviving unknown's
`provenance_state` through `reports/unknown_gates.json` and `state.json`.
Fixture suite (`test_gates`, `test_pipeline`, `test_entail`,
`test_store_sqlite`, `test_store_conformance`, 97 tests) green before the
target-scale exercise above; no defect found this session (unlike M4.1,
which found two).

**Golden baseline re-blessed, same pattern as every prior phase.**
`REPORTS` gaining `unknown_gates` changes every scan's captured report set
(now always includes `unknown_gates: {}` when `collect` never ran, same
convention `rejected` already established). Re-blessed with
`python3 scripts/fixture_gate.py bless` and
`cdp selftest --golden $TARGET_REPO --bless`; `make check` is the gate run
reported in `PHASE/TARGET.md`.

**Out of scope this session, unimplemented:** M4.3 (`needs_*` required
vocabulary, the full R12 ratchet including rollback-restores-unknowns and
`moot` vs `resolved`, the grandfathering migration decision D20 explicitly
declines to improvise) and M4.4 (`cdp answer`, R11, the `RetryPolicy.execute`
decay scenario end to end).

---

## Phase 4 (M4.3-M4.4) -- needs_*/R12 ratchet, and `cdp answer`

Scoped to M4.3 and M4.4 in one session (M4.1/M4.2 were already done going
in). Both milestones landed; the plan's own stress-test table is what's
tested in `tests/test_gates.py`'s new classes and `tests/test_answer.py`.

**F13 -- a real defect found and fixed: unknowns silently vanished across a
node's re-run, which is exactly what R12 forbids.** Before this session,
`state.fold` took claims *and* unknowns from only the highest-generation
`complete` patch per node (M3.4's supersession, correct for claims, applied
unmodified to unknowns too). A later patch for the same node that simply
didn't restate an earlier question made it disappear from `state.json` --
"a later patch that simply omits it does not resolve it" is R12's own
wording for the failure this reproduced exactly. Fixed in `cdp/state.py`:
unknowns now accumulate across *every* `complete` patch for a node (claims
still take only the best generation); `_dedupe_unknowns` already collapses an
exact repeat, so this costs nothing for the common case and only matters when
a re-run's patch omits a question a prior one asked.

**What shipped.**
- `cdp/gates.py`: `NEEDS_VALUES` (the closed vocabulary), `gate_needs_valid`
  (per-unknown, alongside gates 1-3 in `gate_patch_unknowns` -- a 4th
  rejection reason, same report), `grandfather_needs` (missing `needs` ->
  `needs_human` + `needs_migrated: true`), `discharge_unknowns` (the R12
  ratchet itself: `open` / `resolved` / `moot`, `resolved_by` attribution).
- `cdp/state.py`: wires `grandfather_needs` -> `discharge_unknowns` ->
  `cluster_unknowns` into the fold pipeline, using the same
  `build_extraction_index` `entail.py`/`gates.py` already share. The
  fold-internal "node not examined" unknown now carries `needs: needs_human`
  directly (not grandfathered -- it's a live view, not legacy data).
- `cdp/entail.py` (R11): a `contradicted` claim with `author_kind=human`
  gets `confidence: "contested"` -- the same value `merge.py` already uses
  for a cross-agent conflict, reused here for a claim-vs-extraction one.
  `verdict` itself stays `contradicted`; only `confidence` is downgraded, so
  the structural signal survives alongside the "not accepted" marker.
- `cdp/cli.py` `cmd_answer` (`cdp answer <scope> --subject --kind --claim
  --anchor --channel --confidence --author --mode`): builds one claim,
  reads the real anchor text via `anchor.build_anchor` (a human is not
  exempt from the same span-growing/qualification rule as an agent),
  validates against the schema, appends a `complete`, `author_kind=human`
  patch, and folds -- the exact `validate -> verify -> entail -> fold` path
  `cmd_collect` already runs, no second code path. `--author` defaults to
  `git config user.name <user.email>` in the target repo.
- Schema (`schema/patch-1.0.0.json`): `$defs.needs` (the 5-value enum),
  `$defs.resolved_by` (`claim_id`/`author_kind`/`at_snapshot`, required
  together), `unknown.needs`/`needs_migrated`/`status`/`resolved_by` (all
  optional -- enforced by the gate, not `required`, so a pre-M4.3 patch in
  the log is never retroactively invalid), `claim.author_kind`/`claim.author`
  (per-claim, distinct from the existing patch-level `author_kind`).
- `cdp/helpdoc.py`: a `"unknowns, honestly"` guidance section states the
  completeness-of-unknowns-is-out-of-scope-permanently position in `cdp
  help`, per the plan's own instruction that this belongs in user-facing
  docs, not only design notes.

**D22 -- `needs` is enforced by a gate in `collect`, not `required` in the
JSON schema, despite the plan's "`needs_*` becomes required" wording.** A
hard schema `required` would reject the *entire* patch -- claims included --
the moment one unknown lacked it, which is a much bigger blast radius than
"this one unknown is malformed," and every unknown-producing test and
fold-internal unknown (the superseded-node gap) would need updating in
lockstep with no room to grandfather gradually. Treating `needs` the same
way `subject`/`channel`/`provenance_state` already are (D20: schema-optional,
gate-enforced) keeps one migration discipline for the whole `unknown` object
instead of two, and still satisfies the plan's exit criterion literally: "An
unknown without `needs_*` is rejected" -- in `collect`, with a cited reason,
exactly like gates 1-3.

**D23 -- grandfathering runs in `fold`, unconditionally, not as a one-time
backfill command.** Every unknown that reaches `discharge_unknowns` --
whether logged before this session or emitted fresh by `fold`'s own
superseded-node path -- passes through `grandfather_needs` first. This means
`needs_migrated` is recomputed every fold rather than written once, which is
consistent with the fold invariant (`state.py`'s own docstring: nothing may
enter `state.json` that isn't derivable from the log) -- a one-time backfill
would itself be an undocumented write to the log.

**D24 -- R11 is implemented at the entailment layer (human-vs-extraction),
not inside `merge.py`'s cross-claim precedence (human-vs-model).** The
plan's own stress-test row ("human contradicted by extraction: contested")
is exactly the entailment case, and it's what `entail.py`'s new check
covers. The *other* half R11's CDP_CLI_SCOPE.md wording implies --
"humans outrank models on interpretation" as a merge-time precedence rule,
for when a human claim and a model claim about the same subject conflict --
is not touched: `merge.py`'s conflict resolution (`_resolve`) has no notion
of `author_kind` today, and no scenario in this corpus produces a human-vs-
model merge conflict to prove a fix against. Rewiring `_resolve`'s precedence
order is real, separate work with its own blast radius on `merge.py`'s
existing ownership/evidence-count resolution and the golden baseline; flagged
here rather than improvised, per R-E13.

**D25 -- `cdp answer --kind` uses the existing closed `claim_kind` enum, not
`ARCHITECTURE.md`'s illustrative `--kind rationale`.** `rationale` is not one
of `claim_kind`'s ten values and was never meant to extend the vocabulary --
`_parser()` now loads `schema/patch-1.0.0.json`'s `$defs.claim_kind`/
`$defs.channel` directly for `--kind`/`--channel`'s `choices`, so this can't
drift from the schema. R11 says humans outrank models on interpretation,
never on structure, and a closed vocabulary is exactly the structure a human
does not get to bypass either -- the demonstration below uses `--kind naming`
in place of the prose example's `rationale`.

**Real-scale exercise (R-E7), on `$TARGET_REPO/sql-pool/sql-pool-api`
(scratch state dir, removed after):**

```
$ cdp answer "root/(files+2)" --subject Dockerfile.JDK_JAVA_OPTIONS \
    --kind naming --claim "..." --anchor Dockerfile:17
answer    human.a0000fcd013c02a1  verdict=consistent  confidence=high

$ cdp answer "root/(files+2)" --subject Fake.Thing --kind naming \
    --claim "..." --anchor Dockerfile:99999
cdp: no citable anchor at Dockerfile:99999 -- humans are not exempt from
anchor verification either                                    (exit 2)

$ cdp collect   # hand-written unknown with no `needs`
gates     1 unknown(s) rejected
  REJECTED unknown (root/(files+2)): needs None is not one of
    ['needs_external_doc', 'needs_human', 'needs_other_repo',
     'needs_runtime', 'needs_wider_scope']
```

`query unknowns --json` on the same scratch scan shows the real,
pre-existing "What is this module called?" structural unknown grandfathered
correctly: `"needs": "needs_human", "needs_migrated": true, "status": "open"`
-- exercised on live target data, not a synthetic dict.

**Test coverage.** `tests/test_gates.py` gained `NeedsGateTest` (3),
`GrandfatherNeedsTest` (2), `DischargeUnknownsTest` (5, covering the plan's
own table: scope-level always open, subject-gone is moot not resolved,
matching claim resolves with attribution, a contradicted claim does not
discharge, no match with a live subject stays open); two existing tests
(`test_mixed_batch_splits_kept_and_rejected`,
`test_collect_rejects_bad_unknowns_and_keeps_the_legitimate_one`) needed one
line each adding `needs_human` to their previously-kept unknowns -- expected
fallout of turning the gate on, not a defect. `tests/test_entail.py` gained
the R11 pair (human-contradicted -> contested; llm-contradicted -> unchanged
confidence). `tests/test_answer.py` (new, 3 tests, end-to-end through the
real CLI on the fixture repo): a claim is kept and discharges a matching
unknown with attribution; a fabricated anchor is rejected; editing the
anchored file and running `refresh` clears `claim_reviewed_at` and relocates
the anchor -- the `ARCHITECTURE.md` `RetryPolicy.execute` decay scenario,
reproduced end to end. Full suite: 335 tests (up from 320), all green;
vendored copy re-synced via `cdp install --self`.

**Out of scope, unimplemented:** R11's merge-precedence half (D24); a
`--visibility`/other-discrete-field flag on `cdp answer` (only `naming`-style
claims with no comparable discrete field were exercised, so a human-authored
contradiction was proven at the unit level, not through the live CLI);
Phase 6/8/9's consumers of `needs_wider_scope`/`needs_other_repo`/the
`contradicted` bucket, unchanged from M4.1/M4.2's own account.

## Phase 5 (M5.1) — runner protocol, exercised on a real prompt/patch pair

Scoped to M5.1 only this session; M5.2-M5.6 deferred to later turns (the
phase's own concurrency/crash-simulation content does not compress into one
sitting — see the budget flag raised before starting).

**D26 -- the protocol lives as `cdp/runner.py`'s module docstring, not a
separate doc file.** ~50 lines, matching M5.1's acceptance line exactly; kept
next to the two reference implementations so it can't drift from them
unnoticed. `RunResult` is a 4-field dataclass (`ok`, `wall_ms`, `tokens`,
`error`) -- `tokens` is `Optional[int]` since a subprocess runner often
can't see it, per the plan's own text.

**D27 -- a runner-level failure (non-zero exit, timeout, OSError) is
`ok=False`; a well-formed-but-empty patch is not the runner's problem.**
Schema/yield-collapse classification is `cdp run`'s job (M5.2), not the
runner's -- kept the boundary exactly where the docstring's own "Output"
section draws it, rather than have `runner.py` start guessing about patch
content.

`tests/test_runner.py` (6 tests, new): a stdlib-only-imports check via
`ast.parse` (AST walk, not the file's text, so it can't be fooled by a
comment); one shared conformance pair (`_assert_success`/`_assert_failure`)
driven against both `SubprocessRunner` and `FileRunner` for success,
non-zero-exit, and timeout -- the timeout cases prove rule 1 (no exception
escapes `run()`) rather than just asserting it in prose.

**Real-target exercise (R-E7):** `sql-pool/sql-pool-api` scanned fresh into
a scratch dir (0.34s), `cdp prompts` run for real (`root/(files+2)`,
`root/src/main/java` -- both node names contain `/`, and one contains `(`
and `+`, a real adversarial case for the `__`-replacement inbox-naming
convention). `SubprocessRunner` driven against the real
`prompts/root__(files+2).md` file, writing a real patch to the exact
`patches/inbox/root__(files+2).json` convention `cdp prompts`' own docstring
specifies; `cdp collect` then accepted it (`accepted 1, rejected 0`,
`41/41 claims kept`) with no modification to either command -- the
file-handoff contract holds against real node names, not just a synthetic
tmp path. Scratch dir removed after.

**Out of scope, unimplemented:** M5.2 (task state machine), M5.3
(`cdp run` itself), M5.4 (leases), M5.5 (`--resume`/partition-drift guard),
M5.6 (overhead measurement) -- all deferred, none started.

## Phase 5 (M5.2-M5.3) -- the task state machine and `cdp run`

Scoped to M5.2 and M5.3 only this session, by explicit user choice: the
remaining five milestones could not fit this session's budget with the same
rigor prior phases used (M5.4's lease atomicity and M5.5's crash/resume both
carry real concurrency-simulation weight of their own). M5.4-M5.6 remain
unimplemented.

**What shipped.** `cdp/supervisor.py` (new): the state machine
(`pending -> dispatched -> returned -> validated -> folded`, with
`expired`/`invalid`/`anchors_failed`/`empty` retrying up to `MAX_ATTEMPTS`
(3) before `abandoned`) plus `dispatch_scope` (one scope's full retry loop),
`run_wave` (dispatches every scope in a set of nodes, sequentially -- see
D29), and `mark_folded` (bumps a wave's validated tasks to `folded` once its
fold has run). `SqliteStore` gains `begin_run`/`finish_run`/`upsert_task`/
`task_rows` (`store/sqlite_backend.py`) -- `snapshot_run`/`snapshot_task`
were schema-only since Phase 2 ("created here, driven in Phase 5"); this is
that driver. `cli.py` gains `cdp run --wave N|--wave-all|--stale-only|--scope`,
wired to a `--runner-cmd` (shells out via `SubprocessRunner`) or, by default,
`FileRunner` (today's manual loop, waited on automatically). `status` gains
the per-run task table M5.2's acceptance line asks for.

**D28 -- a runner-level failure (`RunResult.ok=False`) is classified
`expired`, not a fifth failure category.** The plan names four failure
states and says what each *means* (`invalid` = schema violation,
`anchors_failed` = fabricated/moved anchor, `empty` = yield collapse,
`expired` = the supervisor died) but the plan's own vocabulary has no name
for "the runner crashed, timed out, or returned non-zero" -- a real,
frequent case `runner.py`'s `SubprocessRunner`/`FileRunner` both produce.
Chosen: `expired` covers all three, since the operational fact is identical
in every case -- the task did not return a usable result within its
allotted time -- and the remedy is identical too (redispatch). The specific
cause is never lost: `last_error` carries the runner's own message
(`result.error`), only the *bucket* is shared. This also means `expired` is
real-world reachable **now**, inside a single `cdp run` process, well before
M5.4's supervisor-heartbeat mechanism exists to detect an actual supervisor
death -- proven by `tests/test_supervisor.py`
`test_expired_invalid_empty_then_abandoned`, which forces a `SubprocessRunner`-
style `ok=False` on the first attempt and confirms `expired` is written to
`snapshot_task` before the retry loop continues.

**D29 -- `run_wave` dispatches every scope in a wave sequentially, not
concurrently, despite `runner.py`'s own M5.1 rule that a runner "must
tolerate concurrent calls... a wave dispatches in parallel."** Real parallel
dispatch needs the atomic lease acquisition M5.4 provides (`upsert_task`'s
insert-or-update today has no protection against two processes racing the
same `(run_id, scope_hash)` row -- fine for one supervisor, wrong for the
"two supervisors, same run" stress test M5.4 owns). M5.3's own acceptance
line only asks that `cdp run --wave-all` "completes... and matches what the
manual `SKILL.md` loop produces for the same scopes" -- sequential dispatch
satisfies that literally, at the cost of not yet buying wall-clock
parallelism. Flagged rather than raced against M5.4's real job.

**D30 -- `cdp run`'s dispatch `run_id` is the scan's own `run_id`
(`store.manifest["run_id"]`), not a separately invented dispatch-session
id.** `snapshot_run`/`snapshot_task` are keyed by `run_id`, and so is every
patch's own `run_id` field (`cmd_scan`/`cmd_collect` already stamp
`store.manifest.get("run_id", "cdp")` onto every patch) and `cdp rollback
--to-run`'s target. Reusing the same value means a `cdp run`-dispatched
patch is indistinguishable in provenance from a manually-collected one, and
`cdp rollback --to-run <this-commit's-run>` addresses exactly what `cdp run`
produced, with no second identifier space to reconcile.

**D31 -- gate 3's `provenance_state` (`cdp/gates.py`, M4.2) is updated to
read the real state names `dispatch_scope` now writes.** Before this
session it checked `state == "complete"` (-> `unknown`) and
`attempts >= 3` (-> `abandoned`), both placeholders guessed before any real
writer existed. Now it checks `state == "folded"` (-> `unknown`: the scope
was actively, successfully examined and this question still stands) and
`state == "abandoned"` (-> `abandoned`, M5.2's own terminal name) directly.
`tests/test_gates.py`'s two placeholder-era tests
(`test_complete_task_is_unknown`, `test_three_failed_attempts_is_abandoned`)
are renamed and updated to the real vocabulary
(`test_folded_task_is_unknown`, `test_abandoned_task_is_abandoned`).

**R6 held with no new fold-side code.** An `abandoned` scope needs to
surface as an honest `unknown`, never a silent gap. `state.fold` already
synthesises exactly that unknown ("What does %s contain? Its scope was not
successfully examined.") for any node whose best patch status is not
`complete` (`cdp/state.py:178-197`, Phase 1). `_apply_wave_results` (`cli.py`)
appends a `status: "failed"` patch (no claims) for every abandoned scope --
reusing the *existing* `failed` status value `STATUS_RANK` already ranks --
so the existing fold logic does the rest. Verified directly in
`tests/test_supervisor.py`'s real-target exercise: 100% coverage held with
both scopes `complete`, and separately (fixture-level, via the state-machine
unit tests) an abandoned scope's synthesized unknown was inspected, not
assumed.

**Real-target exercise (R-E7), not just the fixture.** `sql-pool/sql-pool-api`
scanned fresh into a scratch dir; a fake runner (a 6-line external script,
driven through the real `--runner-cmd` / `SubprocessRunner` path, not an
in-process stub) always contributes a scope-level unknown and no claims:

```
$ cdp run --repo .../sql-pool-api --wave-all --runner-cmd "python3 fake_runner.py"
wave 0       2 scope(s)  validated 2

$ cdp status
tasks     run cdp-7e10575adf69
    folded         root/src/main/java                       attempts 1
    folded         root/(files+2)                            attempts 1
```

Both real scopes went `pending -> dispatched -> returned -> validated ->
folded` end to end through the actual CLI (not the state-machine functions
called directly), coverage stayed 100% (the module's 41 structural claims,
untouched by this run, already covered it), and `status`'s new task table
rendered correctly. Scratch dir removed after.

**Test coverage.** `tests/test_supervisor.py` (new, 4 tests): a scripted
runner drives one scope through `expired -> invalid -> empty -> abandoned`
in one dispatch call (a spy on `upsert_task` proves every intermediate state
was actually written, not just the final one), a second scope through
`anchors_failed -> validated -> folded` (a fabricated anchor demotes the
first attempt's claim entirely under strict mode, a clean claim on the
retry survives), and two CLI end-to-end tests (`cdp run --wave 0` against a
real scan folds and marks every task `folded`; `cdp run --stale-only` with
nothing stale exits cleanly, printing "zero scopes need review," per the
plan's own stress-test row). Full suite: 345 tests (up from 339 pre-M5.1's
own two new files, +6 from this session's `test_supervisor.py`... `git diff
--stat` shows the exact count), all green; vendored copy re-synced via
`cdp install --self` before the gate.

**Out of scope this session, unimplemented:** M5.4 (leases -- heartbeat,
atomic acquisition, "two supervisors" stress test), M5.5 (`--resume`,
partition-drift guard, `--max-attempts` as a CLI flag rather than
`supervisor.MAX_ATTEMPTS`'s hardcoded default), M5.6 (fixed-overhead
measurement, the batching decision).

---

## Phase 5 (M5.4) — leases, held by the supervisor

Scoped to M5.4 only this session, by explicit user choice (M5.5/M5.6 remain
deferred — the user was asked directly, given the remaining phase's real
concurrency/crash-simulation weight, and chose leases first).

**What shipped.** `SqliteStore.acquire_lease(run_id, scope_hash,
lease_seconds)` (new): one atomic `UPDATE ... WHERE lease_until IS NULL OR
lease_until < now()`, falling back to an `INSERT` for a scope's first-ever
claim (guarded by the table's existing `(run_id, scope_hash)` primary key
against a same-instant race on that insert). `heartbeat_lease`/`release_lease`
round out the trio. `supervisor.py` gains `_LeaseHeartbeat`, a background
thread started around every `runner.run()` call that renews the lease every
`HEARTBEAT_SECONDS` (30) for up to `LEASE_SECONDS` (90) — the numbers
`phase_5_plan.md` M5.4 names directly, still a constant because there is no
per-`dim_tier` p99 to derive a ceiling from until Phase 9's star exists (the
plan says so explicitly; this session records `wall_ms` per task, a new
`snapshot_task` column via `SCHEMA_V5`, so that ceiling has real data to
replace the constant with later). `dispatch_scope` returns `None` — not any
task state — for a scope another live supervisor already holds the lease
for; `run_wave` filters those out of its results rather than reporting them
as any of M5.2's task states, since "someone else is working this" is not a
outcome this process produced.

**Why a background thread and not a between-attempts check.** The one place
`dispatch_scope` blocks is inside `runner.run()`, which can run for an
unbounded time (a slow frontier model, or literally forever per the plan's
own stress-test row). A lease held only at dispatch time would let another
supervisor reclaim a scope out from under a runner that is still working,
the moment `LEASE_SECONDS` elapses — the heartbeat thread is what keeps a
genuinely long-but-alive call safe, proven directly
(`tests/test_supervisor.py` `HangingRunnerLeaseTest`: a runner that sleeps
longer than one lease period; a second, independent `SqliteStore` connection
attempts to steal the lease mid-sleep and fails, then succeeds immediately
once the scope reaches a terminal state and releases it).

**`check_same_thread=False` on the connection (`sqlite_backend.py`).** The
heartbeat thread and the main thread both touch the same `SqliteStore`'s
connection, but never concurrently — the main thread is parked inside
`runner.run()` while the heartbeat fires, not racing it — so this is safe
without adding a lock of this module's own. Also added: `PRAGMA busy_timeout
= 5000`, since two *separate* `SqliteStore` connections (two real supervisor
processes) racing the same lease row is now a real code path, not a
hypothetical one, and the loser should lose the race cleanly (0 rows
affected) rather than raising `database is locked`.

**Test coverage, both stress-test rows the plan names by name.**
`tests/test_supervisor.py`, 5 new tests, all at millisecond lease durations
(the mechanism is duration-independent; a fast suite proves it the same as a
slow one, per `PHASE/EXECUTION_RULES.md` R-E5): atomic acquisition (a second
connection gets nothing while the first holds it — "two supervisors, same
run" from the plan's stress-test table, verbatim), release-then-reacquire,
expiry-based reclaim with no heartbeat (simulating a dead process — "kill
the supervisor mid-wave" from the acceptance criterion, at the mechanism
level), heartbeat keeping a live holder's lease alive past what the bare
lease duration would allow, and `HangingRunnerLeaseTest` — the plan's
"runner hangs forever... lease expiry is the only thing that saves the run"
row, driven through the real `dispatch_scope`, not a synthetic timer.

**Real-target exercise (R-E7).** `sql-pool/sql-pool-api` scanned fresh into
a scratch dir; `acquire_lease`/`release_lease` exercised directly against
that real `index.db` via two independent `SqliteStore` connections (see
`PHASE/TARGET.md` for the transcript) — atomicity and reclaim hold against a
real scanned store, not only the fixture. Scratch dir removed after.

**Not done this session, by the scoping choice above.** `--max-attempts`
stays `supervisor.MAX_ATTEMPTS`'s hardcoded `3`, not yet a CLI flag (M5.5).
`cdp run` does not yet call `acquire_lease` for a *second concurrent process*
in practice — nothing launches two `cdp run` invocations against one run
today — so the atomicity this session proves is proven at the backend level
(two connections, real races) and is ready for M5.5/a future concurrent
driver to exercise end-to-end, not yet exercised through two live `cdp run`
CLI processes. The `ARCHITECTURE.md` crash scenario (2 reclaimed, 1
dispatched, 13 folded untouched) is M5.5's acceptance line, not this one's —
this session proves the lease primitive it depends on.

---

## Phase 5 (M5.5) — `--resume`, the partition-drift guard, and `--max-attempts`

Scoped to M5.5/M5.6 only this session (M5.1-M5.4 already landed; `phase_5_
plan.md`'s remaining two milestones). `cdp/store/sqlite_backend.py` gains
three methods: `get_run` (the `snapshot_run` row, or `None`), `reclaim_expired`
(moves any `dispatched` task past its lease to `expired`, returning the
`scope_hash`es reclaimed), and `copy_folded_tasks` (carries a `folded` row
from one run into another verbatim — only `folded` rows, an unfinished scope
has nothing worth inheriting). `supervisor.dispatch_scope`/`run_wave` take
`max_attempts` as a parameter (default still `MAX_ATTEMPTS = 3`) instead of
reading the module constant directly, and `run_wave` takes `skip_hashes` — a
set of scope hashes to leave alone entirely, never dispatched, never reported.

**`cmd_run`'s resume logic (`cdp/cli.py`).** `partition_hash` is computed
fresh on every invocation: `stable_hash(sorted((node, scope_hash) for every
scope in the current partition))`. Compared against `snapshot_run.partition_
hash` (already schema-present since Phase 2, unused until now):

- **No `--resume` flag:** unchanged from before this session — `begin_run` is
  idempotent (reuses the row if one exists), everything asked for is
  redispatched from a fresh `--max-attempts` budget. Not a regression: this is
  what "invoked again by hand" already did pre-M5.5, per M5.3's own docstring.
- **`--resume`, partition unchanged:** `reclaim_expired` runs first (any task
  still `dispatched` past its lease — the supervisor that held it is presumed
  dead), then every `folded` scope's hash is collected into `skip_hashes` so
  `run_wave` leaves it alone. This is the crash-and-resume path.
- **`--resume`, partition differs:** a new run id (`<run_id>-rN`, first unused
  `N`) is opened with the new `partition_hash`. Every scope this run's old
  `folded` set contains **whose `scope_hash` still appears in the new
  partition** (content unchanged) has its task row copied into the new run and
  is added to `skip_hashes`; everything else is re-queued under the new run.
  This is the answer to Phase 3's open interaction (a refresh landing mid-run
  changes the partition) named in `phase_5_plan.md` M5.5.

**Decision (D-M5.5a): attempt-count continuity is not preserved across a
reclaim.** A scope reclaimed from `dispatched`/`expired` re-enters
`dispatch_scope` and runs a fresh `1..max_attempts` loop rather than resuming
from wherever its attempt counter stood before the crash. The plan's
acceptance criteria (the `ARCHITECTURE.md` crash scenario: reclaimed / pending
/ folded counts, and the partition-drift new-run test) are both stated at the
*task-state* granularity, not the attempt-count one, and preserving exact
attempt continuity across a process crash would require persisting and
resuming the retry loop's internal state — a materially bigger change than
this milestone's own text asks for. Flagged, not implemented: a scope that
crashed on its 2nd of 3 attempts effectively gets a fresh 3-attempt budget on
resume rather than one more attempt. Own it if `--max-attempts` under
frequent crash-resume cycles is ever observed burning more attempts than
intended.

**Decision (D-M5.5b): a partition-drift resume does not update `manifest.
run_id`.** `cmd_status` reads `run_id` from `manifest.json`, which still names
the *original* run after a drift-triggered new run opens — an operator running
bare `cdp status` after a mid-run `refresh` would not see the new run's task
table without knowing to look for `<run_id>-r2`. Not fixed here: the plan
specifies the guard's *dispatch* behaviour (inherit unchanged, re-queue the
rest), not `status`'s display of it, and writing a new `run_id` into the
manifest on every `cdp run` invocation (rather than only scan/collect writing
it, today's convention) is its own decision outside this milestone's scope.

**Real-target exercise (R-E7), not just the fixture.** `sql-pool/sql-pool-api`
scanned fresh into a scratch dir; `cdp run --wave-all` folded both real scopes,
one task row was force-set back to `dispatched` with a lapsed lease (simulating
a crash), and `cdp run --wave-all --resume` reclaimed exactly that one scope
and left the other `folded` and untouched — see `PHASE/TARGET.md` for the
transcript. The partition-drift branch is exercised only at fixture scale
(`tests/test_supervisor.py`
`test_resume_with_changed_partition_opens_a_new_run_inheriting_unchanged_scopes`)
— reproducing it against the real target would need a second real scratch
scan after editing a tracked file, deferred for this session's budget (see
`PHASE/TARGET.md`).

**Test coverage.** `tests/test_store_sqlite.py` `TestRunsAndTasks`: 3 new
tests (`get_run`, `reclaim_expired` moving only past-lease `dispatched` rows,
`copy_folded_tasks` copying only `folded` rows). `tests/test_supervisor.py`
`RunCommandEndToEndTest`: 2 new tests, both driving the real `cdp run` CLI via
subprocess — the crash-and-resume scenario above, and the partition-drift
new-run scenario (edit a tracked file, re-scan, `--resume`, assert the new
`<run_id>-r2` run's task table shows the untouched scope still `folded`).

---

## Phase 5 (M5.6) — fixed overhead measured, batching decision recorded

`CDP_CLI_SCOPE.md` marks per-leaf fixed overhead "unverified — measure first"
and the plan forbids implementing batching before that measurement.
`cdp/prompts.py`'s `build_prompt` now tracks each of its six named sections'
character counts (`section_chars`) and a crude chars/4 token estimate
(`CHARS_PER_TOKEN_EST = 4`, documented as an estimate, not a real tokenizer).
`header` and `task` are the two sections whose size is a function of `node`/
`run_id` only, not of scope content — the part of the cost that scales with
*scope count* rather than code size, which is exactly the shape a wrong cost
curve would have. `cdp prompts --measure` (new flag) sums this across every
matched scope and prints the fixed/variable split instead of the usual
per-scope summary.

**Measured, on `sql-pool/sql-pool-api`'s 2 real scopes:**

```
fixed     757 tokens_est (378/leaf avg)
variable  11601 tokens_est (5800/leaf avg)
total     12358 tokens_est (6179/leaf avg)
```

**~378 tokens/leaf of CDP's own fixed template overhead, not ~10k.** At the
full `$TARGET_REPO` scale (172 scopes, `PHASE/TARGET.md`'s census), this
projects to roughly 65k tokens of fixed template overhead total — a real cost,
but nowhere near the "170k of overhead scaling with scope count" the plan
poses as the thing to check for, and small relative to the ~5.8k tokens/leaf
of variable (scope-specific) content already being sent.

**Batching decision: not implemented, and this measurement is why.** The
plan's own instruction is explicit — batch only if overhead is large enough
that batching buys something, because batching adds a real failure mode (one
bad scope's malformed JSON poisoning the whole batch's parse) that a
per-scope dispatch does not have. At ~378 tokens/leaf of *template* overhead,
batching 6-8 scopes per call would save on the order of 2-3k tokens per call
— not nothing, but not the order-of-magnitude problem that would justify
trading away per-scope isolation. **Not implemented.**

**What this number does not cover, stated rather than left implicit.** This
measures CDP's own prompt template only. It is *not* a real tokenizer's count
(the chars/4 heuristic is stated as such in the code and the CLI's own
output), and it does not include the system-prompt-plus-tool-definitions
overhead a real agent framework pays before reading anything — the exact
concern `phase_5_plan.md` M5.6 names first ("each leaf pays a system prompt
plus tool definitions before reading anything"). That overhead lives outside
this codebase, in whichever runner/framework a leaf actually runs under
(Phase 9's LiteLLM adapter and provider-specific system prompts), and remains
unmeasured — this session measures the one component CDP itself controls and
records that the other component is still an open question for whoever wires
up a real framework runner.

**Test coverage.** No test asserts an exact token count (the count is a
measurement artifact, not a behavioural contract); `tests/test_pipeline.py`
`TestCli` gains one new test driving `cdp prompts --measure` through the real
CLI and asserting the fixed/variable/total lines are present.

## Phase 6 (M6.1 only) — `cdp doctor`, scoped down from the full phase 6 plan

Session budget: the full `phase_6_plan.md` (doctor + a 25-40 question graded
benchmark run out-of-session against two arms + digest-first shipped behind a
flag + tiering v1, each re-benchmarked) needs dozens of live model calls and
is hours of work, not the ~20min/60k-token session budget. User chose to scope
this session to M6.1 (`cdp doctor`) only; M6.2 (graded benchmark), M6.3
(digest-first) and M6.4 (tiering) are **not started**.

**Shipped.** `cdp/doctor.py` + `cdp doctor` CLI command. Dispatches one
runner (reusing `SubprocessRunner`, same `--runner-cmd` convention as `cdp
run`) over every scope of an already-scanned repo and scores each patch on:
schema validity, anchor survival (`verify.py`), entailment split
(`entail.py`), recall vs a hand-authored golden set, and false-unknown rate.
Writes `<state>/doctor/<model-label>.json` per run and prints a compatibility
table across every model report already on disk.

**Golden set decision (unstated by the plan, resolved here).** The plan says
"golden set" without saying what one looks like. Implemented as
`GOLDEN_MINIREPO` in `cdp/doctor.py`: 4 hand-authored facts (2 per module),
read directly from `tests/fixtures/minirepo` source — not derived from any
CDP run, so it isn't circular. Matching rule: a claim "hits" a gold fact if
its `subject` contains a fixed substring AND its `statement` contains a fixed
keyword. Cheap and deterministic (no model-as-judge), but proven **brittle
on real model output** (below) — recorded as an open problem for M6.2's
judge-based grading to actually solve, not for this milestone to patch.

**Runner design fork, found and fixed only by running it for real (R-E7).**
First cut of `scripts/claude_leaf_runner.sh` piped the prompt into `claude -p`
with no tools. Against a real target-repo scope (`root/.claude` in
`/Users/sharmp49/git/code_scanner`) the model didn't fail loudly — it
fabricated a filesystem it never read ("23 files listed in scope do not
exist in repository"), because `build_prompt`'s output is a file *list*, not
file *contents* (`prompts.py`'s own docstring says so); a leaf needs
Read/Grep/Glob to do its job, matching `.claude/agents/cdp-leaf.md`'s
`tools:` line. Fixed: the script now takes `MODEL REPO` (not just `MODEL`)
up front, `cd`s into `REPO`, and runs with `--allowedTools "Read Grep Glob
Write" --permission-mode acceptEdits`, letting the model `Write` the patch
to an absolute path instead of printing to stdout. This is the real,
would-have-shipped-broken defect this milestone's own R-E7 exercise exists to
catch — invisible on `tests/test_doctor.py`'s fake runners, which never
touch a real filesystem.

**Live results (real `claude -p`, not fakes).**

- Against `code_scanner/.claude/` (real target, 1 scope, haiku): schema
  validation caught a genuine conformance defect — the model emitted
  `kind: "purpose"` and `kind: "authority"`, both outside the closed
  vocabulary the agent prompt lists verbatim. Doctor's schema-validity metric
  discriminates for a reason the plan's own "false-unknown" framing didn't
  anticipate: a capable model can still violate a closed vocabulary the
  prompt states explicitly.
- Against `tests/fixtures/minirepo` (2 golden scopes, `--timeout 180-280`):

  | model  | schema_valid | yield_collapse | recall | false_unknown |
  |--------|---|---|---|---|
  | haiku  | 100% | 0%  | 0%  | 0% |
  | sonnet | 33%  | 67% | 25% | 0% |
  | opus   | 33%  | 67% | 0%  | 0% |

  Haiku's 0% recall is **not** a real recall failure — inspecting its raw
  patch (`core.config.display_name_indexed_query_hint`, subject
  `table:widget`) shows it correctly stated "no corresponding custom query
  method appears in WidgetRepository," the exact fact the golden set wants,
  attached to a different `subject` than the golden entry's substring
  expects. Same for the duplicate-FQN fact: haiku's claim states the fact
  correctly but never uses the literal word "duplicate." **This is the
  brittleness the golden-set decision above warned about, demonstrated on
  real output, not hypothesised.** Sonnet and opus both show the identical
  67% yield-collapse pattern (`root/core`+`root/web` empty even at a 280s
  timeout for opus) — same two scopes fail for both, which points at an
  infra artifact in `scripts/claude_leaf_runner.sh` (most likely: the model
  attempts a tool outside `--allowedTools` and `acceptEdits` hangs on a
  permission prompt with no TTY to answer it, rather than a model capability
  difference) and not a model-quality finding. **Not disambiguated this
  session** — flagged rather than presented as a real capability result.
- Deviation from the acceptance criterion: all 3 models ran, but the
  compatibility table does not unambiguously demonstrate the specific
  "passes recall, fails false-unknown" pattern the acceptance criterion
  names — the closed-vocabulary violation (haiku, real target repo) and the
  golden-matcher brittleness (all 3, minirepo) are real discriminating
  signal, just not that exact pattern, and the sonnet/opus yield-collapse
  numbers are confounded by the runner-hang artifact above rather than
  trustworthy as capability data.

**Test coverage.** `tests/test_doctor.py`: 3 unit tests against fake
in-process runners (well-formed patch -> recall 1.0/false-unknown 0.0;
all-unknowns collapse runner -> recall 0.0/false-unknown 1.0, proving the
metric doesn't reward blanket "unknown" the way raw precision would; silent
runner -> reported as `empty`, not a crash).

**Open for M6.2+ (recorded, not solved here).** The golden-matching
brittleness above is exactly what "grade with a different model than
answers" (M6.2) is for -- a judge model reading "does this claim state fact
X" tolerates paraphrase; a substring match does not. Don't re-litigate the
substring approach inside M6.1 -- replace it when M6.2's judge exists.

---

## F10 (revisited) — verification caveat closed

F10's own text flagged that its `SyntaxWarning`-suppression fix had shipped
without a fresh `make check TARGET_REPO=...` re-run. Ran it: `359 tests`,
determinism (fixture + target), `fold --check` (fixture + target), golden
(fixture + target) all green, and the target run's stderr carries no
`SyntaxWarning` output (previously four lines per M6.1's account). Treat the
"believed zero-risk" language in F10 as confirmed, not merely argued, as of
this run.

---

## F14 — `--allowedTools` does not restrict the leaf's toolset; a leaf could
run Bash the whole time

**Severity:** high — this is not the M6.1 entry's "yield-collapse, cause
undisambiguated" note, it is the actual mechanism, and it is worse than a
timeout: `scripts/claude_leaf_runner.sh`'s entire safety premise is "a leaf
can only Read/Grep/Glob/Write, never execute" (its own comment, and
`.claude/agents/cdp-leaf.md`'s `tools:` line), and that premise did not hold.

**Confirmed live, not inferred.** `claude -p --model haiku --allowedTools
"Read Grep Glob Write" --permission-mode acceptEdits ...`, prompted to run
`date +%s%N` via Bash and report the exact stdout: it returned a real,
live nanosecond timestamp close to the invocation's own wall-clock time --
not a fabrication, an actual Bash execution. Same result whether
`--allowedTools` is space- or comma-separated. Only adding an explicit
`--disallowedTools "Bash"` blocked it -- meaning `--allowedTools` is a
permission-*pre-approval* list (skip the prompt for these), not an
allow-*list* (nothing outside it is available), which is the opposite of
what the runner's own comment assumed.

**Second-order consequence: this is also the undisambiguated yield-collapse
mechanism from the M6.1 entry above.** Any action `--allowedTools` doesn't
cover -- including, it turns out, a `Write` to a path outside the model's
working directory, which is the *normal* case here since the patch path is
CDP's out-of-repo state dir -- raises a permission prompt. `-p` is fed via a
pipe with no TTY to answer it, so without a deny-by-default it hangs until
`SubprocessRunner`'s own `--timeout` (180-280s in the M6.1 run) kills it --
indistinguishable from a real empty yield. This plausibly explains that
session's sonnet/opus 67% yield-collapse on the exact two scopes whose
patch path required an out-of-tree write, not a model-capability gap.

**Fix, `scripts/claude_leaf_runner.sh`:**
- `--tools "Read,Grep,Glob,Write"` replaces `--allowedTools` -- confirmed
  live to actually remove Bash from the model's toolset (a follow-up prompt
  gets "I don't have a Bash tool available", not an execution).
- `--add-dir "$ABS_PATCH_DIR"` -- `--tools`'s stricter mode also confines
  `Write` to the working directory unless granted, which broke the normal
  out-of-repo patch path; confirmed live that the same `Write` succeeds
  inside the repo and is refused outside it without this flag.
- `--permission-prompts none` -- makes any action still requiring a prompt
  (there should be none left, but this is the safety net) fail fast and
  visibly instead of hanging to the timeout.

**Verified end to end, real model calls, not fakes:** a normal `Write`
outside the repo succeeds (~12s); a Bash-escape prompt is refused with no
patch written and no hang (~8s); and the actual production composition --
`cdp scan` + `cdp prompts` on `tests/fixtures/minirepo`, the real prompt
file fed to the fixed runner, patch written to the real
`<state>/patches/inbox/<node>.json` path -- produces a schema-shaped patch
(2 claims, 2 unknowns) in ~75s.

**Not done this session:** re-running M6.1's sonnet/opus doctor pass against
the fixed runner to confirm the yield-collapse actually clears (would need
another round of live, multi-minute model calls per model/scope; flagged
for whoever picks up M6.2).

---

## F15 — no guard against dispatching leaf agents at AI-tool/editor scaffolding

**Severity:** medium -- not a correctness defect (nothing wrong was claimed),
but a real waste: it burns real model calls and attempts to extract
"architecture" from content that has none. **Status: fixed.**

**Found live, not theorised:** dispatching a leaf agent (`cdp run --scope
root/.cursor`) against `$TARGET_REPO` -- first with haiku, then sonnet --
both calls failed, because `.claude/`/`.cursor/` in that repository are
checked-in AI-coding-assistant configuration (rule files, plan documents,
skill definitions), not source code. Haiku's two attempts were rejected by
the patch schema itself (an anchor under the 12-character floor, a
statement over the 500-character cap) -- the gate did its job, but the
underlying question ("what does this Cursor rule file's architecture look
like") should never have been asked.

**Root cause:** `cdp/inventory.py` builds from `git ls-files` (deliberately
-- its own docstring: this is what keeps a 372-file-on-disk/2-in-git
generated module from reporting as 372) with no dot-directory
special-casing at all. A `role` classifier already exists
(`classify_role`, `cdp/lang/__init__.py:78-90`) that would tag an ordinary
`.md` rule file as `docs`, but Cursor's own `.mdc` extension isn't matched
by `_DOC_PATTERN` (`md|rst|adoc|txt`) and falls through to `source` --
and, more fundamentally, `role` was never wired up as an actual filter
anywhere (`partition.py`/`prompts.py`/`schedule.py` only use it for
`by_role` reporting counts and a label in the leaf prompt). Nothing stopped
any tracked file, regardless of role, from being partitioned into a scope
and handed to a leaf.

**Fix, a denylist rather than a role-based redesign** (user's explicit
choice -- simpler, ships now, doesn't require redesigning how `role` is
used throughout the pipeline): `cdp/inventory.py`'s new
`DEFAULT_EXCLUDES` (`.claude`, `.cursor`, `.windsurf`, `.vscode`, `.idea`,
`.zed` -- not `.github`/`.gitlab`/`.circleci`, which keep their `ci` role
and real signal). `build_inventory(repo, extra_excludes=...)` drops any
path with a matching `/`-separated segment (segment-exact, not substring --
`.cursorstuff/` survives) before extraction/partitioning/scheduling ever
see it, and **records what it dropped rather than silently discarding it**
(`inventory["excluded"]`: patterns, count, full path list) -- this
project's standing rule against silent gaps.

**Made configurable, per the user's explicit request**, so this isn't a
one-target special case: `.cdp.toml` (`cdp/store/registry.py`'s existing
team-config file, "checked into the repo, for a team") gains an `exclude`
array, read by new `team_excludes()`; `cdp scan` gains a repeatable
`--exclude` flag for one-off additions. Both are strictly additive on top
of `DEFAULT_EXCLUDES`, never a replacement -- a team extending the list
can't accidentally un-exclude the defaults.

**Verified, not assumed:** `tests/test_inventory_excludes.py` (6 tests:
defaults excluded and recorded, segment-exact matching, nested occurrences,
`.cdp.toml`/`--exclude` both additive). Real-scale, `$TARGET_REPO`: an
independent count (`git ls-files | grep -E '(^|/)\.(claude|cursor|...)/'`)
gave 42 tracked files under those directories; the tool's own
`inventory["excluded"]["count"]` matched exactly, and no `.claude`/`.cursor`
scope remained in `cdp status`. Golden re-blessed on **both** the fixture
and the target -- not because file selection changed on the fixture (it has
no `.claude`/`.cursor` content), but because `inventory.json` gained a new
`excluded` key for every scan regardless of whether anything matched,
changing the JSON shape everywhere. Inspected the diff before blessing
either baseline: fixture's was exactly `excluded: {count: 0, ...}` and
nothing else; target's was 4,728 -> 4,686 tracked files (42 fewer, matching
the independent count) and `root/.claude`/`root/.cursor` gone from the
incomplete-scopes list, nothing else. `make check TARGET_REPO=...` green
after (determinism, fold, golden -- fixture and target).

---

## F16 — silent `--repo` defaulting produced a misleading all-anchors-failed signature

**Severity:** medium -- no wrong claim was ever accepted (the schema/anchor
gates caught it), but the failure it caused is actively misleading: it looks
exactly like a bad leaf run, not like an operator/tooling mistake, and costs
a real model call to discover. **Status: fixed.**

**Found live, immediately after F15:** running `cdp run --scope
root/client-java/client-core --runner-cmd "...sonnet $TARGET_REPO"
--state-dir /tmp/cov_run --timeout 240` (no `--repo`) against a state dir
scanned from `$TARGET_REPO`, from this tool's own repo as cwd: all 16
claims came back `anchor_not_found`. Traced before assuming the model was at
fault: `--repo` silently defaults to cwd (`_paths()`, `cli.py:319-334`),
which here was this tool's own repo, not the target -- so anchor
verification ran against completely unrelated file content. The claims
themselves were fine (confirmed: re-running with `--repo
$TARGET_REPO` explicitly, the same scope validated cleanly, 1,877 claims
kept, 0 demoted).

**Fix.** New `_check_repo_matches_manifest(paths, manifest)`
(`cdp/cli.py`): compares the current invocation's resolved `--repo` against
`manifest["repo"]`, the resolved path `cmd_scan` already records there --
no schema change, no new field, **no golden re-blessing** (a runtime
cross-check of two already-recorded values, nothing new to serialize).
Raises `CdpError` naming both paths if they differ; a state with nothing
recorded yet (or `--repo` matching, or omitted and happening to match cwd)
is untouched. Called in the five commands that read `--repo`'s file content
to verify or build an anchor: `cmd_run`, `cmd_collect`, `cmd_fold`,
`cmd_refresh`, `cmd_answer`. Not `cmd_scan` -- it is the writer of the
record, and re-scanning a `--state-dir` at a new repo on purpose is
legitimate.

**Second, an optional-flag warning in the same command.** `_build_runner`
silently returns a `FileRunner` (waits for a human/external process to drop
the patch file -- a legitimate mode, M5.1's own protocol) whenever
`--runner-cmd` is omitted, with nothing printed to say so -- indistinguishable
from `cdp run` simply hanging. `cmd_run` now prints one line when this
happens; a warning, not a `CdpError`, since the fallback is often exactly
what's wanted.

**Verified:** `tests/test_repo_guard.py` (9 tests) -- each of the five
commands raises on a mismatched `--repo` (message names both paths); none
raise when `--repo` matches or nothing is recorded yet; the runner-fallback
line appears only when `--runner-cmd` is omitted. Real-scale: reproduced
the exact original failure (`cdp run` from this tool's repo, no `--repo`,
against a `$TARGET_REPO`-scanned state) -- now fails immediately with the
new error, no leaf call spent. `make check TARGET_REPO=...` green against
the *existing* blessed baseline, confirming nothing serialized changed.

---

## M6.3 — Digest-first leaves (4.2), scoped down to prompts.py + schema only

**Status:** shipped behind `--digest`, fixture- and real-target-verified. **Not
done this session:** re-running `doctor` and the M6.2 benchmark in both modes
(M6.2 itself is not built yet — that acceptance criterion cannot be met until
it is), and the `runner.py`/`store/` pieces the plan's "Modules touched" list
names (escalation signalling at the runner layer, tier columns on `tasks`).
Recorded here rather than silently dropped, per the plan's own out-of-scope
discipline.

**What shipped.** `cdp prompts --digest`: `prompts.py`'s `build_prompt` gains
`digest_mode`/`repo_root`. In digest mode, a leaf's prompt inlines the full,
line-numbered text of every in-scope file (capped at
`MAX_DIGEST_CHARS_PER_FILE` = 6000 chars/file, truncation stated in-prompt,
never silent) instead of instructing the leaf to `Read` them; the leaf's tools
are unchanged (still `Read,Grep,Glob,Write`), so reading a file directly is
still possible and is now framed as an explicit **escalation** the leaf
self-reports via a new optional `claim.escalated` boolean (schema addition,
`schema/patch-1.0.0.json` and its `.claude/skills/cdp/` copy, kept in sync by
hand — no symlink exists between them). `digest_fingerprint` (sha256 of the
concatenated digest text) is recorded in `cdp prompts`' stats and printed in
the prompt itself, so two runs' inputs can be compared without diffing the
whole prompt.

**Escalation rate**, the plan's named new metric: `cli._escalation_rate`,
fraction of claims across an accepted batch with `escalated: true`. Returns
`None` (not `0.0`) when the batch has no claims at all, so "nothing escalated"
is never confused with "the question doesn't apply." Printed by `cdp collect`
and stored in the `verify` report. **Known gap:** the rate is computed over
whatever batch `cdp collect` sees regardless of whether that batch was
produced in digest mode — a non-digest run's claims simply never set
`escalated`, so its rate prints as `0.000` rather than the more honest `None`.
Not fixed this session; `cmd_collect` would need to know which mode produced
the batch, which the patch schema does not currently carry.

**Anchors are not references into the digest.** The plan's stated determinism
win ("fabrication structurally impossible rather than merely detectable") is
NOT delivered by this slice — anchors are still model-typed strings verified
by re-opening the real file (`verify.py`, unchanged). Making anchors digest-
relative would mean the verifier resolves against the digest's line numbers
instead of the live file, which is a real redesign of `verify.py`/`anchor.py`
this session's budget did not include. Recorded as the gap between what M6.3
claims and what shipped.

**Verified, not assumed:** `tests/test_digest.py` (6 tests) — default mode
unchanged (no digest section, byte-identical prompt shape to before), digest
mode inlines real file text and a deterministic fingerprint, `_escalation_rate`
pure-function cases, and an end-to-end CLI run (`cdp scan` + `cdp prompts
--digest` on the fixture) confirming the flag actually reaches `build_prompt`
and the written `.md` file carries a `## Digest` section. `python3 -m
unittest test_digest test_schema test_pipeline` green (35+6 tests).

**Real-target exercise (R-E7), not fixture-only:** `cdp prompts --digest`
against a full scan of `$TARGET_REPO` (170 scopes, 5.7s scan — F6's fix still
holds) measured digest at 3219 chars/leaf average across the whole repo, but
a single real scope (`root/sql-pool/sql-pool-smoketest`, 12 files) showed
digest as the *dominant* section (38,916 chars, `structure` 4,974) with one
real truncation firing and stating itself in-prompt — the repo-wide average
being small is an artifact of many near-empty scaffolding/config scopes
dragging the mean down, not the mechanism failing to include real content.
**Caught live, fixed before the freeze (F17):** the first attempt (no `--repo`
flag) silently defaulted `--repo` to this tool's own cwd -- the exact F16
failure class, in a spot F16's own five-command guard list did not cover,
because `cmd_prompts` had no prior reason to read `--repo`'s file content and
digest mode gives it one. Every in-scope digest came back empty (`OSError`
caught and swallowed to `""`) until `--repo` was passed explicitly -- silent,
plausible-looking, wrong. Fixed in the same session, before declaring the
milestone frozen (the fixture-correctness freeze had not yet been declared
when this was found): `_digest_section` now raises `CdpError` on a missing
`repo_root` or an unreadable path instead of degrading, and `cmd_prompts`
calls `_check_repo_matches_manifest` when `--digest` is set, extending F16's
guard to a sixth call site. Regression test:
`test_digest_mode_refuses_a_mismatched_repo`. This is the one point in this
session's work where a live exercise fed back into the frozen code, which is
why the freeze declaration below is the second one, not the first.

---

## Phase 6, M6.4 only — tiering v1, exercised on this target and with one real T2/T3 sample

User explicitly scoped this session to M6.4 after M6.2 (graded benchmark) was
flagged as incompatible with the session budget (25-40 questions, an
independent judge, dozens of live model calls — `phase_6_plan.md`'s own
estimate, confirmed against this session's ~20-minute ceiling before any code
was written). M6.2 remains not started.

**What shipped.** `cdp/tiering.py` (new): the plan's literal v1 rule —
everything is T2; a scope escalates to T3 only when it has an unresolved
import (pre-dispatch, free — `scope_unresolved_imports` reuses
`graph.build_symbol_index`/`owners_of`/`_looks_third_party`, scoped to one
scope's own files rather than the whole repository) or its T2 leaf's own
claims self-report `escalated: true` (post-dispatch, M6.3's existing flag).
Wired into `prompts.py` (`build_prompt` gained an optional `symbol_index`
param, computes `stats["tiering"]` when given one) and `cli.py`: `cmd_prompts`
builds the symbol index once (not per scope — quadratic otherwise), writes
`reports/tiering.json`, and prints the T3 rate; `cmd_collect` reads that
report back, applies `leaf_escalated` upgrades from the batch's accepted
patches, and reports which scopes were upgraded. `tiering` added to
`store.REPORTS` (present, `{}`, on any scan that never ran `prompts`, same
convention `unknown_gates` already established).

**D — tiering is computed only at `cdp prompts` time, not inside `cdp
run`/`cdp doctor`'s own internal `build_prompt` calls.** `grep -n
"build_prompt("` found three other call sites (`supervisor.py`, `doctor.py`,
plus the new `tests/test_digest.py`); none pass `symbol_index`, so none gets
a `tiering` stats key. This is the same posture `TARGET.md`'s M6.3 entry
already recorded for `runner.py` escalation signalling — v1 threads the
signal only into the surface where a human currently decides what to
dispatch (`cdp prompts`), not into the two automated dispatch loops, which
is a real, stated gap rather than a silent one.

**Exercised on a real module first (R-E7), which found a real confound in
the rule's own inputs.** A scratch scan of `$TARGET_REPO/sql-pool/sql-pool-api`
alone (one module) reported **2/2 scopes T3**, both for `unresolved_imports`
— read literally, this looked like the stress-test's feared "T3 escalation
fires everywhere" outcome. Inspecting the actual unresolved fqns showed it
was not the rule collapsing: scanning one module in isolation makes every
real *inter-module* import (`rms.unifiedstore.sqlpool.common.*`, a real
sibling module never in this scan's `module_set`) look unresolved, and
`org.mapstruct.*`/`com.rms.auth.framework.*` — real third-party/internal-org
packages — are not recognised by `graph._looks_third_party`'s hardcoded
list. Re-run as a **full scan of `$TARGET_REPO`** (170 scopes, 5.8s scan,
2.8s prompts build, all modules present so cross-module imports resolve):
**117/170 scopes (69%) T3**, all `unresolved_imports`. Still a real majority,
but not "everywhere," and not an artifact of scan scope — this is the honest
number the stress test asked for.

**One real T2/T3 sample, on a real scope, live model calls, not simulated.**
Per the plan's M6.4 acceptance line, one T2 scope (`root/automation`, 2
files, 40 LOC — the smallest T2 scope in the full-target run) was run
through the actual `scripts/claude_leaf_runner.sh` twice: once against `cdp
prompts --digest`'s output (T2 shape), once against the same scope's default
non-digest prompt (T3 shape — full source, no digest section). **Same model
(haiku) both times, deliberately** — the plan's own T2/T3 distinction bundles
input mode with model tier, but isolating input mode alone is the cleaner
measurement of "how much of this scope can Python already explain by
itself," which is exactly what the deferred residue score (§N) needs signal
on; a model-tier swap would confound the two.

```
T2 (digest, haiku)       5 claims, 3 unknowns
T3 (source-read, haiku)  3 claims, 2 unknowns
```

**The direction is the opposite of what the residue-score intuition
predicts, on this one scope: T2 found *more*, not fewer, claims.** Recorded
rather than smoothed over. n=1, same model both arms, and this is exactly
the kind of small/config-heavy scope where a fully-inlined digest (this
scope's digest holds its *entire* 40-LOC content) can plausibly out-perform
a source-read leaf that has to choose what to open — the opposite of a
large scope where digest truncation would bite. Not generalised past this
one pair; this is the labelled sample the plan asks M6.4 to produce as a
by-product, not a result about tiering's correctness. Anchors in both
patches were not independently re-verified against the live file this
session (budget); `cdp collect` was not run against either patch, so neither
went through real anchor verification.

**Not delivered this session, stated rather than dropped:** the T2/T3
sample is a single pair, not "a sample of scopes" (plural) the plan's
acceptance line names — collecting more pairs needs the same per-scope
live-model cost repeated, which is M6.2-shaped budget, not M6.4-shaped.
M6.2 itself (the graded benchmark) was not attempted. `runner.py`
escalation *signalling* (as opposed to the self-reported `escalated` flag
M6.3 already emits) is still not built.

**Verified:** `tests/test_tiering.py` (new, 10 tests, fixture-only — every
`scope_unresolved_imports`/`compute_tier`/`apply_leaf_escalation` branch,
including the "existing T3 reason is not overwritten" case). `python3 -m
unittest tests.test_tiering` and `cd tests && python3 -m unittest
test_pipeline` both green (10 and 24 tests respectively — the two existing,
unrelated cwd conventions this repository's test files already use;
`tests/test_digest.py` fails under both from a pre-existing `helpers` import
gap unrelated to this session's change, left as found). `make check
TARGET_REPO=...` is the full-target confirmation (see below).

---

## Phase 6, M6.2 — design only, execution deferred (budget)

User scoped this session to design-only after the M6.2 acceptance criteria
(25–40 questions, two model arms, an independent judge, a crossover sweep)
were sized at dozens of live model calls — structurally past a 20-minute/
60k-token session, and already deferred twice before for the same reason
(`PHASE/TARGET.md` M6.3/M6.4 entries). No code written this session.

Full design at `PHASE/M6_2_BENCHMARK_DESIGN.md`: question schema, 6 grounded
starter questions reusing facts already human-verified by prior sessions
(F2, F5, T1, T2, and two Phase-3 real-history exercises) rather than newly
fabricated, the judge/reader-model-separation and expected-failure-question
stress tests carried over verbatim from `RESEARCH_GRAPHIFY.md §7.2`, the four
reported numbers' exact definitions, and the crossover-sweep methodology.

**Gap surfaced by writing the question set concretely, not left implicit:**
zero `table`-category gold facts exist yet — no session has human-verified a
fact about `$TARGET_REPO`'s 497 SQL files/669k LOC. That category is fully
unfilled and is called out in the design doc's own caveats section as a
precondition for execution, not something to paper over with a weaker
question at run time.

---

## Phase 6, M6.2 — graded benchmark, executed (superseding the "design only, deferred" entry above)

User asked for full execution after the design-only pass. Full account,
numbers, and caveats are in `BENCHMARKS.md`; this entry is the process
record. `benchmarks/run_benchmark.py` (new, out of core per the plan's
"Modules touched" note) drives a real out-of-session harness: `claude -p`,
haiku reader / sonnet judge, two arms (`Read,Grep,Glob` vs. `+Bash` scoped to
`cdp.cli`), 25 real questions against a real scratch scan of `$TARGET_REPO`.

**F18 — the first full run's `--allowedTools` pattern silently denied every
compound `cd ... && cdp.cli ...` Bash call, making the "cdp" arm behave like
the baseline arm.** `--allowedTools "Bash(python3 -m cdp.cli *)"` is a
leading-literal match; the model always wrote `cd
/Users/sharmp49/hackathon/code_scanner && python3 -m cdp.cli ...`, which
never matches. Caught by reading `permission_denials` in the raw run output,
not assumed. Fixed to `Bash(*cdp.cli*)` (substring match), verified live with
a direct smoke test first, then **the entire cdp arm was re-run and
re-judged** rather than patched over — coverage moved 0.828 → 0.838, a small
but real change, meaning the pre-fix numbers were close by luck, not by
correctness. Pre-fix artifact kept at `benchmarks/results/run_v1_broken_cdp_arm.json`
rather than deleted, so the before/after is auditable.

**Real result, not assumed:** coverage baseline 0.765 → cdp 0.838 (+7.3
points), concentrated in `trace` (0.50→0.90) and `config` (0.56→0.81) —
cross-file aggregate questions — while `table` (single-file lookups) hit a
1.00 ceiling on both arms and `paths` moved the wrong direction (0.44 vs
0.50, n=4, not investigated further this session).

**A design flaw in the benchmark's own expected-failure question (`q25`)
found by inspecting its judged verdicts, not assumed correct:** one of its
two gold facts is a meta-statement about CDP's expected limitation, not a
codebase fact, so it cannot be meaningfully "covered" by either arm's answer.
Flagged in `BENCHMARKS.md`'s caveats rather than silently kept in the
aggregate coverage number's interpretation.

**Crossover, `scan`+`query` path, real measurements:** 44 files → 0.29s, 477
files → 0.83s, 4,686 files (full target) → 5.36s scan wall time — all
cheaper than one reader-arm model call (avg 19-24s in this run), so the
`scan`+`query` crossover is effectively immediate, as the plan predicted
("scan is free ... CDP's crossover is lower than the peer's ~50 files"). The
pyramid's crossover was **not** measured live this session (needs a
per-scope leaf-dispatch cost sweep, separate budget) — recorded as a gap,
not silently substituted with the scan+query number.

**Not done, stated rather than silently dropped (see `BENCHMARKS.md`
Caveats for the full list):** n=25 is the low end of the plan's 25-40 range;
no second independent judge (Graphify's own 90.6%/κ=0.81 cross-check was not
reproduced); `trace` has only 2 questions against a 3-5 target; the pyramid
crossover sweep.

---

## Phase 7 (M7.6 only) — Postgres adapter, gated on a real multi-writer
requirement the user asserted this session

Scoped to M7.6 only (`PHASE/phase_7_plan.md`'s other five milestones — scope
selector, per-scope materialised state, `compact`, `verify --full`, `export`
— deferred to their own sessions; M7.1 explicitly picked as the next one).
The plan's own instruction is to gate this milestone on a real need rather
than build it speculatively; the user asserted that need exists, so it was
built rather than deferred.

**D32 — a real Postgres adapter breaks the zero-dependency distribution
model, surfaced before writing code, not after.** `pyproject.toml`'s
`dependencies = []` is stated as deliberate and load-bearing (F2's
resolution: this is why C#/Scala got hand-rolled extractors instead of
tree-sitter). `SqliteStore` needs only stdlib `sqlite3`; a Postgres client
needs `psycopg2`, a C extension linking `libpq` — no way around that.
Resolved as an optional extra: `pyproject.toml` gained
`[project.optional-dependencies] postgres = ["psycopg2-binary"]`, and
`cdp/store/postgres_backend.py` imports `psycopg2` lazily inside
`PostgresStore.__init__`, not at module scope. Verified live:
`python3 -c "import cdp.store"` succeeds with no `psycopg2` importable
anywhere on the path — the base install is untouched.

**Verified against a real, live Postgres server, not mocked.** No
`psycopg2`/`psql`/`docker` exists in the execution sandbox; the user pointed
at an already-running local Postgres (port 5432, `dbname=postgres
user=postgres host=localhost`, trust auth). `psycopg2-binary` installed
clean. `PostgresStoreConformance` (new, `tests/test_store_conformance.py`,
skipped via `unittest.skipUnless` unless `CDP_TEST_POSTGRES_DSN` is set — the
same opt-in convention `TARGET_REPO` already uses, so `make check` stays
hermetic for anyone without a Postgres server) reuses the exact
`ConformanceMixin` `FileStoreConformance`/`SqliteStoreConformance` already
pass: **all 17 assertions green against the real server**, isolated per test
by creating and dropping a dedicated Postgres *schema* per store (the
per-file-per-store isolation `SqliteStore`'s fresh `index.db` gets, ported to
"one schema, shared server" instead of "one file").

**A real defect the live exercise found, not the conformance suite (which
never opens two connections at once): every read-only method left its
transaction open (`idle in transaction`), which silently blocks DDL against
the whole schema — the actual failure mode a shared multi-writer store must
not have.** `psycopg2` connections default to `autocommit=False`, so a bare
`SELECT` with no following `commit()`/`rollback()` never ends its
transaction. `load_patches`, `read_artifact`, `has_artifact`, `read_report`,
`mark_durable`, and `append_patch`'s early-return (already-deduped) path all
had this bug. Found concretely: a hand-written two-writer exercise (two
independent `PostgresStore` connections to one schema, each appending a
different patch, a third fresh connection confirming both are visible) hung
indefinitely on cleanup; `pg_stat_activity` named the exact blocked session —
`idle in transaction` holding `SELECT payload FROM claim_patch ...` — and the
exact blocked statement, `DROP SCHEMA ... CASCADE`. Fixed by committing after
every read. Re-ran both the conformance suite (51/51, unchanged) and the
two-writer exercise clean afterward: two independent connections write
concurrently, a third fresh connection sees both patches immediately — real
MVCC, not asserted.

**Scope of what "the adapter" means here, stated explicitly.** Only the
`WorkspaceStore` interface is ported — `read/write_artifact`, `read/
write_report`, `load_patches`, `append_patch`, `write_derived_patch`,
`ensure/read/clear_inbox`, `begin_snapshot`, `mark_durable` — because that
interface, proven by the conformance suite, is the milestone's own stated
acceptance criterion. `SqliteStore`'s runs/tasks/leases tables (M2.5/M5.2/
M5.4: `snapshot_run`, `snapshot_task`, lease columns) are dispatch-loop
bookkeeping for the single-writer CLI supervisor (`cdp run`), not part of
`WorkspaceStore`, and are not ported. Owner: whichever future phase wires
`cdp run`'s supervisor to run against a shared team store, if that ever
becomes a real requirement — not invented speculatively here, same posture
this milestone's own plan text takes toward the whole adapter.

**Not done, explicitly, in the M7.6 session above:** no CLI wiring — closed
in the follow-up below, in the same session the user asked "no store should
be hardcoded."

---

## Follow-up — real backend selection: sqlite (default) / file / postgres,
none hardcoded

The M7.6 session above shipped `PostgresStore` but explicitly deferred CLI
wiring, following D3's precedent for `SqliteStore`. Asked directly to audit
that: `_open_store()` (`cli.py`) was hardcoded to `SqliteStore` at every one
of ~12 call sites; `grep -rn "FileStore("` in `cli.py` returned zero hits —
`FileStore` has been fully conformant since Phase 2 (D3) but never
constructed by the CLI. `cdp run`/`cdp gc` additionally called 18
`SqliteStore`-only methods (`begin_run`, `upsert_task`, `acquire_lease`,
`list_snapshots`, etc.) unconditionally, undeclared on `WorkspaceStore` and
not even stubbed on `FileStore` — selecting a non-sqlite backend for those
two commands would have `AttributeError`'d deep in `supervisor.py`, not
raised a clear error.

**Design forks surfaced before implementing, not after (R-E13):**

- **D33 — backend selection lives in `.cdp.toml`, not a CLI flag or env
  var**, per explicit choice: `backend = "sqlite"|"file"|"postgres"` plus an
  optional `[postgres]` table (`dsn`, `schema`). `registry.py` gained
  `team_backend`/`team_postgres_config`, same style as the existing
  `team_store`/`team_excludes`. No writer added — `.cdp.toml` stays
  human-authored (existing, deliberate policy).
- **D34 — `WorkspaceStore` gains the 18 methods as non-abstract, split
  read/write.** Read-side (`list_snapshots`, `get_run`, `task_states`,
  `task_rows`, `snapshot_id`, `use_latest_snapshot`) default to an honest
  empty answer, matching the precedent `task_states`' own docstring already
  set. Write-side (`begin_run`, `upsert_task`, `acquire_lease`, etc.) default
  to raising a `CdpError` naming the missing capability. One exception:
  `copy_patches_from` defaults to a no-op, not a raise — it's only invoked
  when a fresh snapshot's log is empty, which can't happen on a
  single-snapshot backend, so raising would break `cdp refresh` against
  `FileStore`, which otherwise works fine. `SqliteStore` needed no changes;
  `FileStore` needed none either — it inherits the defaults, which is the
  whole design.
- **D35 — chose to extend `WorkspaceStore` and port run/task/lease/retention
  to `PostgresStore` too**, not just refuse on it (the other option offered).
  Ported from `SqliteStore`'s `SCHEMA_V2`-`V5` in one additive migration (no
  Postgres store has shipped yet, so no earlier version to stage through):
  `snapshot_run`, `snapshot_task` (+ `wall_ms`), `pinned`/`touch_seq` on
  `snapshot_meta`. `link_run`/`link_task` (Phase 8) deliberately not ported.

**A real concurrency defect the live exercise found, not the conformance
suite (single-connection tests can't see it): concurrent first-time schema
creation raced on Postgres's own catalog.** 20 threads constructing
`PostgresStore` against a not-yet-existing schema simultaneously threw
`UniqueViolation` on `pg_type` — `CREATE SCHEMA/TABLE IF NOT EXISTS` is not
safe under true concurrency without an explicit lock. Fixed with a
session-level `pg_advisory_lock(hashtext(schema))` held only around
first-time setup (schema creation + migration), released immediately after —
costs nothing once the schema exists. Re-ran the same 20-thread race after
the fix: all 20 succeed, exactly one wins the lease.

**A UX defect the live exercise found: `cdp gc` against `FileStore` gave a
wrong, confusing error.** Because `list_snapshots()`'s honest-empty default
returns `[]`, `gc`'s "does HEAD have a snapshot" check failed *before* ever
reaching a write-side method, producing "no snapshot for HEAD — run `cdp
scan` first" — wrong, since a scan had run; the backend just doesn't track
snapshots. Fixed with a new `WorkspaceStore.supports_run_tracking() -> bool`
(`False` default, `True` on Sqlite/Postgres), checked up front by both
`cmd_run` and `cmd_gc` so the real refusal reason is always what's reported.

**Verified live, not assumed:**
- Full run/task/lease/retention flow (`begin_run`/`get_run`/`acquire_lease`/
  `release_lease`/`upsert_task`/`reclaim_expired`/`copy_folded_tasks`/
  `list_snapshots`/`set_pinned`/`use_latest_snapshot`/`copy_patches_from`)
  exercised directly against the real Postgres server before writing formal
  tests — every call behaved as designed.
- `RunTaskLeaseMixin` (new, `tests/test_store_conformance.py`, ported from
  `test_store_sqlite.py`'s `TestSnapshotLineage`/`TestRetention`/
  `TestRunsAndTasks`) parameterized over `SqliteStoreConformance` and
  `PostgresStoreConformance`: both pass identically (72 conformance tests
  total, up from 51). `FileStoreRefusesRunTracking` (new) proves the
  write-side raises and read-side stays honest on `FileStore`.
- `tests/test_registry.py` (new — none existed before): `team_backend`/
  `team_postgres_config` parsing.
- **Real cross-backend exercise on `$TARGET_REPO`** (a detached worktree of
  `sql-pool/sql-pool-api`, per `PHASE/EXECUTION_RULES.md` R-E7): the same
  real module scanned three times, once per backend (`.cdp.toml` switching
  between them), `cdp query stats` output byte-identical across all three —
  same claims, symbols, routes, confidence. The Postgres-backend scratch
  directory held only `docs/`/`patches/inbox/` — no `index.db`, no artifact
  JSON — confirming the data genuinely lives in Postgres, not the local
  filesystem. `cdp gc --dry-run` and `cdp run` against that same module:
  sqlite and postgres both dispatch identically through the real supervisor
  (reaching the same "abandoned after 3 attempts" state via a schema
  hiccup in the synthetic test runner, identically on both backends — proof
  the dispatch loop and lease/task tracking run the same real code path
  against Postgres as against Sqlite); `file` refuses both `gc` and `run`
  with the new clear error. Worktree removed after the exercise; main
  checkout's `git status --porcelain` was empty before and after.

**Not done, explicitly:** `cdp run`'s supervisor was proven to *dispatch*
correctly against Postgres (leases/task-state transitions all fired for
real), but no run completed to a *folded* claim end-to-end this session —
the synthetic runner script used for the live exercise didn't emit a
schema-valid patch (a test-script gap, not a product one; both backends
failed identically at the same point). `VACUUM`/connection pooling/
retry-on-serialization-failure for real sustained concurrent load remains
unexercised beyond the 20-thread race above.

---

## Phase 7 (M7.1) — design session, no code; M7.2 explicitly deferred

M7.1's acceptance criterion ("`query --scope`/`refresh --scope` touch only
that subtree, provable by instrumenting store reads") presupposes M7.2's
per-scope storage, which doesn't exist yet — surfaced before writing any
code (R-E13). `run --scope` already ships (`cli.py:201`, `1305-1308`) but
only as an in-memory filter over an already-fully-loaded `store.partition`;
it does not satisfy the read-instrumentation bar either, and was already
merged before this gap was noticed.

**D36 — reject M7.2 as literally written (physically chunked per-scope
storage files).** Discussed and rejected in favor of a lighter alternative,
not yet built:

- Every artifact that is currently one opaque JSON blob per snapshot
  (`inventory`, `partition`, `xref`, `graph`; `snapshot_artifact` table,
  `sqlite_backend.py:63-68`) would gain a `node` column and index, the same
  treatment `claim_patch` already has (`node` extracted via
  `json_extract(payload, '$.node')`, indexed at `sqlite_backend.py:91`).
  Scoped queries become `WHERE node LIKE ?` over one table — no chunk
  files, no compose-and-hope-it-equals-a-full-recompute step, no new write
  path.
- `state` stops being pre-folded and stored whole; `fold`/`check_fold`
  (`state.py:51`, `state.py:287`) get called with a scope filter instead.
- Genuinely global facts (`coverage` fraction, `contested` in
  `merge.py:169-188`) stay global, computed as an incrementally-updated
  running summary rather than a from-scratch walk on every query, audited
  periodically by the existing `check_fold`/future `verify --full`
  machinery rather than trusted blindly.
- The acceptance test becomes a real read-counter (wrap backend reads,
  assert a scoped query never touches a row outside its `node` prefix) —
  replacing the vaguer "byte for byte" chunk-composition test the plan
  proposed.

**Why deferred rather than built this session:** this is still a real
schema/query-path change across `state.py`, `query.py`, and every
`snapshot_artifact` writer — not a quick add-on — and the user chose to
table it explicitly rather than execute mid-design-discussion. Recorded
here so the next session picks up D36's shape rather than re-deriving it.

**Not done:** no code changed this session. `query --scope`, `refresh
--scope`, and scoped-coverage labelling (M7.1's own acceptance items) are
still open, and are now understood to depend on D36 landing first — M7.1
and M7.2 are not actually separable the way the plan assumed.

---

## Phase 7, M7.3 only — `cdp compact`, exercised on a real scratch scan

Scoped to M7.3 only this session, per explicit instruction (M7.1/M7.2 left
for later, as recorded above). The cold table itself (`claim_patches_archive`,
`(scope_hash, run_id)` index) already existed — created in Phase 2 as a
precondition, unused until now.

**What shipped.** `WorkspaceStore.supports_compaction()` (default `False`,
same posture as `supports_run_tracking`) and `SqliteStore.compact
(keep_generations=1, threshold=0.30, dry_run=False)`. Whole-store, not
scoped to the currently-selected snapshot: generations accumulate per
`(snapshot_id, node)` across every re-run of a node on one commit, so this
is a maintenance pass over the whole DB file, mirroring `cdp gc`'s own
`--db` escape hatch (`cli.py cmd_gc`). Only `complete` patches are
generations at all — the same definition `state.fold`'s `best_complete`
already uses (`state.py:144-156`), reused verbatim for the keep/archive
sort so the row kept hot is provably the same row `state.fold` already
treats as live. `cdp compact --db <path> --compact-threshold F
--keep-generations N [--dry-run]`.

**D37 — `--compact-threshold` gates whether `compact` acts at all, not just
how much it archives.** The plan states the default (30%) and that it is
"customisable" but not what it does. Read literally against `CDP_CLI_SCOPE.md`
0.16's stated cost concern (someone treating `--keep-generations` as data
loss) and the plan's own acceptance line (5 generations, moves 4), the
natural reading is: below `threshold`, `compact` is a no-op that reports the
observed ratio and moves nothing — so running it on an already-lean store
costs a report, not a `VACUUM`. Recorded per R-E13 rather than defended only
after the fact.

**D38 — the archive's `scope_hash` column is populated from that snapshot's
own `partition` artifact, not carried on the patch.** A patch only ever
carries `node` (`schema/patch-1.0.0.json`); `claim_patches_archive`'s index
is `(scope_hash, run_id)` per the plan (`CDP_CLI_SCOPE.md` 0.16). `compact`
resolves `node -> scope_hash` per snapshot via `snapshot_artifact`'s stored
`partition` payload, falling back to the node string itself if the
partition is missing — never blocking the move on a missing index value.

**Verified, not assumed.** `tests/test_store_sqlite.py::TestCompaction` (6
new tests, fixture-scale): below-threshold no-op, 5-generations-keep-1-move-4,
archived rows never deleted (only relocated — R5), `--dry-run` moves
nothing, the kept generation is the correct (highest) one, and a `pending`
patch is never treated as a generation. **Exercised on a real scratch scan**
of `$TARGET_REPO/sql-pool/sql-pool-api`: three synthetic `complete` patches
appended to the same real node (`root/(files+2)`) via three separate `cdp
collect` calls, so the node carried four real generations end to end
through the actual CLI (the original scan's generation-1 patch plus three
more). `cdp compact --db <path>` moved exactly 2 (of the 3 synthetic
generations superseding the original), kept 1, and both archived rows'
`scope_hash` matched the real scope's actual content hash from
`partition.json` (not the node-string fallback) — confirmed by reading the
archive table back directly, not trusting the summary line. `cdp query
stats`/`cdp fold --check` ran against the post-compaction store afterward
without crashing.

**Found, not a defect: `fold --check`'s hash is expected to diverge after a
real compaction, and that is exactly the gap M7.4 exists to close.**
`fold_hash` (`state.py:227-243`) hashes the literal patch list passed to it,
not the derived claims — so once `compact` relocates superseded rows out of
`claim_patch`, a `fold --check` that reads only the hot table sees a
different raw patch set than `state.json` was last computed from, and
fails with "the log has changed since state.json was written" even though
the *derived* claims are unaffected (`best_complete` never selected an
archived row in the first place). This is the literal problem statement
`CDP_CLI_SCOPE.md` 2.5 names for `cdp verify --full`: re-fold from
archive-plus-hot and compare to the live hash, which `fold --check` alone
cannot do post-compaction. Not fixed here — M7.4's own milestone — but
recorded as confirmed behavior rather than left as a surprise for whoever
picks up M7.4.

**Scratch scan removed after the exercise.** `make check
TARGET_REPO=/Users/sharmp49/git/code_scanner`, launched after freeze: **all
gates green** (459 tests, determinism fixture+target, `fold --check`
fixture+target, golden fixture+target byte-identical, no re-bless needed)
— the confirmation that adding `compact` changed nothing about the existing
`scan`/`fold`/`golden` pipeline, since no command on that path calls it.

**Not done, named rather than silently skipped:** `--compact-threshold`'s
gating semantics (D37) is a reading, not a spec quote — worth confirming if
a future session finds it surprising. Postgres has no
`claim_patches_archive` table yet; `supports_compaction()` defaults `False`
there via the base class, so `cdp compact --db <postgres-dsn>` fails with a
named capability error rather than silently no-opping — deferred to
whichever session gives Postgres real multi-writer traffic that needs it
(the same gate M7.6 already applies to the adapter as a whole).

## Phase 7, M7.4 only — `cdp verify --full`, exercised on a real scratch scan

Scoped to M7.4 only this session, per explicit instruction. Picks up exactly
where M7.3 left off: `fold_hash` diverging after a real compaction is not a
regression, it is the gap this milestone closes.

**What shipped.** `WorkspaceStore.load_patches_full(partition)` and
`.verify_archive_integrity(partition)`, both with a no-op base implementation
(`load_patches()` unchanged, `[]`) for backends with no archive (`FileStore`,
`PostgresStore` — mirroring `supports_compaction()`'s posture). `SqliteStore`
overrides both: `load_patches_full` unions the hot table with every archived
row whose `scope_hash` is one of the *current snapshot's own* scopes (read
from the `partition` argument — the same lookup `compact` itself used to
write that column, so filtering on it back out is the mirror operation, not
a new inference); with no partition given, every archived row is included
unfiltered (matches `compact`'s own node-string fallback when a snapshot's
partition artifact is absent). `state.check_fold` grew a `full: bool` kwarg:
`True` runs the archive integrity check first, then re-folds from
`load_patches_full` instead of `load_patches`. `cdp verify [--full]` is a new
top-level command — `fold --check` was not reused directly because the
plan's acceptance criteria name a `verify` command, not a `fold` flag, and
the two need different exit messaging (`state.json = fold(merge, patches/ +
archive/, xref.json)` vs. `patches/, xref.json`).

**D39 — a corrupted archive row is caught by a per-row content hash, not
only by the aggregate fold mismatch it would eventually cause.** The plan's
acceptance line ("corrupting one archived row makes it fail with the row
named") is not satisfiable by `check_fold`'s existing comparison alone: that
comparison only ever reports "claims not derivable" or "fold_hash mismatch"
at the whole-state level, naming no row. `SCHEMA_V6` adds a `content_hash`
column to `claim_patches_archive`, populated by `compact` at archive time
(`stable_hash(payload)`); `verify_archive_integrity` recomputes it per row
and reports `scope_hash`/`run_id`/`rowid` on mismatch. Pre-`SCHEMA_V6` rows
(none exist outside this session's own scratch/test runs) have a `NULL`
`content_hash` and are silently skipped rather than false-failing.

**Verified, not assumed.** `tests/test_store_sqlite.py::TestVerifyFull` (4
new tests, fixture-scale): `load_patches_full` recovers exactly the
pre-compaction patch count; a clean archive reports no problems; a
corrupted row is named by its `rowid`; an uncompacted store's `full` and
non-`full` reads are identical. **Exercised on a real scratch scan** of
`$TARGET_REPO/sql-pool/sql-pool-api`: three synthetic `complete` generations
appended to the real snapshot's real node, `cdp verify` (hot-only) `ok`
before compaction; `cdp compact --compact-threshold 0` moved 2; `cdp verify
--full` afterward reproduced the live state hash exactly (`ok` on both the
fold and the archive-integrity lines) — the concrete form of "provably
lossless rather than asserted." Directly tampering with one archived row's
payload (`UPDATE ... json_set(payload, '$.claims[0].claim', 'TAMPERED')`)
made the next `cdp verify --full` fail with that exact `rowid` named, plus
the expected downstream `fold_hash mismatch` — both lines, not one.
Scratch directory removed after the exercise.

**Not done, named rather than silently skipped:** the plan's stress test
"`verify --full` on a store compacted twice" (two-generation archives) was
not separately exercised this session — `load_patches_full`'s scope-hash
filter and `verify_archive_integrity`'s per-row check are both indifferent
to how many times a row has moved (they read `claim_patches_archive`
directly, not `compact`'s own accounting), so a second compaction pass is
expected to compose without a code change, but that expectation is
unverified rather than proven. Postgres still has no archive table
(D38/M7.6's own deferral), so `load_patches_full`/`verify_archive_integrity`
there are the inert base-class defaults — `cdp verify --full` against a
Postgres-backed store today just re-runs the hot-only fold, silently, since
nothing marks that fallback as degraded. Worth a named warning if Postgres
ever gains compaction.

---

## Phase 7, M7.5 only — `cdp export`, four formats, exercised on a real scratch scan

Scoped to M7.5 only this session (M7.1/M7.2 remain deferred per D36; M7.3/
M7.4/M7.6 already landed in prior sessions). `WorkspaceStore` gained
`dump_archive` (base: `CdpError`, same refusal shape as `compact`;
`SqliteStore` override reads `claim_patches_archive` raw) and `cdp/export.py`
implements the plan's four fixed shapes, wired to a new `cdp export
--format {json,patches,archive,anonymized} --out DIR [--db PATH]`.

**json** writes every artifact/report a source store has through
`FileStore`'s own interface, so the destination is a real `FileStore` root
afterward — R1's "files are an export format, not a storage format" made
literal, and provable: `canonical(src.read_artifact("state"))` equals
`canonical(FileStore(dest).read_artifact("state"))` after the round trip
(`tests/test_export.py`).

**Real bug found by this milestone's own real-target exercise, not the
fixture:** `WorkspaceStore.read_report`'s contract treats `default=None` as
"no default, raise if missing" (both backends), not "default value `None`" —
so the naive `store.read_report(name, default=None)` raised `CdpError` on
the *first* real scratch scan of `sql-pool/sql-pool-api`, because no
`collect` had run and several reports were genuinely absent. Fixed by
passing `default={}` (a real default, so the raise path never fires) and
still guarding with `except CdpError: continue` for backend variance. Caught
before the fixture tests were even written, by the R-E7 discipline of
exercising each milestone on real, non-fixture input as it is built rather
than only at the end.

**patches** dumps `load_patches()` as one pretty-printed file per patch,
named `NNNN-<node>.json` — reviewable by a human, never read back by CDP
(the same asymmetry `docs/` already has with the artifact store).

**archive** requires `supports_compaction()` (the same capability gate
`compact` uses) and calls the new `dump_archive`; refused with a named
missing-capability error against `FileStore` (`tests/test_export.py`
`test_archive_export_refused_on_a_backend_with_no_cold_table`), and against
the real target scratch scan (0 rows, since nothing had been compacted —
correctly *not* refused, since the sqlite backend does support the
capability, just has nothing archived yet).

**anonymized** replaces every field CDP's own schema/merge output uses for a
subject, a statement, a question, or a node/scope name — enumerated by field
name (`_TEXT_FIELDS`, `_TEXT_LIST_FIELDS`, `_NODE_FIELDS`,
`_NODE_LIST_FIELDS` in `cdp/export.py`) rather than inferred from content, so
an uncovered future field defaults to *kept*, a decision made explicit in
the module's own comment rather than left implicit. `evidence` (which quotes
source text verbatim) is dropped outright. **Two real leaks found and fixed
by the test itself, not anticipated up front:** the first pass covered
`subject`/`statement` only, per the patch schema — but `fold`'s own output
adds `source_nodes` (a list of scope names) that a first anonymized export
of a synthetic distinctive-symbol claim leaked verbatim (`"root"` found in
the corpus); and `unknown`'s free-text fields are actually named
`question`/`why_unresolved`, not `statement`. Both added to the field lists
after the test caught them, not asserted safe from reading the schema alone.

**Real-scale exercise (R-E7), on `sql-pool/sql-pool-api`:** all four formats
run against one real scratch scan (`/tmp/m75_scratch`, removed after). json:
11 artifacts/reports written and re-opened as a real `FileStore`. patches: 1
reviewable file (`0000-root.json`) for the module's one patch. anonymized:
41 claims / 1 unknown / 0 conflicts scrubbed; `grep -c "sql-pool-api"
corpus.json` → **0**, confirming the real repo path does not survive.
archive: 0 rows (nothing compacted on this scratch scan), exit 0 — the
correct answer, not a false refusal.

**Not built this session, stated rather than silently dropped:** the plan's
"conformance suite passes on it" line for the json export is proven by the
round-trip equality test above (`canonical` hash match), not by re-running
the full `test_store_conformance.py` suite against an exported directory as
a fifth backend fixture — that would need `FileStore` accepted into the
conformance harness's own backend list, which is a harness change, not an
export change, and out of this session's scope.

---

## Phase 8 (M8.1 only) — `cdp link scan`, and F-link1 found on a real pair of modules

Scoped to M8.1 only this session, by explicit user choice: the phase's
precondition ("at least two real repositories that genuinely talk to each
other") is unmet — `PHASE/TARGET.md` pins one `$TARGET_REPO`, not a pair —
and M8.2-M8.5 (unmatched-as-output beyond the basic case, the LLM tier,
refresh/query, the non-entanglement test) are each their own session's worth
of work. **Uncommitted Phase 6/7 work (M6.2-M6.4, M7.3-M7.6) found sitting in
the tree at the start of this session was committed first**, as its own
commit, so this phase's diff is clean.

**Design, given the precondition gap.** Two real *modules* of `$TARGET_REPO`
(`sql-pool/sql-pool-api`, `service-api`) stand in for "two repos" — real code,
real edges, just not two separate git remotes. `cdp link scan STATE_DIR...`
(`cdp/link.py`, new module; `cdp/cli.py` gains a `link` subcommand group with
`scan` as its only child, so `prompts`/`collect`/`refresh`/`query` can be
added under it later without a CLI reshape) reads N already-scanned state
directories' `dataflow.json`/`manifest.json` read-only — R3 holds by
construction, since no code path here opens a store for writing. Matching is
directional (`http_out`→`http_in`, `event_publish`→`event_subscribe`,
`persist`→`schema_own`) on a normalised path/table key; `match_kind` is
`exact` when the two edges' bare paths agree verbatim, `heuristic` when only
the param-normalised form agrees (`/orders/{id}` vs `/orders/:id`); an
outbound edge with no candidate anywhere becomes a named `unmatched` entry
(5.6), never a silent gap.

**`library:`-prefixed targets are excluded from matching, by design, not
oversight.** `dataflow.py` already excludes them from traversal for the same
reason (a package name is not a place data goes); this session confirmed why
that decision also binds here: `event_publish`/`event_subscribe` in this
codebase are produced *only* as `base.py`'s package-fallback edges
(`library:kafka`, `library:pika`, ...) — no extractor in this repository
emits a topic-specific event edge. Matching library targets would link import
statements, not services.

**F-link1 — the route-param regex also matched `table:`/`entity:`'s own
prefix separator, collapsing every distinct table name onto one key.**
Severity: high — it would have silently linked every `persist` edge to every
`schema_own` edge in scope. **Found live, on the real-module exercise below,
not by unit test first** (the unit tests as originally written all used
distinct short table names that happened not to trigger it): `cdp link scan`
against two real scans reported 82,519 links, `table:dbo` "matching"
`table:Address`, `table:Bridge`, `table:Lookup`, and dozens of others.
Root cause: `_ROUTE_PARAM_RE` (`:[A-Za-z_][A-Za-z0-9_]*`) is meant to collapse
a URL path param like `/orders/:id`, but `table:Address` also contains a
literal `:name` — the same character sequence, different meaning — so the
substitution stripped every table name down to the same `"table*"` key
regardless of which table it named. Fixed by only applying the param
substitution for `http_in`/`http_out` channels (`cdp/link.py` `_normalise`);
`persist`/`schema_own` compare on the bare `table:`/`entity:` token, unmodified.
Re-run after the fix: 2,697 exact matches (down from 82,519 fabricated ones),
0 heuristic, 1,396 unmatched — and a differential check confirms the drop is
exactly the fabricated cross-table matches, not real ones lost (0 cross-repo
matches exist between this specific pair either before or after, since
`sql-pool-api` and `service-api` don't share table names — see below).

**Separately, and *not* fixed here (real, pre-existing, out of Phase 8's
scope): `cdp/lang/data.py`'s `CREATE_TABLE_RE`/`INSERT_RE` capture only the
schema qualifier (`dbo`) for a bracketed, schema-qualified name
(`[dbo].[Address]`), not the table name itself.** This is why `table:dbo`
recurs as almost every SQL migration's `schema_own`/`persist` target in
`service-api` — a real extractor defect in Phase 1's data extractor, found
as a side effect of this session's real-module exercise, not a link-matching
bug. Flagged for its own owning session (data.py's regex, not link.py) rather
than fixed opportunistically here, per this project's own standard against
rider fixes on an unrelated milestone.

**Real-module exercise (R-E7), not fixture-only.** `sql-pool/sql-pool-api`
and `service-api` each scanned fresh into their own scratch state dir
(~5s each); `cdp link scan` run against both. Result, post-fix: 2,697 exact
`persist`↔`schema_own` matches, all **self-links** within each module's own
migrations (a module persisting to a table its own migration owns — the
5.7 stress test "a service calls itself... must not be filtered as noise",
demonstrated on real data), 1,396 unmatched persist/entity edges (e.g. EF
Core `DbSet<TenantRecord>` with no `schema_own` counterpart in either
scanned module — a real boundary of what's been mapped, per M8.2's own
framing), **0 cross-repo matches** between this specific pair. Scratch
directories removed after the exercise.

**M8.1's literal acceptance line ("exact matches on at least one route and
one topic") is not met, and cannot be with real target evidence today —
recorded honestly rather than worked around with a fixture pair.** No route
match is possible because the only extractor that emits a path-carrying
`http_out` target (`cdp/lang/web.py`, JS/TS) has no corresponding files
anywhere in `$TARGET_REPO` (Finding T1: C#/Java/SQL/Scala only); every other
language's `http_out` edges are `base.py`'s package-level fallback
(`library:okhttp3`), excluded from matching by design (above). No topic
match is possible for the reason already stated: no extractor anywhere in
this codebase emits a topic-specific `event_publish`/`event_subscribe` edge.
The matcher's route/event-direction code paths are therefore exercised only
by the synthetic unit tests (`tests/test_link.py` `ExactMatchTest`,
`HeuristicMatchTest`), not by live target data — the same honest gap this
project's own convention (F9, F10) requires stating rather than silently
degrading to "the fixture passed."

**`make check TARGET_REPO=/Users/sharmp49/git/code_scanner` (475 tests,
determinism fixture+target, `fold --check` fixture+target, golden
fixture+target): all gates green, golden baseline byte-identical, no
re-blessing needed** — `link.py`/`cli.py`'s new `link` subcommand are
additive and untouched by the `scan`/`fold`/`golden` pipeline, since no
existing command calls the new code path.

**Not delivered this session, recorded as scope rather than silently
dropped:** M8.2 (unmatched rendering beyond the basic list — no `link
query --service` view yet), M8.3 (the LLM tier for ambiguous matches;
`needs_other_repo` routing), M8.4 (`link refresh`), M8.5 (the non-entanglement
test — moot today since `link scan` writes nothing to any store to drop, but
becomes real once M8.3's runner path lands and a store table exists to
assert against). A genuine two-repository pair (not two modules of one
monorepo) has not been exercised; whether real cross-service route/topic
matches exist anywhere in this organisation's actual estate remains unknown.

### Follow-up, same session — `link scan` explodes a snapshot by module, so one monorepo scan is enough

**Gap the user caught:** the version above only ever compared whole
snapshots (`(repo, head)`) against each other, so a *single* `cdp scan --repo
$TARGET_REPO` — one `dataflow.json` pooling all 63 modules' edges — had
nothing to compare against itself, and `link scan` could never surface a
link between two of the monorepo's own modules without scanning each module
into its own state dir by hand first (the workaround the M8.1 exercise
above actually used). That defeats the point for anyone who scans a
monorepo once, which is the normal case.

**Not fixed by, and not blocked on, M7.2/D36.** Asked and answered in
session: M7.2's per-scope materialisation is a storage/query-cost fix for
`state.json` at very large scope counts; `dataflow.json`'s edges already
carry a `module` tag today, independent of M7.2, and cost nothing extra to
filter in Python at this target's scale (single-digit-MB dataflow, 170
scopes). The gap was purely that `link.py` never read that tag.

**Fix:** `scan_links` now explodes every input snapshot into one
pseudo-snapshot per distinct `edge["module"]` value
(`_explode_by_module`) before matching, so a whole-repo scan and N
separately-scanned single-module repos take the same code path. `self_link`
is redefined as `(repo, head, module)` equality (was `(repo, head)` alone) —
two edges in different modules of the *same* scan are now a real
cross-module link, not a self-link. `cdp link scan` now accepts a single
state directory (previously required 2+); the report gains a `modules`
total alongside `snapshots`.

**Re-verified on the real target, not just synthetic dicts (R-E7).** A
*single* full `cdp scan --repo $TARGET_REPO` (5.97s, one state dir) fed to
`cdp link scan` directly: 60 modules exploded from the one snapshot, 3,330
`persist`↔`schema_own` matches, **350 of them genuinely cross-module** (not
self-links) — real signal, not noise: filtering out the known F2/data.py
`table:dbo` artifact still leaves 84 cross-module matches naming real,
distinct table names (`Property`, `Address`, `policyconditions`, `loccvg`,
`FLDET`, ...) shared between `ms-sql-java/downgrade-processor`,
`service-api`, `catalog-service`, and `exposure-snapshot`'s modules — the
actual "what touches this table across services" answer the phase exists
to give, obtained from one ordinary scan. Scratch state dir removed after
the exercise.

**Two unit tests added** (`tests/test_link.py` `ByModuleExplosionTest`):
two modules pooled in one synthetic snapshot link and are *not* self-links;
one module persisting to its own table stays a self-link. All 10 tests in
the module green; `make check TARGET_REPO=...` re-run after this change
(result recorded once it completes, same expectation as before — additive,
untouched by `scan`/`fold`/`golden`).

---

## Phase 8 (M8.2 only) — `link.*` persistence and `link query --service`

Scoped to M8.2 only this session, by explicit user choice: M8.2-M8.5 is not
one milestone's worth of work (M8.3 needs the runner/Phase 4 gates wired to
`link_task`, M8.4 mirrors Phase 3's whole refresh design, M8.5 needs real
`link.*` data to assert against) — every prior phase in this project's own
history scoped down the same way, so this one did too rather than attempting
all four in one sitting. M8.3-M8.5 remain fully unstarted.

**What shipped.** `link_edge` (created Phase 2, empty until now) gets two
new `SqliteStore` methods: `write_link_edges(report)` — a full `DELETE` +
re-`INSERT` of `report["links"]`/`report["unmatched"]` as
`{"kind": "link"|"unmatched", "data": ...}` rows — and `read_link_edges()`.
Full replace, not append, because `link.*` is entirely re-derived from a
fresh `link scan` (R3) and there is nothing to accumulate against. `cdp link
scan` gains an optional `--db <path>` (mirrors `cdp gc --db`'s escape-hatch
convention — link data spans multiple repos' stores, so it is never the
thing `_paths()`/`.cdp.toml` resolves to for "the current repo"); a new `cdp
link query --db <path> --service <name>` subcommand
(`cdp/link.py`'s new `query_service`/`summarise_query`) reads the persisted
rows and renders every link touching that service in either direction plus
that service's own unmatched outbound calls — 5.6's "named deliverable, not
an empty row" applied to the query surface, not just the scan output.

**Design decision left open by the plan, resolved here:** the plan does not
say which store owns cross-repo link data, since a link by definition spans
more than one repo's own store. Followed D13/`cdp gc`'s precedent exactly:
`--db` is a required, explicit `SqliteStore` path for both `scan --db` and
`query`, never resolved through `_paths()`. `FileStore`/`PostgresStore` are
untouched by this milestone (no `write_link_edges`/`read_link_edges` on
either) — `PostgresStore`'s own docstring already flags `link_run`/
`link_task` as deliberately not carried across (`postgres_backend.py:82`);
`link_edge` inherits that same posture for consistency, not because
Postgres couldn't support it.

**Exercised on two real modules of `$TARGET_REPO`, not a synthetic
dict.** `sql-pool/sql-pool-api` and `service-api` each scanned fresh into
their own scratch state dir; `cdp link scan <a> <b> --db <scratch>/index.db`
persisted 2,697 links + 1,396 unmatched (the same totals M8.1's own exercise
found). `cdp link query --service <service-api's repo path>` read them back
and rendered 2,697 links (all self-links between that repo's own modules,
matching M8.1's finding that this pair shares no cross-repo table names) and
1,396 unmatched outbound calls; querying `sql-pool-api`'s repo path returned
0 unmatched (confirmed directly against the persisted rows: every unmatched
row's `outbound.repo` is `service-api`, none is `sql-pool-api`) — the service
with no unmatched calls renders an empty section, not a missing one;
querying a nonexistent service name returned `{"links": [], "unmatched":
[]}` rather than erroring. Scratch directories removed after the exercise.

**Tests.** `tests/test_link.py` `QueryServiceTest` (two new cases: a service
as both caller and callee surfaces once each direction, an unmatched call
surfaces only for its own outbound service) and
`tests/test_store_sqlite.py` `TestLinkEdgePersistence` (round-trip, and a
second `write_link_edges` call fully replacing the first). 4 tests added
across the two modules, all green (`test_link` 13/13, `test_store_sqlite`
32/32, narrow runs); full-suite count and `make check TARGET_REPO=...`
(launched after freeze, result recorded once it completes) below.

**Correction, same session — `--db` was wrongly required; D3's resolution
order applies here too.** First pass made `--db` a mandatory explicit path
for both `link scan`/`link query`, reasoned as "link data spans more than
one repo, so there is no natural repo to resolve a store from." User caught
the inconsistency: every other command that has a `--db` escape hatch
(`gc`, `compact`, `export`) makes it *optional*, defaulting through
`_paths(args)`/`_open_store(paths)` — D3's `.cdp.toml` -> registry ->
`cwd/.cdp` order, sqlite by default — and only uses `--db` to point at a
store *other than* the one that resolution would pick. `link scan`/`link
query` had no principled reason to be the one command pair that breaks that
pattern: "which repo" is answered the same way it always is, by wherever the
invocation resolves to (typically one of the repos being linked, or a
dedicated link-workspace repo), and `--db` remains for the real cross-repo
case (a shared team store). Fixed to match: `--db` optional on both, capability-
gated via a new `WorkspaceStore.supports_link_edges()` (default `False`;
`True` only on `SqliteStore`, same posture as `supports_compaction`/
`supports_run_tracking` — `FileStore`/`PostgresStore` refuse with a named,
clear message rather than silently no-op'ing or reading empty). Read-side
`read_link_edges()` defaults to an honest `[]` on the base class (matching
`list_snapshots`/`task_states`'s convention); write-side raises, since a
write that silently no-ops would look like a successful persist.

Re-verified after the fix: full 482-test suite green (including the
vendored-copy-drift check, which requires `cdp install --self` to be re-run
after touching `cdp/store/__init__.py`/`sqlite_backend.py` — done). Live
exercise, not just units: `cdp --repo <scratch-repo> link scan <a> <b>`
(no `--db`) persisted into `<scratch-repo>/.cdp/index.db` via ordinary
resolution; `cdp --repo <scratch-repo> link query --service <s>` read it
back correctly; setting `backend = "file"` in that repo's `.cdp.toml` and
re-running `link query` produced the intended clear refusal (`FileStore
cannot back \`cdp link query\` -- needs the sqlite backend`) instead of a
confusing empty result. One process note: `registry_mod.resolve_store`'s
own fallback default is `Path.cwd() / ".cdp"` (the *process* cwd, not
`--repo`) when neither `.cdp.toml` nor the registry has an entry yet — a
pre-existing quirk of every command using `_paths`, not something this
milestone introduced, but it bit the first live-exercise attempt here (ran
from this project's own directory with only `--repo` pointing elsewhere,
so it silently wrote a real `.cdp/index.db` into this checkout). Caught
before it was committed (`.cdp/` is gitignored, and the directory was
removed); the second attempt passed `--repo` correctly and everything
after cwd-matched. Worth a follow-up note for whoever next touches
`resolve_store`, not fixed here since it is out of M8.2's scope and every
other command already lives with it.

---

## Phase 8 (M8.3 only) — `link prompts`/`link collect`, the LLM tier for ambiguous matches

Scoped to M8.3 only this session, per explicit user choice after the plan's
three remaining milestones (M8.3-M8.5) were flagged as each carrying its own
design fork — M8.4/M8.5 remain unstarted.

**D40 — "ambiguous" is `match_kind == "heuristic"`, not a second detector.**
`scan_links` (M8.1) already names the ambiguous case at scan time: the
normalised key matched, the raw path/topic/table did not. No env-var/topic-
concatenation detector exists anywhere in this codebase's extractors (Finding
T1: no extractor emits that shape of edge), so building one for this
milestone alone would be inventing a signal with no real corpus support --
the exact mistake `RESEARCH_GRAPHIFY.md` §9 warns against. `heuristic` is the
real, already-shipped ambiguity; M8.3 routes exactly that into the LLM tier.

**D41 — one task per distinct caller target string, not per link.** The
plan's own stress test ("a topic built by string concatenation in three
places... must not become three unrelated tasks") is answered by grouping
`report["links"]` by `(protocol, caller.target)` before building tasks
(`link.build_tasks`): several call sites sharing one raw ambiguous string
become one task naming every candidate callee, answered once.

**D42 — `link_id` is a pure function of `(protocol, caller, callee)`
content, recomputed on read, never stored as report state.** The real-target
exercise below found this the hard way: the first implementation set
`link["link_id"]` as a side effect of `build_tasks`, so a link scanned,
persisted, then read back in a *separate* `link collect` process invocation
had no `link_id` at all -- `fold_resolutions` silently matched nothing
(`accepted 1, rejected 0, 0 resolution(s) folded`, the false-success shape
the project's own `verify-or-mark-unverified` discipline exists to catch).
Fixed by making `_link_id` a `stable_hash` over content, called fresh
wherever a link_id is needed (`build_tasks`'s candidate list, and
`fold_resolutions`'s lookup index) rather than trusted as prior mutation.
Verified by re-running the exact live sequence that found it (below) after
the fix: `1 resolution(s) folded`, confirmed by reading `read_link_edges()`
back directly, not the summary line.

**D43 — validate+verify+entail are one function (`validate_task_patch`), not
three, and Phase 4's `gates.py` is not called.** The plan says "the same
validate → verify → entail → fold pipeline" and "the Phase 4 gates ...
unchanged" -- `gates.py`'s actual functions (subject-exists, negative-
entailment, closed `needs_*` vocabulary, clustering) all operate against one
repo's own `extraction` index, which a cross-repo link-task patch has no
access to and no use for. Reusing them literally would mean either
constructing a fake single-repo extraction index for two repos' worth of
candidates, or silently no-op'ing every gate -- both worse than the
honest alternative taken: a link-task patch gets its own closed vocabulary
(`link.VERDICTS = {"match", "no_match", "uncertain"}`, the same *shape* of
closed-vocabulary gate `gates.py` established for `needs_*`) and its own
entailment check (a cited `anchor` must equal one of the caller/callee
anchors this task's own prompt actually showed the model -- no fabricated
citation trusted, same spirit as Phase 4's negative-entailment gate, applied
to the data a cross-repo verdict actually has). **Deviation from the plan's
literal wording, stated rather than silently reinterpreted.**

**D44 — `link prompts`/`link collect` do not wire into `cdp run`/
`supervisor.py`; only the manual prompt-file / inbox-directory loop and
direct `SubprocessRunner` reuse are built.** `runner.py`'s own `SubprocessRunner`/
`RunResult` classes are reused literally and unmodified (`runner.run(prompt_path,
patch_path)`, exactly `cdp run`'s own call shape) via `link prompts --runner-cmd`.
Full `cdp run` integration (leases, `snapshot_task` rows, wave scheduling) is
not attempted -- that needs `dim_task_kind = link` rows in a schema this
session did not touch, and is real schema work belonging to its own reviewed
change, the same posture F9/D7 already take toward similarly-scoped
deferrals.

**Real-scale exercise.** `sql-pool/sql-pool-api` and `service-api` each
scanned fresh, `cdp link scan --db` persisted (2,697 links, 0 heuristic --
same real finding M8.1 already recorded: this specific pair produces no
ambiguous edges). `link prompts --db ... --out ...` against that real,
persisted store correctly produced **0 tasks** -- the honest answer, not a
fixture workaround. To exercise the actual adjudication path against a real
persisted SQLite store (not just the fixture unit tests), one synthetic
heuristic link (`/orders/{id}` vs `/orders/:id`, the same param-syntax
ambiguity `tests/test_link.py`'s own fixture case uses) was written directly
into the real `index.db` via `SqliteStore.write_link_edges`. Against that:
`link prompts` produced one task naming both candidate anchors; a
hand-written valid patch folded correctly (`accepted 1, rejected 0, 1
resolution(s) folded`, confirmed via `read_link_edges()`); a hand-written
patch citing a fabricated anchor was rejected with the specific reason
(`fabricated citation rejected`); and `--runner-cmd` invoked a real
subprocess (a throwaway script) whose own citation-parsing bug produced a
wrong anchor -- `link collect` correctly rejected it rather than trusting a
subprocess-produced patch by default, proving the entailment gate holds
against real subprocess output, not only hand-crafted dicts. Scratch
directories and the scratch `index.db` removed after the exercise.

`make check TARGET_REPO=/Users/sharmp49/git/code_scanner` (launched after
freeze, per R-E3): 487 tests green; determinism, `fold --check`, golden all
green fixture+target, byte-identical, no re-bless needed. Full readout in
`PHASE/TARGET.md`.

---

## Phase 8 (M8.4) — `link refresh`, and the design fork it left implicit

**Design taken, not specified by the plan.** 5.3 says only "re-verify link
contracts against new snapshots, mirroring Phase 3's refresh semantics."
`refresh_links(old_report, new_snapshots)` re-verifies **only the repos named
in `new_snapshots`**: for each existing link touching a refreshed repo, it
checks whether an outbound/inbound edge with the same `(repo, module,
channel, normalised-key)` still exists in the fresh scan; if not, the link
is kept but marked `status: "decayed"` with a `decay_reason` naming which
side and which repo; if so, that side's `repo`/`head`/`anchor` are replaced
with the fresh data (re-anchoring). A link touching no refreshed repo is
returned byte-identical — this is what makes 5.5's "the other repo's
snapshot is unchanged" literal rather than aspirational: `refresh_links`
never reads or re-derives anything about a repo it wasn't handed fresh data
for. Brand-new links are discovered only among the refreshed snapshots
themselves (`scan_links(new_snapshots)`, filtered to link_ids not already in
`old_report`) — a new link between a refreshed repo and an *un*-refreshed one
is out of scope for one `refresh` call, since only one side's fresh edges are
available; that repo's own next `link refresh` (or a re-run `link scan`) is
what would surface it. Mirrors `cdp refresh`'s own D10 posture (re-verify the
existing log; a genuinely new structural fact needs a fresh derivation pass,
not a bolt-on to refresh).

CLI: `cdp link refresh STATE_DIR... [--db PATH] [--json]`, requiring the
sqlite backend the same way `scan`/`prompts`/`collect`/`query` already do
(`supports_link_edges()`). Replaces the store's `link_edge` contents with the
merged report, same as `link scan --db` (R3: link data is fully derived, an
overwrite is correct, not destructive of anything `snapshot.*`/`claim.*`
owns).

**Verified on synthetic data with a unique key** (`tests/test_link.py`
`RefreshTest`, 4 new tests): a caller route removed decays the link with a
reason naming the caller side and the refreshed repo, leaving the untouched
callee side's anchor exactly as before; an endpoint that survives at a new
line carries forward `status: "live"` with the caller re-anchored to the new
line; a link touching neither refreshed repo is returned `==` the original
(not just equivalent — literal equality); an unmatched call from a
non-refreshed repo is left alone.

**Real-target exercise ran, but produced a negative result worth recording
rather than working around (per this project's own standard).** A real
`persist` edge (`Resources/RollbackScripts/Rollback_V21_to_V18.sql:17` in a
worktree of `service-api`) was deleted and committed; refreshing against that
new scan gave `0 decayed` out of 5,359 links. Root cause: this target's real
`persist` self-links all key on `table:dbo` (F-link1 — the C# extractor's
schema-name extraction collapses many distinct migration files onto one
normalised key), so removing one file's edge does not remove the key itself —
a different file sharing the same key satisfies `_still_present`'s lookup.
This is not a bug in `refresh_links`'s decay logic (the unit tests prove that
logic correct on data with a real key), it is this target having no
uniquely-keyed persist/http/event edge available to remove: `$TARGET_REPO`
still has no cross-repo route or topic edge at all (Finding T1/M8.1's own
finding), and its only real persist self-links inherit F-link1's collision.
**Not fixed here** — F-link1 is a pre-existing, separately-tracked C#-extractor
finding, out of this milestone's scope, and fixing it to get a clean refresh
demo would be scope creep into Phase 6-era extractor work from a Phase 8
session.

---

## Phase 8 (M8.5) — non-entanglement test, found already satisfied

The milestone asks to re-run M2.5's non-entanglement assertion "against fully
populated [link] tables, which is the only version that proves anything."
`tests/test_store_sqlite.py::TestRunsAndTasks::test_dropping_every_link_row_leaves_snapshot_and_claim_untouched`
already does exactly this — one row inserted into each of `link_run`,
`link_task`, `link_edge` before dropping all three and diffing
`snapshot_run`/`snapshot_task`/`snapshot_artifact`/`claim_patch` before and
after. It predates this session (added alongside the M8.2 schema work) and
was never renamed to reflect that it had already superseded the empty-table
version the plan describes. **No new code was needed**; it is confirmed
green in isolation this session and runs as part of `unittest discover`,
which `make check`'s `selftest` gate already invokes — so it is enforced in
CI on every phase after this one without further wiring, satisfying the
plan's own "In CI, every phase after this one" clause.

`make check TARGET_REPO=/Users/sharmp49/git/code_scanner`: **491 tests green
(up from 487 — this session's 4 new `RefreshTest` cases), determinism
(fixture+target), `fold --check` (fixture+target), golden (fixture+target)
all green, byte-identical, no re-bless needed** — `link refresh` is additive
and untouched by the existing `scan`/`fold`/`golden` pipeline, since no
existing command calls the new code path.

---

## Phase 9 (M9.1 only) — trajectory store and star schema

**Scoped down from the full phase.** `phase_9_plan.md`'s four milestones
(trajectory store; corpus/regret/routing; reflection/lesson-sets/holdout;
distribution — MCP/LiteLLM/adapters/`SKILL.md`/strict-mode/`AGENTS.md`) are
each independently larger than a typical prior single-session milestone.
User chose M9.1 only after being asked explicitly (this session's first
action, per `PHASE/EXECUTION_RULES.md`'s budget instruction: say so and ask
before spending the budget silently on a scope this large). M9.2-M9.4 are
unstarted.

**What shipped.** `cdp/trajectory.py` (new module): a `TrajectoryStore`
wrapping a *separate* SQLite file at `~/.cdp/trajectories.db` (override:
`CDP_TRAJECTORY_DB`, the same env-override pattern this codebase already uses
for `HOME`-redirection in tests — never the real home directory during
tests). Star schema: `dim_model`/`dim_scope_shape`/`dim_template`/`dim_repo`/
`dim_tier`/`dim_task_kind` dimensions, `fact_leaf_run` (grain: one run x scope
dispatch) and `fact_run_event` (grain: one run-level event) facts, exactly as
0.17/0.18 specify. Wired into `cli.py`: `cmd_run` writes a `started` event
before dispatch and a `finished` event after (including the `--stale-only`
early-return path), and `_apply_wave_results` writes one `fact_leaf_run` row
per scope per wave (`VALIDATED`/`ABANDONED` state, attempts, tier, scope
shape, claims/unknowns emitted). `cmd_rollback` writes `rolled_back` events
for every newly-excluded run, one per run_id — the plan's own worked example
("Phase 3's `rollback` writes `fact_run_event(rolled_back, reason)` here").

**Decisions made, not left implicit (R-E13 — surfaced here since none of
these needed a mid-session pause, all resolved by reading what already
exists rather than by unstated judgment calls):**

- **`dim_model`** is populated from the real `--runner-cmd` string's first
  token (or `"human"` with no `--runner-cmd`), not a model name — D1 already
  established that no model-identity tracking exists anywhere in this
  codebase yet (`snapshot_run.model` is a nullable column nothing writes).
  This is real, un-fabricated data (the actual command CDP invoked), labeled
  honestly rather than invented; a real model-name column can replace it the
  moment something upstream knows the model, without a schema change.
- **`dim_template`** is always `"unversioned"` for the same reason (D1: no
  template versioning exists in `prompts.py` yet). Recorded as unset rather
  than guessed.
- **`dim_tier`** is read from `backend.read_report("tiering", {})` (M6.4's
  existing per-node tier record) when present, `"unset"` otherwise — never
  fabricated for scopes M6.4's tiering pass didn't touch.
- **`task_kind`** is always `"scope"` this session; `cdp run` has no `link`
  dispatch path (Phase 8's `link prompts`/`link collect` are a separate,
  non-`cdp-run` CLI surface) — `dim_task_kind` is schema-ready for `"link"`
  the day that changes, and raises rather than silently accepting a third
  value (a closed vocabulary enforced by code, matching this codebase's
  existing convention for `needs`/`kind` elsewhere).
- **`scope_shape_key`** buckets on file-count power-of-two plus the scope's
  `by_language`/`by_role` composition — coarse by construction, since M9.2's
  routing prior needs shape-alike neighbours across repos, not a fingerprint
  of one scope.
- **Compaction events are out of scope this session.** The plan's acceptance
  criteria for M9.1 name only `fact_leaf_run`/`fact_run_event` populating
  from real Phase 5 runs and workspace-delete survival; `cdp compact`
  (Phase 7, M7.3) writing a `compacted` event is prose in the milestone
  description, not one of its acceptance lines, and adding it was not free
  (`cmd_compact` doesn't currently resolve a `repo_id` the way `cmd_run`/
  `cmd_rollback` already do). Deferred, not silently dropped: a future
  session should add it alongside whichever milestone next reads
  `fact_run_event` for `compacted` rows.

**Verified, not assumed.** `tests/test_trajectory.py` (new, 3 tests):
`scope_shape_key` buckets two shapes with different file counts into the
same key when both round to the same power-of-two; `dim_task_kind` raises on
an out-of-vocabulary value; and a real, subprocess-driven `cdp scan` + `cdp
run --wave-all` (fixture repo, `CDP_TRAJECTORY_DB` pointed at a scratch
file) populates both facts, then `shutil.rmtree`s the entire workspace state
directory and re-reads the trajectory DB — same rows, unaffected — which is
M9.1's own "deleting the workspace store leaves the trajectory DB intact"
acceptance line, exercised literally rather than argued.

**Exercised on a real target module (R-E7), not only the fixture.**
`sql-pool/sql-pool-api` scanned fresh into a scratch dir; `cdp run
--wave-all` via a real external `--runner-cmd` script:

```
$ cdp run --wave-all --runner-cmd "python3 fake_runner.py"
wave 0       2 scope(s)  validated 2

run_id: cdp-7e10575adf69
leaf rows: [{'node': 'root/(files+2)', 'state': 'validated', ...},
            {'node': 'root/src/main/java', 'state': 'validated', ...}]
events: [{'event': 'started', ...}, {'event': 'finished', 'reason': 'complete', ...}]
```

Both real scopes produced a `fact_leaf_run` row keyed to their real
`scope_hash`, and the run produced its `started`/`finished` event pair —
against real target-derived data, not a synthetic scope dict. Scratch
directories removed after the exercise.

**Real defect caught by the gate itself, fixed before the reported green
run.** The first `make check` run (after the freeze above) failed
`selftest`: `tests/test_store_sqlite.py`
`TestSqliteImportBoundary.test_sqlite3_is_imported_in_exactly_one_module`
asserts `sqlite3` is imported nowhere but `cdp/store/sqlite_backend.py` —
`cdp/trajectory.py`'s own `import sqlite3` (a separate database, but still a
raw sqlite3 connection) violated it. Fixed by adding
`sqlite_backend.connect_raw(db_path)` — a thin, exported wrapper around
`sqlite3.connect` plus the same `PRAGMA foreign_keys = ON` every other
connection in this codebase sets — and having `trajectory.py` import that
instead of `sqlite3` directly. This is the one intended crossing point the
boundary test allows: `trajectory.py` needs its own connection to a
different file with a different schema, not `WorkspaceStore` machinery, so a
full `SqliteStore` subclass would have been the wrong fit. Re-verified: the
boundary test and the full `test_trajectory` module both green after the
fix, and the freeze/gate cycle was repeated (R-E3: last edit before the
gate, not after) — no code changed between the second freeze and the
reported green run below.

`make check TARGET_REPO=/Users/sharmp49/git/code_scanner`: **494 tests green
(up from 491 -- this session's 3 new `test_trajectory` cases), determinism
(fixture+target), `fold --check` (fixture+target), golden (fixture+target)
all green, byte-identical, no re-bless needed** -- confirming the trajectory
store's writes, wired only into `cmd_run`/`cmd_rollback`, changed nothing
about the existing `scan`/`fold`/`golden` pipeline, since neither is on that
pipeline's path.

**Not done this session, named rather than silently dropped:** M9.2
(corpus/regret/routing-prior), M9.3 (reflection/lesson-sets/holdout), M9.4
(distribution: MCP/LiteLLM/adapters/`SKILL.md`/strict-mode/`AGENTS.md`).
M9.2's elision regret in particular needs `prompts.py`'s digest-elision
instrumentation (M6.3) read back against real leaf escalations/unknowns,
which this session's `fact_leaf_run` rows do not yet carry (no
`elided_rows`/`digest_vs_source` column exists on the fact yet — 0.18 names
the input fingerprint as M9.2's own addition, not M9.1's).

---

## Phase 9 (M9.2 only) — corpus, elision regret, routing prior

**Scoped down from the full phase, asked explicitly before implementing**
(`PHASE/EXECUTION_RULES.md`'s budget instruction): M9.3
(reflection/lesson-sets/holdout, safety-critical under R10) and M9.4
(distribution) are each independently as large as M9.1 was on their own, so
this session covers 6.3/6.4/6.5 only.

**Citation drift found and reported, not silently worked around.** The
plan's `prompts.py:120` (the elision-ranking function M9.2's regret grades)
had drifted a few lines since M9.1 landed — that line now sits inside
`_imported_symbols`'s docstring. The actual function is `_inherit`
(`cdp/prompts.py:142-167`; the fan-in sort that decides what gets elided is
line 164).

**What shipped.** `fact_leaf_run` gained seven columns: `rows_elided`,
`tokens_est`, `digest_mode` (the input fingerprint, sourced from
`build_prompt`'s own stats dict, already computed and previously discarded
by `supervisor.dispatch_scope`) and `entailed`/`consistent`/`contradicted`/
`elision_regret` (the output scorecard, computed in `cli._apply_wave_results`
once a leaf's patch folds). Both halves share one row — `record_leaf_run`'s
existing grain (`run_id` x `node`, joined to `scope_hash`) already satisfies
the plan's "joined on `scope_hash`" requirement without a second table.

**Migration, not a fresh-DB assumption.** A real `~/.cdp/trajectories.db`
from M9.1's own earlier real-target exercises already existed on disk at
73KB with the pre-M9.2 schema — `CREATE TABLE IF NOT EXISTS` is a no-op
against it, so `TrajectoryStore.__init__` now runs
`_migrate_leaf_run_columns()` (a `PRAGMA table_info` diff + `ALTER TABLE ...
ADD COLUMN` for whatever is missing) after the `executescript`. R4 held: no
row was altered or dropped, only nullable columns added — verified with a
new test (`test_migration_adds_m92_columns_to_a_pre_m92_db`) that builds a
literal pre-M9.2 schema by hand and confirms a new-shape row inserts and
reads back correctly afterward.

**Elision regret (6.4), the plan's own highest-value item, implemented as a
named, unit-tested pure function** (`trajectory.elision_regret(elided_subjects,
unknown_subjects)` — a set intersection), not inlined into `cli.py`'s wave
loop, specifically so it is testable independent of the dispatch plumbing.
`prompts.build_prompt` now also returns `elided_subjects` (previously only a
count, `elided_claims`) in its stats dict; `supervisor.dispatch_scope`
threads that whole stats dict back to the caller (`"prompt_stats"`, a new
key on its return dict — previously discarded as `_stats`) so
`_apply_wave_results` can compare a leaf's own emitted unknown subjects
against what its own prompt elided.

**Entailment (part of the output scorecard) computed against the leaf's own
claims, not deferred to `collect`.** `entail.entail_claims` (M4.1, already
existed, already cheap — a dict lookup against the extraction the leaf
already saw) is called once per validated leaf inside `_apply_wave_results`;
`cdp run`'s wave loop had never called it before (M4.1 wired it into
`collect`'s standalone path only).

**Routing prior (6.5), exactly the plan's own SQL-not-model shape.**
`TrajectoryStore.routing_prior(scope_shape_key, task_kind)` is one query —
`GROUP BY` folded into aggregate functions over a join across
`dim_scope_shape`/`dim_task_kind` — returning `n`, average
claims/unknowns/tokens, validated rate, and average elision regret for
every prior run of a shape-alike scope. Zero model calls, deterministic by
construction (SQL aggregates, no ordering-sensitive tie-break needed since
nothing here picks a single winner).

**Exercised on a real target module (R-E7), not only the fixture.**
`sql-pool/sql-pool-api` scanned fresh into a scratch dir; `cdp run
--wave-all` via a real external `--runner-cmd` script emitting one
legitimate scope-level unknown (no claims) per scope:

```
wave 0       2 scope(s)  validated 2

[{'node': 'root/(files+2)', 'rows_elided': 0, 'tokens_est': 3472,
  'entailed': 0, 'consistent': 0, 'contradicted': 0, 'elision_regret': 0},
 {'node': 'root/src/main/java', 'rows_elided': 0, 'tokens_est': 8886,
  'entailed': 0, 'consistent': 0, 'contradicted': 0, 'elision_regret': 0}]
```

**Provably zero, not silently zero** (the acceptance line's other branch):
this is a first scan with no prior claims to inherit or elide, and the fake
runner emits zero claims, so `rows_elided`/`entailed`/`elision_regret` are
all correctly zero by construction — not measured-and-happened-to-be-zero.
`routing_prior` queried against each scope's own real, non-trivial shape key
(`files<=16|langs=config,docker,gradle,java,other|roles=build,config,source,test`
and `files<=64|langs=java|roles=source`) correctly returned `n=1` with the
matching aggregates for each, and `n=0`/`validated_rate=None` for a shape
with no prior rows — the concrete form of "a SQL query, not a model call"
against real target-derived data. Scratch directories and the scratch
trajectory DB removed after the exercise; the real `~/.cdp/trajectories.db`
used for the migration check above was read, migrated in place, and left
with its prior rows intact (re-verified by reading them back post-migration
with the original, unmigrated columns still present and unchanged).

**Not built this session, named rather than silently dropped:** the
"digest-vs-source" half of the input fingerprint (0.17/M9.2 both name it,
but `build_prompt`'s stats already carry `digest_mode` as a bool, which is
what got wired — a source-vs-digest *comparison* on the same scope, the
stress-table item M6.3 left for M9.2, was not attempted, since it needs two
real leaf dispatches of the same scope in both modes, which `cdp run`'s
single-dispatch-per-wave loop does not do today); `sigma_claims` (the count
of imported-symbol claims specifically, distinct from `inherited_claims` —
`build_prompt`'s stats has `imported_symbols`/`inherited_claims` but nothing
narrower); and `task_kind="link"` rows for this corpus (Phase 8's `link
prompts`/`link collect` still run outside `cdp run`'s dispatch loop, per
M9.1's own note — `routing_prior` and `elision_regret` both already work for
`link` by construction the day that changes, since neither hardcodes
`"scope"`).

`make check TARGET_REPO=/Users/sharmp49/git/code_scanner`: **497 tests green
(up from 494 — this session's 4 new `test_trajectory` cases), determinism
(fixture+target), `fold --check` (fixture+target), golden (fixture+target)
all green, byte-identical, no re-bless needed** — the new columns and the
`entail_mod` call wired into `_apply_wave_results` changed nothing about the
existing `scan`/`fold`/`golden` pipeline, since `cdp run` never sits on that
pipeline's path.

---

## Phase 9 (M9.3, 6.6 only — reflection) — a real defect this milestone's own
## real-target exercise found in M9.2's code, plus what shipped

**Scoped down from the full M9.3** (reflection/lesson-sets/holdout), asked
explicitly before implementing: lesson-sets (6.7, needs a cut/pin/reproduce
mechanism and CLI wiring) and holdout A/B (6.8, needs a second repo and a
promotion bar) are each independently as large a slice as M9.1/M9.2 were —
deferred, not started. This session is 6.6 only: select a handful of outlier
scopes from a run's own trajectory corpus (M9.2), spend one real model call
per outlier, keep only what comes back as a deterministic, closed-vocabulary
promotion.

**Real defect found by this milestone's own real-target exercise
(R-E7), in code M9.2 shipped, not this session's new code.**
`TrajectoryStore.leaf_runs_for` (`cdp/trajectory.py`) — extended by M9.2 to
select the new scorecard columns — dropped `claims_emitted`/
`unknowns_emitted` from its `SELECT` entirely while adding the new ones.
Every caller reading `claims_emitted` off a `leaf_runs_for` row therefore
silently got `None`. This session's own `select_outliers`
(`row.get("claims_emitted") or 0`) turned that `None` into `0`, which wrongly
qualified *every* high-token scope as `high_spend_low_yield` regardless of
its real yield — caught immediately on the real-target exercise below (a
seeded scope with `claims_emitted=5`, `tokens_est=8000` was wrongly flagged
as an outlier and reflected on) rather than on the fixture, where the test
suite's own synthetic rows happened to construct `leaf_runs_for`'s return
dict directly rather than round-tripping through the real query. Fixed by
adding `claims_emitted`/`unknowns_emitted` back to the `SELECT`/dict-building
in `leaf_runs_for`; re-verified live (below) that only the genuinely
contradicted scope is selected afterward.

**What shipped.** `cdp/reflect.py` (new module): `select_outliers(leaf_rows,
limit=5)` — deterministic, no model call, pulled straight from M9.2's own
corpus columns: a scope qualifies if `contradicted > 0` (gold-standard per
`entail.py`'s own docstring) or `tokens_est >= 5000` with `claims_emitted ==
0`, sorted worst-first, capped ("a handful per run"). `build_reflection_prompt`
writes one scope's outlier context plus a strict closed-vocabulary output
contract into a real prompt file. `validate_promotion` enforces R10
structurally: `PROMOTION_KINDS = ("import_channel_hint", "prompt_fix",
"budget_change")` share no vocabulary with a claim's own `kind` field, each
kind has a fixed, small field allowlist, and **any extra key is rejected
outright** — a model cannot smuggle a `subject`/`anchor`/`evidence` triple
(claim-shaped content) through a promotion even if it tried, proven by
`test_r10_a_claim_shaped_payload_is_structurally_impossible`
(`tests/test_reflect.py`). `{"promotion": "none"}` (or anything that fails
validation) is discarded with a stated reason, never stored — the plan's own
"a store of vague lessons is the peer system's failure mode" stress test,
enforced by `test_unactionable_reflection_is_discarded_not_stored_as_a_lesson`.

**CLI: `cdp reflect --run-id ID --runner-cmd CMD [--limit N]`.** Reuses
`runner.SubprocessRunner` verbatim (same `runner.run(prompt_path, out_path)`
protocol `cdp run`/`link prompts` already use — no new runner abstraction).
Writes `reports/reflections.json` (`{"accepted": [...], "discarded": [...]}`)
via the existing `write_report`/`read_report` convention (M4.2's
`unknown_gates`, M6.4's `tiering`), and prints one `PROMOTED`/`DISCARDED`
line per outlier, matching the "gates" reporting style established
throughout this codebase.

**Verified, not assumed.** `tests/test_reflect.py` (new, 17 tests):
`select_outliers`' two trigger conditions and its cap; every valid/invalid
shape of all three promotion kinds; the R10 smuggling test above; and
`reflect()`'s end-to-end behaviour against fake runners (accepted,
runner-failure, no-output, and unactionable-`none` cases), each via a
minimal `_FakeResult`/fake-runner class rather than a real subprocess, since
the runner protocol itself is `runner.py`'s own, already covered.

**Exercised on a real target module (R-E7), not only the fixture — and this
is what caught the defect above.** `sql-pool/sql-pool-api` scanned fresh
into a scratch dir; two real `fact_leaf_run` rows seeded directly against
its real `run_id`/`scope_hash`es (one genuinely contradicted, one merely
high-token but with real claims emitted — the exact case that exposed the
`leaf_runs_for` regression). Before the fix: `cdp reflect` selected and
reflected on **both** scopes (wrong). After the fix:

```
$ cdp reflect --repo .../sql-pool-api --state-dir ... --runner-cmd "python3 fake_runner.py"
reflect   PROMOTED  (root/(files+2)): prompt_fix
reflect   1 accepted, 0 discarded

$ cdp reflect ... --runner-cmd "python3 fake_runner_none.py"
reflect   DISCARDED (root/(files+2)): no actionable promotion
reflect   0 accepted, 1 discarded
```

Only the contradicted scope selected either time; the high-token-but-real-yield
scope correctly excluded. Scratch directories and fake runner scripts removed
after the exercise; both this checkout's and `$TARGET_REPO`'s own working
trees (`git status --porcelain`) were empty before and after.

**Not built this session, named rather than silently dropped:** lesson-sets
(6.7 — cut/pin/`--lessons vN`/`--no-lessons`/reproduction) and holdout A/B
(6.8) both remain unstarted; a promotion this session produces has nowhere
to land yet (no lesson-set exists to fold it into) — `reports/reflections.json`
is the honest current terminus, read by nothing downstream yet, the same
posture M9.1 took toward `cdp compact` writing a `compacted` event.

`make check TARGET_REPO=/Users/sharmp49/git/code_scanner`: **514 tests green
(up from 497 — this session's 17 new `test_reflect` cases), determinism
(fixture+target), `fold --check` (fixture+target), golden (fixture+target)
all green, byte-identical, no re-bless needed** — `reflect.py`/`cdp reflect`
are additive and untouched by the existing `scan`/`fold`/`golden` pipeline,
since no existing command calls the new code path; the `leaf_runs_for` fix
likewise touches nothing on that pipeline's path.

### Follow-up — cross-backend alignment, all three `WorkspaceStore` backends, real target module

Asked explicitly after the milestone above landed: does the trajectory store
behave consistently regardless of which `WorkspaceStore` backend a workspace
uses. **By design it should**, since `TrajectoryStore` is deliberately
independent of `backend` (0.17's "separate database" is separate from every
workspace backend, not just from `FileStore`) — `cmd_run`/`cmd_rollback` open
it once per invocation, unconditionally, regardless of which `WorkspaceStore`
subclass `_open_store` constructed. Verified rather than assumed, against a
real local Postgres server on port 5432 (`psycopg2` reachable at
`host=localhost port=5432`, no fixture stand-in):

- `tests/test_store_conformance.py`'s full `PostgresStoreConformance` suite
  (75 tests total across both backends) run live against
  `CDP_TEST_POSTGRES_DSN="host=localhost port=5432 dbname=postgres
  user=sharmp49"` — green, including `test_supports_run_tracking_is_true`,
  which is the exact capability `cdp run` gates on.
- Real-target exercise: a detached worktree of `$TARGET_REPO`'s
  `sql-pool/sql-pool-api` (pinned commit) scanned and run through all three
  backends via `.cdp.toml`'s `backend` key, one shared
  `CDP_TRAJECTORY_DB`:
  - **sqlite** (default, no `.cdp.toml`): `cdp run --wave-all` validated
    both real scopes; two `fact_leaf_run` rows and a `started`/`finished`
    event pair landed under `run_id=cdp-7e10575adf69` (the manifest's own
    commit-derived id).
  - **postgres** (`backend = "postgres"`, real `dsn`/`schema`, same module,
    same commit): validated the same two scopes identically; because the
    commit is the same, the manifest computes the *same* `run_id` as the
    sqlite run above — reading the shared trajectory DB back for that
    `run_id` returns **all four** leaf rows (two per backend) and both
    event pairs, which is the honest, expected shape for a store that is
    genuinely cross-workspace and backend-agnostic by construction, not a
    bug: the trajectory store was never asked to distinguish "which backend
    produced this row," only "which run."
  - **file** (`backend = "file"`): `cdp run` refused immediately —
    `cdp: FileStore has no run/task tracking -- \`cdp run\` needs the sqlite
    or postgres backend` (exit 2) — before `cmd_run` reaches the trajectory
    setup at all (the `supports_run_tracking()` check in `cli.py`
    (`cmd_run`) runs first), so no partial/incorrect trajectory row is ever
    written for a backend that can't support `cdp run` in the first place.
    Matches D3's existing account of `FileStore`'s stated refusal for
    `cdp gc`/`cdp link scan`.

Worktree, scratch state dirs, the scratch trajectory DB, and the Postgres
test schema (`cdp_m91_target_test`, dropped via `PostgresStore.drop_schema()`
before disconnecting) all removed after the exercise; both the main checkout
and `$TARGET_REPO`'s own working tree (`git status --porcelain`) were empty
before and after. No code changed by this follow-up — it is verification of
the milestone already frozen and gated above, not a new change needing its
own `make check` run.

---

## Phase 9 (M9.3, 6.7 only — lesson-sets) — cut/pin/reproduce, holdout deferred

**Scoped explicitly, asked before implementing.** M9.3's two remaining
pieces, lesson-sets (6.7) and holdout A/B (6.8), were each flagged as
independently as large as M9.1/M9.2 were on their own — the same posture the
6.6-only session took toward the full M9.3. Asked, and answered: **6.7 only**
this session. 6.8 (needs a second repo and an explicit promotion bar) remains
unstarted, named rather than silently dropped.

**What shipped.** `cdp/trajectory.py`: a new `lesson_promotion` table —
deliberately *not* part of the star (0.18's `fact_leaf_run`/`fact_run_event`
are the star; a promotion is routing metadata cut into versions, not a new
grain of run history). `cmd_reflect` now writes every `accepted` promotion
here via `record_promotion` (unassigned, `cut_version IS NULL`) the moment
`cdp reflect` accepts it — this is what "the corpus accrues continuously"
(6.7) means concretely: the corpus is `cdp reflect`'s own accepted output
across every run, not a separate collection step.

`cut_lessons()` assigns the next integer version to every currently-pending
row and never reassigns it — immutability by construction is what makes
`load_lessons(v)` reproduce exactly, not a promise enforced elsewhere.
`latest_lesson_version()` returns `None` until the first cut, which is 6.7's
"off for run #1 (no corpus)" stated literally: `cdp run`'s own resolution
(`--lessons N` pins explicitly, `--no-lessons` forces off, otherwise the
latest cut or `None`) auto-enables the moment a first cut exists, with no
separate flag needed to turn it on.

**CLI.** `cdp lessons cut` / `cdp lessons show [--version N]` (new
subcommand). `cdp run` gained a mutually-exclusive `--lessons N` /
`--no-lessons` group; the resolved version is pinned onto the run itself via
a new `WorkspaceStore.set_run_lessons_version` (sqlite: `UPDATE snapshot_run
SET lessons_version=...`; postgres: same; base: raises `_no_run_tracking`,
same guard `FileStore` already has for every other run-tracking method) —
`snapshot_run.lessons_version` existed as an unused nullable column since
Phase 2's D1/D2 audit; this is the first thing that writes it. `get_run` on
both real backends now also returns it, so `cdp run --lessons 1` followed by
reading `backend.get_run(run_id)["lessons_version"]` shows the pin verbatim
— the plan's own "a run pins `lessons: v7` in its manifest" line, concretely.

**R10, enforced at the persistence layer too, not just at
`validate_promotion`.** A promotion already cannot carry claim-shaped
fields by construction (`reflect.validate_promotion`'s closed per-kind
allowlist, M9.3-reflection). This session adds
`test_r10_a_claim_shaped_payload_cannot_survive_the_cut_load_round_trip`
(`tests/test_trajectory.py`) asserting the *stored and reloaded* payload's
key set is identical to what was validated — the cut/load round trip is not
a second place a `subject`/`anchor`/`evidence`/claim field could be
reintroduced.

**Verified, not assumed.** `tests/test_trajectory.py`'s new `LessonSetTest`
(5 tests): no-cut-means-`None`, cutting nothing pending is a no-op (never
mints an empty version), a cut numbers and freezes exactly the pending rows
and a later promotion is not retroactively part of an already-cut version,
repeated loads of the same version are identical (byte-for-byte, via
`assertEqual` on the returned list of dicts), and the R10 round-trip test
above. 516 tests green (up from 514).

**Exercised on a real target module (R-E7), not only the fixture.**
`sql-pool/sql-pool-api` scanned fresh into a scratch dir; two real
promotions seeded directly against the real trajectory DB (standing in for
what `cdp reflect` would have accepted — no live model call spent on this
session's budget, per the explicit 6.7-only scoping):

```
$ cdp lessons show
lessons   no cut exists yet
$ cdp lessons cut
lessons   cut v1 (2 promotion(s))
$ cdp run --wave-all --lessons 1 --runner-cmd "python3 fake_runner.py"
lessons   pinned v1
$ python3 -c '... backend.get_run(run_id) ...'
{'run_id': 'cdp-7e10575adf69', ..., 'lessons_version': '1'}
$ cdp run --wave-all --runner-cmd "..."      # no flag: picks latest automatically
lessons   pinned v1
$ cdp run --wave-all --no-lessons --runner-cmd "..."
(no "lessons" line; lessons_version: None)
```

All three resolution paths (`--lessons N`, default-latest, `--no-lessons`)
confirmed against a real run and a real `snapshot_run` row, not a synthetic
dict. Scratch directory and trajectory DB removed after the exercise; main
checkout's `git status --porcelain` was empty before and after.

**Not built this session, named rather than silently dropped.** Holdout A/B
(6.8) — needs a second repo, a promotion bar, and the cut-cadence/regression
decisions the plan explicitly defers to this milestone — remains entirely
unstarted. A cut lesson-set also has **no consumer yet**: nothing in
`prompts.py`/`supervisor.py` reads `load_lessons(v)` to actually change a
leaf's prompt content or budget — `cdp run --lessons vN` pins the version on
the run and proves the mechanism reproduces, but a pinned lesson-set does not
yet *do* anything to a dispatched leaf. This is the same posture M9.1's
`compacted` event and M9.3-reflection's `reports/reflections.json` already
took: an honest, additive terminus, not a silently absent feature. Wiring a
`prompt_fix`/`budget_change` promotion into `prompts.build_prompt` is real
work belonging to its own reviewed change (it touches the one module every
leaf prompt depends on), not a rider on this session's budget.

**F19 — `get_run`'s additive `lessons_version` key broke two pre-existing
exact-`assertEqual` tests, caught by the gate itself.** Severity low, exactly
F7's class of defect: a caller-side breakage the bundled suite's own strict
equality checks surfaced on the first post-change `make check` run, not a
design flaw in the change itself. `tests/test_store_sqlite.py` and
`tests/test_store_conformance.py` each asserted `get_run(...)` against a
three-key literal dict (`run_id`/`partition_hash`/`status`); adding a fourth
key (`lessons_version`, always present now, `None` until a run pins a cut)
made both fail on the very first gate run after freeze. Fixed by updating
both literals to include `"lessons_version": None` — the correct, expected
value for a run that never pinned a cut — not by loosening the assertion.
Re-verified: `python3 -m unittest test_store_sqlite test_store_conformance`
green (107 tests, 27 skipped — no live Postgres this session), then a full
re-run of `make check TARGET_REPO=...` from a clean freeze.

`make check TARGET_REPO=/Users/sharmp49/git/code_scanner`: **519 tests green
(up from 516 mid-session, 514 before this milestone), determinism
(fixture+target), `fold --check` (fixture+target), golden (fixture+target)
all green, byte-identical, no re-bless needed** — `lessons.py`'s cut/pin
mechanism, `cdp lessons`, and `--lessons`/`--no-lessons` on `cdp run` are all
additive and untouched by the existing `scan`/`fold`/`golden` pipeline,
since no existing command calls the new code path; the only real caller
breakage was the two test literals above, both fixed and re-verified.

---

## Phase 9 (M9.4, scoped to `SKILL.md` only) — rewritten for the post-`cdp run` world

Session scoped down from all of M9.4 (MCP server, LiteLLM adapter, `SKILL.md`
rewrite, LangGraph/ADK adapters, strict mode, `AGENTS.md`) to `SKILL.md` alone
— explicit user choice, given the 20-minute/60k-token budget and that each of
the other five items needs its own real-input exercise (per
`PHASE/EXECUTION_RULES.md`), not a shared one. MCP, LiteLLM, LangGraph/ADK,
strict mode and `AGENTS.md` remain entirely unstarted; owner is whichever
session picks up M9.4 next.

**Real bug in the first draft, caught before freezing anything.** `SKILL.md`'s
actual source is the top-level `/SKILL.md`; `.claude/skills/cdp/SKILL.md` is
the vendored self-copy `cdp install --self` overwrites from it (`DIST_MEMBERS`,
`cli.py:2270`). The rewrite was first applied to the vendored copy alone, then
`install --self` was run to "sync" it — which instead clobbered the edit back
to the stale top-level version. Caught by grepping both copies for the new
text and finding neither had it, not assumed correct because the Edit tool
reported success. Fixed by re-applying the rewrite to `/SKILL.md` and re-running
`install --self`, then diffing the two copies to confirm they match.

**What changed, and why, ground-truthed against the real parser/runner code,
not assumed:**

- The "wave loop" section (`scan` → `prompts --wave N` → spawn a wave in one
  message → `collect` → `status`, repeat) is superseded by `cdp run`
  (`cli.py:200-229`, Phase 5's M5.2/M5.3), which owns dispatch, retry
  (`--max-attempts`), lease-based concurrency (M5.4) and resume (`--resume`,
  M5.5) — the bookkeeping `SKILL.md` used to describe by hand.
- `cdp run`'s own docstring (`supervisor.py:183-205`, `run_wave`) states the
  one fact this rewrite is built around: one `cdp run` process dispatches its
  scopes *sequentially*; concurrency across scopes in one wave comes only from
  running a *second* `cdp run` process on a different scope, which the lease
  (M5.4) makes safe. So the rewritten skill recommends one `cdp run --scope
  <node>` per scope, backgrounded, with the wave's leaf subagents still spawned
  in one message — the only way to keep the "concurrent per wave" property
  `SKILL.md` always had, now on top of `cdp run`'s supervision instead of
  hand-rolled `prompts`/`collect` calls.
- Confirmed the prompt/patch path contract is unchanged before promising it in
  prose: `dispatch_scope` (`supervisor.py:141,143`) writes
  `.cdp/prompts/<node with / -> __>.md` and reads
  `.cdp/patches/inbox/<node with / -> __>.json` — byte-identical to what the
  pre-rewrite `SKILL.md` already told a leaf agent to do, so the leaf-agent
  contract itself needed no change, only who calls `collect`/`fold`.
- `FileRunner` (`runner.py:98-100`) — used whenever `cdp run` has no
  `--runner-cmd` — carries its own docstring confirming it *is* "today's
  manual `SKILL.md` loop, made explicit": exactly the behavior the rewrite
  describes, not an invented one.
- The hand-maintained command reference table (11 commands, several already
  stale — no `run`, `doctor`, `link`, `gc`, `compact`, `verify`, `export`,
  `rollback`, `diff`, `reflect`, `lessons`, `answer`, `githook`) is cut down to
  six essentials and now points to `cdp help` for the rest. `cdp help`
  (`cli.py:2220-2239`, `cmd_help`) is generated from the live `argparse`
  parser via `helpdoc.describe`, so — unlike a hand-written table — it cannot
  drift from the CLI it describes; this is a real existing mechanism, not one
  invented for this rewrite. `cdp help --json` is the same surface as data,
  matching the plan's note that LangGraph/ADK adapters bootstrap from it
  (7.4, unbuilt).

**Not delivered this session, stated rather than silently dropped:** the
`--runner-cmd` real-model path is described in prose only; it was not
exercised against a real subprocess runner this session (Phase 6's
`scripts/claude_leaf_runner.sh` real-model exercises already cover that
composition elsewhere in this file). No fixture or `$TARGET_REPO` scan was
needed for a pure-docs change — `make check TARGET_REPO=...` (below) is run
only to confirm the docs edit changed nothing about `scan`/`fold`/`golden`,
since no command reads `SKILL.md`.

`make check TARGET_REPO=/Users/sharmp49/git/code_scanner`: **519 tests
green, determinism (fixture+target), `fold --check` (fixture+target),
golden (fixture+target) all green, byte-identical, no re-bless needed** —
expected: a pure `SKILL.md` edit, and no command reads `SKILL.md`.

---

## Phase 9 (M9.4 pre-work) — interface-adapter scaffold, ahead of MCP/LiteLLM/agent-adapter implementation

Not a plan milestone by number — a structural pass requested ahead of M9.4's
real adapters, so their eventual code has a place to land that's already
excluded from `cdp install`'s vendored copy and already wired into a test
target that can't break `make check` for anyone without their optional
dependencies installed. Three empty-but-real top-level packages created:
`mcp_server/`, `litellm_adapter/`, `agent_adapter/` — each a stub `__init__.py`
(one docstring, no placeholder API) plus a `tests/` dir with a scaffold test
that imports the package and skips cleanly if its real optional dependency
(`mcp`/`litellm`/`langgraph`/`google.adk`) isn't installed.

**D40 — named `agent_adapter/`, not `langgraph_adapter/`, on the user's own
steer.** LangGraph and ADK are commonly combined in one real agent (ADK for
runtime/session, LangGraph for the graph/state machine), so a
LangGraph-specific name would misdescribe the package once ADK support lands
too. `agent_adapter/` is the neutral home for both, expected to grow sibling
entry points (`agent_adapter/langgraph.py`, `agent_adapter/adk.py`) rather
than one framework-generic shim — the two integration surfaces are not the
same shape.

**D41 — `mcp_server/`/`litellm_adapter/`, not the plan's literal `mcp/`/
`litellm/`, because the literal names would shadow their own real
dependency.** `run.py` inserts its own directory (repo root) at
`sys.path[0]`, and `python3 -m` does the same via `cwd` — so a local
directory named `mcp` would resolve before the real `mcp` PyPI package for
any code executed from the repo root, and a package inside it that tries
`import mcp` would import itself. Confirmed by reasoning about `sys.path`
order rather than assumed; not reproduced with an actual shadow-and-crash,
since nothing inside the stub imports anything yet. Caught before writing any
files, not after.

**New enforcement, not previously possible: `tests/test_core_purity.py`.**
"Core imports no framework, ever" was true only by discipline before this
pass — nothing stopped `cdp/` from importing `mcp`/`litellm`/`langgraph`
directly. This test `ast.parse`s (never executes, so an import's side effect
can't fire just from being checked) every `cdp/**/*.py` and fails naming
every forbidden import's `file:line`, accumulating all violations rather than
stopping at the first (same style as `test_distribution.py`). Verified it
actually discriminates, not merely trusted to pass because the real tree is
currently clean: called `_violations()` directly against a temp file
containing `import litellm` and `from google.adk import Agent` and confirmed
both were caught, with line numbers. A first attempt — editing a real
`cdp/util.py` in place and running `unittest test_core_purity` — crashed
before the check ever ran: `tests/helpers.py` eagerly imports several `cdp`
submodules, one of which transitively imported the doctored file, raising a
real `ModuleNotFoundError` at collection time rather than exercising the
ast-based check. Reverted immediately; the isolated call above is what
actually verifies the mechanism.

**Packaging (`pyproject.toml`).** `mcp_server`, `litellm_adapter`,
`agent_adapter` added to `[tool.setuptools] packages`; three new
`[project.optional-dependencies]` entries (`mcp`, `litellm`, `agent`) left
empty pending real code, mirroring the existing `postgres` extra's own
lazy-import pattern and comment style. Base `dependencies = []` untouched —
the property this whole pass protects.

**Testing (`Makefile`).** New `check-interfaces` target (three
`unittest discover` calls, one per package), deliberately **not** added to
`check`'s dependency list, so `make check` — the contract every phase keeps
green — never depends on an optional adapter's test environment being
present.

**Vendoring confirmed excluded, not just stated.** `cdp/cli.py`'s
`DIST_MEMBERS` is unchanged (a comment was added above it naming the three
packages and why they're absent); `cdp install --self` + a fresh
`tests/test_distribution.py` run confirms the vendored
`.claude/skills/cdp/` copy contains none of the three new directories.

**Verification, all before freezing:**
- `make check-interfaces`: 7 tests across the three packages, 5 skipped
  (their real optional deps aren't installed here), 0 failed.
- `cdp selftest`: **520 tests** (up from 519 — `test_core_purity`'s one
  test), all green, including the vendored-copy check after re-running
  `cdp install --self` to pick up the new source file.
- `python3 -c "import cdp"` and `import mcp_server, litellm_adapter,
  agent_adapter`: all four import cleanly with zero third-party packages
  installed.
- `make check TARGET_REPO=/Users/sharmp49/git/code_scanner`: **520 tests
  green (up from 519), determinism (fixture+target), `fold --check`
  (fixture+target), golden (fixture+target) all green, byte-identical, no
  re-bless needed** — confirms nothing about core's own behaviour moved;
  this pass touches no file `scan`/`fold`/`golden` reads, only new sibling
  packages, one new core-only test, and comments.

---

## Phase 9 (M9.4, 7.1 only) — MCP server, real tools, no real SDK to test against

**Scoped to 7.1 only**, asked before implementing (LiteLLM/strict mode/
`AGENTS.md` remain each their own session's worth — same posture the M9.1-M9.3
sessions and the M9.4 `SKILL.md`/scaffold sessions above already took).

**D42 — `query.dispatch` extracted from `cmd_query` into `query.py` itself,
before writing any MCP code.** The alternative was letting `mcp_server`
duplicate `cmd_query`'s ~15-line `if kind == ...` ladder, which is exactly the
kind of second copy that drifts (the same argument D41 already makes about
naming, applied to logic instead of a directory name). `query.dispatch(store,
kind, term, **kwargs)` is now the one place that maps a `kind` to the right
`QUERIES[kind]` call; `cli.cmd_query` calls it and raises `CdpError` on the
`ValueError`s it raises (`query %s needs a term`, the never-budgeted check),
preserving the CLI's existing error text and exit behaviour exactly.
`tests/test_pipeline.py`'s `test_query_answers_from_a_fresh_scan` (and the
rest of the suite) passed unchanged, confirming the refactor is behaviour-
preserving, not just plausible.

**What shipped, three files, no `mcp` SDK dependency in two of them:**

- `mcp_server/tools.py` — `cdp_query`/`cdp_scan`/`cdp_status` as plain
  functions. Repo/state-dir resolution reuses `cli._paths`/`_open_store`
  (same `.cdp.toml` -> registry -> cwd/.cdp order, D3) rather than
  reimplementing it, so a tool answers from the same store a `cdp`
  invocation in that directory would. `cdp_scan` calls `cli.cmd_scan`
  directly (the real pipeline, not a reimplementation) with `docs=False`
  (skip markdown rendering — a tool call has no use for it) and returns
  `query.dispatch(store, "stats")` against the freshly-scanned store, since
  a scan has no single natural return value of its own. `cdp_status`
  reconstructs the exact dict `cmd_status` prints as text (coverage,
  freshness buckets via `freshness.bucket_counts`, this run's task rows via
  `store.backend.task_rows`) rather than shelling out to the CLI and parsing
  its stdout back.
- `mcp_server/schemas.py` — the three tools' descriptions/JSON schemas, and
  `estimate_at_rest_tokens()`: chars/4 over each tool's `name` +
  `description` + `inputSchema`, the **same estimator** `cdp prompts
  --measure` already uses (`cdp.prompts.CHARS_PER_TOKEN_EST`), so this
  number and that one are comparable rather than two independently-invented
  units. **Measured: 649 tokens_est for all three tools** (378/167/104
  per tool) — against the plan's own 13-tool/49.2k-token reference point,
  not asserted to be small. A synthetic 13-tool schema set (10 copies of
  `cdp_query`'s schema appended) costs >3x the real 3-tool number under the
  same estimator — the plan's own stress-test row ("MCP tool count grows to
  13 ... the token-at-rest objection returns in full") reproduced
  mechanically, kept as a permanent test rather than a one-off calculation.
- `mcp_server/server.py` — the real `mcp.server.Server` wiring
  (`create_server`/`main`), **written against the SDK's documented shape but
  not run against it**: `mcp` is not installed in this environment
  (confirmed: `python3 -c "import mcp"` -> `ModuleNotFoundError`). Per
  `PHASE/EXECUTION_RULES.md` R-E6 (design for the uncertainty rather than
  guess further), the risk is isolated to this one file's SDK-facing half —
  `_call(name, arguments)`, the dispatch `list_tools`/`call_tool` delegate
  to, carries no SDK import and is fully tested. `create_server()` raises a
  clear `ImportError` naming `pip install cdp[mcp]` when the SDK is absent
  (verified: this is the path this session's own test suite actually
  exercises), rather than a server silently missing tools.

**Verified, all before freezing:**
- `make check-interfaces` (`mcp_server`/`litellm_adapter`/`agent_adapter`):
  10 + 2 + 3 tests, all green (5 skipped for absent optional SDKs, as before).
- **Real-target exercise (R-E7), not just the fixture:** `sql-pool/sql-pool-api`
  via `tools.cdp_scan`/`cdp_query`/`cdp_status` directly (no CLI subprocess) —
  `scan claims 41 symbols 413 scopes 2`, `unknowns 0`, `status run_id
  cdp-7e10575adf69 head 7e10575adf69` — the exact 41-claim/413-symbol numbers
  Phase 4's own real-target exercises recorded for this module, confirming
  the tool layer answers identically to the CLI it wraps rather than a
  silently-different number. Scratch state dir removed after.
- `make check TARGET_REPO=/Users/sharmp49/git/code_scanner` (launched after
  freeze, result recorded once it completes — see below) is the confirmation
  that `query.dispatch`'s extraction changed nothing about `cmd_query`'s
  observable behaviour and that the new `mcp_server` files (outside `cdp/`)
  changed nothing about `scan`/`fold`/`golden`.

**Not delivered this session, named rather than silently dropped:** the real
MCP transport (`create_server`/`main`) run against an actual `mcp` client;
LiteLLM adapter, strict mode, `AGENTS.md` (M9.4's other four items, each
scoped down and asked about in this same session before picking MCP first).

`make check TARGET_REPO=/Users/sharmp49/git/code_scanner`: **520 tests
green, determinism (fixture+target), `fold --check` (fixture+target), golden
(fixture+target) all green, byte-identical, no re-bless needed** — confirms
`query.dispatch`'s extraction is behaviour-preserving and the new
`mcp_server` files changed nothing about `scan`/`fold`/`golden`.

---

## Phase 9 (M9.4, strict mode only) — blocks the first source read, gated on coverage *and* HEAD

**Scoped to strict mode only**, asked before implementing (LiteLLM adapter,
`AGENTS.md`, LangGraph/ADK adapters — the plan's other three remaining M9.4
items — each still their own session's worth, same posture every prior M9.4
session took).

**What shipped, in `cdp/hook.py` (the existing PreToolUse nudge, extended, not
replaced) and `cdp/cli.py`:**

- The nudge's gating logic (state reachable, `inventory.head == git HEAD`,
  role `source`) was extracted from `decide()` into a new `_gate(event)`
  helper that also reads `state.json`'s `coverage.fraction` while the store is
  already open — one code path both the existing nudge and the new strict
  path share, rather than two copies that drift.
- `strict_decide(event)` reuses `_gate` and the same one-shot
  `claim_session` marker `decide()` already uses, so a block (or the nudge it
  degrades to) fires **at most once per session**, exactly the plan's own
  "triggers at most once per session, never gets stuck" — copied as a
  constraint, not just a phrase. It returns `{"block": True, ...}` only when
  `coverage.fraction >= STRICT_MIN_COVERAGE` (new constant, **0.95** — an open
  decision this plan explicitly left unset, picked high because blocking is
  the higher-cost mistake of the two directions); otherwise `{"block": False,
  ...}`, the ordinary nudge text.
- **The stress test named in the plan** ("Strict mode at 100% coverage but
  stale index") is enforced by construction, not just tested: `_gate` already
  returns `None` the moment `inventory.head != git HEAD`, before
  `strict_decide` ever looks at coverage, so a stale-but-fully-covered index
  degrades to silence, never a block. `tests/test_hook.py`
  `test_full_coverage_but_stale_head_still_degrades_to_a_nudge` pins it.
- `payload(message, block=False)` grew the block half of the PreToolUse
  contract: `permissionDecision: "deny"` + `permissionDecisionReason`, which
  the existing nudge path never sets (still no `permissionDecision` at all,
  same as before — `test_payload_reports_no_permission_decision` unchanged).
  **Not verified against a live harness** — same posture the module's own
  docstring already takes toward `additionalContext`: `mcp_server`'s
  MCP-SDK-facing half was "written against the documented shape, not run
  against it" for the identical reason (nothing in this environment can fire
  a real PreToolUse block to observe the result). Named as unverified rather
  than asserted.
- `cdp install --hook --strict` (`cli.py`) writes `args: ["--strict"]` on the
  installed hook entry; `hook.main()` reads `"--strict" in argv` and calls
  `strict_decide` instead of `decide`. Re-running `install --hook` with a
  different `--strict` choice **updates the existing entry's args in place**
  rather than leaving the stale choice (a real gap in the pre-existing
  idempotency check, found while wiring this: it matched by `command` string
  alone and never touched `args`) — `tests/test_hook.py`
  `test_install_strict_writes_the_flag_and_reinstall_updates_it` covers both
  directions.

**Verified, not assumed:**
- `tests/test_hook.py`: 7 new tests (`StrictModeTest`, plus one each in
  `HookSafetyTest`/`InstallHookTest`) — below-threshold degrades, full
  coverage blocks, full-coverage-but-stale-HEAD still degrades (the named
  stress test), one-shot-per-session holds for a block too, the real CLI
  subprocess with `--strict` emits `permissionDecision: "deny"`, and the
  install/reinstall args-update roundtrip. All 22 pre-existing `test_hook`
  tests pass unchanged (the refactor into `_gate` is behaviour-preserving).
- **Real-target exercise (R-E7), not just the fixture:**
  `sql-pool/sql-pool-api` scanned fresh into a scratch dir (real coverage
  0.0 — a bare `scan` with no agent dispatch, matching the earlier real
  fixture reading exactly). `strict_decide` against the real, previously
  unseen `ServerResource.java` path returned `{"block": False, ...}` — the
  honest degrade, not forced. The same store's `state.coverage.fraction` was
  then set to 1.0 directly (the only way to exercise the block branch without
  a live multi-agent `cdp run`, which this session's budget does not include)
  and the identical call returned `{"block": True, "message": "Blocked: the
  index covers 100% of this repository at 7e10575adf69..."}` — a real repo
  path, a real commit sha, a real file, both directions proven on the same
  scan. Scratch directory removed after the exercise.

**Not delivered this session, named rather than silently dropped:** a live
harness firing a real `PreToolUse` block and confirming Claude Code actually
refuses the read (no such harness is reachable from inside this session);
`STRICT_MIN_COVERAGE`'s value (0.95) is a judgment call, not derived from any
labelled corpus — Phase 9's holdout/benchmark machinery (M9.2/M9.3) has
nothing yet that grades a *blocking* threshold, only claim quality, so there
is no data this session could have fit it to.

`make check TARGET_REPO=/Users/sharmp49/git/code_scanner`: **527 tests green
(up from 520 — the 7 new strict-mode tests), determinism (fixture+target),
`fold --check` (fixture+target), golden (fixture+target) all green,
byte-identical, no re-bless needed** — confirms `hook.py`'s `_gate`
extraction is behaviour-preserving and strict mode changed nothing about
`scan`/`fold`/`golden`, since no existing command calls the new code paths.

---

## Phase 9 (M9.4, §7.9 only) — Tier-0 `AGENTS.md`, exercised on a real module

Scoped to §7.9 only, asked before implementing (same posture every prior
M9.4 session took): LiteLLM adapter (7.2) and LangGraph/ADK adapters (7.4)
remain docstring-only stubs, each its own session's worth.

**Where it lives, and why not inside `DIST_MEMBERS`.** A root-level
`AGENTS.md` is the convention Cursor/Codex/Copilot/Aider actually read —
none of them look inside `.claude/skills/cdp/`. `DIST_MEMBERS`
(`cdp/cli.py:2260`) is copied to `<target>/.claude/skills/cdp/`, the wrong
place for this file, so `cmd_install` gained a second, separate copy step
that writes `<target>/AGENTS.md` directly, alongside the existing
`.claude/agents/cdp-leaf.md` copy.

**Never overwritten, on purpose** — the same posture `githook install`
already takes toward a foreign hook (`PHASE/FINDINGS.md`, Phase 3 M3.8): an
`AGENTS.md` already present is the operator's own file, and `install`
prints `kept ... (already present, not overwritten)` rather than silently
replacing it. Verified against this repository's own re-install
(`cdp install --self`): the root `AGENTS.md` this session created was left
untouched, confirmed by the printed line above.

**Content**: the Tier-0 question→command table, reproduced from
`SKILL.md:35-46` per the plan's own citation, plus the coverage-before-
absence and stale-index rules `SKILL.md` already states for a hook-capable
session — the same rules apply with no hook to enforce them, just stated as
guidance instead of a block.

**Verified, not assumed:**
- `tests/test_distribution.py` `AgentsMdInstallTest` (2 new tests): a fresh
  target gets `AGENTS.md` with the expected command table; a target with its
  own pre-existing `AGENTS.md` keeps it byte-for-byte.
- **Real-target exercise (R-E7):** `sql-pool/sql-pool-api` copied into a
  scratch target directory, `cdp install <target>` run against it (not
  `--self`) — printed `wrote .../AGENTS.md`. Then, simulating exactly what a
  hook-less assistant does — no `cdp` CLI, no Claude Code, just the two shell
  commands the new file itself documents — `python3
  .claude/skills/cdp/run.py scan --repo sql-pool-api` and `... query stats`
  were run directly from that target directory and produced a real,
  correct census (48 tracked files, 1 module, 41 claims, 2 unknowns) —
  concrete proof the Tier-0 path needs nothing beyond a shell and Python
  3.9, the plan's own claim for this item. Scratch directory removed after.

**Not delivered this session, named rather than silently dropped:** no live
non-Claude assistant (Cursor/Codex/Copilot/Aider) was available to fire an
actual session against this file — the exercise above stands in for "any
assistant that can run a shell command" by running the shell commands
directly, which is the whole content of the Tier-0 claim, but it is not the
same as watching a real Cursor/Aider session read `AGENTS.md` and act on it.
LiteLLM adapter (7.2), LangGraph/ADK adapters (7.4), and the MCP server's
still-open "3 tools" cap (7.1, already shipped, not re-litigated here)
remain the rest of M9.4.

`make check TARGET_REPO=/Users/sharmp49/git/code_scanner`: **529 tests green (up from 527 — the 2 new AgentsMdInstallTest cases), determinism (fixture+target), `fold --check` (fixture+target), golden (fixture+target) all green, byte-identical, no re-bless needed** — confirms the new install step is additive and changed nothing about `scan`/`fold`/`golden`'s own pipeline.

---

## Phase 9 (M9.4, 7.2 only) — LiteLLM adapter, real preflight against a real subprocess pipeline

Scoped to 7.2 only (LangGraph/ADK adapters, 7.4, remain the one unstarted
M9.4 item, still its own session's worth — same posture every prior M9.4
session took). `litellm` is not installed in this environment (`python3 -c
"import litellm"` -> `ModuleNotFoundError`), so this session follows the
`mcp_server.server` precedent exactly: isolate the SDK-facing call into one
function, test everything else without the SDK present.

**What shipped, `litellm_adapter/__init__.py`:**

- `_complete(model, prompt_text, ...)` — the only line that imports
  `litellm`. Raises a clear `ImportError` naming `pip install cdp[litellm]`
  when absent (verified: this is the path this session's own tests
  actually exercise, same as `mcp_server.server.create_server`).
- `LiteLLMRunner` — the `Runner` protocol (`cdp/runner.py`:
  `run(prompt_path, patch_path) -> RunResult`). No exception escapes `run()`
  (runner.py Rule 1) — an SDK exception, a malformed response shape, and a
  missing prompt file are all caught and returned as `RunResult(ok=False,
  error=...)`, verified by three separate tests each forcing one of those
  paths via a stubbed `_complete`. Unparseable model output is `ok=True`
  with no patch written — matching runner.py's own contract exactly
  ("a well-formed-but-wrong patch is `collect`'s job... not the runner's");
  `cdp run` is what classifies an absent patch as yield collapse, not this
  adapter. Reuses `cdp.doctor._extract_json` for the "outermost `{...}`
  span" parse rather than a second copy (same reuse argument D42 already
  makes).
- `preflight(model)` — the answer to this milestone's own stress test
  ("LiteLLM to a local 8B that collapses -- `doctor` catches it. Verify the
  adapter surfaces `doctor`'s verdict before a full run, not after."):
  shells out to the real `cdp scan` then `cdp doctor --runner-cmd "python3
  -m litellm_adapter --model <model>"` against `tests/fixtures/minirepo` in
  a scratch state dir, and returns the real aggregate verdict
  (`schema_validity_rate`/`yield_collapse_rate`/`recall`/
  `false_unknown_rate`) plus an `ok` bit. Reuses the actual doctor harness
  rather than re-deriving inventory/extraction/xref/schedule by hand — the
  same "one place, not a second copy" argument as `_extract_json` above,
  one level up.
- `python3 -m litellm_adapter --model M prompt.md patch.json` (`__main__.py`
  + `_run_argv`) — the `SubprocessRunner` shape `cdp run --runner-cmd`/`cdp
  doctor --runner-cmd` already expect, same convention as
  `scripts/claude_leaf_runner.sh`. `--preflight` prints the verdict JSON and
  exits nonzero on failure, so a caller can gate a real `cdp run` invocation
  on it from a shell (`litellm_adapter --preflight --model M && cdp run
  --runner-cmd "..."`).

**Real-input exercise (R-E7), not just stubbed unit tests — and it is
exactly the stress test's own scenario, not a synthetic stand-in for it.**
`preflight("fake-model-no-such-provider")` was run for real: real
subprocess `cdp scan` of `tests/fixtures/minirepo`, real subprocess `cdp
doctor` dispatching a real `SubprocessRunner` that shells out to `python3 -m
litellm_adapter`, which correctly raises the `ImportError` (no `litellm`
installed) and reports a runner-level failure back through `doctor_scope`.
`preflight` returned `ok: False` — the model can't even be called, in a
harness with no local 8B to actually collapse, but this is the identical
shape doctor would report for one that does: `schema_valid=False,
runner_ok=False`. This proves the whole preflight pipeline end to end
(three real subprocesses chained, scratch state dir, real fixture) rather
than only proving `LiteLLMRunner.run()`'s error handling in isolation.

**Verified, all before freezing:**
- `make check-interfaces`: `litellm_adapter` now 9 tests (up from 2 scaffold
  tests), 1 skipped (`litellm` genuinely absent), 0 failed; `mcp_server`
  (10) and `agent_adapter` (3, still scaffold-only) unchanged.
- `python3 -m litellm_adapter --model x prompt.md patch.json` run directly
  (not through a test) against a real prompt file from an actual
  `tests/fixtures/minirepo` scan: printed the expected `ImportError` message
  to stderr and exited 1 — the CLI entry point itself behaves correctly
  under the SDK-absent condition, not only when driven through `unittest`.
- `cdp install --self`: confirmed (per `DIST_MEMBERS`'s comment, D41)
  `litellm_adapter/` is still absent from the vendored
  `.claude/skills/cdp/` copy — this adapter stays outside the zero-dependency
  distribution, same as `mcp_server`/`agent_adapter`.
- `pyproject.toml`'s `litellm` extra changed from `[]` to `["litellm"]` —
  the one line that stops being a placeholder now that real code depends on
  it; `mcp`/`agent` stay `[]`, unchanged, since those two adapters are still
  stubs.
- `make check TARGET_REPO=/Users/sharmp49/git/code_scanner` (launched after
  freeze, result recorded once it completes — see below) is the
  confirmation that this adapter, entirely outside `cdp/`, changed nothing
  about `scan`/`fold`/`golden`'s own pipeline.

**Not delivered this session, named rather than silently dropped:** a real
call against an actual LiteLLM-routed model (local or hosted) — `litellm`
is not installed here, so `LiteLLMRunner.run()`'s real HTTP/subprocess path
through the SDK is written against its documented `completion(...)` shape
but not run against it, the same posture `mcp_server.server`'s SDK-facing
half already takes. LangGraph/ADK adapters (7.4) remain the one fully
unstarted M9.4 item — `agent_adapter/` is still scaffold-only.

`make check TARGET_REPO=/Users/sharmp49/git/code_scanner`: **529 tests
green (unchanged — this session's new tests live in `litellm_adapter/`,
which `check-interfaces`, not `check`, runs), determinism (fixture+target),
`fold --check` (fixture+target), golden (fixture+target) all green,
byte-identical, no re-bless needed** — confirms the adapter, entirely
outside `cdp/`, changed nothing about `scan`/`fold`/`golden`'s own pipeline.

---

## Phase 9 (M9.3, 6.8 only) — holdout A/B, the missing lesson-consumer found and built to make it measurable

Asked before implementing (per R-E13): attempt 6.8 or defer it, given its own
class ("independently as large as M9.1/M9.2") and this session's 20-minute
budget. User chose attempt.

**A defect surfaced immediately, before any holdout code was written**:
`--lessons vN`/`--no-lessons` were wired into `cdp run`'s manifest
(`cli.py:1468-1476`) but nothing ever *read* a loaded lesson-set to change
behaviour — `apply_lessons` did not exist. A holdout A/B of a no-op is a
measurement of nothing, so this session's first real work was building the
consumer 6.7/6.8 both assumed already existed:

- `reflect.apply_lessons(lessons)` (new): turns cut, pinned promotion rows
  into the two routing knobs `prompts.py`/`graph.py` actually expose --
  `import_channel_hint` patterns (unioned) and a `max_inherited` override
  (last `budget_change` wins, append order). `prompt_fix` promotions round-trip
  through but are not yet consumed anywhere (no code renders `instruction`
  into a prompt section) -- named, not silently dropped.
- `graph._looks_third_party(fqn, extra_patterns=())` / `tiering.compute_tier`
  / `tiering.scope_unresolved_imports` all gained the same `extra_third_party`
  parameter, threaded through `prompts.build_prompt` -> `cdp prompts
  --lessons vN` and `supervisor.dispatch_scope`/`run_wave` -> `cdp run`
  (which already resolved `lessons_version`; it now also calls
  `apply_lessons` and passes the hints through). This is the one lever a
  lesson can pull today, and it is exactly the real gap `TARGET.md`'s M6.4
  finding named: `com.rms.auth.framework.*`/`org.mapstruct.*` are real
  third-party roots this repo's `graph._looks_third_party` hardcoded list
  does not recognise -- an `import_channel_hint` lesson is the mechanism
  meant to close that, at routing time, never at claim-content time (R10).

**Promotion gating (6.8's own point — a cut is not "latest" for free):**
`trajectory.py` gained a `lesson_cut` table (`promoted` bit,
`holdout_repo`, `holdout_metric`). `cut_lessons()` now inserts an
unpromoted row; `latest_lesson_version()` only returns a *promoted* version
(a regression from the pre-6.8 semantics, deliberately -- the existing
fixture test asserting `latest_lesson_version()==1` right after a bare cut
was updated to reflect the new gate, `tests/test_trajectory.py`
`LessonSetTest`). `--lessons vN` still pins an unpromoted cut explicitly,
same as before.

**The A/B itself (`cdp holdout --lessons vN`, new command), and the open
decisions this milestone named but declined to settle in advance:**

- **Metric, decided here:** T3-escalation rate under `tiering.compute_tier`,
  with vs without the cut's `import_channel_hint` patterns applied, over
  every scope of the holdout repo's own already-completed scan. Chosen
  because it needs **zero live model calls** — the tiering rule is
  deterministic by construction (M6.4) — matching 6.5's own "no model
  involved" posture and keeping the whole A/B inside this session's budget.
  The plan's own stress test ("verify the split is real") is the harder
  requirement this milestone actually meets; the benchmark-coverage version
  of 6.8 (live models, `benchmarks/run_benchmark.py`, a repo pair large
  enough to need real A-E/F selection) is **not** attempted here and remains
  open, named rather than faked.
- **Split-is-real check, decided here:** `trajectory.learned_repos_for_cut`
  joins `lesson_promotion.run_id -> fact_leaf_run.run_id -> dim_repo`; `cdp
  holdout` refuses outright (`CdpError`, nonzero exit) if the target repo's
  own `repo_identity` appears in that set — "a repo outside the learning
  set" enforced, not merely asserted. Exercised for real:
  `tests/test_holdout.py::test_holdout_refuses_a_repo_in_the_cuts_own_learning_corpus`.
- **Promotion bar, decided here:** the cut must not *increase* T3 rate on
  the holdout repo (`after <= before`); an increase would mean the pattern
  overfits the learning corpus rather than naming a real third-party root.
  **Caveat, found by reasoning about the metric rather than hidden after
  the fact:** with only `import_channel_hint` hints in play, T3 rate is
  *structurally monotonic non-increasing* — a hint can only turn an
  already-unresolved import into a recognised one, never the reverse — so
  the REJECT branch of this bar is currently unreachable in practice. It
  remains real code (a `budget_change`/`prompt_fix`-driven regression is a
  different, not-yet-built, path), but the promotion bar as shipped cannot
  presently be exercised on its failing side without a second, adversarial
  lesson kind this session did not build.
- **What "regression on the holdout triggers"**, the plan's third open
  question: nothing beyond non-promotion. `latest_lesson_version()` simply
  stays at whatever the last *promoted* cut was; `cdp run`'s default
  behaviour is unaffected. No rollback/alerting mechanism was asked for or
  built.
- **Cut cadence** remains genuinely open, unaddressed this session (no
  scheduling code, manual `cdp lessons cut` only) — same as every prior
  M9.3 session recorded it.

**Verified, all before freezing (R-E3):**
- `tests/test_reflect.py::ApplyLessonsTest` (4 new tests): pattern union,
  last-budget-change-wins, prompt_fix round-trips with no claim-shaped
  field, empty-lessons no-op.
- `tests/test_trajectory.py::HoldoutSplitTest` (1 new test) +
  `LessonSetTest`'s updated assertion (promote_cut required before
  `latest_lesson_version` moves).
- `tests/test_holdout.py` (2 new tests, real subprocess end-to-end, two
  *distinct* real fixture repos — `minirepo` as the learned repo,
  `solorepo` as the holdout, never the same directory): a real promotion
  recorded only against `minirepo`, cut, `cdp holdout --repo solorepo
  --lessons 1` promotes it, and a subsequent real `cdp run --repo solorepo`
  (no `--lessons` flag) picks up v1 as the default latest, confirmed by its
  own printed `lessons   pinned v1` line. The second test confirms the
  same-repo refusal against a real scan, not a mocked one.
- **Real-target exercise (R-E7):** `sql-pool/sql-pool-api` scanned fresh
  into `/tmp/m98_scratch` (removed after); a synthetic promotion recorded
  against a *different*, fake repo id; `cdp holdout --repo
  sql-pool/sql-pool-api --lessons 1` ran against this real target module,
  printed `T3 rate 1.000 (none) -> 1.000 (lessons) -- PROMOTE`, and
  promoted the cut. The rate did not move on this specific module — expected,
  since M6.4's own finding already established this module's T3 scopes have
  other unresolved imports independent of the one tested pattern — but the
  full real pipeline (scan, promotion recording, cut, deterministic A/B,
  promotion write) ran end to end against real target data without error.

**Not delivered this session, named rather than silently dropped:** the
live-model, `benchmarks/run_benchmark.py`-style holdout (coverage A-E vs F)
that the plan's own prose leans toward is not built — the deterministic
tiering-rate A/B above is the real, budget-compatible substitute this
session chose and is defensible against R10 and the stress table, but it is
a narrower instrument than a full benchmark comparison. `prompt_fix`
promotions are validated, cut, and round-tripped but not yet rendered into
an actual prompt section. Cut cadence remains unaddressed. LangGraph/ADK
adapters (7.4) remain the one fully unstarted M9.4 item — the plan itself
calls 7.4 "on demand" and it is not named in Phase 9's own exit criteria,
so it was not attempted this session.

`make check TARGET_REPO=/Users/sharmp49/git/code_scanner`: **536 tests green
(up from 529 — the 4 `ApplyLessonsTest` + 1 `HoldoutSplitTest` + 2
`test_holdout` cases), determinism (fixture+target), `fold --check`
(fixture+target), golden (fixture+target) all green, byte-identical, no
re-bless needed** — confirms the tiering/`build_prompt`/`run_wave` threading
this session added is dormant unless a lesson-set is actually pinned, so it
changed nothing about the existing `scan`/`fold`/`golden` pipeline.

## Phase 9 (M9.4, 7.4 only) — LangGraph/ADK adapters, the last named item

Prior sessions closed every other Phase 9 exit criterion; this one was
explicitly asked for by the user even though the plan itself marks 7.4
"on demand" and Phase 9's exit criteria don't name it.

**Design.** `agent_adapter/__init__.py` is the SDK-free core:
`tool_specs()` reuses `mcp_server.tools.TOOLS` (the same
`cdp_scan`/`cdp_query`/`cdp_status` three tools 7.1 already settled as the
right L4 surface) and sources each one's description from `cdp help
--json`'s command summaries (`cdp/helpdoc.describe`) rather than
hand-writing one — a description cannot drift from the CLI it wraps, same
argument `cmd_help` already makes for itself. Raises `KeyError` if `scan`/
`query`/`status` ever disappear from the help surface, rather than silently
dropping a tool. `agent_adapter/langgraph.py` and `agent_adapter/adk.py` are
thin converters: each imports its SDK only inside its one function
(`litellm_adapter`'s `_complete` isolation precedent, R-E6) and both were
verified *not* installed in this environment
(`python3 -c "import langchain_core"` / `"import google.adk"` ->
`ModuleNotFoundError`), so each is written against its SDK's documented
shape — `StructuredTool.from_function(func, name, description)` for
LangGraph/LangChain, `FunctionTool(func)` for ADK (confirmed from ADK's
public docs and GitHub source, not a local install: ADK inspects the
function's own docstring/signature/type hints and takes no separate
description argument) — but neither is executed against the real package.
`pyproject.toml`'s `agent` extra, previously empty, now names
`langgraph`/`langchain-core`/`google-adk`.

**Decision left implicit by the plan, made explicit here:** 7.4 shares
7.1's three-tool surface rather than exposing a wider one (e.g. `answer`,
`refresh`, `run`) at L4. Consistent with the plan's own framing ("RCA,
reviewer agents" — read/query consumers, not orchestration consumers) and
with 7.1's own three-tool cap rationale (`idea`+`pycharm` at 49.2k tokens
at rest) extended to a second interface.

**Tests** (`agent_adapter/tests/test_agent_adapter.py`, 8 cases, run by
`make check-interfaces` not `make check`): `tool_specs()` covers exactly
`mcp_server.tools.TOOLS`'s three names; each spec's description is
non-empty and its `func` is the identical object `mcp_server.tools` holds
(not a copy); a mocked missing help-command raises `KeyError` rather than
silently shrinking the tool set; both wrappers raise a clear `ImportError`
naming the missing package (the only branch exercisable without the real
SDKs).

**Real-target exercise (R-E7):** `tool_specs()['cdp_scan'].func` and
`['cdp_status'].func` called directly (no CLI subprocess, no framework)
against `sql-pool/sql-pool-api` into a scratch state dir: `scan claims 41
symbols 413`, `status run_id/head cdp-7e10575adf69
7e10575adf69a193da7f547aed088f7409f1f7c4` — the identical numbers every
prior Phase 9 real-target exercise of this same module has produced,
confirming this adapter answers from the same code path as the CLI and
`mcp_server`, not a third reimplementation. Scratch directory removed
after.

**Not delivered, named rather than silently dropped:** neither SDK's
`FunctionTool`/`StructuredTool` construction is exercised against the real
package — this environment has neither installed, and installing either
was out of this session's scope. `agent` extra install itself is
unverified. Only the 3-tool L4 surface is wrapped; a wider agent-side
surface (mutating commands) was a deliberate non-goal per the design
decision above, not an oversight.

`make check TARGET_REPO=/Users/sharmp49/git/code_scanner`: **536 tests
green, determinism (fixture+target), `fold --check` (fixture+target),
golden (fixture+target) all green, byte-identical, no re-bless needed** —
`agent_adapter`'s own 8 tests run under `make check-interfaces`, exercised
separately above. Phase 9's exit criteria, including the on-demand 7.4
item, are now all closed.

## Post-Phase-9 follow-up — the "cut cadence" open decision, resolved: a nudge, not an auto-cut

Phase 9's own text left cut cadence unaddressed by design ("open decisions to
make here, not before"). Asked directly: the user's answer is **cutting stays
manual** (`cdp lessons cut`, unchanged) but **every `LESSONS_HINT_EVERY=5`
finished runs** (a global, cross-repo count — `trajectory.finished_run_count()`
over `fact_run_event WHERE event='finished'`, matching the corpus's own
cross-workspace scope, not a per-repo one), `cdp run` prints a one-line nudge
naming how many promotions are pending and the exact command to freeze them,
*only if* something is actually pending — silent otherwise, both off-cadence
and on-cadence-with-nothing-pending.

`cdp/trajectory.py`: new `finished_run_count()` and the `LESSONS_HINT_EVERY`
constant. `cdp/cli.py`: new `_maybe_print_lessons_hint()`, called from both
`cmd_run` exit paths (the `--stale-only` early return and the normal
end-of-wave-groups path) right after the `finished` run event is recorded.

**Tests** (`tests/test_trajectory.py`, 4 new cases): `finished_run_count` is
global across repos and only counts `finished`, not `started`; the hint is
silent off-cadence even with promotions pending; silent on-cadence with
nothing pending; and on-cadence with pending promotions it names the count
and `cdp lessons cut` verbatim.

**Real-target exercise (R-E7).** `sql-pool/sql-pool-api` scanned fresh into
`/tmp/hint_scratch` (removed after); `cdp run --wave-all` driven five times
through a real external `--runner-cmd` fake runner against this real module
(each real end-to-end `cmd_run` invocation, not a synthetic event insert) —
`finished_run_count()` read back as exactly 5. A pending promotion was seeded
directly (no `cdp reflect` call spent — reflection itself is orthogonal to
this milestone) and `_maybe_print_lessons_hint` against that real store
printed:

    lessons   1 promotion(s) pending after 5 runs -- `cdp lessons cut` to freeze them

Scratch directory and its trajectory DB removed after the exercise (this
change writes to `~/.cdp/trajectories.db` by default in normal operation;
the exercise used `CDP_TRAJECTORY_DB` override to avoid touching the real
one).

`make check TARGET_REPO=/Users/sharmp49/git/code_scanner` (launched after
freeze, result recorded once it completes — see below) is the confirmation
that this additive change to `cmd_run`'s end-of-run path didn't move
anything in the `scan`/`fold`/`golden` pipeline, since the hint fires only
inside `cdp run`, which that pipeline never invokes.

`make check TARGET_REPO=/Users/sharmp49/git/code_scanner`: **540 tests
green (up from 536 — this session's 4 `LessonsHintTest`/`finished_run_count`
cases), determinism (fixture+target), `fold --check` (fixture+target),
golden (fixture+target) all green, byte-identical, no re-bless needed.**

## Post-Phase-9 follow-up — the live-model holdout (M9.3, 6.8's other half), built, and two real bugs it found

The deterministic T3-rate `cdp holdout` only proves a lesson doesn't worsen
tiering escalation; asked directly, the user chose to spend real API budget
building the coverage-based A/B the plan's own prose leans toward, on the
real held-out module `sql-pool/sql-pool-api` (never in any cut's own
`learned_repos_for_cut`), with a real, seeded `import_channel_hint` cut
(`com.rms.auth.framework`, `org.mapstruct` — the exact two previously-
unrecognised third-party roots M6.4's own finding named for this module).

**Why this needed a new script, not just re-running `run_benchmark.py`:**
unlike the deterministic holdout (pure SQL over already-scanned state),
lessons only steer leaf *dispatch* (`build_prompt`/tiering), so a real A/B
needs the held-out module scanned and leaf-dispatched **twice** with a real
model — once `--lessons none`, once with the cut pinned — before either
state exists to benchmark. `benchmarks/run_live_holdout.py` (new, out of
core, same posture as `run_benchmark.py`): seed + cut a lesson into a
**scratch** trajectory DB (`--trajectory-db`, never `~/.cdp/trajectories.db`),
dispatch both arms with a real `haiku` leaf model via the existing
`scripts/claude_leaf_runner.sh`, then benchmark each resulting state with a
small hand-verified 3-question gold set (`benchmarks/holdout_live_questions.json`)
using a real haiku reader + sonnet judge, mirroring `run_benchmark.py`'s own
`coverage_of` scoring.

**Bug 1 (real, found on the first live dispatch, fixed): the leaf agent
prompt never stated the schema's own anchor length ceiling.** Both scopes of
`sql-pool-api` came back `abandoned` after 3 attempts each — every attempt's
`evidence[].anchor` exceeded `schema/patch-1.0.0.json`'s `maxLength: 400`
(the anchor def states a **12-char minimum** prominently but never mentions
400). `agents/cdp-leaf.md` (canonical source — NOT `.claude/agents/` or
`.claude/skills/cdp/agents/`, which are install/vendor targets `cdp install
--self` overwrites) now states the ceiling explicitly and tells the model
"two or three lines is normally enough — never quote a whole method body."
Re-dispatching the identical prompt/model/module after the fix: both scopes
`validated`, zero abandons. Propagated via `cdp install --self` to both
downstream copies.

**Bug 2 (real, found on the first live benchmark run, fixed): the reader
model could read the gold-fact file directly and did.** `run_live_holdout.py`
initially granted `Read,Grep,Glob,Bash` (`run_benchmark.py`'s own tool list)
— fine for M6.2, whose target repo was a separate checkout, but this harness
runs with cwd inside **this** repo, which also contains
`benchmarks/holdout_live_questions.json`. Arm A's first h03 answer opened
with "Based on the benchmark questions in the repository" — the model had
read its own gold answers off disk, not from `cdp query`. Fixed by dropping
to `--tools Bash` only (still `--allowedTools Bash(*cdp.cli*)`), forcing
every answer through the actual query surface. Re-run after the fix produced
materially different, lower numbers for both arms — confirming the first
run's coverage was contaminated, not measuring anything real.

**Result (post-fix, the real one):** `coverage 0.444 (none) -> 0.167
(lessons) — REJECT`. Not promoted. Read at face value this says the lesson
hurt; the honest caveat, stated rather than hidden: **n=3 questions, one
sample per arm, no repeat sampling** — h03 (the one question the lesson
should plausibly move, since it asks exactly about the two hinted packages)
scored **0.0 in both arms**, because neither arm's model found a `cdp query`
subcommand that surfaces third-party imports at all (a real capability gap,
independent of lessons — imports.json / symbol tables are built for
internally-defined symbols, not for naming what a scope imports from
outside). h02's swing (1.0 -> 0.0-then-clarifying-question) looks like
single-call model variance (a haiku reader asking a clarifying question
instead of just running `cdp query`), not a systematic lessons effect. **This
sample size cannot support "lessons hurt" as a general claim** — the honest
read is that the mechanism now works end to end (seed, cut, dual real
dispatch, dual real benchmark, promote/reject decision), but three questions
against one small module is far too little signal to trust the number
itself, exactly the concern that made a live-model holdout expensive in the
first place. The deterministic T3-rate `cdp holdout` remains the sound
production gate; this script is available for a larger question set/repo
when that budget exists.

Not delivered: no repeat sampling (would need 3-5x the spend already
recorded above); no second held-out repo (would need a second gold question
set, verified by hand the same way this one was); a `cdp query` subcommand
for third-party-import lookups (the actual gap h03 surfaced) was not built —
named as a real, separate finding, not silently absorbed into this one.

`make check TARGET_REPO=/Users/sharmp49/git/code_scanner` (launched after
freeze, result recorded once it completes — see below): confirms the
`agents/cdp-leaf.md` fix and the new out-of-core `benchmarks/` script didn't
move anything in the `scan`/`fold`/`golden`/`selftest` pipeline.

## Post-Phase-9 follow-up — `prompt_fix` promotions rendered into an actual prompt section

Asked directly (control question: "what stops a bad `prompt_fix`?"): R10's
content firewall (`validate_promotion` gives it no claim-shaped field to
smuggle content through) plus the existing `--no-lessons`/`--lessons vN`
escape hatches were judged sufficient for now; a `cdp lessons unpromote <v>`
revert command was scoped and costed but deferred, not built this session.

**The gap this closes:** `reflect.apply_lessons()` already built a
`prompt_fixes: List[Dict]` from a cut's promotions, but nothing downstream
ever read it — a promoted `prompt_fix` was validated, cut, pinned, and
completely inert. `cdp/prompts.py`'s `build_prompt()` gains a `prompt_fixes`
parameter and a new `_apply_prompt_fixes()` helper: after `named_sections` is
built (all 7 of `reflect.KNOWN_PROMPT_SECTIONS` — `header`/`files`/
`structure`/`inherited`/`gaps`/`digest`/`task`), each fix's `instruction` is
appended to the section its `section` field names, as `**Lesson:** <text>`.
General by construction — one mechanism for all 7 sections, not a
header-only or digest-only special case. A fix targeting `digest` is
silently absent whenever `digest_mode=False`, since that section is never
built for that call — stated in the docstring as expected, not a bug.
Wired through both real call sites that already thread `lesson_hints`
(`cli.py`'s `cmd_prompts`, `supervisor.py`'s `run_wave`); `doctor.py`'s
`build_prompt` call takes no lessons and is unaffected (default `()`).

**Tests** (`tests/test_digest.py`, 5 new cases, `PromptFixTest`): no-op with
an empty list; a `header`-targeted fix appears exactly once; a
`digest`-targeted fix is silently absent without `digest_mode`; the same fix
appears when `digest_mode=True`; multiple fixes on one section all render.

**Real-target exercise (R-E7).** A real `prompt_fix` (`section: "task"`,
"Double-check every route path against ApiConstants before citing it.") was
seeded into a scratch trajectory DB, cut, and promoted; `cdp prompts
--lessons 1` against a fresh scan of `sql-pool/sql-pool-api` wrote it
verbatim into both scopes' real prompt files (`root/(files+2)`,
`root/src/main/java`), confirmed by `grep` on the actual written `.md`
files, not a unit-test string. Scratch DB and state dir removed after.

`make check TARGET_REPO=/Users/sharmp49/git/code_scanner` (launched after
freeze, result recorded once it completes — see below): confirms
`build_prompt`'s new parameter (default `()`, opt-in) changed nothing about
the existing `scan`/`fold`/`golden` pipeline, since neither takes lessons.

`make check TARGET_REPO=/Users/sharmp49/git/code_scanner`: **545 tests green
(up from 540 — this session's 5 new `PromptFixTest` cases), determinism
(fixture+target), `fold --check` (fixture+target), golden (fixture+target)
all green, byte-identical, no re-bless needed.**

## Session handoff — 3 of 7 post-Phase-9 gaps closed; 4 remain, one decision pending

Every remaining Phase 9 "Not delivered" marker was enumerated and split into
two kinds: environment-blocked (no real MCP/LiteLLM/LangGraph/ADK SDK
installed, no live non-Claude assistant, no live `PreToolUse` harness — not
actionable by more code) and 7 genuine code/design gaps, asked about one at a
time and worked in order. Status at handoff:

**Closed this session:**
1. **Cut cadence** — resolved as a nudge, not an auto-cut: `cdp run` prints
   `lessons N promotion(s) pending after M runs -- \`cdp lessons cut\`` every
   `LESSONS_HINT_EVERY=5` finished runs (global, cross-repo), only when
   something's actually pending. `cdp/trajectory.py` (`finished_run_count`,
   `LESSONS_HINT_EVERY`), `cdp/cli.py` (`_maybe_print_lessons_hint`). See
   "Post-Phase-9 follow-up — the 'cut cadence' open decision" above.
2. **Live-model benchmark-style holdout** — built (`benchmarks/
   run_live_holdout.py` + `benchmarks/holdout_live_questions.json`), real
   spend, dual real leaf-dispatch + real reader/judge. Found and fixed two
   real bugs along the way: (a) `agents/cdp-leaf.md` never stated the
   schema's 400-char anchor ceiling, only the 12-char floor, causing
   abandoned scopes on the first live run; (b) the benchmark harness let the
   reader model read its own gold-fact file off disk (fixed: `--tools Bash`
   only). Real post-fix result: `coverage 0.444 (none) -> 0.167 (lessons) --
   REJECT`, explicitly caveated as too small a sample (n=3, one draw per arm)
   to trust as a real verdict — a genuine, separate capability gap surfaced
   too (no `cdp query` subcommand names a scope's third-party imports at
   all). See "Post-Phase-9 follow-up — the live-model holdout" above.
3. **`prompt_fix` rendering** — `build_prompt()` now consumes `prompt_fixes`
   generally across all 7 `KNOWN_PROMPT_SECTIONS`, not just header/digest.
   See "Post-Phase-9 follow-up — `prompt_fix` promotions rendered" above.

**Decision made, build deferred pending further analysis:** `cdp lessons
unpromote <v>` — a revert path for a promoted cut that later shows harm.
Costed at small (one `UPDATE ... SET promoted=0`, `latest_lesson_version()`
already falls back correctly with zero extra logic, a CLI subcommand, ~40
lines of tests, one real-target exercise). **User's explicit call: build it,
but only after further analysis** — not scheduled to a specific future
trigger yet; the open questions worth resolving before implementing are (a)
should unpromote be silent or leave an audit trail (`unpromoted_at`/
`unpromote_reason` columns on `lesson_cut`, matching R4's write-always
posture elsewhere in this store), and (b) should un-promoting the *latest*
cut auto-fall-back to the next-highest promoted version for any run already
mid-flight with `--lessons latest` resolved, or only affect future
resolutions.

**Not started — 4 remaining code/design gaps, in the order the user set:**

4. **Correction (this session):** item 4 as written below is stale — M8.2-M8.5
   were **not** "not started". They were built and committed in `5c160e7`
   ("Phase 8 (M8.1-M8.5): cross-repo link — cdp link scan/prompts/collect/
   refresh/query"), with their own completed sections above at "Phase 8
   (M8.2 only)" (line ~3102), "Phase 8 (M8.3 only)" (~3206), "Phase 8 (M8.4)"
   (~3300) and "Phase 8 (M8.5)" (~3360) — `cmd_link_query`/`link_mod.
   query_service`/`summarise_query` (unmatched-as-named-section), the LLM
   adjudication tier, `link refresh`, and the non-entanglement test all exist
   and are wired into `cli.py` today. Whatever prompted this list item to be
   written as "not started" was a documentation error, not a rediscovered
   gap — confirmed by re-reading git log and the cited line ranges directly
   rather than trusting this entry's own prior wording. Original (stale) text
   preserved below for the record, not as a live TODO:

   ~~M8.2 (`link query --service` view over unmatched persist/entity edges),
   M8.3 (LLM adjudication tier for ambiguous matches + `needs_other_repo`
   routing — the largest of the four, a real model-call path), M8.4 (`link
   refresh`, mirroring Phase 3's refresh design for the cross-repo case),
   M8.5 (the non-entanglement test — moot until M8.3 lands a store table to
   assert against). Not yet asked which sub-items to build; my standing
   suggestion was M8.2 alone (cheapest, pure read-path).~~
5. **`link` tasks never run through `cdp run`** — no leases/`snapshot_task`
   rows/wave scheduling for `dim_task_kind=link`, so trajectory learning
   (routing_prior, elision_regret) is blind to link work even though both
   already work for `link` by construction (M9.1's own note — neither
   hardcodes `"scope"`). Real schema work (`dim_task_kind` rows), same
   deferral posture F9/D7 already took toward similarly-scoped work.
6. **Source-vs-digest same-scope comparison** (M6.3's own stress-table item,
   left for M9.2, still not attempted) — needs two real leaf dispatches of
   the *same* scope in both modes, which `cdp run`'s single-dispatch-per-wave
   loop does not support today. Real dispatch-loop change, not a small patch.
7. **`sigma_claims`** — the count of imported-symbol claims specifically
   (narrower than `inherited_claims`, which `build_prompt`'s stats already
   has). Smallest of the four remaining; likely a one-line stats addition
   once picked up.

**To resume in a new session:** read this block, then `PHASE/phase_9_plan.md`
+ `PHASE/EXECUTION_RULES.md` as before, and pick up at item 4. All of items
1-3's code is committed to the working tree (uncommitted in git — see
`git status`), gated green (545 tests) as of this handoff.

## Item 7 closed — `sigma_claims`, a direct-import-touch count narrower than `inherited_claims`

User chose item 7 alone this session (items 5/6 are real schema/dispatch-loop
work, out of budget). `_inherit`'s existing `touches` boolean (`prompts.py`)
already distinguished a claim reached because its subject is literally one of
the scope's own imported symbols from one pulled in only via a sibling
module's `module_deps` fallback (`entrypoint`/`data_model`/`ownership`/
`deployable` kinds) — that distinction just wasn't counted separately.
Factored into `_is_sigma_claim(claim, imported)`, reused by both `_inherit`
and a new `stats["sigma_claims"]` line in `build_prompt` (`cdp/prompts.py`).

Plumbed through to the trajectory input fingerprint the same way
`rows_elided`/`tokens_est`/`digest_mode` already are: new `sigma_claims`
column on `fact_leaf_run` (schema + `_LEAF_RUN_MIGRATION_COLUMNS`, so a
pre-existing `trajectories.db` gets it via `ALTER TABLE`, not a
`CREATE TABLE IF NOT EXISTS` no-op), a new kwarg on
`TrajectoryStore.record_leaf_run`, read back in `leaf_runs_for`, and wired at
the one real call site (`cdp/cli.py`'s post-fold `record_leaf_run(...)`) from
`prompt_stats.get("sigma_claims")`. Mirrored into
`.claude/skills/cdp/cdp/{prompts,trajectory,cli}.py` — that tree had been
kept byte-identical to `cdp/` before this change (diffed to confirm) and
`cdp install --self` re-syncs it anyway.

**Exercised on a real module**, not just the fixture (`sql-pool/sql-pool-api`,
scratch scan + `cdp prompts --wave 0`, read back via
`backend.read_report("prompts")` rather than trusting stdout): both real
scopes show `sigma_claims == inherited_claims` (12/12, 20/20). That equality
is the honest result for a *single-module* scan, the same caveat M6.4's
tiering exercise already recorded: the dep-fallback path needs a sibling
module present in `schedule["module_deps"]`, which a standalone single-module
scan never has. The two counts diverging is therefore a cross-module-scan
result to look for later, not something this exercise could produce with the
scan shape available. `cdp run --wave-all` against a hand-written
`--runner-cmd` fake was attempted to also exercise the `record_leaf_run`
write path directly, but was abandoned after two schema-shape misses (missing
`status`, then a `node` mismatch) rather than continuing to spend budget on
a call site that is a single dict `.get()` already verified correct by the
`prompts` report above — the risk this leaves unverified is confined to that
one `.get()` line, not the stats computation itself.

`cd tests && python3 -m unittest test_trajectory test_digest`: 28/28 green,
no fixture changes needed (no existing test asserted a fixed column count or
`fact_leaf_run` column list). `make check TARGET_REPO=/Users/sharmp49/git/code_scanner`
launched after freeze: **545 tests green, determinism (fixture+target),
`fold --check` (fixture+target), golden (fixture+target) all green,
byte-identical, no re-bless needed** — `sigma_claims` is additive (a new
optional stats key and DB column), and no existing golden artifact captures
either the `prompts` report or `fact_leaf_run` rows, so nothing in the
blessed baseline could move.

## Item 5 — link tasks now run through leases and `link_task`, and record to the trajectory store as `dim_task_kind=link`

User chose item 5 (of the 4 remaining post-Phase-9 gaps named in the prior
session's handoff), after being asked which to pick up next this session.
Before this, `link prompts`/`link collect` were a manual, file-handoff pair
with no lease, no per-task state row, and no trajectory record — link work
was invisible to `dim_task_kind=link`'s routing prior/elision regret even
though both already supported the dimension by construction (M9.1's own
note: neither hardcodes `"scope"`).

**Schema (SCHEMA_V7, `cdp/store/sqlite_backend.py`).** `link_task` (created
schema-only at M2.5, never populated) gets `state`/`attempts`/
`dispatched_at`/`lease_until`/`last_error`/`patch_hash`/`wall_ms` — the same
columns `snapshot_task` already has. Its existing `scope_hash` column now
holds a link task's `task_id`; same column name deliberately, so the
generic lease/task helpers below work against either table unmodified.
`link_run` (the `link.*` counterpart of `snapshot_run`) is left untouched —
nothing needs a run-level row yet, and forcing one would have required
`begin_run`'s `snapshot_id` FK, which a `--db`-only link store has no
snapshot context to satisfy.

**Generalised, not duplicated (`sqlite_backend.py`).** `upsert_task`/
`acquire_lease`/`heartbeat_lease`/`release_lease` were refactored into
private `_upsert_task`/`_acquire_lease`/`_heartbeat_lease`/`_release_lease`
taking a `table` parameter, with the original public names becoming thin
`table="snapshot_task"` wrappers and new `upsert_link_task`/
`acquire_link_lease`/`heartbeat_link_lease`/`release_link_lease`/
`link_task_states` wrapping `table="link_task"`. Existing scope-task callers
are unchanged in behaviour (verified: `test_store_sqlite`/`test_supervisor`
green with no assertion touched).

**`supervisor._LeaseHeartbeat` generalised the same way.** It took
`(backend, run_id, scope_hash, lease_seconds, interval)` and called
`backend.heartbeat_lease(...)` directly, hardcoding the scope-task path. Now
takes a zero-arg `heartbeat_fn` callable; `dispatch_scope`'s call site
becomes `_LeaseHeartbeat(lambda: backend.heartbeat_lease(run_id, scope_hash,
lease_seconds), heartbeat_seconds)`, and `link.dispatch_link_task` reuses the
same class with `heartbeat_link_lease` closed over instead. One test call
site (`tests/test_supervisor.py::LeaseTest::
test_heartbeat_keeps_a_live_holders_lease_from_being_reclaimed`) constructed
`_LeaseHeartbeat` with the old positional signature and needed updating to
match — found by running the narrow module, not by the target gate.

**`link.dispatch_link_task` (new, `cdp/link.py`)** mirrors
`supervisor.dispatch_scope`'s retry loop (`PENDING -> DISPATCHED -> RETURNED
-> VALIDATED/EMPTY/INVALID -> retry up to `max_attempts` -> ABANDONED`)
against `link_task` instead of `snapshot_task`. Validation is
`validate_task_patch` alone (no separate anchor-liveness check the way
`_classify_returned` runs `verify_patch` for a scope's claims against live
source — a link task's own citation check, "every anchor must be one shown
in the prompt," already is the fabrication guard for this shape, M8.3). A
new `link_task_shape_key(task)` is `dim_scope_shape`'s counterpart for a link
task: bucketed candidate count plus protocol, the same coarseness
`trajectory.scope_shape_key` uses and for the same reason (M9.2's routing
prior needs shape-alike neighbours, not per-task fingerprints).

**New CLI surface: `cdp link run`.** Reads a persisted `link scan --db`
report, builds ambiguous tasks (`build_tasks`, unchanged), dispatches each
through `dispatch_link_task` with real leases, folds every `VALIDATED`
task's resolutions immediately (`fold_resolutions`, unchanged), and records
one `trajectory.record_leaf_run(task_kind="link", ...)` row per task —
`repo_id` taken from the task's first candidate's caller repo (a link task is
inherently cross-repo; the caller is the more natural "owner" of the
question being asked). `link prompts`/`link collect`'s existing file-handoff
path is untouched — `link run` is additive, not a replacement, so no
existing test or documented workflow needed migrating.

**Exercised on real modules, not just the fixture.** `sql-pool/sql-pool-api`
and `service-api` each scanned fresh into scratch dirs, `cdp link scan --db`
persisted (2,697 links, 0 heuristic — the same real finding M8.1/M8.3 already
recorded for this pair). One synthetic heuristic link was written directly
into the persisted report (same technique M8.3's own session used to exercise
its adjudication path, since this pair produces none naturally) with real
repo paths as both sides. `cdp link run --runner-cmd "python3
/tmp/item5_fake_runner.py"` (a real subprocess, not an in-process stub)
answered correctly:

```
link run  1 task(s)  validated 1  1 resolution(s) folded
```

Confirmed by reading state back directly, not trusting the summary line:
`sqlite3 index.db "select run_id, scope_hash, state, attempts from
link_task"` showed one real row (`cdp-link | link-<hash> | validated | 1`);
`fact_leaf_run` in the real `~/.cdp/trajectories.db` (no `CDP_TRAJECTORY_DB`
override was set for this exercise — an oversight, corrected below) carried
a real `task_kind_dim` resolving to `'link'` (id 2, alongside `'scope'` at id
1 — `dim_task_kind`'s two-row closed vocabulary, both now populated for
real) and `scope_shape_dim` resolving to `protocol=http_out|candidates<=1`.
The one synthetic row this exercise wrote to the real, cross-workspace
trajectory corpus was deleted afterward (`DELETE FROM fact_leaf_run WHERE
run_id='cdp-link' AND node LIKE 'link-%'`) since it was fabricated test data,
not a real learning signal, and no lesson cut had consumed it yet — R4's
write-always posture governs real corpus rows, not a same-session cleanup of
a row this exercise itself created by mistake. Scratch scan/db/prompt
directories removed after.

**Not done, named rather than silently dropped:** no wave/schedule grouping
for link tasks the way `sched["waves"]` groups scopes (`link run` dispatches
every ambiguous task in one flat pass — link tasks have no cross-task
dependency structure the way scopes' `module_deps` does, so a single pass is
the honest granularity, not a missing feature); `--resume`/partition-drift
handling for link runs (a link report has no `partition_hash` equivalent
today); no `link_run`-row-level `started`/`finished` `fact_run_event` pair
(only per-task `fact_leaf_run` rows are written — the M9.1 run-event pair is
scope-run-shaped and a link run has no clear equivalent of "the whole run
finished" beyond "every task was dispatched," which the caller already knows
from its own loop).

`cd tests && python3 -m unittest test_store_sqlite test_supervisor test_link
test_trajectory`: 84/84 green. `cdp install --self` (required — `cli.py`/
`link.py`/`supervisor.py`/`store/sqlite_backend.py` all changed) then `cd
tests && python3 -m unittest discover`: **549 tests green (up from 545,
skipped=30)**.

`make check TARGET_REPO=/Users/sharmp49/git/code_scanner`: **549 tests
green, determinism (fixture+target), `fold --check` (fixture+target), golden
(fixture+target) all green, byte-identical, no re-bless needed** — the new
`link_task` columns/state machine and `link run` CLI surface are additive
and untouched by the existing `scan`/`fold`/`golden` pipeline, since no
existing gate command calls `cdp link run` (the same posture every prior
Phase 8/9 additive-feature entry in this file records).

## Item 6 — closed as a decision, not built: source-vs-digest comparison does not belong on `cdp run`

The remaining post-Phase-9 gap (source-vs-digest same-scope comparison,
`prompts.py:120`'s ranking function's own stress-table item, M9.2 left it
unattempted since `cdp run`'s wave loop dispatches each scope once per run).
A design was drafted this session — a `--compare-digest` flag on `cdp run`
that would dispatch the named scope a second time in digest mode via a new
lease/task-state-free `run_shadow_dispatch` in `supervisor.py`, recording a
second `fact_leaf_run` row for the pair without folding its patch — and
**rejected by the user before implementation**: the actual need behind this
item is feeding the trajectory corpus paired source/digest data so
`routing_prior` (6.5) can eventually judge digest safety per scope shape,
which is a benchmarking concern, not a production dispatch-loop feature. This
codebase already keeps that distinction (`cdp doctor`, `benchmarks/
run_benchmark.py`, `benchmarks/run_live_holdout.py` are standalone tools, not
`cdp run` flags), and folding a diagnostic second dispatch into the command
real automation depends on would blur it.

**If picked up later, the right shape:** a standalone `benchmarks/`-style
script that dispatches one scope twice (source, then digest) via the
existing `build_prompt`/runner/`_classify_returned` pieces directly, and
records both outcomes to the trajectory store — never touching
`cdp/supervisor.py` or `cdp/cli.py`. Not built this session. No code changed,
no tests added, no gate run needed.

**Manual, no-code alternative for a one-off data point** (same pattern
M6.4's `root/automation` comparison already used, still available any time):
scan a module into two scratch state dirs, `cdp prompts --wave N` in one and
`cdp prompts --wave N --digest` in the other, dispatch each through the same
real model, and compare `cdp query stats`/`prompts` report output by hand.
Gives a real number for one scope; does not write anything to the
trajectory corpus.

With this, all 7 post-Phase-9 follow-up gaps are accounted for: 3 closed and
shipped (cut cadence, live-model holdout, `prompt_fix` rendering), one
already done before this handoff trail existed (M8.2-M8.5, corrected above),
`sigma_claims` and link-tasks-through-leases both closed and shipped, and
this one — source-vs-digest comparison — closed as a considered decision not
to build it into the CLI. `cdp lessons unpromote` remains the only item still
explicitly deferred pending further design analysis, per the user's own
earlier call.

## `cdp lessons unpromote` — built, both open design questions resolved

Picked up in a later session. The two questions the "deferred pending further
analysis" entry above left open are both answered by this implementation,
not left for a future one:

**(a) Audit trail, not silent.** `lesson_cut` gains `unpromoted_at`/
`unpromote_reason` columns (`_LESSON_CUT_MIGRATION_COLUMNS`, same
`ALTER TABLE`-on-missing-column migration pattern `_LEAF_RUN_MIGRATION_COLUMNS`
already established for a pre-existing `trajectories.db`). `unpromote_cut`
flips `promoted` back to 0 but never clears `holdout_repo`/`holdout_metric` —
R4's write-always posture: the promotion still happened, this only records a
later decision on top of it, the same way `fact_run_event(rolled_back,
reason)` doesn't erase the run it applies to.

**(b) Fallback is automatic, by construction, and only affects future
resolutions.** `latest_lesson_version()` was already a fresh `MAX(version)
FROM lesson_cut WHERE promoted=1` query with no caching (M9.3's own code, not
touched here) — so `unpromote_cut` needs no special fallback logic at all.
The very next default-mode `cdp run` (no explicit `--lessons`) re-resolves
and gets whichever *other* cut has the highest version number among those
still promoted, or no lesson-set if none remain promoted — exercised directly
below. A run already mid-flight is unaffected either way, because `cmd_run`
resolves and pins its own `lessons_version` once at start; an explicit
`--lessons vN` pin is also unaffected, since it never reads `promoted` at
all — only the implicit default does.

`cdp lessons unpromote --version N [--reason TEXT]` on the CLI; refuses
(`CdpError`, exit 2) when `N` is not currently promoted, naming that as the
reason rather than silently no-opping.

**Exercised for real**, not just the fixture: `CDP_TRAJECTORY_DB` pointed at
a scratch file (never the real `~/.cdp/trajectories.db`), a promotion
recorded and cut via the real `TrajectoryStore` API, promoted via
`promote_cut`, then the actual installed CLI (`python3 -m cdp.cli lessons
unpromote --version 1 --reason "..."`) run for real:

```
$ cdp lessons show
lessons   v1 (1 promotion(s))
$ cdp lessons unpromote --version 1 --reason "regressed on repo X in a live check"
lessons   v1 unpromoted -- default `cdp run` resolution now falls back to no lesson-set
$ cdp lessons show
lessons   no cut exists yet
$ cdp lessons unpromote --version 1
cdp: v1 is not currently promoted -- nothing to unpromote          (exit 2)
```

Fallback to a second, still-promoted cut (not just the "no cut left" case
above) and the R4 audit-trail claim (`holdout_repo` unchanged, `unpromote_
reason` recorded) are both covered by new unit tests in
`tests/test_trajectory.py` (`test_unpromote_reverts_promoted_flag_but_keeps_
holdout_record`, `test_unpromote_falls_back_to_next_highest_promoted_cut`,
`test_unpromote_a_cut_that_is_not_promoted_is_a_noop`) — 19/19 green in
`test_trajectory` alone. Mirrored into `.claude/skills/cdp/cdp/{trajectory,
cli}.py` via `cdp install --self`.

`make check TARGET_REPO=/Users/sharmp49/git/code_scanner`: **552 tests green
(up from 549), determinism (fixture+target), `fold --check` (fixture+target),
golden (fixture+target) all green, byte-identical, no re-bless needed** —
additive only (a new `lesson_cut` migration, a new CLI subcommand action, no
existing call site changed), matching every other additive Phase 9/
post-Phase-9 entry in this file.

With this, every post-Phase-9 follow-up item named in the handoff trail is
closed: three shipped earlier, item 4 corrected (already done), items 5 and
7 shipped, item 6 closed as a decision not to build, and now `unpromote`
shipped with both of its own open questions resolved rather than deferred
again.
