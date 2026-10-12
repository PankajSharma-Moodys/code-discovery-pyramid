# CDP — Annotations Plan (complete)

**Budget:** none, by request. Every "today" fact was probed or read in code on 2026-10-12;
anything not yet checked is marked **(to ground)** and is checked at the start of its phase.

## 1. Goal

Every annotation (Java, Scala), attribute (C#), decorator (Python) and struct tag (Go) is in
the index verbatim, with its lines and parsed arguments, and reaches every answer that cites
its declaration. Method bodies become searchable code text cited to their member.

CDP is a harness: it hands the agent the source facts, and the agent interprets them. CDP
interprets an annotation itself only where an answer needs a join across files that text
search cannot do — routes, outbound HTTP, event topics, schedules, SQL → tables. Everything
else (`@Transactional`, `@RolesAllowed`, `@Cacheable`, a team's own annotations) is shown
verbatim wherever its symbol is cited, and the agent reads it.

## 2. Principles

1. **Capture is unconditional.** No allow-list decides what is stored.
2. **Interpret only for joins.** Built-in rules exist only for facts that combine several files
   (§1). No team-rule files, no behaviour labels: the agent derives those from the annotation.
3. **One source of truth.** Facts live on the declaration row in `extract`; `xref` is rebuilt
   from it; claims, routes and tables never hold copies — queries attach by cited symbol.
4. **Additive by default.** Existing fields keep their values. The only intended value changes
   are bug fixes (P1) and rule-migration differences, each listed and reviewed.
5. **Refresh for free.** Everything rides on `defines` rows, which `incremental_extract`
   already drops and re-derives per module (`refresh.py:68-146`); rule application runs as a
   post-pass on every scan and refresh.
6. **No search index for now.** Search is a plain scan; scale is revisited when measured.
7. **Every phase ends verified** on fixtures and on real sql-pool, with output shown.

## 3. Today (grounded)

| # | Finding | Evidence |
|---|---|---|
| T1 | Parser reads full annotation text, then drops it | `java_decl.py` `_modifiers` builds `(name, text)`; `java.py` `_declarations` never stores it |
| T2 | Line reader: one annotation per line, at line start | `java.py:64` `ANNOTATION_RE`; reused at `java.py:702` |
| T3 | → `@RestController @RequestMapping("/c")` gives `GET /x`, not `/c/x` | probe |
| T4 | → `@Entity @Table(name="pool_config")` gives no table | probe; sql-pool `EPoolConfig.java:9` has this shape |
| T5 | `@Every`, `@DelayStart`, `@Scheduled`, `@Transactional`, `@RolesAllowed`, `@Retryable`, `@Async`, `@PostConstruct`, `@Query` values: absent | probes; `search @Every` = 0 hits on sql-pool |
| T6 | Spring `@Scheduled` produces no schedule claim (edge targets the class, `derive.py:279` needs `"scheduler"`) | probe + code |
| T7 | `@Value("${k:30}")` default dropped | probe; `VALUE_KEY_RE` `java.py:72` |
| T8 | `@Query` native SQL: table invisible to `table` and `search` | probe |
| T9 | Parameter annotations (`@PathVariable`, `@RequestBody`, `@Valid`) skipped | `java_decl.py:396` `_params` |
| T10 | Supertypes parsed (`JType.extends/implements`), not stored | grep finds no consumer in `java.py`/`resolve.py` |
| T11 | Join-building meaning is hard-coded: `SPRING_MAPPINGS`, JAX-RS `Path`+verbs, `Value`, `ConfigurationProperties`, `Table`, `Entity`, scheduling tuple, `@Subscribe`, `@FeignClient`, Retrofit, C# `Route`/verbs/`ApiController`/`NonAction`, Python `ROUTE_METHODS`/`TASK_DECORATORS` | `java.py:75-87,486-547,588-613`; `java_flow.py:102,367`; `csharp.py:39,134,261-272`; `python_io.py:30-33` |
| T12 | SQL helpers know CREATE/ALTER/INDEX/INSERT only (no SELECT/UPDATE/DELETE/MERGE) | `lang/data.py:24-29` |
| T13 | Python decorators reachable via `ast` with line spans; Python defines built in one place | `python_io.py:356`; `python_flow.py:151-167` |
| T14 | Scala extractor is regex-based, no annotation handling; Go extractor has no struct tags | `scala.py` (171 lines, 0 `@`), `go.py` |
| T15 | Leaf prompt shows type rows only (fqn, visibility, kind, line); 10k-token shrink loop | `prompts.py:55,98-125,264-275,409-416` |
| T16 | Patch schema: extraction never validated; leaves never write `defines`; `claimgate.py:75` strips them | code |
| T17 | Channel vocabulary already covers the joins (`http_out`, `event_subscribe`, `schedule`, `persist`, `read`) | `schema/patch-1.0.0.json` `$defs.channel` |
| T18 | Constant substitution exists for routes (`expand_placeholders`) | `resolve.py:398-424` |
| T19 | `@interface` declarations are define rows of kind `annotation` (meta-annotations possible) | `java_decl.py:260` |
| T20 | Per-member call facts exist (`uses` kind `call`, `from_symbol`) | `java_body.py:13,599` |
| T21 | sql-pool Java source is 2.9 MB | probe |

## 4. Data model

**Annotation row**, on every define row (`defines[].annotations`) and every parameter
(`defines[].params[].annotations`):

```json
{"name": "Every", "fqn": "de.spinscale.dropwizard.jobs.annotations.Every",
 "text": "@Every(jobName=\"AutoScaleJob\",misfirePolicy=Every.MisfirePolicy.NOW_WITH_REMAINING_COUNT,value=\"60s\")",
 "line": 15, "end_line": 18,
 "args": {"jobName": "AutoScaleJob", "value": "60s",
          "misfirePolicy": {"ref": "Every.MisfirePolicy.NOW_WITH_REMAINING_COUNT"}}}
```

- `text`: whitespace-normalised source, ≤ 400 chars (longer cut with `...`; lines hold the rest).
- `fqn`: resolved through the file's imports with the existing `_Resolver`; unresolved stays the simple name.
- `args`: single unnamed argument → key `value`. Values: string, number, bool, `{"ref": X}`
  (constant/enum), `{"class": X}` (`Foo.class`), list (`{a, b}`), nested annotation row,
  `{"concat": [...]}` (`BASE + "/x"`), `{"text": ...}` when unparseable.
- After resolve, refs to repo constants gain `"resolved": "/v1/servers"` in `xref` (T18).

**Other new fields on define rows**
- `supertypes`: `["...AbstractJob", "org.quartz.Job"]` for types (T10).
- `params`: `[{"name": "id", "type": "Long", "annotations": [...]}]` for methods (T9).

**New artifact**
- `code`: per-file source text of `source`-role files at the indexed commit, for code search (P12). ~3 MB for sql-pool.

**Unchanged:** database schema (all JSON in `snapshot_artifact.payload`), patch schema, claim shape, edge shape.

## 5. Phases

Each phase: steps → tests → exit check.

**Order of work** (decided 2026-10-12): Java and search first, then C#, then other languages.

| Stage | Phases | Notes |
|---|---|---|
| 1. Java + search | P1 (Java), P2 (Java), P3, P4, P5 (Java families), P6, P7, P12, P13 | P14 check on sql-pool after each phase |
| 2. C# | P1 C# steps (attributes on rows, parameter attributes, `using` resolution), P2 C# arguments, P5 C# family migration, C# rules, P13 | `Ann` line spans for C# already in place |
| 3. Other languages | P9 Python, P10 Scala, P11 Go, P13 | |

### P1 — Capture and the line-reader fix (Java in stage 1; C# steps in stage 2)
1. `lang/base.py`: `Ann`, `annotation_rows`, `mk_define(annotations=)` ✅ done.
2. `java_decl.py`, `csharp_decl.py`: record line spans ✅ done.
3. `java.py`, `csharp.py`: pass `anns` to every `mk_define` (types, methods, ctors, fields, constants, enum constants, record components).
4. `java_decl.py` `_params`: keep parameter annotations instead of skipping (T9); `csharp_decl.py` same **(to ground)**.
5. Store `supertypes` from `JType.extends/implements` (C#: base list) (T10).
6. `java.py` `_read_annotations`: read `@` tokens from `Tokens` — every annotation, any position; `_emit_repository_edges` uses the same list (T2–T4).
7. Annotation `fqn` via `_Resolver`; C# via `using` directives **(to ground)**.
- **Tests:** inline route prefix; inline `@Table`; 1-based lines on single- and multi-line annotations; parameter annotations; supertypes; C# attributes; annotation inside a string or comment is not captured.
- **Exit:** sql-pool rescan; diff of `routes`/`table`/`config` before vs after reviewed; only T3/T4-type corrections.

### P2 — Argument parsing
1. `lang/annotation_args.py` (new): token-level parser for Java/Scala element-value pairs and C# positional/named arguments into `args` (§4).
2. `resolve.py`: resolve `{"ref"}` and `{"concat"}` against the constant table with `expand_placeholders`; store `resolved` on `xref` sites.
3. `@Value`/`${k:default}`: default kept in `args` and surfaced by the `config` query as `default` (T7).
- **Tests:** every value shape in §4; constant from another file resolved; enum ref; nested `@Schedules({@Scheduled(..), @Scheduled(..)})`; text block `"""` in `@Query`; unparseable falls back to `text`.

### P3 — Query surfaces
1. `resolve.py` `_symbol_table`: copy `annotations`, `params`, `supertypes` onto sites.
2. `query/common.py`: one helper `annotations_of(store, fqn)` returning member + owner-class annotations.
3. `file`, `symbol`: each definition carries `annotations`, `class_annotations`, `params`.
4. `routes`, `table`, `config`, `trace` hops, claims: rows citing a symbol carry its annotations.
5. `search`: `annotations` bucket — matches name, fqn, text or arg values, whitespace ignored on both sides; row = `owner  @text  file:line-end`. `SEARCHED` lists it. Fair budget split gains a bucket.
6. `query/render.py`: text output shows them compactly.
7. `hook.py` `RECIPE`: schedules and annotation values → `search @Every` / `file <Class>`.
- **Tests:** each query shows annotations; `search @Every`, `search value = "60s"`, `search 60s` hit; budget split still reports true `counts`.
- **Exit:** sql-pool `search @Every` → 12 jobs (counted in source) with intervals and delays; `file AutoScaleJob`; output size before/after measured.

### P4 — Leaf prompt
1. `prompts.py` `_structure`: types with annotations, plus annotated members in scope with their parameter annotations.
2. `_structure_section`: `- Class#method L14-18: @Every(...)`; prompt-only noise filter (`Override`, `SuppressWarnings`, `Generated`); shrinks with `row_cap` inside the existing token loop.
3. `_task_section` and `.claude/agents/cdp-leaf.md`: annotations are verbatim source — cite their lines.
- **Tests:** prompt for a fixture jobs scope contains `@Every`; stays ≤ `max_prompt_tokens`; shrink order preserved.
- **Exit:** render the sql-pool `sql-pool-manager/jobs` leaf prompt and show it.

### P5 — Built-in rule table and migration (joins only)
1. `cdp/rules/*.json` (one file per framework family, shipped with CDP) and `cdp/rules.py` (loader, matcher, applier).
2. Rule shape:
```json
{"match": {"fqn": "org.springframework.web.bind.annotation.GetMapping", "on": "method"},
 "emit": {"channel": "http_in", "target": "route:GET {owner.RequestMapping.value}{value|path}"},
 "aliases": ["GetMapping"], "id": "spring.web.get"}
```
   Match by `fqn` first, simple-name `aliases` as fallback when imports are unresolved. Emit: channel + target template over `args`, owner-class annotations and resolved constants; or `sql` (P7).
3. `rules.apply(extraction, rules)`: post-pass after extract in `pipeline.py` and `refresh.py`, emitting edges in the existing shape, each tagged `"rule": "<id>"`. They are stored in a separate `extraction["rule_edges"]`, never in `io_edges`: `incremental_extract` carries `io_edges` forward per module, so rule edges mixed in would be carried *and* re-emitted (duplicates). Consumers read both through one accessor `all_edges(extraction)`; `rule_edges` is recomputed in full on every scan and refresh.
4. **Meta-annotations:** an annotation with no rule whose `@interface` definition (in the repo) carries ruled annotations inherits them (depth ≤ 3, cycle guard). Arguments come from the meta-annotation; Spring `@AliasFor` overrides are mapped when the alias is declared in the repo **(to ground)**.
5. **Inheritance:** route and client annotations on an interface or superclass apply to implementations through `supertypes`, per a rule flag.
6. **Migration:** move every T11 rule into the table, one family per commit; the gate for each commit is goldens byte-identical (only P1 corrections excepted). Python router-prefix logic stays in code (call-based, not annotation-based) **(to ground)**.
- **Tests:** rule matcher (fqn vs alias, collision of same simple name); template expansion; meta-annotation; inheritance; goldens identical after each migration commit.

### P6 — New join rules
- **Scheduling (values in claims):** Spring `@Scheduled(cron|fixedRate|fixedDelay|initialDelay)`, `@Schedules`; dropwizard-jobs `@Every`, `@On`, `@DelayStart`, `@OnApplicationStart/Stop`; Jakarta `@Schedule`; Quarkus `@Scheduled(every|cron)`; Micronaut `@Scheduled`; Quartz markers. Claim: "AutoScaleJob runs every 60s after a 50s start delay (misfire NOW_WITH_REMAINING_COUNT, no concurrent runs)", evidence = annotation lines + class line. Fixes T6.
- **Messaging:** `@KafkaListener(topics)`, `@JmsListener(destination)`, `@RabbitListener(queues)`, `@SqsListener`, `@StreamListener`, `@EventListener` → `event_subscribe`; `KafkaTemplate`-style sends stay in code.
- **HTTP clients:** `@HttpExchange`/`@GetExchange`… (Spring interface clients), `@FeignClient` (migrated), Retrofit (migrated), MicroProfile `@RegisterRestClient` → `http_out`.
- **Web parameters:** `@PathVariable`, `@RequestParam`, `@RequestBody`, `@RequestHeader`, JAX-RS `@PathParam`/`@QueryParam`, C# `[FromBody]` → route rows list their inputs.
- **No rule (shown verbatim, agent interprets):** `@Transactional`, `@RolesAllowed`, `@PreAuthorize`, `@Cacheable`, `@Async`, `@Retryable`, `@Valid`, `@PostConstruct`, `@Profile`, `@ConditionalOn*`, custom annotations.
- **Tests:** one fixture per family; sql-pool schedule claims carry intervals.

### P7 — SQL in annotations
1. `lang/data.py`: add SELECT/FROM/JOIN, UPDATE, DELETE FROM, MERGE INTO patterns (T12); shared `sql_tables(text) -> [(table, read|write)]`.
2. Rule `emit.sql`: `@Query(value, nativeQuery)`, `@NamedQuery(query)`, `@NamedNativeQuery`, JDBI `@SqlQuery`/`@SqlUpdate`, MyBatis `@Select`/`@Insert`/`@Update`/`@Delete`.
3. Native SQL → `table:` edges; JPQL → `entity:` edges, which the existing entity→table mapping turns into tables.
- **Tests:** native DELETE → writer; JPQL SELECT → reader via entity; `${schema}` placeholders; text blocks.
- **Exit:** sql-pool `table` diff reviewed.

### P8 — (removed)
Rule-gap reports, leaf rule proposals, a `cdp rules` command and team rule files were dropped:
an annotation with no rule is still captured, cited and searchable, and the agent reads it.

### P9 — Python decorators
1. `python_flow.py` `define`: `annotations` from `node.decorator_list` via `ast.unparse`, `lineno/end_lineno`, `args` from `ast` literals/names.
2. Migrate `TASK_DECORATORS` and decorator-name triggers to rules; add Celery `@app.task`, APScheduler `@scheduled_job("interval", minutes=5)`.

### P10 — Scala annotations
Tokenise with the Java `Tokens` **(to ground: Scala syntax coverage)**; attach annotations to the regex-found defines in `scala.py`.

### P11 — Go struct tags
`go.py`: struct field tags (`json:"id" db:"id" gorm:"column:id"`) as annotation rows on fields; rules for `db`/`gorm` → table columns **(to ground)**.

### P12 — Method bodies
1. `code` artifact: source text of `source`-role files at the indexed commit.
2. `search` gains a `code` bucket: substring match inside member bodies, cited `owner file:line` — replaces grep for literals, log messages, inline SQL. Plain scan, same on SQLite and Postgres; no search index for now.
3. `file`/`symbol`: per member `calls` (from T20), `throws`, and literal count; `trace` unchanged.
4. Leaf prompt: no body text (digest mode already covers it).
- **Tests:** literal inside a method found and cited to the member; comment text found; dirty-tree caveat stated in `as_of`.
- **Exit:** search latency on sql-pool measured and reported.

### P13 — Documentation (commands and README only)
- `guide_kinds.py`: `file`, `symbol`, `search`, `routes`, `table`, `config`, `trace` describe annotations, parameters, supertypes and code search.
- Regenerate from it: `SKILL.md`, `docs/CDP_REFERENCE.md`, the MCP `cdp_query` schema, `cdp help`, and the `README.md` command table (`scripts/gen_guide.py`, `scripts/gen_readme.py`; `--check` passes).
- Done once per stage, after its phases.

### P14 — Verification (every phase, final sweep)
Fixture goldens reviewed and re-blessed per phase; full suite green; sql-pool dropped and rebuilt;
report shows: `search @Every`, `file AutoScaleJob`, `table pool_config`, native-SQL table writers,
routes/table/config diffs, schedule claims with values, leaf prompt, index size and query
latency before/after.

## 6. Adversarial cases (each becomes a test)

Annotation in a comment or string literal; fully qualified `@org.x.Y`; same simple name from two
packages; repeated annotations; nested annotation arrays; constant concatenation in arguments;
text blocks; annotations on parameters, record components, enum constants, `package-info.java`;
type-use annotations (`List<@NonNull String>`) — captured on the type, not as declaration
annotations; Lombok-generated members (not in source — annotations captured, members not
invented); overloaded methods sharing an fqn; inherited annotations through interfaces;
meta-annotation cycles; a 2,000-char `@Query`; a file with 500 annotated fields; a deleted
method, an edited argument, a renamed file across refresh.

## 7. Decisions (settled 2026-10-12)

1. **No team rule files.** Built-in join rules only; the agent interprets everything else.
2. **No behaviour labels (facets).** Annotations are shown verbatim; the agent derives meaning.
3. **No search index.** Plain scan now; revisit with measurements when scale demands it.
4. **Order:** Java + search first, then C#, then Python/Scala/Go (§5).
5. **Documentation:** command docs and README only, generated from `guide_kinds.py`.

## 8. Risks

- **Output size:** measured at P3/P12 exits; budget caps rows, not row length — may need a compact mode.
- **Migration drift:** P5 gate is byte-identical goldens per family; any difference is reviewed, not re-blessed blindly. Route extraction has context the table must express (Feign/Retrofit interfaces emit no routes, constant paths, class prefixes); a family that cannot reach identical goldens stays in code and is listed, rather than forced.
- **Edge duplication on refresh:** prevented by keeping rule output in `rule_edges` (P5.3); covered by the incremental-equals-full test.
- **Rule mistakes publish wrong facts:** each rule has an id carried on its edges, so a bad rule is traceable and removable.
- **Index growth:** `code` artifact ~ source size (2.9 MB for sql-pool) plus annotations; measured.
