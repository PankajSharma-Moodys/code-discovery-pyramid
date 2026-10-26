# Epic: TypeScript/JavaScript extraction (split of X20/X21; part of EPIC_EXTRACTION.md)

Budget: <= 70 lines. Facts: gap analysis 2026-10-26 (baseline 36d58cd). Rules, generality items and done-definition
as in EPIC_EXTRACTION.md (rule 0: classify target misses first; fixtures; no holdout; own worktree from feature/imporvements).
TS and JS share ONE extractor (cdp/lang/web.py, web_decl.py, web_flow.py, web_scan.py): one fix covers both languages, so
tasks are per fact, not per language. Tasks touching web.py/web_decl.py run ONE AT A TIME in the order below. Today the
extractor emits only fqn, kind, visibility, anchor, end_line, value (no params, ret, ftype, annotations, supertypes).

## Owner decisions, made upfront (veto by replying; none are open)
- D1 S4 convention: free functions and arrows get kind `function` and fqn `<module>#<name>` (as Python does; the scorer
  exempts kind `function`); class members get kind `method` and `<module>.<Class>#<name>`. Define and use fqns change together
  (use fqns are built in web.py ~118-122). Fresh rescans, SQLite and Postgres both, no migration.
- D2 Type alias: new kind `alias` (no extractor has one; Scala/Python/C# aliases are not defines). No scorecard cell counts it.
- D3 Object-literal methods (JS, ~1198 by heuristic, mostly vendored/static): excluded. The spec's present rule cannot measure
  them and nothing needs them; revisit only if a user query does.
- D4 Production-file rule for coverage rows (S, G, M, R, U, F), JS: exclude `*.min.js` and bundled/hashed assets (spec edit).
  H rows keep all files (H1 errors on vendored bundles still count). Scorer task X44.
- D5 F2 `fetch`: bare `fetch(`, `window.`/`globalThis.`/`self.fetch(` count; other dotted `X.fetch(` (e.g. a project wrapper
  `CTFd.fetch(`) does not: it cannot be known to be HTTP. Scorer task X45. Non-literal URLs emit `http:<VERB> {}` (X43).
- D6 R3 (TS 179/187, JS 1422/1458) and S2 TS (166/171) pass the mark: no task. G2 `ret` text truncation (`Promise<`) is
  scorer-side only and changes no count: no task.

## Tasks (cells: baseline count -> target)
| Task | Scope | Files | Verified on | After |
|---|---|---|---|---|
| X44 | Scorer: D4 exclusion + spec text | scripts/extraction_scorecard.py, EXTRACTION_METRICS.md | corpus | - |
| X45 | Scorer: D5 F2 present rule | scripts/extraction_scorecard.py | corpus (F2 JS 3/121 -> 3/13 by arithmetic from the gap analysis: 121-35 minified/bundled-73 wrapper; not re-run) | - |
| X30 | JS class member fqn `Cls.m` -> `Cls#m`, kind method: S4 80 misses | web.py | corpus | X44 |
| X31 | Free functions/arrows: kind `function`, `mod#name`; use fqns aligned; S4 TS 84, JS 460. Report resolved% before/after on a scanned repo | web.py, web_decl.py | corpus | X30 |
| X32 | Params G1: TS 0/60, JS 0/351 (function, arrow, method, ctor) | web_decl.py, web.py | corpus | X31 |
| X33 | Return type G2: TS 0/61 (full text, generics kept) | web_decl.py, web.py | corpus | X32 |
| X34 | Interface property/method signatures emitted as defines: S2 TS 5 misses | web_decl.py | corpus | X33 |
| X35 | Field type G3: TS 0/15 (10 consts/lets + 5 interface props from X34) | web_decl.py, web.py | corpus | X34 |
| X36 | Supertypes R1: `extends`/`implements`, interface extends: JS 0/1, TS 0 present | web_decl.py, web.py | JS 1; TS fixtures | X35 |
| X37 | Decorators -> annotations M1 (name, text, line, end_line); decorated members no longer dropped (web_decl.py:77 skips `@`) | web_decl.py, web.py | fixtures only (0 in corpus) | X36 |
| X38 | Decorator args + fqn M2, M3 | web_decl.py, web.py | fixtures only | X37 |
| X39 | `accessor` fields (TS 5): S2/G3 | web_decl.py | fixtures only (0 in corpus) | X38 |
| X40 | Type alias kind `alias` (D2); 36 in corpus; first list every consumer that enumerates kinds, report before editing any outside web*.py | web_decl.py | corpus (36) | X39 |
| X41 | `const enum` -> kind enum; `namespace`/`declare module` members | web_decl.py | fixtures only | X40 |
| X43 | F2 JS non-literal URL: 6 bare `fetch(url)`, 4 `axios.*` -> target `http:<VERB> {}` | web_flow.py | corpus | X45 |
| X46 | H1: 4 swagger-ui*.js extractor errors -> 0 (one did not reproduce standalone: reproduce in the real scan first) | web.py/web_flow.py (report first) | corpus | X41 |

Targets: S4 95%, G1/G2/G3/M/R 95%, F2 90%. Cells with 0 corpus cases are fixtures-only; the report says so.
Not tasks (decisions above): object-literal methods (D3), TS R3/S2, G2 text truncation (D6), H4 labelling (X26 done).
