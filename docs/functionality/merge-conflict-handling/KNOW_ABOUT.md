# Know About — Merge & Conflict Handling (`merge.py`)

- `source_node` (singular, per-patch) is renamed to `source_nodes` (plural
  list) at merge time, since one claim can be attributed to several converging
  scopes post-merge. Any downstream code reading the singular field on merged
  output silently breaks (real defect, fixed in `entail.summarize`).
- Merge never fabricates an answer under genuine ambiguity: a cross-agent
  conflict becomes `contested` confidence, not an arbitrarily-picked winner.
- R11's "human vs model" merge-precedence half is explicitly **not**
  implemented in `merge.py._resolve` — only the entailment-layer half (human
  claim vs deterministic extraction → `contested`) is built. No real corpus
  scenario has produced a human-vs-model merge conflict to design against.
