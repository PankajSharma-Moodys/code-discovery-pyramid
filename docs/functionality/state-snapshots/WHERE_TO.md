# Where To — State & Snapshots (`state.py`, `snapshot.py`)

| | |
|---|---|
| Core | `cdp/state.py` (`fold`, `check_fold`, `STATUS_RANK`, `_dedupe_unknowns`), `cdp/snapshot.py` (`resolve_snapshot`, `snapshots_to_keep`), `cdp/freshness.py` (`file_churned_between`, two-dates), `cdp/rollback.py`, `cdp/refresh.py` (`scope_hash`, `annotate_scope_hashes`, `changed_scopes`) |
| Tests | `tests/test_pipeline.py`, `tests/test_snapshot.py`, `tests/test_rollback.py`, `tests/test_refresh.py`, `tests/test_scope_hash.py` |
