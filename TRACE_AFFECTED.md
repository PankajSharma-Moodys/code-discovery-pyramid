# Trace: features affected by normalized storage (PLAN_STORAGE.md §2)

Scope: what replacing `snapshot_artifact` JSON payloads with `blob`/`fseg`/`xseg`/`wseg`/`doc` + `snapshot_file` touches.
No migration (fresh rescans). Method: grep, then Read of the cited ranges. `cdp query symbol cdp.store.WorkspaceStore#read_artifact`
finds only 11 of the 51 call sites (untyped receivers do not resolve), so grep is the source of truth for the counts.
Counts: 51 direct `read/write/has_artifact` calls in `cdp/`; 30 `conn.read_artifact` in `web/api/app.py`; 226 `Store.<artifact>`
property reads (`cdp/query/store.py:59-67`, cached in `_cache`); 53 report/patch/snapshot calls outside `store/`.

## 1. Every artifact writer
| caller | feature | artifact(s) | notes |
|---|---|---|---|
| pipeline.py:93-100 | scan | inventory, extract, graph, partition, schedule, xref, dataflow, code | full objects, after `begin_snapshot` (:82) |
| pipeline.py:123 | scan | manifest | written last; this is the commit marker the web layer reads (store_reader.py:145-150) |
| refresh.py:294-306, 317 | refresh | same 8 + manifest | `manifest = dict(store.manifest, head=..)` from the **old** snapshot's cache (:319) |
| session.py:212 (fold_and_write) | scan/collect/answer/fold/compact | state | whole fold output |
| refresh.py:316; commands/maintenance/rollback.py:93,115 | refresh, rollback | state | |
| rollback.py:213,227; refresh.py:198 | rollback, carry | `rollback` ledger (not in `ARTIFACTS`, store/__init__.py:31-34) | read-modify-write append |
| export.py:37 | export --format json | all `ARTIFACTS` -> FileStore | ledger and the reports rereview/reflections/holdout are not exported |

