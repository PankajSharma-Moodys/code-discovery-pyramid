# Frontend TODO — gaps vs `WEB_RESEARCH.md` / `PLAN.md`

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
