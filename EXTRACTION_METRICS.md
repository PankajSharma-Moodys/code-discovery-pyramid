# EXTRACTION_METRICS: what every extractor must produce, and how to score it

Budget: ≤ 200 lines. Audience: agents doing the scoring. Read all of it before starting.

## 0. Rules for the agent doing the scoring

1. Your job is to **measure**. Do not change any extractor, rule, or file in this repo.
2. The repos in `~/git` are **read-only**. Do not write inside them. Do not run their code or build tools.
3. Score **only** what this document defines. If something is unclear, stop and ask. Do not guess.
4. Every number you report must come from something you actually ran. Say how you got it.
5. Section 8 records the owner's decisions. Follow them exactly.

## 1. Words used in this document

| Word | Meaning |
|---|---|
| **file facts** | What the extractor returns for one file: `defines`, `uses`, `imports`, `io_edges`. |
| **define** | One declared thing (a type, method, field, constant). A dict with at least `fqn`, `kind`, `visibility`, `anchor`. |
| **type define** | A define whose `kind` is **not** `method`, `function`, `field`, `constant`, or `table`. |
| **use** | One reference from code to a symbol. A dict with at least `fqn`, `resolved`, `via_import`, `anchor`. |
| **edge** | One dict in `io_edges` or `rule_edges`, with `source`, `target`, `channel`, `anchor`. |
| **anchor** | The citation: `{"file", "line", "anchor"}`. `line` is **1-based**. |
| **present** | The source code contains the thing (decided by the "Present when" rule). |
| **emitted** | The file facts contain it in the exact shape given (decided by the "Emitted when" rule). |
| **production file** | A file whose inventory `role` is `source`. Test files are never scored (section 8). For the coverage rows (S, G, M, R, U, F) JS files that are minified or bundled are also not scored: basename `*.min.{js,mjs,cjs}`; a `bundle` word in the basename; `X.dev.js` with a sibling `X.min.js`; or a build-hash suffix (`name.<8+ hex with a digit>`, `name-<8 base64url chars>`) under a `static`/`assets`/`dist`/`build`/`vendor` directory. H rows keep all files (section 8, item 5). |

## 2. Where the facts come from

- **Corpus:** `~/git/data-lake`, `~/git/unified-store`, `~/git/workflow-service`.
- **Get the facts the same way a real scan does:**
  1. `cdp.inventory.build_inventory(repo)`
  2. `cdp.extract.run_extract(repo, inventory)`
  3. `cdp.rules.apply(extraction, repo=repo)`

  Framework edges are in `io_edges` **plus** `rule_edges` together.
- **Resolution status** (`resolved` on a use) is set only by the later resolve phase. Score H3 from a scan's stored result, not from raw extraction.
- **Language of a file:** the inventory's `language` field. Columns: `java`, `csharp`, `scala`, `python`, `typescript`, `javascript`.

## 3. How to score

- **Coverage % = emitted ÷ present × 100**, per fact, per language. Count over all production files of that language in all three repos.
- **Each cell holds exactly one value:**
  - a **%**, with the counts behind it, e.g. `92% (460/500)`
  - **N/A**: the language has no such construct (listed in the "Applies to" column)
  - **0 present**: the construct exists in the language but never occurs in the corpus
- **Pass marks (confirmed):** ≥ 95% for S, G, M, R, U facts and ≥ 90% for F facts.
- **Present rules are text checks.** They will sometimes be wrong. For each fact, list up to 5 example misses with `file:line` so a person can check them.

## 4. Code facts

**S1 Type declarations.**
- Present: a line declares a type with a keyword:
  - Java: `class`, `interface`, `enum`, `record`
  - C#: `class`, `interface`, `enum`, `record`, `struct`
  - Scala: `class`, `trait`, `object`, `enum`
  - Python: `class`
  - TS/JS: `class`, `interface`, `enum`
- Emitted: a type define exists whose `anchor.line` is that line.
- Applies to: all.

**S2 Members.**
- Present: a method, function, field, or constant is declared.
- Emitted: a define with `kind` `method`, `function`, `field`, or `constant`, anchored on that line.
- Applies to: all.

**S3 Span.**
- Present: every type define and method/function define.
- Emitted: the define has `end_line` (integer, ≥ `anchor.line`).
- Applies to: all.

**S4 Canonical name.**
- Present: every define.
- Emitted: `fqn` starts with the file's declared package or namespace. Members use `#` (`pkg.Type#method`) and fields use `.` (`pkg.Type.field`). The file path is not the package unless the language has no package keyword.
- Applies to: all.

