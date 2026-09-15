# CDP CLI — Scope to Completion

**Product:** the `cdp` CLI toolset. Stdlib-only Python (`sqlite3` included).
Every front-end — Claude Code skill, LangGraph/ADK app, MCP server, RCA agent — is a
*consumer* of this CLI, never a dependency of it.

Companion: `RESEARCH_GRAPHIFY.md`

### Governing rules

| # | Rule |
|---|---|
| R1 | Everything persists in the store. **Provenance is a column, not a directory.** Files are an export format, not a storage format. |
| R2 | **Structure is per-snapshot and disposable. Claims span snapshots and are precious.** |
| R3 | **`scan` writes, `link` reads.** `link` never mutates snapshot data. |
| R4 | Trajectory corpus is **write-always**. Reading it is versioned and pinned, never live. Leaves never consult it. |
| R5 | Compaction and rollback **archive, never destroy** — and the archive must prove the live state. |
| R6 | **A failed scope becomes an `unknown`, never a silent gap.** Coverage must not lie. |
| R7 | **Config is a file. Data is a table.** |
| R8 | **An anchor surviving is not a claim being fresh.** Two dates, always. |
| R9 | **Never assume — diff.** File changed? The claim needs review. Decide from `git diff`, not elapsed time. |
| R10 | **Learning may steer routing, never claim content.** Verification stays downstream of every decision it makes. |
| R11 | **Humans outrank models on interpretation, never on structure.** A human claim contradicted by extraction is `contested`, not accepted. |
| R12 | **Unknowns are sticky.** Only an adjudicated claim discharges one. Silence never does. |

---

## A. Command surface when complete

| Command | State | Purpose |
|---|---|---|
| `scan` | exists | Deterministic structural index. No LLM. Free. **Now renders docs by default** (`--no-docs`). |
| `prompts` | exists | Write one leaf prompt per scope |
| `collect` | exists | Validate → verify anchors → fold |
| `answer` | **new** | Submit a human claim against an unknown. Same gate as any claim. |
| `query` | exists | Typed queries, file:line answers |
| `query trace` | **new** | Minimal cited file set for an entry point, budgeted |
| `docs` | exists | Render overview, `modules/*.md`, `CLAUDE.md` |
| `status` / `stats` | exists | Coverage, wave state, **per-run task table** |
| `run` | **new** | Supervisor — drives the wave loop, resumable |
| `refresh` | **new** | Rescan + re-verify + fold. Claim decay. |
| `diff` | **new** | Structural diff between two snapshots |
| `link` | **new** | Cross-repo relations — own scan/prompts/collect/refresh/query |
| `rollback` | **new** | Re-fold excluding a run, or up to a snapshot |
| `compact` | **new** | Archive superseded patch history to a cold table |
| `verify --full` | **new** | Re-fold from archive, prove live state hash |
| `doctor` | **new** | Model conformance harness |
| `export` | **new** | Canonical JSON · reviewable patches · archive · anonymised corpus |
| `gc` | **new** | Drop unretained snapshots |
| `help` | **new** | Workflow guidance, not just flags. `--json` makes it machine-readable. |

---

## B. P0 — Storage & schema

