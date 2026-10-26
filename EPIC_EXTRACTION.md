# Epic: extraction fixes, measured by a scorecard (base: feature/imporvements head)

Budget: ≤ 80 lines. Spec: EXTRACTION_METRICS.md (authoritative; owner decisions in its section 8).
Rules as in EPIC_RECALL.md and EPIC_VERIFY.md: one owner per file, own worktree, own `CDP_HOME`/`--state-dir`
under `~/.cdp-phase1/<task>/`, nothing writes `~/.cdp`, no deletion commands of any kind.
`~/git` repos are read-only. Extractor tasks do NOT regenerate `tests/golden/`; they report the golden diff.
A task needing a file outside its Owns list stops and reports. One Sonnet agent per task.

**Order:** X0 first. Nothing else starts until the baseline exists and the owner has seen it.
Every later task is judged against it, so no task may define its own measure.

**Atomicity rule:** one task = one fact in one language (or one framework), <= 3 target cells, one before/after table.
A letter suffix is its own agent and its own task; letters of one ID are independent unless stated.

**Shared done-definition for every task except X0:**
0. Before coding, classify the misses of your target cells (all, or >= 30 by recorded seed) as real vs scorer error. Scorer errors are fixed in the scorer first, with a fixture, and the baseline re-taken. Report the split.
1. Scorecard run before and after (same command, same corpus).
2. Target cells reach the pass mark (95% S/G/M/R/U, 90% F), or the report says which did not and why.
3. No other cell drops.
4. Existing tests pass.
5. Report carries one before/after table (target cells + any cell that moved), no prose self-assessment.

**Generality (every code task; guards against tuning to the 3 corpus repos):**
6. Implement the construct as the language/library documents it, not just the forms seen in the corpus; the report names the reference used.
7. Add unit tests on small hand-written snippets covering the syntax variants, including ones absent from the corpus. Tests must not read corpus repos.
8. No holdout repo (owner decision 2026-10-26: the three corpus repos are huge monorepos, results on them are the check). Fixtures + rule 9 are the generality guard; the report says so.
9. Diff contains no corpus-specific strings (package prefixes, repo/project names, class names from the repos). Agent states this; supervisor greps the diff independently.
10. Framework tasks (F rows) cover the library's documented forms and version differences, not only the call shapes in the corpus.

