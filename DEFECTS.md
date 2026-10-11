# CDP defects — investigation log

Found 2026-10-10/11 on `unified-store` (`sql-pool` Java, `managed-sql`/`catalog-service` C#, HEAD `56b65654a`) and in throwaway repos.
Status: **R** reproduced by me · **Rs** reproduced by a sweep agent (repro in its report, not re-run by me) · **M** measured · **C** code-read · **O** observed in a session · **U** user-reported · **S** suspected.

Common thread: A, B, D and H return answers that look complete but are not; I and L silently delete or corrupt indexed knowledge. F2 is why none were caught.

## A. Snapshot selection / identity / refresh — wrong answers, silently
| ID | Defect | Evidence | St |
|---|---|---|---|
| A1 | No snapshot for HEAD → newest snapshot (any branch) is used | `use_current_snapshot`; root answered at `d9edda607`, HEAD `56b65654a` | R |
| A2 | Root and `#sql-pool` are separate identities; MCP `repo` path picks one, undocumented | `repo=.../unified-store` stale, `.../sql-pool` current | R |
| A3 | Worktrees (and `--local` clones) share one identity → another branch's answers | `feature` told `compute` exists (it doesn't) | R |
| A4 | `refresh` refuses in any worktree/clone but the one in `manifest.json` | "does not match the repo this state was scanned from" | R |
| A5 | SessionStart hook swallows refresh failure, reports "ready" with wrong commit | "ready: commit b30319e" in worktree at `26b60ff` | R |
| A6 | `refresh` carries claims forward from newest snapshot, possibly another branch | `refresh.py:298-305`; rolled-back claims return after next commit (I7) | C/Rs |
| A7 | MCP answers carry no stale or dirty marker | session answers at `d9edda607`; dirty answers show plain sha | R |
| A8 | One work dir (inbox/prompts) shared by all worktrees | `work/<slug>` | C |
| A9 | After a new commit, `prompts`/`collect`/`status`/`docs` silently work on the old snapshot | temp repo | R |
| A10 | **Subfolder `refresh` never re-extracts changed files** (git-root-relative diff paths joined onto subfolder, `refresh.py:92-97`) | `#sql-pool` 7/7 methods stale; temp repo `Svc#a` line 3, truth 6 | R |
| A11 | **Whitespace-only commits never re-extracted** (`refresh.py:91-94`) → line numbers stale until the module changes again | 5 blank lines added: "0 edited", `beta` at 4, truth 9 | R |
| A12 | **Dirty-scan facts leak into the next permanent snapshot** when the dirty edit is in a module the next commit doesn't touch: refresh bases on the newest (dirty) snapshot, diffs real HEAD→new HEAD, copies the untouched module's dirty rows and patch log forward (`refresh.py` ~293) | dirty `a/mod.py` scan → revert → commit `b/` only → refresh: `dirtyB` served at H1 (`git show H1:a/mod.py` has none), ephemeral=0. Earlier miss: one-module repos | R |
| A16 | `answer`/`collect` accepted on an ephemeral (dirty) snapshot (`mark_durable` never called) and carried into the next permanent one via A12 | `answer --subject a.mod.dirtyB` consistent → at H1 `root/a complete` | Rs |
| A13 | Queries/MCP/status use the last-touched snapshot for HEAD, ignoring the current tree; `refresh` can't recover. After a new commit `status` stays on the old commit | dirty scan then `git checkout`: `dirtyB` served labelled clean sha, refresh "nothing to do"; status head `1305fd` vs git `5259df`; same on Postgres | Rs |
| A14 | `scan --exclude` not persisted; `refresh` re-includes excluded files (no facts) | `excluded.count` 1→0 | Rs |
| A15 | Adding/changing `origin` changes identity; old snapshots orphaned, error lists bare UUIDs | `git remote add` then `status` | Rs |

