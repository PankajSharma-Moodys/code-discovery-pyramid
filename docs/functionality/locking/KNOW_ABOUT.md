# Know About — Locking (`cdp/lock.py`)

- Per-repo mutual exclusion (pessimistic), not optimistic compare-and-swap.
  Some hazards this closes can't be expressed as a version check: `compact`'s
  `VACUUM` cannot run while another connection holds an open write
  transaction, and `refresh` moving the shared "current snapshot" pointer
  (`snapshot_meta.touch_seq`) mid-read produces a torn, cross-commit view
  with no error raised.
- Scope is per-repo, keyed off whatever `_paths()` already resolved
  (`--state-dir`, `--repo`, the `.cdp.toml` walk, or the `~/.cdp/config.toml`
  registry) to one canonical `paths.state` directory. Two processes naming
  the same repo contend; two processes on different repos never see each
  other's lock.
- Backend-dependent implementation, chosen by the same `_resolve_backend()`
  every command already calls — this module never re-derives backend
  config:
  - `sqlite`/`file` — an `fcntl.flock` on `<state_dir>/.cdp.lock`.
  - `postgres` — a session-scoped advisory lock (`pg_try_advisory_lock[_shared]`)
    keyed by `repo_identity()`, on a throwaway connection independent of the
    command's own `WorkspaceStore` connection. Postgres has no shared local
    directory to lock, and this backend exists specifically so multiple
    machines share one server.
- Shared (`shared=True`) vs. exclusive (`shared=False`) is chosen per
  command, not per invocation: shared is for a command that only needs a
  torn-write-free multi-artifact *read* (`query`, `docs`, `status`, `diff`,
  `export`, `verify`, `doctor`) and blocks a concurrent writer without
  blocking another reader; exclusive is for anything that appends a patch,
  writes an artifact, moves the snapshot pointer, or touches task/rollback
  state, and blocks every other locked command, reader or writer alike.
- Default wait is 60s (`DEFAULT_TIMEOUT_S`), polled every 0.2s
  (`_POLL_S`) — not configurable from the CLI (no `--lock-timeout` /
  `--no-lock` flag exists). A crashed holder of a file lock leaves
  `.cdp.lock` on disk but not held (`fcntl` locks release when the holding
  process dies); the timeout message explicitly tells the operator to
  delete the file if the other process crashed rather than exited cleanly —
  that guidance is cosmetic reassurance, not a required step, since a dead
  process's flock is already gone.
- Two identical copies of this module exist by design, not by drift:
  `cdp/lock.py` and the vendored `.claude/skills/cdp/cdp/lock.py`. See
  [cross-cutting-infra](../cross-cutting-infra/) for the distribution
  mechanism that keeps them byte-identical.
