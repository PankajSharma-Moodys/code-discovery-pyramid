# Triage: csharp M1 misses after X1 (measure only)

## Result
- Rerun of /tmp/x1_triage/sc.py (copy; cap `[:50]` -> `[:5000]`): csharp M1 = 96% (1806/1874), identical to the scorecard. 68 missing annotations.
- The 68 are annotation counts, not locations. They come from only 5 miss locations (min(e,n) < n on 5 scanned items), with deficits 9+41+15+1+2 = 68.
- REAL 0 / CHECK-ERROR 68 (5 locations) / AMBIGUOUS 0.
- If the 68 are removed from the denominator: 1806/1806 = 100%.

## How a miss is decided
`score_code_facts`, scripts/extraction_scorecard.py:849-866. For each scanned type/member with `ann` > 0, it takes the defines anchored on `it["line"]`, `e` = their max `len(annotations)`, and a miss when min(e, n) < n.
`ann` is set in `Scan._scan_braces` (:300-318): `pend_ann` (:304) accumulates leading `[..]` counts and is attached to the next decl_item (:309-312).
`_cs_member` (:484-499) returns None for properties (only appended to `self.props`), so the pending count is never attached or reset at a property. The only reset for a non-declaration line is :316-318, and it is skipped when the line starts with `[`.

## Patterns (all CHECK-ERROR)
A. Same-line `[Attr] public T Prop { get; set; }` properties leak their count onto the next non-property member: 4 locations, 65 annotations.
 - Each property line starts with `[`, so :316-318 never resets `pend_ann`. The counts sum up (9, 41, 15 properties) and attach to the next method or field: `ToString()` or `_sv`. `ann_line` is the first attribute line, which is why the reported location is far above the item.
 - UpdateExposureSetArchiveRequest.cs:8 (n=9 on `ToString` at :26); CreateAccumulationAnalysisRequest.cs:13 (n=41 on `ToString` at :55; 41 attribute lines in file, all same-line attrs except `[Required]` lines).
 - SqlPoolReservationOutput.cs:48 (n=15 on `ToString` at :68; the file has 16 attribute lines, 15 attached here, I did not trace the 16th).
 - ImportTransientDbRequest.cs:31 (n=2 on field `_sv` at :35; `[Required] public string DatabaseName {..}` at :31 and :33).
 - Extractor output for the properties is correct: UpdateExposureSetArchiveRequest.cs has 9 `field` defines at lines 8..24, each with 1 `JsonPropertyName` annotation at its own line. ImportTransientDbRequest.cs defines at :31 and :33 each carry `Required`.
B. C# collection expression `[` counted as an attribute: 1 location, 1 annotation.
 - UpgradeSystemDatabasesBackgroundJob.cs:59 (`[` alone at :59 opens `.. s_systemDbsDatasetMemberNames,` as a list initializer; `_leading_annotations` :350-385 treats it as an unclosed attribute, n=1). The scorer's member scan then sees the `..` spread line at :60 as a field `s_systemDbsDatasetMemberNames`; the extractor has no define at :60 (defines in that file: lines 26, 36, 38, 49, 51, 52, 58, 68, 132).

## Known example (UpdateExposureSetArchiveRequest.cs:8)
The extractor emits `JsonPropertyName` on the define at :8 (confirmed by dump). The miss is not about line 8: the scorer's `ann_line` is the first accumulated attribute line (:8), but the checked item is `ToString` at :26 (no annotations), carrying the 9 property attributes of the file. Cause: pattern A.

## Method
- Ran sc.py as given, except `python3 -I` fails (`No module named cdp`: -I drops cwd), so I ran `PYTHONPATH=<worktree> python3` (no -I; script dir /tmp/x1_triage holds only my scripts).
- Added one logging line in a second copy (/tmp/x1_triage/sc2.py) after `c.misses.append(w)` to dump n, e, category, name, line and defines at the item line; this gave the 5 rows.
- Read each source (lines 1-30 / 10-16 / 45-70 / 56-62 / 28-37) and dumped defines+annotations with /tmp/x1_triage/dump.py (cdp inventory + extract + rules). Counted attribute lines with grep -c.
- Not run: M1 scoring excluding the 5 locations beyond arithmetic (1874-68).
