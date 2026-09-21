# Where To — Scheduling / CLI Cross-Cutting Concerns

| | |
|---|---|
| Core | `cdp/cli.py` (`_paths`, `_open_store`, `_check_repo_matches_manifest`, `cmd_*` dispatch), `cdp/helpdoc.py` (`describe`), `cdp/hook.py` (`decide`, `strict_decide`, `_gate`), `cdp/schedule.py`, `cdp/partition.py` |
| Tests | `tests/test_pipeline.py`, `tests/test_help.py`, `tests/test_hook.py`, `tests/test_repo_guard.py` |
| Docs | `SKILL.md`, `AGENTS.md`, `ARCHITECTURE.md`, `CDP_CLI_SCOPE.md` |