| # | Item | Detail |
|---|---|---|
| 0.1 | **Store module boundary** | All SQL in one module. None in `query.py`, `graph.py`, `state.py`. Makes a second backend a small job later, designed against real query shapes. |
| 0.2 | **Workspace store (SQLite)** | Three namespaces: `snapshot.*` (structure — immutable, disposable) · `claim.*` (claims, patches, lineage — precious) · `link.*` (cross-repo — derived). |
| 0.3 | **`patches` table** | Append-only, immutable, content-addressed. Re-collecting an identical patch is a no-op by hash — idempotency for free. |
| 0.4 | **Provenance as columns** | `author_kind` (python\|llm\|human), `model`, `run_id`, `verdict`, `template_version`, `lessons_version`. |
| 0.5 | **Incremental fold** | `state` materialised on insert, not recomputed from history. **Kills the O(all-patches-ever) read** — the real wall at monorepo scale. |
| 0.6 | **Snapshot model** | Identity `(repo_id, commit_sha)`. Dirty tree → allowed but `ephemeral=true` + tree hash, auto-GC, **never citable by a durable claim**. |
| 0.7 | **Claim lineage spans snapshots** | A claim is *anchored at* a snapshot, not *inside* one. This is what makes `refresh` expressible at all. |
| 0.8 | **Two freshness dates** | `anchor_verified_at` (machine-checked, free, updated by refresh) and `claim_reviewed_at` (a model re-read the context; expensive). **Staleness = churn in the anchored file since `claim_reviewed_at`** — not elapsed time, not commit count. A claim about a file untouched for two years is not stale. |
| 0.9 | **Review invalidation (R9)** | Any diff to the anchored file → `claim_reviewed_at` does **not** carry forward. Sole exception: a pure rename (`git diff -M` @100% similarity) — path moved, content identical, anchor relocates, review stands. Rename + edit = review needed. |
| 0.10 | **Snapshot retention rule** | Kept iff **HEAD, pinned, or cited** by a live claim's `last_verified`. One sentence; fully determines `gc`. |
| 0.11 | **Incremental extract** | `git diff --name-status <prev> <new>` → re-extract changed files only, carry the rest forward. Works because `extract_file()` is already pure per-file. **Graph/resolve/dataflow always recomputed** — one moved file can change the whole DAG. |
| 0.12 | **`runs` + `tasks` tables** | `runs(run_id, snapshot_id, partition_hash, status, started_at, finished_at, model, template_version, lessons_version)` · `tasks(run_id, scope_hash, state, attempts, dispatched_at, lease_until, last_error, patch_hash)`. Turns "it didn't work well" into a table. |
| 0.13 | **Separate `link_runs` / `link_tasks`** | In the `link.*` namespace. Keeps R3's non-entanglement test trivially true; independent scaling and audit. |
| 0.14 | **JSON columns + expression indexes** | Claims/patches/link payloads as JSON; `CREATE INDEX … ON claims(json_extract(payload,'$.subject'))`. Document flexibility *and* relational joins in one stdlib engine. |
| 0.15 | **Index set** | `(snapshot_id, fqn)` · `(snapshot_id, file)` · `(snapshot_id, scope_hash)` · expr on `$.subject`, `$.kind` · unique `(repo_id, commit_sha)` · `(run_id, state)` on tasks · `(scope_shape_hash)`, `(run_id)` on trajectories. |
| 0.16 | **Archive as cold table** | `patches_archive`, same DB file, minimal index `(scope_hash, run_id)`. Hot queries never touch it. Read only by `verify --full` and `export --archive`. `VACUUM` after large compactions. |
| 0.17 | **Trajectory store (separate DB)** | `~/.cdp/trajectories.db`. Cross-workspace, cumulative, irreplaceable. Separate file so a workspace rebuild can never destroy it. |
| 0.18 | **Trajectory constellation schema** | Two facts sharing dimensions: `fact_leaf_run` (grain: one run×scope dispatch) and `fact_run_event` (grain: one run-level event — `started`, `finished`, `aborted`, `rolled_back(reason)`, `compacted`). Dimensions: `dim_model`, `dim_scope_shape`, `dim_template`, `dim_repo`, `dim_tier`, `dim_task_kind` (`scope`\|`link`). **Build as a star from day one** — retrofitting after 50k rows is miserable. |
| 0.19 | **`cdp export`** | Canonical JSON (determinism harness) · reviewable patch files on demand · archive dump · anonymised corpus. |

### Why SQLite, not a document or graph DB