## 2. Artifact readers, by feature (fields actually used)
| feature | caller (file:line) | artifact.fields used | impact | minimal store method |
|---|---|---|---|---|
| scan | pipeline.py:31 (`load_patches` on other snapshots); refresh.py:177-179 carry | patches, ledger | none | - |
| refresh | refresh.py:229-283 | manifest.excludes/budgets, inventory.head, **whole extract** (incremental_extract :89-102), partition (changed_scopes :275), state.unknowns len | logic | `snapshot_file` diff by `blob_sha` replaces carry-forward; `file_facts(path)` per carried file |
| refresh (dirty/ephemeral) | pipeline.py:82, refresh.py:231-233; sqlite_archive.py:75+ prune_ephemeral | snapshot rows | adapter | prune drops manifest rows only; leave shared objects to the gc sweep |
| fold / verify | state.py:315-345, session.py:206-213 | xref.symbols, partition.scopes, extract.defines + io_edges (fold_hash state.py:238-241) | adapter | `symbols()`, `defines()`, `io_edges()` in a stable order |
| query stats/coverage | query/stats.py:14-61 | inventory, state, extract.defines (count), partition.scopes, xref.symbols/routes/resolution, graph.divergence | adapter | counts by SQL; `xref_summary()` |
| query symbol | query/lookup.py:19-325 | xref.symbols (scan over every key :39), xref.uses/used_by (:265,:599), extract.uses/defines (call index :203-227), code.files[rel] (:289) | logic | `symbol(fqn)`, `symbols(prefix/suffix)`, `uses_from(file, sig)`, `edges_to(fqn)`, `blob_text(path)` |
| query file | lookup.py:331-388 | inventory.files, extract.files[path], extract.defines, state.claims | adapter | `file_facts(path)`, `file_row(path)` |
| query module | lookup.py:390-439 | inventory.modules, graph, state.claims, manifest.module_level, partition.scopes | adapter | `graph_doc()`, `module(name)` |
| query routes | lookup.py:478-533; common.py:165 | xref.routes, xref.unresolved_routes, symbols for annotations | adapter | `routes()` |
| query table | lookup.py:572-840 | extract (entity index :576), xref.symbols, xref.used_by/uses (:599,:687) | logic | `edges_to(fqn)`, `iter_uses(kind)` |
| query config | lookup.py:848-902 | extract.defines, xref.constants, xref.config_wrapped | adapter | `constants()`, `config_reads()` |
| query paths | query/trace.py:24 | dataflow.paths | adapter | `wseg` paths |
| query trace | trace.py:138-379; trace_entry.py:48-136 | dataflow.edges/sources, xref.used_by/symbols/routes, extract.files, state.unknowns | logic | `flow_edges()`, `edges_to(fqn)`, `symbol(fqn)` |
| query search | query/search.py:22-200 | state.claims/unknowns, xref.symbols, inventory.files, code.files (substring scan of every file :140-172) | logic | `iter_blobs(role=source)` (PLAN_STORAGE §6: 0.08 s over zlib) |
| query claims/unknowns/conflicts | search.py:212-290 | state only | none | `doc("state")` |
| query `--as-of` | session.py:250-260 | patches, xref, partition, extract; **overwrites `store._cache["state"]`** | adapter | keep an override hook on the view |
| query suggestions | query/suggest.py:22-35 | xref.symbols keys, routes, inventory.files/modules, extract.defines | adapter | `symbols(prefix)`, `paths()` |
| _as_of on every answer | query/common.py:16-45 | inventory.repo_name/head, state.provenance | adapter | manifest row |
| docs | session.py:216-226 -> docs.py:30-53 | all 8 whole | adapter | compat `read_artifact` (render-only, export) |
| status (CLI, MCP) | status.py:21-79; mcp_server/tools.py:162-205 | schedule, state.claims, inventory.head, manifest.run_id, partition.scopes.scope_hash | adapter | manifest row + `doc("state")` |
| diff | commands/core/diff.py:39-46,81-95; diffs.py:34-140 | graph.modules/declared/observed/divergence, xref.symbols.sites, xref.routes, state.claims, inventory.files bytes/loc | logic | `manifest_diff(a,b)` over `snapshot_file.blob_sha` (diffs.py:38 says "the index keeps no content hash"), `symbols()` per side |
| prompts | commands/leaf/prompts.py:49-120; prompts.py | schedule, partition.scopes, state.claims, inventory.files/modules, extract.files/defines/imports, xref.uses | adapter | `scope_facts(files)`, `uses_from(files)` |
| collect / answer | intake.py:60-300 | manifest, partition.scopes, inventory.head, extract (gates index :142), xref (fold) | adapter | `defines()`, `io_edges()` |
| run | supervisor.py:239-585 | same as prompts + schedule (:488) | adapter | as prompts |
| fold / verify / rollback | commands/leaf/fold.py:27-46; verify.py:35-42; maintenance/rollback.py:84-115 | xref, partition, extract, patches, ledger | adapter | as fold |
| reflect / lessons | commands/learning/reflect.py:45; lessons.py:50 | reflect: manifest.run_id; lessons: trajectory store only | none | manifest row |
| holdout | holdout.py:34-43 | partition, state.claims, extract, manifest, inventory, xref, schedule | adapter | as prompts |
| rereview | rereview.py:47-99 | partition, state.claims, inventory.head | adapter | - |
| link scan/refresh | link.py:258-299, 815-825; commands/link/scan.py:58-60, refresh.py:49-50 | inventory.repo/repo_name, dataflow.edges (http channels only, link.py:85,110), manifest.head; `use_snapshot` per repo | adapter | `flow_edges(channel in http_*)` per snapshot |
| link prompts/collect/run/query | commands/link/*.py; linkview.py:74-84 | `link_edge` table, not artifacts | none | - |
| gc | commands/maintenance/gc.py:89-110 | state.claims anchor_verified_at/claim_reviewed_at; `delete_snapshot` | logic | `delete_snapshot` + reachability sweep of fseg/xseg/wseg/doc/blob |
| compact | commands/maintenance/compact.py:60-63; sqlite_archive.py:137-155 | xref, partition, extract via raw SQL `_artifact()`; ledger | adapter | store-internal `_artifact` must go through the new reader |
| export | export.py:30-50, 142-150 | all artifacts; state claims/unknowns/conflicts | adapter | compat `read_artifact` |
| doctor | commands/setup/doctor.py:52-74 | schedule, manifest, partition, xref, inventory, extract, state.claims | adapter | as prompts |
| selftest / golden | selftest.py:48-60, 262-276; golden.py:77-79 | **every artifact whole, canonical JSON** | adapter (byte-exact) | compat `read_artifact` must reproduce today's dict exactly |
| hook (PreToolUse) | hook.py:286-310 | inventory.head, files[].path/role, loaded whole on every tool call; opens `SqliteStore` directly | adapter (perf gain) | `head()`, `file_row(path)` |
| install / githook | install.py, githooks.py | no artifact access found | none | - |
| MCP tools | mcp_server/tools.py:40-205 | through `query.dispatch`, `pipeline.scan`, `refresh_repo`, status fields above | follows query/scan/status | - |
| agent_adapter | agent_adapter/__init__.py:31 wraps mcp_server.tools | none of its own | none | - |
| litellm_adapter | litellm_adapter/__init__.py:140-148 runs `cdp scan`/`doctor` as subprocesses | none of its own | none | - |

## 3. Web UI (web/api) reads raw SQL, sqlite only
| caller | endpoint | reads | impact |
|---|---|---|---|
| store_reader.py:109-118, 145-160 | snapshot pick for every endpoint | `JOIN snapshot_artifact a.name='manifest'` used as the commit marker | logic: needs a manifest row or `complete` flag |
| store_reader.py:166-197 | all | `SELECT payload FROM snapshot_artifact`; process cache keyed (db, snapshot_id, name), skips state/manifest (:45) | logic: new reader, or the cache keyed by object hash |
| app.py:182-187 | /api/status | manifest, inventory, schedule.waves, partition, state.coverage/nodes | adapter |
| app.py:487, 522-620 | /api/graph L0/L1 | inventory.files.role, xref.symbols, dataflow.edges, partition.scopes, extract.imports | adapter |
| app.py:640, 820 | grouped / dataflow graph | graph.levels/cycles/divergence, dataflow.edges, xref.symbols | adapter |
| app.py:998-1001, 1149-1153 | /api/confidence, /api/node | xref, partition, dataflow, graph, state (5 whole artifacts for one node) | logic: `symbol(fqn)`, `edges_to(fqn)` |
| app.py:1091, 1412-1414, 1520-1522, 1671 | repos, trajectory, events, jobs | inventory.head/repo, graph, xref, state.claims, manifest.run_id, partition | adapter |
| query_store.py:41-60 | /api/query, /api/search, /api/trace | `ReadOnlyWorkspaceStore` implements only `read/has_artifact` | logic: any new query method must exist here too |

## 4. Backends
- Base defaults (store/__init__.py:200-300): compaction off and `compact` raises; `dump_archive` raises; link edges off (`write_link_edges`
  raises, `read_link_edges` returns []); churn cache off; `list_snapshots` [], `restore_archived` 0; `use_snapshot` raises (:66-80).
- Postgres overrides snapshots, `use_snapshot`, run tracking, tasks/leases, `list_snapshots`, `delete_snapshot`, `copy_patches_from`,
  `model_patch_hashes`, `checkout_heads`. It **does not** override compaction, archive, link edges, churn cache, or link resolution, so
  `cdp compact`, `export --format archive`, `link scan` saving edges, and the churn cache fall back to the refusal/empty defaults.
- Postgres-specific behaviour to keep: `snapshot_artifact.payload JSONB` (postgres_backend.py:50-56); `claim_patch` expression index
  `((payload->>'node'))` (:76); `->>'status'`/`->>'author_kind'` filters (:280). The patch table is out of scope, but its JSONB
  must stay. JSONB normalizes object key order (shortest key first); sqlite and FileStore write `sort_keys=True` (sqlite_backend.py:953,
  util.py:241). Reassembly must emit sorted keys on both backends.
- Not wired for Postgres at all: web (store_reader uses `sqlite3`), hook (hook.py:286 `SqliteStore`), linkview (linkview.py:28-36).
- FileStore (file_backend.py:29-50): one JSON file per artifact, an export format, and the target of `export_json`. It keeps whole
  artifacts and does not normalize, so the compat `read_artifact`/`write_artifact` must stay on the ABC.
- Raw SQL against `snapshot_artifact` inside the store: sqlite_backend.py:921,943 (`_describe_repo` parses inventory.repo), 951, 961;
  sqlite_archive.py:25 (migration parses every partition), 70 (delete list), 137, 147; postgres_backend.py:230, 362, 382, 391.

## 5. Tests
- 28 files call the artifact API (most: test_store_conformance 22, test_store_sqlite 18, web test_graph_endpoint 13, test_supervisor 12,
  test_export 11). 39 build `query.Store`; 18 index `xref[...]`/`extraction[...]` directly.
- **Break on schema** (raw SQL on `snapshot_artifact`): test_store_sqlite.py:344,354; test_state_core.py:377 (INSERT partition);
  test_refresh_snapshot.py:38; web/tests/test_search_endpoint.py:40-44; web/tests/test_graph_endpoint.py:39-43; web/tests/test_store_reader.py.
- **Break on decomposition** if `write_artifact` stops accepting arbitrary shapes: toy payloads such as `{"head":"abc"}`, `{"i": i}`, and an
  arbitrary graph (test_store_conformance.py:40-229; test_store_sqlite.py:69-165; test_fix_stores.py:67 `state={"a":1}`).
- **Break on byte drift**: test_golden.py and test_determinism.py against tests/golden/*/scan/{extract,dataflow,state,graph,partition,
  inventory,patches}.json (canonical JSON via golden.py:77-79). Also test_pipeline, test_minirepo, test_export, test_doctor.
