# Phase 7 — Scale & durability

**Goal.** Make the unit of work a *scope* rather than a repo, so a team working
three modules does not pay for two thousand; and make compaction provably
lossless rather than asserted.

`CDP_CLI_SCOPE.md §D`: *"Monorepo / multi-team pressure. Cheap now, brutal to
retrofit."* Most of the retrofit cost was already paid in Phase 2 — the index
set, the store boundary and the cold table were created there for this reason.

## Scope items

| id | Item |
|---|---|
| 2.1 | Scope is the unit, not repo |
| 2.2 | State materialised per scope |
| 2.4 | `cdp compact` |
| 2.5 | `cdp verify --full` |
| 2.6 | Postgres adapter |
| 0.19 | `cdp export` |

## Preconditions

Phase 2 (store boundary, `patches_archive` table, index set) and Phase 3
(retention, so `compact` and `gc` do not contradict each other).

## Milestones

### M7.1 — Scope selector everywhere (2.1)

`refresh`, `query`, `run` and coverage all take a scope selector and touch only
that subtree. **A monorepo is N indexes sharing a commit**, not one index of
size N.

This is mostly plumbing, but coverage is the subtle part: `_coverage`
(`state.py:194-217`) divides complete files by total files across the whole
partition. Scoped coverage must report the scope's own denominator, and a
scope-filtered query must never present scoped coverage as global — that is the
false-absence failure `SKILL.md:58-61` warns about, wearing a new hat.

**Acceptance.** `cdp query --scope <s>` and `cdp refresh --scope <s>` touch only
that subtree, provable by instrumenting store reads. Scoped coverage is labelled
as scoped in every renderer.

### M7.2 — Per-scope materialised state (2.2)

State composed on read from per-scope materialisations rather than one global
blob. A team working 3 modules loads 3, not 2,000.

The fold invariant must survive the split: a full recompute across all scopes
must still equal the composition of per-scope states. That equality is the test.

**Acceptance.** Composition equals global recompute, byte for byte. Load time for
a 3-scope query on a synthetic 2,000-scope store is independent of the 2,000.

### M7.3 — `cdp compact` (2.4)

Superseded rows **move** to `patches_archive` — same DB file, minimal
`(scope_hash, run_id)` index, never touched by hot queries. `--compact-threshold`
defaults to **30%**, customisable. `--keep-generations` defaults to **1**, where
a generation is one `(scope, run)` complete patch.

Because nothing is lost to the archive, `--keep-generations` is a **performance
knob, not a retention decision** — and the CLI help must say so, or someone will
treat it as data loss and never run compaction.

`VACUUM` after large compactions.

**Acceptance.** Compaction on a store with 5 generations per scope moves 4,
leaves hot queries untouched, and reduces the hot table measurably.

### M7.4 — `cdp verify --full` (2.5)

Re-fold from the archive and compare the hash to live state. This is what makes
compaction **provably lossless rather than asserted** — R5 requires that the
archive prove the live state, not merely coexist with it.

It is the same mechanism as `fold --check` (`state.py:235-255`), extended over
the cold table. If Phase 2 kept `check_fold` honest, this is a small milestone.
If it is not small, Phase 2 left something behind.

**Acceptance.** `verify --full` after a compaction reproduces the live state hash
exactly. Corrupting one archived row makes it fail with the row named.

### M7.5 — `cdp export` (0.19)

Four outputs: canonical JSON (feeds the determinism harness from Phase 0) ·
reviewable patch files on demand · archive dump · anonymised corpus.

R1 in practice: files are an export format, not a storage format. The canonical
JSON export is also what keeps the Phase 0 golden test alive after Phase 2 moved
state into SQLite.

**Acceptance.** Canonical JSON export round-trips into the file backend and the
conformance suite passes on it. Anonymised corpus contains no repository paths,
symbol names or claim text — verified by test, not by inspection.

### M7.6 — Postgres adapter (2.6)

Its real justification is a **multi-team shared store**, not scale for its own
sake. The port is near-1:1 given 0.14's JSON columns and expression indexes —
JSON, expression indexes, recursive CTEs and MVCC all carry over.

**Gate this milestone on a real multi-writer requirement.** Building it
speculatively means maintaining two backends to serve one. The conformance suite
from Phase 2 M2.1 is what makes it cheap whenever it is actually needed; until
then, keeping that suite green is the whole investment.

The stated triggers (`CDP_CLI_SCOPE.md §B`): >10M edge rows, or multi-writer.
Unbounded deep traversal would mean a graph DB — but traversal here is bounded at
≤8 hops over ~10² module nodes, so recursive CTEs handle it and that trigger will
not fire. Semantic search would mean `sqlite-vec` / pgvector, same shape.

**Acceptance.** Either the adapter passes the conformance suite, or a written
decision to defer with the trigger condition recorded. Both are acceptable exits;
silently skipping it is not.

## Modules touched

`store/` (per-scope materialisation, archive, Postgres backend), `state.py`
(scoped fold, composition), `query.py` (scope selector, scoped-coverage
labelling), `cli.py` (`compact`, `verify --full`, `export`, `--scope`).

## Stress tests

| Case | Expectation |
|---|---|
| Scoped coverage presented as global | The false-absence failure. Caught by a test asserting every renderer labels it. |
| Scope selector matching nothing | Say so. An empty result that looks like a complete answer is the same bug in a third costume. |
| Compaction during a run | Refuse while a run holds live leases, or compact only runs in a terminal state. Decide and enforce. |
| `verify --full` on a store compacted twice | Must still reproduce. Two-generation archives are where an off-by-one in supersession shows up. |
| Archive grows unbounded | It is meant to. But `export --archive` plus a documented cold-storage path is the answer, not silent deletion — R5 says archive, never destroy. |
| Anonymised corpus leaks identifiers | Test with a repo containing a distinctive symbol name and grep the export for it. |
| Per-scope state and a cross-scope merge conflict | `merge.py`'s `contested` resolution is global by design (`merge.py:169-188`). Per-scope materialisation must not localise it, or two scopes disagreeing would each report themselves confident. This is the highest-risk item in the phase. |

## Exit criteria

- Scope selector on `refresh`, `query`, `run`, coverage; scoped coverage always labelled.
- Per-scope composition equals global recompute, byte for byte.
- `compact` moves superseded generations; hot queries never read the archive.
- `verify --full` proves the live state from the archive.
- `export` produces all four outputs; anonymised corpus verified clean by test.
- Postgres adapter shipped **or** deferred with a written trigger condition.
- Cross-scope `contested` resolution demonstrably unaffected by per-scope materialisation.

## Out of scope

Cross-repo relations (Phase 8) — a different axis entirely. Anything that would
make `link.*` rows load-bearing for `snapshot.*`; R3's non-entanglement test
(5.7) must stay trivially true.