| | |
|---|---|
| Data mix | Mostly relational (defines/uses/io_edges — high volume, exact lookup). Two document-ish things (claims, patches). Traversal is **bounded ≤8 hops** over ~10² module nodes; recursive CTEs handle it. |
| Document flexibility | JSON1 is built in. You get it without a server. |
| Upgrade path | **SQLite → Postgres is near-1:1** (JSON, expression indexes, recursive CTEs, MVCC). SQLite → Mongo is a rewrite that loses the joins dominating your volume. |
| LLM-ops workload | Thousands of rows per run, not millions per minute. Document stores win on log throughput — not the constraint here. |
| Outgrow it when | >10M edge rows or multi-writer → Postgres. Unbounded deep traversal → graph DB (not this workload). Semantic search → `sqlite-vec` / pgvector, same shape. |

**Division of labour:** code relationships live in the **workspace store** as normalised tables + JSON contract payloads. The **trajectory star** never models code — it measures the process that discovered it.

---

## C. P1 — Correctness

Small, ships first.

| # | Item | Detail |
|---|---|---|
| 1.1 | **Module detection at scan root** | **Bug, hit in the field.** A manifest at the scan root → zero modules, a bogus `src` module from the fallback, zero declared edges, zero observed edges. Fix: root-with-manifest = one named module. Degrade honestly. |
| 1.2 | **`scan` renders docs by default** | `--no-docs` to opt out. The user-facing half of the same bug: docs were a separate command, so a rescan appeared to produce nothing. |
| 1.3 | **Budget + truncation honesty** | `--budget` on every query · `elided: N` in every response · every response carries `as of commit X, state vY`. ~10 silent-truncation sites in `query.py` today — cosmetic for a human, fatal once an RCA agent gets a clipped "who calls this". |
| 1.4 | **`cdp help`** | Guidance, not flags: when to use what, in what order, what comes next. `cdp help workflows` ships named recipes — onboard a repo · refresh after a sprint · investigate a bug · review a PR. **`--json` makes it machine-readable**, so a LangGraph/ADK front-end discovers the surface without a hand-written adapter. |
| 1.5 | **`cdp answer`** | Human claim against an unknown: `--subject X --kind Y --claim "…" --anchor <file:line>`. Reuses the entire pipeline — validate → verify anchor → entail → fold. `author_kind=human` plus an identity column. Changes merge precedence (R11), **never the gate**. Turns the record from write-only-by-machine into collaborative, and makes institutional knowledge decay honestly like everything else. |
| 1.6 | **`cdp query trace <entrypoint> --budget N`** | The bundle operation every L4 consumer reaches for first: the minimal cited file set needed to answer a question about an entry point. Composes `dataflow.py` traversal + `resolve.py` transpose + the budget work in 1.3. Each file carries the edge that justified its inclusion; unknowns on the path are surfaced, not hidden; `elided: N` is explicit. |

---

## D. P2 — Scale

Monorepo / multi-team pressure. Cheap now, brutal to retrofit.

| # | Item | Detail |
|---|---|---|
| 2.1 | **Scope is the unit, not repo** | `refresh`, `query`, coverage all take a scope selector and touch only that subtree. A monorepo is N indexes sharing a commit. |
| 2.2 | **State materialised per scope** | Composed on read. A team working 3 modules doesn't load 2000 scopes. |
| 2.3 | **Store resolution** | `~/.cdp/config.toml` registry (repo_id → store) is the **default** — zero litter in someone else's checkout. `.cdp.toml` in-repo is **opt-in** for teams: git hooks find it without registration, and a teammate cloning inherits the store URL. Order: `--store` → `CDP_STORE` → `.cdp.toml` walking up → registry → `./.cdp/index.db`. **Repo identity is never the filesystem path** — declared id → normalised origin remote → UUID. Dissolves the old `--in-repo` dilemma. |
| 2.4 | **`cdp compact`** | Superseded rows **move** to the cold table. `--compact-threshold` default **30%**, customisable. `--keep-generations` default **1** — a *generation* is one `(scope, run)` complete patch; since nothing is lost to the archive, this is a performance knob, not a retention decision. |
| 2.5 | **`cdp verify --full`** | Re-fold from archive, compare hash to live state. Makes compaction **provably lossless** rather than asserted. This is the audit story. |
| 2.6 | **Postgres adapter** | Multi-team shared store is its real justification. Near-1:1 port given 0.14. |

