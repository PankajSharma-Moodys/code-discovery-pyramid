# Where To — Scanning / Extraction (language extractors)

| | |
|---|---|
| Core | `cdp/extract.py` (`run_extract`), `cdp/inventory.py` (`build_inventory`, `DEFAULT_EXCLUDES`), `cdp/anchor.py` (`find_matches`, `build_anchor`) |
| Extractors | `cdp/lang/__init__.py` (registry, `classify_role`), `cdp/lang/{java,python,web,go,sql,data,csharp,scala,base}.py` |
| Tests | `tests/test_extract_parallel.py`, `tests/test_anchor.py`, `tests/test_inventory_excludes.py`, `tests/test_csharp.py`, `tests/test_scala.py`, `tests/test_module_roots.py` |
| Docs | `PHASE/TARGET.md` (Finding T1: extractor coverage), `RESEARCH_GRAPHIFY.md` §9 |
