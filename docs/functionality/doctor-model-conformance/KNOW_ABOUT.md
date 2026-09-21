# Know About — Doctor / Model Conformance (`doctor.py`)

- Scores schema validity, anchor survival, entailment split, recall against a
  small hand-authored golden set, and false-unknown rate — recall alone is
  insufficient (a model that answers "unknown" everywhere scores perfectly on
  naive precision).
- The golden-set substring matcher is known brittle on real model output: a
  model can state the exact correct fact using different wording/subject
  than the golden entry's hardcoded substring, scoring a false 0% recall.
  This is an open problem left for a judge-model-based grader (M6.2), not
  patched in `doctor`.
- Yield-collapse (many scopes empty, 0 claims) can be an infra artifact
  (the leaf runner hanging on an unanswered permission prompt with no TTY),
  not a model-capability signal — always check `--allowedTools` semantics
  before trusting a doctor run's numbers as capability data.
