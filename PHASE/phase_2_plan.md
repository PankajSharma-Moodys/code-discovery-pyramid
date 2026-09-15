# Phase 2 — Store & schema

**Goal.** Replace seven JSON files and a patch directory with a SQLite store
behind a module boundary, so that claims can span snapshots, provenance is a
column, and the fold stops being O(every patch ever written). This is the phase
everything downstream depends on and the phase most likely to go wrong, so it
ships in two halves: the boundary first with today's file backend behind it, then
SQLite behind the same boundary.

R1 in one line: **provenance is a column, not a directory. Files are an export
format, not a storage format.**

## Scope items

| id | Item |
|---|---|
| 0.1 | Store module boundary — all SQL in one module |
| 0.2 | Workspace store: `snapshot.*` · `claim.*` · `link.*` namespaces |
| 0.3 | `patches` table — append-only, immutable, content-addressed |
| 0.4 | Provenance as columns |
| 0.5 | Incremental fold — materialised on insert |
| 0.6 | Snapshot model, `(repo_id, commit_sha)`, ephemeral for dirty trees |
| 0.7 | Claim lineage spans snapshots |
| 0.12 | `runs` + `tasks` tables |
| 0.13 | Separate `link_runs` / `link_tasks` |
| 0.14 | JSON columns + expression indexes |
| 0.15 | Index set |
| 0.16 | `patches_archive` cold table (created, not yet used) |
| 2.3 | Store resolution — registry, `.cdp.toml`, repo identity |
| — | Verification moves into the fold (`RESEARCH_GRAPHIFY.md §7.4` prerequisite) |

## Preconditions

Phase 1 complete. The golden baseline and determinism gate are the only thing
that will tell us a 7-file-to-SQLite migration preserved meaning.

## Why verification moves in this phase, not Phase 3

`refresh` (Phase 3) needs to re-verify existing claims at a new commit. Today
verification happens at collect time and the *post*-verification patch is what
enters the log (`cli.py:476-478`), while the log is append-only with no
compaction (`state.py:73-93`) and supersession is per-node and status-only
(`state.py:44,131`). Re-verification has nowhere to write.

