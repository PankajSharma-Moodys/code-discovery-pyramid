# Know About — State & Snapshots (`state.py`, `snapshot.py`)

- `state.fold` is a pure map/reduce over the immutable patch log — nothing
  may enter `state.json` that isn't derivable from the log (the "fold
  invariant"). Verification is a per-patch map with no cross-patch state, so
  composing it inside fold cannot introduce order-dependence.
- `generation` (an integer stamped once per patch, `1 + max(prior generations
  for that node)`) is what makes supersession order-independent: `state.fold`
  picks the highest-generation `complete` patch per node, ties break on
  `stable_hash`, never insertion order.
- `scope_hash` (a content fingerprint of a scope's file set) is the primitive
  that lets `refresh` report "N/M scopes changed" and is the input a future
  dispatch loop needs to skip unchanged scopes — it does not itself skip
  dispatch (that's a `cdp run`-side decision).
- Two freshness dates only: `claim_reviewed_at`/`anchor_verified_at` — both
  are **commit shas, not timestamps**, because a wall-clock value would break
  the reproducibility gate (two scans of the same commit must hash
  identically). Staleness = churn since the sha, never elapsed time.
- A pure `git mv` must not be counted as churn: path-scoped `git log
  --numstat` sees a rename as an N-line addition unless `--follow -M100%` is
  used; `freshness.file_churned_between` checks numstat *numbers*, not "a
  commit exists."
- Rollback is a ledger (`rollback.json`), never a mutation — excluded patches
  are marked `superseded_by_rollback` conceptually but the patch file itself
  is never touched; `state.fold` takes an `excluded_run_ids` parameter.
  `--to-snapshot` orders by log append order (no timestamps exist), not time.
- `query --as-of <commit>` replays fold over a truncated patch log against the
  *current* xref/partition — it does not re-verify anchors or rebuild
  graph/xref (that's `refresh`'s job, at tree granularity, not log position).
