# TRIAGE_X9A: Scala S1 and M2 misses (measure only)

## Method
- Ran `scripts/extraction_scorecard.py` (CDP_HOME=~/.cdp-phase1/x9a, out-dir /tmp/x9a_out): S1 scala 88% (1108/1254), M2 scala 77% (406/526).
- scorecard.json keeps only 50 misses per cell. I ran a copy (/tmp/x9a_scripts/sc.py, only `[:50]` changed to `[:5000]`, out /tmp/x9a_out2) to get all misses: S1 146, M2 120. Same percentages.
- Sample: sorted miss list, `random.Random(9101).shuffle`, first 35 per cell (>= 30). For each, I read the source line (+/-1) and dumped the extractor's defines/annotations for the file (via the script's own `load_repo`).
- To extrapolate, I also classified ALL misses by source-line regex (146 S1, 120 M2): no exceptions.
- Spec text applied (EXTRACTION_METRICS.md): S1 Present = "a line declares a type with a keyword: Scala: class, trait, object, enum"; Emitted = "a type define exists whose anchor.line is that line". M2 Present = "an emitted annotation whose text contains `(`"; Emitted = "it also has args (dict)".

## S1 scala (146 misses, 35 sampled)
| Category | Sample 35 | All 146 (regex) |
|---|---|---|
| REAL | 35 | 146 |
| CHECK-ERROR | 0 | 0 |
| AMBIGUOUS | 0 | 0 |

- Every miss is an `object X {` line (146/146) whose name also has a `class`/`trait X` in the same file (companion object). 0 are in comments/strings, 0 are other keywords, 0 are test files.
- Extractor output on those lines: no type define anchored there. Only the members inside are emitted, anchored on later lines (e.g. `DEF constant @51`). Where the companion class is emitted, it sits on its own line.
- The keyword line is a real `object` declaration and `object` is in the spec's Scala list, so I count all as REAL. The spec does not say companion objects are exempt or merged. Unclear sentence, if the owner intends merging: "Scala: `class`, `trait`, `object`, `enum`" (it does not mention companions). I did not count this as AMBIGUOUS because the text is explicit.
- Real fraction of misses: 35/35 sample, 146/146 all = 100%.
- Cell with CHECK-ERRORs excluded from denominator: 1108/1254 = 88% (unchanged, 0 check-errors).
- Sensitivity only (not my classification): if companion objects were not meant to count, 1108/1108 = 100%.

REAL pattern (one):
- "companion object": 146 of 146. Examples:
  - unified-store/exposure-snapshot/snapshot-legacy/snapshot-legacy-accumulation/src/main/scala/com/rms/unifiedstore/snapshot/accumulation/view/task/AccumulationViewTask.scala:312
  - workflow-service/workflow-service/persistence/execution-dal/src/main/scala/com/rms/execution/dal/dao/WorkflowDao.scala:238
- Split by repo: workflow-service 134, unified-store 12.

## M2 scala (120 misses, 35 sampled)
| Category | Sample 35 | All 120 (regex) |
|---|---|---|
| REAL | 0 | 0 |
| CHECK-ERROR | 0 | 0 |
| AMBIGUOUS | 35 | 120 |

- Every miss is an annotation with EMPTY parentheses: 35/35 sample are `@Inject()` on a class constructor (`class X @Inject() (...)`); all 120 = 118 `@Inject()` + 2 `@JsonCreator()`. The extractor emits the annotation (name, fqn, text `@Inject()`, line) with NO `args` key.
- Extractor behavior check (all annotations in unified-store and workflow-service, with `(` in text): Scala with non-empty args 408, all have `args` dict; Scala empty parens 120, none have `args`. Java: non-empty 3790 all have `args`; empty parens 2, none have `args`. So the extractor consistently omits `args` for `()`.
- Why AMBIGUOUS: "Present: an emitted annotation whose text contains `(`" is literally met by `@Inject()`, and "Emitted: it also has args (dict)" is literally not met (key absent, not `{}`). But the fact is named "Annotation args" and an empty `()` carries no arguments, so the spec does not say whether an absent `args` or `{}` is wanted. The unclear sentence is the Present line.
- Real fraction: cannot be fixed from the spec: 0% to 100% of the 120. Literal reading: 100% real. Intent reading: 100% check-error.
- Recomputed cell values:
  - literal (all REAL): 406/526 = 77%
  - if all counted as CHECK-ERROR and removed from denominator: 406/406 = 100%
- Pattern: "annotation with empty parentheses, args absent": 120 of 120. Examples:
  - unified-store/exposure-snapshot/snapshot-legacy/snapshot-legacy-accumulation/src/main/scala/com/rms/unifiedstore/snapshot/accumulation/view/task/AccumulationViewTask.scala:36
  - workflow-service/workflow-service/core/execution-api-core/src/main/scala/com/rms/execution/api/core/service/JobService.scala:29
- No miss involves named args, multi-line annotations, or non-empty args.

## Caveats
- Not run: any check on data-lake (no Scala cell misses are listed there; all S1/M2 scala misses were in unified-store and workflow-service).
- Sample order was not spec-ranked; the regex pass over all misses is the basis for "all" columns.
