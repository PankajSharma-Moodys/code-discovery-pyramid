# Where To — Cross-Repo Link (`link.py`, Phase 8)

| | |
|---|---|
| Core | `cdp/link.py` (`scan_links`, `_normalise`, `build_tasks`, `refresh_links`, `query_service`, `dispatch_link_task`, `link_task_shape_key`) |
| Store | `cdp/store/sqlite_backend.py` (`write_link_edges`, `read_link_edges`, `link_task`/`link_run` tables) |
| Tests | `tests/test_link.py`, `tests/test_store_sqlite.py::TestLinkEdgePersistence` |