---

## E. P3 — Freshness & history

| # | Item | Detail |
|---|---|---|
| 3.1 | **`cdp refresh`** | Rescan → re-verify every anchor → fold. Moved line → relocate, update `anchor_verified_at` **only**. Gone → demote, reason `code changed at <sha>`. **Must be rename-aware (`git diff -M`)** or one `git mv` mass-demotes the corpus. Requires moving verification from append-time into `fold`. |
| 3.2 | **`cdp diff`** | New/removed modules and edges, moved anchors, coverage regression. One build, three consumers: refresh, reviewer agent, CI/CD agent. |
| 3.3 | **Scope-hash caching** | Unchanged hash → reuse claim, skip agent. Also fixes a real defect: re-running a node today **accumulates** rather than replaces (both patches `complete`, neither supersedes the other). |
| 3.4 | **`cdp rollback`** | `--to-run R` re-folds excluding R's patches; `--to-snapshot S` re-folds up to S. Excluded patches marked `superseded_by_rollback`, never deleted. Writes `fact_run_event(rolled_back, reason)` — the run still happened; nothing is retracted. |
| 3.5 | **`query --as-of <commit\|time>`** | Free consequence of immutable patches + deterministic fold: **state at any point = fold(patches up to that point)**. |
| 3.6 | **Staleness signal** | Churn in the anchored file since `claim_reviewed_at` (`git log --numstat`) → a deterministic input to routing (4.8). `status` reports **"anchored but unreviewed"** as its own bucket. |
| 3.7 | **Git hooks** | `post-commit` / `post-checkout` → auto-refresh via the store pointer. |

---

## F. P4 — Runner, portability & resumability

| # | Item | Detail |
|---|---|---|
| 4.1 | **Runner protocol** | `prompts → [any LLM, any framework] → inbox → collect`. ~50-line documented interface. Core imports no framework, ever. **This is the entire de-vendoring job.** |
| 4.2 | **Digest-first leaves** | Digest is the input; reading source becomes an explicit, logged escalation. **Three wins from one build:** portability (leaf = text-in/JSON-out, no tools, any model incl. local), determinism (anchors become references — fabrication structurally impossible, not merely detectable), cost. New metric: **escalation rate**. |
| 4.3 | **`cdp run`** | Supervisor as a component: read schedule, dispatch, collect, retry, resume. A map-reduce with a validation gate — **not an agent graph**. Stdlib, no framework. |
| 4.4 | **Task state machine** | `pending → dispatched → returned → validated → folded`, with `expired` / `invalid` / `anchors_failed` / `empty` → retry → `abandoned`. Each failure has a **different remedy**; conflating them is why failures are undiagnosable today. |
| 4.5 | **Leases** | **Held by the supervisor, not the leaf.** Heartbeat 30s, lease 90s → supervisor death detected in 90s regardless of tier. Fallback for stateless runners: tier-derived ceiling, **learned empirically** from `dispatched_at` + `wall_ms` p99 per `dim_tier` rather than guessed. |
| 4.6 | **`--resume` + partition-drift guard** | `runs.partition_hash` matches → resume. Differs → **new run**, inheriting completed scopes whose *scope hash* is unchanged, re-queueing the rest. Prevents folding stale work against a changed partition. |
| 4.7 | **`--max-attempts` default 3** | Configurable. On exhaustion the scope surfaces as an honest `unknown`, not missing coverage (R6). |
| 4.8 | **Tiering → residue score** | Tiers: T0 structure (free) → T1 derived characterisation (free) → T2 label from digest (cheap, **local model**) → T3 semantic read (frontier, residue only). **v1 ships a rule, not a score:** everything gets T2; escalate to T3 only when the leaf escalates or the scope has unresolved imports. The *residue score* — "how much of this scope can Python already explain by itself?" — arrives only once calibrated (see §N). Doubles as the privacy story: local for T2, escalate nothing sensitive. |
| 4.9 | **Measure fixed overhead → batch** | Each leaf pays system prompt + tool defs before reading anything. If ~10k, 17 leaves ≈ 170k overhead scaling with **scope count, not code size**. **Unverified — measure first.** If it holds, batch 6–8 scopes per call; bounded scope is a property of the prompt, not the process. |
| 4.10 | **`cdp doctor`** | Extend the `minirepo` golden test into model qualification: schema validity, anchor survival, entailment rate, recall vs golden, **and false-unknown rate** — unknowns emitted where the golden set has an answer. Recall alone is not enough: a model that answers "unknown" to everything scores perfectly on precision. Publish a compatibility table. **The gate on "works with any LLM."** Failure mode is **yield collapse**, not corruption — 17 leaves in, 3 claims out, 14 nodes of unknowns. |

