# CDP storage: JSON blobs -> manifests over shared objects

Budget: 170 lines. Deepens and corrects PLAN.md M1. Design only. Probes were read-only, run on `~/.cdp/index.db` (2026-10-17) and then deleted.

## 1. Current model

A **snapshot** is a `snapshot_meta` row keyed by `(repo_id, commit_sha)`; a dirty tree is `sha+dirty:<treehash>`, ephemeral (`sqlite_backend.py:57-64`, `snapshot.py:92-99`).
Each snapshot owns 10 JSON artifacts (`snapshot_artifact`, `:66-71`; `store/__init__.py:31-34`), its reports, and its own copy of the claim log: `copy_patches_from` copies patch rows verbatim (`:888-916`, called at `refresh.py:196`).
A re-scan of the same commit reuses the row and overwrites artifacts one commit each (`:390-413`, `:949-955`).
So history today is whole copies: snapshot 2 alone is 575 MB of extract/xref/dataflow/code.

| Feature | Reads today | Cite |
|---|---|---|
| scan | writes all 10 artifacts, derived patch, `state`, reports | `pipeline.py:93-100,123` |
| refresh | base `extract`/`partition`; rewrites every artifact; copies log; per-*module* re-extract | `refresh.py:69-86,262,294-317` |
| query lookup/search/stats/trace | inventory, extract, graph, partition, state, xref, dataflow, manifest, `code` | `query/store.py:58-66`, `lookup.py:289,633` |
| `--as-of` | **current** snapshot's patch log vs **current** xref/partition/extract; no old artifacts | `session.py:236-262` |
| diff `--old-sha/--new-sha` | graph, xref, state of both snapshots | `commands/core/diff.py:81-88` |
| rollback | `rollback` ledger artifact, then refold | `rollback.py:193-227`, `maintenance/rollback.py:93,115` |
| verify, fold `--check` | state, patches (+archive if `--full`), xref, partition, extract; anchors read from **disk** | `state.py:315-345`, `verify.py:39-47,114` |
| export | json: every artifact via FileStore; patches; archive; anonymized from `state` | `export.py:31-37,144` |
| gc | HEAD `state` claims (cited shas), `checkout_heads`, `model_patch_hashes`; deletes snapshot rows | `gc.py:90-97`, `sqlite_archive.py:63-73,103-127`, `snapshot.py:257` |
| compact | `claim_patch`; xref/partition/extract for lossless check; `VACUUM` | `sqlite_archive.py:150-236` |
| link | inventory, dataflow, manifest of each repo's latest snapshot | `link.py:266-299` |
| selftest determinism | canonical `read_artifact` of every artifact | `selftest.py:53,267` |

**Correction to PLAN.md:** its stress case "`as_of` on an old snapshot needs `blob.text`" is false; `as_of` never reads old structure (`session.py:237-248`).

## 2. Target schema: git-like objects plus per-snapshot manifests

**Shared objects** (content-addressed, insert-only via `INSERT OR IGNORE`, never mutated):

| Table | Key | Holds |
|---|---|---|
| `blob` | `sha` (sha1 of bytes) | `size`, `z` (zlib text) for every file extraction parsed |
| `str`, `alts` | `id`; lookup index on `h64` (8-byte hash), not on text | interned paths/fqns/kinds/modules; interned name-id lists |
| `fseg` + `f_def/f_use/f_imp/f_io/f_note` | `(blob_sha, path_id, xver)` -> `seg_id`; rows `seg_id, line, span, ...` | one file's **raw** extractor output |
| `xseg` + `x_use` | `seg_id` = hash of rows | one file's resolved out-edges |
| `wseg` + `flow` | `seg_id` = hash of rows | one file's dataflow edges |
| `doc` | `sha` | zlib JSON of non-row artifacts: graph, partition, schedule, state, manifest, ledger, xref aggregates, dataflow paths |

- `fseg` carries the path because extractors read it for language, package and test-path rules (`lang/__init__.py:104-108`, `lang/go.py:47`, `lang/web.py:55`). No extractor reads `ctx.module`; module is stamped afterwards (`refresh.py:113-131`), so it stays out of the key.
- `span` is a signed width; anchor text is recomputed from blob lines as `build_anchor` does (`anchor.py:199-234`).

**Per-snapshot rows** (these are the snapshot):

| Table | Holds |
|---|---|
| `snapshot_meta` | existing columns + `layout` (1 = JSON, 2 = tables) + `complete` |
| `snapshot_file` | `(snapshot_id, path_id)` -> `blob_sha, module, role, language, bytes, binary, fseg, xseg, wseg` |
| `snapshot_doc` | `(snapshot_id, name)` -> `doc.sha` |
| `snapshot_overlay` | rows rewritten by cross-file passes: `sigs.partial_overloads` sig/from_sig (`sigs.py:130-152`), `rule_edges` (`pipeline.py:56`) |
| `claim_patch` | unchanged, except `payload` moves to `patch_body(content_hash)`, so carried logs stop duplicating bodies |

