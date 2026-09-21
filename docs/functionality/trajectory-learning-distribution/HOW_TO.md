# How To — Trajectory Learning & Distribution (`trajectory.py`, `reflect.py`, Phase 9)

```bash
cdp reflect --run-id <id> --runner-cmd "<cmd>" [--limit N]
cdp lessons cut
cdp lessons show [--version N]
cdp lessons unpromote --version N [--reason "..."]
cdp holdout --repo <held-out-repo> --lessons N
```

`CDP_TRAJECTORY_DB` env var overrides the trajectory DB path (default
`~/.cdp/trajectories.db`) — always set it when experimenting, never point
experiments at the real file.
