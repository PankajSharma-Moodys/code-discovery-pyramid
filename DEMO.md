# CDP Demo Script

## 1. Product description

CDP (Codebase/Dependency... — actually "Continuous Documentation Protocol"-style tool, referred to throughout as "cdp") reconstructs undocumented architecture from a codebase and answers questions about it with file:line citations. Instead of an LLM re-reading and re-guessing a repo's structure every session, `cdp scan` runs a deterministic extraction pass once (imports, defines, io_edges, routes, dataflow) and dispatches bounded "leaf" agents over real scopes to produce anchored, verifiable claims — every claim traces to a literal source-text citation that's mechanically re-verified, not trusted. The output is a queryable, versioned index (`cdp query`, `cdp docs`) that stays cheap to consult afterward, and that re-verifies itself against new commits (`cdp refresh`) rather than going stale.

## 2. Distinction from other products

- **Anchored, not vibes-based**: every claim carries a literal source-text span (12–400 chars) that's independently re-verified against the real file — a claim whose anchor doesn't resolve is automatically demoted to an `unknowns[]` entry, never silently kept. This is the core discipline (R-rules like R4, R9, R10, R12 in the design docs) that most "AI documents your codebase" tools don't have.
- **Explicit unknowns are first-class output, not failure** — "who owns the retry policy for X" is treated as valuable as a resolved claim, because it names exactly where the knowledge gap lives.
- **Deterministic core, LLM only where it adds value** — extraction/dataflow/routing/tiering are all plain code; the model is only spent on bounded leaf reads and rare high-value reflection, not on every query.
- **Token-frugal by design** — the MCP surface is capped at exactly 3 tools (`cdp_query`, `cdp_scan`, `cdp_status`) specifically because reference tools like idea/pycharm MCP servers were found to burn ~49.2k tokens at rest; a token-reduction product can't itself cost tokens sitting idle.
- **Learning that can't corrupt truth (R10)**: the trajectory/lesson-set mechanism can only steer *routing* (which import patterns count as third-party, prompt hints, budget knobs) — it is structurally incapable of altering claim content, enforced by test, not convention.
- **Portable without lock-in**: works via CLI/hooks for Claude Code, but also ships an MCP server, a LiteLLM adapter (~100 providers + local models), LangGraph/ADK adapters, and a Tier-0 `AGENTS.md` path for assistants with no hook or subagent capability at all (Cursor, Copilot, Aider) — a shell and Python 3.9 is enough.

## 3. High-level technical overview + DB schema

Pipeline: `scan` (walk repo, classify modules/files) → `extract` (per-language: defines, imports, io_edges) → `graph`/`dataflow` (symbol resolution, cross-file edges) → `partition` (scopes/waves for leaf dispatch) → leaf dispatch (`prompts`/`collect`, bounded reads, schema-valid patches) → `fold` (merge patches into state, entailment verification) → query surface (`query`, `docs`).

Two storage layers:
- **Workspace store** (`.cdp/index.db`, SQLite/Postgres/File backends) — one repo's current extracted state: claims, unknowns, conflicts, patches, snapshots, run/task tracking for `cdp run`'s wave scheduler, leases for concurrent dispatch.
- **Trajectory store** (`~/.cdp/trajectories.db`, separate, cross-workspace, cumulative — deleting a workspace can never destroy it) — a star schema: `fact_leaf_run` (grain: one run × scope dispatch — tokens, retries, escalations, claims emitted/entailed/contradicted, elision regret) and `fact_run_event` (run-level started/finished/aborted/rolled_back/compacted), against dimensions `dim_model`, `dim_scope_shape`, `dim_template`, `dim_repo`, `dim_tier`, `dim_task_kind`. This is what routing priors, elision-regret measurement, and lesson-sets (`lesson_promotion`/`lesson_cut` tables) are built on.

## 4. Exposed functionality (commands, example, workflow, DB side effects)

- `cdp scan --repo <path>` — walk + extract + partition. Side effect: creates `.cdp/index.db`, populates inventory/extraction/partition/graph tables.
- `cdp query <stats|trace|unknowns|...> --repo <path>` — read-only answers from the index. No side effect.
- `cdp docs --repo <path>` — renders module-level markdown docs from state. Writes doc files, no DB mutation.
- `cdp prompts --wave N` / `cdp collect` — builds leaf prompts, accepts patches into an inbox. Side effect: writes patch files; `collect` validates and stages them.
- `cdp run --wave-all --runner-cmd "<leaf runner>"` — drives the full dispatch loop (prompts → runner → collect → fold) through the task state machine, with leases for crash recovery and `--resume` support. Side effect: `snapshot_task`/lease rows, folded claims into state, `fact_leaf_run`/`fact_run_event` rows in the trajectory DB.
- `cdp refresh --repo <path>` — re-verifies existing claims against a new commit without a full re-scan (rename-aware). Side effect: updates `claim_reviewed_at`/anchors, demotes anything that no longer resolves.
- `cdp diff <old_state> <new_state>` — structural delta between two snapshots. No side effect (read-only over two stores).
- `cdp rollback --to-run <run_id>` — append-only exclusion of a bad run's patches. Side effect: writes to an exclusion ledger; nothing is deleted.
- `cdp compact` / `cdp verify --full` — archive superseded patch generations / hash-check the archive. Side effect: moves rows to `claim_patches_archive`.
- `cdp lessons cut` / `cdp holdout --lessons N` — freeze pending trajectory promotions into a numbered, pinned lesson-set; A/B it against a held-out repo before promoting it to "latest". Side effect: `lesson_cut`/`lesson_promotion.cut_version` writes.
- `cdp link scan` — cross-repo/cross-module persistence-edge matching (e.g., which service owns a table another service also touches).

## 5. Why SQL storage

- **Structural facts are inherently relational** — claims, evidence spans, conflicts, unknowns, and now the trajectory star schema are naturally normalized rows with foreign keys (scope → claim → evidence), not documents; SQL gets joins, `GROUP BY` routing priors, and referential integrity for free instead of reimplementing them.
- **Content-addressing and snapshot lineage** need atomic, transactional writes (a fold must not half-apply), which SQLite/Postgres give by construction.
- **Determinism and diffability**: canonical-JSON comparison over query results is what proves two independent scans agree byte-for-byte — a relational store with stable ordering makes that check straightforward.
- **Multiple backends, same guarantees** — SQLite (default, zero-ops), Postgres (concurrent/shared), and a plain-File backend all satisfy the same interface, so the storage choice doesn't dictate deployment shape.
- **No vector store, on purpose** — CDP's stated position is that anchored, verifiable text beats embeddings for this problem; a relational schema is the natural fit for a system whose central claim is "every fact is a citation," not "every fact is a similarity match."