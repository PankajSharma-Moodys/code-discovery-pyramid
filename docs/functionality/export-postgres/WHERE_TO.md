# Where To — Export / Postgres (`export.py`, `postgres_backend.py`)

| | |
|---|---|
| Core | `cdp/export.py` (`_TEXT_FIELDS`, `_NODE_FIELDS`, format dispatch), `cdp/store/postgres_backend.py` (`PostgresStore`) |
| Tests | `tests/test_export.py`, `tests/test_store_conformance.py::PostgresStoreConformance` |
| Packaging | `pyproject.toml` (`[project.optional-dependencies] postgres`) |
