# Phase 3 — Freshness & history

**Goal.** Make expensive knowledge survive a commit where it still holds, and
retire itself visibly where it does not. This is the phase where CDP does
something no peer system does: claims are anchored to literal source text, so
re-verifying the whole corpus at a new commit costs zero tokens.

`RESEARCH_GRAPHIFY.md §7.4`: *"No other property in this document is as
differentiating."* `CDP_CLI_SCOPE.md §L` ranks `refresh` third of five.
Freshness *is* the product.

## Scope items

| id | Item |
|---|---|
| 0.8 | Two freshness dates |
| 0.9 | Review invalidation (R9) |
| 0.10 | Snapshot retention rule |
| 0.11 | Incremental extract |
| 3.1 | `cdp refresh` |
| 3.2 | `cdp diff` |
| 3.3 | Scope-hash caching |
| 3.4 | `cdp rollback` |
| 3.5 | `query --as-of` |
| 3.6 | Staleness signal |
| 3.7 | Git hooks |
| — | `cdp gc` (falls out of 0.10) |

## Preconditions

Phase 2 complete. Specifically: claim lineage spans snapshots (0.7),
verification lives in the fold, and snapshots are identified by
`(repo_id, commit_sha)`. None of this phase is expressible without those three.

## Milestones

### M3.1 — Two dates, and what staleness actually means (0.8, 0.9, 3.6)

Two columns, always:

- `anchor_verified_at` — machine-checked, free, updated by every refresh.
- `claim_reviewed_at` — a model re-read the context. Expensive.

R8: **an anchor surviving is not a claim being fresh.** Conflating them is how a
system reports 100% freshness while every interpretation in it is two years old.

**Staleness = churn in the anchored file since `claim_reviewed_at`** — computed
from `git log --numstat`, not from elapsed time and not from commit count. A
claim about a file untouched for two years is not stale.

R9, the invalidation rule: any diff to the anchored file means
`claim_reviewed_at` does **not** carry forward. Sole exception — a pure rename
at `git diff -M` 100% similarity: path moved, content identical, anchor
relocates, review stands. Rename **plus** edit means review needed.

`status` reports **"anchored but unreviewed"** as its own bucket. It is not a
subset of stale and not a subset of live; it is the population `run --stale-only`
targets.

**Acceptance.** A formatting-only commit relocates anchors and carries review
forward. A one-line semantic edit to a cited file moves its claim into
"anchored but unreviewed" without demoting it. A two-year-old claim in an
untouched file is reported live, not stale.

### M3.2 — Incremental extract (0.11)

`git diff --name-status -M <prev> <new>` → re-extract changed files only, carry
the rest forward. This works because `extract_file()` is already pure per-file
(`extract.py`).

**Graph, resolve and dataflow are always recomputed.** One moved file can change
the whole DAG; a cached graph is a wrong graph. This is not an optimisation to
revisit later — it is a correctness requirement.

**Acceptance.** On `$TARGET_REPO`, a 7-file commit re-extracts 7 files and
produces a snapshot byte-identical to a full rescan at the same commit. That
equality test is the whole milestone; without it, incremental extract is a
silent divergence generator.

### M3.3 — `cdp refresh` (3.1)

```
new snapshot at HEAD  →  re-verify every live claim  →  fold
```

Per claim, five outcomes:

| Condition | Action |
|---|---|
| anchor resolves, same line | carry forward |
| anchor resolves, moved | relocate, bump `anchor_verified_at` only |
| file renamed @100%, not edited | relocate, review **stands** (R9 exception) |
| file edited | relocate, review **invalidated** |
| anchor gone | demote → unknown, reason `"code changed at <sha>"` |

**Rename-awareness is mandatory, not a nice-to-have.** Without it, every anchor
in a renamed file fails `FileCache.lines()` (`verify.py:43-46`) and one `git mv`
of a package mass-demotes a correct corpus. `RESEARCH_GRAPHIFY.md §7.4` calls
this "the landmine in the whole proposal". Read `git diff -M --name-status
<old>..<new>` and rewrite the `file` field **before** verifying.

Note what is preserved for free: `anchor.py:15-18` normalises interior
whitespace precisely so an anchor survives an indentation-only pass, and
`verify_anchor` (`anchor.py:142-169`) already returns the true line. The
relocation machinery exists; refresh is what finally calls it.

Adopt the peer system's presentation for decayed claims — mark them
**"code changed — re-verify"** rather than deleting them silently
(`RESEARCH_GRAPHIFY.md §7.12`, the one thing worth taking from their memory
layer).

**Acceptance.** The `ARCHITECTURE.md` scenario reproduced on `$TARGET_REPO`:
6 changed + 1 renamed → re-extract 7, carry the rest, N live / M demoted /
K anchored-but-unreviewed, and the refresh costs **zero** model calls.

### M3.4 — Scope-hash caching (3.3)

