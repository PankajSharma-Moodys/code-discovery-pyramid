# Where To — Locking (`cdp/lock.py`)

| | |
|---|---|
| Core | `cdp/lock.py` (`repo_lock`, `_file_lock`, `_advisory_key`, `_postgres_lock`) |
| Decorator / wiring | `cdp/cli.py:575` (`_locked`), applied to every store-touching `cmd_*` — `cmd_scan` (662, exclusive), `cmd_query`/`cmd_docs` (906/946, shared), `cmd_prompts`/`cmd_collect`/`cmd_fold` (960/1073/1212, exclusive), `cmd_verify` (1239, shared), `cmd_refresh` (1267, exclusive), `cmd_run` (1497, exclusive), `cmd_reflect`/`cmd_holdout` (1652/1724, exclusive), `cmd_doctor`/`cmd_status`/`cmd_diff` (1793/1862/1937, shared), `cmd_link_scan`/`cmd_link_prompts`/`cmd_link_collect`/`cmd_link_run`/`cmd_link_refresh` (1994/2047/2095/2151/2205, exclusive), `cmd_link_query` (2252, shared), `cmd_gc`/`cmd_compact` (2281/2328, exclusive), `cmd_export` (2360, shared), `cmd_rollback`/`cmd_answer` (2394/2461, exclusive) |
| Backend resolution reused by lock | `cdp/cli.py` (`_resolve_backend`) — `lock.py` never re-derives backend config, it consumes `_resolve_backend`'s `(kind, pg)` return value |
| Repo identity for the Postgres key | `cdp/store/registry.py` (`repo_identity`) — same identity `_default_postgres_schema` uses |
| Vendored copy | `.claude/skills/cdp/cdp/lock.py` (kept byte-identical to `cdp/lock.py`; see [cross-cutting-infra](../cross-cutting-infra/)) |
| Tests | none yet — `cdp/lock.py` has no dedicated test file |
