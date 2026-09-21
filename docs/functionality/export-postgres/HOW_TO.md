# How To — Export / Postgres (`export.py`, `postgres_backend.py`)

```bash
cdp export --format json --out <dir> [--db path]
cdp export --format patches --out <dir>
cdp export --format archive --out <dir>       # requires supports_compaction()
cdp export --format anonymized --out <dir>
```

Enable Postgres backend:

```bash
pip install cdp[postgres]
```

```toml
# .cdp.toml
backend = "postgres"
[postgres]
dsn = "host=localhost port=5432 dbname=... user=..."
schema = "cdp_<repo>"
```
