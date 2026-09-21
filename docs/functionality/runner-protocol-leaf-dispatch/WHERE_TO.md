# Where To — Runner Protocol & Leaf Dispatch (`runner.py`, `supervisor.py`, `scripts/claude_leaf_runner.sh`)

| | |
|---|---|
| Core | `cdp/runner.py` (`RunResult`, `SubprocessRunner`, `FileRunner`), `cdp/supervisor.py` (`dispatch_scope`, `run_wave`, `_LeaseHeartbeat`, `mark_folded`) |
| Store | `cdp/store/sqlite_backend.py` (`begin_run`, `upsert_task`, `acquire_lease`, `heartbeat_lease`, `release_lease`, `reclaim_expired`, `copy_folded_tasks`) |
| Agent contract | `agents/cdp-leaf.md` (canonical source), `.claude/agents/cdp-leaf.md` (vendored copy) |
| Tests | `tests/test_runner.py`, `tests/test_supervisor.py` |
