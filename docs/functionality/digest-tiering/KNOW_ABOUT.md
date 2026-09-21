# Know About — Digest & Tiering (`prompts.py` digest mode, `tiering.py`)

- Tiering v1 is a rule, not a learned score: everything is T2; a scope
  escalates to T3 only on an unresolved import (pre-dispatch, free) or the
  leaf's own `escalated: true` self-report (post-dispatch). The residue score
  concept is explicitly deferred until calibration data exists.
- Tiering computed per-module can wildly over-report T3 (inter-module imports
  look "unresolved" when a sibling module isn't in scope) — always compute
  tiering against a full-repo scan, not a single-module scratch scan, to get
  an honest T3 rate.
- Fixed per-leaf prompt overhead (~378 tokens/leaf measured) is small relative
  to per-scope variable content (~5.8k tokens/leaf) — batching multiple
  scopes per model call was evaluated and explicitly *not implemented*
  because the savings don't justify losing per-scope failure isolation.
