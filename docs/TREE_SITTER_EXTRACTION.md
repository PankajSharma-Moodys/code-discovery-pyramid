# Tree-sitter (tool-based) extraction

Budget: 60 lines. Figures are from scorecard runs at `79a8154` (5-repo corpus, one run each).

## What it is
A shared layer in `cdp/ts/` parses source with tree-sitter and emits declaration rows (`cdp/ts/rules/<lang>.scm`, mapped by `emit_map.json`) in the same schema as the hand extractors. It covers declarations: names, kinds, visibility, params, return and field types, supertypes, annotations.

## Install
Needs the `ts` extra: `pip install -e '.[ts]'` (pins in `pyproject.toml`; the core stays dependency-free). See README "Install".

## Switch
`CDP_TS=<lang,lang | all | off>`. Default: `java,scala,typescript,javascript,csharp,python`. `CDP_TS=off` runs the hand extractors only. `all` or `baseline` also turns on the day-0 baseline fallback for languages with no extractor.

## How it works with the hand code
It is an overlay, not a replacement. For java, csharp, python and scala the extractor first runs the hand parse, then `<lang>_ts.apply(...)` takes the hand `facts.defines` as input, replaces rows with tool rows, and carries hand-only fields (tparams, throws, signature, constant value, annotation args and fqn) by (fqn, line). If the tool returns nothing for a file (generated-file policy, parse error, empty or import-only file, over-long lines), the hand rows stay.

Hand code still produces every use, call, edge, import, constant and resolved type. The tool has no uses or call queries, no constructor rows (Scala), no annotation arguments and no type resolver.

## Measured effect (tool on vs `CDP_TS=off`)
- Failing scorecard cells: 13 of 180 vs 27. 14 cells fixed, none newly failing.
- Fixed: S3 (java, csharp, scala), S4 (typescript, javascript), G1/G2/G3 (typescript, javascript, python), M1 python, M3, R1, S1 scala. Python gains are new capability: the scorer finds nothing there with the tool off.
- Speed (H2): 265.1 to 185.4 kLOC/s pooled, one run each, noise not measured.
- Hand code did not shrink. Proof-of-concept branches `poc/ts-min-{java,csharp,python,scala}` (not merged) removed 59, 9, 5 and 28 lines of about 3150, 3760, 1880 and 2420, with the fact dump identical (Java: 1 file differs and 3 tests fail).

## Still failing with the tool on
F2 (java, csharp, scala), F3 (java, scala), F4 and F5 (csharp), F7 (java), U3 (csharp, scala), U4 (scala, python), H4 language label (python). These are framework rules and judged samples; the tool does not touch them.

## Known issues
- With `CDP_TS=off`, `tests/test_empty_paren_annotations.py::test_java` and `::test_python_decorators_unchanged` fail; all 5 pass with the default.
- The tool cache version hash must list every `cdp/ts` module, or a stale cached result hides a fix (`cdp/ts/cache.py`).
- Process pools crash in some sandboxes; run the scorecard with `workers=1`.

## To shrink the hand code later
The tool layer needs a type resolver (receiver types, resolved annotation, return and assign types), call and use queries with scope, constructor and constant rows, annotation argument trees, and error tolerance for rejected files. Then `CDP_TS=off` can be retired.

## Check
`python3 scripts/extraction_scorecard.py` (spec: `EXTRACTION_METRICS.md`); run once with `CDP_TS=off` and once without, and diff the cells.
