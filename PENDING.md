# Pending: Scala/Web/link work (budget: 60 lines)

State: all of `PLAN_SCALA_WEB.md` A-C is in the working tree, **uncommitted**. Sources: the 2026-10-14 review
(fresh scan of `~/git/workflow-service` @ d6b7b5d vs stored baseline; full suite; two independent reviews,
top findings reproduced). "(unverified)" = reported by a reviewer, not reproduced.

## 1. Blockers before commit
- [x] **Vendored copy drift**: `.claude/skills/cdp/` lacks all 26 changed/new files, so the skill and `cdp_query`
      still run the old extractors; `test_vendored_copy_is_byte_identical` fails. Fix: `cdp install --self`.
- [x] **Wrong `primary` (Scala)**: when `object X {..}` precedes `class X`, a member becomes the file's primary type
      (`lang/scala.py:50`, takes `decls[0]`). 43/1332 files (Java 0/679). 12 Quartz jobs get a constant as the
      `schedule.every` target (`CleanupJob.scala:18` -> `CleanupJob.CleanupJobName`).
- [x] **Self-type drops members**: `trait T { self: Foo =>` swallows the body (`lang/scala_decl.py:113-119`).
      Real case: `BaseWorkflowService.scala` emits only the type.
- [x] **For-comprehension false calls**: `for { f <- xs } yield f.bar()` resolves `f` to the outer field
      (`lang/scala_body.py:66-90`).
- [x] **Nested block comments**: `/* /* */ */` hides the code after it (`lang/scala_tokens.py:23`).
- [x] **Gate tests don't test Scala**: `tests/test_jvm_gates.py` relabels Java extractor output as Scala. Add
      tests that run `ScalaExtractor` rows through `rules.apply` and `schedfacts`.

## 2. Latent bugs (all grounded 2026-10-14: each reproduced with a snippet through the real extractor)
Fixed: Scala `.stripMargin` annotations, lambda/`case` scope leak, Web JSX apostrophe, Pusher `.bind(this, x)` +
literal `.subscribe`, regex after `return`/`typeof`/`case`.., test files emitting `ui_route` (live: 17 -> 16 edges).
- [x] Scala: an untyped `val x = new T(..)` (field or local) now takes type T (`scala_decl.new_type`, `_dry`). Frozen
      corpus: +108 call rows, 0 removed; 12 rows read against source, all correct. The earlier "970 sites" counted
      every `new T` initializer, mostly locals (43 are class-level). Builder chains (`new B()` + leading `.m()`) stay untyped.
- [ ] Scala `Util("x")` on a pure `object` resolves to the type, not `apply` (`jtypes.py:201-203`; no `#<init>` define for
      objects, `scala_decl.py:307`). Grounded: 2 rows move (`StringToMillis` at `AbstractJob.scala:62`, `HeartBeat.scala:21`);
      26 more hit companions with both `<init>` and `apply` (undecidable by name). Fix ~4 lines, gate on `.scala`. Later.
- [ ] Scala class/object-body statements emit no calls (`scala_decl.py:487-490`). Grounded: 2640 statements / 380 files, 8
      in 5 production files (`setShowStacks(false)`, `executorService.submit(..)`), the rest ScalaTest DSL. Simulated fix (~10
      lines, `<init>`/`<clinit>` owner): +5 production rows but +36k test rows (3x). Gate to non-test files first. Later.
- [ ] Scala ignore: `val A, B = Value` gives bogus value/type uses (names are right); unterminated `s"` with many `${}`
      holes backtracks ~2x per hole (24 holes = 9.7s; only on non-compiling input; guard is one line, `_HOLE`
      `scala_tokens.py:18-25`); nesting > 8 (0 files); unbraced `val g = x => x` keeps `x` bound (0 sites).
- [ ] Web ignore (0 occurrences in workflow-ui): paren-less wrapper `path => axios.get(..)` not learned; `+=`,
      ternary-head and same-line locals drop the call; named-object import drops the object name; generic arrows are
      `constant` not `method`; `@Input()` fields undeclared.
- Namespace risk: THEORETICAL. Links pair on an exact string (`link.py:136-163`); only a bare-name `event_publish` could
  falsely match a Web `event:<name>` (reproduced synthetically); none exists. Before adding a Pusher `trigger`
  extractor, namespace Web edges (`channel:<n>`, `pusher_event:<n>`).

## 3. Link grounding (planned: `PLAN_SCALA_WEB.md` Part D)
- [ ] D1: `validate_task_patch` re-reads the cited line with `anchor.verify_anchor` at the snapshot's `head`.
- [ ] D2: refresh's `_still_present` also keys on the end's symbol.

## 4. Verification still open
- [ ] C1 false-link risk on a repo that really has `${base}` calls to several services (only a synthetic probe so far).
- [ ] The 19 UI->Scala links are all `heuristic` and only hand-checked. `link prompts` yields 19 tasks; resolving
      them costs one model call each (`link run --runner-cmd` or leaf agents). Not run.
- [x] Scala `event_subscribe` 12/12 (class name within 3 lines of the anchor) and the 35 non-library `schedule` edges
      (each on an annotation/`extends` line) checked against source; 23 more are `library:` import hints, as in Java.
- [x] Hand-check of Scala routes: all 48 match source (trailing `/` on `/v1/config/`, `/v1/login/` as in Java).

## 5. Housekeeping
- [x] Committed on `feature/imporvements` as 8aa35ba and a second commit for the step-2 fixes.
- [x] All scratch worktrees and branches (lane/*, fix/*, fix2/*) removed. Commits: 8aa35ba, then the step-2 fixes.
- [ ] Headline numbers to quote: links 30 -> 62 distinct (+19 HTTP, +13 persist), not 171 -> 459 rows.