---

## G. P5 — Cross-repo relations

Mirrors the core loop; reuses the runner protocol.

| # | Item | Detail |
|---|---|---|
| 5.1 | **`cdp link scan`** | Deterministic: gather `http_out/http_in`, `event_publish/subscribe`, `persist/schema_own` edges across registered snapshots; match on path / topic / table. |
| 5.2 | **`cdp link prompts` / `collect`** | LLM tier for ambiguous matches only — base URL from env vars, topic built by concatenation. |
| 5.3 | **`cdp link refresh` / `query`** | Re-verify against new snapshots. Query: who calls this service, what publishes to this topic. |
| 5.4 | **Link schema** | `match_kind`: `exact` \| `heuristic` \| `unmatched`. Contract: protocol, path/topic/table, direction, payload shape. Plus findings, unknowns, metadata. |
| 5.5 | **Links are between *snapshots*** | Repo A@X talks to repo B@Y. Not a graph over repos — a graph over pinned commits. |
| 5.6 | **`unmatched http_out` is a deliverable** | A call to something outside the scanned set. Often the most interesting output on a microservice estate. |
| 5.7 | **Non-entanglement test** | Assert: drop every `link.*` row → no snapshot changes. R3 as an executable test, not a promise. |

---

## H. P6 — Trust, reflection, learning

| # | Item | Detail |
|---|---|---|
| 6.1 | **Entailment validation** | Second gate beyond "does the anchor resolve": **does the deterministic layer agree?** `entailed` (backed by an existing `io_edge`/`defines`) · `consistent` (no opinion) · `contradicted` (reject + log). The contradicted bucket is gold — every entry is an agent error or an extractor gap. Also the reward signal all learning needs. |
| 6.1b | **Negative entailment** | The same machinery, inverted, applied to unknowns: **if the deterministic layer can already answer it, the unknown is invalid.** Agent says "I don't know what table this writes" while a `persist` io_edge sits in xref for that scope → reject. Free, and it kills the cheapest category of false unknown outright. See *Unknown discipline* below. |
| 6.2 | **PreToolUse hook + `--strict`** | Makes "prefer the index over grep" enforced, not requested. Scoped to `role == "source"` using the existing inventory classification. |
| 6.3 | **Trajectory corpus** | Joined on scope_hash. **Input fingerprint** (at `prompts`): template version, rows included/elided, sigma claims, prompt tokens by section, tier, digest-vs-source. **Output scorecard** (at `collect`): tokens, retries, escalations, claims emitted/surviving, entailed/consistent/contradicted, unknowns, wall time. Same grain as `tasks` — one writes for recovery, the other for learning. |
| 6.4 | **Elision regret** | When a leaf escalates or emits `unknown` — **was the answer in a row the budget elided?** Grades the ranking function in `prompts.py`, currently an unvalidated guess that decides what every leaf on every repo gets to see. |
| 6.5 | **Routing prior** | Nearest-neighbour matched on scope **shape**, not identity. Falls out as a `GROUP BY` over `dim_scope_shape` — the star makes this nearly free. Deterministic, no model. Works for `link` too via `dim_task_kind`. |
| 6.6 | **Outlier reflection** | LLM call only on high-spend/low-yield or high-contradiction scopes. Handful per run. Output should be a **deterministic promotion** — a new `IMPORT_CHANNEL_HINTS` entry, a prompt fix, a budget change — not a vague lesson in a store. |
| 6.7 | **Lesson-sets: cut, versioned, on by default from run 2** | The corpus accrues continuously, but a lesson-set is **cut and numbered** at intervals. A run pins `lessons: v7` in its manifest; re-running with `--lessons v7` reproduces exactly. Default is *latest cut*, not *live corpus*. Off for run #1 (no corpus), auto-on thereafter, `--no-lessons` to opt out. **Safe because of R10** — lessons steer routing, never claim content; verification stays downstream. |
| 6.8 | **Holdout benchmark** | A/B on a pinned snapshot: `--lessons none` vs `--lessons vN`. **Learn on repos A–E, benchmark on F**, or you're measuring memorisation. Gates whether a cut is promoted to latest. |