| Task | Scope (baseline cells) | Status | Owns | Depends on |
|---|---|---|---|---|
| X0 | Scorecard script | done; X0b scorer fix 83f2471 (epic/x0b-scorer-fix: C# property attrs, collection exprs, multi-line attrs; 8 fixture checks); baseline retaken 2026-10-26 on b14daae | scripts/extraction_scorecard.py | - |
| X1 | C# annotations M1 0/2519 on fixed scorer (name, text, line, end_line) | done, verified (59ca47f on epic/x1-csharp-annotations; 100% (2519/2519) with X0b scorer; 68 old misses were all scorer errors, TRIAGE_X1_M1.md); unmerged | cdp/lang/csharp*.py | X0 |
| X2 | C# annotation args + fqn (M2, M3) | queued | csharp*.py | X1 |
| X3 | C# supertypes R1 0/832 | queued | csharp*.py | X0 |
| X4 | C# structured params G1 0/5473 | queued | csharp*.py | X3 |
| X5 | Python decorators -> annotations M1 (provisional) | done (5c507ac on epic/x5-py-annotations; 0/11 -> 11/11 before the owner deleted the Python files from the corpus; now 0 present, fixture tests only); unmerged | python*.py | X0 |
| X6 | Python bases -> supertypes R1 0/7 (provisional) | queued | python*.py | X27 |
| X7 | Python structured params G1 0/52 (provisional) | queued | python*.py | X6, X27 |
| X8 | JS structured params G1 0/216 (provisional) | queued | javascript*.py | X0 |
| X9 | (retired as a standalone task; owner 2026-10-26) triage happens inside each task, see rule 0. Done before retirement: a Scala, see TRIAGE_X9A.md; C# M1, see TRIAGE_X1_M1.md | retired | - | - |
| X10 | Span S3: a Java 85% b C# 74% c Scala 79% | queued | per-language file | - |
| X11 | (after X25) Types on defines, G2 + G3: a Java (29%/37%) b C# (73%/65%) c Scala (62%/44%) d Python (30%/11%). Void counts as return type (X0 reading; owner to confirm) | queued | per-language file | - |
| X12 | HTTP-out F2: a Java/JAX-RS 0/33 b C# HttpClient 0/4 c Scala 0/9 d JS axios/fetch 1/5 | queued | rules + per-language file (report first) | - |
| X13 | C# F4 schedule 0/22 (BackgroundService, Hangfire) | queued | rules + csharp*.py (report first) | X3 |
| X14 | C# F5 DI 0/376 (MS DI AddScoped etc.) | queued | rules + csharp*.py (report first) | X3 |
| X15 | F3 persist: a Java 70% b Scala 70% | queued | rules + java/scala (report first) | - |
| X16 | F7 Swagger annotations Java 88% | queued | java*.py | - |
| X23 | Scala companion `object X {` gets its own type define: S1 Scala 88% (146 misses) (owner: fix) | queued | scala*.py | X0 |
| X24 | Annotation with empty parens emits `args: {}`: M2 Scala 77% (120), Java (2) (owner decision) | queued | scala*.py, java*.py | X0 |
| X25 | Void return representation: investigate impact first (how consumers read `ret`; owner leans None/NULL or a fixed value like NO_RETURN, not "void"), then G2 work in X11 | queued | investigation, then per-language | X0 |
| X26 | Inventory labels .ts/.tsx `typescript` (H4 0/72 -> 72/72) | done, verified (991d99e, merged); TS cells now real: S4 60%, G1 0/54, G2 0/58, G3 0/13 | cdp/inventory.py, cdp/lang/__init__.py | X0 |
| X27 | Python corpus: dispatch (FastAPI, dd2837e82a0b) + CTFd (Flask, 66d49ae1c433) added to ~/git and the scorer corpus (5 repos) | done, verified (4259b34, merged); Python cells now real: G1 0/2560, R1 0/1115, M2 0/950, F3 0/2012 | scripts/extraction_scorecard.py | X0 |
| X28 | F1 covers Flask (spec row + scorer rule, 14 fixtures); Python U3 (49 y, 1 x) / U4 (3 n) samples judged | done, verified (d94c0ab, 7cb4c88, merged); F1 Flask 59/144 40%: misses look like flask_restx `ns.route` on Resource classes, not triaged | EXTRACTION_METRICS.md, scripts/ | X27 |
| X29 | Flask route emission (F1 Flask 40%); triage the 85 misses first (rule 0) | queued | python*.py, rules (report first) | X28 |
| X17 | Java text-block constant values | queued | java*.py | X0 |
| X18 | C# 14 extension members | queued | csharp*.py | X4 |
| X19 | Explicit "unsupported" per field: a Java b C# c Scala d Python e JS | queued | per-language file | X1-X8 |
| X20 | TS/JS extraction: split into atomic tasks X30-X46 in EPIC_EXTRACTION_TSJS.md (decisions D1-D6 made upfront there) | split, queued | web*.py | X26 done |
| X21 | TS member separator `.` -> `#`: now X30 (class members) and X31 (free functions, use fqns aligned; rescans on SQLite + Postgres) | split, queued | web.py, web_decl.py | X30 |
| X22 | Version check, per language; scope set after X19 | parked | - | X19 |

## X0 done-definition (additional)
1. One command scores all three repos.
2. Every row S1–H4 plus one row per framework (F1–F7) has a value in every column: `NN% (e/p)`, `N/A` or `0 present`.
3. Every ❌ cell lists up to 5 example misses as file:line.
4. 10 random "present" and 10 random "emitted" judgments listed with file:line (fixed seed, recorded).
5. U3/U4 manual samples list each checked call with file:line; seed recorded.
6. `git status` of each `~/git` repo recorded before and after, shown identical.
7. H3 from `~/.cdp/index.db` opened read-only, no rescan. If that scan lacks any of the three repos, report the gap; do not rescan.
8. Python/TS/JS columns marked provisional (decision 1). No recommendations in the report.
9. Nothing under `cdp/` changed; existing test suite passes.

## Owner decisions 2026-10-26
- Companion objects count (X23). Empty-paren annotations emit `args: {}` (X24). Void return: investigate first, owner leans a null/enum value (X25).
- No holdout repos. Triage inside each task (rule 0). Scorer stays in `scripts/`. Full suite runs during tasks. R2 (extends vs implements) dropped: `uses` rows already carry the kinds.
- Corpus changes by owner: deleted Python files and one Java file; added dispatch and CTFd. Baseline retaken on 7cb4c88.

## Open points
- Task scope is from the baseline; owns paths are guesses, agents report before touching others. X20/X21 (TS work) need splitting into atomic tasks; X6/X7 are ready.
