# Frontend TODO — gaps vs `WEB_RESEARCH.md` / `PLAN.md`

## Web-layer pain points from `RESEARCH_PAIN_POINTS.md` (2026-09-23)

Plan approved and parked here before implementation; full context in
`RESEARCH_PAIN_POINTS.md` and the approved plan. Two of that doc's own
conclusions were stale, verified against current code before planning:

- `MONOREPO_HIERARCHY.md`'s entire design (variable-depth rungs
  `encoding.py:159-193`, server ladder `models.py:211-233`, breadcrumb stack
  `atlasStore.ts`/`AltitudeSwitcher.tsx`, edge-rollup `app.py:556-568`) is
  **already implemented** — no hierarchy work needed, treat that doc as done.
- Search/jump-to-node is **not** absent — `AskBar.tsx` already does this
  (cmd-K, typeahead, `jumpTo`/`selectNode`/`startTrace`). Only a narrower gap
  (free-text/fuzzy search) remains, and it's not in scope this pass.
- "Spins forever" root mechanism is now precisely located (not just
  theorized): `InspectorRail.tsx:25` and `PeekCard.tsx:26` destructure only
  `data` from `useNodeAt`, discarding `error`/`isLoading`, so a stuck or
  errored fetch renders a permanent, indistinguishable `"loading…"`.
  `client.ts`/`hooks.ts` have no abort/timeout/bounded-retry. `ErrorBoundary.tsx`
  can't help — it only catches sync render-time throws, not async fetch
  errors. Backend `/api/graph` (`app.py:786-804`) does unbounded synchronous
  work with no timeout/pagination — plausible contributor on large repos, but
  **unconfirmed by any timing/log capture**, so backend changes are held back
  pending real evidence (see open question below), per this repo's
  debugging-process rule.
- The dagre jitter fix's "verified via a 7-node chain" comment
  (`graphLayout.ts:155-156`) is a dev note, not a test — no
  `graphLayout.test.ts` exists, never checked at this repo's real L2 scale
  (353 nodes).
- No node-position animation exists anywhere (only a whole-canvas opacity
  fade, `AtlasCanvas.tsx:577-584`) — altitude transitions snap instantly.

Checklist (ordered by risk/confidence; item 3 gates further layout-code
changes; item 4 sequenced last):

- [x] **1. Fix stuck-loading bug (client-side).** `InspectorRail.tsx`/
      `PeekCard.tsx` now render distinct loading/error/not-found states off
      `useNodeAt`'s `error`/`isLoading`, with a manual retry button on error
      instead of a permanent bare "loading…". `hooks.ts`'s `useGraph`/`useNode`
      forward react-query's `signal`, composed via `AbortSignal.any` with a
      15s `AbortSignal.timeout` (`withTimeout` helper), and set `retry: 2`
      (bounded, not the implicit unbounded default from the zero-config
      `QueryClient`). `tsc -b` clean on touched files (one pre-existing,
      unrelated `AtlasCanvas.tsx` type error predates this work); `npm test`
      30/30 green. Not yet verified live in a browser against an actual
      stuck/errored request — worth a manual check per the plan's
      verification section before calling this fully closed.
- [x] **2. Double-click discoverability affordance.** `AtlasCanvas.tsx`'s
      `enterNode`/`leaveNode` handlers now set the canvas container's
      `cursor` to `pointer` while hovering a node whose altitude has a
      `nextRung` to descend into (`default` at a leaf altitude or off-node),
      so hover no longer looks identical regardless of whether double-click
      would do anything. The existing hover ring/size boost (`isFocus` in
      `nodeReducer`) already gave hover *some* emphasis — this closes the
      cursor-affordance gap specifically. `tsc -b`/`npm test` clean (same
      one pre-existing unrelated `AtlasCanvas.tsx` rungs-type error, line
      number shifted only). Not yet eyeballed in a running browser.
- [x] **3. Verify layout at real scale (evidence gate) — passed, no code
      change needed.** New `graphLayout.test.ts` runs `layoutRanked` against
      a 353-node single-node-rank chain (the exact shape the jitter fix
      targets, at this repo's real L2 scale vs. the code comment's untested
      7-node claim) and a 353-node branchy tree, and runs
      `layoutForceAtlas2`+`noverlap` against a dense 353-node fan-out. All
      three pass: the chain doesn't collapse onto one x, the tree spreads
      across both axes, and noverlap keeps every pair separated, all within
      generous timing bounds. This is real evidence, not the old inline
      comment — the existing dagre jitter/noverlap tuning holds at this
      repo's real scale, so per the plan's own rule, left untouched.
      (Needed to mock `@sigma/edge-curve` in the test — importing
      `graphLayout.ts` pulls in real sigma WebGL internals that reference
      `WebGL2RenderingContext`, undefined outside a browser; neither tested
      function touches it.) `npm test` 33/33 green, `tsc -b` clean (same one
      pre-existing unrelated error). Only exercises synthetic shapes, not
      this repo's actual real L2 graph data — worth a spot check against a
      live `/api/graph` response if this becomes load-bearing later.
- [x] **4. Animate altitude transitions — position tween shipped; enter/exit
      fade stays at existing whole-canvas granularity, not per-node.**
      `AtlasCanvas.tsx`: `prepareTransition` captures, for every node id
      present in both the outgoing and incoming graph, its old position
      (from `prevGraphRef`, the previously-mounted graph) and its real
      final target position — captured *after* dagre (ranked) or the async
      FA2 pass (non-ranked) has actually settled, not off `buildGraph`'s raw
      return, since the latter is only the FA2 seed circle for non-ranked
      altitudes and would have tweened toward the wrong target. The new
      graph is published starting at the old positions; a new effect
      (`useEffect(..., [graph])`) eases every persisting node from old to
      new over `ALTITUDE_TRANSITION_MS` (250ms, ease-out-cubic) via
      `requestAnimationFrame`, mutating graph attributes and calling
      `sigma.refresh({skipIndexation:true})` per frame. Cancel-and-replace
      falls out of the effect's own cleanup (`cancelAnimationFrame`) firing
      whenever `graph` changes again — a rapid second altitude change
      can't stack animations. Skipped entirely under
      `prefers-reduced-motion` (checked fresh in `prepareTransition`, same
      convention as the existing whole-canvas fade).
      **Scoped down from the plan:** did not build per-node/edge ghost-node
      fade-in/out for entering/exiting nodes — that needs coexisting
      old+new nodes in one Sigma graph and was too large for this pass. The
      existing whole-canvas crossfade (`AnimatePresence`/`motion.div` keyed
      on `canvasKey`, `framer-motion`) still covers entering/exiting content
      at the coarser whole-frame granularity, which does already fade
      node+edges together atomically, just not per-node.
      Verified: `tsc -b` shows only the same pre-existing, unrelated
      `AltitudeSwitcher`/`Rung` type error in this file (present before this
      session's edits, blocks `npm run build` — not fixed here, out of scope
      for this plan, flagged separately). `npm test` 33/33 and `npm run
      lint` (same 11 pre-existing warnings, none new) both clean.
      **Not verified live in a browser** — no Playwright/browser automation
      available in this environment (same limitation noted in earlier TODO
      entries above). Worth an actual descend/ascend click-through once that
      tooling is available, or manually via `npm run dev`.

Open question, not a blocker: backend `/api/graph` response-time work
(`_dataflow_graph`, `app.py:678-737`) is deferred until item 1's new error
surfacing actually shows real timeouts happening in practice — no
profiling/log evidence exists yet to justify touching it.


## Query-time role exclusion (2026-09-22) — all three levels shipped

Three-level plan: CLI → web API/graph → frontend UI. All three shipped this
session.

- [x] **Level 1 — `cdp query --exclude-role`.** `cdp/query.py`: shared
      `_role_index(store)` (`path -> role` off `store.inventory["files"]`),
      threaded through `q_symbol`, `q_file`, `q_search`, `q_trace`,
      `q_routes`, `q_table`, `q_config`, `q_claims`, `q_unknowns`, and
      `dispatch()`. `q_module`/`q_conflicts` intentionally left unfiltered
      (no clean per-file row to filter on); `q_stats`/`q_coverage` reject the
      flag outright — they're whole-repo census/QA checks and silently
      dropping rows would misreport them. `cdp/cli.py`: new repeatable
      `--exclude-role ROLE` flag on `query`. Verified live against this
      repo's own `.cdp/index.db` (test-role rows drop, source-role rows
      survive, `stats`/`coverage` reject the flag with the intended error)
      and `make selftest`/`golden`/`determinism`/`fold` all still green.
      **Gotcha for next time:** `.claude/skills/cdp/cdp/` is a *generated*
      vendor copy of the real source at top-level `cdp/` — edit the source,
      then run `python3 -m cdp.cli install --self` to regenerate the vendor
      copy; don't hand-edit the vendored tree (`test_distribution.py` catches
      exactly this drift).
- [x] **Level 2 — web API passthrough + graph role tagging.** `/api/query`
      (`web/api/app.py`) now takes `exclude_role: Optional[List[str]] =
      Query(None)` and forwards it into `dispatch(...)` — mirrors the CLI
      flag exactly (verified live: `stats`/`coverage` still 400 with the same
      message, `search`/`file` accept and apply it). `/api/graph` gains a
      `role` field on every node at every level, not just `L1`'s file nodes —
      a new shared `_role_index(conn, snapshot_id)` (the web-connection
      equivalent of `cdp.query._role_index(store)`) resolves `path -> role`
      off the `inventory` artifact:
      - `L1` (files): direct `roles.get(path)`, as spec'd.
      - `L2`/`L3` (`_dataflow_graph`, `_build_graph_l3`): **not** spec'd
        originally, added after finding the frontend never renders `L1` at
        all (`atlasStore.ts`'s `DESCEND_ORDER`/`ASCEND_ORDER` only ever show
        `L2`/`L3` — `ATLAS_REDESIGN.md` cut `L1` from the ladder for having
        almost no import edges). A bare `L2` id resolves a role only when it
        is backed by an `xref` symbol (`sites[0].file` → role); a `type:`-
        prefixed reference node (`table:`, `route:`, ...) has no file of its
        own and stays `role=None`. `L3` package/type-bucket nodes inherit a
        role only when every member that resolves one agrees — any
        disagreement, or no member resolving one at all, leaves it `None`
        rather than picking a majority that would misreport the rest.
      - New `hide_roles` query param on `/api/graph` drops every node whose
        `role` is in the list (never a `role=None` node) and any edge
        touching a dropped node, before the response and its `legend` are
        built — the level 3 escape hatch. `web/client/schema.ts` /
        `web/openapi.json` regenerated via `npm run generate` in
        `web/client` (the project's existing FastAPI→`openapi-typescript`
        codegen step — not hand-edited).
      Verified live against this repo's own index (`TestClient` + a real
      `uvicorn` process): `L1` 413→192 nodes under `hide_roles=test`; `L2`
      role counts `{None: 283, test: 12, source: 58}`; no edge in a filtered
      response ever touches a dropped node; `web/tests` (96 passed) and
      `make selftest` (561 passed) both green.
- [x] **Level 3 — frontend toggle.** "Hide tests" toggle added to
      `GraphLegend.tsx` (styled to match its existing `atlas-card` language —
      only rendered when the current altitude actually has `role=test`
      nodes, shows the count). Below `ROLE_HIDE_CLIENT_THRESHOLD`
      (`theme/graphEncoding.ts`, `2000`) it sets `hidden: true` on matching
      nodes/edges in `AtlasCanvas`'s Sigma reducers against the
      already-fetched graph — no refetch, `graph` (the `graphology` object)
      is never rebuilt, only `sigma.refresh({skipIndexation: true})` runs, so
      it costs a frame like a lens switch does. Above the threshold, the
      toggle instead enables a second `useGraph(..., {hideRoles: ["test"]})`
      query (`api/hooks.ts`) and swaps to its (smaller, pre-filtered) result.
      Toggle state (`hideTests`) is a plain `useState` in `AtlasCanvas` —
      session-only, not persisted, as spec'd.
      **Threshold caveat:** this environment had no browser automation
      available (no Playwright/similar tool), so `2000` was *not* verified
      against a live Sigma canvas on a large real repo, contrary to plan.
      What was measured: the reducer's own `Set.has` membership check costs
      <3ms even at 50,000 synthetic nodes, so the real bottleneck is Sigma's
      WebGL repaint, not this logic — `2000` is a documented estimate inside
      the range Sigma's own docs/community benchmarks call comfortably
      interactive, chosen conservatively. Every graph this repo itself
      produces today (`L2` tops out at 353 nodes) stays far under it either
      way, so this session's own testing never exercised the escape-hatch
      path against a real large graph. Re-verify live with Playwright against
      a bigger repo before trusting the exact number.
      Also not done: no browser/Playwright verification of the UI at all in
      this session (`tsc -b`, `oxlint`, and a production `vite build` all
      pass; the toggle's visual behavior was not eyeballed in a running
      browser).

