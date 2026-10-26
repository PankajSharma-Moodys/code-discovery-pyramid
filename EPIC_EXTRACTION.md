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

**Shared done-definition for every task except X0 and X9:**
1. Scorecard run before and after (same command, same corpus).
2. Target cells reach the pass mark (95% S/G/M/R/U, 90% F), or the report says which did not and why.
3. No other cell drops.
4. Existing tests pass.
5. Report carries one before/after table (target cells + any cell that moved), no prose self-assessment.

**Generality (every code task; guards against tuning to the 3 corpus repos):**
6. Implement the construct as the language/library documents it, not just the forms seen in the corpus; the report names the reference used.
7. Add unit tests on small hand-written snippets covering the syntax variants, including ones absent from the corpus. Tests must not read corpus repos.
8. Holdout: score before/after on a repo the agent never sees during development (owner to name one per language; if none, fixtures only and the report says so). Target cells must move there too.
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
| X6 | Python bases -> supertypes R1 0/7 (provisional) | queued | python*.py | X5 |
| X7 | Python structured params G1 0/52 (provisional) | queued | python*.py | X6 |
| X8 | JS structured params G1 0/216 (provisional) | queued | javascript*.py | X0 |
| X9 | Triage, measure only, no code. a done (TRIAGE_X9A.md: S1 Scala 146 misses = companion `object X {`, all real by spec text; M2 Scala 120 misses = `@Inject()` empty parens, spec ambiguous) b-e queued. a Scala (S1 88%, M2 77%) b JS (S2, S4 40%, R3 94%) c C# (U3 32%) d Java (F1 97%, F6, F7) e Scala/Java (F3 70%): real miss or text-check error? | queued | notes in SCORECARD.md only | X0 |
| X10 | Span S3: a Java 85% b C# 74% c Scala 79% | queued | per-language file | X9 |
| X11 | Types on defines, G2 + G3: a Java (29%/37%) b C# (73%/65%) c Scala (62%/44%) d Python (30%/11%). Void counts as return type (X0 reading; owner to confirm) | queued | per-language file | X9 |
| X12 | HTTP-out F2: a Java/JAX-RS 0/33 b C# HttpClient 0/4 c Scala 0/9 d JS axios/fetch 1/5 | queued | rules + per-language file (report first) | X9 |
| X13 | C# F4 schedule 0/22 (BackgroundService, Hangfire) | queued | rules + csharp*.py (report first) | X3 |
| X14 | C# F5 DI 0/376 (MS DI AddScoped etc.) | queued | rules + csharp*.py (report first) | X3 |
| X15 | F3 persist: a Java 70% b Scala 70% | queued | rules + java/scala (report first) | X9 |
| X16 | F7 Swagger annotations Java 88% | queued | java*.py | X9 |
| X17 | Java text-block constant values | queued | java*.py | X0 |
| X18 | C# 14 extension members | queued | csharp*.py | X4 |
| X19 | Explicit "unsupported" per field: a Java b C# c Scala d Python e JS | queued | per-language file | X1-X8 |
| X20 | TS decorators, supertypes, params, accessor | blocked: TS never labelled `typescript` (H4 0/72); split once unblocked | typescript*.py | owner call |
| X21 | TS member separator `.` -> `#.`; fresh rescans, SQLite + Postgres, no migration | blocked as X20 | TS extractor + store/query (report first) | X20 |
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

## Open points (owner)
- Owner decision needed (X9a): do companion objects get their own type define (S1 Scala)? does `@Inject()` count as present for M2 (extractor emits no `args`)?
- Corpus drift: the owner deleted Python files from the corpus, so Python cells differ from SCORECARD.v0.md; Java 4244->4243 files unexplained.
- X0 caveats: H3 excludes data-lake (no stored scan) and uses scans older than current HEADs; U3/U4 verdicts are the agent's own (U4 pool is 1 call per language, so U4 cells mean little); TS column is all `0 present`.
- TS/JS labelling (H4) is deferred by decision 1, but X20/X21 cannot be measured until it is fixed. Decide: fix labelling first, or leave TS out of this epic.
- R2 (extends vs implements) is "not emitted anywhere" and has no task. Add one if wanted.
- Scorecard stays in `scripts/` (confirm). Owns paths are guesses; each agent reports before touching files outside its list.
- Task scope is from the X0 baseline; X10-X16 rely on X9 saying the misses are real.
