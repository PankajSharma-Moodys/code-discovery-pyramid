# How To — Golden / Regression Testing (`golden.py`, `scripts/fixture_gate.py`)

```bash
python3 scripts/fixture_gate.py bless          # bless fixture golden baseline
cdp selftest --golden $TARGET_REPO --bless     # bless target golden baseline
make check TARGET_REPO=/path/to/target         # full gate: determinism, fold, golden
cdp selftest                                    # run bundled test suite
```

Always inspect a golden diff before blessing — never blind-bless.
