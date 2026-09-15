# Phase 0 — Baseline & guardrails

**Goal.** Before a single behavioural change: put the product where the scope
document says it lives, and build the instrument that will tell us when a later
refactor broke something. Every subsequent phase rewrites load-bearing code
(`state.fold`, every JSON write, `verify`); without a byte-level baseline over a
real repository those rewrites are unfalsifiable.

Nothing user-visible changes in this phase. That is the point.

## Scope items

| Item | Source |
|---|---|
| Repo layout: `cdp/` as product, skill as vendored consumer | `CDP_CLI_SCOPE.md` preamble |
| Determinism / reproducibility gate | `cli.py:277-280` already asserts it; nothing tests it |
| Validation target selection | `RESEARCH_GRAPHIFY.md §12.4` |
| Test-suite entry point that cannot pass having run nothing | `cli.py:592-599` |

## Preconditions

None. This is the entry point.

## Milestones

### M0.1 — Promote `cdp/` to the repository root

Move `.claude/skills/cdp/{cdp,tests,schema,run.py}` to the repository root; add a
`pyproject.toml` declaring a `cdp` console script over `cdp.cli:main`. Zero
third-party dependencies (`RESEARCH_GRAPHIFY.md §8.7`).

`.claude/skills/cdp/` becomes a **generated** vendored copy: `cdp install` already
does a `shutil.copytree` (`cli.py:564-589`); extend it with a `--self` mode that
refreshes the in-repo skill directory, and add a test asserting the vendored copy
is byte-identical to the source tree. Hand-editing the vendored copy is the drift
failure this test exists to catch.

**Acceptance.** `python3 -m cdp.cli --help` works from the repo root.
`python3 .claude/skills/cdp/run.py --help` still works. `cdp install --self`
produces no diff on a clean tree. All 5 existing test modules pass unchanged.

### M0.2 — Reproducibility gate as an executable test

`cli.py:277-280` claims `manifest.json` is "the only state file containing a
timestamp, and is excluded from the byte-identical reproducibility check for that
reason". No such check exists.

Build `tests/test_determinism.py`: scan the same commit twice into two state
directories, assert every file except `manifest.json` is byte-identical, and
assert `manifest.json` differs only in `generated_at`. Add a `cdp selftest
--determinism <repo>` flag so the gate runs against an arbitrary repository, not
only the fixture.

**Acceptance.** The gate passes on `tests/fixtures/minirepo`, on this repository,
and on `$TARGET_REPO`. A deliberately introduced `set()` iteration in any phase
makes it fail.

### M0.3 — Name and pin the validation target

Record in `PHASE/TARGET.md`: repository, pinned commit SHA, file/module/LOC
counts, languages present, and whether a build manifest sits at its root (which
decides whether Phase 1's 1.1 fix is observable there).

If `$TARGET_REPO` has no root manifest, Phase 1 additionally needs a second
target that does, or a fixture constructed to have one — the bug is otherwise
untestable on real input.

**Acceptance.** `TARGET.md` exists with a pinned SHA. `cdp scan --repo
$TARGET_REPO` completes and its phase counts are recorded as the baseline.

### M0.4 — Capture the golden baseline

Run `scan`, `docs` and all 13 queries against `$TARGET_REPO@<pinned>`; store
canonical JSON under `tests/golden/<repo>@<sha>/`. Add `tests/test_golden.py`
which diffs current output against it and **prints the diff** rather than only
asserting inequality — a regression test whose failure message is `False != True`
costs more than it saves.

Golden files are updated by an explicit `--bless` flag, never silently.

**Acceptance.** Golden test passes. Deleting one `io_edge` from an extractor
produces a readable, localised diff.

### M0.5 — Make `selftest` unable to lie

`cli.py:592-599` documents the failure it already hit — in-process discovery
"silently found zero tests instead of saying so". The subprocess fix works but
still reports success on an empty suite.

Assert a minimum test count and fail loudly below it. Add a CI entry point
(`make check` or equivalent) running: selftest, determinism gate, golden diff,
`fold --check`, `check_order_independence`.

**Acceptance.** `make check` is green. Emptying `tests/` makes it red with a
message naming the cause.

## Modules touched

`cli.py` (install `--self`, selftest guards), `pyproject.toml` (new),
`tests/test_determinism.py` (new), `tests/test_golden.py` (new). No logic
changes in any pipeline module.

## Stress tests

| Case | Expectation |
|---|---|
| `$TARGET_REPO` is not a git repo | `inventory["source"] == "walk"`, the structural unknown at `cli.py:293-303` fires, baseline still captured — with a note that the walk fallback is noisier and the golden set will churn. |
| Target has files with undecodable bytes | `read_lines` (`util.py:181-193`) decodes lossily; two runs must still be byte-identical. Add a fixture file with a bad byte. |
| Target has a submodule | `git ls-files` lists the submodule as one gitlink entry. Record the observed behaviour in `TARGET.md`; do not fix it here. |
| Golden set is enormous | If `$TARGET_REPO` produces >20 MB of canonical JSON, store hashes per file plus full bodies for `state.json`/`graph.json`/`partition.json` only. Decide at M0.4, record the decision. |
| Two developers on different filesystems | `inventory["repo"]` is an absolute path (`inventory.py:85`) and will differ. The golden diff must normalise it, or the gate fails for everyone but its author. |

That last one is the most likely to bite and is cheap to get right now.

## Exit criteria

- `cdp` importable and runnable from the repo root; vendored skill copy generated and verified.
- Determinism gate, golden diff, `fold --check` and order-independence all green on the fixture **and** on `$TARGET_REPO`.
- `TARGET.md` pins a commit; baseline counts recorded.
- `make check` is the single command every later phase must keep green.

## Out of scope

No behaviour changes, no new commands, no schema changes, no store work. If a
bug is found while building the baseline, record it in Phase 1 rather than fixing
it here — a baseline captured mid-fix describes nothing.