---

### Unknown discipline

**The asymmetry:** claims are falsifiable, unknowns are not. A claim says "X is at line 47" — open the
file and check. An unknown says "I don't know why this retries" — there is nothing to open. The verifier
is structurally blind to the entire unknowns array.

You cannot validate an unknown's *content*. You validate everything around it.

**Four deterministic gates** — all free, all run in `collect`:

| Gate | Check |
|---|---|
| Subject exists | The unknown must name a subject present in `defines[]`/`io_edges`. If not, it's about nothing. |
| **Negative entailment** (6.1b) | If extraction can answer it, reject it. |
| Provenance state | `unexamined` (no agent ran — from coverage) vs `unknown` (agent ran, couldn't tell) vs `abandoned` (agent ran, failed 3×). Today all three look identical; `tasks` (0.12) separates them. |
| Clustering | The same unknown across 40 scopes is one systemic gap — a weak extractor — not 40 findings. |

**No verification service.** An LLM judging another LLM's "I don't know" is unverifiable all the way
down. Grounding is deterministic, human (`cdp answer`, 1.5), or **runtime** — traces and logs are the
only genuinely new evidence source, and that join lives in the RCA agent, outside CDP core.

**Compliance bias.** An unknown is cheap to emit and impossible to falsify, and CDP *praises* honest
absence — so the incentive is perverse. Three countermeasures:

| # | Countermeasure |
|---|---|
| 1 | Negative entailment — kills the cheapest category |
| 2 | **An unknown must state what would resolve it.** Closed vocabulary: `needs_runtime` · `needs_external_doc` · `needs_human` · `needs_wider_scope` · `needs_other_repo`. One that can't say is **malformed and rejected.** Raises the price of the easy out — and makes unknowns *routable*: `needs_wider_scope` escalates the tier, `needs_other_repo` becomes a `link` task. |
| 3 | False-unknown rate in `doctor` (4.10), tracked per `dim_model` × `dim_template` in the star so a prompt regression shows up immediately |

**The ratchet (R12):**

| Rule | |
|---|---|
| Only an adjudicated claim discharges an unknown | agent re-run or `cdp answer` — both pass validate → verify → entail → fold |
| **Silence does not discharge** | a later patch that simply omits it does *not* resolve it |
| Subject disappears → `moot`, not `resolved` | different outcome, recorded separately, matters for audit |
| Discharge is attributed | `resolved_by(claim_id, author_kind, at_snapshot)` — who decided, when, on what basis |
| Rollback restores unknowns | it's a re-fold; nothing special needed |

**Stated limit.** You cannot validate whether the unknowns are *complete* — whether an agent failed to
notice something it didn't know it didn't know. That is unknowable by construction. The only proxies
are coverage (was this scope examined at all) and `doctor`'s recall against a golden set. This belongs
in user-facing docs, not just here.

---

## I. P7 — Distribution

| # | Item | Detail |
|---|---|---|
| 7.1 | **MCP server (stdio)** | **3 tools, not 13**: `cdp_query` (typed `kind` param), `cdp_scan`, `cdp_status`. Reference point: `idea`+`pycharm` MCP servers consume **49.2k tokens permanently** in a live session. A token-reduction product must not cost tokens at rest. |
| 7.2 | **LiteLLM adapter** | One adapter ≈ 100 providers + local via Ollama/vLLM. Highest coverage per unit of work. |
| 7.3 | **Claude Code skill** | Keep it. Best UX today. Only lock-in if it's the *only* front-end. |
| 7.4 | **LangGraph / ADK adapters** | On demand. These earn their place at L4 consumers (RCA, reviewer), not in the core. Bootstrapped by `cdp help --json` (1.4). |

---

## J. What we took from Graphify

| Graphify feature | Taken? | Lands at | How ours differs |
|---|---|---|---|
| `EXTRACTED`/`INFERRED`/`AMBIGUOUS` provenance | ✅ **best single idea** | **6.1** | Applied to *claims* vs deterministic extraction, not just to edges |
| `query --budget` | ✅ | **1.3** | Plus mandatory `elided: N` — they don't report what was dropped |
| `PreToolUse` hook + `--strict` | ✅ | **6.2** | Scoped to `role == "source"`; theirs fires on any read |
| Git `post-commit`/`post-checkout` hooks | ✅ | **3.7** | Drives `refresh` with claim decay, not just re-index |
| MCP server | ✅ | **7.1** | 3 tools vs their 7 |
| Memory layer (`save-result`/`reflect`) | ✅ **reshaped** | **6.3–6.8** | Ours is SQL over recorded telemetry; model only on outliers; cut and versioned. Theirs is agent-authored memory. |
| Union merge driver | ❌ **dropped** | — | Solved single-repo sharing. Multi-team wants a shared store. Superseded by 0.3 + 2.6. |
| tree-sitter (~37 grammars) | ❌ | — | Kills stdlib-only, the actual adoption advantage |
| Leiden clustering for modules | ❌ | — | We read modules from build manifests — ground truth, not inference |
| Their token-reduction headline | ❌ | — | Their own `BENCHMARKS.md`: reduction "was not computed as a standalone metric" |

---

## K. Dependency order

```
0.1 store boundary
  ├─→ 0.2/0.3 tables ─→ 0.5 incremental fold ─→ 0.6 snapshots ─→ 0.7 lineage
  │                                                 │              └─→ 0.8 two dates ─→ 0.9 R9 rule
  │                                   ┌─────────────┼─→ 0.10 retention ─────→ gc
  │                                   │             ├─→ 0.11 incremental extract
  │                                   │             ├─→ 2.1 scope selector ─→ 2.2 per-scope state
  │                                   │             ├─→ 3.1 refresh ────────→ 3.3 scope-hash cache
  │                                   │             ├─→ 3.2 diff
  │                                   │             ├─→ 3.4 rollback ───────→ 3.5 query --as-of
  │                                   │             ├─→ 3.6 staleness ──────→ 4.8 tiering
  │                                   │             └─→ 5.1 link scan
  │                                   └─→ 0.12 runs+tasks ─→ 4.4 state machine ─→ 4.5 leases
  │                                       0.13 link tables       └─→ 4.6 resume ─→ 4.7 max-attempts
  └─→ 0.16 cold table ─→ 2.4 compact ─→ 2.5 verify --full

0.17/0.18 trajectory constellation ─┐
6.1 entailment ─────────────────────┴─→ 6.3 corpus ─→ 6.4 regret ─→ 6.5 prior
                                                                      └─→ 6.7 lesson cuts ─→ 6.8 holdout
                                                                            └─→ residue score (§N)

4.1 runner protocol ─┬─→ 4.2 digest-first ─┬─→ 4.8 tiering
                     │                     └─→ 4.10 doctor
                     ├─→ 4.3 cdp run
                     ├─→ 5.2 link prompts/collect
                     └─→ 7.2–7.4 adapters

1.3 budget ───────────→ 7.1 MCP
1.4 help --json ──────→ 7.4 adapters
2.3 store resolution ─→ 3.7 git hooks ─→ 6.2 PreToolUse hook

1.1 / 1.2 the field bug — independent, ship anytime
```

---

## L. If you only do five

| Rank | Item | Why |
|---|---|---|
| 1 | **1.1 + 1.2** module detection + docs on scan | The bug you actually hit, both halves |
| 2 | **0.1–0.12** store, incremental fold, snapshots, lineage, runs+tasks | Upstream of everything. The O(history) fold is a wall, not a slowdown. |
| 3 | **3.1** refresh | Freshness *is* the product |
| 4 | **4.2** digest-first | Portability + determinism + cost in one build |
| 5 | **6.1 + 6.3** entailment + corpus | The only items that tell you whether the agent spend bought anything |

---

## M. Decisions settled

| Decision | Resolution |
|---|---|
| Storage engine | SQLite default; store-module boundary; Postgres adapter when multi-writer |
| Patch log | Table, not directory. Union merge driver dropped. |
| Compaction | Cold table in the same DB, `--compact-threshold 30%`, `--keep-generations 1`, exportable, provable via `verify --full` |
| Repo → store pointer | Registry default, `.cdp.toml` opt-in. Config is a file; data is a table. |
| Claim freshness | Two dates. Staleness = churn, not time. Any file diff invalidates review; pure rename @100% does not. |
| Max attempts | 3, configurable; exhaustion → `unknown` |
| Rollback + trajectory | Nothing retracted; `fact_run_event(rolled_back, reason)` appended |
| Lease duration | Supervisor-held, 30s heartbeat / 90s lease; stateless fallback learned from p99 per tier |
| Link runs/tasks | Separate operational tables; shared analytical star via `dim_task_kind` |
| Docs | Rendered by `scan` by default; `--no-docs` opts out |
| Guidance | `cdp help` covers when/where/how; `--json` bootstraps front-ends |
| Lessons | Cut + versioned + pinned. Off for run 1, on by default after, `--no-lessons` opts out. Routing only, never claim content. |
| Tiering v1 | A rule, not a score. Residue score deferred until calibrated. |
| Human claims | `cdp answer`, anchored, same gate, `author_kind=human`. Outranks models on interpretation only (R11). Decays like any claim. |
| Unknown validation | Four deterministic gates. No verification service — an LLM judging an LLM is unverifiable. |
| False unknowns | `needs_*` closed vocabulary is mandatory; false-unknown rate gates model qualification |
| Unknown lifecycle | Sticky (R12). Only an adjudicated claim discharges. Subject gone → `moot`, not `resolved`. |

---

## N. Residue score — the calibration process

Deferred deliberately. The inputs are decided; the coefficients are not, and guessing them would put an unvalidated number on the critical path.

| Stage | Available | Action |
|---|---|---|
| **v1** | nothing | **No score.** Everything gets T2. Escalate to T3 only on unambiguous signals: the leaf escalated, or the scope has unresolved imports. A rule. |
| **v2** | `fact_leaf_run` rows | Run a **sample of scopes at both T2 and T3.** Measure the delta in *novel* claims (surviving, non-entailed). Delta ≈ 0 → that scope never needed T3. Produces labelled data. |
| **v3** | ~few hundred labels | Fit features → label with **logistic regression** — not a neural net, because the coefficients must be readable ("unresolved count matters 3× more than LOC") in a product built on explainability. |
| **v4** | growing corpus | Re-fit periodically. Weights ship as a versioned artifact pinned like lesson-sets. |

**Candidate features**, all already computed: channel diversity · fan-in/fan-out · role mix · LOC per definition · `unresolved` count · churn since `claim_reviewed_at` · comment density.
