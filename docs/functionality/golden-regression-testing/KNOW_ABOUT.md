# Know About — Golden / Regression Testing (`golden.py`, `scripts/fixture_gate.py`)

- Golden baselines exist for both the fixture (`tests/fixtures/minirepo`) and
  a real, pinned `$TARGET_REPO` commit — `make check TARGET_REPO=...` is the
  full-scale gate. A blessed baseline changing shape (new field, new report
  key) requires deliberate re-blessing and diff inspection before blessing,
  never blind re-bless.
- Golden capture must read data back through the store API
  (`SqliteStore`/`FileStore`), never walk raw on-disk bytes — a SQLite file's
  page layout is not stable across two logically-identical writes, so
  byte-level capture/compare of `index.db` produces permanent false
  positives. `check_determinism` therefore excludes `index.db` from its raw
  byte comparison and instead re-reads it through the store API.