- **Break if query moves to methods**: duck-typed fake stores with dict attributes plus `_cache` (test_overload_sigs.py:45,
  test_quality_fixes.py:30); `store._load("schedule")` (test_digest.py:39,102; test_supervisor.py:106,268; test_prompts_annotations.py:52).
- Postgres paths: test_store_conformance, test_export, test_rollback, test_hook, test_store_registry (gated on a DSN).

## 6. Hidden coupling hazards
1. **fold_hash covers whole artifacts in list order**: `stable_hash(xref.symbols)`, scope nodes, `extract.defines` and
   `io_edges` (state.py:236-242). Reassembled lists in a different order flip `cdp verify`/`fold --check` to "fold_hash mismatch"
   (state.py:336) and make compaction's lossless check refuse (sqlite_archive.py:150-155).
2. **Per-file facts are not purely per-file**: `rules.apply` rewrites `files[rel].signals`/`io_edges` and `totals` from all rule
   edges (rules.py:656, 685-703). `declared_deps`/`module_notes` are per-module with no file attribution (refresh.py:75-80, 95-102).
   A content-addressed `fseg` must hold only raw extractor output, with rule and module aggregates in a separate layer.
3. **Mutation through the cache**: incremental_extract hands out the prior extraction's `files[p]` dicts by reference (refresh.py:94),
   then `rules.apply` mutates them in place (rules.py:697-698). If decoded segments are shared or cached, this corrupts them.
   scan also mutates before writing (pipeline.py:58 rules, :68 scope hashes).
