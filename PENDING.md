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
- [ ] Scala: a lambda param or `case x:` binder stays bound after its body (`scala_body.py`); a later real `x.m()` is
      lost or mis-targeted. Nested block comments deeper than 8 levels are not handled (`scala_tokens.py:20-24`).
- [ ] Web: an apostrophe in JSX text (`Don't`) drops every later class member (`lang/web_scan.py:56-65`). Reproduced.
- [ ] Web: `.bind(this, x)` in a Pusher file emits `event:${this}` (`lang/web_flow.py:377-395`). Reproduced.
      `.subscribe('ch')` channels are never emitted.
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
- [ ] The 19 UI->Scala links are all `heuristic` and only hand-checked: run `cdp link scan --db` then `cdp link run`
      to put them through the verdict stage.
- [ ] Scala `event_subscribe` (12 edges, `*Subscriber.scala`) and 35 Scala `schedule` edges: sampled, not checked
      against source one by one.
- [x] Hand-check of Scala routes: all 48 match source (trailing `/` on `/v1/config/`, `/v1/login/` as in Java).

## 5. Housekeeping
- [ ] Decide commit and branch (currently `feature/imporvements`); nothing is committed.
- [ ] Remove lane worktrees/branches in `~/hackathon/cs-lanes/` (scala, web, link, rules, merged) once committed.
- [ ] Headline numbers to quote: links 30 -> 62 distinct (+19 HTTP, +13 persist), not 171 -> 459 rows.