## B. Index / extraction — incomplete facts shown as complete
| ID | Defect | Evidence | St |
|---|---|---|---|
| B1 | Java: calls to inherited methods not recorded | `getServersForStaticPool` 0 uses, 2 call sites | R |
| B2 | `Class#method` lookup ignores inheritance, silently returns a prefix match | `ServerService#setServerHint` → `setServerHintApplied` | R |
| B3 | Java: package-private methods not indexed (all JUnit 5 tests) | ~390 in `sql-pool` | R |
| B4 | Java: non-final static fields not indexed | `MAX_MAINTENANCE_MINUTES` | R |
| B5 | `search` matches indexed names only, not text; not stated | empty for a real constant | R |
| B6 | Java: interface methods not indexed | 112, e.g. `Provisioner#getPriority` | M |
| B7 | Java: constructors not indexed (undocumented) | 130 | M |
| B8 | `used_by` 60% recall: chained 0%, `X::m` 0%, inherited/static 0%, field 76%; Python bare calls 0 | javac ground truth, 1,809 sites | M/Rs |
| B9 | C#: only `public` methods indexed | private 3/363 | Rs |
| B10 | C#: primary-constructor classes (>15-line param list) lose methods; generic `M<T>` and tuple-return methods dropped | `AdminController` 0 methods; tuples 0/23; routes get wrong/no handler | Rs |
| B11 | C# routes: partial-class `[Route]` and `[controller]` token not applied | exact path 112/272 = 41% | Rs |
| B12 | Tables: Flyway `${placeholder}` DDL unparsed; EF Core tables not reported; prose/SQL keywords parsed as tables (Python too) | `QRTZ_LOCKS` 0 (in V001.004); Flyway 7/29; C# 0/18; `body`/`lines`/`failed`; Python `table:the`, `SET`, 9/22 real tables missed | R/Rs |
| B13 | Config: Java/C# code reads not indexed; `appsettings.json` and `${DW_*}` not config; YAML lists mis-nested | `SQL_POOL_SCHEMA` `read_count: 0`; Java 0/23, C# 0/7 | R/Rs |
| B14 | Files > 2 MB silently unparsed; symlinks followed (incl. outside repo, indexed as in-repo) | `big_tail` not found; `outside_secret` at `pkg/ext.py:1` | Rs |
| B15 | Routes: Dropwizard context path not prefixed; trace/paths show unresolved `${ApiConstants…}` labels | `/v1/servers` vs `/unified-store/sql-pool/v1/servers` | Rs |
| B16 | trace: no async/event edges (EventBus subscribers never reached) | `ServerSubscriber` | Rs |
| B17 | Over-budget `(files)` scopes always `oversized=False` (`partition.py:105-106`) | 64 files vs limit 40 | Rs |
| B19 | **Python `used_by` always empty, every call form** (only import uses emitted; `from x import f` records the module) | 0/436 sampled sites (bare, `self.m`, `mod.f`, references); live: `stable_hash` 0 callers, 28 call sites | R/M |
| B20 | Python defs missed: nested functions, class attributes (incl. enum members), annotated assignments (`t.Final`), defs under module-level `if`/`try`; module functions typed `method`; `end_line` null | nested 0/50, class attrs 0/318; defs 92% (cdp) / 64% (click), lines exact | M |
| B21 | Config: one site per key shown with `elided: 0`; env keys passed via a constant unresolved | `COMP_WORDS` 5 reads, 1 shown; `CDP_HOME`, `CDP_LEAF_SESSION` absent | M |
| B18 | Docs label normal tracked modules "generated at build time" (`inventory.py:311,327`) | `sql-pool` "20 tracked against 500" | Rs |

## C. Freshness — wasted AI re-review
| ID | Defect | Evidence | St |
|---|---|---|---|
| C1 | Claim staleness is per file | 35/35 stale claims in a 15-commit replay were false alarms; section hash doesn't fix it: anchor-span misses 74/79 real invalidations, enclosing-member 0/79 but by coincidence and still 939/1578 false alarms (sql-pool, 26 commits) | M |
| C3 | **Aggregate claims ("N files…", "imports at N sites") go wrong with no evidence file changed; never flagged stale.** Anchors sample a few sites; the count covers all | base→26 commits: 70 invalidated claim-pairs had no evidence-file change (vs 79 that had one); 16 in consecutive pairs; `naming.package_path.case` 77→74 at `7caa74aef`, evidence file not in commit | R/M |
| C2 | `scope_hash` is all-or-nothing per scope | 58 dispatches vs 9 from staleness. Real leaf (sonnet): smallest scope (62 lines) $0.151 / 27 s; median scope (1,797 lines) $0.236 / 46 s → ≈ $0.15 fixed + $0.05/1k lines; 49 extra dispatches ≈ **$12 per occurrence** | M |