**G1 Params.**
- Present: a method/function define whose declaration has at least one parameter. Do not count Python's `self` and `cls`.
- Emitted: the define has `params`, a list with one dict per parameter. Each dict has `name` (string) and `type` (string or absent when the source has no type). It also has `annotations` when the parameter has any.
- A count-only field such as `pmax` does **not** count as emitted.
- Applies to: all.

**G2 Return type.**
- Present: the method declares a return type. Python counts only with `->`; TS only with `): Type`; JS is N/A.
- Emitted: the define has `ret` (string). A `void` return is the sentinel `<none>` (owner decision 2026-10-28); primitives and builtins such as `String` are emitted as written. Constructors have no return type and are not counted. C#: `string`, `int`, `bool` and other predefined types are emitted as written; nullable `T?` is emitted as `T`; destructors and operators are not counted.
- Not scored: C# properties (never members) and Python properties (`@property`, `@x.setter/.getter/.deleter`, `@[functools.]cached_property`); the extractor emits `ftype` for them, so they are excluded from G2 and G3 and only counted in `csharp_properties_present_not_scored` / `python_properties_present_not_scored`.
- Applies to: Java, C#, Scala, Python, TS.

**G3 Field type.**
- Present: the field declares a type.
- Emitted: the define has `ftype` (string).
- C# fields, constants and record parameters carry `ftype`; predefined types (`string`, `int`) are emitted as written.
- Applies to: Java, C#, Scala, Python (annotated only), TS.

**G4 Visibility.**
- Present: every define.
- Emitted: `visibility` is one of `public`, `protected`, `internal`, `package`, `private`.
- Applies to: all.

**M1 Annotations.**
- Present: annotation lines directly above the declaration, or at the start of its line:
  - Java/Scala: `@Name`
  - C#: `[Name]`, where `[A, B]` counts as 2
  - Python/TS: `@decorator`
- Emitted: the define's `annotations` list has one dict per annotation, with `name`, `text`, `line`, `end_line`. Score as `min(emitted, present)` per define.
- Parameter annotations are scored inside G1.
- Applies to: Java, C#, Scala, Python, TS. JS is N/A.

**M2 Annotation args.**
- Present: an emitted annotation whose `text` contains `(`.
- Emitted: it also has `args` (dict).
- Applies to: as M1.

**M3 Annotation full name.**
- Present: every emitted annotation.
- Emitted: it has `fqn`.
- Report the % without a pass mark: unresolvable names are allowed.
- Applies to: as M1.

**R1 Supertypes.**
- Present: the type declaration names a base type:
  - Java/TS: `extends` or `implements`
  - Scala: `extends` or `with`
  - C#: `class X : Base`
  - Python: `class X(Base)`, not `(object)`
  - JS: `extends`
- Emitted: the type define has `supertypes`, a non-empty list of strings.
- Applies to: all.

**R2 Extends vs implements.**
- Present: a define that passes R1.
- Emitted: each base type is marked as class or interface. **This field does not exist yet in any language.** Report "not emitted anywhere" until it is added.
- Applies to: Java, C#, Scala, TS. Python and JS are N/A.

**R3 Imports.**
- Present: an import line:
  - Java/Scala: `import`
  - C#: `using X;`
  - Python: `import` or `from … import`
  - TS/JS: `import`
- Emitted: an entry in `imports` with that `line`.
- Applies to: all.

**U1 Type uses.**
- No text check. Report uses with `kind` = `type` per 1,000 lines of code. There is no pass mark; this is used to compare languages.
- Applies to: all.

**U2 Call uses.**
- No text check. Report calls per 1,000 lines of code, and the % of uses with `kind` = `call` that have `from_symbol`. The pass mark applies to the `from_symbol` %.
- Applies to: all.

**U3 Receiver typing.**
- Present: a call use whose receiver is a field or parameter with a declared type in the same file.
- Emitted: the use's `fqn` is `<that type's fqn>#<method>`.
- Measure by checking 50 random such calls per language by hand, listing each `file:line`.
- Applies to: Java, C#, Scala, TS. Python only when annotated.

**U4 Constant folding.**
- Present: an HTTP client call or SQL call whose URL/SQL argument is built from a constant plus something else, e.g. `URL + id`.
- Emitted: the edge `target` contains the constant's value, with `{}` for the unknown parts (e.g. `http:GET /orders{}`).
- Measure by checking 20 such calls per language by hand.
- Applies to: all.

## 5. Framework facts

