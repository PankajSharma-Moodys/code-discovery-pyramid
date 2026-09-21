# Where To — Verification / Entailment (`verify.py`, `entail.py`, `gates.py`)

| | |
|---|---|
| Core | `cdp/verify.py`, `cdp/entail.py` (`entail_claims`, `summarize`, `build_extraction_index`), `cdp/gates.py` (4 unknown gates, `NEEDS_VALUES`, `discharge_unknowns`, `grandfather_needs`) |
| Schema | `schema/patch-1.0.0.json` (`claim.verdict`, `unknown.needs`/`subject`/`channel`/`cluster_id`) |
| Tests | `tests/test_entail.py`, `tests/test_gates.py` |
