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

## Phase 3 (M3.1-M3.3) — `cdp refresh` exercised on a real module, real history

Scoped to M3.1-M3.3 only this session (`PHASE/FINDINGS.md` records why the
other five milestones were deferred). Exercised on `$TARGET_REPO` via a
detached `git worktree` (never touching the main checkout):

    git worktree add --detach /tmp/refresh_target_wt 7e10575adf69a193da7f547aed088f7409f1f7c4
    cdp scan --repo /tmp/refresh_target_wt/sql-pool/sql-pool-api --state-dir <scratch>
    git -C /tmp/refresh_target_wt checkout -q bab4ea0dc   # current tip, ~8 months later
    cdp refresh --repo /tmp/refresh_target_wt/sql-pool/sql-pool-api --state-dir <scratch>

```
refresh   7e10575adf69 -> bab4ea0dce85
extract   544 file(s) changed (renamed/edited/added), 49 total parsed
rename    18 file(s) renamed, 527 edited, 17 added, 444 deleted
verify    41 live, 0 stale, 0 anchored-but-unreviewed, 0 unknown-churn (0 newly demoted), zero model calls
```

~12s wall time for an 8-month span of real history over one module. Zero
demotions across a real rename set (18 files), zero crashes, and the 41
structural claims from the original scan all verified live — plausible, since
this module's derived claims (declares a process entry point, persists an
entity, etc.) tend to anchor on lines that outlive a typical refactor.

**One negative result, recorded rather than hidden:** the pinned commit is
**not an ancestor** of the current tip (`git merge-base --is-ancestor` fails
both directions), meaning this repository's history was rewritten (rebase or
force-push) sometime in the roughly eight months between them. `git diff
--name-status -M <old> <new>` succeeded anyway — git diffs two arbitrary,
still-present commits regardless of ancestry — so `HistoryUnavailable` (the
fallback for a truly unreachable/pruned commit, e.g. a shallow clone's
boundary) was never triggered here. That path is proven only at fixture scale
with a synthetic nonexistent sha; it has not been exercised against a real
shallow clone or a truly garbage-collected commit.

Worktree removed after the exercise (`git worktree remove --force`); the main
checkout's `git status --porcelain` was empty before and after.

## Phase 3 (M3.4) — scope-hash caching exercised on a real one-file edit

Scoped to M3.4 only this session (`PHASE/FINDINGS.md` records the fix and why
M3.5–M3.8 stay deferred). Same worktree pattern as M3.1–M3.3's exercise above:

    git worktree add --detach /tmp/m34_wt 7e10575adf69a193da7f547aed088f7409f1f7c4
    cdp scan --repo /tmp/m34_wt/sql-pool/sql-pool-api --state-dir <scratch>
    # append one line to one .java file in the 38-file scope, commit
    cdp refresh --repo /tmp/m34_wt/sql-pool/sql-pool-api --state-dir <scratch>

```
scopes    1/2 changed (dispatch needed for 1, 1 reuse the prior claim)
```

The 11-file scope's `scope_hash` did not move; the edited 38-file scope's did.
This is the milestone's own acceptance line ("a commit touching 2 of 17
scopes dispatches 2 scopes, not 17") reproduced against real content changed
by a real commit, not a synthetic partition. Worktree removed after the
exercise; main checkout's `git status --porcelain` was empty before and
after.

## Phase 3 (M3.5-M3.6) — `cdp diff` and `cdp gc` exercised on the same real commit pair

Scoped to M3.5/M3.6 only this session (`PHASE/FINDINGS.md` records the
multi-snapshot gap this surfaced — `FileStore` cannot hold two snapshots, and
the CLI never constructs a `SqliteStore` — and why each milestone's design
answers it differently). Same worktree pattern as the M3.1-M3.4 exercises:

    git worktree add --detach /tmp/diff_wt 7e10575adf69a193da7f547aed088f7409f1f7c4
    cdp scan --repo /tmp/diff_wt/sql-pool/sql-pool-api --state-dir /tmp/diff_old --quiet
    git -C /tmp/diff_wt checkout -q bab4ea0dce85   # current tip, ~8 months later
    cdp scan --repo /tmp/diff_wt/sql-pool/sql-pool-api --state-dir /tmp/diff_new --quiet
    cdp diff /tmp/diff_old /tmp/diff_new

```
diff      0 module(s) added, 0 removed
          0 declared edge(s) +/-0/0, 0 observed edge(s) +/-0/0
          0 route(s) added, 0 removed
          0 claim(s) added, 0 removed, 0 anchor(s) moved
```

