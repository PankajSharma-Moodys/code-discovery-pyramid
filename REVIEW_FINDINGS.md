# Independent review findings (2026-10-15) — budget: 80 lines

Source: research agent on snapshot 0dcd53b+uncommitted (before relationship-following), measured on clones of
workflow-service and unified-store, no model calls. "(unverified)" = the reviewer's measurement, not reproduced.
Scores: Quality 7, Scalability 6, Features 8, Harness 7, Overall 7.

## Quality — wrong or misleading answers
1. [x] Java `import static` constants unresolved: 18/580 routes `${..PATH}`, 12 unknowns say "not defined anywhere".
2. [x] Overloads share calls in `symbol` body rows — all languages, not just Scala (grounded: Java 38+215, Scala 68,
       C# 164). **Decided: plan B** — additive signature id (`Class#m(Types)`) as `sig`/`from_sig`; name stays the
       primary id (claims, links, --as-of); `symbol` body rows and `trace`/`paths` nodes use `sig`.
       Done (uncommitted): pooled sites ws 176 -> 0, us 659 -> 0; overload->overload steps not counted
       toward the hop cap (us paths 504 -> 512); field-initialiser calls listed under every constructor; scan's
       collision count excludes overloads (ws 624 -> 474). C# partial-class overloads across
       files get sigs too (us: 3 methods, e.g. AdminController#AddJobTypeAsync).
3. [x] Scala `logger.info` (StrictLogging) resolves to the class itself (`ArchiveLogService#info`).
4. [x] `symbol`/`trace` embed test/library claims. **Decided:** same default filters as `claims`.
5. [x] Claims built from library imports (mapstruct `Mappers` -> "converted to factory"); need `@Mapper`.
6. [x] Nested Gradle builds: ~20 false "imported but not declared" (paths relative to the wrong settings.gradle).
7. [x] 19-20 false "declared but never imported" for `platform(project(':..-bom'))`. **Decided:** keep the edge,
       label it "uses version platform", not an anomaly. Library-version view = separate feature (F-lib).
8. [x] Help: "elided: 0 — the list is complete" while the answer is paged (shown 1-57 of 91).
9. [x] Text `stats` omits languages that help promises. **Decided:** add one line.
10. [x] `--budget 5` reports inconsistent numbers ("56 rows … elided 69 … budget=74").
11. [x] Budgeted table rows drop their file:line citation.

   #1,#3-#11 done (uncommitted); #4 `trace` half not reproduced (trace embeds no claims); logger calls stay out (decided).

## Scalability
12. [x] Per-query fixed overhead ~1-2 s: 16 `git` subprocesses (0.76 s) + whole-artifact JSON decode (0.49 s).
13. [ ] Store = one JSON blob per artifact (935 MB, 30 rows), no per-element index.
14. [ ] MCP server reopens the store per call (`mcp_server/tools.py:91`): warm == cold.
15. [ ] Peak RSS ~0.7 MB/file: 3.4 GB on unified-store (4.8k files); risk at 20k+.
16. [ ] Each snapshot is a full copy: 187 -> 346 MB after one refresh.
17. [ ] Refresh after a one-file change 4.7 s vs 7.1 s full scan.
18. [ ] Unbudgeted answers large: stats ~4.1k tokens, coverage ~5k; one route compact 10.6 KB (OpenAPI args).
    Measured 2026-10-15: SQL `json_each` on the blob 0.13 s vs json.loads 0.22 s; one-row-per-element table with an
    index 0.04 ms (+0.27 s at scan).
    Decided 2026-10-16 (profiled: 16 git calls 0.43 s, decode 0.41 s, no git hook involved):
    #12 git part done -- repo root/git dir asked once per command (16 -> 5 git calls); dirty check kept as is
    (left: its 4 repeated name-only diffs on a dirty tree, and an fsmonitor tip in doctor).
    #13 keep one blob per artifact: no new table, no document store, no JSON-in-SQL lookups.
    #14 MCP cache parked. #16 full snapshot copies are fine; if ever needed, split into a document DB.

## Features — gaps
19. [ ] `--as-of` fails on a scanned commit with no claims of its own (while `diff` uses that snapshot).
20. [ ] Helm `configmap data.X` not joined to env-var reads (`config EXECUTION_JOBS_DATABASE` declared 0).
21. [ ] `routes unresolved` returns 0 rows though the scan reports 18.
22. [ ] Calls through generated OpenAPI clients invisible (`LockServiceClient.scala:40`).
23. [ ] No Kotlin, Rust, Ruby, C++.
24. [ ] Leaf prompts list noise files (Kibana JSON, gradle-wrapper.jar).

## Harness — how it steers the agent
25. [ ] Strict gate presents a partial answer as complete (denied grep `requestLock`; missed `LockServiceClient.scala:40`).
26. [ ] Nudges send config keys and table names to `kind=symbol`, not `config`/`table`.
27. [ ] In strict mode those greps get neither nudge nor deny (gate replaces the nudge, `install.py:263`).
28. [ ] Coverage rule contradicts itself: deterministic coverage is always 0%, so "not found" never means absent.
29. [ ] SessionStart injects ~3k tokens on every start and compaction.
30. [ ] UserPromptSubmit injects ~400 tokens on every prompt, even non-code ones.
31. [ ] Strict-mode hooks add 1.2-2.2 s to each Bash/Grep/Read.
32. [ ] Leaf prompt says "Java/Python/JS/Go extractor" (stale: Scala, C# missing).

## Not verified by the reviewer
33. Agent behaviour under hooks/MCP; leaf and link resolution quality (need model calls).
34. MCP token counts are chars/4 estimates (1990/2000 unconfirmed).
35. Web UI not run (backend only).
36. Python and Go extractors not tried on real code.
37. Cold-cache timings.

## Plan
- Now: #2 (plan B) by one subagent; then verify and measure; then #1, #3-#11 by a second subagent.
- Later, each with its own approval: speed (#12-#14), harness (#25-#31), gaps (#19-#22), F-lib (library versions).