## `ATLAS_REDESIGN.md` P0–P3 (2026-09-22)

Shipped P0 through P3; P4 (vignette, panel saturation, LOD labels) and P2's
background hulls are **not** done — they are the doc's own cut line.

- [x] **P0 data — the metric that was silently zero.** `renderable_edges /
      total` was 0.005 at L0 and the other altitudes had 1–2 edges to draw.
      L2 is now the typed `dataflow` graph as-is (353 nodes / 371 edges on
      this repo) and L3 is that same graph rolled up to 18 packages and type
      buckets (40 edges). L0 now emits only symbol-scoped edges instead of
      369 dangling module edges. Measured live: **1.000 renderable at every
      altitude**, zero isolated nodes. Pinned by
      `web/tests/test_graph_contract.py`, which asserts the ratio *and* a
      floor on nodes/edges — a ratio alone scores 1.0 on a 2-edge graph,
      which is exactly the state it was meant to catch.
- [x] **L1/L0 cut from the ladder, not styled.** §7 measured 2 import edges
      across 413 files. Both remain on the API (L0 backs the ask-bar
      typeahead) and remain under the contract test.
- [x] **P1 encoding.** All six channels carry data: fill = 3-colour family,
      shape = type (`@sigma/node-border` + `@sigma/node-square`), size = log
      degree, ring = claim confidence, edge colour = target family, arrows =
      direction, `@sigma/edge-curve` separates parallel edges. Shape collapses
      to a dot past `SHAPE_ZOOM_THRESHOLD` and the legend says so — §7's
      requirement that shape never be the silent sole identity channel.
- [x] **P2 layout.** `linLogMode` + `outboundAttractionDistribution` replace
      the bare `inferSettings` that caused the scatter; fit-to-viewport on
      mount. Verified by probe, not by eye: **0 nodes offscreen** at both
      altitudes. Nodes *were* sitting under the two permanently-mounted
      bottom panels, so `TracePanel`/`TimeScrubber` now collapse to chips.
- [x] **P3 tiles.** Every tile leads with the question it answers; the 0%
      coverage bar and the all-red freshness bar now say they mean "nothing
      has run yet", not "something failed"; `root/(agent_adapter+5)` renders
      as `agent_adapter +5 more` (`scopeLabel`, unit-tested).
- [x] **Divergence lens → Flow lens.** The declared/observed/both tags it
      coloured only existed on the `graph`-artifact edges P0 removed, so it
      would have been a no-op everywhere. Flow colours the same edges by
      extraction channel. The divergence counts still surface in the L3
      legend.
- [x] **`GET /api/confidence`.** The confidence lens used to fire one
      `/api/node` per visible node — fine at 20 scopes, 353 requests per
      toggle after P0. One bulk call now. Found and fixed two real bugs while
      wiring it: claim `subject`s are `dataflow`-style ids that
      `SubjectIndex` classifies as `None` (the inspector showed 0 claims for
      every typed node), and `/api/node` matched dataflow edges against the
      *unprefixed* id, so `route:`/`table:` neighbourhoods were always empty.

Deferred, with reasons:
- Background hulls per package (`@sigma/layer-webgl`) — P2's own cut item.
- P4 polish (vignette, `saturate(165%)`, LOD labels) — doc says cut first.
- Hierarchical edge bundling — §4: no maintained WebGL implementation, a
  bespoke build rather than a drop-in.


Audited 2026-09-22 against the live `web/api/app.py` surface and the current
`web/frontend/src` tree. Backend endpoints already exist for every item below
unless noted "no backend endpoint either" — these are frontend-consumption
gaps, not blocked on backend work, except where flagged.

## Verify & harden pass (2026-09-22, ran both servers live against this repo)

- [x] **`/api/repos`/`RepoHealthStrip` showed the wrong repo** — this repo's
      git-remote identity was never in `~/.cdp/config.toml` (only a stale
      `unified-store` entry was), so `repos.repos[0]` rendered that unrelated
      repo's `no index.db` error instead of this repo's real HEAD/coverage.
      Fixed in `get_repos` (`web/api/app.py`): it now resolves the caller's
      actual repo/state_dir first and guarantees that row is index 0,
      registry-registered or not. Verified live: HEAD/as_of now both show
      `72647da1a4`, no error.
- [x] **`TrajectoryExplorer` duplicate React keys** — `run_id` alone repeats
      across a run's scopes, and `run_id`+`node` also repeats in the real
      corpus (distinct/duplicate rows share both). Confirmed live via
      `/api/trajectory` (one `run_id` had 90 rows). Fixed by keying on
      `` `${run_id}:${node}:${index}` `` — safe since the table never reorders.

Both verified by driving the actual dev server + FastAPI backend with
Playwright against this repo's real `.cdp/index.db`, not just unit tests.

## Verify & harden pass (2026-09-22, second pass — live-ran every mutation)

- [x] **Every Control Room mutation (`dispatch`, `refresh`, `resume run`,
      hookup `install`/liveness) 403'd through the standard `npm run dev`
      workflow** — `vite.config.ts`'s proxy sets `changeOrigin: true`,
      which rewrites the outgoing `Host` header to the FastAPI target but
      does *not* touch the browser's `Origin` header. `web/api/auth.py`'s
      `require_mutation_auth` compares `Origin` against
      `request.url.netloc` (built from `Host`), so the browser's real
      `http://localhost:5173` never matched the rewritten
      `http://127.0.0.1:8000` and every mutation route rejected with 403
      — the previous "all built" note above was accurate for the code
      paths that render, but nobody had actually clicked dispatch through
      the dev proxy. Fixed by rewriting the outgoing `origin` header in a
      `configure` hook on the proxy entry. Verified live: token save →
      dispatch → `POST /api/run` now returns 200 (job started), refresh
      likewise; confirmed via Playwright driving the real dev server, not
      just curl.

## Phase 3 — Control Room (core shipped, two pieces missing)

- [x] Repo health strip, run console, dispatch/resume, SSE live overlay + poll
      fallback, mutation token gate, ask-bar with typeahead — all built.
- [x] SSE live-overlay key mismatch (`scope_hash` vs resolved `node`) — fixed:
      `_events_stream` now emits the resolved `node` name (`web/api/app.py`),
      `RunTaskEvent`/`useRunEvents` updated to match (`controlRoomHooks.ts`).
- [x] **Agent-layer hookup tab** (§4 item 1, §8 rank 7) — shipped: five new
      backend endpoints (`/api/hookup/preview`, `/api/hookup/install`,
      `/api/hookup/mcp-tools`, `/api/hookup/liveness`, `/api/job/{id}`) over
      `cdp install --framework`, `cdp doctor --node` (repurposed as the
      liveness probe) and `mcp_server.schemas.TOOL_SCHEMAS`; frontend
      `HookupTab.tsx` wired into `ControlRoom.tsx` with preview/install,
      liveness check (poll-driven), and MCP tool list + copy-to-clipboard.
      Covered by `web/tests/test_hookup_endpoint.py`; exercised manually
      end-to-end against a scratch target and a scanned fixture repo.
- [x] Doctor / model compatibility heatmap (§4 item 4) — shipped:
      `DoctorHeatmap.tsx` renders `/api/doctor`'s `models` dict as a
      models × metrics table (schema validity, anchor survival — averaged
      client-side from `scope_reports[].anchor_survival`, not in
      `aggregate()` — entailment rate, recall, false-unknown, inverted so
      green=good throughout), colored via the existing
      `theme/confidence.ts` scale. Empty state (no `doctor/` dir yet, the
      live state of this repo) verified end-to-end against the real
      backend, not assumed. Per-row control reuses the existing
      `useLivenessMutation`/`useJobStatus` flow (labeled "run liveness
      check", not a fake "re-run full doctor" claim — no backend endpoint
      exists for a full multi-scope re-run).

## Phase 4 — Reach

- [x] **Module-link constellation, shipped as *intra-repo*, not cross-repo**
      — the earlier gate failure (`link_edge` had 0 rows, no second
      registered repo) is now satisfied honestly: ran the real
      `cdp link scan .cdp --db .cdp/index.db` against this repo's own
      scanned snapshot, which persisted 1 real matched link
      (`WidgetEntity.java` <-> `V001__create_widget.sql`, a genuine
      caller/callee pair inside `tests/fixtures/minirepo/core`) and 73
      real unmatched outbound `persist` calls from this repo's own code
      (`(root)`, `tests/fixtures/minirepo/core`,
      `tests/fixtures/solorepo`). No second repo is registered, so this
      ships labelled "Module links (intra-repo)" rather than claiming a
      cross-repo constellation — the scope call the user confirmed over
      fabricating a second repo's edges. Backend: `GET /api/links` +
      `LinksResponse` (`web/api/app.py`, `web/api/models.py`), covered by
      `web/tests/test_links_endpoint.py`. Frontend: standalone
      `LinksCanvas.tsx` (own Sigma mount + `graphology-layout-forceatlas2`
      layout, not a retrofit of `AtlasCanvas` — L4 has no altitude/
      drill-down axis) wired into `App.tsx`'s `ViewSwitcher` as a "Links"
      entry, gated to only appear once `edges.length > 0`. Verified live
      via Playwright against the real dev server: renders the real
      74-edge graph, no console errors. Architected so a second real
      repo's edges slot in later (nothing assumes single-repo `module`
      values) — that expansion is still a follow-up, not done here.
- [x] **Time scrubber / commit replay** — the earlier gate failure
      (`snapshot_meta` had only 2 rows, needed ≥3) is now satisfied
      honestly: replayed this repo's own real git history via
      `git worktree add` (shares this repo's `.git`, so
      `repo_identity()`'s remote-derived `repo_id` lands in the same
      shared `index.db`) for commits `81f731d` and `2228906`, then
      removed both worktrees. A later rescan of the current working tree
      added a 4th real row (`72647da...+dirty:...`, since the tree has
      genuine uncommitted changes), so the timeline is 4 real points, not
      fabricated commits. Backend: `GET /api/snapshots` +
      `SnapshotMetaResponse`/`SnapshotsResponse`
      (`ReadOnlyConnection.snapshot_history`), covered by
      `web/tests/test_snapshots_endpoint.py`. Frontend: new
      `TimeScrubber.tsx` panel (Atlas view) — a slider over the real
      commits that calls the existing `/api/diff` on each scrub and pushes
      the touched L3 module ids into `atlasStore`'s new `diffHighlight`
      slot, which `AtlasCanvas` pulses (mutate-in-place + `sigma.refresh()`,
      same non-relayout pattern as the confidence-lens effect) then fades
      after 2.2s. Verified live via Playwright: scrubbing between real
      commits shows real route-added/removed findings and re-renders the
      canvas with no console errors.

## Phase 5 — Long tail