- **Present:** the markers listed below appear in production code.
- **Emitted:** an edge with that `channel` whose `source` is the method or class carrying the marker, anchored on the marker's line or the declaration's line.
- **Scoring is per framework**, not per language. Each row below is a separate line in the report.
- **A framework counts as covered by three kinds of input:** an annotation, a call (with its arguments), or a supertype.

| ID | Channel and exact target format | Framework: present when |
|---|---|---|
| F1 | `http_in`, target `route:<VERB> <full path>`. The full path includes the class-level prefix. | JAX-RS (Java and Scala): `@GET`/`@POST`/`@PUT`/`@DELETE`/`@PATCH` on a method. Spring MVC: `@GetMapping` etc. or `@RequestMapping`. ASP.NET: `[HttpGet]` etc. Django: `path(` / `re_path(` in `urls.py`. FastAPI: `@<router>.get(` etc. Flask: `@app.route(` or `@<blueprint>.route(` with a string path (verbs from `methods=[...]`, default GET), and the Flask 2.0 shortcuts `@app.get(` / `@bp.post(` etc. with a string path. Express: `app.get(` / `router.get(` etc. with a string path. |
| F2 | `http_out`, target `http:<VERB> <url>` | C# `HttpClient.GetAsync`/`PostAsync`/`SendAsync`. JAX-RS client `.target(...)`. TS `axios.get` etc. and `fetch(`. |
| F3 | `persist` (any target) | JPA `@Entity`/`@Table`. Spring Data `extends JpaRepository`/`CrudRepository`. JDBI `@SqlQuery`/`@SqlUpdate` (Java and Scala). EF Core `: DbContext` and `DbSet<T>`. Django `models.Model`. SQLAlchemy `declarative_base`/`Column(`. |
| F4 | `schedule` (any target) | Dropwizard Jobs `@Every`/`@On`/`@OnApplicationStart`. Quartz `implements Job`. Hangfire `RecurringJob.`/`BackgroundJob.`. `: BackgroundService` / `IHostedService`. |
| F5 | DI (signal `di:<Name>` on the file, or an injection edge) | Spring `@Component`/`@Service`/`@Repository`/`@Autowired`. `@Inject` (javax/jakarta). MS DI `AddScoped<`/`AddSingleton<`/`AddTransient<`. |
| F6 | `config_read` (any target) | Dropwizard `Configuration` getters. C# `IConfiguration[...]` / `GetSection(` / `GetValue<`. Typesafe `config.getString(` etc. |
| F7 | Swagger/OpenAPI: the route's method define has the `io.swagger` annotations in `annotations` | `@Operation`, `@ApiResponse`, `@Tag`, `@Schema` (Java and Scala). |

## 6. Health metrics

- **H1 Errors:** notes starting `extractor_error` per 1,000 production files. Target 0.
- **H2 Speed:** thousands of lines per second for the whole extraction step (wall clock) per repo. Target: no regression.
- **H3 Resolution:** from a stored scan, the % of `call` and `type` uses whose `resolved` is `local` or `matched`. Also report the `third_party`, `ambiguous` and `unresolved` %.
- **H4 Classification:** for every `.java .cs .scala .py .ts .tsx .js` file, check that the inventory `language` matches the extension. TS/TSX files must be `typescript`. Also check that `role` = `source` vs `test` follows the project's rule: every file under a test project is a test. Report mismatches with paths.

## 7. Report format

1. One markdown table. Rows = fact IDs (S1…H4, plus one row per framework for F). Columns = `java | csharp | scala | python | typescript | javascript`.
2. Each cell is `NN% (emitted/present)`, `N/A`, or `0 present`. Mark cells below the pass mark with ❌.
3. Under the table: for each ❌ cell, up to 5 example `file:line` misses.
4. A short section listing how each number was produced.
5. No recommendations. Measurement only.

## 8. Owner decisions (2026-10-23)

1. **Classification (H4) is fixed later, during language support.** Until then, mark the `python`,
   `typescript` and `javascript` columns **provisional**: `.ts`/`.tsx` were seen labelled `javascript`,
   and only 3 Python files counted as production code.
2. **Tests stay test.** Score production files only (`role` = `source`).
3. **Pass marks confirmed:** 95% for S, G, M, R, U facts and 90% for F facts.
4. **Scope:** Java, C#, Scala, Python, TS/JS. Go and Kotlin are out until a repo needs them.
5. **Minified and bundled JS is not scored by coverage rows** (owner decision 2026-10-26, D4). The file-name rule is in the
   'production file' row of section 1; H1-H4 still count every production file.
