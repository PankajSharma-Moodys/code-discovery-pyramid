# Know About — Cross-Repo Link (`link.py`, Phase 8)

- `link scan` only ever reads already-scanned state directories'
  `dataflow.json`/`manifest.json` — R3 ("scan writes, link reads") holds by
  construction, no store is ever opened for writing during a scan.
- A single whole-repo scan is sufficient for cross-module link discovery: a
  snapshot is exploded into one pseudo-snapshot per distinct `module` tag
  before matching, so a monorepo scan finds cross-module links without
  needing per-module state directories.
- The route-param-normalization regex must never be applied to
  `table:`/`entity:` channels — it collapses distinct table names onto one
  key by matching the literal `:tablename` syntax as if it were a route
  param (a real, high-severity bug, F-link1: 82,519 fabricated links from one
  collision).
- `link_id` must be a pure function of `(protocol, caller, callee)` content,
  recomputed on every read — never stored as report state, or a link
  persisted then re-read in a separate process silently fails to match
  anything (a false "0 resolutions folded" success).
- Cross-repo link tasks cannot reuse Phase 4's `gates.py` literally — those
  gates operate against one repo's own extraction index. Link tasks get
  their own closed vocabulary (`match`/`no_match`/`uncertain`) and their own
  entailment check (a cited anchor must be one of the anchors the prompt
  actually showed).
- `link.*` data lives only on `SqliteStore` (`supports_link_edges()` gate) —
  `FileStore`/`PostgresStore` refuse with a named error, never silently
  no-op or return empty.
