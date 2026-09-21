# Know About — Anchoring & Diffs (`anchor.py`, `diffs.py`)

- Humans are not exempt from anchor verification: `cdp answer` runs through
  `anchor.build_anchor` exactly like an agent patch.
- `cdp diff` operates on two independently-scanned `FileStore`/state
  *directories*, not on `SqliteStore` snapshot lineage — it never reads two
  snapshots of one store, because the CLI historically never produced more
  than one live snapshot per store directory.