Zero deltas, consistent with the M3.1-M3.3 finding that this module's 41
structural claims all verified live across the same commit range: a real diff
of zero is the expected cross-check here, not a vacuous run. The eight
non-trivial delta shapes (module/edge/route/claim added or removed, anchor
moved, undeclared dependency appearing, coverage regression) are exercised on
synthetic dicts shaped like the real schemas (`tests/test_diffs.py`), since
this real commit pair never produced any of them within this session's
budget.

For `cdp gc`, since no scan path writes into a `SqliteStore` (the CLI's
default backend is still `FileStore` — D3), one was populated directly at
this target's real `repo_id` and the same two real commit shas: an old
snapshot cited by a claim's `claim_reviewed_at`, an uncited orphan snapshot,
and the head snapshot. `cdp gc --db ... --repo /tmp/diff_wt/sql-pool/sql-pool-api`
(a real CLI invocation, real `repo_identity`/git-HEAD resolution) dropped only
the orphan and kept the cited old snapshot plus HEAD, confirmed by reading
`list_snapshots()` back rather than trusting the summary line; `--dry-run`
reported the identical plan without deleting anything, checked first.

Worktree removed after the exercise; main checkout's `git status --porcelain`
was empty before and after.

## D3 resolved — `SqliteStore` exercised as the CLI's real default, live

`PHASE/FINDINGS.md`'s "D3 resolved" entry has the fix; this is its real-target
evidence. `cdp scan` / `query stats` / `fold --check` / `docs` / `prompts` /
`status` all run against `$TARGET_REPO/sql-pool/sql-pool-api` (scratch state
dir): `index.db` is confirmed a real SQLite file (`file(1)`: "SQLite 3.x
database... database pages 275"), every command reads it correctly, and no
stray top-level `*.json` artifact sits alongside it. `hook.find_state`
against a freshly `git init`'d, never-scanned scratch directory returns
`None` and creates no `.cdp/` at all (the bug `store.has_scanned` fixes:
constructing `SqliteStore` merely to check existence would otherwise litter
one at every parent directory the hook probes).

Both golden baselines (fixture and `$TARGET_REPO`) re-blessed for the shape
change golden capture now has (`scan/patches/0000-derived.json` -> one
`scan/patches.json`; `REPORTS` always present, `{}` when unwritten): target
diff is 15 files, the same shape as every prior phase's re-bless (`fold_hash`
via the new `"rollback": null` field already pending un-blessed from M3.7,
`scope_hash` per scope from M3.4, plus this session's patches/reports
restructuring) — confirmed via `git diff` on `scan/state.json` showing only
the additive `rollback` field and its consequent hash change, nothing else.

`make check TARGET_REPO=/Users/sharmp49/git/code_scanner` (selftest,
determinism x2, fold --check x2, golden x2): **all gates green**, including
the reproducibility gate against the new default backend
(`test_minirepo_scans_reproducibly` and the target's own `determinism`
gate both pass) — the concrete proof that `_store_snapshot`'s canonical-JSON
comparison, not a raw byte-diff of `index.db`, is what makes two independent
scans of one commit agree.

## Phase 3 (M3.8) — git hooks, and a defect they exposed in `refresh` itself

Scoped to M3.8 only this session -- the last milestone in `phase_3_plan.md`;
M3.1-M3.7 were already complete going in. `PHASE/FINDINGS.md` F12 and the
"Phase 3 (M3.8)" entry (D19) have the full account; this is the real-target
evidence.

Exercising the hooks' effect required composing `scan` -> a hook-triggered
`refresh` -> a separate `cdp status` process -- a composition no prior
phase's real-target exercise had performed (each trusted `refresh`'s own
printed summary). Doing that composition surfaced F12: `refresh` wrote into
a snapshot that `status`/`query`/`docs`/`fold`/`collect` never read back, and
separately, a freshly-selected snapshot's patch log started empty (M2.4's
correct per-snapshot isolation), so `refresh`'s fold saw zero claims. Both
fixed this session (`SqliteStore.use_latest_snapshot`/`touch_seq`,
`copy_patches_from`); the fixture-level proof is
`tests/test_githooks.py::RealHookFiringTest`, driven by real `git commit`/
`git checkout` subprocesses invoking the installed hook scripts, not a direct
`cdp refresh` call.

