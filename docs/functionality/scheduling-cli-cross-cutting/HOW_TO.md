# How To — Scheduling / CLI Cross-Cutting Concerns

```bash
cdp help              # generated from the live argparse parser, cannot drift
cdp help --json        # machine-readable surface for a non-Claude driver
cdp status             # coverage, freshness buckets, per-run task table
cdp install <repo>      # copy skill + cdp-leaf agent + AGENTS.md into another repo
cdp install --self       # re-sync this repo's own vendored .claude/skills/cdp/ copy
```

Always pass `--repo` explicitly when your cwd is not the repo you're
operating on — omitting it defaults to cwd and silently produces
all-anchors-failed if that's the wrong tree.
