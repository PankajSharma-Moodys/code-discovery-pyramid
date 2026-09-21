# How To — State & Snapshots (`state.py`, `snapshot.py`)

```bash
cdp fold --check --repo <path>        # verify state.json derivable from log
cdp refresh --repo <path>             # rescan + re-verify + fold; claim decay
cdp rollback --to-run <run_id|sha>    # exclude one run's patches, re-fold
cdp rollback --to-snapshot <sha>      # exclude everything after S (log-order)
cdp query claims --as-of <run_id>     # replay fold at a historical log position
```
