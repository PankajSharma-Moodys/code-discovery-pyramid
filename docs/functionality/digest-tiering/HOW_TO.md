# How To — Digest & Tiering (`prompts.py` digest mode, `tiering.py`)

```bash
cdp prompts --digest             # inline full file text instead of Read instructions
cdp prompts --measure            # print fixed/variable token-cost split
cdp prompts --wave N             # write prompts for one wave only
```

Tiering (`reports/tiering.json`) is computed automatically by `cdp prompts`
and read back by `cdp collect` — no separate command.
