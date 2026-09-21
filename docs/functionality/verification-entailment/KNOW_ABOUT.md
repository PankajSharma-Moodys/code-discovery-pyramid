# Know About — Verification / Entailment (`verify.py`, `entail.py`, `gates.py`)

- Entailment matches over **structure only** (subject/channel/visibility),
  never claim wording — `test_no_statement_text_matching` pins this
  permanently. `visibility` is the only field checked for `contradicted`
  because it's the only claim field with both a same-shape counterpart in
  `definitions[]` and a closed enum.
- Four deterministic unknown-gates (never a model-as-judge — "an LLM judging
  another LLM's 'I don't know' is unverifiable all the way down"): subject
  exists, negative entailment, provenance state, clustering. `subject`/
  `channel` are optional on an unknown — a missing subject means "scope-level
  gap" and passes both gates unconditionally, not a hard requirement.
- `needs_*` (closed vocabulary: `needs_runtime`/`needs_external_doc`/
  `needs_human`/`needs_wider_scope`/`needs_other_repo`) is gate-enforced in
  `collect`, not JSON-schema `required` — a hard schema requirement would
  reject the whole patch (claims included) the moment one unknown lacked it.
  Grandfathering (`needs_migrated: true`) runs unconditionally inside every
  `fold`, never as a one-time backfill.
- R12 (unknowns are sticky): unknowns accumulate across *every* `complete`
  patch for a node (unlike claims, which take only the highest generation) —
  a later patch that omits a question does not resolve it. This was a real
  regression (F13) before the fix.
- `fold_hash`'s `extraction` parameter: `None` (omitted) and `{}` (empty dict)
  must hash identically for "no extract artifact" — a `default={}` vs
  `default=None` mismatch in `read_artifact` calls caused a permanent false
  `fold_hash mismatch` (fixed by using `has_artifact` as the gate).