4. **The cache outlives a snapshot switch**: `query.Store._cache` (query/store.py:55-57) is keyed by name only. refresh reads
   manifest/state before `begin_snapshot` and relies on that (refresh.py:276-281, :319). diff's sha mode reads each side eagerly
   between `use_snapshot` calls (diff.py:81-89). Lazy per-row reads bound to "current selection" would read the wrong snapshot.
   `_memo` puts derived indexes into the same `_cache` (lookup.py:193-200), and `apply_as_of` overwrites `_cache["state"]` (session.py:259).
5. **Manifest as commit marker**: the web layer treats "manifest row exists" as "snapshot complete" (store_reader.py:145-150). The web
   artifact cache assumes a snapshot never changes after that (:36-45), but a rescan of the same commit reuses the snapshot id
   (store/__init__.py:46-54). Content-addressed keys would remove that staleness.
6. **Key order**: every stored artifact reads back key-sorted today (sqlite json.dumps sort_keys, write_json). Output order in query,
   docs and golden follows `dict.items()` of that sorted form (e.g. code.files `dict(sorted(..))`, codeindex.py:37).
7. **Byte-exact golden/determinism**: selftest.py:53,267-276 canonicalizes every artifact plus `rules_mod.legacy_view(extract)`.
   The compat `read_artifact` must rebuild today's dicts exactly, including `totals`, `head` and the empty defaults.
8. **Shared-object lifetime**: `delete_snapshot` and `prune_ephemeral` (inside `begin_snapshot`'s transaction) delete by
   `snapshot_id` (sqlite_archive.py:63-73). Shared rows need a reachability sweep, not cascade delete, and must not slow `begin_snapshot`.
9. **Per-snapshot names outside `ARTIFACTS`**: the `rollback` ledger (rollback.py:38), and the reports rereview/reflections/holdout.
   web `read_artifact` rejects names not in `ARTIFACTS` (store_reader.py:167).

## Minimal store API (beyond a compat `read_artifact`)
Required: `manifest()` / `head()`; `file_row(path)`, `paths(role)`; `manifest_diff(a, b)`; `file_facts(path)` / `scope_facts(files)`;
`symbol(fqn)`, `symbols(prefix|suffix)`; `edges_to(fqn)`, `uses_from(file, sig)`, `iter_uses(kind)`; `defines()`, `io_edges()` (stable order);
`flow_edges(channel)`, `flow_paths()`; `routes()`, `constants()`, `config_reads()`; `blob_text(path)`, `iter_blobs(role)`;
`doc(name)` for state/graph/partition/schedule; `sweep()` after `delete_snapshot`. Each must also exist on
`ReadOnlyWorkspaceStore` (web) and fall back to whole-artifact reads on FileStore/Postgres until those are ported.
