# TARGET.md — the validation target

`RESEARCH_GRAPHIFY.md §12` item 4 asks "What is the real target repo?" and notes
that language-extractor breadth should be driven by that answer. This file is
the answer, pinned, so that every later "exercise on real input" acceptance
criterion resolves against a fixed object rather than a moving one.

## Pin

| | |
|---|---|
| `$TARGET_REPO` | `/Users/sharmp49/git/code_scanner` (private) |
| Commit | `7e10575adf69a193da7f547aed088f7409f1f7c4` |
| Subject | `IRP-7024: Integration tests.` |
| Working tree at capture | clean (`git status --porcelain` empty) |
| Inventory source | `git` (not the walk fallback) |
| Submodules | none (`.gitmodules` absent) |

## Census

| | |
|---|---|
| Tracked files | 4,728 |
| Files on disk | 4,729 (ratio 1.00) |
| Total LOC | 1,424,015 |
| Modules detected | 63 |
| Scopes / waves | 172 scopes (17 oversized) over 17 waves, max 12 concurrent |
| Scan wall time | 2m32s (single-threaded, stdlib only) |

The ratio of 1.00 is worth noting against `RESEARCH_GRAPHIFY.md §8` item 6,
which treats a high on-disk/tracked ratio as a finding (391 tracked vs 2,065 on
disk there). This target was scanned from a clean checkout with no build output
present, so the generated-code signal that item describes is **not exercised
here**. A target whose ratio is 1.00 cannot demonstrate `generated_suspect`.

### Languages by file count

| Language | Files | LOC | defines | imports | io_edges |
|---|---|---|---|---|---|
| C# (`.cs`) | 2,262 | 264,497 | **0** | **0** | **0** |
| Java | 1,420 | 162,348 | 11,782 | 11,903 | 397 |
| SQL | 497 | 669,157 | 493 | 0 | 3,316 |
| Scala | 73 | 11,850 | **0** | **0** | **0** |
| `.csproj` | 20 | 519 | 0 | 0 | 0 |

Roles: 3,243 source · 776 test · 512 schema · 85 build · 60 docs · 39 config ·
8 ci · 5 asset.

Pipeline totals: 18,697 defines · 11,907 imports · 10,137 io_edges · 12,949
symbols defined (497 colliding, 112 across modules) · 43 routes · 8,807 dataflow
edges over 3,548 nodes · 1,279/1,279 derived claims anchored (0 demoted) ·
1,278 claims, 0 conflicts, 1 near-miss.

## Finding T1 — the target is majority C#, and CDP reads no C#

**2,262 of 4,728 tracked files (48%) produce nothing.** `.cs` files are
classified with `language: "csharp"` but fall through to `GenericExtractor`:
zero defines, zero imports, zero io_edges across 264,497 LOC. Scala (73 files,
11,850 LOC) is in the same position. `cdp/lang/__init__.py` registers eight
extractors; none of them is C#.

Every structural claim CDP currently makes about this repository is therefore
derived from its Java, SQL and build files — a minority of the code, and not
the part a `.NET` service is mostly written in.

This is precisely the decision `RESEARCH_GRAPHIFY.md §9` item 4 defers to the
target: *"Add languages on demand, driven by what real target repos contain,
not to close a number gap."* The demand signal has now arrived. It is **not** a
Phase 0 change — Phase 0 changes no behaviour — but it materially affects how
Phase 6's graded benchmark should be read, because recall measured over a
corpus where half the code is invisible measures the extractors we have, not
the repository.

Recorded for scheduling, not fixed here.

## Finding T2 — no *recognised* root manifest, so scope item 1.1 is not
observable at this target's root

Phase 1's 1.1 is a field bug: a manifest at the scan root yields zero modules
and a bogus `src` module. `PHASE/phase_0_plan.md` M0.3 asks whether a build
manifest sits at this target's root, because that decides whether the fix is
observable here.

The root contains `Directory.Build.props`, `global.json` and `nuget.config`.
None is in `MANIFEST_NAMES` (`cdp/lang/build.py:23-26`), which lists
`build.gradle`, `build.gradle.kts`, `pom.xml`, `package.json`, `go.mod`,
`pyproject.toml`, `setup.py`, `Cargo.toml`, `build.sbt`, `*.csproj`. There is
no `.csproj` at the root.