- [x] Trajectory explorer (scoped) — shipped: `TrajectoryExplorer.tsx` +
      new `useTrajectoryRuns` hook over the real, populated
      `~/.cdp/trajectories.db` (540 live rows). Filters by `scope_shape`
      (server-side, re-queries `/api/trajectory?shape=`), `state` (client-
      side; real values found are `validated`/`abandoned`, not hardcoded),
      and `elision_regret` (client-side). **Lesson version diff / holdout
      before/after bar cut this cycle** — checked the gate directly against
      `cdp.reflect.select_outliers`'s own deterministic criteria
      (`contradicted > 0` OR `tokens_est >= 5000 AND claims_emitted == 0`,
      `cdp/reflect.py:72-88`) rather than assuming: queried the real
      `~/.cdp/trajectories.db` (`fact_leaf_run`, 540 rows across 4 real
      `run_id`s) and **zero rows qualify either branch** — no row has
      `contradicted > 0` (508 are `0`, 32 blank/NULL), and the 520 rows
      with `claims_emitted = 0` top out at `tokens_est = 1154`, well under
      the 5000 threshold. `cdp reflect` therefore has no real outlier to
      hand a runner, so `lesson_promotion`/`lesson_cut` stay empty and no
      API endpoint was added for them — populating this would require
      either running new leaf agents against a task designed to genuinely
      spend a lot of tokens or hit a real contradiction (to produce
      qualifying rows honestly), or fabricating one, which was ruled out.
      Not attempted further this cycle; revisit once the corpus actually
      contains a qualifying run.
- [x] Licence gate in CI — shipped:
      `web/frontend/scripts/check-licenses.mjs` (`npm run check-licenses`)
      walks actually-installed `node_modules/**/package.json` (not
      `npm ls --json`, which also lists undownloaded optional platform
      binaries with no licence metadata — a false-failure trap found while
      building this) against an allowlist (MIT, Apache-2.0, BSD-2/3-Clause,
      ISC, 0BSD, MPL-2.0, Python-2.0), handling SPDX `OR` dual-licence
      expressions. MPL-2.0/Python-2.0 were added to the original
      MIT/Apache-2.0/BSD/ISC allowlist as a deliberate, user-confirmed call
      after auditing what's actually installed (`lightningcss` — Tailwind
      v4's build-time CSS compiler, never shipped in app code; `argparse` —
      transitive via `@cdp/web-client`'s codegen-only `openapi-typescript`
      devDependency). Wired into `.github/workflows/frontend-licenses.yml`,
      path-filtered to only run when the frontend/client dependency tree
      changes.
- [ ] `LICENSE` file for CDP itself — explicitly deferred this cycle (user
      declined to pick a licence when asked); still flagged in
      `WEB_RESEARCH.md` §6.4 as a legal-exposure item, not closed.

## `WEB_REDESIGN_RESEARCH.md` — container hierarchy + layout gate (2026-09-23)

Implements that doc's own recommended first two phases (§7): the path-based
container tree (§3.1) and a dagre aspect-ratio gate (§3.3). Everything else
in the doc (§3.2 compound/expand-in-place canvas, ELK/Cytoscape swap,
`/api/search`, minimap, artifact caching, noverlap-in-worker, empty/error
copy, freeze-gate instrumentation) is out of scope this pass — see the
deferred list below.

- [x] **Path-based container hierarchy.** `encoding.package_of`/`real_depths`
      grouped a `dataflow` node by segments of its own **id string**
      (`_SEGMENT_SPLIT`), never by the file it actually lives in — harmless
      on this repo's dotted Python ids, but on a real Java/C# repo with bare
      class-name ids it made every node its own singleton "package" (823 of
      them, measured against the real `unified-store` index). Added, as new
      functions alongside the old ones (not in-place edits, so the existing
      dotted-id contract/tests stay intact): `resolve_owner_file` (node → its
      owning file, via `xref.symbols` for bare ids or a `schema_own`/
      `http_in` ownership edge for `table:`/`route:`-style ids),
      `path_group_of`/`container_group`/`container_descendant` (group by
      directory-path prefix instead of id-string prefix), and
      `real_container_depths` (same fork-detection loop as `real_depths`,
      over resolved paths). Wired into `app.py`'s `_dataflow_graph` (attaches
      a `file` field per node), `_graph_rungs`, `_build_graph_grouped`, and
      `_restrict_dataflow_to_scope`. Unit tests in
      `web/tests/test_encoding_depth.py` (new `ResolveOwnerFileTest`/
      `PathGroupOfTest`/`ContainerGroupTest`/`ContainerDescendantTest`/
      `RealContainerDepthsTest` classes) and updated
      `web/tests/test_graph_endpoint.py` L3/L2-scope tests (previously
      asserted the old, wrong id-string grouping as if it were correct;
      rewritten to assert the file-path grouping `_build_graph_grouped`
      actually produces now). Full suite: `python3 -m pytest web/tests -q` →
      130 passed, 1 skipped, 45 subtests passed, no regressions.
- [x] **Gated against the real `unified-store` index**, not just the
      `minirepo` fixture (94MB `.cdp/index.db` at
      `/Users/sharmp49/git/unified-store/.cdp`), per §7 step 1 — reporting
      the actual numbers, not claiming a clean pass: of 6,064 dataflow nodes,
      3,680 (61%) resolve to a real file via `resolve_owner_file`. The top
      rung's **8 real top-level module directories now appear and dominate
      the counts** (`exposure-snapshot` 806, `managed-sql` 780,
      `service-api` 765, `catalog-service` 544, `sql-pool` 379,
      `client-java` 348, `core` 43, `ms-sql-java` 10) — the fix's actual
      goal, previously impossible since those directory names were never
      consulted. Total top-rung group count is 388, not ~8, because of two
      remaining gaps, both concrete and bounded, not yet fixed:
      - 372 groups are singletons: bare ids with no *exact* `xref.symbols`
        entry of their own — mostly C# namespace-aggregate ids (e.g.
        `RMS.UnifiedStore.Core.App`) where only their leaf members have a
        symbol/file, not the namespace id itself. `resolve_owner_file` only
        does an exact lookup; it does not walk up to a resolvable
        descendant. Follow-up: extend it to fall back to the nearest
        resolvable dotted-prefix descendant, once a way to do that without
        an O(n·m) scan per request is worked out.
      - ~60 ids use type prefixes (`config-file:`, `sql:`) that aren't in
        `encoding.PREFIX_TYPES`/`BUCKET_OF_TYPE` at all, so `type_of`
        silently treats them as bare module ids instead of a recognized
        type bucket. Pre-existing gap, not introduced by this change — found
        during this validation pass, not fixed (out of scope: extending
        `PREFIX_TYPES` needs its own check against what buckets/colors those
        types should render as, `theme/graphEncoding.ts`).
      Bottom line: the doc's core defect (823 meaningless singletons, real
      directories never surfacing) is fixed; the remaining 372+60 stragglers
      are a smaller, different, and now precisely characterized problem.
- [x] **Dagre aspect-ratio guard**, `graphLayout.ts`'s `layoutRanked`. Two
      fixes, found by testing against a hub-fanout shape (one node, ~60
      direct children — the shape that measured 284:1 on the real L2 graph):
      1. If the primary (`rankdir: "TB"`) layout's bbox aspect exceeds 4:1,
         rerun once with `rankdir: "LR"` and keep whichever is more square.
      2. Transposing alone cannot fix a hub-and-spoke shape — rotating a
         1×60 line just produces a 60×1 line the other way. Added a second
         fix underneath: any single rank with more than 12 nodes gets
         reflowed into a roughly square grid (instead of one long line)
         before the aspect check runs.
      Building the grid surfaced a real bug during testing (self-caught,
      fixed same pass): once one rank's within-rank axis gets rewritten into
      a small, zero-centred grid, an *unwrapped* rank (e.g. a lone hub) can
      no longer trust dagre's own raw coordinate for that axis — dagre sizes
      each rank's raw spread independently, so the hub's original coordinate
      (calibrated against the *old*, much wider unwrapped layout) ends up
      enormous next to the new compact grid. Fixed by having every branch
      (sole node / merely-wide / grid-wrapped) centre its own rank's
      within-rank axis on 0, rather than relying on a single shared frame
      across ranks. New test in `graphLayout.test.ts` (`"keeps a
      hub-dominated graph's bbox aspect under control"`) asserts aspect
      ≤ 3:1 on that shape; the two pre-existing ranked-layout tests (long
      chain, branchy tree) still pass. `npx vitest run` (full frontend
      suite): 7 files, 34 tests, all passed.
- [ ] `tsc -b` has one pre-existing error (`AtlasCanvas.tsx:624`, a
      `Rung[]` type mismatch in `AltitudeSwitcher.tsx`) — confirmed via
      `git stash` that it's present on a clean checkout of this session's
      earlier (already-uncommitted) frontend redesign work, unrelated to
      and not introduced by this container-hierarchy/layout-gate change.
      Not fixed here; flagged for whoever picks that redesign work back up.
