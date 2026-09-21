# How To — Cross-Repo Link (`link.py`, Phase 8)

```bash
cdp link scan <state_dir> [<state_dir> ...] [--db path]   # can take a single dir
cdp link query --service <name> [--db path]
cdp link prompts --out <dir> [--runner-cmd "<cmd>"]
cdp link collect
cdp link refresh <state_dir> [<state_dir> ...] [--db path]
cdp link run --runner-cmd "<cmd>"      # dispatch ambiguous matches through leases
```

`--db` defaults through the same `.cdp.toml` → registry → `cwd/.cdp`
resolution every other command uses; pass it only to point at a store other
than the resolved default (e.g. a shared cross-repo link workspace).
