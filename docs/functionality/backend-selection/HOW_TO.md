# How To — Backend Selection (`store/`, `.cdp.toml`)

```toml
# .cdp.toml
backend = "sqlite" | "file" | "postgres"
exclude = ["some_dir"]
```

```bash
cdp gc --dry-run [--pin SHA] [--unpin SHA] [--db path]   # retention: HEAD/pinned/cited kept
cdp compact --compact-threshold 0.30 --keep-generations 1 [--dry-run] [--db path]
cdp verify --full [--db path]                            # re-fold from archive, prove hash
```

Install hooks for auto-refresh on commit/checkout:

```bash
cdp githook install [--strict]     # post-commit + post-checkout -> cdp refresh
cdp githook uninstall
```

Note: hooks install into the repository's one shared `.git/hooks/`, affecting
every worktree of that repository, not just the one you ran the command in.