**History = manifests over shared objects** (like git trees):
- A new snapshot writes about one `snapshot_file` row per file and reuses every unchanged `fseg`/`xseg`/`wseg`/`doc`.
- Old snapshots keep pointing at their own segments, including ones from an older extractor, so their facts stay frozen as scanned, as today.

| Shared, keyed by input | Per snapshot, content-addressed (reused when identical) | Per snapshot only |
|---|---|---|
| blob, fseg rows | xseg (resolution is global), wseg, docs | `snapshot_file`, overlay, patch rows |

- An `xseg` is keyed by the hash of its output, never its inputs, so reuse cannot serve a stale edge.
- Legacy `code` becomes a view: non-generated `role='source'` files (`_generated` is pure over the first 3 lines, `codeindex.py:23-37`).
- `symbols`/`used_by` are derived from `f_def`/`x_use` through the manifest; byte-identity is unverified until the gate.

## 3. Lifecycle and maintenance

**Write path (scan/refresh).** Extract and resolve in memory as today; insert objects in batched transactions; then in **one** final transaction write `snapshot_file`, `snapshot_doc`, overlay and derived patch, set `complete=1`, bump `touch_seq`.
Readers see only `complete=1`. This fixes today's crash hazard: a crash between per-artifact commits leaves a reused snapshot with mixed old/new artifacts (`sqlite_backend.py:949-955`).

**GC is mark-and-sweep, not refcounts.**
- Refcounts would need updating on every manifest insert/delete, plus drift repair.
- A sweep is a few anti-joins, e.g. `DELETE FROM fseg WHERE seg_id NOT IN (SELECT fseg FROM snapshot_file)`; likewise `xseg`, `wseg`, `doc`, `blob`, `patch_body`, then unreferenced `str`/`alts` ids.
- The retention rule is unchanged (`snapshot.py:257-293`): `delete_snapshot` drops manifest rows (`sqlite_archive.py:63-73`), then `gc` sweeps.
- `compact` keeps archiving patches (`:163-236`), then sweeps and runs `VACUUM`.

**Concurrency.** Locks are per repo, under `CDP_HOME/locks/` (`lock.py:14-17,60-75`), but objects are shared across repos.
- Race: repo A's scan finds an old unreferenced object already present (`INSERT OR IGNORE` no-op); repo B's `gc` sweeps it; A commits a manifest pointing at nothing.
- Fix: a store-wide `objects` lock via the existing `scope=` parameter (`lock.py:60-63`). Writers take it shared for the write phase; the sweep takes it exclusive.
- WAL is already on (`sqlite_backend.py:328,373`), so readers never block. `verify --full` adds a dangling-reference check.

**Extractor upgrade.** `xver` = per-language `EXTRACTOR_VERSION` + `CDP_VERSION`. A scan after an upgrade misses every `fseg` and re-extracts. Old snapshots keep old segments until retention drops them; the sweep then frees them. Nothing is rewritten in place.

**Migration (`cdp migrate`, schema V12).**
1. Add the tables.
2. Per snapshot, in its own transaction: convert artifacts to tables, regenerate each, and **byte-compare** with the stored `payload`. `write_artifact` stores `json.dumps(sort_keys=True)` (`:949-955`), so string equality is exact.
3. On equality set `layout=2`; keep JSON rows until `--finalize`. `--revert` writes JSON back via the export function, so the move is lossless both ways.
4. During dual-read, `read_artifact` dispatches on `layout`.

- Blob text comes from the `code` artifact (source files) or `git cat-file` (clean commits). Dirty snapshots 2 and 3 cannot recover text changed since the scan; those `fseg`s keep anchor text in a nullable `atext` column (no blob).
- An older `cdp` would see migrated snapshots as missing artifacts until `--finalize`; a `min_reader` row it checks prevents that.
- Postgres keeps layout 1 behind the same `read_artifact` interface (normalizing it is out of scope).

## 4. Feature compatibility and proof

Universal proof: on a layout-2 snapshot, `read_artifact(name)` materializes the legacy dict, and `json.dumps(sort_keys=True)` of it must equal the layout-1 payload, for 10 artifacts × 3 repos. That also proves `export json`, `selftest --determinism` and the golden tests.