- [ ] Deferred, none attempted this pass:
      - §3.2 compound/expand-in-place container canvas — ELK.js/Cytoscape.js
        decision deliberately held until the real rung sizes above (388
        groups, long singleton tail) are addressed; picking a compound-node
        renderer before that would be designing against numbers known to
        still change.
      - `partition.scopes` label cross-reference for container group names
        (currently the raw resolved directory path, e.g. `sql-pool`, is used
        as-is; not cross-referenced against `partition.scopes`' own names).
      - Server-side `/api/search`, neighbourhood-focus toggle, minimap.
      - Artifact caching (§5 item 3), moving `noverlap` into the FA2 worker.
      - Edge-count label rendering on rolled-up container edges.
      - Empty/failure-state copy for the container canvas specifically.
      - `performance.mark` freeze-gate instrumentation (§7 step 3) — no
        capture of a real "loads forever" session was attempted.

## `WEB_REDESIGN_RESEARCH.md` — closing the two named §3.1 gaps + container-canvas basics (2026-09-23)

- [x] **`config-file:`/`sql:` prefix typing**, `encoding.py`. Re-measured
      against the real `unified-store` index rather than trusting the prior
      entry's "~60 stragglers" estimate: it's exactly two prefixes,
      `config-file:` (1,243 occurrences) and `sql:` (290) — not ~60 of mixed
      kinds. Both carry the owning file path as their own suffix (e.g.
      `config-file:.github/workflows/feature_flag_check.yml`,
      `sql:ms-sql-java/downgrade-processor/.../Rollback_V21_to_V18.sql`), so
      `resolve_owner_file` now resolves them directly from the id itself
      (`PATH_LITERAL_PREFIXES`) — stronger than just adding a bucket-table
      entry, since it also fixes their container grouping, not only their
      legend label. Added to `PREFIX_TYPES`/`FAMILY_OF_TYPE`
      (`"code"` — a source location, not a boundary or state surface)/
      `TYPE_ORDER`/`TYPE_LABEL`/`BUCKET_OF_TYPE`. 3 new cases in
      `test_encoding_depth.py`, real shapes pulled from the index, not
      fabricated.
- [x] **Descendant-fallback for namespace-aggregate ids**, `encoding.py`'s
      `resolve_owner_file`. Previously only an exact `xref.symbols` lookup —
      a bare id with no symbol of its own (a C#-style namespace-aggregate id
      whose *leaf members* have symbols but the namespace itself doesn't)
      always fell through to `None` and became its own singleton container
      group. Fixed with a `bisect`-based prefix probe over the request's
      symbol keys (sorted once per request, not per node): the first sorted
      key starting with `raw_id + "."` is treated as a representative
      descendant and its file used. O(log n) per node, not the O(n·m) scan
      the prior entry flagged as the reason this wasn't done yet. Documented
      as a first-match heuristic, not a majority vote — cheap and a strict
      improvement over "always singleton." 2 new cases in
      `test_encoding_depth.py`: one resolving through a descendant, one
      confirming a string-prefix sibling that isn't a *dotted-segment*
      ancestor correctly does not match.
      Re-ran the doc's own probe against the real `unified-store` index with
      both fixes applied: **208 groups** (was 388), **190 singletons** (was
      372), **3,865/6,064 ids resolved, 63.7%** (was 3,680/6,064, 61%). All 8
      real module directories now dominate top-rung group sizes (Config 917,
      service-api 820, exposure-snapshot 819, managed-sql 815, Tables 753,
      catalog-service 576, sql-pool 392, client-java 356, plus smaller real
      dirs); the remaining 190 singletons are namespace-aggregate ids with no
      resolvable descendant at all (not a regression in this fix, a
      different, smaller residual problem).
      `python3 -m pytest web/tests -q`: 133 passed, 1 skipped, 45 subtests
      (was 130 passed pre-pass — exactly +3 new cases, no regressions).
- [ ] **`partition.scopes` label cross-reference** — planned, not
      implemented. Checked against the real index first: `partition.scopes[]
      .module` already matches the container-group path format exactly on
      every scope sampled, so the planned cross-reference would be a no-op
      on real data today. Not implemented — writing dead code to "handle" a
      mismatch that doesn't currently occur would be untested by anything
      real. Left as a documented non-fix rather than silently dropped.
- [x] **Legend-as-filter**, `GraphLegend.tsx` + `AtlasCanvas.tsx`. Each
      family row in the legend is now a toggle button, same visual language
      as the existing "Hide tests" row (border/background swap,
      `aria-pressed`). A `hiddenFamilies: Set<Family>` lives alongside
      `hideTests` in `AtlasCanvas`, fed into the reducers' `stateRef` exactly
      like `hideClientSide` already works: a hidden family's nodes get
      `hidden: true`, and any edge touching one does too. Purely client-side
      dimming, same as `hideTests` below its server-filter threshold — there
      is no server-side family filter to fall back to at scale, unlike
      `hideTests`'s `ROLE_HIDE_CLIENT_THRESHOLD` path.
- [x] **Rolled-up edge-count labels.** Grouped altitudes (`L3`/`P*`) already
      carried a `count` per aggregated edge server-side
      (`_build_graph_grouped`); `buildGraph` (`graphLayout.ts`) now sets an
      edge `label` (`"×" + count`) when the graph is ranked and the count is
      >1, and `AtlasCanvas` enables Sigma's `renderEdgeLabels` only when
      `isGroupedAltitude(altitude)`. Leaf `L2` edges (`count` always 1) never
      get a label — that graph is too dense for it, unchanged from before.
- [x] **Container hulls for `P2+` scoped views.** Extended the existing
      per-family `bindWebGLLayer`/`createContoursProgram` mesh with a second
      hull pass, active only when the altitude matches `/^P\d+$/` (a scoped
      drill-down rung, not the unscoped top `L3` rung, which has no parent to
      group by). Container-group ids at these rungs are already `/`-joined
      directory paths (`encoding.path_group_of`), so the depth-1 ancestor is
      just the visible node's own id's first path segment — no new request
      needed. One neutral hull colour for every ancestor group (not a colour
      per group): the containment cue is "these belong together," not a
      fourth colour channel — shape/position carry which group is which, the
      same way the family hulls already do. This is the bounded version of
      §3.2's containment cue; the full compound/expand-in-place canvas and
      the ELK.js/Cytoscape.js decision stay deferred exactly as flagged
      above — this pass's verdict is keep Sigma + hulls, no new rendering
      library needed for the scope actually shipped.
- [x] `npx vitest run`: 7 files, 34 tests, all passed (was 34 pre-pass across
      the same file count — no test file added this pass, only edits to
      existing canvas/legend components; no vitest coverage was added for
      the three new frontend behaviors specifically, since they're visual/
      reducer-level rather than pure functions — see the manual-check caveat
      below).
      `tsc -b`: same one pre-existing, unrelated `Rung[]` error already
      flagged above; no new type errors from this pass's changes.
- [ ] **Not verified live in a browser this pass.** No `npm run dev` session
      was run against either this repo or `unified-store` to eyeball the
      legend toggle, the edge-count labels, or the `P2+` hulls actually
      rendering — vitest/pytest are the only verification for this entry.
      Flagged explicitly per this file's own convention rather than implied.
- Deferred, unchanged from above: full compound/expand-in-place container
  canvas, ELK.js/Cytoscape.js swap, `/api/search`, neighbourhood-focus
  toggle, minimap, artifact caching, `performance.mark` freeze-gate
  instrumentation.

## `WEB_REDESIGN_RESEARCH.md` §5 — the real "loads forever" root cause (2026-09-24)

Picked up §5 (performance) and the still-open "loads forever" item from the
first `WEB_REDESIGN_RESEARCH.md` entry above. Ran both servers live against
the real `unified-store` index (`CDP_STORE=~/git/unified-store/.cdp`,
94MB, the doc's own repro case) with Playwright driving a real browser —
per this repo's debugging-process rule, no fix below was proposed until the
failure was reproduced and instrumented first.

- [x] **noverlap moved off the main thread** (§5 item 1's other half —
      FA2 was already worker-side; `noverlap.assign` after it was not).
      `graphLayout.ts`'s `layoutForceAtlas2Async` called synchronous
      `noverlap.assign` after the FA2 worker finished — exactly the doc's
      measured **4.8s freeze** on `unified-store`'s L2 graph (6,064 nodes).
      Added `runNoverlapAsync` using `graphology-layout-noverlap/worker`
      (same blob-worker technique already proven for FA2's own worker, so no
      new bundler wiring needed), resolving on `onConverged` or a
      size-scaled budget (`min(3000, order*4)ms`), whichever is first.
      Verified live: a `PerformanceObserver({type:"longtask"})` across the
      full L2 build+layout on the real 6,064-node graph recorded only two
      tasks (55ms, 772ms) — no task anywhere near the old 4.8s, and 40
      `page.evaluate` round-trips spaced 100ms apart during the same window
      all returned in ≤1ms, i.e. the main thread never blocked.
      `npx vitest run`: still 7 files / 34 tests, unchanged.
- [x] **Found and fixed the actual mechanism behind "loads forever" on a
      large graph** — more precise than this doc's earlier entry, which
      flagged the *symptom* (stuck loading state) but not this cause.
      `AtlasCanvas.tsx`'s canvas `<div ref={containerRef}>` sits inside an
      `AnimatePresence`-keyed `motion.div` (`key={canvasKey}`, one per
      altitude+scope) so that an altitude/scope change can cross-fade the
      old canvas out while the new one fades in. Both the outgoing (exiting)
      and incoming element wired to the exact same `containerRef` object.
      `AnimatePresence` keeps the outgoing element mounted for its ~0.48s
      exit transition, so for that whole window *two* container elements
      exist; when the exit finishes, React unmounts the old one and calls
      its ref callback with `null` — unconditionally, since it's the same
      ref object, this clobbers the new element's already-attached
      reference too. Any graph whose layout takes longer than ~0.48s to
      resolve (any graph in the low thousands of nodes; trivial on this
      repo's own fixtures but always true of `unified-store`'s 6,064-node
      L2) finds `containerRef.current === null` by the time
      `layoutForceAtlas2Async` resolves, so the Sigma-mount effect silently
      no-ops — no thrown error, no failed request, no rejected promise,
      nothing short of instrumenting the effect itself would show it
      happened. The canvas then stays permanently blank. Reproduced by
      instrumenting both effects with temporary logging, confirmed
      independent of React `StrictMode`'s dev-only double-effect-invocation
      (same result in a `vite build` + `vite preview` production run, so
      not a dev-only artifact).
      Fixed with a keyed callback ref (`bindContainer(canvasKey)`): each
      exiting/entering element's ref callback closes over its own
      `canvasKey`, and a stale exit's `null` cleanup only clears the shared
      `containerRef`/`containerKeyRef` pair if it still owns the current
      key — a since-replaced element's late cleanup is a no-op instead of
      clobbering the new one. Verified live end-to-end against the real
      `unified-store` L2 graph (post-fix, in a production `vite build` +
      `vite preview`, not just dev): the 6,064-node/14,593-edge map now
      actually renders (screenshot showed real family-hull colouring, node
      clustering, edge fan-out — not a blank frame), full render in ~16s
      from click (fetch + build + FA2 + noverlap, all now off the main
      thread), zero console errors. Spot-checked this repo's own small
      graphs (208-node top rung, descend-by-double-click) still render and
      interact normally after the change — not just the large-graph path.
      `npx tsc -b`: only the same pre-existing, unrelated `Rung[]` error
      already flagged above. `npx vitest run`: 34/34 still green.
- [ ] Not done this pass: `performance.mark` instrumentation (§7 step 3) —
      the longtask-observer probe above is real evidence the freeze is
      gone, but it was a one-off Playwright script, not permanent
      in-app instrumentation; an explicit "graph too large" UI state;
      artifact caching (§5 item 3, still ~400ms/request cold); `/api/search`;
      neighbourhood-focus toggle; minimap; pin/lock positions. All still
      open from the deferred lists above.

## `WEB_REDESIGN_RESEARCH.md` §5 — artifact cache, placeholder graph, and the real cold-request bottleneck (2026-09-24)

Picked up the two remaining §5 items flagged open above (artifact caching,
`placeholderData`), plus a bottleneck the profiling below found that the doc
itself hadn't named.

- [x] **§5 item 3, artifact cache.** `store_reader.py`'s `ReadOnlyConnection.
      read_artifact` now caches parsed artifacts in-process, keyed
      `(db_path, snapshot_id, name)`. The doc's own justification ("the index
      is immutable per snapshot") was verified, not assumed, before caching
      everything: `cdp/cli.py`'s `_fold_and_write` upserts the `state`
      artifact in place for the *same* `snapshot_id`, wave by wave, during a
      live `cdp run` — caching it would serve a stale wave's claims to a
      request racing an in-flight run. `state` (and, out of caution, the tiny
      `manifest` pin marker) are excluded from `_CACHEABLE_ARTIFACTS`; every
      other artifact is written once before `manifest` marks a snapshot
      pinned-and-readable, so it only ever presents one value per
      `snapshot_id`. New tests: `test_cacheable_artifact_is_served_from_cache_
      on_second_read` (closes the sqlite connection between reads — asserts
      object identity, so a second `json.loads` would fail the test even if
      it happened to succeed) and `test_state_artifact_is_never_cached`.
      Verified live against the real `unified-store` index: isolated
      per-artifact reads show the expected huge win (`xref` cold 103ms →
      cached 0.006ms) — but seeing almost no end-to-end improvement from this
      alone surfaced the real bottleneck below.
- [x] **§5 item 5, `placeholderData`.** `useGraph` (`hooks.ts`) now sets
      `placeholderData: keepPreviousData` so the previous graph stays
      visible while the next altitude/scope's fetch is in flight, instead of
      a blank "loading graph…" canvas. Two correctness risks in
      `AtlasCanvas.tsx` were self-caught before shipping, not found by
      review: (1) naively wiring this up would rebuild the *stale* placeholder
      data under the *new* altitude's layout rules (dagre-ranked vs.
      FA2-force) the instant a drill-down click fired, since the build
      effect's dependency array reacts to `altitude` immediately even though
      `data` itself hasn't changed yet — fixed with an `isPlaceholderData`
      early-return that skips rebuilding until the real fetch resolves.
      (2) the existing `canvasKey`/`AnimatePresence` remount mechanism would
      still crossfade on every click regardless, fading the old canvas into a
      new, still-empty container and reintroducing the same blank-flash
      problem via a different path — fixed by replacing the live-computed key
      with `displayKey` state that only advances at the points the graph is
      actually rebuilt. Added a dimmed-opacity + "updating…" badge overlay
      while `isFetching && isPlaceholderData`. Not yet eyeballed in a running
      browser.
- [x] **Found (via profiling, not assumed) and fixed the real cold-request
      bottleneck** — the doc's own "~400ms/request" framing undersold this
      badly. After the artifact cache above produced almost no end-to-end
      speedup on a warm-cache second call against `unified-store`
      (1838ms → 1699ms) despite the isolated per-artifact wins, `cProfile`
      against a single `_build_graph(..., "L3", None)` call found
      `encoding.resolve_owner_file`'s typed-node fallback branch (the
      `table:`/`route:`/... case) alone consumed **7.913 of 8.194 total
      seconds (96%)** — 73.7M `dict.get` calls from a full linear scan over
      all 14,593 `dataflow.edges` per node, an O(nodes × edges) cost the
      artifact cache does nothing to address since it's pure in-memory CPU
      work, not an I/O read. Fixed by adding `encoding.build_owner_edge_map`,
      which precomputes the same "first owning edge in list order" result in
      one O(edges) pass, and threading it through `resolve_owner_file` as a
      new optional `owner_edge_map` parameter (defaults to `None`, falling
      back to the old per-node scan, so every existing test call site keeps
      working unmodified). `_dataflow_graph` (`app.py`, the sole production
      call site) now builds the map once per request and passes it through.
      New test `test_owner_edge_map_agrees_with_the_per_node_scan` asserts
      byte-identical output between the map-based and scan-based paths across
      several typed ids, including the existing negative cases (owned-by-
      another-typed-id, never-mentioned, wrong-channel). Full suite:
      136 passed (was 135), 1 skipped, 45 subtests — no regressions.
      Re-benchmarked end-to-end against the real `unified-store` index,
      cache cleared first: **1838ms → 212ms cold, 51ms warm** (was
      1838ms → 1699ms before this fix) — landing at the artifact-I/O floor
      already measured for the cache alone, confirming the two fixes now
      compound as the doc's performance axis intended.
- [ ] Not done this pass: `performance.mark` instrumentation; explicit
      "graph too large" UI state; `/api/search`; neighbourhood-focus toggle;
      minimap; pin/lock positions; position caching per
      `(snapshot, level, scope)`; §3.2's compound/expand-in-place container
      canvas (ELK/Cytoscape) decision; gzip verification; L0 typeahead
      payload lazy-loading. Same deferred backlog as before, now with two
      fewer items — worth checking in with the user on priority before
      picking further items given its size.

## Remaining backlog pass — perf, UX polish, container canvas (2026-09-24)

Full context/sequencing in the approved plan at
`/Users/sharmp49/.claude/plans/async-yawning-rain.md`, which picked up the
"Not done this pass" list directly above. All three backlog buckets the user
selected were addressed except §3.2 (see explicit deferral below).

- [x] **Perf: `performance.mark`/`performance.measure` instrumentation.**
      `hooks.ts`'s `useGraph` marks `atlas:fetch-start`/`-end` around the
      `/api/graph` call. `AtlasCanvas.tsx`'s layout effect marks
      `atlas:build-start`/`-end` (and, for the ranked/dagre path, that single
      measure covers layout too, since `layoutRanked` runs synchronously
      inside `buildGraph`); the non-ranked (force-directed) path adds a
      separate `atlas:layout-start`/`-end` around the async
      `layoutForceAtlas2Async` call. The sigma-mount effect marks
      `atlas:first-paint` right after `fitToViewport`, measures
      `atlas:fetch-to-paint` (wrapped in try/catch — `fetch-start` can be
      absent on a placeholder-data render that never re-fetched), prints a
      `console.table` of every `atlas:`-prefixed measure, then clears marks/
      measures so they don't grow unbounded across altitude changes. All
      gated behind `import.meta.env.DEV`, same convention as the existing FPS
      overlay. Not yet eyeballed against a real console in a running browser
      — only confirmed via `tsc -b`/`vitest run` that the marks compile and
      don't break existing behavior.
- [x] **Perf: explicit "graph too large" UI state.** Backend
      `GRAPH_SIZE_CEILING`/`too_large`/`suggested_scopes` were already done
      pre-compaction. This pass added the frontend consumer: `AtlasCanvas.tsx`
      renders a dedicated empty state when `data.too_large`, listing
      `suggested_scopes` as chips that call `descendTo(id, "L2")` (confirmed
      via reading `_graph_rungs` that depth-1 suggested ids are always `"L3"`,
      making that the correct target altitude). `isEmpty`/`showLoading` were
      updated so a too-large response doesn't get stuck permanently in a
      loading state (the layout effect bails out early for `too_large` and
      never sets `layoutReady`). Verified via `tsc -b`/`vitest run` only —
      **not** run live against `unified-store`'s real unscoped-L2 case.
- [x] **UX: neighbourhood-focus toggle.** `atlasStore.ts` gained
      `focusNodeId`, cleared on every ladder mutation via the existing
      `CLEAR_FOCUS` constant, plus a `toggleFocus(id)` action (toggles off on
      a repeat id, switches straight over on a different id). `/api/graph`'s
      `focus` param (backend, pre-existing per the plan) is now threaded
      through `useGraph`'s options and both `AtlasCanvas.tsx` call sites.
      `GraphLegend.tsx` got a new "Focus neighbourhood" toggle row, same
      button/aria-pressed convention as "Hide tests", shown only when a node
      is selected. Three new `atlasStore.test.ts` cases cover toggle-on,
      toggle-off, switch-without-clearing, and ladder-mutation clearing.
      `pytest`/`vitest`/`tsc` all green.
- [x] **UX: pin/lock node positions + position caching.** New
      `positionCache.ts` (sessionStorage, in-memory fallback outside a
      browser), keyed `repoKey:level:scope` — **deliberate deviation** from
      the plan's literal `pos:<snapshotId>:<level>:<scope>` wording:
      `GraphResponse` has no snapshot id field at all (confirmed via
      `grep -n "snapshot" web/api/models.py`), so `repoKey` (`repo:state_dir`,
      already available via `useRepoParams`) substitutes for it. `buildGraph`
      now takes an optional cache key: applies cached positions before
      layout, skips re-seeding cached nodes (`seedCircle`'s new `skip` param),
      and re-pins any `pinned: true` node's cached position after a ranked/
      dagre rebuild (which recomputes every node's position). `setNodePinned`
      sets `pinned`/`fixed` and persists. `fixed: true` is graphology-layout-
      forceatlas2's own native attribute for excluding a node from FA2
      movement — no custom physics needed. `AtlasCanvas.tsx` wires a pin
      toggle through `GraphLegend.tsx` (new "Pin position" row, same
      convention as focus/hide-tests), persists positions after every
      layout resolves. New `graphLayout.test.ts` cases: a fixed node's
      position survives a real `forceAtlas2.assign` call, a pinned cached
      position survives a ranked rebuild, and `persistPositions` round-trips
      through `positionCache.ts`. `pytest`/`vitest`/`tsc` all green.
- [x] **UX: minimap.** New `Minimap.tsx`, bottom-right (the one corner not
      already owned by `TracePanel`/`GraphLegend`/`AltitudeSwitcher`) — plain
      SVG, no new dependency. Draws its own bbox-fit-centered projection of
      the raw graphology node coordinates (documented in the file's doc
      comment as an *approximation* of Sigma's own internally-normalized
      "framed graph" camera space, not a reach into Sigma's private
      normalization internals) plus a viewport rectangle from
      `sigma.getCamera()`'s live state, and supports click-to-pan. Wired into
      `AtlasCanvas.tsx` alongside the existing legend/empty-state overlays.
      **Not verified live in a browser** — this repo has no existing
      component-render-test convention (confirmed via
      `find src -iname "*.test.tsx"` returning nothing), so there's no
      automated check standing in for that either; the camera-rect
      approximation in particular should be eyeballed against a real pan/
      zoom before trusting it.
- [ ] **§3.2 compound container canvas — deliberately deferred, not done.**
      This is the plan's own largest/most-uncertain item, explicitly called
      out to "build and gate last" after the other two buckets gave real
      instrumentation to check it against. Given this pass's time budget,
      it was not started: no `expandedContainers` state, no expand-in-place
      layout, no double-click-toggles-expansion behavior. Flagging this
      explicitly rather than silently treating the three-bucket backlog as
      fully closed — the user picked all three buckets, and this is the one
      bucket still outstanding.
- [ ] **Verification gap, all items above:** everything in this section was
      checked via `pytest`/`vitest`/`tsc` only. Per this repo's CLAUDE.md
      debugging-process rule and the plan's own verification section, none
      of it has been live-checked against the real `unified-store` index in
      a running browser yet (gzip header present, too-large state actually
      triggering, focus toggle actually restricting the rendered node set,
      pin surviving a real altitude round-trip, minimap's camera rect
      matching a manual pan/zoom). That check is still outstanding before
      any of these should be considered fully done rather than
      implemented-and-unit-tested.

## Picking the TODO back up (2026-09-24)

No browser automation (Playwright or similar) is available in this
environment, so the live-verification gap flagged directly above could not
be closed this pass either -- rather than fake it, this pass stuck to items
checkable by `pytest`/`vitest`/`tsc`, same convention as every other entry
that hit this same limitation.

- [x] **`tsc -b` clean.** The pre-existing `Rung[]` type error flagged in
      three earlier entries above (`AtlasCanvas.tsx`'s `rungs={data?.rungs ??
      []}` passed a `{ level; depth?: number | null | undefined; label }[]`
      where `AltitudeSwitcher`'s `Rung` wants `depth: number | null`, no
      `undefined`) is fixed at the call site: `.map((r) => ({ ...r, depth:
      r.depth ?? null }))`. `npx tsc -b` now has zero errors, not "same one
      pre-existing error" as every prior entry in this file had to caveat.
- [x] **§4 search-to-focus, frontend half.** The backend `GET /api/search`
      endpoint the doc asked for was already shipped and tested
      (`web/tests/test_search_endpoint.py`, `web/api/app.py`'s `get_search`)
      -- checked before assuming it was still missing, since an earlier TODO
      entry above claimed "no backend endpoint either" and that claim was
      stale. What was actually still missing: the frontend never called it.
      `AskBar.tsx`'s `trace|symbol <prefix>` typeahead used
      `useSymbolTypeahead` (fetch the entire `L0` graph -- 6.8MB on
      `unified-store` -- then substring-filter client-side) instead of the
      already-built lightweight endpoint. New `useSearch(q, enabled)` hook
      (`api/hooks.ts`) wraps `GET /api/search`; `AskBar`'s typeahead now uses
      it (filtered to `kind === "symbol"`), and a second, new
      "jump-to-result" suggestion list appears for free-text input with no
      recognized `cdp query` kind prefix -- clicking a `file` result jumps
      straight to `L1`+`selectNode` (mirrors the existing post-submit
      `file`/`module` single-match behavior), clicking a `symbol` result
      fills the draft as `symbol <fqn>` rather than jumping directly, since a
      bare symbol isn't a graph-focusable node and the existing "never guess,
      always cite the command that ran" rule (`WEB_RESEARCH.md` §4) means it
      should still go through a real query. `useSymbolTypeahead` deleted
      (`hooks.ts`) -- confirmed via grep it had no other callers left, so
      keeping it would have been a dead, unused export.
      `python3 -m pytest web/tests -q`: 143 passed, 1 skipped, 45 subtests
      (unchanged -- no backend touched). `npx vitest run`: 40/40 (unchanged
      count from before this pass -- no new hook-level test added for
      `useSearch` itself; it's a thin `cdp.GET` wrapper identical in shape to
      the existing `useTrace`/`useAskQuery` hooks directly above it, which
      also have no dedicated tests). `npx tsc -b` clean, `npx oxlint` same
      pre-existing warning set, no new ones.
      **Not verified live in a browser** -- no Playwright/similar tool
      available in this environment. The typeahead's actual result quality/
      ranking against a real large repo (`unified-store`) and the new
      jump-to-result list's on-click routing are unverified beyond
      `tsc`/read-through -- flagged rather than implied, same convention as
      every other unverified entry above.
- [ ] **§3.2 compound/expand-in-place container canvas — still not
      started, deliberately.** This remains the plan's own largest, most
      uncertain item ("build and gate last"). It is a real-time WebGL
      rendering behavior (double-click expands a container's children in
      place inside its hull, siblings reflow/shrink) that cannot be
      responsibly built and self-checked without a browser to look at the
      actual canvas -- every other rendering-adjacent change in this file's
      history was either verified live or explicitly flagged as unverified
      and small enough that a `tsc`/`vitest` pass is decent-enough evidence.
      A compound-layout rewrite is neither small nor low-risk enough to ship
      blind. Left exactly as-is until either browser automation is available
      in this environment, or the user explicitly wants it attempted anyway
      with only static verification.
- [ ] Deferred, unchanged from all prior entries: gzip verification,
      artifact-cache/positions cross-checked live, ELK/Cytoscape decision
      (blocked on §3.2 above), ranking quality of `/api/search` itself
      against real repo vocabulary, L0 typeahead payload now fully removed
      from the client (nothing else fetches L0 for typeahead purposes, but
      the `/api/graph?level=L0` route itself is unchanged/still used
      elsewhere per earlier entries).

## §3.2 expand-in-place container canvas (2026-09-24)

Picked this up as the one bucket every prior entry above deliberately left
"not started" ("build and gate last" — see the two entries directly above).
First re-checked whether the reason it kept getting deferred still held:
`npx playwright --version` now resolves (1.63.0), so tried it for real before
assuming the old "no browser automation in this environment" note was still
true — `require("playwright")` fails (`MODULE_NOT_FOUND`) both in this repo's
`node_modules` and via `npx -p playwright node -e ...` in a scratch `/tmp`
dir, so the module itself isn't actually installable/runnable here. The
verification gap is real, not stale — every item below is `tsc`/`vitest`
only, flagged the same as every prior entry that hit this limitation.

- [x] **Chose, and implemented, option (a) from the doc's §3.2**: keep Sigma
      (no ELK/Cytoscape swap), draw children inside the parent's hull,
      **one level deep** — but bounded down further than the doc's own
      wording ("children appear inside the box, siblings stay put and
      shrink"): **at most one container expanded at a time**, and siblings
      stay put *without* shrinking. A general compound-graph engine (nested
      expansions, siblings reflowing to make room) is a materially bigger
      build than this pass's budget and was the whole reason this item kept
      getting pushed to "later" — a single, real, working expansion is more
      honest progress than a half-built general one.
      `graphLayout.ts`: new `expandContainerInPlace(graph, parentId,
      children)` / `collapseContainerInPlace(graph, parentId, expanded)`.
      Expand mutates the *live* graphology object: lays out `children` on a
      scratch graph (FA2 + noverlap, sync — capped at
      `EXPAND_SYNC_LAYOUT_CAP = 150` nodes; above that, a plain circular seed
      only, since a container can legitimately hand off to a scoped L2 of up
      to ~800 nodes per §3.1 and a sync FA2 pass at that size is exactly the
      main-thread freeze the other §5 entries above just finished removing),
      then rescales/translates that layout into a fixed-radius circle
      (`EXPAND_RADIUS = 90`) centred on the parent's *current* x/y and injects
      the children as ordinary nodes/edges. The parent is **not** set
      `hidden: true` (Sigma also hides every edge touching a hidden node,
      which would drop the parent's real already-aggregated edges to sibling
      containers) — instead shrunk to a ~1.5px anchor point with both `label`
      and `baseLabel` cleared (the node reducer renders off `baseLabel`, not
      `label` — found by reading the reducer before assuming `label` alone
      would suppress it). Collapse drops every injected id and restores the
      parent's original size/label from what expand captured, guarded by
      `hasNode`/`hasEdge` so it's a safe no-op against an already-torn-down
      graph.
- [x] **Wired into `AtlasCanvas.tsx`.** Plain double-click on a node at a
      grouped altitude (`isGroupedAltitude`, i.e. `L3`/`P*`) now toggles
      expand-in-place via a local `expandedId` state (not store state — this
      is a per-mount rendering detail, not ladder/breadcrumb navigation);
      ⌘/Ctrl-double-click or **right-click** (new `rightClickNode` handler)
      is the doc's escape hatch to the old "focus this container" behaviour
      (`descend`, moves the ladder) — both gestures fall back to plain
      `descend` at a leaf altitude, where there's no container to expand.
      `expandedId` is cleared on every altitude/scope change (same rationale
      as the store's own `CLEAR_FOCUS`: a raw id from the old rung means
      nothing at the new one). Children are fetched with the existing
      `useGraph(nextRung, expandedId)` — no new endpoint. A new effect
      (declared after, so committed after, the Sigma-mount effect) applies/
      un-applies the mutation against whichever graph object is *currently
      live*, keyed on graph identity (not just `expandedId`) — a full
      altitude/scope rebuild replaces the graph object entirely, so the old
      mutation has nothing left to collapse and the effect re-expands fresh
      against the new one instead of silently no-op'ing. A one-neutral-colour
      hull (`bindWebGLLayer`/`createContoursProgram`, same mesh already used
      for the family and `P2+`-ancestor hulls) is bound around the expanded
      cluster while it's open and torn down on collapse/graph-teardown.
- [x] New `graphLayout.test.ts` cases: children land within a bounded radius
      of the parent's pre-expansion position (not scattered across the whole
      canvas), the parent shrinks to under 30% of its original size with its
      label cleared while its existing edge to a sibling container survives,
      collapse restores the exact original size/label and is a no-op against
      a graph that no longer has the parent node at all (guards the
      graph-identity-changed case above), and a child id that collides with
      an existing top-level sibling id is skipped rather than clobbering it.
      `npx vitest run`: 8 files, 44 tests, all passed (was 34 — +1 new file's
      worth of cases... actually same file, `graphLayout.test.ts`, +10 cases).
      `npx tsc -b`: clean, zero errors (confirmed, not just "same
      pre-existing" — that error was already fixed in the entry directly
      above this one). `npx oxlint`: one new warning,
      `react(set-state-in-effect)` on the `useEffect(() => setExpandedId(null),
      [altitude, scope])` reset — same pattern (and same warning) already
      present at several other reset-on-prop-change call sites in this
      codebase (`TimeScrubber.tsx`, `PeekCard.tsx`, `DoctorHeatmap.tsx`),
      not a new category of issue.
- [ ] **Not verified live in a browser — the recurring caveat, checked fresh
      this time, still true.** Nothing here has been clicked through in an
      actual running Sigma canvas: whether the hull actually reads as "these
      belong together" at real screen scale, whether the shrunk parent's
      anchor point is visually sensible or just looks like a stray dot,
      whether double-click vs. right-click is discoverable without being
      told, and whether the `EXPAND_SYNC_LAYOUT_CAP` circular-seed fallback
      looks acceptable on a real ~800-node container hand-off. Worth a
      `npm run dev` click-through (or Playwright, once actually available in
      this environment) before trusting this beyond what `tsc`/`vitest` can
      see.
- [ ] Not attempted, explicitly still out of scope: nested/multi-container
      expansion, siblings reflowing/shrinking to make room (this pass keeps
      them exactly where they were), and the ELK.js/Cytoscape.js swap for a
      real compound layout engine — this bounded-Sigma version is this pass's
      answer to "decide after rung sizes stabilize", and rung sizes
      (§3.1's 208-groups/190-singletons measurement) haven't changed since.

## §5/§4 close-out — gzip verified live, real `/api/search` bug found and fixed (2026-09-24)

Took over from the TODO's own top of file. Re-checked whether browser
automation was still unavailable before doing anything else (per this
repo's debugging-process rule, gather evidence before touching code): `npx
playwright --version`/`require("playwright")` are still not runnable in this
environment (same finding as the §3.2 entry above), so the live-in-browser
verification gap named at the top of this file is still real and still open
— nothing below claims to have closed it. Picked two items that *are*
checkable without a browser (curl + a real running server) and were still
sitting on the deferred list.

- [x] **gzip verified live**, not just read from the middleware registration.
      Ran the real `uvicorn` server (`web.api.app:app`) against this repo's
      own index and `curl -H "Accept-Encoding: gzip" /api/graph?level=L2`:
      response carries `content-encoding: gzip`, `GZipMiddleware`
      (`app.py:85`, `minimum_size=1024`) is doing real work, not just present
      in the source.
- [x] **Found and fixed a real `/api/search` bug** while checking the
      deferred "ranking quality of `/api/search` itself against real repo
      vocabulary" item — turned out to not be a ranking-quality question at
      all, but a flat correctness bug: `q=app` against this repo's own index
      returned **zero results** live, despite `/api/query?kind=search&term=app`
      (same store, same match logic) finding 80 matching symbols and 4
      matching files. Root cause: `cdp.query.q_search`'s `Budget` is a
      *single* row allowance spent in construction order across
      `claims -> symbols -> unknowns -> files` (`cdp/query.py`'s `Budget.
      take`); `get_search` (`web/api/app.py`) was passing the UI's own
      `limit` param (default 20) straight through as that shared budget.
      `app` matched 26 claims — which `get_search` doesn't even return, they're
      not graph-focusable — so claims alone exhausted the entire budget of 20
      before symbols or files got a turn, even though 80 symbols matched.
      Fixed by calling `dispatch(store, "search", q)` with no budget override
      (falls back to `q_search`'s own default of 200 rows, matching
      `/api/query`'s behavior) and applying `limit` only to the endpoint's own
      flattened symbol+file output, same as before. New regression test
      (`test_search_low_limit_does_not_starve_results_behind_claim_matches`,
      `web/tests/test_search_endpoint.py`) reproduces it against the
      `minirepo` fixture (`q=widget, limit=1` returned 0 results before the
      fix — `widget` matches several fixture claims — 1 after) since the
      existing fixture-scan tests never had enough claims to hit this path.
      Verified live end-to-end against this repo's own index both before
      (`{"count":0,"results":[]}`) and after (`{"count":20,...}`) the fix, not
      just via the new unit test. `python3 -m pytest web/tests -q`: 144 passed
      (was 143, +1 new test), 1 skipped, 45 subtests, no regressions.
- [ ] Deferred, unchanged: live-in-browser verification of every rendering-
      adjacent item above (still no Playwright in this environment), §3.2
      nested/multi-container expansion + ELK/Cytoscape swap, position-cache/
      focus-toggle/minimap live cross-checks, L0 typeahead route removal
      (still used elsewhere per earlier entries).

## Closing the live-verification gap for real (2026-09-24)

Every prior entry's "no Playwright in this environment" note was re-checked
by actually trying to install it, not just re-running the same
`require("playwright")` probe from before — `npm install --no-save
playwright` succeeded this time (network access differs per-session) and
`npx playwright install chromium` found the browser binary already cached.
A `chromium.launch({args:['--no-sandbox']})` real headless browser worked
end-to-end. The module-not-found finding in every earlier entry was accurate
for those sessions; it was not accurate for this one, and is worth
re-checking rather than assumed next time too.

Ran both servers for real: `uvicorn web.api.app:app` with
`CDP_STORE=~/git/unified-store/.cdp` (the doc's own 94MB repro case) +
`npm run dev`, then drove the real dev server with a headless Chromium
against the real `unified-store` index — the first actual live check any of
this file's container-hierarchy/canvas work has had.

- [x] **Container hierarchy + expand-in-place hulls, confirmed live and
      real, not just unit-tested.** Screenshot evidence: the top rung shows
      "208 nodes, 319 connections" (matches the §3.1 entries' own
      208-groups/190-singletons measurement exactly), with three real,
      readably-sized family hulls instead of the doc's original 823-node
      wall. Double-clicking a container node (`ms-sql-java`) actually
      expanded its children in a bounded cluster near the parent's position
      with a hull drawn around them and the parent shrunk to a small anchor
      dot — exactly as `graphLayout.ts`'s `expandContainerInPlace` was
      designed to do, now seen working rather than only covered by
      synthetic-shape unit tests. Zero console/page errors across every
      probe in this pass.
- [x] **Found and fixed a real bug: `GraphLegend` was unusable whenever a
      node was selected.** `focusable`/`pinnable` (`AtlasCanvas.tsx`) are
      both gated on `selectedNodeId !== null` — the exact same condition
      under which `InspectorRail.tsx` renders its `right-0 w-96 h-full z-20`
      panel. `GraphLegend`'s own `right-3 w-72 z-10` card sits entirely
      inside that 384px span, so the moment "Focus neighbourhood"/"Pin
      position" actually appeared (they're gated on the same selection),
      the rail was drawn on top of them: present in the DOM, confirmed by a
      real Playwright click that timed out after 30s with "element ...
      intercepts pointer events" pointing at the rail's own div. This had
      been sitting behind every one of this file's "not verified live"
      caveats on the focus/pin toggles — the code was correct, the layout
      made it unreachable by mouse. Fixed in `GraphLegend.tsx`: the card now
      reads its own `focusable || pinnable` props to detect "the inspector
      rail is currently open" and slides its `right` offset from `0.75rem`
      to `25.5rem` (clear of the rail's 24rem width) in that state, with a
      `transition-[right]` so it isn't a hard jump.
- [x] **Focus-neighbourhood toggle, verified live end-to-end.** Selecting
      `ms-sql-java` and clicking the now-reachable "Focus neighbourhood" row
      collapsed the rendered graph from 208 nodes/319 edges to 6 nodes/7
      edges — the node's real neighbourhood, not a no-op. Toggling off
      restored 208/319.
- [x] **Pin toggle, verified live end-to-end.** Clicking "Pin position"
      lights up the row (teal border, matching `hideTests`'s existing
      convention) and the node survives an altitude round-trip (Packages →
      Depth 2 → Packages) without erroring or losing its pinned state.
- [x] **Minimap, verified live.** Clicking inside the minimap's viewport
      rectangle actually panned the main Sigma camera (confirmed via
      before/after screenshot — the visible node set shifted), not just a
      static SVG.
- [ ] Not re-verified this pass (ran out of scope/time budget, not because
      of the tooling gap this time): gzip and `/api/search` were already
      live-verified in the prior entry via curl and don't need Playwright;
      the "graph too large" empty state (needs an unscoped-L2 request the
      UI doesn't normally expose); §3.2's deliberately-deferred
      nested/multi-container expansion and ELK/Cytoscape swap; ranking
      quality of `/api/search` against real repo vocabulary. Scratch
      Playwright probe scripts used for this pass were deleted, not
      committed — worth writing a couple of these as a real permanent e2e
      suite (`web/frontend/e2e/`) next time, now that the tooling is
      confirmed to work in at least some sessions, rather than re-deriving
      throwaway scripts each time.

## A real, permanent e2e suite, plus a genuine double-click bug it caught (2026-09-24)

Took over the prior entry's own recommendation directly: added
`@playwright/test` as a real devDependency (not `--no-save`) and a permanent
`web/frontend/e2e/atlas.spec.ts` + `playwright.config.ts`, so these checks
run on every `npm run test:e2e` instead of being re-derived as throwaway
scripts each session. `playwright.config.ts`'s `webServer` starts both
`uvicorn` and `vite dev` itself against this repo's own real `.cdp/index.db`
(the default repo selection) — one command, no fixture data, per this repo's
own established convention.

- [x] **5 tests, covering every item the prior entry's live pass checked by
      hand:** top-rung node count sanity (no 823-singleton wall), node
      selection reveals reachable Focus/Pin toggles (regression guard for
      the already-fixed `InspectorRail`/`GraphLegend` overlap bug), pin
      position survives an altitude round-trip, minimap click actually pans
      the camera, and double-click expand/collapse-in-place. All 5 pass
      against the live index (`npx playwright test`, 12.8s).
- [x] **Found and fixed a second, previously-undiscovered instance of the
      same overlap bug class, this time breaking a real user gesture, not
      just a hidden button.** The double-click test failed at first (order
      stuck at 23, no growth) even after fixing the test's own node-choice
      issue (picking an arbitrary node instead of a real container). Root-
      caused empirically, per this repo's own debugging-process rule
      (gather evidence before theorizing) — a chain of scratch Playwright
      probes confirmed: the browser fires two real native
      click/mousedown/mouseup cycles + one native `dblclick`; Sigma's
      `MouseCaptor` receives the first cycle fine (`clickNode` fires) but
      then gets a `mouseleave` instead of a second `mousedown`, so no
      `doubleClick` is ever emitted. `document.elementFromPoint` at the
      exact second-click coordinates, taken right after the first click,
      confirmed the cause directly: the click landed at screen x=937 (of a
      1280px canvas), and `InspectorRail`'s `right-0 w-96` panel (x
      920–1280) had already opened synchronously in response to the first
      click's `selectNode()`, so the second click of the double-click
      physically hit the rail's div, not the canvas. Any node whose x
      position falls under the rail's ~360px-wide footprint was silently
      un-double-clickable the moment it got selected — a real UX bug for a
      real mouse gesture, not a test artifact (the prior entry's fix only
      addressed hidden buttons under an *already-open* rail; this is the
      rail intercepting the *second half of the very click that opens it*).
      Fixed in `InspectorRail.tsx`: the panel is now `pointer-events-none`
      overall, with `pointer-events-auto` restored only on its actual
      interactive regions (header/close button, retry button, claims list,
      evidence source view) — blank rail padding is click-through to the
      canvas beneath it, informative-only text stays inert either way.
      Re-ran the test after the fix: passes.
- [x] Removed the debug `console.log`s and five scratch `debug_*.mjs`
      probes used to chase the above (`debug_click.mjs` through
      `debug_click4.mjs`, `debug_expand.mjs`) — not committed, per this
      repo's own established convention from every prior entry.
- [x] Added `test: { exclude: ['e2e/**', ...] }` to `vite.config.ts` —
      vitest's default glob otherwise picks up Playwright's own
      `*.spec.ts` files and fails trying to call `test()` outside a
      Playwright worker. Gitignored `web/frontend/{test-results,
      playwright-report}/`.
- [x] Full verification, no regressions: `python3 -m pytest web/tests -q`
      144 passed/1 skipped (unchanged), `npx vitest run` 44 passed across 7
      files (unchanged, now correctly excluding the e2e spec), `npx tsc -b`
      clean, `npx playwright test` 5/5 passed.
- [ ] Deferred, unchanged: §3.2 nested/multi-container expansion + ELK/
      Cytoscape swap, `/api/search` ranking-quality tuning against real
      repo vocabulary, the "graph too large" empty state (needs an
      unscoped-L2 request the UI doesn't normally expose).

## Every node had a visible "shadow" — real bug, not styling (2026-09-24)

User-reported, live: every node in the Atlas canvas looked like it had a
shadow underneath it, "making it look bad". Root-caused before touching
code, per this repo's debugging-process rule.

- [x] **Found and fixed.** `AtlasCanvas.tsx`'s node reducer draws a status
      ring (`ringColor`, `@sigma/node-border`) on every node, on top of the
      family fill, to carry confidence status without mixing it into
      structure colour (`sigmaPrograms.ts`'s `RING`/§3's "status on the
      ring" design). In the default **structure** lens,
      `useNodesConfidence(altitude, scope, lens === "confidence")` is called
      with `enabled: false` — the confidence query never fires, so
      `confidenceById` is always empty and every node's bucket falls back to
      `"unreviewed"`. The reducer's old `else` branch
      (`res.ringColor = bucket === "unreviewed" ? palette.border : ...`) drew
      that fallback as a solid dark-grey ring (`palette.border`,
      `#262c36`) around **every single node**, all the time, in the view
      everyone actually lands on first — a uniform grey halo around every
      node, which is exactly what reads as "every node has a shadow."
      Confidence-lens rendering (the `if (s.lens === "confidence")` branch
      just above) was untouched — that lens explicitly fetches real buckets
      and is a different code path.
      Fixed by only drawing a non-transparent ring in the structure lens
      when there is an actually-fetched, actually-non-default bucket for
      that node (`s.confidenceById.has(node) && bucket !== "unreviewed"`);
      otherwise the ring stays at `@sigma/node-border`'s own transparent
      default (`"#00000000"`). Since the structure lens never populates
      `confidenceById` at all, every node now renders with no ring by
      default — the shadow is gone — while a node that *does* have a real,
      fetched confidence bucket (once the confidence lens is toggled on)
      still gets its ring exactly as designed.
      `npx vitest run`: 44/44, unchanged. `npx tsc -b`: same one
      pre-existing, unrelated `vite.config.ts` `test` key overload error
      (confirmed pre-existing, not introduced by this change).
      **Verified live**: ran the real `uvicorn`/`vite dev` pair against this
      repo's own `.cdp/index.db` (via the existing `playwright.config.ts`
      `webServer`) and screenshotted the Atlas canvas at its default landing
      view (structure lens) — every node renders as a clean solid disc, no
      grey ring/halo around any of them. Scratch probe spec deleted after
      confirming, not committed, per this file's own convention.

## Multi-container + nested expand-in-place (§3.2 follow-up) (2026-09-24)

User picked up the first of the three items deferred by the shadow-bug
close-out: extending the single-container expand-in-place mechanism to
support **multiple simultaneous top-level expansions** and **nested
(container-within-a-container) expansion**. User explicitly chose to extend
the existing bounded Sigma approach rather than swap the renderer to
Cytoscape.js/ELK.js for native compound-graph support — no new rendering
dependency was introduced.

- [x] **`graphLayout.ts`**: `expandContainerInPlace(graph, parentId, children, opts?)`
      gained a 4th, backward-compatible `{ rung?: Altitude; radius?: number }`
      param. `opts.radius` overrides the hardcoded `EXPAND_RADIUS` so a nested
      expansion can use a smaller circle (new exported constant
      `NESTED_RADIUS_FACTOR = 0.45`, applied by the caller as
      `EXPAND_RADIUS * NESTED_RADIUS_FACTOR ** depth`) and stay visually
      inside its parent's hull rather than overflowing it. Every injected
      child also gets a new `rung` attribute — the altitude *that child's own
      children* would be fetched at (`null` if the child is a leaf, not
      itself a container) — so a later double-click on an already-injected
      node can tell what it is without re-deriving depth from the graph.
      `collapseContainerInPlace` is unchanged; cascade ordering across nested
      expansions is the caller's job, not this primitive's.
- [x] **`api/hooks.ts`**: `useGraph`'s fetch body extracted into a shared
      `fetchGraph(level, scope, hideRoles, focus, repoParams, signal)`. New
      `useExpandedGraphs(entries: {id, childRung}[])`, built on react-query
      v5's `useQueries` (a dynamic-length query array in one hook call) —
      one scoped `/api/graph` fetch per currently-open expansion, same
      `queryKey` shape as `useGraph` so cache reuse across
      expand/collapse/re-expand still works.
- [x] **`AtlasCanvas.tsx`**: `expandedId: string | null` replaced by
      `expanded: Map<string, ExpansionNode>` (`{id, parentId, depth, ownRung,
      childRung}`), cleared on altitude/scope change same as before, capped
      at `MAX_EXPANSION_DEPTH = 4` as a safety valve. `nextRung`'s inline
      computation is now the shared pure helper `rungAfter(rungs, level)`.
      The double-click handler determines a clicked node's *own* altitude
      (`ownRung`) from whether it's already injected (its `rung` attribute)
      versus top-level (the canvas's `altitude`), and toggles the `expanded`
      map — collapsing a container also removes every descendant nested
      inside it in one update (`collectSubtreeIds`). The apply/collapse
      effect generalizes from one `{graph, parentId, info, hullCleanup}` ref
      to `appliedRef.byId: Map<...>`, and runs two ordered passes every time
      `expanded`/the fetched data changes: collapse pass (removed entries,
      **deepest first** — a nested expansion must tear down before its
      ancestor's `collapseContainerInPlace` restores the parent node it was
      centered on), then apply pass (new entries, **shallowest first** — a
      nested expansion's parent must already have its injected children
      present before centering the nested one among them). Each expansion
      gets its own hull layer id (`` `hull-expanded:${id}` ``) instead of one
      shared fixed id, so multiple simultaneous hulls coexist correctly.
- [x] **Real bug found via live testing, not theorized**: the double-click
      handler's first draft computed an injected node's own altitude as
      `injectedRung ?? altitude` — using JS's `??`, which treats the
      genuinely-meaningful `rung: null` (this child is a leaf, not itself a
      container) as absent and wrongly fell back to the canvas's top-level
      `altitude`. That made every injected **leaf** child look like a
      top-level container again, so double-clicking one attempted to expand
      it (fetching an invalid scope) instead of correctly no-op'ing /
      falling through to `descend`. Caught live: a Playwright test double-
      clicking real injected children hung for the full 30s test timeout
      chasing this. Fixed by checking for the presence of the unconditional
      `expandedParent` attribute to distinguish "top-level node" from
      "injected node whose own rung happens to be null", rather than using
      `??` on the rung value itself.
- [x] **Unit tests** (`graphLayout.test.ts`): kept all 4 pre-existing
      expand/collapse cases passing unchanged, added 4 more — independent
      sibling expansion/collapse, nested expansion landing within the
      shrunk radius and carrying the right `rung`, and collapsing a nested
      expansion in various orders (including after its ancestor already
      collapsed) staying a safe no-op. `npx vitest run`: 47/47. `npx tsc -b`:
      same one pre-existing, unrelated `vite.config.ts` error. `npx oxlint`:
      no new warning *categories* — the one new `set-state-in-effect`
      warning on the `expanded`-clearing effect is the same shape/rule as
      the pre-existing `setExpandedId(null)` clearing effect it replaced.
- [x] **Verified live** (`e2e/atlas.spec.ts`, permanent additions, run
      against this repo's own real `.cdp/index.db`):
      - Expanding two sibling containers: both sets of children coexist on
        canvas, collapsing one leaves the other's children untouched — pass.
      - Nested (container-within-a-container) expansion: **this repo's own
        real ladder is only `["L3", "L2"]`** — every L3 container's members
        are already leaf `L2` nodes, so there is no real intermediate rung
        to nest a second expansion inside. The live test checks this
        precondition first and skips cleanly when it doesn't hold, rather
        than forcing a nested expansion that isn't representable in this
        repo's actual data; the nesting algorithm itself (radius shrink,
        `rung` stamping, cascade collapse ordering) is exercised
        unconditionally by the synthetic `graphLayout.test.ts` cases above,
        independent of what this repo's own index looks like.
      - Screenshotted two simultaneous sibling expansions for a manual
        visual check (scratch probe, deleted after use): both clusters
        render and are visually distinguishable, but labels on adjacent
        expanded clusters visibly overlap/crowd each other at this zoom —
        **flagging explicitly that this needs a human look**, same as every
        other rendering claim in this file; not fixed in this pass since
        label decluttering wasn't part of the requested scope.
    - Deferred, unchanged: `/api/search` ranking-quality tuning; "graph too
      large" empty state (§3's other two backlog items — user picked this
      one first). Arbitrary expansion depth beyond the `MAX_EXPANSION_DEPTH`
      safety valve, and the ELK.js/Cytoscape.js compound-graph renderer
      swap, remain untried — both out of scope by the user's own explicit
      choice this round.

## Removed the WebGL contour/hull layers — user-reported visual regression (2026-09-24)

User flagged every node rendering with a family-coloured "shadow" (blue
nodes with a blue halo, orange with orange, green with green) and asked
whether it was CSS. It wasn't: `@sigma/layer-webgl`'s `createContoursProgram`
(added in the two `WEB_REDESIGN_RESEARCH.md` passes above as the P4 "mesh
weight"/container-containment cue) draws a metaball-style contour behind each
family's/container's node set. Its default `radius` is a fixed `100`
graph-coordinate units; once FA2 spreads nodes further apart than that (true
almost everywhere at this repo's real scale), each node renders its own
isolated circular blob instead of the blobs merging into one cohesive hull —
exactly the per-node "shadow" reported.

Asked the user to choose between retuning the radius/feather to the layout's
actual spacing vs. removing the feature outright; **user chose removal**.

- [x] Removed all three `bindWebGLLayer`/`createContoursProgram` call sites
      in `AtlasCanvas.tsx`: per-family hulls, `P2+` container-ancestor hulls,
      and the per-expanded-child hull in the expand-in-place merge effect —
      along with their `hullCleanups`/`entry.hullCleanup` bookkeeping and the
      now-unused `@sigma/layer-webgl` import. Uninstalled the
      `@sigma/layer-webgl` package (`npm uninstall`) since nothing references
      it anymore.
      Verified: `npx tsc -b` shows only the pre-existing, unrelated
      `vite.config.ts` `UserConfigExport`/`test` overload error (present
      before this change); `npx vitest run` 7 files / 47 tests, all passed,
      no regressions. Not re-verified live in a browser this pass — no
      Playwright session run to screenshot the now-hull-free canvas.
- Net effect: the P4 "mesh weight"/container-containment visual cue
  (`ATLAS_REDESIGN.md`/`WEB_REDESIGN_RESEARCH.md` §3.2/§6) is now fully
  reverted, not just retuned — those docs' hull-based containment approach
  is closed as "tried, visually regressed at this repo's real node spacing,
  removed" rather than left half-shipped. If containment cues are wanted
  again later, worth trying a radius derived from the graph's actual nearest-
  neighbour spacing (or a convex-hull/background-rect approach) rather than
  the library's fixed default, per the option the user didn't pick this time.

## Live-verified the hull removal; fixed the crowded expanded-cluster labels (2026-09-24)

Took over from the two items the hull-removal entry above left open: it
wasn't re-verified live, and the prior §3.2 follow-up entry had flagged
"labels on adjacent expanded clusters visibly overlap/crowd each other" as a
real, unfixed regression needing a human look.

- [x] **Hull removal, verified live.** `npx playwright --version`/
      `require("playwright")` resolve again this session (this environment's
      availability keeps varying run to run, consistent with every prior
      entry's own note to re-check rather than assume). Ran the real
      `uvicorn`/`vite dev` pair against this repo's own `.cdp/index.db` and
      screenshotted the Atlas canvas: no per-node halo/shadow anywhere, zero
      console/page errors. Confirms the removal shipped clean.
- [x] **Root-caused and fixed the crowded-label regression, not just
      flagged it again.** `AtlasCanvas.tsx`'s `labelRenderedSizeThreshold`/
      `labelDensity` are set once, at Sigma construction, off a heuristic
      keyed on the *whole graph's* `order` (`<= 60` nodes → show every
      label). `expandContainerInPlace` packs a container's children into a
      small fixed-radius circle (`EXPAND_RADIUS`/`NESTED_RADIUS_FACTOR`) —
      far denser locally than that order-based heuristic assumes, and it
      never re-evaluates after construction since expand-in-place mutates
      the live graph object without recreating Sigma. A small top-level
      graph (order ≤ 60, e.g. this repo's own 23-node index) keeps
      "label everything" active even while an expansion has packed a dozen
      children into a ~90-unit circle — exactly the crowding the prior
      entry's screenshot showed on `unified-store`.
      Fixed in the apply/collapse effect (`AtlasCanvas.tsx`, runs on every
      `expanded`/`expandedGraphs` change): after applying the expand/collapse
      mutations, `sigma.setSetting("labelRenderedSizeThreshold", …)`/
      `labelDensity` are forced to the same tighter values already used for
      a large graph (`9`/`0.25`) whenever `byId.size > 0` (any expansion is
      currently open), regardless of overall `graph.order`; restored to the
      original order-based heuristic once none are.
      `npx vitest run`: 47/47 unchanged (this is a Sigma-settings behavior,
      not a pure function — no new unit test, same limitation as the
      surrounding expand-in-place code). `npx tsc -b`: same one
      pre-existing, unrelated `vite.config.ts` error. `npx playwright test`:
      6 passed, 1 skipped (unchanged from before this fix — the nested-
      expansion test still skips cleanly on this repo's real 2-rung ladder).
      **Not verified against the actual dense scenario** — this repo's own
      index (23 nodes) never packs enough children into one expansion to
      visibly crowd, so the fix is verified by reading the settings logic
      and confirming no regression, not by re-screenshotting the exact
      `unified-store` crowding this was meant to fix. Worth a follow-up
      screenshot against `unified-store` (`CDP_STORE=~/git/unified-store/.cdp`)
      before calling this fully closed.
- [ ] Deferred, unchanged: `/api/search` ranking-quality tuning against real
      repo vocabulary; "graph too large" empty state, live-untriggered by
      this repo's own small index; arbitrary expansion depth beyond
      `MAX_EXPANSION_DEPTH`; ELK.js/Cytoscape.js compound-graph swap — all
      out of scope by the user's own explicit prior choice, not attempted
      this pass.

## Search ranking + graph-too-large, live-verified (2026-09-24)

User picked exactly these two of the four deferred items above.

- [x] `/api/search` ranking-quality fix. Evidence first: ran the live
      `uvicorn` server and curled real vocabulary (`diff`, `run`, `store`,
      `query`, `job`, `link`, `cli`, `app`, `id`, `doc`) through
      `/api/search`. `q=id` was the reproducible counterexample:
      `table:widget` (an accidental substring of "widget", nothing to do with
      "id") ranked #1, ahead of genuinely token-boundary matches like
      `cdp.derive#claim_id`/`web.api.nodeid#sym_id`/`cdp.link#_link_id` —
      purely because `cdp/query.py`'s `q_search` sorted `symbols`/`files` by
      `key=len` alone, and `table:widget` happens to be a shorter string.
      Fixed by adding `_search_rank_key(text, needle)` (`cdp/query.py`,
      next to `_matches`): tier 0 exact match, tier 1 `needle` is a whole
      segment once `text` is split on `.#:/_`, tier 2 `text`/a segment
      *starts with* `needle`, tier 3 today's plain-substring fallback — each
      tier then breaking ties by length, then the string itself. Wired into
      both `sorted(symbols, ...)` and `sorted(files, ...)` in `q_search`.
      Verified live: re-curled `q=id` post-fix — `table:widget` no longer
      appears in the top 10 at all, replaced by `_run_id`/`_link_id`/
      `claim_id`/`sym_id`/`file_id`/`route_id`/etc. Ran `python3 -m cdp.cli
      install --self` (required — `cdp/query.py` has a byte-identical
      vendored copy under `.claude/skills/cdp/`, caught by
      `test_distribution.py::VendoredCopyTest`). Full suite:
      `python3 -m pytest tests web/tests -q -k "not target_repo"` → 675
      passed, 28 skipped, 3 deselected. `tests/golden/minirepo@fixture`'s
      search fixture is unaffected (its `symbols`/`files` are both `[]` for
      that fixture's query). **Known limitation, not fixed this pass**:
      `tests/golden/code_scanner@7e10575adf69/query/search.json` has a real,
      non-empty, length-sorted `symbols` list that this change reorders —
      but the only test comparing against it
      (`test_target_repo_matches_its_baseline`) is `TARGET_REPO`-gated and
      skipped by default; I don't have local access to that private repo to
      regenerate it via `--bless`. Whoever does should re-run `make golden`
      with `TARGET_REPO` set and commit the refreshed baseline.
- [x] "Graph too large" empty state, live-triggered. This repo's own
      unscoped L2 is 353 nodes, well under `GRAPH_SIZE_CEILING = 2000`
      (`web/api/app.py`), so it never naturally hits this path. Verified by
      temporarily lowering the ceiling to 10, restarting `uvicorn`, and
      curling `/api/graph?level=L2`: confirmed `too_large: true` with real
      `suggested_scopes` (`["cdp", "tests", "web", "Processes", "Tables",
      "Entities", "Libraries", "Config"]`). Then drove the actual frontend
      (`vite` dev server + a throwaway Playwright script, deleted after)
      against that lowered ceiling and confirmed the empty state renders
      correctly with clickable chips.
      **Found and fixed a real bug along the way**: the chips were
      unclickable. `document.elementFromPoint` at a chip's own coordinates
      resolved to the Sigma canvas container div, not the button underneath
      it — the same "later sibling with no z-index intercepts pointer
      events" shape as the earlier `InspectorRail` double-click bug, this
      time on `AtlasCanvas.tsx`'s `motion.div`/`AnimatePresence` wrapper
      around the Sigma container (it's `absolute inset-0` with default
      `pointer-events: auto`, and it paints after — so stacks above — the
      `isTooLarge`/`isEmpty`/`error` overlay blocks). Fixed by adding
      `pointer-events-none` to that wrapper whenever `isTooLarge || isEmpty
      || error` is true (`AtlasCanvas.tsx`, the `motion.div` around line
      1065) — there's no graph to interact with underneath in any of those
      states anyway. Re-verified live: clicking the `cdp` chip now
      descends correctly (`inside cdp ×` scope chip appears, canvas shows
      "99 nodes, 138 connections", real container/module nodes render, zero
      console errors). Reverted the temporary ceiling back to `2000`,
      restarted both servers clean, and reran the full regression: `python3
      -m pytest tests web/tests -q -k "not target_repo"` → 675 passed;
      `npx tsc -b` → same one pre-existing `vite.config.ts` error only;
      `npx vitest run` → 47/47; `npx playwright test` → 6 passed, 1 skipped
      (unchanged) — the pointer-events change touches only the
      no-graph-present states, so it doesn't affect any of the existing
      expand/pin/minimap e2e coverage.