Unchanged scope hash → reuse the claim, skip the agent. This also fixes a real
defect: re-running a node today **accumulates** rather than replaces — both
patches are `complete` and neither supersedes the other (`state.py:44,131`, and
`ARCHITECTURE.md`'s sharp-edges table).

**Acceptance.** Re-running one scope twice yields one generation, not two.
Refresh after a commit touching 2 of 17 scopes dispatches 2 scopes, not 17.

### M3.5 — `cdp diff` (3.2)

Typed structural deltas between two snapshots: new/removed modules and edges,
moved anchors, coverage regression. One build, three consumers — `refresh`, a
reviewer agent, a CI/CD agent.

CDP's channels are typed, so this reports a **reviewable finding**, not churn:
*"`sql-pool-api` now imports `sql-pool-dal`, and that edge is not declared in any
manifest"*. That is the declared-vs-observed divergence analysis (`graph.py:1-14`)
applied across time instead of across sources.

**Acceptance.** Diff across two real commits of `$TARGET_REPO` names a route
added, a table gaining a writer, or an undeclared dependency appearing —
something a reviewer would act on.

### M3.6 — Retention and `cdp gc` (0.10)

A snapshot is kept iff **HEAD, pinned, or cited** by a live claim's
`last_verified`. One sentence, fully determining. `gc` drops the rest;
ephemeral dirty-tree snapshots auto-GC.

**Acceptance.** `gc` on a store with 5 snapshots and claims citing 2 keeps HEAD +
those 2. A test asserts `gc` never removes a snapshot a live claim depends on —
the failure mode here is silent corpus destruction.

### M3.7 — `rollback` and `--as-of` (3.4, 3.5)

`rollback --to-run R` re-folds excluding R's patches; `--to-snapshot S` re-folds
up to S. Excluded patches are marked `superseded_by_rollback`, **never deleted**
(R5). A `fact_run_event(rolled_back, reason)` is appended in Phase 9 — the run
still happened and nothing is retracted.

`query --as-of <commit|time>` is a free consequence of immutable patches plus a
deterministic fold: state at any point = fold(patches up to that point). If it
is *not* nearly free, the fold is not as pure as Phase 2 believes, and that is
the finding.

**Acceptance.** Rollback of a bad run restores the prior state hash exactly.
`--as-of` reproduces the state a past `cdp status` printed.

### M3.8 — Git hooks (3.7)

`post-commit` / `post-checkout` → auto-refresh via the store pointer from 2.3.
Embed the absolute interpreter path at install time so the hook survives GUI git
clients and CI (`RESEARCH_GRAPHIFY.md §2`).

Opt-in, never installed by default, and `cdp` must remain fully usable with them
off. A hook that fires on every commit in a large monorepo needs a cost
statement attached before anyone enables it.

**Acceptance.** Commit triggers refresh; branch switch triggers refresh;
`git checkout -- <path>` does not (documented, matching the peer behaviour).
Uninstalling leaves no trace.

## Modules touched

`refresh.py` (new), `snapshot.py` (incremental extract, retention), `diffs.py`
(new), `verify.py` (rename rewriting), `store/` (lineage queries, rollback
re-fold), `query.py` (`--as-of`), `cli.py` (`refresh`, `diff`, `rollback`, `gc`),
hook scripts.

## Stress tests

| Case | Expectation |
|---|---|
| `git mv` of a whole package | **Zero** mass demotion. The landmine test. Run it on `$TARGET_REPO` at real scale, not on a 12-file fixture. |
| Rename **and** edit in one commit | Anchor relocates, review invalidated. Both halves, not one. |
| Reformat-only commit (whole repo) | Anchors survive via `normalise_ws`; review carries forward only where content is genuinely identical. Verify the two are distinguished. |
| File deleted, claim existed | Demote to unknown with the deletion as the reason. Do **not** mark `moot` — that word is reserved for a subject disappearing (R12, Phase 4). |
| Rebase / force-push rewrites history | `<prev>` snapshot's commit no longer exists. `git diff` fails. Detect and fall back to a full re-extract rather than producing a wrong incremental diff. This is likely and easy to miss. |
| Refresh across 200 commits at once | Diffing HEAD~200..HEAD is one diff, not 200. Verify cost is a function of changed files, not of commit count. |
| Shallow clone | `git log --numstat` for staleness has no history. Degrade to "unknown churn" and say so; never report "not stale" from missing data. |
| Claim anchored in a file that became binary | `read_lines` returns `[]` for null-byte files (`util.py:191-192`). Demote with a distinguishable reason, not `anchor_not_found`. |
| Refresh while a `run` is in flight | Phase 5 territory, but the interaction starts here: refresh changes the partition under a running supervisor. Note the requirement now — 4.6's `partition_hash` guard is what resolves it. |

## Exit criteria

- `refresh` on `$TARGET_REPO` across a real multi-commit range: zero model calls, correct relocate/demote/invalidate split, and the `git mv` test passes at scale.
- Incremental extract provably equals full rescan at the same commit.
- Three buckets visible in `status`: live · anchored-but-unreviewed · demoted.
- `gc` never drops a cited snapshot.
- `rollback` restores an exact prior state hash; `--as-of` reproduces past state.
- Hooks install, fire, uninstall cleanly and are off by default.
- `make check`, determinism gate, `fold --check`, order-independence all green.

## Out of scope

Re-reviewing stale claims — that needs `run --stale-only` (Phase 5). This phase
*identifies* what needs re-review and makes the identification free; it does not
pay for the re-review. `compact` and `verify --full` are Phase 7.
