# Know About — Export / Postgres (`export.py`, `postgres_backend.py`)

- Postgres support is an **optional extra** (`psycopg2-binary`), imported
  lazily inside `PostgresStore.__init__` — the base install must remain
  zero-dependency; `import cdp.store` must succeed with no `psycopg2` on the
  path.
- Every read-only Postgres method must explicitly commit/rollback — `psycopg2`
  defaults to `autocommit=False`, so a bare `SELECT` with no following commit
  leaves a transaction open (`idle in transaction`), which silently blocks
  DDL against the whole schema. This is the actual failure mode a shared
  multi-writer store must avoid.
- First-time schema creation across concurrent connections needs an explicit
  `pg_advisory_lock` — `CREATE SCHEMA/TABLE IF NOT EXISTS` is not safe under
  true concurrency and will race on Postgres's own catalog.
- The `anonymized` export format enumerates scrub-fields by name, not by
  content inference — an unlisted future field defaults to *kept*. Real
  leaks were caught by testing, not anticipated: `source_nodes` (fold output,
  not on the patch schema) and unknown's actual field names
  (`question`/`why_unresolved`, not `statement`).