**Real-target exercise, deliberately scoped down for safety (D19).** A git
repository's hooks directory is shared across every worktree
(`git rev-parse --git-path hooks` resolves to the common `.git/hooks/`) --
confirmed live: installing against a detached worktree of `$TARGET_REPO`
(`sql-pool/sql-pool-api`, pinned commit) placed the hooks in
`/Users/sharmp49/git/unified-store/.git/hooks/`, the real, shared hooks
directory this session's own working copy (`/Users/sharmp49/git/code_scanner`)
also resolves to, since it is itself a linked worktree of that repository.
`cdp githook uninstall` against the same worktree path was run immediately
after and confirmed (by listing the directory) to remove exactly those two
files and nothing else; `git status --porcelain` on the real repo was empty
before and after. Given that, the hook-*firing* acceptance criteria (commit
triggers refresh; branch switch triggers refresh; file checkout does not)
were proven on the fixture instead of risking a second real install/fire
cycle against a live, currently-used repository -- what real-target scale
did confirm is `hooks_dir()`'s worktree-aware resolution and a clean
install/uninstall roundtrip, both above.

## Phase 4 (M4.1) — entailment, exercised on a real module before the gate

Scoped to M4.1 only this session (`PHASE/FINDINGS.md` has the full account,
including the `source_nodes` bug the real-target exercise found and the fix).
`sql-pool/sql-pool-api` scanned fresh into `/tmp/m41_scratch`:

```
verify    41/41 derived claims anchored (0 demoted, rate 0.000)
```

Entailment on those 41 derived claims (read back from `index.db` directly):

```
{"consistent": 39, "contradicted": 0, "entailed": 2}   rate_contradicted: 0.0
```

Matches M4.1's own acceptance line for a derived patch exactly. Per-node
`entailed_ratio` (after the `source_nodes` fix): `root/(files+2)` 0.1667,
`root/src/main/java` 0.0286 -- both low, expected for a module whose claims
are almost entirely `naming`/`ownership`/`test_behaviour` kinds with no
`channel` set, so `entailed` only fires for the `config`/`side_effect`-style
claims built directly from an `io_edge`.

The full-`$TARGET_REPO` number, from the blessed golden `state.json`
(1,278 derived claims, `make check TARGET_REPO=... ` fully green):

```
{"consistent": 1243, "entailed": 35, "contradicted": 0}   rate_contradicted: 0.0
```

Zero contradicted at full scale, on the exact same claims `TARGET.md`'s
census already counts (1,278). `entailed_ratio` by scope ranges 0.0 (most
SQL-migration and C#-only scopes -- no `channel`-bearing claims at all, since
CDP reads no C#, Finding T1) to 1.0 (a few small scopes whose only claims are
process-entrypoint/config-read facts an `io_edge` already states);
`sql-pool-manager` (14/19 claims entailed, 0.74) is the highest non-trivial
concentration. `make check`'s own two full-target passes (determinism,
`fold --check`, golden) all green with this data live -- see
`PHASE/FINDINGS.md` for the two real defects the exercise found
(`source_nodes` breaking the per-scope ratio, and `fold_hash`'s
`extraction=None` vs `extraction={}` inconsistency) before this number was
trustworthy.

## Phase 4 (M4.2) — the four unknown gates, exercised on a real module

