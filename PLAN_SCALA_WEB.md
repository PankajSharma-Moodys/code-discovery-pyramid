# Plan: bring Scala and Web (JS/TS) up to the Java/C# standard (budget: 110 lines)

## Context
Scanning `~/git/workflow-service` @ d6b7b5d (1332 `.scala`, 182 `.js` in `workflow-ui`) missed its Scala
endpoints, JDBI SQL, Quartz jobs, and the UI's API calls. Java (`lang/java*.py`) and C# (`lang/csharp*.py`),
~2.9k lines each, are the reference. Scala (`lang/scala.py`, 171 lines, 6 tests) and Web (`lang/web.py`, 166
lines, no test file) are regex sketches. Goal: same fact types and row shapes, so rules, resolve, dataflow,
link and docs work. Supersedes `PLAN_SCALA.md`. Counts exclude tests; (unverified) = not yet measured.

**"Web" = `cdp/lang/web.py`** (`.js .jsx .mjs .cjs .ts .tsx .mts .cts`; Node and browser alike). Today: imports,
regex declarations, Express/Nest literal routes, `process.env.X`, `fetch/axios/got/superagent('<literal>')`.

## Baseline (stored scan + `cdp link scan`, 2 snapshots / 62 modules)
- Java: 43 real `route:` edges. Scala: 0 (44 `library:jakarta.ws.rs` hints only).
- Link scan: 171 links (30 distinct), all `persist`/`event_publish`; **0 HTTP**. UI: 2 placeholder `http_out` edges.

## What the golden standard covers vs Scala / Web
| # | Capability (Java / C# implementation) | Scala today | Web today | Size in workflow-service |
|---|---|---|---|---|
| 1 | Token parser; all members, any access, with extents (`java_decl`, `csharp_decl`) | class/object/trait only | regex decls | 3139 `def` |
| 2 | Annotations parsed to structured args (`lang/annotation_args.py`) | none | none | routes/jobs/SQL depend on it |
| 3 | Rules `rules/*.json`: JAX-RS, Spring Web, JPA, JDBI/MyBatis/Spring-Data SQL, Kafka/JMS/Rabbit/SQS, scheduling, `@Value`, HTTP clients | gated off (`rules.py:173,181,572,579,661,668`) | n/a | 48 JAX-RS verbs, 20 `@Sql*`, 15 `@Every/@On` |
| 4 | Inbound routes, class+method join, constants + context path (`resolve.py`) | 0 `route:` | Express/Nest literals | 48 |
| 5 | Call graph; chains settled by `java_types.py`/`csharp_types.py` | none | none | flow questions |
| 6 | Outbound HTTP (`java_flow`, `csharp_http`) -> `link` | none | literal URL only | 1 WebTarget; 21 UI call sites |
| 7 | Config reads in bodies (`java_config`, `csharp_config`) | none | `process.env` | 7 `sys.env/getenv/getProperty` |
| 8 | Persistence: repos/entities -> `persist/read`, SQL -> `table:` | none | n/a | JDBI DAOs (unverified count) |
| 9 | Events publish/subscribe (`java_flow` + messaging rules) | none | none | 1 Pusher subscription (UI) |
| 10 | Schedule values (`schedfacts.py`, java-gated at `:129`) | none | n/a | 15 |
| 11 | `main` -> `process_boundary`; DI signals `di:*` | none | none | 22 `def main`/`extends App`, 117 `@Inject()` |

`rules.TYPE_KINDS` (`rules.py:61`) fits A2's kinds; resolve needs no gate (non-`.cs` -> Java `TypeIndex`, `resolve.py:299`).

## Part A: Scala (JVM annotations are Java's, so mirror the Java pipeline)
A1. **Tokens**: `lang/scala_tokens.py`, modelled on `java_tokens.py`. Adds triple-quoted strings (+ `s"`/`f"`),
    backtick identifiers, `[` `]` generics. Reuse `java_tokens` if a probe shows a flag is enough.
A2. **Declarations**: `lang/scala_decl.py` (like `java_decl`). Covers package (also nested `package a { }`);
    class / case class / object / trait / enum; constructor params as fields; `def`/`val`/`var` at any
    visibility (`private[x]`); extents; `extends A with B` -> supers. Kinds: trait -> `interface`,
    object -> `class` + `object: true`. `final val X = "..."` -> `constant` with `value`, which the
    route constant table (`resolve._constant_table`) needs.
A3. **Annotations**: emit rows in `lang/annotation_args.py`'s shape. Normalise `Array(a,b)` -> list,
    `classOf[T]` -> `{"class": T}`, `k = v`, `new Ann(..)` -> nested row, `class X @Inject() (..)` as
    the constructor annotation. Method `@Path` follows the verb (`WorkflowResourceV2.scala:127-128`).
A4. **Open the gates**: each `rules/*.json` family has a single `"language": "java"` string (defaulted `rules.py:111`,
    compared `:173,661`). Change the schema to a `languages` list (string still accepted), add `scala` to jaxrs,
    scheduling, sql_annotations, messaging, http_clients, config; make `rules.py` and `schedfacts.py:129`
    accept `JVM_LANGS`.
A5. **Context path**: `resolve.py:498` adds `server.applicationContextPath` only for `.java`; accept `.scala`
    too (execution-api states `/workflow-service`).
