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

## 2. Should fix (latent; none occur in workflow-ui)
- [x] Scala: `@SqlQuery("""..""".stripMargin)` on an annotation yields no `table:` edge (`scala_annotations.py` `_value`
      ~130-146 returns `{"text"}`; only `scala_emit.py:169` handles `.stripMargin`). 0 of 20 `@Sql*` sites here use it.
      Fixed: `_value` peels a trailing `.stripMargin`/`.trim`; tests in `tests/test_scala_gates.py`.
- [x] Scala: a lambda param or `case x:` binder stayed bound after its body (`scala_body.py`). Fixed (`_open_body`);
      0 rows changed on workflow-service. Open: an unbraced `val g = x => x` still binds to block end.
- [ ] Scala: nested block comments deeper than 8 levels are not handled (`scala_tokens.py:20-24`).
- [x] Web: an apostrophe in JSX text (`Don't`) dropped later class members. Fixed (JSX-aware lexer, `web_scan.py:71-124`).
- [x] Web: `.bind(this, x)` emitted `event:${this}`; literal `.subscribe('ch')` is now emitted (plan B4). Fixed in
      `web_flow.py`. Open: channel and event names share the `event:` namespace, so equal names could link falsely.
- [ ] Web (unverified): regex after `return` read as division (`web_scan.py:98`); a wrapper whose parameter has no
      parentheses isn't learned (`web_flow.py:170`); a reassigned/`+=`/ternary/same-line local drops the call
      (`web_flow.py:188-204`); namespace/named-object import call targets (`web_flow.py:438`); TS generic arrows and
      `@Input()` fields; test files emit `ui_route`.
- [ ] Scala (unverified): `Util("x")` on an `object` becomes `<init>`, not `apply` (`scala_body.py:252`); fields
      initialised with `new T` lose their type; class-body statements skipped (`scala_decl.py:441`);
      `val A, B = Value` -> phantom constants (`scala_emit.py:303`); interpolation tokenizer gaps, including
      exponential backtracking on an unterminated `s"` with many holes (`scala_tokens.py:18-25`).

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