| Feature | On the new schema | Extra proof |
|---|---|---|
| scan | writes objects + manifest; full xref/dataflow compute unchanged | scan to JSON and to tables, byte-compare |
| refresh | **per-file** re-extract: per-file `f_note` removes the module-granularity reason (`refresh.py:75-80`); xref/dataflow still full (`refresh.py:3-6`) | refresh equals a fresh scan (existing acceptance test) |
| query (all kinds) | SQL over `snapshot_file` ⋈ segments; compat dicts until each kind is ported | golden query outputs identical |
| `--as-of` | unchanged: patch log + current structure | existing tests |
| diff (sha) | diff manifests first; only files whose `xseg` changed feed the typed delta | diff JSON identical to layout 1 |
| rollback | ledger is a `doc`; refold unchanged | `fold --check` clean after rollback |
| verify, fold `--check` | same inputs, materialized; anchors still from disk by default | `fold_hash` equal under both layouts |
| export patches/archive/anonymized | `claim_patch` + `patch_body`, archive, `state` doc | byte-compare export trees |
| gc `--pin`/`--dry-run` | same rule and output, plus a `freed N objects` line (dry-run counts only) | report unchanged apart from that line |
| compact | as today, plus sweep | `verify --full` |
| link | inventory/dataflow/manifest compat dicts per repo | link report identical |

## 5. Anchors across snapshots

| Fact kind | Cites | Survives edits? |
|---|---|---|
| Deterministic (`f_*`, `x_use`, `flow`) | `(blob_sha, line, span)`, exact | Need not: a changed blob gets a new segment. Removes bug D (`anchor.py:32,188-196`) once the gate allows divergence from legacy. |
| Derived patch 0000 | text anchors materialized from `(blob, line, span)` | regenerated each scan (`pipeline.py:103-110`) |
| Model/human claims | text anchors, unchanged | yes, via `verify_anchor` (`anchor.py:257-284`) |

Carry-forward stays: copy the log, fold re-verifies against the tree with the git-drift rename map (`verify.py:100-114`). Two additions:
- **Skip unchanged files:** if an anchor's path has the same `blob_sha` in source and target manifests, reuse the previous verify result.
- **Opt-in history verify without a checkout:** `verify_anchor` can read lines from the blob of `snapshot_file(S, path)`; the default stays disk.

`anchor_verified_at`/`claim_reviewed_at` still pin whole snapshots in gc (`gc.py:90-92`); a kept snapshot now costs only its manifest plus unique segments.

## 6. Cost

**Size, measured.** The probe re-encoded each snapshot's extract, xref.uses, xref.symbols and dataflow.edges into the tables above, plus zlib text of every parsed file (read from disk), interned strings and 14 indexes, then read the file size.

| Snapshot | Today: extract+xref+dataflow+code | Probe DB | Parsed text raw / zlib |
|---|---|---|---|
| 1 workflow-service | 180 MB | 35.1 MB | 16.4 / ~3 MB |
| 2 unified-store | 575 MB | 144.7 MB | 80.8 / 15.3 MB |
| 3 code_scanner | 46 MB | 14.2 MB | 12.2 / ~2 MB |

- Snapshot 2 breakdown: `str` + text index 42 MB (289K strings, avg 58 B); `f_use` + indexes 29 MB; `x_use` 27 MB (23 MB of it un-interned `from_symbol`/`kind`/`to_modules`); `blob` 15 MB; `alts` + index 9 MB. ~9 MB of JSON (xref aggregates, dataflow paths) sits outside the probe.
- Only 5 of 5.7K files share content across the 3 repos, so there is no cross-repo saving.

**Size, estimated.**
- Store ≈ 194 MB probe + ~10 MB docs/patches. Interning `x_use` extras (-~20 MB) and an `h64` index on `str` (-~17 MB) bring it to **~150 MB vs 811 MB today**.
- **Second snapshot of an unchanged snapshot-2-sized repo, one file edited:** manifest 0.2 MB (measured `snapshot_file` + index) + 1 blob + 1 `fseg` + changed `xseg`s + new `state` doc (2 MB JSON, zlib ~0.2 MB) = **~1-3 MB vs ~580 MB today**. How many `xseg`s change after a one-file edit is unmeasured.

**Latency and RSS, measured on the probe DB.**

| Operation | New | Today |
|---|---|---|
| Callers of an fqn (237 rows, join via manifest) | 0.06 ms | 0.38-1.1 s |
| Peak RSS | 36 MB | 1.8 GB |
| Read + inflate one blob | 0.03 ms | n/a |
| Substring scan over all 4.7K zlib blobs | 0.08 s | n/a |

The 0.08 s scan means FTS5 can wait (PLAN.md open question 1).

**Refresh, estimated.** Today a refresh re-serializes ~575 MB (snapshot 2); new writes only changed objects plus the manifest, and extraction drops from per-module to per-file. xref/dataflow compute is unchanged and still needs the full extraction dict in memory; building it from tables is unmeasured and must be no slower than today's 0.72 s `json.loads`.

## Gates

1. `cdp migrate` byte-equality for 3 repos × 10 artifacts; `fold --check` and `verify --full` clean.
2. Store ≤ 200 MB; a one-file refresh adds ≤ 5 MB.
3. Callers p50 ≤ 5 ms with RSS ≤ 150 MB.
4. A concurrent scan of repo A during gc of repo B passes the dangling-reference check.
