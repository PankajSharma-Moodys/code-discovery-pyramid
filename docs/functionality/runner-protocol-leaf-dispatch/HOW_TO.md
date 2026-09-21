# How To — Runner Protocol & Leaf Dispatch (`runner.py`, `supervisor.py`, `scripts/claude_leaf_runner.sh`)

```bash
cdp status                                  # scopes in the next wave
cdp run --wave N | --wave-all | --stale-only | --scope <node>
cdp run --scope <node> --runner-cmd "<cmd>"  # background one per scope for concurrency
cdp run --resume                            # reclaim lapsed leases, continue same run_id
cdp run --max-attempts N
cdp run --lessons vN | --no-lessons
```

Manual (no `--runner-cmd`) mode: `cdp run` writes `.cdp/prompts/<node>.md`
and blocks on `.cdp/patches/inbox/<node-with-/-as-__>.json` — hand a leaf
agent that contract directly (see `SKILL.md`).
