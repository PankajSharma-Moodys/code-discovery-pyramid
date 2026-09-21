# How To — Locking (`cdp/lock.py`)

Locking is automatic and not user-facing — every store-touching command
already takes the right kind of lock via the `@_locked(shared=...)`
decorator in `cdp/cli.py`. There is nothing to opt into and no flag to
disable it.

If a command hangs waiting on the lock, it raises after the 60s default
timeout:

```
another cdp process is already writing to this store (<state_dir>) -- waited
60s. If that process crashed instead of exiting cleanly, delete <state_dir>/.cdp.lock
and retry.
```

- If the reported process is still running (check `ps`/your job runner),
  wait for it or stop it — do not delete the lock file out from under a
  live process.
- If it crashed, delete `<state_dir>/.cdp.lock` and retry. This is only
  needed for the `sqlite`/`file` backend's on-disk lock file; a Postgres
  advisory lock is released automatically when the holding connection
  drops.

Commands that only read (`query`, `docs`, `status`, `diff`, `export`,
`verify`, `doctor`) take a shared lock and can run concurrently with each
other; they still block behind, and block, any writer (`scan`, `run`,
`refresh`, `fold`, `collect`, `prompts`, `reflect`, `holdout`, `gc`,
`compact`, `rollback`, `answer`, and the `link` subcommands other than
`link query`).
