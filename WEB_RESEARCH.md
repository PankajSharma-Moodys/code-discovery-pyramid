# WEB_RESEARCH — an interactive web layer for CDP

**Date:** 2026-09-21
**Status:** Research and design only. No application code was written. The only
thing executed was a read-only probe (`cdp scan --state-dir /tmp/cdpweb`) to
verify what the backend can actually serve; nothing in the repo was modified.
**Companion:** `RESEARCH_GRAPHIFY.md` (what CDP learned from Graphify's engine);
this document is the *interface* counterpart.

**Revision (2026-09-21, after review):** §6, §7 and §11 are rewritten. The first
draft treated the backend as a solved read problem and described the web layer
as "transport, not data". A review against the code found that the runtime
behaviour — locking, snapshot selection, write ordering — was never checked.
§6.0 below records what the second pass verified; §7.0 records the concurrency
model that follows from it. Sections 1–5 stand as written.

---

## 0. Method and epistemic status

### Verified by probing the live backend (not from docs)

I scanned this repo into a throwaway state dir and read the artifacts directly,
so every data-shape claim in §1 is ground truth as of commit `81f731d`:

| Fact | Value |
|---|---|
| Storage | SQLite `index.db`; artifacts are JSON blobs in `snapshot_artifact(snapshot_id, name, payload)` |
| Artifact names | `inventory, extract, graph, partition, schedule, xref, dataflow, state, manifest` (`cdp/store/__init__.py:33`) |
| Run/task tables | `snapshot_run(run_id, status, started_at, finished_at, model, template_version, lessons_version)`, `snapshot_task(run_id, scope_hash, state, attempts, lease_until, last_error, wall_ms)` |
| Link tables | `link_edge(id, payload)`, `link_task(...)`, `link_run(run_id, payload)` |
| This repo's scale | 377 tracked / 3,576 on disk, 97 claims, 1,967 symbols, 223 dataflow edges, 141 paths, 17 scopes, 3 waves |
| Payload sizes | `xref` **1.04 MB**, `dataflow` 184 KB, `state` 61 KB, `partition` 25 KB, `graph` 12.7 KB |

### Verified gaps (these constrain the design)

- `--json` exists on **`query`, `diff`, `link scan`, `link query`, `link refresh`, `help`** only.
  `status`, `refresh`, `run`, `reflect`, `lessons`, `holdout`, `doctor`, `verify`
  are **human-text-only** today (`grep -n '"--json"' cdp/cli.py`).
- There is **no HTTP surface**. `mcp_server` exposes exactly three tools —
  `cdp_query`, `cdp_scan`, `cdp_status` (`mcp_server/schemas.py:20,55,76`).
- `cdp status` already prints run id, coverage, freshness buckets
  (live/stale/anchored-but-unreviewed/unknown-churn) and per-wave scope states —
  all four of the pre-scan panels the user asked for exist as *text*.

### Verified in the second pass (2026-09-21)

- **Runtime behaviour**: the per-repo lock policy, SQLite pragmas, artifact
  write atomicity and write *ordering* — all read from source, cited inline in
  §7.0. This is the material the first draft never checked.
- **Every licence and version in §6** was read from the npm and PyPI registries
  rather than recalled, including the finding that Sigma v4 is beta-only.

### Unverified / assumed

- Graph-library performance numbers below are vendor and third-party claims, not
  my measurements. §6 says what to benchmark before committing.
- The 2026 design-trend synthesis in §5 is from published trend write-ups
  (sources in §12), not from user testing of this product.
- Bundle sizes are not measured. §6.2's Monaco-vs-Shiki call is a
  qualitative one; measure the built output before finalising.

---

## 1. What the backend can actually feed a UI

This is the honest inventory. Every UI idea later in the doc is traceable to a
row here — nothing in the design requires data CDP does not have.

| UI need | Source today | Shape (verified) |
|---|---|---|
| Module dependency graph | `graph` artifact | `modules[]`, `levels[][]`, `declared[]`, `observed[]`, `cycles[]`, `divergence{}`, `external.third_party_packages{}` |
| Repo → scope → file tree | `partition` artifact | `scopes[]` with `files[]`, `by_role{docs,source,test}`, `by_language{}`, `file_count`, `budgets{max_files}` |
| Data-flow paths & highlight | `dataflow` artifact | `edges[]{source,target,channel,confidence,module,anchor{file,line,anchor}}`, `paths[]{hops[],fully_anchored}`, `sources[]{node,channel,trigger,anchor}` |
| Symbol graph / hover cards | `xref` artifact | `symbols{fqn → {kind, modules[], sites[]}}` (1,967 here), `used_by{}`, `routes[]`, `constants{}`, `collisions[]`, `coupling{}` |
| Claims, confidence, provenance | `state` artifact | `claims[]{subject, kind, confidence, evidence[{file,line,anchor}], anchor_verified_at, claim_reviewed_at, author_kind}`, `coverage{}`, `entailment.by_node{}`, `conflicts[]`, `contradictions[]`, `near_misses[]` |
| Unknowns (the honest holes) | `query unknowns --json` | per-scope open questions |
| Cross-repo link graph | `link_edge` rows / `link scan --json` | matched + ambiguous channel edges across state dirs |
| Live run status | `snapshot_run` + `snapshot_task` | states, attempts, lease expiry, last error, wall_ms — **pollable/streamable as-is** |
| Freshness / "am I behind HEAD" | `cdp/freshness.py:79` `claim_bucket`, `:104` `bucket_counts` | live / stale / unreviewed / unknown-churn counts vs HEAD |
| Model conformance | `<state>/doctor/<model>.json` + `doctor.aggregate` (`cdp/doctor.py:182`) | per-model schema validity, anchor survival, entailment, recall, false-unknown |
| Trajectory / lessons | `cdp/trajectory.py` (`scope_shape_key:141`, `elision_regret:155`), `lessons show` | per-scope run corpus, promotions, lesson versions |
| Time travel / diff | `query --as-of <sha>`, `diff --json` | typed structural deltas between snapshots |

**No new analysis is needed — but "transport" was too glib.** Every *fact* the
UI wants exists above. What does not exist is a machine-readable surface for
half of it (`status`/`doctor`/`refresh`/`lessons` are human-text-only, and
splitting computation from `print()` is a refactor, not a flag), a node
identity scheme that joins these four artifacts, or a concurrency story for
reading while an agentic run writes. See §7.0, §7.2 and §7.3.

---

## 2. Product shape: two rooms, one continuous surface

The user's request splits cleanly along a seam the backend already has —
deterministic index (post-scan) vs. supervised agent work (pre/during scan).

```
┌─ ATLAS ───────────────────────────────┐  ┌─ CONTROL ROOM ────────────────────┐
│ post-scan. one infinite canvas.       │  │ pre-scan. bento dashboard.        │
│ semantic zoom across 5 altitudes.     │  │ hook up an agent layer, dispatch  │
│ hover = peek, click = focus,          │  │ waves, watch runs, doctor table,  │
│ path highlight, lens modes, time      │  │ freshness, trajectory/lessons,    │
│ scrubber, ask-bar.                    │  │ interactive query console.        │
└───────────────────────────────────────┘  └───────────────────────────────────┘
                     └──── same cmd-K, same ask-bar, same theme ────┘
```

Do **not** make these two separate apps. The single strongest emotional beat in
this product is: *dispatch a wave in the Control Room, and watch nodes in the
Atlas light up as claims land.* That requires one process, one event stream.

---

## 3. The Atlas: one canvas, five altitudes

The user asked for scroll-up → dependency graph, scroll-down → repo → submodules.
Generalize that into **semantic zoom**: scroll is not zoom-in-pixels, it is
zoom-in-*meaning*. Each altitude is a different artifact, cross-faded.

| Alt | Level | Nodes | Edges | Backed by |
|---|---|---|---|---|
| **L4** | Constellation | repositories / services | contracts, unmatched calls | `link_edge`, `link query` |
| **L3** | Dependency | modules | declared vs observed (divergence styled differently) | `graph.modules/levels/declared/observed` |
| **L2** | Territory | scopes & packages | coupling weight | `partition.scopes`, `xref.coupling` |
| **L1** | Files | files in a scope | imports | `inventory`, `extract` |
| **L0** | Symbols & flow | functions, routes, tables | call/http/db channels | `xref.symbols`, `dataflow.edges` |

**Rules that make it feel designed rather than gimmicky:**

1. **Altitude is a continuous variable, transitions are not.** Wheel accumulates
   into a rubber-banded scalar; crossing a threshold triggers a 420 ms
   cross-fade + spring layout morph. Nodes do not teleport — the module you were
   looking at becomes the *frame* you descend into, its children expanding from
   its centroid. This is the Prezi/Figma "zoom is navigation" idiom, done with
   pre-computed per-level layouts so it never re-simulates mid-flight.
2. **Context never disappears.** A breadcrumb spine on the left shows all five
   altitudes with the current one lit; the parent level renders as a dim
   receding backplate at 8 % opacity (atmospheric depth, §5).
3. **Scroll hijack is opt-in and reversible.** Canvas captures wheel only when
   the pointer is over it *and* the canvas has focus; `Esc` pops one altitude;
   browser back maps to altitude history. Trackpad pinch = spatial zoom within
   an altitude, wheel = altitude. (Verified risk: conflating the two is the #1
   complaint about zoom-UI demos — keep them on separate gestures.)

### Interaction grammar (four verbs, everywhere)

- **Hover → Peek card** (~120 ms delay, follows cursor, never covers the node).
  Contents, all available today: *what it is* (claim subjects + kinds from
  `state.claims`), *what flows through it* (in/out `dataflow.edges` by channel),
  *what functionality it belongs to* (owning scope + module + role mix from
  `partition.by_role`), *how sure we are* (confidence chip + `anchor_verified_at`
  vs HEAD), *what we don't know* (unknowns count — **always show this, even at
  zero**; it is CDP's differentiator).
- **Click → Focus.** Pins an inspector rail on the right: claims with clickable
  `file:line` anchors, evidence snippets, entailment ratio for the node
  (`state.entailment.by_node`), conflicts/near-misses, and a "show in code"
  pane. Graph dims to the node's 1-hop neighbourhood; double-click descends an
  altitude into it.
- **Trace → Path highlight.** Pick a source (`dataflow.sources[]`, e.g. an
  `http_in` on a Dockerfile `EXPOSE`) and the full `paths[]` it participates in
  animate as flowing edges: a dashed stroke offset animation, ~1.2 s per hop,
  staggered. Hops that are `fully_anchored: true` glow solid; inferred hops
  render as a dotted stroke. Clicking a hop opens its exact anchor line.
  *This single feature is the demo.* It is the visual proof of CDP's thesis —
  every hop is a citation, not a guess.
- **Lens → recolor the whole canvas by one dimension.** A segmented control:
  `Structure` (default, colored by module) · `Freshness` (live/stale/unreviewed/
  churn) · `Confidence` (high/medium/low) · `Coverage` (complete/partial/
  untouched) · `Divergence` (declared-but-not-observed vs observed-but-not-
  declared — CDP already computes this and *nobody else shows it*) · `Blast
  radius` (fan-in from `xref.used_by`). Lens changes animate color only, never
  layout, so the user keeps their mental map.

### Two more Atlas features that are cheap and land hard

- **Time scrubber.** The store keeps snapshots per commit; `query --as-of` and
  `diff --json` already exist. A bottom scrubber over commits replays the
  architecture: added nodes bloom in, removed nodes ghost out, changed claims
  pulse. Cost is one endpoint (`/api/diff?old=&new=`).
- **Unknowns as first-class geography.** Render open unknowns as translucent
  voids/craters rather than hiding them. An index that admits its holes *looks*
  more trustworthy than one that doesn't. Clicking a void offers `cdp answer`
  (a human claim) or "dispatch a leaf here".

---

## 4. The Control Room: pre-scan and live operation

Bento grid (§5), five tiles, all backed by data verified in §1.

1. **Agent layer hookup** — the tab the user explicitly asked for. `cdp install
   --framework {claude-code,langgraph,adk,none}` already exists, and so do
   `agent_adapter/{langgraph,adk}.py` + `mcp_server`. UI: pick target repo →
   pick framework → shows the exact files it will copy and the `--runner-cmd`
   it will wire → an **"Is it alive?" check** that dispatches one throwaway
   scope and reports schema-validity + anchor survival. Show the MCP tool list
   (`cdp_query/cdp_scan/cdp_status`) with copy-to-clipboard config.
2. **Run console.** `snapshot_task` is a lease table — render it as a live wave
   board: columns = wave, cards = scopes, state transitions animate
   (`pending → dispatched → collected → folded`), lease countdown rings,
   `last_error` inline with a one-click `run --resume --run-id`. Stream via SSE
   from a poll of the two tables (no backend rewrite).
3. **Repo health strip.** Per repo: HEAD vs `as_of.commit` ("**4 commits
   behind** — refresh available"), coverage %, freshness buckets as a stacked
   bar, fold-hash verified badge (`verify`), conflicts count. Primary action:
   `refresh` (zero model calls) with a live diff preview of which claims decay.
4. **Doctor / model compatibility.** `doctor.aggregate` + `compatibility_table`
   already produce the matrix; render it as a heatmap (models × metrics:
   schema validity, anchor survival, entailment, recall, false-unknown) with a
   "re-run doctor on this model" button.
5. **Trajectory & lessons.** Start-pattern query over the trajectory corpus:
   filter by `scope_shape_key`, outcome, elision-regret; see which lesson
   version was pinned for a run; diff `lessons vN` vs `vN+1`; `holdout` results
   as a before/after bar. This is the "query on our trajectory (start pattern)"
   ask, and the data exists in `cdp/trajectory.py`.

**The ask-bar** (persistent, cmd-K) is the connective tissue: it accepts CDP
query kinds directly (`trace OrderResource`, `symbol foo`, `unknowns`,
`table orders`) with typeahead from `xref.symbols`, and *routes every answer
back onto the canvas* — a query result is never just a table; it selects,
highlights, and flies the camera to its subjects. Natural-language mode is
optional and must render as "I ran `cdp query X` for you" with the command
visible and editable (2026 copilot convention: suggest, don't take over).

---

## 5. Visual design language

Dark-first, provenance-legible, quiet until it moves.

- **Palette.** Deep cyber-monochrome base (`#07090c` → `#151a21` elevation
  ramp), one saturated accent for focus/flow (electric cyan), and a **semantic
  triad that is never used decoratively**: verified-anchor green, inferred amber,
  unknown violet. Because color carries epistemic meaning here, it must also be
  encoded redundantly — stroke style (solid/dashed/dotted) and a glyph — for
  colorblind users. Enforce 4.5:1 body contrast; verify accent-on-dark ratios.
- **Depth over chrome.** 2026 has settled on atmospheric depth — translucent
  layers, blur-and-opacity hierarchy, no hard drop shadows. Inspector rails and
  peek cards are `backdrop-filter` glass panels over the canvas; receding
  altitudes use blur + desaturation. Synthesize grain/noise in CSS rather than
  shipping image payloads.
- **Bento for the Control Room, canvas for the Atlas.** Don't bento the graph.
  Asymmetric bento tiles give the dashboard implicit hierarchy (run console
  large, doctor heatmap small); collapse to a single column with an explicit
  mobile ordering, not a duplicated DOM.
- **Motion spec.** 150–300 ms for feedback, 400–600 ms for layout/altitude
  transitions, `cubic-bezier(.2,.8,.2,1)`, every animation reversible, all of it
  behind `prefers-reduced-motion` (which should also disable edge-flow
  animation and fall back to a static highlight + step-through list).
- **Empty and honest states.** This repo scans to **0 % coverage, 97 claims** —
  a first-run user will see a mostly-grey graph. Design that state on purpose:
  grey nodes read as "not yet reviewed", with a single call to action ("12
  scopes pending — dispatch wave 0"). Never let emptiness look like failure.

---

## 6. Technology choices (decided)

### 6.0 What the second pass verified

Everything in this section was checked against the registries on 2026-09-21,
not recalled:

- **Sigma v4 does not exist as a release.** npm dist-tags are
  `latest: 3.0.3`, `beta: 4.0.0-beta.6`, `alpha: 4.0.0-alpha.7`. The first
  draft recommended "Sigma.js v4" from the docs site, which is ahead of the
  shipped package. **Pin `sigma@3.0.3`** — MIT, renders graphology, has
  worker-mode ForceAtlas2, which is everything the design actually needs.
- **Cosmograph is `CC-BY-NC-4.0`** (`@cosmograph/cosmos@3.4.1`, verified).
  The non-commercial clause fails the Open Source Definition, so it is out
  regardless of how distribution lands. §11.4 is closed.
- **elkjs is `EPL-2.0 OR GPL-3.0-or-later`.** You could elect EPL-2.0, but it
  is file-level weak copyleft and we do not need it: `graph.levels` is already
  a topological layering, so dagre (MIT) only has to assign order *within* a
  rank. Dropped for licence and payload both.
- **Every other pick is MIT, Apache-2.0 or BSD-3-Clause.** No copyleft, no
  non-commercial, no source-available-but-not-open.

### 6.1 Backend

**Python + FastAPI + uvicorn + Pydantic**, living in the web subproject with
its own dependency declaration.

This is the `mcp_server/` pattern, not a departure from it. `cdp/` itself stays
dependency-free — `pyproject.toml`'s `dependencies = []` is load-bearing for
`cdp install`'s copy-a-directory path, and `tests/test_core_purity.py` keeps it
true. An adapter package with its own dependencies does not touch that
property: `mcp_server/server.py:38` already imports the `mcp` SDK lazily behind
`pip install cdp[mcp]` and fails loudly if it is absent. The web layer does the
same thing one package over.

| Component | Pick | Licence |
|---|---|---|
| Framework | `fastapi` 0.141 | MIT |
| Server | `uvicorn` 0.53 | BSD-3-Clause |
| Models | `pydantic` 2.13 | MIT |
| ASGI core | `starlette` 1.6 | BSD-3-Clause |
| SSE | `sse-starlette` 3.4 | BSD-3-Clause |

Four consequences worth writing down, because three of them are easy to get
wrong:

1. **Handlers are `def`, not `async def`.** Everything touching `sqlite3` or
   `subprocess` must be sync so Starlette runs it in the threadpool. An
   `async def` handler doing a blocking SQLite read stalls the event loop for
   every other client. Only the SSE endpoint is `async def`.
2. **Pydantic response models are the CLI-parity contract.** This is the
   mechanism §7.1 of the first draft asserted but never supplied: one contract
   test validates `/api/status` *and* `cdp status --json` against the same
   model, so divergence fails CI instead of surfacing as a trust bug in a demo.
3. **Generate the TypeScript client from the OpenAPI schema.** Free once
   FastAPI is in, and it makes the API contract unbreakable from the frontend.
4. **Add `fastapi`, `uvicorn`, `starlette`, `pydantic` to `FORBIDDEN_EXACT` in
   `tests/test_core_purity.py`.** Same guard the repo already runs for
   `mcp`/`litellm`/`langgraph`/`google`: the deps live in the subproject, and
   the test is what stops them leaking upward into `cdp/`.

Declare them as `[project.optional-dependencies] web = [...]` to match the four
existing extras (`postgres`, `mcp`, `litellm`, `agent`), or as a standalone
`pyproject.toml` in the subproject if it should version independently.

### 6.2 Frontend

| Layer | Pick | Licence | Why |
|---|---|---|---|
| App | React 19 + Vite 8 + TypeScript 7 | MIT / MIT / Apache-2.0 | Ecosystem for everything below; HMR at hackathon pace |
| Graph model | **graphology** 0.26 | MIT | The hedge: renderer-agnostic. Swapping renderers later is a swap, not a rewrite. |
| Renderer | **sigma 3.0.3** (WebGL) | MIT | Reads graphology natively; worker ForceAtlas2 so physics never blocks the UI. Not v4 — see §6.0. |
| Layout, L3–L4 | `@dagrejs/dagre` 3.1 | MIT | Feed `graph.levels` in as fixed ranks; dagre only orders within a rank |
| Layout, L0 | `graphology-layout-forceatlas2` 0.10, in a worker | MIT | Force suits the symbol cloud |
| State/data | TanStack Query 5 + Zustand 5 | MIT | Server truth and view state stay separate; altitude history becomes trivially undoable |
| Motion | Framer Motion 13 for DOM/panels; imperative tweens inside the canvas | MIT | Never animate canvas content through React re-renders |
| Styling | Tailwind 4 + CSS custom properties; Radix primitives | MIT | The token layer is what makes the epistemic palette survive light/dark |
| Code peek | **Shiki** 4.4, not Monaco | MIT | §10 forbids a write path, so we need highlighting and jump-to-line and nothing else. Monaco is far heavier for ~5% use. Measure the built bundle before finalising either way. |

Fallback, if Sigma's label/hit-test pass janks at the chosen scale:
`react-force-graph` (MIT) ships faster but owns the layout, which costs the
altitude-morph in §3.1. Prefer clustering below a zoom threshold before
changing renderers.

### 6.3 Where layout runs — **client-side**

The first draft said "precompute per-altitude layouts server-side at scan
time", which contradicts §1's own "the one missing piece is transport, not
data". It does more than that: an artifact written at scan time enters
`ARTIFACTS` (`cdp/store/__init__.py:33`), the golden and determinism suites,
and fold-hash reproducibility — layout would have to be a pure deterministic
function of the graph or `cdp verify` starts failing.

Compute layout in the browser and cache it in IndexedDB keyed by `snapshot_id`.
Layout is paid once per snapshot, not per page load, and the scan pipeline is
untouched. Server-side pre-layout stays documented as the scale escape hatch —
and if it is ever built, it ships as a *derived, non-hashed cache* (like
`docs/`, an export) so it stays outside the determinism gate.

### 6.4 Licence hygiene

- **CDP itself has no licence.** There is no `LICENSE` file and no `license`
  key in `pyproject.toml`. Under default copyright that is all-rights-reserved:
  nobody may legally copy, modify or redistribute CDP, which is directly at
  odds with `cdp install`'s copy-a-directory model. This is a larger exposure
  than any dependency on the list and it is a one-file fix. MIT or Apache-2.0
  are the consistent choices given what we consume; Apache-2.0 if the patent
  grant should run both ways.
- **Shiki's grammars and themes are separate upstream artifacts.** Shiki is
  MIT; the TextMate grammars it vendors come from various sources with their
  own terms. Check the specific language grammars actually bundled.
- **Gate it in CI, no new dependency.** A short script over `npm ls --json`
  that fails on any licence outside an allowlist (`MIT`, `Apache-2.0`,
  `BSD-2-Clause`, `BSD-3-Clause`, `ISC`) catches a copyleft or NC package
  arriving transitively later. Same posture as `tests/test_core_purity.py`:
  enforce the invariant with a test, not a convention.

**Benchmark before committing** (half a day, worth it): render this repo's real
`xref.symbols` (1,967 nodes) *and* a synthetic 30k-node graph with labels on,
on mid-range hardware. Hit-testing and label rendering — not node count —
usually decide the experience.

---

## 7. The backend adapter (`cdp serve`)

### 7.0 The concurrency model (the part the first draft missed)

The first draft said the web layer needs "transport, not analysis" and left the
runtime behaviour unexamined. Here is what the code actually does.

**Verified:**

- `cmd_run` is `@_locked(shared=False)` (`cdp/cli.py:1527`) — an exclusive
  per-repo `fcntl` lock held for the *entire* run body, 60 s acquire timeout
  (`cdp/lock.py:47`). `query`/`status`/`diff`/`doctor` take the same lock
  shared.
- SQLite is opened with `busy_timeout = 5000` and **no WAL**
  (`cdp/store/sqlite_backend.py:252`).
- `write_artifact` is a single `INSERT … ON CONFLICT DO UPDATE` followed by
  `commit()` (`sqlite_backend.py:844-850`) — **one artifact is replaced
  atomically**, but a multi-artifact write is *not* one transaction.
- `manifest` is written **last** in both write paths: `cli.py:746` (scan,
  after the reports) and `cli.py:1379` (refresh).

**The split that follows.** Reads go straight to storage and never take the
repo lock. Expensive, repetitive, agentic operations — `scan`, `refresh`,
`run`, `reflect`, `link scan` — keep the existing lock discipline, because they
are costly and a second concurrent copy of one produces no information the
first will not.

This is safe, and the reason is specific: **during agentic operation exactly
one artifact mutates.** `run` → `fold` → `write_artifact("state", …)`
(`cli.py:873`, `:2509`). `graph`, `xref`, `partition`, `dataflow` and
`inventory` are written once at scan (`cli.py:701-707`) and not touched again
until a `refresh`. So an unlocked reader combining a freshly-folded `state`
with the existing `xref` is reading a *correct* view, not a torn one — the
other artifacts did not move. The Atlas lighting up live as a wave folds is
safe by construction.

**The one window that is not safe, and the fix.** `refresh` moves everything,
non-atomically. It calls `begin_snapshot` first (`cli.py:1358`), which bumps
`touch_seq`, and `use_latest_snapshot()` orders by `touch_seq DESC`
(`sqlite_backend.py:797`). So the instant a refresh starts, a reader resolving
"latest" jumps to the **new, empty snapshot**: `graph`/`xref` land at
`cli.py:1366-1371`, then `state_mod.fold` runs — the expensive part — and
`state` only appears at `:1378`. For that whole window the Atlas would render a
fully-structured graph with **zero claims**, which reads to a user as "CDP lost
everything": precisely the trust failure this product exists to avoid.

Fix, no schema change: **the read API selects the latest snapshot that has a
`manifest`, and pins that `snapshot_id` for the session.** Because `manifest`
is written last in both paths, its presence is already a commit marker.
Incomplete snapshots become invisible rather than half-rendered. Note that this
is currently an accident of write order, not a stated invariant — a future
reorder would silently break it, so it needs a test.

**Residual, accepted:** `cdp compact`'s `VACUUM` takes SQLite's exclusive lock
for its whole duration; an unlocked reader will see `SQLITE_BUSY`. `compact` is
rare and explicit — return 503 with a clear message rather than engineering
around it. WAL (`PRAGMA journal_mode=WAL`) would remove reader-blocking
entirely and is worth doing, but it is now a latency optimisation rather than a
prerequisite, and it carries a migration for existing `index.db` files and does
not work over network filesystems.

**`query` belongs on the read side.** It is `@_locked(shared=True)`
(`cli.py:906`) — pure artifact reads, no git, no model calls — and
`query.dispatch` (`query.py:1332`) is already the clean library seam shared by
the CLI and `mcp_server`. The "expensive and repetitive" argument covers
`scan`/`refresh`/`run`/`reflect`; it does not describe `query`. Routing it
through the lock would kill the ask-bar — the connective tissue of §4 — for the
40 minutes a wave runs.

**The one read that is not cheap: freshness.** `claim_bucket`
(`cdp/freshness.py:79`) shells out to `git log --follow -M100%` per anchored
file, cached only for the duration of a single call. Under this split it is
conspicuous: the single expensive thing in an otherwise-free read path. It
needs a persisted churn cache — `churn_cache(path, since_sha, head_sha,
churned)` in the store, populated during fold, which already re-verifies
anchors. Until that exists the Freshness lens is a multi-second spinner, not a
recolor.

### 7.1 Surface

```
GET  /api/repos                      list scanned state dirs + HEAD vs as_of
GET  /api/graph?level=&scope=        nodes+edges for one altitude
GET  /api/node/:id                   claims, evidence, unknowns, in/out flow
GET  /api/trace?from=&to=&max-hops=  dataflow paths (wraps `query trace/paths`)
GET  /api/query?kind=&term=&budget=  delegates to `query.dispatch`
GET  /api/source?file=&line=&ctx=    NEW: file bytes for the code-peek pane
GET  /api/diff?old=&new=             wraps `diff --json`
GET  /api/status                     NEW json: wraps status/freshness/coverage
GET  /api/link?service=              wraps `link query --json`
GET  /api/doctor                     reads <state>/doctor/*.json + aggregate
GET  /api/trajectory?shape=          trajectory corpus query
GET  /api/events                     SSE: snapshot_run/snapshot_task deltas
POST /api/run   POST /api/refresh    guarded mutations, single-flight
```

Every response carries the pinned `snapshot_id` and `touch_seq`. Without a
version token on each payload the Atlas will happily paint a mix of pre- and
post-fold state, and TanStack Query has nothing correct to key its cache on.

`/api/source` is new and was missing from the first draft: the code-peek pane
needs file bytes, and no other endpoint serves them. It reads the **repo**, not
the store, so it is a new trust boundary and needs path-traversal confinement
to the repo root.

### 7.2 Design constraints

1. **The web layer is a client of the CLI's semantics, not a second
   implementation.** Every read endpoint delegates to the functions
   `cdp/cli.py` calls. Divergence between what the web shows and what `cdp
   query` says would be fatal to trust — and per §6.1 this is now *enforced*
   by a Pydantic-model contract test, not merely intended.
2. **The `--json` gap is a refactor, not a flag.** `cmd_status`
   (`cli.py:1911`) interleaves computation and `print()` line by line; there is
   no `status() -> dict` to call. Compare `query.dispatch` (`query.py:1332`),
   which is already a clean seam serving both the CLI and `mcp_server` — that
   is the shape `status`, `doctor`, `refresh` and `lessons` need. Order:
   `status` → `doctor` → `refresh --preview`, because those are the three
   load-bearing Control Room tiles and each pays off in the CLI immediately.
3. **Reads are read-only at the driver.** Open SQLite as
   `sqlite3.connect("file:…/index.db?mode=ro", uri=True)`, thread-local. The
   server then structurally *cannot* write — the read/mutation seam is
   enforced rather than promised. Operational footgun to handle: a read-only
   connection cannot recover a journal left by a crashed writer; catch that and
   say "run any `cdp` command to recover state" rather than rendering an empty
   graph.
4. **Mutations shell out, and coalesce.** `POST /api/run` spawns
   `cdp run` as a subprocess rather than calling `supervisor` in-process: it
   inherits the lock, `--resume`, and the repo-mismatch guard
   (`_check_repo_matches_manifest`) for free, and a crashed run cannot take the
   server down. Because a second concurrent `refresh` produces nothing the
   first will not, these endpoints are **single-flight**: a second POST while
   one is in flight returns the in-flight job's handle rather than enqueuing.
   `run --resume` already gives idempotent join semantics (`cli.py:1560-1590`).
   Decide join / 409 / queue explicitly — the Control Room's button states
   depend on it.
5. **Mutations are explicit, confirmed, and attributed.** `run`/`reflect` spend
   model tokens. Show an estimated scope count and the exact runner command
   before dispatch; the run must stay cancellable and resumable.
6. **Localhost-only, and check `Origin` on the POSTs.** Binding `127.0.0.1`
   with a session token is the honest posture for a local dev tool's *reads*. A
   POST that executes a configurable `--runner-cmd` is a different risk class:
   any page in the user's browser can POST to `127.0.0.1`. Require a
   non-cookie token and an `Origin` check on the mutation surface. Concentrating
   every dangerous operation behind two endpoints makes that check the whole
   security boundary — which is good, provided it exists.

### 7.3 Still open, carried forward

- **No node identity scheme.** Four namespaces with no join key:
  `graph.modules` (module names), `partition.scopes[].node` (`root/…`),
  `xref.symbols` (FQNs), and claim `subject` — an FQN *or* table *or* route
  *or* config key (`schema/patch-1.0.0.json:59`). `/api/node/:id` cannot exist
  until IDs are namespaced (`module:`, `scope:`, `file:`, `sym:`, `route:`,
  `table:`) and the roll-up rule for "which claims belong to this module" is
  written down — including what happens when `source_node` and the evidence
  anchors disagree, which they can.
- **`query._claim_module` (`query.py:990`) linear-scans `inventory.files` per
  anchor** — O(claims × anchors × files). Fine at 377 files, not at 10k. Build
  `file → module` and `module → claims` indices once at server start.
- **Backend polymorphism is unhandled.** The surface above assumes
  `SqliteStore`. On `FileStore`, `supports_run_tracking()` is false
  (`cli.py:1560`) — no run console at all. On Postgres there is no per-snapshot
  directory, so `/api/doctor`'s `<state>/doctor/*.json` reads have nothing to
  read. Decide per endpoint: degrade, hide, or refuse.

---

## 8. Ranked build order (wow ÷ effort)

| # | Feature | Wow | Effort | Note |
|---|---|---|---|---|
| 0 | Read-only store access + manifest-pinned snapshot + `status()` extraction | ☆ | M | Invisible, and the actual spine. Items 4 and 6 and half of 3 are blocked on it. §7.0/§7.2. |
| 1 | Altitude canvas L3→L2→L1 + hover peek + click inspector | ★★★★ | M | Everything else attaches to it. Needs the node-ID scheme in §7.3 first. |
| 2 | Animated anchored path trace | ★★★★★ | S | Data is already in `dataflow.paths`. Highest ratio in the doc. |
| 3 | Lens modes — Divergence and Confidence first | ★★★★ | S | Recolor only for these two. Divergence is unique to CDP. |
| 3b | Freshness lens | ★★★★ | **M, backend** | *Not* a recolor: `claim_bucket` shells out to `git log --follow` per anchored file (`freshness.py:79`). Needs the persisted churn cache in §7.0 first. |
| 4 | Control Room run console over `snapshot_task` | ★★★★ | M | Live state transitions sell the agent story. |
| 5 | Ask-bar that answers *onto* the canvas | ★★★★ | M | Needs typeahead index from `xref.symbols`. |
| 6 | Repo health strip + one-click refresh | ★★★ | S | Directly answers "are we behind the repo?" |
| 7 | Agent-layer hookup tab + liveness check | ★★★ | M | Explicit user ask; `install --framework` exists. |
| 8 | L4 cross-repo constellation | ★★★★ | M | Needs ≥2 scanned repos to look like anything — prepare a demo set. |
| 9 | Time scrubber / commit replay | ★★★★ | M | Depends on multiple snapshots existing. |
| 10 | Doctor heatmap, trajectory explorer | ★★★ | M | Deepest, narrowest audience. Last. |

---

## 9. Stress tests against my own design

| Case | What breaks | Mitigation built into the design |
|---|---|---|
| This repo scans to **0 % coverage** | A grey, "broken-looking" graph on first run | Deliberate pre-review styling + "dispatch wave 0" CTA (§5) |
| `xref` is **1.04 MB** at 377 files | Shipping it whole to the browser won't scale 10× | Server-side pre-layout, per-altitude payloads, on-demand subgraph fetch (§6) |
| Symbol altitude = 1,967 nodes here, 50k elsewhere | Labels + hit-testing jank before node count does | LOD: labels only above a zoom threshold, cluster below it; benchmark gate before committing to Sigma |
| Dense hover targets | Peek card fights the cursor; flicker | 120 ms open delay, 250 ms close grace, card offset away from the node, pinning on click |
| Wheel-based altitude change | Hijacks page scroll; users get lost | Pointer+focus gating, `Esc` to ascend, browser-back history, pinch ≠ wheel (§3) |
| A 40-minute `run` | SSE drops, tab sleeps, user closes laptop | Status is derived from the lease table on reconnect, not from stream memory — refresh always recovers truth |
| A 40-minute `run`, **lock contention** | If reads took the repo lock they would block 60 s then error for the whole run — killing §2's "dispatch a wave, watch the Atlas light up" | Reads bypass the lock on a `mode=ro` connection. Safe because exactly one artifact (`state`) mutates during a run, and `write_artifact` replaces it atomically (§7.0) |
| A `refresh` starting mid-session | `begin_snapshot` bumps `touch_seq` before `state` is written; a reader following "latest" sees a full graph with **zero claims** for the whole fold | Select the latest snapshot **that has a `manifest`** — written last in both paths (`cli.py:746`, `:1379`) — and pin it. Needs a test: the guarantee is currently an accident of write order |
| `cdp compact` running | `VACUUM` holds SQLite's exclusive lock; unlocked readers get `SQLITE_BUSY` | Accepted. `compact` is rare and explicit — 503 with a clear message |
| Crashed writer left a hot journal | A `mode=ro` connection cannot recover it and errors | Catch and surface "run any `cdp` command to recover state", never an empty graph |
| State on `FileStore` or Postgres | `FileStore` has no run tracking (`cli.py:1560`); Postgres has no `<state>/doctor/*.json` | Decide per endpoint — degrade, hide or refuse. Do not let the UI imply the feature is broken |
| Model claims a wrong anchor | UI would launder a bad claim as fact | Never render a claim without its `anchor_verified_at` vs HEAD state; unverified anchors render dotted + amber, not neutral |
| Color-coded epistemics | Colorblind users lose the entire meaning layer | Stroke style + glyph redundancy is mandatory, not a setting (§5) |
| `prefers-reduced-motion` | The whole product is motion | Every animated affordance has a static equivalent (path trace → ordered hop list) |
| Two repos with the same module name at L4 | Ambiguous nodes, wrong merges | `link scan` already separates matched vs **ambiguous**; render ambiguity as a distinct edge type with a "resolve via `link prompts`" action — don't silently unify |
| Mobile | Canvas navigation is desktop-shaped | Ship a read-only responsive Control Room; state plainly that the Atlas is a desktop surface rather than degrading it badly |

---

## 10. What not to build

- **No embeddings, no vector search, no "AI explains your codebase" panel that
  isn't citation-backed.** The entire value of this UI is that every pixel
  traces to a `file:line`. A hallucinating summary box would poison it.
- **No 3D graph** unless someone demands it. It costs frame budget and
  costs legibility; 2026 trend write-ups flag WebGL 3D as the highest-risk item.
- **No write path into the repo from the browser.** `answer` (human claims) is
  the only content the UI should be able to add, and it goes through the same
  validate → verify → entail → fold pipeline as a leaf patch.
- **No second query language.** The ask-bar speaks CDP query kinds.

---

## 11. Questions — resolved and still open

### Resolved

| # | Question | Decision |
|---|---|---|
| 3 | Is `cdp serve` in scope, or does the web layer read `index.db` directly? | **Both, split by operation.** Reads go direct to storage on a `mode=ro` connection, no repo lock. Mutations shell out to the CLI. Query semantics are never reimplemented — handlers delegate to `query.dispatch` (§7.0, §7.2). |
| — | May the web layer have dependencies? | **Yes.** It is a subproject with its own dependency boundary; `cdp/` stays dependency-free and `tests/test_core_purity.py` keeps it that way. This is the `mcp_server/` pattern, not a departure from it (§6.1). |
| — | Backend framework? | **Python + FastAPI + uvicorn + Pydantic.** Sync `def` handlers; Pydantic models double as the CLI-parity contract (§6.1). |
| 4 | Commercial distribution — is Cosmograph on the table? | **No, and the question is moot.** `@cosmograph/cosmos` is `CC-BY-NC-4.0`; non-commercial fails the Open Source Definition, so it is out either way (§6.0). |
| — | Where does layout run? | **Client-side**, cached in IndexedDB by `snapshot_id`. Server-side pre-layout would enter the determinism gate; it stays a documented escape hatch (§6.3). |

### Still open

1. **Scale target** — biggest repo to demo on? Decides whether Sigma 3.0.3
   holds at L0 or we cluster below a zoom threshold, and whether server-side
   pre-layout moves from escape hatch to day-5 work.
2. **Demo corpus** — is there a set of ≥2 scanned repos with real cross-repo
   edges? L4 (the constellation) is the most striking view and needs one.
3. **Does CDP get a `LICENSE` file, and which one?** Blocking for open-sourcing
   anything here, and larger than any dependency question (§6.4).
4. **Single-flight semantics** — join, 409, or queue? The Control Room's button
   states depend on it (§7.2.4).
5. **Does the hackathon judge sit at the Atlas or the Control Room first?**
   The first 15 seconds should be the path-trace animation; confirm.

---

## 12. Sources

Graph rendering: [Sigma.js](https://www.sigmajs.org/) (the shipped line — 3.0.3) ·
[v4.sigmajs.org](https://v4.sigmajs.org/) (**pre-release docs**; v4 is
beta-only on npm, see §6.0) ·
[Cytoscape vs vis-network vs Sigma, 2026](https://www.pkgpulse.com/guides/cytoscape-vs-vis-network-vs-sigma-graph-visualization-2026) ·
[Cosmograph library comparison](https://cosmograph.app/library/compare/) ·
[Top JS graph visualization libraries (Linkurious)](https://linkurious.com/blog/top-javascript-graph-libraries/) ·
[Rendering large force-directed graphs on the web](https://weber-stephen.medium.com/the-best-libraries-and-methods-to-render-large-network-graphs-on-the-web-d122ece2f4dc) ·
[Graph visualization with Sigma + React](https://lyonwj.com/blog/sigma-react-graph-visualization) ·
[Neo4j: 15 graph visualization tools](https://neo4j.com/blog/graph-visualization/neo4j-graph-visualization-tools/)

Design language: [UI/UX trends 2026 — spatial UI & glassmorphism 2.0](https://superfiles.in/ui-ux-design-trends-2026-spatial-glassmorphism.php) ·
[UI design trends 2026 (Midrocket)](https://midrocket.com/en/guides/ui-design-trends-2026/) ·
[Bento grids & beyond](https://writerdock.in/blog/bento-grids-and-beyond-7-ui-trends-dominating-web-design-2026) ·
[What's actually shipping in 2026](https://rajeshrnair.com/blog/design/ui-ux/ui-design-trends-2026-bento-grids-glassmorphism.html) ·
[UX trends 2026: AI, bento grids, zero UI](https://espiolabs.com/blog/posts/ux-trends-2025-from-ai-assisted-design-to-bento-grids-what-actually-works) ·
[Tactile brutalism & invisible architecture (Fireart)](https://fireart.studio/blog/the-best-web-design-trends/) ·
[12 UI patterns to adopt](https://mediaplus.com.sg/ui-trends/)

Licence and version verification (second pass, read from the registries on
2026-09-21, not from documentation): `registry.npmjs.org` `/latest` and
`dist-tags` for every frontend package in §6.2 plus `elkjs`, `monaco-editor`,
`cytoscape`, `vis-network` and `@cosmograph/cosmos`; `pypi.org/pypi/<pkg>/json`
`license_expression` for `fastapi`, `uvicorn`, `pydantic`, `starlette`,
`sse-starlette`.

Internal: `RESEARCH_GRAPHIFY.md`, `README.md`, `ARCHITECTURE.md`,
`cdp/store/__init__.py`, `cdp/store/sqlite_backend.py`, `cdp/cli.py`,
`cdp/lock.py`, `cdp/query.py`, `cdp/freshness.py`, `cdp/doctor.py`,
`cdp/trajectory.py`, `mcp_server/server.py`, `mcp_server/schemas.py`,
`schema/patch-1.0.0.json`, `tests/test_core_purity.py`, `pyproject.toml`, and a
live probe scan of this repo at `81f731d`.