A6. **Body facts** (`lang/scala_flow.py`, like `java_flow` + `java_config`): `sys.env`, `System.getenv/getProperty`
    -> `config_read`; JAX-RS `target(..).request().get()` -> `http_out`; `def main`/`extends App` -> `process_boundary`; `@Inject` -> `di:`.
A7. JDBI SQL: triple-quoted + `.stripMargin` text into table extraction (`rules.py:67`).
A8. **Call graph** (`lang/scala_body.py`, Java `TypeIndex`): receivers typed from declared types; an untyped
    `val x = foo()` becomes a chain; an untypable call is dropped. Done last, measured alone.

## Part B: Web (JS/TS)
B1. **Declarations**: top level and class members only (class-field arrows `name = (..) =>`, methods, `export
    default`, React components). Sample the 1357 UI `constant` defines first; whether they're locals is unverified.
B2. **Outbound HTTP through wrappers** (in-file): learn `fn(path) => axios.VERB(\`${base}/${path}\`)` and resolve
    its 20 call sites (19 GET, 1 DELETE) plus 6 `smlUrl` calls. 6 of the 20 pass a local, so follow
    single-assignment locals in the calling function. Read multi-line call arguments
    (`axios.post(\n \`${this.baseUrl}/v1/login\``). Drop the wrapper's own placeholder edge.
B3. **Routes**: keep Express/Nest. Add React Router `<Route path>` (24 elements, 17 distinct edges; nesting joined via `rules.join_route`)
    as a new `ui_route` channel (none exists in `cdp/` today; check downstream tolerates it). Link scan ignores it.
B4. **Events**: `new Pusher(..)` + `.subscribe('ch')` / `.bind('Evt')` -> `event_subscribe`. It only links if the
    server's Pusher trigger is emitted as `event_publish` with the same name (Java extractor, optional).
B5. **Calls across modules** (lightweight): `import X from './service/WorkflowService'` + `X.m(` -> `uses`
    `kind: "call"`, so a path runs page -> service -> backend route.

## Part C: link scan (`link.py`, `linkroute.py`: match `dataflow.edges` by channel; no language gate)
Measured with real `link.scan_links` on the real dataflow plus 48 Scala routes and 21 UI calls built from source
(expected A+B2 output). Today's rule links 6 of 15 `${this.baseUrl}` calls.
C1. **`linkroute.py` suffix rule**: a client path missing the server's context prefix needs >= 2 informative
    segments (`v1` doesn't count), so `/v1/consumptions`, `/v3/tenants/{id}`, `DELETE /v2/workflows/{id}`,
    `/v2/workflows?..`, `POST /v1/login` miss real routes. Lowering it to >= 1 when the outbound path starts
    with a `${base}` variable, plus a literal-first-segment guard: live 10 -> 19 UI links, `heuristic`. False-link risk elsewhere unmeasured.
C2. Expected misses: `/v2/workflows/{id}/graph`, `/logs` (no route here); `smlUrl` (external).
C3. Fix stale `link.py:31` docstring: `java_flow` does emit topic-specific event edges.

## Out of scope
Akka-HTTP/Play/http4s (0 files here), Scala type inference beyond declared types, JDBI fluent
`handle.createQuery` (Java skips it too), a full JS/TS parser.

## Verification
- Unit fixtures per matrix row; `python -m pytest tests/`. `minirepo` has no Scala/JS, so `FixtureGoldenTest`
  must stay unchanged; the target-repo golden (`make golden`) is reviewed once after merge.
- **Live re-scan of `~/git/workflow-service`**, counted from `extract`/`dataflow`:
  - Scala: 48 `route:` with `/workflow-service` prefix (hand-check `UserResource`, `WorkflowResourceV2`,
    `SchedulerResources`); 15 scheduled symbols with intervals; `table:` edges from the 20 `@Sql*`; call rows > 0.
  - Web: 26 resolved UI `http:` edges (20 baseUrl + 6 smlUrl) + `/v1/login`; 17 `ui_route`; 1 Pusher subscription.
  - `cdp link scan`: >= 13 UI -> route HTTP links, hand-checked. All 171 baseline links kept (measured: 459 total, 19 UI).
    `unified-store#sql-pool` re-run: C1 adds no false links. Java-sourced edges identical per channel (measured).
  - D1/D2 tests: a patch citing a shown site whose text changed is rejected; refresh decays a link whose call moved.

## Part D: link grounding (from reading `link.py`, `linkid.py`, `commands/link/collect.py`)
D1. **Re-read the cited line**: `validate_task_patch` (`link.py:476`) only checks that the model's citation is one
    of the sites it was shown. It never reads the source (`link.py:581-585`). Each link end already carries its
    anchor text (`anchor.anchor`); check it with `anchor.verify_anchor` against the file at the snapshot's
    `head`, not the working tree. Reject if not found; store the corrected line it returns. How to reach source at
    `head` is unverified (`snapshot_checkout` table is the candidate).
D2. **Refresh keys on the symbol**: `_still_present` (`link.py:699`) matches (repo, module, channel, normalised
    target), so a link survives when any edge with that target remains. Add the end's `node` (symbol). A
    call site moved to another method -> `decayed`, with the reason "symbol no longer has this edge".
Lanes A-C are merged into the working tree (uncommitted); open work is tracked in `PENDING.md`.

## Golden rule (binds every subagent)
Ground before you act: read the real file and run the real command before stating or coding any fact; no
assumptions. Cite `file:line`, mark unchecked items "unverified", report a missed target instead of working
around it, and run the Java/C# regression tests before reporting done.
