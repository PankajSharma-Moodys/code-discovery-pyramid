# Where To — Backend Selection (`store/`, `.cdp.toml`)

| | |
|---|---|
| Core | `cdp/store/__init__.py` (`WorkspaceStore` interface, capability flags `supports_*`), `cdp/store/file_backend.py` (`FileStore`), `cdp/store/sqlite_backend.py` (`SqliteStore`), `cdp/store/postgres_backend.py`, `cdp/store/registry.py` (`team_backend`, `team_excludes`, `resolve_store`, `repo_identity`), `cdp/githooks.py` |
| Tests | `tests/test_store_sqlite.py`, `tests/test_store_conformance.py`, `tests/test_registry.py`, `tests/test_githooks.py` |
| Config | `.cdp.toml` |
