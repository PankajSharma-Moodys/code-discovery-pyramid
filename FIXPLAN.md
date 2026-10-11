# CDP — Fix plan

**Budget:** under 260 lines. **Source:** `DEFECTS.md`, 115 defects found on 2026-10-10/11. They were found on
`unified-store` (`sql-pool` in Java; `managed-sql` and `catalog-service` in C#) and in throwaway repos.

Each defect has five columns:
- **Defect:** what goes wrong for the user.
- **Observed:** the evidence.
- **Fix:** what to change.
- **Accept:** the test that shows it is fixed.

Code locations come from the investigation. Each phase re-reads that code before changing it.

## Terms
- **Store:** the one index database per machine (`~/.cdp/index.db`, or `CDP_HOME`).
- **Identity:** which repo a scan belongs to. A subfolder scan such as `unified-store#sql-pool` is its own identity, by design (PLAN.md).
- **Snapshot:** the index of one repo at one commit.
  - **Dirty (ephemeral) snapshot:** a scan of a working tree with uncommitted changes.
- **Claim:** one fact in the index, with `file:line` evidence.
  - **Derived:** produced by the scan itself, without a model.
  - **Model-written:** produced by a **leaf** (one model session reading one **scope**, a group of files) or by `answer`.
- **Patch:** a leaf's output, a set of claims. Patches arrive in the **inbox**, and `collect` accepts or rejects them.
- **Fold:** builds the live claim set from the patch log. A **generation** is one accepted patch for one scope.
- **Refresh:** updates the index for new commits without any model calls.
- **Gate / nudge:** CDP's Claude Code hook. The gate blocks the first grep/read and answers it from the index; the nudge only suggests using the index.
- **Link:** a cross-repo call, for example an HTTP client call matched to a route. A **resolution** is a model's verdict on an ambiguous link.

## How we work
- **Order:** fundamental first (P0–P4: the index must be trustworthy), then functionality (P5–P9), then the rest (P10).
- **Every fix** ships with a regression test on a real repo layout (P0), and is run live on `sql-pool`. That run is read-only, via `git archive`.
- **Every phase** passes the main suite and `web/tests`.
- **Scope:** Java, per PLAN.md. C# and Python items are under **Deferred**, waiting for your decision.

---

## P0 — Test foundation
All 631 tests passed while every defect below existed. The tests use 8 small fixture repos, and none of them has the layouts where these bugs occur.

| ID | Defect | Observed | Fix | Accept |
|---|---|---|---|---|
| F2 | Tests cover none of the real-world repo layouts | No worktree, subfolder module, dirty tree, Java inheritance or package-private code in any fixture | 1. Add a test helper that builds temp git repos with those layouts, plus history: multi-module, rebase, rename, whitespace-only commit. 2. After every test that writes state, check three things: (a) **refresh = scan**: refreshing to commit C gives the same index as a fresh scan of C; (b) **no silent loss**: a fold removes model-written claims only through a logged retraction, rollback or demotion; (c) **right snapshot**: the answering snapshot is HEAD or a clean ancestor of HEAD. 3. Add a script that replays 26 `sql-pool` commits under check (a). | The checks fail on today's code for A10, A11, A12, L1, L2 and L3, and pass after each fix |
| F3 | Some tests only pass with a hand-set PYTHONPATH | `ModuleNotFoundError: helpers` | `conftest.py` adds `tests/` to `sys.path` | `pytest tests/` passes with no environment setup |

## P1 — The right snapshot answers
**Today:** when no snapshot matches HEAD, CDP uses whichever snapshot was touched last. That can be another branch, or a scan of uncommitted changes, and nothing says so.

**New rule**, shared by query, MCP, hooks, `refresh`, `collect`, `prompts`, `docs` and `status`:
1. Use the snapshot for HEAD with a matching working-tree state.
2. Otherwise, use the nearest **clean ancestor** of HEAD.
3. Never use another branch's snapshot, or a dirty snapshot that doesn't match the current tree.
4. If no snapshot qualifies, answer "scan needed".

| ID | Defect | Observed | Fix | Accept |
|---|---|---|---|---|
| A1 | When the current commit has no snapshot, answers come from the newest snapshot of any branch, unmarked | Root answered at `d9edda607` while HEAD was `56b65654a` (`use_current_snapshot`) | Apply the new rule | After a commit, answers come from the parent's snapshot with `behind: 1`. After switching branch, they never come from the old branch |
| A2 | Root and subfolder are separate indexes, and MCP silently picks one by the `repo` path | `repo=.../unified-store` gave stale answers; `.../sql-pool` gave current ones | Resolve a path to the most specific scanned identity that contains it; every answer names its identity | Asking from the root about a file in `sql-pool` answers from `#sql-pool` and says so |
| A3 | Worktrees and local clones share an identity, so a worktree gets another branch's answers | A `feature` worktree was told `compute` exists; it doesn't on that branch | The new rule's ancestor check | Two worktrees on two branches, querying at the same time, each see only their own branch |
| A4 | `refresh` refuses in every worktree or clone except the one first scanned | "does not match the repo this state was scanned from" | Compare the git common dir, not the path | `refresh` succeeds in a second worktree |
| A5 | The session-start hook says "ready" when refresh failed, and shows the wrong commit | "ready: commit b30319e" in a worktree at `26b60ff` | Report the failure and its reason, with HEAD and the index's commit | A forced refresh failure produces "refresh failed: <reason>; index N commits behind" |
| A6 | `refresh` copies model claims from the latest snapshot, which may be another branch | `refresh.py:298-305`; rolled-back claims return (I7) | `refresh` builds on the snapshot the new rule chooses | After a branch switch, only an ancestor's claims are carried |
| A7 | Answers don't say they are stale or from uncommitted changes | Answers at `d9edda607` carry no marker; dirty answers show a plain SHA | Every CLI and MCP answer carries `as_of`, `behind`, `dirty_files`, and `changed_since` on each citation | After a commit touches a cited file, that citation is flagged |
| A8 | All worktrees share one work directory (prompts, inbox) | `work/<slug>` | Key the work directory per worktree | Two worktrees' runs never see each other's files |
| A9 | After a new commit, `prompts`/`collect`/`status`/`docs` silently use the old snapshot | Temp repo | Apply the new rule. `collect` rejects a patch from another snapshot's run, with the reason | `status` shows the new HEAD and `behind`; a stale patch is rejected with an explanation |
| A12 | Facts from an uncommitted-changes scan enter the next permanent snapshot | Dirty scan adds `dirtyB` in module a → revert → commit only module b → refresh: `dirtyB` is served at the new commit | `refresh` never builds on a dirty snapshot (new rule) | On that exact repro, `dirtyB` is absent, and refresh = scan holds |
| A13 | Queries ignore the working tree, and `status` stays on an old commit | After a revert, `dirtyB` is still served, labelled `fd237d`; refresh says "nothing to do"; status shows `1305fd` while git is at `5259df`. Same on Postgres | A dirty snapshot is used only if its tree hash matches the current tree | After a revert, `dirtyB` is not found, and `status` equals git HEAD |
| A15 | Adding or changing the git remote orphans every snapshot | `git remote add` then `status`; the error lists bare UUIDs | Keep identity aliases keyed on the git common dir and the root commit | After `git remote add`, `status` still shows the existing snapshots |
| A16 | `answer`/`collect` are accepted on a dirty snapshot, then carried forward | An `answer` about `dirtyB` was accepted; at the next commit, `root/a` showed "complete" | Accept only if every cited file is unchanged against HEAD; otherwise reject, naming the dirty files | Citing a dirty file is rejected; citing clean files is accepted onto the HEAD snapshot |

**Stress cases P1 must pass:** rebase, shallow clone ("scan needed"), detached HEAD, two concurrent worktrees, and a dirty tree over a clean HEAD snapshot (answered with a dirty marker).

## P2 — Indexed knowledge is never silently lost
**Today:** fold keeps the highest generation per scope, and the scan's derived claims are logged as scope `root`. So a patch for a scope replaces everything before it, including derived claims and earlier answers.

**New fold:**
- **Derived claims** are regenerated on every scan and refresh, and are never stored as a generation.
- **Leaf claims** are the latest *accepted* generation per scope.
- **Answers accumulate.** A new answer replaces an old one only for the same subject and question.
- **Rollback exclusions** are ranges of patch numbers.
- `verify` and `fold --check` enforce "no silent loss".

| ID | Defect | Observed | Fix | Accept |
|---|---|---|---|---|
| L1 | A model patch for scope `root` wipes every scan-derived claim | Real `#sql-pool` store has 53 claims and none of the 45 route claims; a fresh scan gives 158 (`pipeline.py:139`, `state.py:144-160`) | Derived claims leave the generation log | After a root patch, all derived claims are live. The rebuilt real store has ≥158 claims, including the 45 route claims |
| L2 | An abandoned scope (crash, timeout, bad output) drops its derived claims | 13 → 8 claims (`state.py:178-179`) | Abandoned or rejected patches create no generation | With a crashing runner, the claim count is unchanged |
| L3 | Each `answer` replaces the scope's leaf claims and every earlier answer | 6 answers given; only the last was live | Answers accumulate, as above | 6 answers on different subjects are all live |
| L5 | Rejected or abandoned patches stay in the inbox, and a later `collect` accepts them | `status` showed one scope as both complete and abandoned | Move them to `inbox/rejected/`. `collect` takes only patches from the active run for dispatched tasks | A rejected patch is never accepted later |
| L8 | `--mode lenient` breaks `fold --check`, and the next strict fold drops its claims silently | FAIL "wrote directly to the materialized view" | Lenient claims go through the patch log, flagged. A strict fold keeps them or reports what it dropped | `fold --check` passes after a lenient run, and every drop is reported |
| I1 | `compact --keep-generations 0` deletes live claims, while help says "nothing is lost" | 1 claim → 0 | `compact` never touches the live set | The live set is byte-identical before and after any `compact` |
| I2 | `compact` leaves `verify` failing until a manual `fold` | "fold_hash mismatch" | `compact` re-folds | `verify` passes right after `compact` |
| I5 | `rollback` also blocks every future patch for that commit, and has no undo | Coverage 0% after a later accepted patch | Exclusions cover a range of patch numbers; add `rollback --undo` | A patch accepted after a rollback is live; undo restores the rolled-back claims |
| I7 | Rolled-back claims come back after the next commit | Coverage back to 100% | `refresh` carries exclusions forward | Rolled-back claims stay out after 3 commits |
| M1 | Re-running `link scan` deletes all link resolutions | 1 → 0 | Merge resolutions by link ID | Resolutions survive a re-scan |
| M2 | One malformed link patch crashes `link run` and loses resolutions already validated in that run | A `[1]` patch → AttributeError (`link.py:385`); the task keeps its lease, and the next run reports "nothing to dispatch" | Save each resolution as soon as it is validated. A bad patch abandons only its own task and releases the lease | A good + bad run keeps the good resolutions, exits non-zero, and the next run picks up the rest |
| M8 | Every commit duplicates every link | The link ID includes the commit SHA (`link.py:139,302-304`); an unrelated commit took 8 links to 16 | Build the ID from protocol plus caller and callee (repo, file, symbol, target), with no SHA and no line | After 3 commits, the link count is unchanged and resolutions are kept |
| M9 | Concurrent `link run`s overwrite each other, and both report success | N=2 kept 4/7 resolutions, N=4 kept 2/7; the lock lives in `CDP_HOME`, not with the store | Key the lock by the store; save per resolution | 10 runs at N=4 keep 7/7 |

## P3 — Staleness is detected; failures are visible
| ID | Defect | Observed | Fix | Accept |
|---|---|---|---|---|
| A10 | Refreshing a subfolder scan never re-reads changed files | `#sql-pool`: 7/7 changed methods stale; diff paths are git-root-relative but joined onto the subfolder (`refresh.py:92-97`) | Convert paths to subfolder-relative; drop paths outside the subfolder | Refresh = scan on the 26-commit `sql-pool` replay |
| A11 | Commits that only change whitespace are never re-read, so line numbers drift | 5 blank lines added → "0 edited"; `beta` reported at line 4, really at 9 (`refresh.py:91-94`) | Re-read any file whose content hash changed | Line numbers are exact after a whitespace-only commit |
| A14 | `refresh` forgets `scan --exclude` | `excluded.count` 1 → 0 | Store the excludes in the snapshot manifest | Excluded files stay excluded after refresh |
| C3 | Count claims ("77 files declare …") go wrong without being flagged stale | 70 such cases over 26 `sql-pool` commits; e.g. `naming.package_path.case` 77 → 74 at `7caa74aef`, with its evidence file untouched | Derived claims: fixed by regeneration (P2). Model-written count claims: stale when any file in their scope changes | Replay: 0 wrong derived counts; a model count claim is flagged after any change in its scope |
| L9 | `run`/`doctor`/`reflect` exit 0 when every scope fails | Real store: a run marked "complete" with 20/24 tasks abandoned (`cdp-leaf` agent not found) | Exit codes: 0 all ok, 3 partial, 1 all failed. Print abandoned and rejected counts and rejected unknowns | An always-failing runner gives rc 1; a half-failing one gives rc 3 |
| M3 | `link run`/`prompts`/`collect` exit 0 when every task fails | Crash, timeout and invalid-JSON stubs → rc 0 | Same exit codes as L9 | Same as L9 |
| D6 | Session start claims "model-reviewed coverage N%" with no model review | 4% on `sql-pool`, 2% on a fresh scan | Count only scopes with an accepted leaf patch | A fresh scan reports "no model review" |
| K3 | The root scope counts as complete after a bare scan (suspected) | `coverage --json` | Confirm it, then apply the same rule as D6 | A fresh scan's root is not complete |

## P4 — No crashes; safe by default
| ID | Defect | Observed | Fix | Accept |
|---|---|---|---|---|
| F1 | `run --parallel` crashes the process | SIGSEGV/SIGBUS. N=2: 2 of 5 runs failed; N=4: 6 of 15. Threads share one SQLite connection (`sqlite_backend.py:270`, `supervisor.py:255-256`) | One connection per thread | 50 runs at `--parallel 4`, outside pytest, with 0 failures |
| L11 | `doctor --model <value>` writes wherever the value points | A crafted value wrote `/tmp/.../escaped.json` | Names must match `[A-Za-z0-9._-]+`, and the resolved path must stay inside the target directory | A traversal value is rejected; nothing is written outside |
| J6 | `selftest --bless` with an unsanitised name could delete any directory | `golden.py:112-117`; `--golden-name` without `--golden` silently runs the full suite | Same name check; require `--golden` | A traversal name is rejected, and a missing `--golden` is an error |
| J3 | `install --remove-harness` deletes the user's own hooks | Any hook containing `cdp/hook.py` is removed (`install.py:266`) | Record exactly what `install` wrote; remove only exact matches | A user hook that mentions `cdp/hook.py` survives removal |
| J7 | MCP accepts any input, and the model can create stores anywhere | No input-schema validation; malformed JSON is dropped silently; `cdp_scan state_dir` | Validate against the schema; return JSON-RPC errors; remove `state_dir` | Bad input gets an error reply; `state_dir` is rejected |
| B14 | Symlinks out of the repo are followed and indexed as repo files; files over 2 MB are skipped silently | `outside_secret` indexed at `pkg/ext.py:1`; `big_tail` not found | Don't follow symlinks out of the repo; list skipped files in `coverage` | Nothing outside the repo is indexed, and skipped files are listed |
| I3 | `gc --dry-run` modifies the store | The SQLite diff shows pins and `touch_seq` written | Open the store read-only for a dry run | The store file's hash is unchanged after a dry run |
| I6 | The "anonymised" export leaks IDs and SHAs, and its tokens can be reversed | `sha1("p.Svc#a")` equals the exported token | HMAC with a random salt per export; drop IDs and SHAs | No source name or SHA can be recovered from the export |
| J5 | CDP writes into the repo despite saying "nothing is written" | `.git/cdp-identity` (even on `query`); `CDP_HOME` allowed inside the repo; `docs --out` | Refuse a `CDP_HOME` inside the repo. Correct the text: `.git/cdp-identity` is untracked and stays | `git status` stays clean after scan, query and docs (with the default output location) |

---

## P5 — Java extraction and query accuracy
Measured against an independent ground truth, the `javac` script from the investigation, which becomes a benchmark. The targets are proposals for you to confirm.

| ID | Defect | Observed | Fix | Accept |
|---|---|---|---|---|
| B1 | Calls to inherited methods are not recorded | `getServersForStaticPool`: 0 uses, 2 real call sites | Resolve calls through the superclass chain | The benchmark finds both sites |
| B2 | `Class#method` lookup ignores inheritance and silently returns a prefix match | `ServerService#setServerHint` → `setServerHintApplied` | Exact match plus inherited members; no prefix fallback unless asked | The inherited method is returned, never the prefix match |
| B3 | Package-private methods are not indexed (this includes all JUnit 5 tests) | About 390 in `sql-pool` | Index every access level | Methods ≥99% overall |
| B4 | Non-final static fields are not indexed | `MAX_MAINTENANCE_MINUTES` | Index all fields | Present |
| B6 | Interface methods are not indexed | 112, e.g. `Provisioner#getPriority` | Index them | Methods ≥99% |
| B7 | Constructors are not indexed | 130 | Index them | Methods ≥99% |
| B8 | Only 60% of call sites are found | 1,809 sites: chained calls 0%, `X::m` 0%, static 0%, field 76% | Resolve chained, method-reference, static and field-typed calls | Call sites ≥90% |
| B12 | Tables (Java side): Flyway DDL with `${placeholder}` is not parsed, and prose is taken for table names | `QRTZ_LOCKS` missing; Flyway 7/29; `body`/`lines`/`failed` reported as tables | Substitute placeholders before parsing; only report SQL identifiers in DDL/DML contexts | Flyway ≥27/29; table precision ≥95% |
| B13 | Config read in Java code is not indexed | `SQL_POOL_SCHEMA` `read_count: 0`; 0/23; `${DW_*}` not treated as config; YAML lists mis-nested | Index `getenv`/`getProperty`/Dropwizard config reads; fix YAML lists | Java config reads ≥90% |
| B15 | Routes lack the Dropwizard context path and show unresolved constants | `/v1/servers` instead of `/unified-store/sql-pool/v1/servers`; raw `${ApiConstants…}` | Prefix the context path; resolve constants | Benchmark routes match exactly |
| B16 | `trace` doesn't follow events (EventBus) | `ServerSubscriber` never reached | Add publish → subscribe edges | `trace` reaches `ServerSubscriber` |
| B17 | Oversized scopes are never flagged | 64 files against a limit of 40, `oversized=False` (`partition.py:105-106`) | Apply the limit to file-group scopes | Flagged |
| B21 | Config shows one site per key with "elided: 0"; keys passed via constants are missed | 5 reads of one key, 1 shown | Show every site, or count what was elided; resolve constants | Counts match the benchmark |
| B5 | `search` matches indexed names only, not text, without saying so | Empty for a real constant | Search text too, or state the limit in output | A known constant is found, or the reply states the limit |
| H1 | `query config` cites nothing at default settings | 0/226 sites; 247 elided | Spend the budget on citations before key names | Default output has citations |
| H2 | `paths` finds nothing when `--from`/`--to` is a middle node | `--from ServerService#register` → 0 | Match any node on the path | Returns the paths through that node |
| H3 | `--exclude-role` doesn't filter `used_by`, and roles aren't validated | 16 test sites remain; `bogusrole` exits 0 | Filter `used_by` too; reject unknown roles | No test sites; a bad role is an error |
| H4 | `table`/`file` match substrings and `routes` matches paths only, all unstated | `table server` → 4 tables | State the matching mode; add `--exact` | `--exact` returns 1 table |
| H9 | `diff` says nothing changed when files changed | 3 files changed, shown as "0 … 0" | Report file and symbol changes | All 3 shown |

## P6 — Claude actually uses CDP well (gate, hooks, MCP)
| ID | Defect | Observed | Fix | Accept |
|---|---|---|---|---|
| E10 | No shared guide convention across the MCP schema, SKILL.md, `cdp help` and docs | The model never used `trace`/`config`; 8 of 19 calls cut short by budgets it chose | Each command and query kind defines **What** (answers / doesn't index / how to read output), **How** (every flag, its default, side effects, examples) and **Where** (which question, next step) once; all four surfaces are generated from it | A test proves the four surfaces match the source, and every kind has all three parts |
| E2 | The MCP schema explains 6 of 14 kinds, describes `term` wrongly, and has no ranges or enums | `schemas.py` | Generated from E10 | Schema covers 14/14 kinds |
| E3 | MCP `cdp_query` lacks `exclude_role`, and passing it raises a TypeError | `tools.py` | Add it | Parity test with the CLI |
| E1 | The gate ignores MCP calls, so it blocks right after the model asked CDP | Live session: `cdp_query symbol` then grep → denied | An MCP query counts as "the index was asked" | No denial after an MCP query |
| D1 | The gate drops search terms it can't answer, but presents the answer as complete | `jdbc:sqlserver\|getConnection` → answers `getConnection` only | Block only if every term is answered | Mixed searches run normally |
| D2 | The gate blocks a whole compound command, non-search parts included | `git log -S… ; grep …` blocked | Never block commands containing non-search parts | `git log` runs |
| D3 | The gate claims the index "already answers" when its answer is wrong or empty | A grep for callers was blocked, while the index had 0 callers | Never block on an empty answer, or for a question the answer can't cover (e.g. callers when `used_by` is empty) | Live: the "who calls X" grep is not blocked |
| E12 | CDP never sees an empty grep, the exact moment it could help | An empty grep fires `PostToolUse` with "No matches found", not `PostToolUseFailure` (verified live, CC 2.1.296) | Add a PostToolUse hook: on an empty grep for a term the index knows, add context pointing to `cdp_query` | A canary session receives that context |
| J9 | `install --harness` turns on the blocking gate by default and writes `AGENTS.md` into the repo | Help says "the Read/Grep/Glob hook"; blocking is documented only under `--strict` | Install the nudge by default and block only with `--strict`; write `AGENTS.md` only on request | Default install has no deny hook and no new repo file |

**Phase acceptance:** a scripted headless Claude session on a Java test repo.
- It answers "who calls X" over MCP with correct callers.
- No blocked call follows an MCP query.
- `trace` is used at least once.

## P7 — Agent loop correctness and re-review cost
| ID | Defect | Observed | Fix | Accept |
|---|---|---|---|---|
| L4 | Claims with evidence outside the dispatched scope, or about subjects that don't exist, are accepted | `outscope` stub → verdict `consistent` | Require evidence inside the scope and a subject that resolves | Both are rejected |
| L15 | One over-long field throws away the whole patch | Real store: a statement of 512 characters against a 500 limit | Reject the claim, keep the rest | The other claims are accepted |
| K1 | `conflicts` reports 0 while claims contradict | "no table name stated" vs `@Table(name="server")` | Compare claims with the same subject and predicate | The contradiction is reported |
| K2 | Wrong claims are accepted | DTOs called "persisted"; a production side effect cited from a test file | A test-file citation can't support a production claim | Rejected |
| L6 | `--resume` silently skips a killed scope, and its tip names a flag that doesn't exist | rc 0, scope stuck `dispatched`; `--run-id` doesn't exist | Reclaim the dead run's leases; fix the tip | The killed scope is re-run |
| L7 | `--stale-only` re-sends the same scope forever | "1 stale" on every run, billed each time | Fixed by P2 (derived claims are regenerated) | Second run: 0 stale |
| L12 | `run` holds the lock for its whole length; `status` fails after 60 s and advises deleting a live lock | rc 2 | Hold the lock per write | `status` works during a run |
| L10 | `reflect` accepts absurd changes; `holdout` measures only import hints, yet promotes; changes apply machine-wide | `new_value=-999999` accepted; sigma emptied | Bound the changes; measure claims; make lesson cuts per repo | An absurd value is rejected; other repos are unaffected |
| L14 | Leaf cost is never recorded | The runner discards Claude's output (`cdp-claude-leaf.sh:41`); `wall_ms` null in 119/119 rows | Use `--output-format json`; store cost and time | The trajectory shows real cost |
| C1 | A claim goes stale when *anything* in its file changes | 35/35 stale flags were false alarms. Per-section hashing was tested and is unsafe: hashing the cited span misses 74/79 real changes | Keep per-file staleness; re-review only the stale claims (see C2) | No missed invalidations on the replay |
| C2 | Any change re-sends the whole scope to the model | 58 dispatches vs 9 needed; ≈ $12 per occurrence (measured: $0.15–0.24 per leaf) | Send only the changed files and stale claims of a scope | The 15-commit replay has ≤9 dispatches |

## P8 — Link correctness
| ID | Defect | Observed | Fix | Accept |
|---|---|---|---|---|
| J8 | `link scan` misses a real HTTP call, writes despite being "read-only", and shows the callee as the caller | catalog → sql-pool Refit call (`ISqlPoolServiceApi.cs:11` ↔ `ReservationResource.java:180`) missed | Detect Refit/HTTP clients; make the scan read-only; fix labels; reject an unknown `--service` | The pair is linked with correct labels; the store is unchanged by the scan |
| M4 | Resolved links are re-sent, and contradictory duplicates are accepted (the last one wins) | 2 resolutions folded for 1 link | Skip resolved links; reject duplicates | A second run dispatches 0 |
| M5 | Link patches land in the scope inbox, where `collect` rejects them and leaves them | `REJECTED link-….json` | Give link patches their own inbox | `collect` never sees them |
| M6 | Any keys are accepted; citations are checked by file and line only, in any repo; `"line":"2"` is rejected | `"evil"` key accepted | Closed schema; check repo + file + line; accept a numeric string | Bad keys are rejected; a wrong-repo citation is rejected |
| M10 | After a call site moves, its resolution still points at the old line, now a different call | Resolution at `client.js:4`, which became the `users` fetch | Re-anchor the resolution together with its link | The anchor follows the call |
| M11 | Flask and JS route parameters aren't normalised, so Flask ↔ fetch never links; `link scan --db` demands a value | `<int:uid>` vs `${id}`: 7/7 unmatched | Normalise `<x>`, `<int:x>`, `{x}`, `:x`, `${x}`; make `--db` optional | 7/7 linked |

## P9 — Setup and integration
| ID | Defect | Observed | Fix | Accept |
|---|---|---|---|---|
| J1 | The git hook fails on every commit when CDP runs from a checkout | "No module named 'cdp'" | Call `run.py`, or set PYTHONPATH | A commit refreshes the index |
| J2 | The git hook installs partially on refusal, is hard-wired to one worktree, and has no pull/rebase hooks | `.git/hooks/post-commit` | Atomic install; per-worktree; add post-merge and post-rewrite hooks | Commit, pull and rebase refresh in any worktree |
| J4 | `install` writes absolute paths, ignores `--strict`, and uninstall leaves `{}` files | `settings.json`, `.mcp.json` | Relative paths; honour `--strict`; delete files left empty | A clean uninstall leaves no `{}` files |
| I4 | `--db` with a wrong path silently creates an empty store | `export --db` exported 0 artifacts, exit 0 | A missing path is an error | rc ≠ 0 with a message |

## P10 — Docs, input validation, hook polish
| ID | Defect | Observed | Fix | Accept |
|---|---|---|---|---|
| E4 | SKILL.md lacks `trace`, MCP usage and `/cdp <question>` handling | SKILL.md | Generated from E10 | All present |
| E5 | Hook text recommends the CLI, but sessions use MCP | 19 MCP calls, 0 CLI | Lead with MCP | Text names `cdp_query` first |
| E6 | Session-start text lists `link` as a query kind | `QUERIES` | Remove it | Absent |
| E7 | About 34 flags are undescribed, and 23 of 26 commands have no examples | `help --json` | E10 generator | Every flag described; every command has an example |
| E9 | `docs/CDP_REFERENCE.md` is incomplete and loaded by nothing | — | Generate it, or delete it | Generated, or gone |
| E11 | Help and recipes are wrong (docs path, `--hook` vs `githook`, `answer`/`holdout` usage, output locations) | `help workflows`, `--help` | Fix each; a test runs every documented example | Every example runs |
| B18 | Docs label normal modules "generated at build time" | `inventory.py:311,327` | Fix the heuristic | Correct label |
| M7 | The link prompt's example JSON is invalid, plus small link CLI issues | `'link-…'` single quotes; `--runner-cmd` split on spaces; a second call site dropped; `no_match` hidden | Emit valid JSON; split with shlex; keep all sites; show the verdict | Example parses; all sites shown |
| E8 | Flags that don't apply are silently ignored | `claims config --kind entrypoint` | Reject them | Error |
| H5 | Short SHAs are rejected, though CDP prints them | `diff`, `--as-of`, `rollback`, `gc` | Resolve unique prefixes | Short SHA accepted |
| H6 | No range or type checks | `--max-concurrent 0` traceback; negative values accepted; MCP `"2"` TypeError | One shared validation layer for the CLI and MCP | Clean error messages |
| H7 | Tracebacks instead of error messages | `validate` on non-JSON; `export --out` onto an existing file | Catch them; give a message | No traceback |
| H8 | Unknown terms exit 0 with no hint | Every kind except `trace` | "Not found; did you mean …", rc 1 | rc 1 with a suggestion |
| L13 | Contradictory or invalid run flags are accepted | `--parallel 0`; `prompts --node nope` writes 0 prompts with rc 0 | Same validation layer | Errors |
| D4 | A gate block is shown to the user as "hook error" | `systemMessage` set alongside the deny | Drop `systemMessage` from the deny payload | No "hook error" shown |
| D5 | Wrong nudge text, a kill switch that misfires, and marker files never cleaned | Nudge suggests `cdp query file .`; `CDP_LEAF_SESSION=0` also disables the hooks; 74 markers in `$TMPDIR` | Fix the text; treat only `1` as on; clean markers by age | Marker count stays bounded |

## Deferred — waiting for your decision (PLAN.md scope is Java only)
`unified-store` has C# services, so these matter if CDP is meant to cover them. If approved, they become P5b, using the same benchmark approach (Roslyn-grade parsing for C#, `ast` for Python).

| ID | Defect | Observed |
|---|---|---|
| B9 | C#: only `public` methods are indexed | private methods 3/363 |
| B10 | C#: classes with long primary constructors lose their methods; generic and tuple-return methods are dropped | `AdminController` 0 methods; tuple-return methods 0/23 |
| B11 | C# routes: the partial-class `[Route]` and the `[controller]` token aren't applied | 41% exact paths |
| B19 | Python: no call sites at all | 0/436 |
| B20 | Python: nested functions, class attributes and annotated constants are missing | nested 0/50; class attributes 0/318 |
| — | C# and Python parts of B12/B13 (EF Core tables, `appsettings.json`, Python tables and config) | C# tables 0/18; C# config 0/7 |
