# Know About — Backend Selection (`store/`, `.cdp.toml`)

- Three backends — `sqlite` (default), `file`, `postgres` — selected via
  `.cdp.toml`'s `backend` key, never a CLI flag or env var.
- `WorkspaceStore`'s run/task/lease/retention methods are non-abstract with a
  split default posture: read-side methods default to an honest empty answer
  (`[]`/`None`); write-side methods default to raising a named `CdpError`.
  `FileStore` therefore "just works" for `scan`/`query`/`docs` and cleanly
  refuses `cdp run`/`cdp gc`/`cdp link` rather than silently no-opping or
  `AttributeError`-ing deep in `supervisor.py`.
- Every "does this backend support X" check (`supports_run_tracking()`,
  `supports_compaction()`, `supports_link_edges()`) exists so the *real*
  refusal reason is always what's reported — without it, a `FileStore` user
  running `cdp gc` sees a misleading "no snapshot for HEAD" instead of "this
  backend doesn't track snapshots at all."
- A git repository's hooks directory is **shared across every worktree** —
  `cdp githook install` run inside one worktree installs into the repository's
  one common `.git/hooks/`, affecting every other worktree of that repo too.
  This is real git behavior, not a CDP bug.
