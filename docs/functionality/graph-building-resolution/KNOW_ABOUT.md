# Know About — Graph Building & Resolution (`graph.py`, `resolve.py`, `dataflow.py`)

- Declared-edge resolution must never fabricate a winner under a basename
  ambiguity (two modules sharing a basename): an ambiguous basename yields
  **no edge**, recorded in `graph.declared_ambiguous`, surfaced as a
  structural unknown — never resolved by an arbitrary/sorted pick. This
  mirrors the *observed*-graph policy in `owners_of`, which already refuses to
  pick a single FQN owner when more than one location declares it (R6: never
  a silent gap, and no merge operator that "always produces an answer").
  This was a real non-determinism (flapping across `PYTHONHASHSEED`), fixed
  by an explicit multi-candidate/no-edge design, not by sorting the set.
- `dataflow.py` keys its adjacency on a file's *primary symbol*, not the raw
  route-handler string `resolve.py` records — walking blindly from the raw
  handler produces a false "leaf endpoint" trace. `_pivot` retries the owning
  class then the primary symbol and records `pivoted_from` rather than
  substituting silently.
- `graph._looks_third_party` is a hardcoded pattern list, known incomplete
  (misses real internal-org roots like `com.rms.auth.framework.*`); an
  `import_channel_hint` lesson (Phase 9) is the mechanism meant to extend it
  at routing time, never at claim-content time (R10).