So as CDP reads it today, this target has **no root manifest**, module detection
takes the normal path, and 63 modules are found. Per M0.3's own instruction,
Phase 1 therefore needs one of:

- a second target that does have a recognised root manifest, or
- a constructed fixture with one (cheapest, and reproducible for everyone), or
- to add `Directory.Build.props` to `MANIFEST_NAMES` as part of 1.1, which
  would *make* this target exhibit the bug and then fix it.

The third option is the most informative, because it is a real .NET repository
layout that CDP currently does not recognise as one. It is a Phase 1 decision,
not a Phase 0 one.

### Decision taken in Phase 1 (M1.1): the constructed fixture, not the widening

Option 2. `tests/fixtures/solorepo` is a single-module Maven project and
`tests/fixtures/anonrepo` is the unnameable case; `minirepo` is retained as the
aggregator regression. Option 3 was rejected on the evidence: adding
`Directory.Build.props` to `MANIFEST_NAMES` would **not** make this target
exhibit the bug, because sub-manifests exist beneath its root and the fixed rule
correctly leaves the root as the root scope in that case. It would change only
that file's role classification, churning the baseline for no signal.

1.1 was nevertheless exercised on real input, by pointing `--repo` at one module
of this target:

    cdp scan --repo $TARGET_REPO/sql-pool/sql-pool-api

Before: the top-level-directory fallback. After: exactly one module, the
`root_module` block recording `is_module: true` from `build.gradle`, and — since
that manifest states no name and no `settings.gradle` sits beside it — `named:
false` plus the *"What is this module called?"* structural unknown, rather than
a name borrowed from the directory.

## Finding T3 — this repository is not a valid golden target for itself

Unrelated to `$TARGET_REPO`, found while capturing the baseline, and recorded
here because it governs which repositories `make check` may use. See
`PHASE/FINDINGS.md` F1: `cdp/graph.py:180` builds a basename→module dict by
iterating a `set`, so two modules sharing a basename resolve non-deterministically.

`$TARGET_REPO` has **no duplicate module basenames** (verified over all 63
modules), so the defect is dormant there and its baseline is stable. This
repository, since M0.1 vendored a second copy of `tests/fixtures/minirepo`
into `.claude/skills/cdp/`, has two modules named `core` and two named `web`,
and its own output flaps between runs.

## Baseline artifacts

`tests/golden/code_scanner@7e10575adf69/` — 91 artifacts: `scan`, `docs` and all
13 queries, captured from a detached worktree at the pinned commit (see
`cdp/cli.py` `pristine_checkout` for why a dirty tree cannot be baselined).

### Size decision (M0.4 asks for this to be decided and recorded)

Stored in full, the scan artifacts alone are **68.27 MB**:

| Artifact | Full size | Stored as |
|---|---|---|
| `extract.json` | 31.27 MB | digest |
| `xref.json` | 28.98 MB | digest |
| `dataflow.json` | 4.88 MB | digest |
| `inventory.json` | 1.42 MB | full |
| `state.json` | 0.96 MB | full (`ALWAYS_FULL`) |
| `partition.json` | 0.59 MB | full (`ALWAYS_FULL`) |
| `graph.json` | 0.13 MB | full (`ALWAYS_FULL`) |

That is far past the 20 MB line the Phase 0 stress test draws, so the
prescription it gives is the one applied: **hashes per file, full bodies for
`state.json`, `graph.json` and `partition.json` only** (`cdp/golden.py`
`ALWAYS_FULL`, `FULL_BODY_LIMIT = 2 MB`). On disk the baseline is **6.0 MB**
rather than 68 MB.

The cost, stated: a regression confined to `extract.json` shows as a changed
digest rather than a readable diff. It is bounded, because extraction changes
propagate — the deleted-`io_edge` rehearsal below moved 10 artifacts, of which
`state.json`, the three docs and the query outputs are all stored in full and
name the claim, file and line. A regression that changes `extract.json` and
*nothing downstream* is the case that degrades to "this digest moved"; if that
becomes common, raise `FULL_BODY_LIMIT` and accept the repository size.

### Rehearsal — the baseline detects what it is for

Deleting one `io_edge` from the Java extractor (`cdp/lang/java.py:698`,
`process_boundary`) against the fixture baseline produces 10 differing
artifacts, each localised, e.g.:

