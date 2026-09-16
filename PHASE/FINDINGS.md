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
