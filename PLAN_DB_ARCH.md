# CDP storage: database architecture (refines PLAN_STORAGE.md)

Budget: 170 lines. Design only, no migration (fresh rescans; 3 snapshots on this machine). Probes were read-only on `~/.cdp/index.db` (SQLite 3.51.0) plus `git` on unified-store, 2026-10-17, then deleted. No Postgres server is available here: every PG claim is **(unverified)** at runtime.

## 1. What scan/refresh write today

- **New commit = new row; same commit = overwrite.** `begin_snapshot` inserts `(repo_id, commit_sha)` if absent, else reuses it, and bumps `touch_seq` and **commits before any data is written**, so a half-written snapshot is "latest" at once (`sqlite_backend.py:390-413`). Artifacts are then upserted one commit each (`:949-955`). Unchanged HEAD: refresh returns early (`refresh.py:243-245`).
- **Dirty tree:** key `sha+dirty:<treehash>`, `ephemeral=1` (`snapshot.py:92-99`). `refresh` refuses it (`refresh.py:236-238`), `scan` accepts it; `prune_ephemeral` keeps at most one per checkout (`sqlite_archive.py:75-101`).
- **Full copies:** refresh writes all 10 artifacts (`refresh.py:294-321`; 578 MB for snapshot 2) after recomputing graph/xref/dataflow in full (`:265-277`) with per-*module* extraction (`:73-81`). The claim log is copied verbatim (`copy_patches_from`, `sqlite_backend.py:888-916`, via `refresh.py:183-199`) in its own commit.

**Measured (snapshot 2, unified-store):** 4,761 files (4,162 with facts); fact rows/file median 30, p90 224, max 5,734; 1,172 dirs, depth median 4, files/dir median 3, max 293; defining-file fan-in median 2, p90 10, max 209. Files changed per refresh (`git diff --shortstat`, 300 first-parent commits): 1 commit median 3, p90 31; 5 commits 19-299; 20 commits 122-593.

## 2. Central decision: what a new snapshot writes

All three options share the same objects: blobs, segments and docs, content-addressed and written only when new. They differ only in the per-snapshot file table. The probe used 4,761 rows of `(snapshot_id, path_id, blob_id, module, role, lang, bytes, flags, fseg, xseg, wseg)`, `WITHOUT ROWID`.

| | A. Full manifest per snapshot | B. Delta on parent (chain) | C. Git-like tree objects per directory |
|---|---|---|---|
| Rows per refresh (3 / 31 / 50 / 300 files changed) | 4,761 always | 3 / 31 / 50 / 300 | 251 / 1,549 / 1,969 / 3,902 (simulated) |
| Bytes per refresh | **0.35 MB** measured (74 B/row; ~0.6 MB with 3 indexes, est.) | ~74 B × changed | ~74 B × tree rows |
| Write time | 7.2 ms measured | <1 ms | ~3 ms (est.) |
| Full listing | 1.08 ms measured | 2.7 ms at chain depth 20, 50 changed per step (window query) | recursive walk over 1,172 trees (est. 3-5 ms) |
| Point lookup (file → segments) | 2.5 µs measured | 5.5 µs measured | depth+1 ≈ 5 probes |
| gc | anti-join; deleting a snapshot touches nobody else | deleting a middle snapshot needs its child rebased (materialized) first | mark = recursive reachability over trees |
| Crash/concurrency | one txn inserts rows | one txn, but parent must stay alive | one txn; trees are shared objects |

**Recommendation: A, a full manifest per snapshot.**
- A costs 0.35 MB per refresh; the docs a refresh writes anyway are ~0.88 MB zlib (§3), so B saves at most ~30% of refresh bytes.
- B's parent pointer is broken routinely: `retention` drops arbitrary middle snapshots (`snapshot.py:257-293`) and `prune_ephemeral` drops dirty parents; each drop becomes a rebase. Checkpoints only bound the chain.
- C writes 251 rows for a 3-file edit (root and wide dirs, up to 293 entries, are rewritten): only 19× less than A, and every read turns recursive.
- With A a snapshot is exactly its rows, so `delete_snapshot`, `diff --old-sha` and every query stay one join deep.

## 3. Per-snapshot derived data: segment, doc, or derived at query time