Scoped to M4.2 only this session (`PHASE/FINDINGS.md` has the full account:
gates 1-3 run in `cmd_collect`, gate 4 (clustering) in `state.fold`, and the
two decisions the plan left open — `subject`/`channel` optional rather than
required, D20; `snapshot_task`'s read path wired with no writer yet, D21).

`sql-pool/sql-pool-api` scanned fresh into `/tmp/m42_scratch`. A hand-written
inbox patch for its one non-empty scope (`root/(files+2)`) carried three
unknowns: a legitimate scope-level one (`subject` = the scope node itself), one
already answered by a real `config_read` io_edge in that scope, and one naming
a fabricated subject. `cdp collect`:

```
gates     2 unknown(s) rejected
  REJECTED unknown (root/(files+2)): already answered by io_edge config-file:.../dropwizard-service-config.yml -> config:logging.type (config_read) at src/main/resources/dropwizard-service-config.yml:21
  REJECTED unknown (root/(files+2)): subject 'Nonexistent.FakeSubject' names nothing in defines[]/io_edges and is not a scope
```

Both gates fired with a cited reason against real target structure, not a
synthetic dict. The legitimate scope-level unknown survived into `state.json`
with `provenance_state: "unexamined"` — the honest answer given D21 (no
`snapshot_task` writer exists yet in this codebase). Scratch directory
removed after the exercise.

`make check TARGET_REPO=...` (selftest, determinism x2, fold --check x2,
golden x2): green after re-blessing both baselines for the additive
`reports/unknown_gates.json` shape (present, `{}`, on every scan that never
ran `collect` — the same convention `rejected` already established).

## Phase 4 (M4.3-M4.4) — needs_*/R12 and `cdp answer`, exercised on a real module

Scoped to M4.3/M4.4 only this session (`PHASE/FINDINGS.md` has the full
account, including F13 — unknowns silently disappearing across a node's
re-run, which is exactly what R12 forbids — found and fixed this session).
`sql-pool/sql-pool-api` scanned fresh into a scratch dir:

```
$ cdp answer "root/(files+2)" --subject Dockerfile.JDK_JAVA_OPTIONS \
    --kind naming --claim "..." --anchor Dockerfile:17
answer    human.a0000fcd013c02a1  verdict=consistent  confidence=high

$ cdp answer "root/(files+2)" --subject Fake.Thing --kind naming \
    --claim "..." --anchor Dockerfile:99999
cdp: no citable anchor at Dockerfile:99999 -- humans are not exempt from
anchor verification either                                    (exit 2)
```

A hand-written unknown with no `needs` field, submitted via the inbox,
was rejected by `collect` with the closed vocabulary cited in the reason —
the same "gates" reporting mechanism M4.2 already established. `query
unknowns --json` on the same scratch scan showed a real, pre-existing
structural unknown ("What is this module called?") grandfathered exactly as
designed: `needs: needs_human`, `needs_migrated: true`, `status: open`.
Scratch directory removed after the exercise; `make check` (below) is the
full-target confirmation.

## Phase 3 (M3.7) — rollback and `--as-of` exercised on a real module

Scoped to M3.7 only this session (`PHASE/FINDINGS.md` D16-D18 record the
design: an append-only exclusion ledger, log-append-order as the ordering
axis since patches carry no timestamp, and `--as-of` limited to a commit).
`sql-pool/sql-pool-api` scanned into a scratch dir at the pinned commit
(41 claims). A synthetic bad run sharing the derived patch's node was
appended and folded; `cdp rollback --to-run <bad-run>` excluded it and
restored exactly 41 claims; `fold --check` passed against the new ledger;
`cdp query claims --as-of <root-run>` reproduced the same 41-claim answer
read-only. Scratch directory removed after the exercise.

## Phase 5 (M5.1) — runner protocol exercised on a real prompt/patch pair

Scoped to M5.1 only this session (`PHASE/FINDINGS.md` D26-D27 have the
design; M5.2-M5.6 deferred — the phase's remaining milestones carry real
concurrency/crash-simulation weight that does not compress into one
sitting). `sql-pool/sql-pool-api` scanned fresh into a scratch dir (0.34s);
`cdp prompts` produced two real scope prompts, one (`root/(files+2)`) with a
node name containing `/`, `(` and `+` — a real case for the inbox
`__`-replacement convention, not a synthetic one. `SubprocessRunner` (M5.1's
reference runner) was pointed at that real prompt file and wrote a real
patch to the exact `patches/inbox/root__(files+2).json` path `cdp prompts`'
own docstring specifies; `cdp collect` accepted it unmodified (`accepted 1,
rejected 0`, `41/41 claims kept`) — the file-handoff contract holds against
real node names. Scratch directory removed after the exercise.

## Phase 5 (M5.2-M5.3) — the task state machine and `cdp run`, exercised on a real module

Scoped to M5.2/M5.3 only this session (`PHASE/FINDINGS.md` D28-D31 have the
design; M5.4-M5.6 deferred). `sql-pool/sql-pool-api` scanned fresh into a
scratch dir; `cdp run --wave-all` driven through a real external `--runner-cmd`
script (not an in-process stub) that always contributes a scope-level unknown
and no claims:

```
$ cdp run --wave-all --runner-cmd "python3 fake_runner.py"
wave 0       2 scope(s)  validated 2

$ cdp status
tasks     run cdp-7e10575adf69
    folded         root/src/main/java                       attempts 1
    folded         root/(files+2)                            attempts 1
```

Both real scopes went `pending -> dispatched -> returned -> validated ->
folded` end to end through the actual CLI, coverage held at 100% (the
module's 41 pre-existing structural claims), and `status`'s new per-run task
table rendered correctly. Scratch directory removed after the exercise.

`make check TARGET_REPO=...` (selftest 345 tests, determinism x2,
fold --check x2, golden x2): **all gates green, golden baseline byte-identical,
no re-bless needed** — `cdp run`/`supervisor.py` are additive and untouched by
`scan`/`fold --check`/`golden`'s own pipeline (`make check` never invokes
`cdp run`), so nothing in `state.json`'s shape moved.

## Phase 5 (M5.4) — leases, exercised on a real scratch scan of `sql-pool-api`

Scoped to M5.4 only this session (`PHASE/FINDINGS.md` has the full account;
M5.5/M5.6 deferred to their own sessions, per the user's explicit scoping
choice this session — the remaining milestones carry independent
crash/measurement weight that does not compress into one sitting). A fresh
scan of `sql-pool/sql-pool-api` into `/tmp/m54_scratch` (removed after the
exercise) was used to exercise the new `SqliteStore.acquire_lease`/
`heartbeat_lease`/`release_lease` directly against real target state, via two
independent connections to the same `index.db`:

```
acquire (A):                                              True
acquire (B), same live lease:                              False
acquire (B) after release:                                 True
acquire (A) after B's lease expired (simulated death):      True
```

Atomic acquisition, no double-claim across two live connections, and
expiry-based reclaim all hold against a real scanned store, not just the
fixture-scale unit tests (`tests/test_supervisor.py` `LeaseTest`,
`HangingRunnerLeaseTest` — 5 new tests, all passing at millisecond lease
durations so the suite stays fast; the real 90s/30s constants are exercised
only by construction, not by a real-time wait, per `PHASE/EXECUTION_RULES.md`
R-E2/R-E5).

`make check TARGET_REPO=...` (below) is the full-target confirmation that
nothing about `scan`/`fold --check`/`golden`'s own pipeline moved — leases are
additive `snapshot_task` bookkeeping (`wall_ms` column, SCHEMA_V5) that
`cmd_run` alone writes, and `make check` never invokes `cdp run`.

## Phase 5 (M5.5-M5.6) — `--resume` and the fixed-overhead measurement, on a real scratch scan

Scoped to M5.5/M5.6 only this session (M5.1-M5.4 already landed). `sql-pool/
sql-pool-api` scanned fresh into `/tmp/m55_scratch` (removed after the
exercise). `cdp run --wave-all` (fake runner) folded both real scopes, then a
crash was simulated by force-setting one already-`folded` task back to
`dispatched` with a lapsed lease directly in `index.db`:

```
$ cdp run --wave-all --resume --runner-cmd "python3 fake_runner.py"
resume    run cdp-7e10575adf69: partition unchanged, reclaimed 1 task(s) past lease
wave 0       1 scope(s)  validated 1
```

Exactly one scope redispatched (the reclaimed one); the other stayed `folded`
and untouched — the concrete form of "leave folded tasks untouched and
unpaid-for again" against real target state, not a synthetic count. The
partition-drift path (file edit -> new `scope_hash` -> new run opening,
inheriting the unchanged scope) is exercised at fixture scale only
(`tests/test_supervisor.py` `RunCommandEndToEndTest`
`test_resume_with_changed_partition_opens_a_new_run_inheriting_unchanged_scopes`)
— reproducing it against this target would need a second real scratch scan
after editing a tracked file, which this session's budget did not allot
alongside the crash-scenario exercise above.

`cdp prompts --measure` on the same scratch scan (M5.6, 4.9 — `CDP_CLI_SCOPE.md`
marks this "unverified, measure first"):

```
measured  2 leaf prompt(s), chars/4 token estimate (not a real tokenizer)
  structure     26122 chars  (13061/leaf avg)
  inherited     11713 chars  (5856/leaf avg)
  files          5457 chars  (2728/leaf avg)
  gaps           3115 chars  (1557/leaf avg)
  task           2446 chars  (1223/leaf avg)
  header          585 chars  (292/leaf avg)
total     12358 tokens_est (6179/leaf avg)
fixed     757 tokens_est (378/leaf avg) -- header+task, independent of scope content
variable  11601 tokens_est (5800/leaf avg)
```

**The measured number is ~378 tokens/leaf, not ~10k.** See `PHASE/FINDINGS.md`
for the batching decision this number drives, and the caveat about what it
does and does not cover (CDP's own prompt template only — not a real model's
tokenizer, and not the system-prompt/tool-definition overhead a real agent
framework adds on top, which lives outside this codebase and Phase 9's
runner adapters).
