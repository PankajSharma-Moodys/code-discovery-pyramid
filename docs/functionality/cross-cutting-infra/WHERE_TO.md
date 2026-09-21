# Where To — Cross-cutting infra (not a "functionality" but load-bearing everywhere)

| | |
|---|---|
| Schema | `schema/patch-1.0.0.json` |
| Distribution | `cdp/cli.py` (`DIST_MEMBERS`, `cmd_install`), `run.py` |
| Core-purity enforcement | `tests/test_core_purity.py`, `tests/test_distribution.py` |
| Utilities | `cdp/util.py` (`stable_hash`, `normalise_ws`), `cdp/schema.py` |