```
docs/modules/web.md:
-- WebApplication declares a process entry point in web; it is one of the
   repository's separately-startable units. — `.../WebApplication.java:5`
```

and the corresponding `claims.json` entry removed in full, with its `id`,
`channel`, `anchor` and `line`. Reverted after the rehearsal.

Regenerate with:

    cdp selftest --golden $TARGET_REPO --bless

Verify with:

    cdp selftest --golden $TARGET_REPO
    cdp selftest --determinism $TARGET_REPO

## Phase 2 — re-blessed for the store boundary

M2.3 moves verification into `fold`, which adds a `verification` block to
`state.json` and an `author_kind` field to every logged patch — a real,
intended content change, not drift. Re-blessed with the command above;
`git diff --stat` on the baseline shows exactly 14 files (12 query outputs'
`fold_hash`, the derived patch, `state.json`), the same shape as the fixture's
own re-bless. `claims`/`unknowns`/`conflicts` are byte-identical to before:
1,279/1,279 claims still kept, 0 demoted, 1,428/1,428 anchors ok, 0 relocated —
this target's derived claims have exact anchors by construction (they come
from the same extraction pass verification checks against), so moving
verification into the fold changed *when* it runs, not its answer here.

### M2.6 exercised live, not just on the fixture

Store resolution and the registry (`cdp/store/registry.py`) were run against
this target with `HOME` and the scan `cwd` both redirected to scratch
directories (never touching the real `~/.cdp/config.toml`):

    cd /tmp/scratch-a && HOME=/tmp/fake-home cdp scan --repo $TARGET_REPO --quiet
    cd /tmp/scratch-b && HOME=/tmp/fake-home cdp query stats --repo $TARGET_REPO

The first command (no `--in-repo`, no `--state-dir`) wrote state to
`scratch-a/.cdp`, today's exact default, and registered
`github.com/moodys-ma-platform/unified-store -> scratch-a/.cdp` (the target's
real, normalised origin remote) in the fake registry. The second command, run
from an unrelated `cwd`, resolved to `scratch-a`'s store via the registry and
answered from the already-scanned state — `scratch-b/.cdp` was never created.
This is the concrete form of two of M2.6's acceptance criteria ("same repo ...
resolves to one store", "a second scan doesn't silently clobber the first")
against a real repository rather than a synthetic one.

This same exercise is what found **F7** (`PHASE/FINDINGS.md`): `fold --check`
invoked without `--repo` (both `scripts/fixture_gate.py` and the `Makefile`'s
`TARGET_REPO` branch did this) silently demoted every claim once verification
moved inside `fold`, because `--repo` defaults to cwd. Caught by the gate
itself on the first post-M2.3 `make check` run, not by a bespoke test.

## Post-M2.6 audit pass — defect sweep, no schema/behaviour changes

A follow-up pass (this repository's `store/`, `snapshot.py`, `registry.py` had
landed uncommitted; nothing further from `phase_2_plan.md`'s milestones was
implemented here) read every new module end to end looking for defects and
algorithmic headroom, not new scope. `make check TARGET_REPO=...` — all
gates green: `selftest` (248 tests), `determinism` (fixture + target),
`fold --check` (fixture + target, order-independence included), `golden`
(fixture + target, byte-identical).

Found and fixed: **F8** (unclosed `SqliteStore` connections in tests — every
construction site now has `addCleanup(store.close)`) and **F10** (`ast.parse`
on target Python source printing `SyntaxWarning` to the gate's stderr — see
`PHASE/FINDINGS.md` for both, including F10's verification caveat: it landed
after this pass's one gate run and was not re-verified by a second full
target scan).

Identified, not implemented: **F9**, `cdp/extract.py:run_extract`'s
per-file loop is still single-threaded — the same "remaining headroom, not
taken" F6 already named. Not attempted here because parallelising it risks
the ordering `check_order_independence`/`fold_hash`/the golden baseline
depend on, and proving that risk is unfounded is its own reviewed change.

No other defects found in the store boundary itself: `SqliteStore`'s
content-addressing, snapshot lineage (`begin_snapshot`/`mark_durable`), and
`store.registry`'s identity chain (`declared id -> origin remote -> UUID`)
all read as implemented, matching both the plan and `PHASE/FINDINGS.md`
D1-D7's own account of what was deliberately deferred.