| Data (snapshot 2 raw → zlib) | Storage | On refresh |
|---|---|---|
| extract defines/uses/imports/io (330 MB) + per-file meta `extract.files` | `fseg` keyed by `(blob, path, xver)`; `f_*` rows | reused on key hit; only misses extracted (per **file**: `declared_deps`/`module_notes` go to per-file `f_note`, removing `refresh.py:73-81`'s module reason) |
| xref `uses` (88 MB) | `xseg` keyed by the hash of the file's resolved rows | xref recomputed in full; rows hashed per file; only new hashes insert. Expect changed files + dependents (fan-in p90 10) |
| dataflow `edges` (33 MB) | `wseg`, same scheme | same |
| xref `symbols` (37 MB → 1.9 MB), `used_by` (46 MB) | **not stored**: query `f_def`/`x_use` through the manifest | nothing to write |
| xref aggregates: constants, routes, collisions, coupling, … (6.6 MB → 444 KB) | `doc` | rewritten; deduplicated by hash when unchanged |
| dataflow paths/sources/boundaries (2.1 MB → 103 KB) | `doc` | rewritten |
| state (2.0 MB → 131 KB), partition (53 KB), graph (13 KB), schedule, manifest, ledger, reports, rule_edges | `doc` | rewritten; identical ones dedupe |
| inventory | is `snapshot_file` (+ a counts doc) | — |
| code (27 MB) | view over `blob` (non-generated `role='source'`) | — |
| derived patch 0000 (1.8 MB → 125 KB) | `patch_body` by content hash | regenerated (`refresh.py:308-310`) |
| carried claim log | `claim_patch` rows point at `patch_body`; copy = new rows, no body copy | copied inside the final txn |
| cross-file `partial_overloads` sig rewrites | `snapshot_overlay(snapshot_id, fseg, ord, sig_id)` | recomputed |

## 4. DDL (SQLite; Postgres by mechanical substitution below)

```sql
CREATE TABLE str  (id INTEGER PRIMARY KEY, h64 INTEGER NOT NULL UNIQUE, s TEXT NOT NULL);
CREATE TABLE alts (id INTEGER PRIMARY KEY, h64 INTEGER NOT NULL UNIQUE, ids BLOB NOT NULL); -- packed int64 str ids
CREATE TABLE blob (id INTEGER PRIMARY KEY, sha BLOB NOT NULL UNIQUE, size INTEGER NOT NULL, z BLOB);
CREATE TABLE fseg (id INTEGER PRIMARY KEY, blob_id INTEGER NOT NULL, path_id INTEGER NOT NULL, xver_id INTEGER NOT NULL,
  lang_id INTEGER, package_id INTEGER, loc INTEGER, meta_doc INTEGER, UNIQUE (blob_id, path_id, xver_id));
CREATE TABLE f_def (seg INTEGER NOT NULL, ord INTEGER NOT NULL, line INTEGER, end_line INTEGER,
  fqn INTEGER, kind INTEGER, sig INTEGER, extra INTEGER, PRIMARY KEY (seg, ord)) WITHOUT ROWID;
CREATE TABLE f_use (seg INTEGER NOT NULL, ord INTEGER NOT NULL, line INTEGER, span INTEGER, kind INTEGER,
  name INTEGER, guess INTEGER, alts INTEGER, flags INTEGER, extra INTEGER, PRIMARY KEY (seg, ord)) WITHOUT ROWID;
-- f_imp(seg,ord,line,span,fqn), f_io(seg,ord,line,span,source,target,channel,extra), f_note(seg,ord,kind,value): same shape
CREATE TABLE xseg (id INTEGER PRIMARY KEY, h BLOB NOT NULL UNIQUE);
CREATE TABLE x_use (seg INTEGER NOT NULL, ord INTEGER NOT NULL, line INTEGER, from_sym INTEGER, to_sym INTEGER,
  status INTEGER, to_modules INTEGER, extra INTEGER, PRIMARY KEY (seg, ord)) WITHOUT ROWID;
CREATE TABLE wseg (id INTEGER PRIMARY KEY, h BLOB NOT NULL UNIQUE);
CREATE TABLE flow (seg INTEGER NOT NULL, ord INTEGER NOT NULL, line INTEGER, source INTEGER, target INTEGER,
  channel INTEGER, confidence INTEGER, PRIMARY KEY (seg, ord)) WITHOUT ROWID;
CREATE TABLE doc  (id INTEGER PRIMARY KEY, h BLOB NOT NULL UNIQUE, z BLOB NOT NULL);
CREATE TABLE patch_body (h TEXT PRIMARY KEY, z BLOB NOT NULL) WITHOUT ROWID;
ALTER TABLE snapshot_meta ADD COLUMN complete INTEGER NOT NULL DEFAULT 0;
ALTER TABLE claim_patch ADD COLUMN node INTEGER;  -- replaces json_extract(payload,'$.node') index; payload -> patch_body
CREATE TABLE snapshot_file (snapshot_id INTEGER NOT NULL, path_id INTEGER NOT NULL, blob_id INTEGER, module_id INTEGER,
  role INTEGER, lang_id INTEGER, bytes INTEGER, flags INTEGER, fseg INTEGER, xseg INTEGER, wseg INTEGER,
  PRIMARY KEY (snapshot_id, path_id)) WITHOUT ROWID;
CREATE TABLE snapshot_doc (snapshot_id INTEGER NOT NULL, name TEXT NOT NULL, doc_id INTEGER NOT NULL,
  PRIMARY KEY (snapshot_id, name)) WITHOUT ROWID;
CREATE TABLE snapshot_overlay (snapshot_id INTEGER NOT NULL, fseg INTEGER NOT NULL, ord INTEGER NOT NULL, sig INTEGER,
  PRIMARY KEY (snapshot_id, fseg, ord)) WITHOUT ROWID;
CREATE INDEX sf_fseg ON snapshot_file (fseg, snapshot_id);  -- also xseg, wseg
CREATE INDEX f_def_fqn ON f_def (fqn);   CREATE INDEX x_use_to ON x_use (to_sym, status);
CREATE INDEX x_use_from ON x_use (from_sym);   CREATE INDEX flow_t ON flow (target);   CREATE INDEX flow_s ON flow (source);
CREATE INDEX sm_live ON snapshot_meta (repo_id, touch_seq) WHERE complete = 1;  -- partial: same syntax on both engines
```

**Postgres = the DDL above with exactly these substitutions** (unverified here): `INTEGER PRIMARY KEY` → `BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY`; other id/`h64` `INTEGER` → `BIGINT`; `BLOB` → `BYTEA`; drop `WITHOUT ROWID` (PK btree over a heap, ~28 B/row more, est.); add `ALTER TABLE blob|doc ALTER z SET STORAGE EXTERNAL` so TOAST skips recompressing zlib. New flags are `SMALLINT`, not `BOOLEAN` (existing PG flags are BOOLEAN, `postgres_backend.py:44`), so `WHERE complete = 1` is identical on both.

**Ids and hashing:**
- `blob.sha` = git's blob id, `sha1("blob <n>\0" + bytes)`: free from `git ls-tree -r` on a clean tree, same formula in Python for dirty/unpinned trees. Segment/doc `h` = sha1 of the canonical per-file rows (`json.dumps(sort_keys=True)`).
- `str.h64`/`alts.h64` = first 8 bytes of sha1 as signed int64. Intern with `INSERT OR IGNORE` (PG `ON CONFLICT (h64) DO NOTHING RETURNING id`), then `SELECT id, s WHERE h64=?`; differing text = collision → `CdpError` (p ≈ 2e-9 at 300K strings). Writers cache string → id in process. `id` stays a small autoincrement (1-3 B varints in reference columns), not `h64`.
- Segments: `INSERT OR IGNORE INTO xseg(h)` (PG `... RETURNING id`); insert rows only if this statement created the header (`changes()==1` / a returned row). A concurrent PG inserter of the same `h` blocks on the unique index until the first commits (unverified), so rows land once.

## 5. WorkspaceStore interface

- **Write:** `lookup_fsegs([(blob_sha, path, xver)])`, `put_blobs`, `put_file_facts(key, facts) -> fseg`, `put_segments(kind, {path: rows}) -> {path: seg}`, `put_doc(obj)`, and `commit_snapshot(files, docs, overlay, derived_patch, carry_from=None)`, the only call that makes a snapshot visible.
- **Read (snapshot-scoped):** `list_files`, `file_facts(path, kinds)`, `defs(fqn)`, `uses_to(fqn, statuses)`, `uses_from`, `walk(fqn, dir, depth, statuses, limit)`, `flow_edges`, `blob_lines(path)`, `search_text`, and `load_extraction()` (the dict `build_xref`/`build_dataflow` need; cost unmeasured, gated at ≤ today's 0.72 s `json.loads`, PLAN.md:13). Maintenance: `sweep_objects(dry_run)`.
- **Kept:** `read_artifact`/`write_artifact` for small docs (graph, partition, schedule, state, manifest, ledger, reports). `read_artifact` of extract/xref/dataflow/code/inventory becomes a slow compat materializer for export/selftest; commands port to typed reads. **Removed:** `begin_snapshot`'s early commit; `copy_patches_from` becomes `carry_from`.
- **FileStore** (one implicit JSON snapshot, `file_backend.py:1-5`): the ABC's default typed reads are built on `read_artifact` dicts; `commit_snapshot` writes the 10 legacy JSON files; no objects, no gc (`supports_object_store() = False`); it stays the export/test format.
- A shared SQL module holds `?` statements, rewritten to `%s` for psycopg2 (today every statement is duplicated per backend).

## 6. Transactions and isolation

**Write phase:** repo lock exclusive (as today, `lock.py:46-76`), then the `objects` lock **shared**; order is always repo → objects. Objects go in batched ~5K-row transactions: SQLite `BEGIN IMMEDIATE`; PG `READ COMMITTED`, `copy_expert` into a temp table then `INSERT ... SELECT ... ON CONFLICT DO NOTHING` (unverified). A crash here leaves only orphans for the next sweep.

**Final transaction** (same SQL on both): `DELETE FROM snapshot_file|snapshot_doc|snapshot_overlay WHERE snapshot_id=S` (makes a same-commit rescan atomic) → insert manifest (4,761 rows) and docs → carried + derived `claim_patch` rows → `prune_ephemeral` → `UPDATE snapshot_meta SET complete=1, touch_seq=MAX+1` → `COMMIT`. The row is created with `complete=0` and no `touch_seq` bump; `choose_snapshot` (`snapshot.py:168`) and `use_latest_snapshot` filter `complete=1`.

**Readers:** SQLite WAL (`sqlite_backend.py:328`): one deferred read transaction per command pins one WAL snapshot. PG: `BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY`; READ COMMITTED snapshots per statement, so a multi-query command could straddle the final commit. The shared repo lock for reads (`lock.py:24-28`) stays.

## 7. GC: mark-and-sweep under a store-wide objects lock

1. `gc` applies `retention` unchanged (`gc.py:90-97`) under the repo lock; `delete_snapshot` also deletes the snapshot's `snapshot_file|doc|overlay` rows (`sqlite_archive.py:63-73`).
2. `repo_lock(paths, scope="objects", shared=False)` (`lock.py:60-76`): SQLite `fcntl LOCK_EX` on `locks/objects.lock`; PG `pg_try_advisory_lock(_advisory_key('objects'))` (`lock.py:109-135`). Non-blocking: if writers hold it, print `sweep deferred` and stop.
3. Mark: `CREATE TEMP TABLE live_x AS SELECT DISTINCT xseg FROM snapshot_file`; likewise fseg, wseg, blob (`snapshot_file.blob_id ∪ fseg.blob_id`), doc, `patch_body` (`claim_patch ∪ claim_patches_archive`).
4. Sweep rows then headers, one transaction per kind: `DELETE FROM x_use WHERE seg NOT IN (SELECT xseg FROM live_x)`, then `DELETE FROM xseg WHERE id NOT IN (...)`; then blob, doc, patch_body. `str`/`alts` (~25 reference columns) are swept only by `compact`, then `VACUUM` (PG: plain, not FULL).

Correctness: the exclusive lock waits out every in-flight writer's shared hold, so no manifest can commit a reference to an object found dead after the mark. `verify --full` adds a dangling-reference anti-join.

## 8. Query patterns (identical SQL; placeholders aside)

| Query | SQL shape | Index |
|---|---|---|
| callers of fqn | `x_use u JOIN snapshot_file f ON f.xseg=u.seg AND f.snapshot_id=?` `WHERE u.to_sym=? AND u.status IN (local,matched)` | `x_use_to`, `sf_xseg` |
| definition / symbol | `f_def d JOIN snapshot_file f ON f.fseg=d.seg AND f.snapshot_id=? WHERE d.fqn=?` (+ overlay sig) | `f_def_fqn`, `sf_fseg` |
| file outline | `snapshot_file` PK `(S, path_id)` → `f_def WHERE seg=? ORDER BY ord` | PKs only |
| trace / `callers --depth N` | `WITH RECURSIVE w(sym,d) AS (SELECT ?,0 UNION SELECT u.from_sym, w.d+1 FROM w JOIN x_use u ON u.to_sym=w.sym JOIN snapshot_file f ON f.xseg=u.seg AND f.snapshot_id=? WHERE w.d<? AND u.status IN (...)) SELECT ... LIMIT ?` | as callers; `UNION` dedups, so cycles terminate on both engines |
| dataflow hop | `flow` by `target`/`source` joined the same way | `flow_t`, `flow_s` |
| diff two shas | `snapshot_file a FULL JOIN b ON path_id` comparing `xseg`/`fseg` (SQLite ≥ 3.39 has FULL JOIN) | PKs |

Callers measured 0.06 ms vs 0.38-1.1 s today (PLAN_STORAGE.md:148); depth-N BFS unmeasured, est. ≈ 0.06 ms × frontier.

## 9. Text search

| Engine | Mechanism | Cost |
|---|---|---|
| default, both | plain scan: inflate the snapshot's source blobs, substring/regex in Python | 0.08 s over 4.7K blobs (PLAN_STORAGE.md:151); zero extra storage |
| SQLite opt-in | `CREATE VIRTUAL TABLE blob_fts USING fts5(t, tokenize='trigram', content='', contentless_delete=1)`, `rowid = blob.id`; match → filter rowids by manifest | measured on workflow-service's 11.2 MB of text: index 25.6 MB (**2.29×**), build 0.37 s, match 0.44 ms. Unified-store would be ~185 MB (est.), larger than the rest of the store, hence opt-in |
| PG opt-in | `CREATE EXTENSION pg_trgm` + `blob_text(blob_id, t TEXT)` + `GIN (t gin_trgm_ops)` | needs the extension installed and CREATE privilege (pg_trgm is "trusted" since PG 13 — unverified); falls back to plain scan if absent, reported in `stats` |

## 10. Cost (snapshot-2-sized repo)

Store (PLAN_STORAGE.md:141): first scan ~150 MB SQLite (est.) vs 578 MB today; PG ~1.5-2× from heap tuple headers (est., unverified). **Per refresh, option A** (median 3 files changed; p90 31; ~220 for a 20-commit pull):

| Item | Rows | SQLite bytes | Basis |
|---|---|---|---|
| manifest | 4,761 | 0.35 MB (0.6 with indexes) | measured / est. |
| new blobs | 3 / 31 / 220 | 10 KB / 100 KB / 0.7 MB | 15.3 MB zlib / 4.7K files, measured mean |
| fseg rows | ~90 / ~2K / ~15K | ~10 KB / 0.2 MB / 1.5 MB | median 30 rows/file × ~106 B (PLAN_STORAGE f_use) |
| xseg + wseg rows | changed + dependents: ~10-40 files | 0.1-1 MB | fan-in p90 10; est. |
| docs + derived patch | ~10 | ~0.88 MB zlib, minus dedup | measured zlib sizes |
| **total** | ~5-25K | **~1.5-4 MB** (est.) vs ~578 MB today | |

- Write amplification: one manifest row per file plus objects for changed content only; B/C would save just the 0.35 MB manifest. Final transaction ~10 ms (manifest 7.2 ms measured).
- Read latency, SQLite measured: file lookup 2.5 µs, full listing 1.1 ms, callers 0.06 ms; PG adds ~0.2-1 ms network round trip per query (est.). A dirty scan costs the same as a refresh; its unique blobs are freed by the sweep after `prune_ephemeral`.

**Gates:** (1) one-file refresh adds ≤ 5 MB (SQLite); (2) `load_extraction()` ≤ 0.72 s; (3) callers p50 ≤ 5 ms on both engines; (4) scan of repo A during `gc` of repo B passes the dangling check; (5) kill -9 in either write phase leaves the previous snapshot readable; (6) PG suite on a real server before any PG claim drops "(unverified)".