It could be deferred to Phase 3, but 0.5 materialises state **on insert**, and
whether verification runs inside that insert path changes its design completely.
Retrofitting verification into an already-built incremental fold is the exact
class of rework `CDP_CLI_SCOPE.md §D` warns about ("cheap now, brutal to
retrofit"). So it happens here.

The change strengthens the invariant rather than bending it. The log stores
**raw agent output**; `fold` becomes `fold(patches, xref, partition, repo)`; and
`state` becomes fully derived — more faithful to `state.py:1-14`'s own stated
invariant than today's design, where verification is a baked-in side effect that
`check_fold` cannot reproduce from the log alone.

## Milestones

### M2.1 — Store boundary with a file backend (0.1)

Define `store/` with an interface covering every read and write the pipeline
performs today. Implement it over the existing JSON files. **No behaviour
changes.** Nothing outside `store/` touches the filesystem for state, and
nothing outside `store/` will later import `sqlite3`.

Write a **backend conformance suite** — one set of tests both backends must
pass. This is what makes M2.2 a swap rather than a rewrite, and what makes 2.6's
Postgres adapter a small job later, designed against real query shapes rather
than guessed ones.

**Acceptance.** Golden diff empty. Determinism gate green. `grep -rn "read_json\|write_json" cdp/ --include=*.py | grep -v store/` returns only genuine non-state IO.

### M2.2 — SQLite backend (0.2, 0.3, 0.14, 0.15, 0.16)

Three namespaces, one file:

- `snapshot.*` — structure. Immutable, disposable, per-commit.
- `claim.*` — claims, patches, lineage. Precious, spans snapshots.
- `link.*` — cross-repo, derived. Tables created here, populated in Phase 8.

`patches` is append-only, immutable and **content-addressed**: re-collecting an
identical patch is a no-op by hash, which buys idempotency for free. Payloads
are JSON columns with expression indexes (`json_extract(payload,'$.subject')`),
giving document flexibility and relational joins in one stdlib engine.

Index set per 0.15: `(snapshot_id, fqn)` · `(snapshot_id, file)` ·
`(snapshot_id, scope_hash)` · expr on `$.subject`, `$.kind` · unique
`(repo_id, commit_sha)` · `(run_id, state)` on tasks · `(scope_shape_hash)`,
`(run_id)` on trajectories.

`patches_archive` is created now with its minimal `(scope_hash, run_id)` index
and left empty — Phase 7's `compact` fills it. Creating it here means no
migration later.

**Schema migrations are versioned from row zero.** A `schema_version` table and a
forward-only migration runner. Adding this after the first real store exists is a
data-migration problem instead of a two-hour job.

**Acceptance.** Conformance suite passes on both backends. Golden diff empty when
state is exported back to canonical JSON. `sqlite3` imported in exactly one
module — enforced by test.

### M2.3 — Provenance as columns, verification inside the fold (0.4, 0.5)

Columns: `author_kind` (`python|llm|human`), `model`, `run_id`, `verdict`,
`template_version`, `lessons_version`.

Move `verify_all` (`verify.py:133-167`) out of `cmd_collect` and into the fold
path. `state` materialises on insert rather than recomputing from history — this
is what kills the O(all-patches-ever) read at `state.py:51-67`, the real wall at
monorepo scale.

**The hard part is preserving order-independence.** `check_order_independence`
(`state.py:258-278`) tests the property rather than asserting it, and it exists
because an order-dependent merge is deterministic-but-arbitrary and would score
1.0 on a naive determinism harness. Incremental materialisation is inherently
order-sensitive in its *implementation*; the test must keep passing over its
*result*. Budget real time for this. If incremental fold cannot be made
order-independent, the correct response is to keep the full fold and pay the
cost — not to relax the test.

Keep `check_fold` working: a full recompute from the patch table must reproduce
the materialised state exactly. That is the audit story, and Phase 7's
`verify --full` is the same mechanism over the archive.

**Acceptance.** `fold --check` and `check_order_independence` green. A synthetic
2,000-scope log folds in bounded time and its incremental result is byte-identical
to the full recompute. Verification is re-runnable against a different commit
without mutating the log.

### M2.4 — Snapshots and claim lineage (0.6, 0.7)

Identity is `(repo_id, commit_sha)`, unique. A dirty tree is **allowed** but
marked `ephemeral=true` with a tree hash, auto-GC'd, and **never citable by a
durable claim**. That last clause is what stops a claim from being anchored to a
state nobody can reproduce.

A claim is *anchored at* a snapshot, not stored *inside* one. This one modelling
decision is what makes `refresh` expressible at all (Phase 3) — without it, a
claim dies with its snapshot and freshness is just rescanning.

N snapshots coexist. Retention lands in Phase 3 (0.10) alongside `gc`.

**Acceptance.** Two scans at different commits produce two snapshots; claims from
the first are still queryable after the second. A dirty-tree scan produces an
ephemeral snapshot, and an attempt to durably anchor against it is refused with a
reason.

### M2.5 — `runs` and `tasks` tables (0.12, 0.13)

```
runs(run_id, snapshot_id, partition_hash, status, started_at, finished_at,
     model, template_version, lessons_version)
tasks(run_id, scope_hash, state, attempts, dispatched_at, lease_until,
      last_error, patch_hash)
```

Created here, driven in Phase 5. They turn "it didn't work well" into a table,
and they are what separates `unexamined` from `unknown` from `abandoned` in
Phase 4's unknown discipline — today all three look identical.

`link_runs` / `link_tasks` live in the `link.*` namespace, keeping R3's
non-entanglement test (5.7) trivially true and allowing independent audit.

**Acceptance.** Tables exist with 0.15's indexes. `cdp status` reads a per-run
task table, empty for now. A test asserts dropping every `link.*` row leaves
`snapshot.*` and `claim.*` byte-identical.

### M2.6 — Store resolution (2.3)

Order: `--store` → `CDP_STORE` → `.cdp.toml` walking up → `~/.cdp/config.toml`
registry → `./.cdp/index.db`.

The registry is the **default** — zero litter in someone else's checkout, which
preserves the argument at `cli.py:14-17`. In-repo `.cdp.toml` is **opt-in** for
teams: git hooks find it without registration, and a teammate cloning inherits
the store URL.

**Repo identity is never the filesystem path.** Declared id → normalised origin
remote → UUID. This dissolves the `--in-repo` dilemma that `RESEARCH_GRAPHIFY.md
§12.2` raised and that blocked Phase 1's hook from working under the default
layout, and it fixes the sharp edge in `ARCHITECTURE.md` where a second scan
silently clobbers the first.

Once this lands, revisit Phase 1 M1.6: the hook's third no-op condition ("state
not resolvable") becomes resolvable in the common case, and the `--in-repo`-only
restriction can be lifted. Do that lift in this milestone — leaving it stated but
undone is how a documented limitation outlives its cause.

**Acceptance.** Same repo cloned to two paths resolves to one store. Two
different repos never collide. A repo with no remote and no declared id gets a
stable UUID that survives a move. The Phase 1 hook works without `--in-repo`.

## Modules touched

`store/` (new, the only module importing `sqlite3`), `snapshot.py` (new),
`state.py` (fold rewritten, invariants preserved), `verify.py` (moves into the
fold path), `cli.py` (`_paths` replaced by store resolution), `query.py` (reads
rows, keeps renderers — Phase 1's budget work survives intact), every phase
module's write path.

## Stress tests

| Case | Expectation |
|---|---|
| Migration from an existing `.cdp/` directory | An import path must exist, or every current user loses their claim corpus. Not optional. |
| Store file corrupted mid-write | Writes are transactional; a killed `scan` leaves either the previous snapshot or the new one, never a half-snapshot. Test with a SIGKILL harness. |
| Two `cdp` processes, same store | SQLite's default locking will surface as `database is locked`, not corruption. Decide and document: fail fast with a clear message. Multi-writer is 2.6/Postgres, not this phase. |
| Same content, two different patches | Content-addressing makes the second a no-op. Verify it does not also silently drop a differing `run_id` that we needed for audit. |
| Dirty tree scanned, then committed unchanged | Ephemeral snapshot and durable snapshot have different ids but identical structure. The durable one must supersede cleanly; the ephemeral must GC without taking claims with it. |
| A claim anchored at snapshot S, S is GC'd | 0.10 says a snapshot is retained iff HEAD, pinned, or cited by a live claim's `last_verified`. Retention is Phase 3, so **this phase must refuse to GC at all** rather than implement half the rule. |
| Incremental fold vs. order-independence | Covered in M2.3. This is the single highest-risk item in the phase. |
| `json_extract` performance at 2,000 scopes | Measure, do not assume. If expression indexes underperform, the fallback is a materialised column — decide with a number. |

## Exit criteria

- All SQL in `store/`; `sqlite3` imported exactly once; enforced by test.
- Conformance suite passes on file and SQLite backends.
- `fold --check` and `check_order_independence` green; incremental fold matches full recompute byte for byte.
- Verification runs inside the fold and is re-runnable at a different commit.
- N snapshots coexist; claims outlive the snapshot they were made against.
- Store resolves by repo identity, not path; Phase 1's hook works under the default layout.
- Golden diff empty when the store is exported to canonical JSON.
- Determinism gate green on `$TARGET_REPO`.

## Out of scope

`refresh`, `diff`, `rollback`, `--as-of`, `gc`, retention (all Phase 3).
`compact`, `verify --full`, Postgres (Phase 7). Trajectory store — it is a
**separate DB** at `~/.cdp/trajectories.db` (0.17) precisely so a workspace
rebuild cannot destroy it, and it lands in Phase 9.
