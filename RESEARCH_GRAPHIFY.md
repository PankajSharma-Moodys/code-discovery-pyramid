# RESEARCH_GRAPHIFY — what CDP can learn from Graphify

**Date:** 2026-09-14
**Subject:** [Graphify-Labs/graphify](https://github.com/Graphify-Labs/graphify) (default branch `v8`, Apache-2.0 + MIT, PyPI `graphifyy`)
**Purpose:** Identify what a mature peer system does better than CDP, and convert that into a ranked, stress-tested maturation plan for CDP.
**Status:** Research only. No code was written or changed.

---

## 0. Method and epistemic status

### What I read

**CDP (primary source, read in full or near-full):**
`SKILL.md`, `agents/cdp-leaf.md`, and `cdp/{cli,query,partition,prompts,derive,resolve,dataflow,merge,state,verify,anchor,graph,schedule,inventory,extract,schema}.py`, `cdp/lang/{__init__,base}.py`, plus the head of `cdp/docs.py`. Every CDP claim in this document carries a `file:line` citation so you can check it.

**Graphify (secondary source, read via web):** `README.md` (62.7 KB), `ARCHITECTURE.md`, `BENCHMARKS.md`, `docs/how-it-works.md`, `docs/node-summaries-rfc.md`, the GitHub API repo metadata, plus four third-party write-ups.

### What I could **not** verify

| Claim | Status |
|---|---|
| Graphify's source code behaviour | **Unverified.** I read its docs, not its Python. Every "Graphify does X" below means "Graphify's own documentation states X." |
| The `71.5×` token-reduction headline | **Unsubstantiated as published.** See §3. |
| Repository popularity | **Anomalous — do not weight it.** The GitHub API returns 116,375 stars / 11,368 forks / **1 watcher**, created 2026-04-03. A five-month-old repo with 116k stars and one watcher is not a plausible organic profile. Secondary sources report 3.7k, 22k, 58.3k and 116k stars, and disagree on license (MIT vs Apache-2.0) and install command. Judge the design on the design. The design is genuinely good; the social proof is not evidence. |
| Whether CDP currently has any harness hooks configured | **Unverified.** My read access was scoped to `.claude/skills/cdp/`; I could not inspect `.claude/settings.json`. §7.1 assumes no hook exists. |

---

## 1. Executive summary

CDP and Graphify make **the same core bet**: run deterministic local extraction once, produce a queryable index, and have the agent query the index instead of reading files. Neither uses embeddings. Neither sends code to a model. That convergence is worth noting — it means CDP's founding thesis is not idiosyncratic.

The difference is *where* each system invested its maturity.

> **Graphify is more mature in surface area and distribution. CDP is more mature in epistemics.**

CDP's anchor verification, `unknowns[]` inventory, order-independent merge operator, fold invariant and declared-vs-observed divergence analysis have **no counterpart in Graphify**. Those are not features Graphify chose not to build; they are a different and stricter theory of what an index is for. Do not trade them away.

But four gaps in CDP map directly onto the user's stated goal — *reduce tokens per call* — and Graphify has a shipped answer for each:

| # | Gap | Graphify's answer | CDP today |
|---|---|---|---|
| **1** | **The index is advisory.** CDP asks the model nicely to prefer the index over grep. | `PreToolUse` hook intercepts Read/Grep/Glob and redirects; `--strict` blocks the first raw read of a session. | `SKILL.md:50-54` — prose only. |
| **2** | **Freshness is manual.** State goes stale silently. | post-commit + post-checkout git hooks, `--watch`, a git merge driver that union-merges the graph. | `SKILL.md:66-67` — "re-scan when the working tree has moved." |
| **3** | **Output is unbudgeted and silently truncated.** | `query --budget 1500`, `GRAPHIFY_MAX_OUTPUT_TOKENS`. | Hard-coded, inconsistent per-renderer caps; several truncate with no "N more" marker. See §10. |
| **4** | **The founding claim is unmeasured.** | `BENCHMARKS.md` — a graded, judge-validated harness with a published spend ledger and honest caveats. | `PLAN.md C2` declares tokens unmeasurable in-session; uses `source_loc_scheduled` as a proxy (`schedule.py:89-93`). |

Gaps 1 and 4 are the two that matter most. Gap 1 is the largest single token lever available to CDP and costs the least to close. Gap 4 is what turns "CDP reduces tokens" from a design intention into a claim you can defend.

---

## 2. What Graphify actually is

### Pipeline (from `ARCHITECTURE.md`, `docs/how-it-works.md`)

```
detect() → extract() → build() → cluster() → analyze helpers → report.generate() → export.to_*()
```

Three passes, only one of which costs money:

- **Pass 1 — code (free).** tree-sitter parses locally: classes, functions, imports, call graphs, inline comments. ~25 languages parsed; cross-file `calls`/`imports`/`inherits`/`mixes_in` resolved across ~40. SQL gets dedicated handling (tables, views, FKs, JOINs). **Code never reaches an LLM.** If a corpus is code-only, Pass 3 is skipped entirely.
- **Pass 2 — audio/video (free, local).** faster-whisper, with the transcription prompt primed by the top "god nodes" from Pass 1 to bias toward domain vocabulary. Nice trick; irrelevant to CDP.
- **Pass 3 — docs/PDFs/images (paid).** Parallel LLM subagents emit JSON node/edge fragments that merge into the graph.

### Data model

`graph.json` in NetworkX node-link format.
- **Nodes:** `id`, `label`, `file_type`, `source_file` (+ `source_location`).
- **Edges:** `source`, `target`, `relation` (`calls|imports|uses|…`), `confidence`, `confidence_score`, `source_file`.
- **Hyperedges** (3+ nodes) in `G.graph["hyperedges"]`.
- `validate.py` checks this shape before `build()` consumes it.

### Provenance model

Three tags, assigned at extraction time:
- `EXTRACTED` — explicit in source. Score always `1.0`.
- `INFERRED` — resolved by graphify (cross-file resolution, co-occurrence). Scored `0.95` near-certain / `0.85` strong / `0.75` reasonable / `0.65` weak / `0.55` speculative.
- `AMBIGUOUS` — flagged for human review in `GRAPH_REPORT.md`.

**Critical observation: nothing re-opens the file to check.** The confidence tag is the extractor's own self-report. CDP's `verify.py` is a categorically stronger mechanism — see §8.1.

### Clustering and analysis

Leiden (via graspologic) over edge density — explicitly *not* embeddings, on the argument that LLM-extracted `semantically_similar_to` edges already shape the communities. Analysis helpers: `god_nodes(G)`, `surprising_connections(G)`, `suggest_questions(...)`, `find_import_cycles(G)`, `graph_diff(G_old, G_new)`. `--exclude-hubs 99` drops p99-degree nodes because hubs distort clustering.

### Query surface

- `graphify query "<question>"` → scoped subgraph. Flags: `--dfs`, `--budget 1500`.
- `graphify path A B` → `Shortest path (3 hops):` with per-hop direction arrows and relation labels.
- `graphify explain "<node>"` → `Node:` / `Source: routing.py L2210` / `Community:` / `Degree:` then `Connections (47):`, each edge tagged `[uses] [INFERRED]`.
- **MCP server:** `query_graph`, `get_node`, `get_neighbors`, `shortest_path`, `list_prs`, `get_pr_impact`, `triage_prs`. stdio or HTTP with `--api-key`.

### Harness integration — the part CDP lacks entirely

- Install writes `CLAUDE.md` **plus a `PreToolUse` hook** (`graphify hook-guard`) that fires before search-style calls and before Read/Glob, injecting a nudge toward `graphify query`.
- `install --project --strict` upgrades the nudge to a **block on the first raw source read of a session**, then falls back to the soft nudge — "triggers at most once per session, never gets stuck."
- Runtime toggle `GRAPHIFY_HOOK_STRICT=1|0`.
- Per-harness degradation is documented and deliberate: Codex's `PreToolUse` entry is **a no-op** because Codex Desktop rejects `hookSpecificOutput.additionalContext`; `AGENTS.md` carries the guidance instead. Trae has no `PreToolUse` at all. Gemini CLI uses `BeforeTool`; OpenCode/Kilo use a `tool.execute.before` plugin.

### Freshness

- `graphify hook install` → post-commit + post-checkout hooks, **plus a git merge driver that union-merges `graph.json`** so committed graph state never produces conflict markers.
- Commits trigger a background AST-only rebuild at zero API cost. Branch switches rebuild. `git checkout -- <path>` does not.
- `git pull` / `git merge` is the documented manual step (`graphify update .`).
- The hook embeds the absolute interpreter path at install time so it survives GUI git clients and CI.
- `--update` re-extracts only changed files; `--force` permits overwriting when the new graph has fewer nodes; `--allow-partial`; a shrink guard on `--no-dedup` incremental merges.
- SHA256 content fingerprints in `graphify-out/cache/`.

### Memory layer

`save-result --question --answer --nodes --outcome {useful|dead_end|corrected}` → `graphify-out/memory/`. `reflect` aggregates into `reflections/LESSONS.md` and writes a work-memory overlay `.graphify_learning.json` tagging nodes `preferred`/`tentative`/`contested`, recency-weighted. `explain`/`query` then surface a `Lesson:` hint, **marked "code changed — re-verify" when the source has moved on.**

### Node-summaries RFC — Graphify naming its own gap

`docs/node-summaries-rfc.md` is the most useful document in the repository for CDP's purposes, because it states the problem precisely:

> `graph.json` provides structure, source files, labels and relationships — enough to spare agents from reading a whole repository, but **not enough to answer "What is this file or node responsible for?" Agents end up opening raw files anyway.**

That is the exact gap CDP's leaf agents already fill, with anchored, verified, merge-resolved claims. **CDP is ahead of Graphify's roadmap here, not behind it.** But the RFC carries two lessons worth taking (§7.6, §7.10).

---

## 3. The token-economics reality check

This section matters most, because token reduction is CDP's founding premise and the peer system's headline number does not mean what it appears to mean.

### The `71.5×` figure

From `docs/how-it-works.md`, measured on a **52-file mixed corpus** (Karpathy repos + 5 papers + 4 images, ~92k words) yielding 285 nodes / 340 edges / 53 communities: average query ~1.7k tokens vs ~123k naive = **71.5×**.

The same document immediately reports the scaling curve, and this is the honest and important part:

| Corpus | Reduction |
|---|---|
| 52 files (mixed: code + papers + images) | **71.5×** |
| 4 files (graphify source + Transformer paper) | **5.4×** |
| 6 files (synthetic Python library) | **~1×** |

Their own conclusion: on small corpora the payoff is *"structural clarity, not compression."*

### What `BENCHMARKS.md` actually says

This is the finding that should change how CDP frames itself:

> **"Token reduction was not computed as a standalone metric."**

The measured code-intelligence result is:

- Agent: Claude Opus 4.8, capped at **14 turns**, given grep/read/list as baseline **plus one graphify tool**.
- Corpus: ERPNext, ~1M lines Python.
- Result: key-fact coverage **70.8% (grep baseline) → 82.0% (graphify-assisted)**, at **~140K tokens per query**.
- **n = 6 questions.**
- The only comparative token claim: stuffing the whole repo into every turn costs "roughly 20× the tokens for lower coverage."

### Four conclusions for CDP

1. **The defensible claim is coverage, not compression.** The peer system's own measured result is *+11.2 points of answer coverage*, not a token ratio. Token reduction is real but is a second-order consequence of a better retrieval path. CDP should lead with correctness-per-token, not tokens.
2. **~140K tokens/query is not small.** If that is what a mature graph system costs on a 1M-line repo, CDP's claim to "reduce tokens per call" needs a number attached or it is unfalsifiable.
3. **There is a crossover point where the index costs more than it saves,** and Graphify puts it somewhere below ~50 files. CDP should find its own. `cdp scan` is free, so CDP's crossover is *lower* than Graphify's — but the *leaf-agent pyramid* (17 agents on a 391-file repo, per `SKILL.md:92-95`) has a much higher one.
4. **CDP's `source_loc_scheduled` proxy (`schedule.py:89-93`) is honest but insufficient.** It bounds what agents are *authorised to read*, which is the right deterministic proxy for pyramid cost — but it says nothing about the `scan`+`query` path, which is where the token savings actually live and where the vast majority of usage will be.

---

## 4. What CDP actually is (for the comparison to be fair)

| Phase | Module | Output |
|---|---|---|
| 1 Inventory | `inventory.py` | `git ls-files`-based census, modules from build manifests, `generated_suspect` from disk:tracked ratio (`inventory.py:178`) |
| 2 Extract | `extract.py` + `lang/` | `defines[]`, `uses[]`, `io_edges[]`, `imports[]`, all anchored |
| 3a Graph | `graph.py` | **Dual-source** module DAG: declared (manifests) vs observed (imports), divergence as deliverable; Tarjan SCC; longest-path layering |
| 3b Partition | `partition.py` | Budget-driven scopes (40 files / 6000 loc), coalesce + bin-pack, `assert_partition` proves exactly-once |
| 3c Schedule | `schedule.py` | Topological waves by DAG level, `--max-concurrent` as wave size not ceiling |
| 7 Resolve | `resolve.py` | Global symbol table, route-constant substitution, **`used_by` as pure transpose** |
| 7b Merge | `merge.py` | Order-independent set-wise merge; conflict = same subject + same kind + differing closed-vocabulary field; ownership → evidence → `contested` |
| 8a Dataflow | `dataflow.py` | Typed-channel BFS source→sink, representation chains, shared-storage process boundaries |
| 8b Docs | `docs.py` | `00-overview.md`, `modules/*.md`, `dataflow.md`, `unknowns.md`, generated `CLAUDE.md` |
| — Derive | `derive.py` | 11 rule families producing anchored claims with **zero model calls** |
| — Verify | `verify.py` + `anchor.py` | Independent re-read of every citation; demote-to-unknown on failure |
| — State | `state.py` | Append-only patch log; `state.json = fold(merge, patches/, xref.json)`; order-independence tested |

**Language coverage:** 8 extractors + generic fallback (`lang/__init__.py:26-35`) — Java, Python, Web (JS/TS), Go, SQL, Docker, build manifests, config. Against Graphify's ~37 tree-sitter grammars. This is CDP's largest *breadth* gap and its smallest *strategic* one; see §9.3.

---

## 5. Side-by-side

| Dimension | CDP | Graphify |
|---|---|---|
| Parsing | hand-written line/regex extractors, stdlib only | tree-sitter, ~37 grammars |
| Dependencies | **zero** (stdlib Python 3.9+) | tree-sitter, networkx, graspologic, ~15 optional extras |
| Install | `shutil.copytree` (`cli.py:564-589`) | `uv tool install graphifyy` + `graphify install`; documented PATH / `externally-managed-environment` / package-name failure modes |
| Provenance | literal source anchor, ≥12 chars, ≤3 matches/file, exactly 1 within ±5 lines, **independently re-verified**, line rewritten to truth | `EXTRACTED`/`INFERRED`/`AMBIGUOUS` self-reported at extraction; never re-checked |
| Confidence | `high`/`medium`/`low`/`contested` — `contested` settable **only by the merge operator** (`schema.py:176-181`) | numeric score 0.55–1.0 |
| Semantic layer | bounded-scope leaf agents, schema-validated anchored claims, DAG-ordered waves | LLM subagents over docs/PDFs/images only; no scope discipline |
| Aggregation | append-only log + fold invariant + tested order-independence | content-hash cache + union merge |
| Unknowns | **first-class output**, the tribal-knowledge inventory | `AMBIGUOUS` edge flag |
| Clustering | module DAG levels + SCC | Leiden communities + god nodes |
| Query | 13 typed CLI queries | `query`/`path`/`explain` + 7 MCP tools |
| Harness enforcement | **none** (prose in `SKILL.md`) | `PreToolUse` hook, `--strict`, 20+ assistants |
| Freshness | manual rescan; SHA printed in `query stats` | git hooks, watch mode, merge driver |
| Output budget | **none** (hard-coded per-renderer caps) | `--budget`, `GRAPHIFY_MAX_OUTPUT_TOKENS` |
| Cost evidence | `source_loc_scheduled` proxy | graded harness, spend ledger, judge validation |

---

## 6. Ranking method

Each idea below is scored on **token leverage × fit with CDP's evidence discipline ÷ effort**. "Fit" is a hard gate: an idea that requires CDP to publish an unanchored or unreplayable fact is rejected regardless of its leverage, because that is the property CDP exists to have.

---

## 7. Twelve ideas, ranked

### 7.1 — `PreToolUse` hook: turn advice into enforcement
**Impact: very high · Effort: low · Fit: excellent**

**Graphify:** hook fires before Read/Grep/Glob, injects a nudge toward `graphify query`. `--strict` blocks the *first* raw source read of a session then degrades to the nudge.

**CDP today:** `SKILL.md:50-54` says *"Prefer the index over grep for these questions"* and gives a worked example (routes declared through constants — grep finds the constant, `query routes` finds all six handlers with both anchors). It is a correct and persuasive argument that the model may simply not read at the moment it reaches for `Grep`.

**Proposal.** A `PreToolUse` hook that, on `Read`/`Grep`/`Glob` against a path in `inventory.json`, injects: *"`.cdp/` indexes this repo at `<sha>`. `cdp query symbol X` / `query file <path>` returns the same fact with citations at a fraction of the cost. If you still need the source, Read only the cited lines."*

**Why CDP can do this better than Graphify.** `inventory.json` already classifies every file's `role` (`source`/`test`/`build`/`schema`/`config`/`docs`/`asset`/`ci`, `lang/__init__.py:74-86`). Graphify's hook fires on any read. CDP's can fire **only on `role == "source"`**, which eliminates the entire class of false positives.

**Stress tests.**
- *"Fix the typo in README.md."* → `role == "docs"`, hook does not fire. Solved by role scoping.
- *State absent or stale.* → hook must no-op silently when `.cdp/` is missing **or** `inventory.head != git HEAD`. A hook nagging about an index that does not describe the working tree is worse than no hook.
- *State location conflict.* → **This is a real blocker.** CDP writes state to `./.cdp` *outside* the analysed repo by default, deliberately (`cli.py:14-17`: "a tool that leaves a directory behind in someone else's checkout has made a decision that was not its to make"). A hook installed in the target repo cannot find state under that default. **The hook is only coherent under `--in-repo`, and `install` must say so.**
- *Loop risk.* → Adopt Graphify's fire-at-most-once-per-session rule verbatim for strict mode.

---

### 7.2 — A graded benchmark harness
**Impact: very high · Effort: high · Fit: excellent**

**Graphify:** `BENCHMARKS.md` — single model across every LLM role, matched token budgets, per-run spend ledger with `--max-spend`, grading as `coverage = (covered + 0.5·partial) / total` against gold atomic facts, **every verdict citing a verbatim quote from the answer**, and a second independent judge at 90.6% agreement / κ=0.81. It also publishes its own embarrassments: supermemory beats it on QA accuracy, n=6 on the code suite, and the documented reproduction command yields 43.3% rather than the 45.3% headline.

**CDP today:** `PLAN.md C2` (quoted at `cli.py:274-276`, `schedule.py:89-93`) states tokens are not measurable under in-session execution, and substitutes `source_loc_scheduled`. Honest, and correct for the pyramid. But it means **CDP cannot currently substantiate its own founding claim**, and the `scan`+`query` path — where the real savings are — is entirely unmeasured.

**Proposal.** Run the agent *out of session* (`claude -p`), which dissolves the measurability objection. Fix the model, cap the turns (Graphify used 14), define a question set with gold atomic facts over a target repo, and run two arms: grep/read/list baseline vs. baseline + CDP. Report **coverage and tokens**, plus two metrics CDP can report that Graphify structurally cannot:

- **Citation validity** — every CDP answer carries `file:line`; re-open and check. Graphify's `EXTRACTED`/`INFERRED` tags are unverifiable by construction.
- **Demotion rate** — already instrumented (`verify.py:62-74`), including `would_survive_lenient`, which is exactly the number that decides whether strict anchoring is buying correctness or costing recall.

**Stress test.** *Is n=6 enough?* No — and Graphify flags this itself. CDP should target 25–40 questions across the query kinds it claims to answer (`symbol`, `table`, `routes`, `paths`, `config`, `module`), because a harness that only tests "where is X used" will validate one query and certify thirteen.

**Second stress test.** *Judge and reader sharing a model* is a real confound Graphify acknowledges. CDP should grade with a different model than it answers with.

---

### 7.3 — `--budget` on every query, with ranked and *stated* elision
**Impact: high · Effort: low · Fit: excellent**

**Graphify:** `query --budget 1500`, `GRAPHIFY_MAX_OUTPUT_TOKENS` (16384/32768 examples).

**CDP today:** hard-coded, inconsistent caps per renderer — `[:40]`, `[:25]`, `[:20]`, `[:12]`, `[:8]`, `[:6]`, `[:4]` — unrelated to any budget, and **several truncate silently**. See §10 for the enumerated list.

**Proposal.** One `--budget N` respected by every renderer, with:
1. **Ranked truncation.** Drop *lowest-evidence rows first* — the exact policy `prompts.py:120-123` already uses for the inherited-sigma budget. Reusing CDP's own idiom keeps the system internally consistent.
2. **Mandatory stated elision.** `q_symbol`'s `"... %d more"` (`query.py:483-484`) is the pattern; generalise it. Also copy the `budget_fired` / `elided_claims` instrumentation from `prompts.py:66-69` so you learn whether the default ever binds.
3. **Exempt the guardrails.** `stats` and `coverage` must never be budgeted. They are the epistemic safety rails.

**Why this is a correctness issue for CDP and not merely a UX one.** `SKILL.md:58-61` instructs: *"Check coverage before saying 'there is no X'. If it is below 100%, absence of a fact means 'not examined', not 'not present'."* A renderer that prints 6 of 47 config read-sites with no marker **manufactures exactly the false absence that rule exists to prevent** — and unlike low coverage, it is invisible, because `coverage` will read 100%.

---

### 7.4 — `cdp refresh`: incremental freshness with claim decay
**Impact: high · Effort: medium-high · Fit: excellent — and this is where CDP can beat Graphify outright**

**Graphify:** post-commit/post-checkout hooks, background AST-only rebuild at zero API cost, `--update` re-extracts only changed files, git merge driver union-merges `graph.json`.

**CDP today:** `SKILL.md:66-67` — "Re-scan when the working tree has moved. State is pinned to a commit; `query stats` prints the SHA." A manual discipline that nobody will follow.

**The insight.** CDP has a mechanism Graphify lacks, and it is already built. Graphify's graph nodes are positions; when code moves, a node is stale and nothing detects it (their memory layer bolts on a "code changed — re-verify" hint as a heuristic patch). **CDP's claims are anchored to literal source text, and `verify.py` re-checks them for free.** So:

> `cdp refresh` = rescan at new HEAD + re-verify the whole existing claim corpus against the new tree + fold.
> Anchors that moved are **relocated** to their true line (`anchor.py:142-169` already returns the true line and requires the caller to store it). Anchors that vanished are **demoted to `unknowns[]`** with *"the code this claim cited changed at `<sha>`."*

That is a strictly stronger freshness story than union-merging a graph: expensive leaf knowledge is preserved where it still holds and *automatically retired where it does not*, at zero token cost. No other property in this document is as differentiating.

**Prerequisite — a real architectural tension.** Verification currently happens at collect time and the *post-verification* patch is what enters the log (`cli.py:476-478`). The log is append-only with no compaction (`state.py:73-93`), and supersession is per-node and status-only (`state.py:44, 131`) — you cannot partially supersede a node's claims. So re-verification has nowhere to write.

**The fix improves the invariant rather than bending it.** Move verification *into the fold*: `fold(patches, xref, partition, repo)`. The log then stores **raw agent output** and `state.json` becomes fully derived — which is more faithful to `state.py:1-14`'s own stated invariant ("nothing may enter `state.json` that is not derivable from the log") than the current design, where verification is a baked-in side effect that `check_fold` cannot reproduce from the log alone.

**Stress tests.**
- *Reformatting commit.* → Survives. `anchor.py:15-18` normalises interior whitespace precisely so an anchor survives an indentation-only pass. ✅
- *File rename or package move.* → **Catastrophic.** Every anchor in a renamed file fails `FileCache.lines()` and mass-demotes correct claims. **Mitigation is mandatory, not optional:** read `git diff -M --name-status <old>..<new>` and rewrite the `file` field before verifying. Without this, a single `git mv` of a package destroys the claim corpus. This is the landmine in the whole proposal.
- *Rescan destroying leaf work.* → Already solved. `write_derived_patch` (`state.py:96-108`) overwrites only slot `0000-derived.json` and leaves leaf patches intact, explicitly because an earlier version cleared `patches/` wholesale.

---

### 7.5 — `cdp query hubs`: blast radius from data CDP already holds
**Impact: medium-high · Effort: very low · Fit: excellent**

**Graphify:** `god_nodes(G)` — highest-degree nodes, framed as blast radius before a change. `--exclude-hubs 99` drops p99-degree nodes because hubs distort clustering.

**CDP today:** `resolve.py:216-228` builds `used_by` as the pure transpose of resolved uses. **`len(used_by[fqn])` is degree.** The data is on disk; nothing surfaces it as a ranking.

**Proposal.** `cdp query hubs [--limit N]` → symbols ranked by in-degree, with defining module, kind, and a sample anchor. Ten lines over existing state. It answers "what breaks if I change this" at *symbol* granularity, complementing `query table` at *table* granularity.

**Stress tests.**
- *Degree is import-derived, not call-derived.* → Must carry the same caveat `dataflow.py:16-19` already states: an import proves reachability, not invocation. Label it `medium`.
- *Framework-managed symbols distort the ranking* — a DI-wired `@Component` has near-zero static in-degree and enormous runtime importance. CDP already knows this and already maintains the exclusion list (`resolve.py:293-335`). The hubs view must annotate framework-managed symbols rather than silently ranking them last, or it will confidently report the most important class in a Spring app as unimportant.

---

### 7.6 — Deterministic file-purpose claims from top-of-file comments
**Impact: medium-high · Effort: low · Fit: good — with a guard**

**Graphify's RFC** lists the signals for a deterministic file summary and puts **module docstrings / top comments** first, as *"typically the best human-written statement of purpose."*

**CDP today — verified gap.** `FileFacts` (`lang/base.py:114-138`) has no docstring or purpose field. Worse, `strip_block_comments` (`lang/base.py:198-234`) **actively blanks out comment bodies before parsing**. `derive.py`'s eleven rule families draw exclusively from edges, annotations, manifests and naming — none from prose. **CDP systematically discards the single highest-signal human-written statement of purpose in every file it reads.**

**Proposal.** A `derive.py` rule emitting a `data_model`/`public_api` claim from a file's leading docstring or comment block, anchored on it, `confidence: medium`.

**Why this pays double.** It is not only free structure — it is *material for the leaf agent to disagree with*. `cdp-leaf.md:53` already lists *"a comment that contradicts the code"* as a target finding. Handing the leaf a derived purpose claim with an anchor turns a vague instruction into a concrete proposition to test.

**Stress tests.**
- *Docstrings lie or go stale.* → That is the point; see above. The confidence tier and the leaf protocol are built for it.
- *Restating the obvious.* → `cdp-leaf.md:55-57` bans leaves from writing "this class handles X" for a class named `XHandler`. **The derive rule needs the same filter or it will flood `state.json` with exactly the noise the leaf protocol forbids.** Concretely: reject a docstring whose content words are a subset of the symbol's name tokens. Also enforce a length bound — the RFC suggests one sentence / 200–300 chars.
- *Anchor feasibility.* → A one-line `"""Utils."""` is 9 characters and fails `MIN_ANCHOR_LEN = 12` (`anchor.py:27`). `build_anchor` will grow the span and, failing that, return `None` — and `derive.py:96` already drops claims with no evidence. The existing machinery handles this correctly; no new code path needed.

---

### 7.7 — `cdp diff <sha> <sha>`: architectural delta
**Impact: medium · Effort: medium · Fit: excellent**

**Graphify:** `graph_diff(G_old, G_new)` in `analyze.py`.

**CDP today:** none. State describes one commit.

**Proposal.** Diff two state directories and report *typed* deltas: routes added/removed, tables gaining a new writer, a module acquiring an undeclared dependency, a process boundary appearing, claims whose anchors moved. This pairs naturally with §7.4 — once `refresh` exists, retaining the prior state is nearly free.

**Why CDP's version is more valuable than Graphify's.** A node-set diff over an untyped graph reports churn. CDP's channels are typed, so it can report **"`sql-pool-api` now imports `sql-pool-dal`, and that edge is not declared in any manifest"** — a reviewable finding, not a statistic. That is the divergence analysis (`graph.py:7-14`) applied across time instead of across sources.

---

### 7.8 — Strict mode
**Impact: medium · Effort: low (once §7.1 lands) · Fit: good**

Graphify's `--strict` blocks the *first* raw source read of a session and redirects to the graph, then degrades to the soft nudge. The design constraint — "triggers at most once per session and never gets stuck" — is the whole reason it is safe, and should be copied verbatim.

**Gate it on coverage.** Blocking a read against an index at 62% coverage is actively harmful: the model is denied the source *and* the index cannot answer. **Strict mode should refuse to engage when `state.coverage.fraction` is below a threshold**, and say why. CDP has this number (`state.py:194-217`); Graphify has no equivalent and therefore cannot make this check.

---

### 7.9 — Tier-0 portability via `AGENTS.md`
**Impact: medium · Effort: low · Fit: good**

Graphify supports 20+ assistants, degrading gracefully: hook-based where hooks exist, instruction-file-based (`AGENTS.md`, `.cursor/rules/`) where they do not.

**CDP today:** `install` copies `.claude/skills/cdp/` and `.claude/agents/cdp-leaf.md` (`cli.py:564-589`) — Claude Code only.

**The split is natural and already exists in CDP's architecture.** The wave loop genuinely requires subagent spawning. But `scan` and `query` need nothing but a shell and Python 3.9. So:
- **Tier 0** (any assistant): `AGENTS.md` lines + the `SKILL.md:35-46` question→command table. Works in Cursor, Codex, Copilot, Aider.
- **Tier 1** (hook-capable): + §7.1.
- **Tier 2** (subagent-capable): the full pyramid.

This is cheap, and it widens the population that could ever validate §7.2's benchmark.

---

### 7.10 — Retrieval hygiene: never let the meaning layer be fetched in bulk
**Impact: medium · Effort: low · Fit: excellent**

The RFC's Option-A drawback: putting summaries inside `graph.json` means *"anyone dumping the entire `graph.json` into an LLM pays for every summary at once."*

**CDP has the same exposure.** `query claims` with no filter returns up to 100 full claims with all evidence (`query.py:343-357`); `docs` renders the entire corpus. The bulk path exists and nothing discourages it.

**Proposal.** Make the per-node path the cheap default and the bulk path explicit: require a filter on `query claims` (or cap it hard and state the cap), and have `SKILL.md`'s table route every question to a *scoped* query. This is §7.3 with a different emphasis — §7.3 bounds the output, this bounds the *request*.

---

### 7.11 — MCP server
**Impact: low-medium · Effort: medium · Fit: neutral**

Graphify ships 7 MCP tools over stdio/HTTP.

**Honest assessment: not a priority for CDP, and I am recommending against it now rather than parroting the feature list.** CDP's queries already run as a subprocess returning text; MCP changes the transport, not the token count. It would add a long-running server to a system whose distribution advantage is `shutil.copytree` and zero dependencies (§8.7). The genuine MCP benefit — typed tool schemas making the query surface discoverable without re-reading `SKILL.md` — is largely obtainable from §7.1's hook, which surfaces the right query at the moment of need.

Revisit if and only if CDP wants team-wide shared state (Graphify's `--transport http --api-key` case).

---

### 7.12 — The memory/reflect layer
**Impact: low · Effort: medium · Fit: POOR — adopt only in a modified form**

Graphify's `save-result` / `reflect` / `.graphify_learning.json` overlay tags nodes `preferred`/`tentative`/`contested` from Q&A outcomes.

**Adopting this as designed would break CDP's central invariant.** A `preferred` tag derived from "an agent found this useful once" is unanchored, unreplayable state entering the materialized view — precisely what `state.py:1-27` and `fold --check` exist to prevent. And CDP's `contested` already means something far stronger and better-founded: *two scopes disagreed on a closed-vocabulary field about the same subject, and ownership and evidence count both failed to break the tie* (`merge.py:169-188`). Overloading that word with "a query went badly" would degrade the term.

**What *is* worth taking:** the `Lesson:` hint rendering marked **"code changed — re-verify."** Adopt that presentation for §7.4's decayed claims. If outcome logging is ever wanted, it must enter as patches in the append-only log like everything else — no side channel.

---

## 8. Where CDP is already ahead — do not regress

Maturity comparisons invite wholesale adoption. These eight properties have **no Graphify counterpart** and are the reason CDP is worth maturing rather than replacing.

1. **Independent anchor verification.** Graphify's confidence tags are the extractor's self-report; nothing re-opens the file. CDP's `verify.py` + `anchor.py` re-read every citation, enforce ≥12 chars / ≤3 matches per file / exactly one within ±5 lines, **rewrite the line to its true location**, and demote failures. `verify.py:1-21` names the reason: *"asking the model to check its own citations is asking the entity that produced the error to detect it, using the same context that produced it."* This is the single largest correctness gap between the two systems, in CDP's favour.

2. **`unknowns[]` as a first-class deliverable.** The tribal-knowledge inventory — *"a precise list of what to ask the incumbent team before they leave"* — and the only artifact whose value rises when the pipeline does badly (`docs.py:9-12`). Graphify's `AMBIGUOUS` is an edge flag; CDP's is a question a named person can answer.

3. **Order-independent merge with escalation to `contested`.** `check_order_independence` (`state.py:258-278`) *tests* the property rather than asserting it, with a precise argument for why: an order-dependent merge is deterministic-but-arbitrary, so a naive determinism harness would score it 1.0 and certify a systematically wrong pipeline. And `_resolve` (`merge.py:186-188`) refuses to pick under an n-way tie — *"a merge operator that always produces an answer is a merge operator that fabricates under contention, and contention is precisely where the interesting knowledge lives."*

4. **The fold invariant.** `state.json = fold(merge, patches/, xref.json)`, with `fold --check` proving it. Merge-policy changes become **offline recomputation over a fixed log at zero token cost** (`state.py:22-27`). Graphify's cache is content-hash file skipping — not the same thing at all.

5. **Declared-vs-observed divergence.** CDP builds the dependency graph *twice* and treats the disagreement as the deliverable (`graph.py:1-14`). On the validation target, manifest-only extraction — what almost every dependency tool does, Graphify included — reports nine nearly-unrelated modules where the truth is a 5-level DAG. "Imported but not declared: compiles by transitive resolution, breaks on a dependency bump" is not obtainable from a single-source graph.

6. **Git-based inventory with the ratio as a finding.** 391 tracked vs 2,065 on disk (`inventory.py:5-13`); `generated_suspect` derived from it (`inventory.py:178`); the generated module then described **by its build contract rather than read** (`derive.py:542-579`). Graphify's `.graphifyignore`/`.gitignore` merge narrows the file set but does not turn the ratio into a claim.

7. **Zero dependencies.** CDP is stdlib Python 3.9+, installed by copying a directory. Graphify needs uv/pipx, tree-sitter, graspologic and ~15 optional extras, with documented install failures (`graphifyy` vs `graphify`, Windows PATH, `externally-managed-environment`). In an agent harness that must work inside an arbitrary repo, possibly offline, **this is a real operational advantage that the feature comparison hides.**

8. **Bounded-scope leaf protocol.** "Read only your files; record boundaries, never follow them" plus a deterministic resolve pass that holds the global symbol table the leaf lacks (`cdp-leaf.md:13-24`, `resolve.py:1-26`). This is a genuine context-hygiene mechanism with no Graphify analogue — their LLM pass is batch document extraction with no scope discipline at all.

---

## 9. Do not copy

1. **Leiden / graspologic.** Breaks the zero-dependency property, which is CDP's actual distribution advantage. And CDP's module DAG + partition already supplies a community structure derived from *ownership*, which is more actionable than one derived from topology. If topological cohesion is genuinely wanted later, label propagation or connected components in stdlib gets most of it at no dependency cost.
2. **Multimodal ingest (PDFs, images, whisper).** Orthogonal to code discovery, and it is the *only paid pass* in Graphify. CDP's entire pitch is that `scan` is free.
3. **Embeddings.** Neither system uses them. "No vector store" is not a differentiator to chase — it is the shared baseline.
4. **Extraction breadth as a headline goal.** 37 grammars is impressive and mostly irrelevant: the marginal grammar adds a language nobody in the target repo uses. CDP's `lang/base.py:1-11` already states the right principle — the vocabulary is language-independent, the detectors are not. **Add languages on demand, driven by what real target repos contain**, not to close a number gap.
5. **Hosted service, telemetry, PR triage.** Out of scope.
6. **Popularity as evidence.** See §0.

---

## 10. Defects found in CDP during this review

These are verified against the source, not inferred. They sit inside §7.3's scope.

**Silent truncation — renderers that drop rows with no "N more" marker**, in direct tension with `SKILL.md:58-61`:

| Location | Truncation | Marker? |
|---|---|---|
| `query.py:258` | `migrations[:12]` in `q_table` | none |
| `query.py:261` | `evidence[:8]` in `q_table` | none |
| `query.py:555` | `t["migrations"][:6]` in render | none |
| `query.py:561` | `t["evidence"][:6]` in render | none |
| `query.py:568` | `c["declared"][:4]` in render | none |
| `query.py:569` | `c["read"][:6]` in render | none |
| `query.py:505` | `entry["defines"][:20]` in render | none |
| `query.py:508` | `entry["io_edges"][:20]` in render | none |
| `query.py:510` | `entry["claims"][:10]` in render | none |
| `query.py:534` | `entry["claims"][:25]` in render | none |
| `query.py:481-484` | `used_by[:12]` | ✅ `"... %d more"` — **the pattern to generalise** |

The `q_table` and `q_config` cases are the worst, because "who writes this table" and "who reads this config key" are exactly the questions where a partial list reads as a complete one and a wrong blast-radius conclusion follows directly.

**Verification is baked into the append-only log** (`cli.py:476-478`), which makes re-verification at a new commit impossible without either mutating the log (forbidden by `state.py:73-93`) or appending a superseding patch (impossible — supersession is per-node and status-only, `state.py:44,131`). This is the prerequisite blocker for §7.4, and fixing it strengthens the fold invariant rather than weakening it.

**Comment bodies are discarded before extraction** (`lang/base.py:198-234`), and `FileFacts` has no field to hold them (`lang/base.py:114-138`). See §7.6.

---

## 11. Proposed roadmap

**Phase 1 — token leverage (low effort, immediate)**
- `--budget N` on every query, with ranked elision reusing `prompts.py`'s policy; fix the §10 silent truncations; exempt `stats`/`coverage`. → §7.3
- `cdp query hubs` over existing `used_by`, with the reachability and framework-managed caveats attached. → §7.5
- `PreToolUse` soft-nudge hook, scoped to `role == "source"`, no-op when state is absent or stale, `--in-repo` only. → §7.1

**Phase 2 — freshness (the differentiating phase)**
- Move verification into `fold`; the log becomes raw agent output. → §7.4 prerequisite
- `cdp refresh`: rescan + **rename-aware** re-verify + fold; relocate moved anchors, demote vanished ones with "code changed at `<sha>`". → §7.4
- Opt-in post-commit / post-checkout hooks. → §7.4
- `cdp diff <sha> <sha>` typed architectural delta. → §7.7

**Phase 3 — measurement (validates the founding claim)**
- Headless graded harness: fixed model, capped turns, 25–40 questions with gold atomic facts, grep-baseline vs CDP-assisted, reporting coverage **and** tokens **and** citation validity **and** demotion rate, with a published caveats section. → §7.2
- Locate CDP's crossover repo size — separately for `scan+query` and for the pyramid. → §3

**Phase 4 — depth and reach**
- Deterministic file-purpose claims from leading comments, with the name-subset and length filters. → §7.6
- Strict mode, gated on `coverage.fraction`. → §7.8
- Tier-0 `AGENTS.md` portability. → §7.9
- Bulk-retrieval hygiene on `query claims` / `docs`. → §7.10

---

## 12. Open questions for you

1. **Is the goal tokens or correctness?** Graphify's own benchmark measures coverage (70.8% → 82.0%), not compression, and explicitly declines to compute token reduction as a standalone metric. CDP's strongest defensible claim is *correctness per token* — anchored, verified, citable. Leading with raw token reduction invites the comparison CDP wins least decisively.
2. **Is `--in-repo` the default now?** §7.1 and §7.4 both require state to live inside the target repo. `cli.py:14-17` argues carefully for the opposite default. That argument was made for the "analysing someone else's repo" case; the hook and freshness work assume "analysing my own repo." These may need to be two documented modes rather than one default.
3. **How much does the pyramid actually get used?** If the dominant path is `scan` + `query`, Phases 1–3 are the entire roadmap and leaf agents are a differentiator you rarely spend. If the pyramid is the point, §7.4's claim-decay mechanism becomes the most valuable item in this document, because it is what makes expensive leaf knowledge survive a commit.
4. **What is the real target repo?** Language-extractor breadth (§9.4) should be driven by that answer, not by Graphify's grammar count.

---

## 13. Sources

| Source | Reliability |
|---|---|
| CDP source at `.claude/skills/cdp/` | **Primary** — read directly, all citations checkable |
| [graphify `README.md` @v8](https://github.com/Graphify-Labs/graphify) (62.7 KB) | High for feature surface; vendor-authored |
| [`ARCHITECTURE.md`](https://raw.githubusercontent.com/Graphify-Labs/graphify/v8/ARCHITECTURE.md) | High — module/API level, internally consistent |
| [`BENCHMARKS.md`](https://raw.githubusercontent.com/Graphify-Labs/graphify/v8/BENCHMARKS.md) | **High and unusually candid** — publishes its own losses, small n, and reproduction mismatch. The best single document in the repo. |
| [`docs/how-it-works.md`](https://raw.githubusercontent.com/Graphify-Labs/graphify/v8/docs/how-it-works.md) | High — source of the 71.5× / 5.4× / ~1× scaling curve |
| [`docs/node-summaries-rfc.md`](https://raw.githubusercontent.com/Graphify-Labs/graphify/v8/docs/node-summaries-rfc.md) | High — the project naming its own gap |
| GitHub API repo metadata | Verified directly; **the star/watcher figures are anomalous** (§0) |
| [Steve Scargall — 79× token reduction](https://stevescargall.com/blog/2026/05/graphify--memmachine-79-token-reduction-zero-vector-database/) | Low — third-party, unreproduced |
| [DEV Community write-up](https://dev.to/terminalchai/graphify-turn-codebases-into-knowledge-graphs-to-slash-ai-token-costs-3lfb) | **Very low** — promotional; repeats 71.5× with no methodology |
| [graphify.com](https://graphify.com/) | Low — marketing; no numbers |