## D. Gate hook — blocks or misleads
| ID | Defect | Evidence | St |
|---|---|---|---|
| D1 | Drops terms it can't answer; partial answer presented as complete | `jdbc:sqlserver\|getConnection` → `getConnection` only | R |
| D2 | Blocks the whole compound command, incl. non-search parts | `git log -S… ; grep …` blocked | R |
| D3 | Blocks a search, saying the index "already answers" it, when the answer is wrong or empty | B1; live: grep for callers blocked, index has 0 (B19) | R |
| D4 | Block shown to the user as "hook error" (payload also sets `systemMessage`, redundant: `additionalContext` verified delivered) | live headless session, `is_error` result | R |
| D5 | Nudge suggests `cdp query file .`; `CDP_LEAF_SESSION=0` also disables; marker files never cleaned | 74 markers in `$TMPDIR` | Rs |
| D6 | SessionStart says "model-reviewed coverage N%" with zero model patches | sql-pool 4%; live fresh scan 2% | R |

## E. Harness surfaces and docs — Claude doesn't know how to use CDP
| ID | Defect | Evidence | St |
|---|---|---|---|
| E1 | PreToolUse hook registered for MCP but ignores MCP calls → gate blocks after the model already asked the index | `hook.py:73` WATCHED; live: `cdp_query symbol` then grep → denied | R |
| E2 | MCP schema explains 6/14 kinds; `term` description wrong; no ranges/enums/error shapes | `schemas.py` | R |
| E3 | MCP `cdp_query` lacks `exclude_role` (passing it → TypeError) | `tools.py` | R |
| E4 | SKILL.md: no `trace`, MCP one line, CLI syntax, no flow row, no `/cdp <question>` handling | SKILL.md | R |
| E5 | Hook text recommends `run.py`; MCP is the channel actually used | 19 MCP calls, 0 CLI | R/O |
| E6 | SessionStart text lists `link` as a query kind | `QUERIES` | R |
| E7 | ~34 flags undescribed (`--module/--subject/--from/--to`, every `--mode`, `scan --max-*`, `export --format`, …); 23/26 commands no examples | `help --json` | R/Rs |
| E8 | Flags silently ignored on kinds that don't use them; positional vs `--kind` conflict silent | `claims config --kind entrypoint` | R |
| E9 | `docs/CDP_REFERENCE.md` incomplete, loaded by nothing | — | U |
| E10 | **No shared guide convention across MCP schema, SKILL.md, `cdp help`, docs.** Each must give per command/kind: **What** (answers, doesn't index, how to read output), **How** (every parameter/flag, applies-to, default, side effects, worked examples), **Where** (which command for which question, next step) | E2–E9; session never used `trace`/`config`; 8/19 calls elided by self-chosen budgets | R |
| E12 | No PostToolUse hook: an empty grep (the miss CDP could answer) is never seen. Empty grep fires `PostToolUse` with `returnCodeInterpretation: "No matches found"`, not `PostToolUseFailure` (which fires on other non-zero exits) | live canary hooks, CC 2.1.296 | R |
| E11 | Help/recipes wrong: docs path `<state>/docs` (really `work/<slug>/docs`), "refresh hasn't landed", `link` subcommands missing, install tip says `--hook` auto-refreshes (that's `githook`), `diff` defaults misstated; `answer` usage shows `--scope` (positional), `holdout` shows `<repo>` (it is `--repo`); prompts/inbox/doctor output locations never stated | `help workflows`, `help link`, `--help` | Rs |

## H. Query semantics and input handling
| ID | Defect | Evidence | St |
|---|---|---|---|
| H1 | `query config` default budget yields zero citations (200 key names consume it) | 0/226 sites, 247 elided | Rs |
| H2 | `paths --from/--to` match only path endpoints → "0 paths" for connected intermediate nodes | `--from ServerService#register` → 0 | Rs |
| H3 | `--exclude-role` filters definitions but not `used_by`; role values unvalidated | 16 test sites remain; `bogusrole` exit 0 | Rs |
| H4 | `table`/`file` terms are substring matches, `routes` term matches path only; unstated | `table server` → 4 tables | Rs |
| H5 | Short SHAs rejected though CDP prints them: `diff`, `--as-of`, `rollback`, `gc --head-sha` | "never appears in this store's patch log" | Rs |
| H6 | No range/type validation: `scan --max-concurrent 0` traceback; negative `--workers/--budget/--max-hops/--keep-generations` accepted; MCP `max_hops:"2"` TypeError, `budget:"ten"` leaks internals | as listed | Rs |
| H7 | Tracebacks instead of errors: `validate` on non-JSON, `export --out` existing file | JSONDecodeError, FileExistsError | Rs |
| H8 | Unknown terms exit 0 with no hint on every kind except `trace`; `help <unknown>` exit 0 | — | Rs |
| H9 | `diff` silent on file/symbol changes (reads "nothing changed" when files changed) | 3 files changed, "0 … 0" | Rs |

## I. Maintenance commands — data loss / state corruption
| ID | Defect | Evidence | St |
|---|---|---|---|
| I1 | `compact --keep-generations 0` archives the live generation → claims lost (help: "nothing is lost") | 1 claim → 0; my rescan-based repro moved 0 patches (needs collect-made generations) | Rs |
| I2 | Default `compact` leaves `fold --check`/`verify` failing until a manual `fold` | "fold_hash mismatch" | Rs |
| I3 | `gc --dry-run` writes (pins, `touch_seq`) | sqlite diff | Rs |
| I4 | `--db PATH` (gc/compact/export/link) silently creates an empty store; `export --db` exports nothing | 0 artifacts, exit 0 | Rs |
| I5 | `rollback --to-run <HEAD>` excludes all future patches for that commit, no undo | coverage 0% after a later accepted patch | Rs |
| I6 | `export --format anonymized` leaks claim ids, shas; unsalted sha1 tokens are reversible | `sha1("p.Svc#a")` = exported token | Rs |
| I7 | Rollback exclusion lost after the next commit (claims return) | coverage back to 100% | Rs |

## J. Setup and integration
| ID | Defect | Evidence | St |
|---|---|---|---|
| J1 | `githook` script runs `python -m cdp.cli` without PYTHONPATH → fails on every commit from a checkout | "No module named 'cdp'" | Rs |
| J2 | `githook`: partial install on refusal; worktrees share hooks but script hard-codes one worktree; no pull/rebase hooks | `.git/hooks/post-commit` | Rs |
| J3 | `install --remove-harness` removes any hook containing `cdp/hook.py`, incl. the user's | `install.py:266` substring match | C/Rs |
| J4 | `install`: absolute non-portable paths; `--strict` silently ignored; remove leaves `{}` files | settings.json, .mcp.json | Rs |
| J5 | Writes into the repo despite "nothing is written": `.git/cdp-identity` (even on `query`), `--state-dir`/`CDP_HOME` inside repo, `docs --out` | `registry.py:88-95` | Rs |
| J6 | `selftest --golden-name` without `--golden` silently runs the full suite; with `--bless`, an unsanitised name could rmtree any path | `golden.py:112-117` | Rs/C |
| J7 | MCP: no inputSchema validation; malformed JSON dropped silently; `cdp_scan state_dir` lets the model create stores anywhere | JSON-RPC probes | Rs |
| J9 | `install --harness` installs the deny gate by default (help: "the Read/Grep/Glob hook"; blocking documented only for `--strict`) and writes `AGENTS.md` into the repo | temp repo install | R |
| J8 | `link scan` misses the real catalog→sql-pool Refit HTTP call; "read-only" scan writes `link_edge`; text output shows callee as caller; unknown `--service` exit 0 | `ISqlPoolServiceApi.cs:11` ↔ `ReservationResource.java:180` | Rs |

## K. AI claim quality
| ID | Defect | Evidence | St |
|---|---|---|---|
| K1 | `conflicts` reports 0 while claims contradict ("no table name stated" vs `@Table(name="server")`) | 6 claims | Rs |
| K2 | Wrong claims accepted: wire DTOs "persisted"; production side effect cited from a test import | `sql_bridge.py:144`, `ServerSubscriberTest.java:5` | Rs |
| K3 | Root scope counted `complete` after a bare scan (no model run) | `coverage --json` | S |

## L. Agent layer (prompts, collect, run, answer, doctor, reflect, lessons, holdout)
| ID | Defect | Evidence | St |
|---|---|---|---|
| L1 | **A leaf patch for `root` replaces the whole deterministic patch** (derived patch logged as node `root`, `pipeline.py:139`; fold keeps highest generation per node, `state.py:144-160`) | real `#sql-pool` store: 53 claims, 0 of the 45 route claims a fresh scan of the same code gives (158 total); minirepo 13 → 1 | R/Rs |
| L2 | **Any abandoned scope drops that scope's deterministic claims** (`state.py:178-179`) | crash/timeout/bad-schema stubs: 13 → 8 claims | Rs |
| L3 | **Each `answer` supersedes the scope's leaf claims and every earlier answer**, even when demoted; demoted answer's promised unknown never appears | gens 1–6, only gen 6 live | Rs |
| L4 | Evidence outside the dispatched scope accepted; claims on unresolvable subjects accepted (unknowns are gated) | `outscope` stub, verdict `consistent` | Rs |
| L5 | Rejected/abandoned patches stay in the inbox; a later `collect` accepts them and marks the node complete; killed runs leave the runner writing into the inbox | `status`: complete + abandoned for one node | Rs |
| L6 | `--resume` within the 90 s lease silently skips the killed scope; printed tip `--run-id` doesn't exist | rc 0, scope still `dispatched` | Rs |
| L7 | `--stale-only` re-dispatches the same scope forever (stale derived claims can't be refreshed by a leaf) | "1 stale" on every run, re-billed | Rs |
| L8 | `--mode lenient` state always fails `fold --check`; next strict fold silently drops lenient-kept claims | FAIL "wrote directly to the materialized view" | Rs |
| L9 | `run`/`doctor`/`reflect` exit 0 when every scope is abandoned or the runner crashed; `run` hides gate-rejected unknowns that `collect` reports | rc 0; real store: run `complete` with 20/24 tasks abandoned (`--agent 'cdp-leaf' not found`, fixed 5d81206) | R/Rs |
| L10 | `reflect` accepts absurd changes (`new_value=-999999`); `holdout` measures only import hints and promotes; cut is machine-wide → affects every repo's default `run` | "BUDGET FIRED", sigma emptied | Rs |
| L11 | `doctor --model` used as a file name unsanitised (path traversal); concurrent doctors share a scratch patch; crash reported as "yield_collapse" | wrote `/tmp/.../escaped.json` | Rs |
| L12 | `run` holds the exclusive lock for its whole length; `status` fails after 60 s and advises deleting a live lock | rc 2 | Rs |
| L14 | Leaf runner discards Claude's output → cost never recorded; trajectory `wall_ms` null for every run | `cdp-claude-leaf.sh:41` `> /dev/null`; 119/119 rows null | R |
| L15 | One over-limit field abandons the whole scope's patch | real store: statement 512 > 500 chars | R |
| L13 | Unvalidated or contradictory flags: `--max-attempts/--timeout/--parallel 0/-n`, `--lessons N` for a missing cut, `prompts --wave 9/--node nope` write 0 prompts rc 0; next-step text prints `--lessons v1` (flag is int) | as listed | Rs |

## M. Link agent layer (`link prompts`/`link run`, stub runners)
| ID | Defect | Evidence | St |
|---|---|---|---|
| M1 | **Re-running `link scan` deletes all folded resolutions** | resolutions 1 → 0 | Rs |
| M2 | Non-object patch crashes `link run` (`link.py:385`) and loses resolutions validated earlier in the run; crashed task keeps its lease, next run "nothing to dispatch" rc 0 | `[1]` patch → AttributeError | Rs |
| M3 | `link run`/`link prompts`/`link collect` exit 0 when every task fails | crash/timeout/nojson stubs: rc 0 | Rs |
| M4 | Not idempotent: resolved tasks re-dispatched and re-prompted; duplicate contradictory resolutions accepted, last wins | `dup` stub: 2 folded for 1 link | Rs |
| M5 | Link patches land in the scope inbox; `cdp collect` rejects them and leaves them | `REJECTED link-….json` | Rs |
| M6 | Open schema (unknown keys accepted); citations checked by (file, line) only, any repo; `"line":"2"` rejected as fabricated | `"evil"` accepted | Rs |
| M7 | Prompt example JSON invalid (Python `%r` quotes); `link prompts --runner-cmd` splits on spaces (`link run` uses shlex); 2nd call site with same target dropped; `no_match` invisible in text output | `{"task_id": 'link-…'` | Rs |
| M8 | **Every commit duplicates every link**: `_link_id` hashes caller/callee incl. `head` (`link.py:139,302-304`) → refresh keeps the old resolved copy and adds an unresolved one | unrelated commit: 8 → 16 links, each twice, one `NONE` | C/Rs |
| M9 | Concurrent `link run` on one `--db` lose updates (lock is under `CDP_HOME/locks`, not with the db; each writes its full report, last wins), each prints "folded", rc 0. No `--parallel`; same-home runs serialise and redo every task | N=2 kept 4/7 resolutions in 9/10 trials, N=4 kept 2/7 | Rs |
| M10 | Re-anchored call site keeps the old resolution anchor, which now points at a different call | resolution `client.js:4` = the `users` fetch after move | Rs |
| M11 | Flask `<int:uid>` and JS template `${id}` params not normalised → Flask ↔ fetch never links; `link scan --db` requires a value though help says it defaults | 7/7 template fetches `unmatched` | Rs |

## F. Tests
| ID | Defect | Evidence | St |
|---|---|---|---|
| F1 | `run --parallel` crashes (SIGSEGV/SIGBUS/SIGTRAP or "missing artifact 'inventory'"): worker threads read artifacts on one shared sqlite connection (`check_same_thread=False`, `sqlite_backend.py:270`) outside the serial lock (`supervisor.py:255-256`); C stack in `libsqlite3` | outside pytest: N=2 2/5, N=4 6/15 runs fail | R/Rs |
| F3 | Registry/home tests import `helpers`, pass only with `tests/` on PYTHONPATH | ModuleNotFoundError | Rs |
| F2 | Suite (631 tests, 8 fixture repos) has no real-repo layouts: worktrees, subfolders, inheritance, package-private, C# variants, MCP via hook | grep of `tests/` | R |

## Reliability baseline (measured against independent ground truth)
- Java methods (javac): 80% overall; 99–100% with explicit modifier; 0% package-private/interface/constructor. Lines: 309/309 unchanged files exact; changed files stale (A10/A11).
- Java call sites: 60% (B8). C# methods (careful regex): 76%; public 94%, private 1%.
- Python (`ast`, cdp + click): defs 92% / 64%, lines exact; call sites 0% (B19); env reads 8/18 sites.
- Routes: Java 100% (minus context path); C# exact path 41%, handler 90%.
- Tables: Java JPA 7/7, Flyway 7/29, precision 70%; C# 0/18. Config: `.properties` 64/64, code reads 0/30.
- Works: Postgres backend = sqlite (conformance 75/75, 16/16 `--json` outputs byte-identical, concurrent scans/refresh and `run --parallel 2` clean — F1 is sqlite-only); hook contract verified live (PreToolUse `additionalContext` without a decision and PostToolUseFailure context both reach the model); leaf patch schema-valid; scan determinism across homes/worker counts (byte-identical); CLI ↔ MCP parity 26/26; 3,410 doc citations resolve (fresh snapshot); root-level add/delete/rename/rebase refresh; hook JSON contract; hook latency 0.05–0.6 s.

## Open questions
All closed 2026-10-11 (hook events, Python, link runner/parallel/refresh, Postgres, C2 cost, section hash, A12). Not covered: Go/JS/TS recall; AI-claim staleness (C1/C3 measured on deterministic claims only); per-site claim miss rate (0 positive cases).
