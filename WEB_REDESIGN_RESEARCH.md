# Web layer — why the Atlas fails on `unified-store`, and a redesign

Budget: ≤230 lines. Research + design only; no implementation code. Every number below was
measured on 2026-09-23 against the real `unified-store` index (`~/.cdp` registry entry,
94 MB `index.db`) through this repo's own `web/api/app.py` builders and the frontend's own
layout libraries — not estimated. Screenshot evidence: `~/Desktop/portal.png`.

## 0. Verdict

Three defects, all confirmed empirically, none of them "tuning":

1. **The hierarchy is built from the wrong key.** `encoding.package_of` groups nodes by the
   first *dotted segment of the symbol id* (`AccessController`, `com`, `rms`), never by the
   *file path*. `unified-store` is C#/Java where ids are bare class names, so "Packages"
   (the landing view) has **823 nodes**, and `sql-pool` / `service-api` can never appear.
   The 6–7 modules the user expects *are* in the store — they are the top-level directories
   of `inventory.files` — the graph just never looks there.
2. **Dagre is the wrong layout for a hub-dominated graph, and the fit-to-viewport makes it
   fatal.** On the real L3 graph dagre yields **4 ranks, 763 nodes in rank 0** → bounding box
   **144,913 × 510**. Sigma fits the long axis, so the map is a 1-px-tall line — precisely the
   screenshot. The "single-node-rank jitter" fix targets the *opposite* shape (one node per
   rank) and cannot help here.
3. **Nothing bounds work by size.** L2 for this repo is **6,064 nodes / 14,593 edges / 4.4 MB
   JSON**; after the FA2 worker, `noverlap` (250 iters) runs **4.8 s on the main thread**; the
   FA2 budget of 1.2 s allows only **~80 iterations** (nowhere near converged); the Ask-bar
   fetches L0 (**20,057 nodes, 6.8 MB**) on every mount. The deeper rungs (P2–P5) are
   *larger* than L3 (848 → 1,295 nodes) — the ladder never reaches a readable size.

## 1. Evidence (unified-store, real index)

| Altitude | Nodes | Edges | Server build | JSON | Client layout |
|---|---|---|---|---|---|
| L3 "Packages" (default) | 823 | 1,085 | 395 ms | 0.6 MB | dagre 203 ms → 763-node rank 0, aspect 284:1 |
| P2 / P3 / P4 / P5 | 848 / 863 / 1,037 / 1,295 | 1,110 – 3,746 | ~380 ms each | — | dagre; same hub shape |
| L2 "Modules" | 6,064 | 14,593 | 359 ms | 4.4 MB | FA2 ≈80 iters in budget + noverlap 4,792 ms **sync** |
| L1 (files, API only) | 4,661 | 3,977 | 440 ms | 2.3 MB | — |
| L0 (symbols, ask-bar typeahead) | 20,057 | 4,000 | 427 ms | 6.8 MB | fetched on mount |

Top-level L3 groups by degree: `Tables` (753 members, deg 3,342), `RMS` (932), `Migrations`
(229), `Config` (917), `Libraries`, `Routes` (512), `com` (1,197 members — the Java tree),
then **hundreds of single-class "packages"** (`ServiceFactory`, `CardController`, …). Double-
clicking `RMS` → P2 scoped view is **766 nodes**: drill-down does not shrink the graph.

What the store *does* know: `inventory.files` = 4,661 paths whose top directories are
`service-api` 1,241 · `exposure-snapshot` 888 · `catalog-service` 780 · `managed-sql` 637 ·
`sql-pool` 490 · `client-java` 422 · `core` 113 · `ms-sql-java` 30 — exactly the user's
mental model. **4,553 of 6,064 L2 nodes (75%) resolve to a file** via
`xref.symbols[id].sites[0].file`; the remainder are `route:`/`table:`/`migration:` reference
nodes (owned by whichever file defines them — also derivable, see §3.1). `partition.scopes`
(170 scopes, path-named like `root/catalog-service/…/Controllers`) is a second, already-
computed directory hierarchy the graph endpoint ignores.

Backend cost is flat (~400 ms regardless of level) because every request re-reads the same
three JSON artifacts from SQLite and `_build_graph` calls `_dataflow_graph` twice (once for
`rungs`, once for the level). No caching, no size cap, no pagination.

## 2. Axis 1 — why the design is not appreciated

- **It draws a general graph where users expect a containment tree.** Every code-map tool
  users have seen (IDE dependency diagrams, Sourcetrail, CodeSee, Structure101, NDepend)
  starts from the *directory/module tree* and shows dependencies *between siblings inside
  one parent*. Ours starts from a flat dataflow edge list and invents "packages" from id
  strings. The mismatch is structural, so no colour/legend work can rescue it.
- **Hubs dominate every rung.** `Tables`, `Config`, `Routes`, `Migrations` are type
  buckets that every module touches. At any rollup they become degree-3,000 super-hubs; in
  dagre they force one giant rank, in FA2 they pull everything into a ball around them
  ("all nodes pooling at one node" — the user's words). Buckets must not be peers of
  modules on the same canvas.
- **The ladder labels are meaningless on this repo.** "Depth 2 … Depth 5" say nothing; the
  user cannot predict what a click does, and each rung is *bigger* than the last.
- **Recent changes made it worse** (user report) is consistent with the uncommitted diff:
  it added the P2–P5 rungs (each larger than L3) and switched L2 to a time-boxed worker +
  sync `noverlap`, which adds the 4.8 s freeze on this repo.

## 3. Redesign

### 3.1 Hierarchy = directory tree, from file paths (server)

- Node → file: `xref.symbols[id].sites[0].file` for bare ids; for `route:`/`table:`/
  `migration:`/`config:` ids, the file of the edge's *other* endpoint that `schema_own`s /
  `http_in`s it, else the bucket (verify coverage on real data before relying on it).
- Rung *k* = directory prefix of length *k*, with pass-through collapse (a dir with exactly
  one child dir and no own files is skipped) and a **stop rule that actually shrinks**: descend
  only while the child count of the *current* container is > 1 and its member count is above
  the readability cap (~60 visible nodes), else hand off to L2 *scoped to that directory*.
- Type buckets (`Tables`, `Routes`, …) become **children of the container that owns them**,
  not global peers. A cross-container edge to a table is rolled into the owning container's
  aggregated edge. This removes the degree-3,000 hubs from every rung at once.
- Reuse `partition.scopes` names for labels (`catalog-service/…/Controllers`) so the
  canvas speaks the user's vocabulary; keep `members` for scoped drill-down.
- Expected top view for `unified-store`: **8 containers** (service-api, exposure-snapshot,
  catalog-service, managed-sql, sql-pool, client-java, core, ms-sql-java) + root configs,
  with ≤ 8·7 aggregated count-labelled edges — instead of 823 nodes.

### 3.2 Containment view, not breadcrumb-only

- Render the current container's children as **compound nodes drawn inside their parent's
  hull** (Cytoscape-style compound / ELK `INCLUDE_CHILDREN`), so "where am I" is visible on
  the canvas, not only in the chip row. Sigma has no compound-node primitive; two honest
  options: (a) keep Sigma and draw containers as `@sigma/layer-webgl` hulls (already used for
  family contours) with a **one-level-deep** expand-in-place; (b) switch the Atlas canvas to
  Cytoscape.js (`fcose`/`cose-bilkent` support compound graphs natively, MIT, Canvas 2D,
  comfortable to ~2–3k elements which the new top rungs never exceed). Recommend (a) first
  if the L2 leaf level must stay WebGL; (b) if compound layout quality matters more than raw
  node count — decide after the §3.1 rung sizes are measured.
- Double-click = **expand in place** (children appear inside the box, siblings stay put and
  shrink), right-click/⌘-double-click = "focus this container" (today's descend). Ascend via
  breadcrumb or Esc as today.

### 3.3 Layout per rung, chosen by shape not by rung name

- Container rungs (≤ ~60 nodes, aggregated edges): **ELK layered** (`elkjs`, runs in a
  worker) — node-size aware, handles wide ranks with compaction, compound-capable; or dagre
  *with a hard aspect-ratio guard*: if bbox aspect > 4:1, re-layout LR or fall back to a
  radial/force layout. Never ship a layout without checking its bbox aspect.
- Leaf L2 scoped to one container (hundreds of nodes): FA2 in the worker until
  **convergence** (supervisor reports; stop when mean displacement < ε or 3 s), then
  `noverlap` **in the same worker**, never on the main thread. Cache positions per
  `(snapshot, level, scope)` in `sessionStorage`/IndexedDB so revisits are instant.
- Unscoped L2 (6k nodes) should not be reachable from the UI; if kept, server-side layout
  precomputed at scan time and shipped as x/y.

## 4. Axis 2 — missing functionality

- **Size-aware drill-down**: every click must land on a graph of bounded size (§3.1). Today
  none do on this repo.
- **Expand-in-place / collapse**, and **aggregated edge labels** with counts (the `count`
  channel exists server-side; nothing draws it).
- **Search-to-focus** exists (⌘K) but only for symbols via the 6.8 MB L0 fetch; needs a
  server-side `/api/search?q=` with prefix/fuzzy match over containers, files and symbols.
- **Neighbourhood focus** ("show only what `sql-pool` touches") as a first-class action —
  `_restrict_dataflow_to_scope` already computes it; expose it as a toggle, not only via
  double-click.
- **Explicit loading / error / empty / too-large states.** The "loads forever" report is not
  fully root-caused (no browser capture yet). What is measured: a 4.8 s sync freeze at L2,
  a 15 s timeout × `retry: 2` → up to ~45 s before an error is shown, a 6.8 MB typeahead
  fetch racing the graph fetch, and repo switch keeping an altitude (`P5`) the new repo may
  not have → 501. Instrument first (request id + timing log on `/api/graph`, `performance.
  mark` around `buildGraph`/layout), then fix. Add a "graph too large — pick a module" state
  instead of attempting 6k-node layout.
- **Legend-as-filter**: clicking a legend row should hide/show that type (today only
  "hide tests" exists).
- **Minimap + zoom controls** once containers exist; **pin/lock node positions** so a
  refetch never re-scrambles a view the user has arranged.

## 5. Axis 3 — performance / near-real-time

Measured bottlenecks, in order of user-visible impact:
1. Main-thread `noverlap` at L2: 4.8 s freeze → move to the worker or drop below a size cap.
2. Payload: 4.4 MB L2 + 6.8 MB L0 on first paint → container rungs are tens of KB; lazy-load
   typeahead; gzip (verify uvicorn/vite proxy compression is on — unverified).
3. Server: ~400 ms/request, 2× artifact reads per request; cache parsed artifacts per
   `(db_path, snapshot_id)` in-process (index is immutable per snapshot) → expected <50 ms.
   Precompute the container tree at scan time or on first request and store it as an
   artifact.
4. Layout: cache positions per `(snapshot, level, scope)`; animate only deltas (already
   built). Target: any click → first paint < 300 ms from cache, < 1.5 s cold.
5. React Query: `placeholderData: keepPreviousData` so the old graph stays visible (dimmed)
   while the next loads, instead of a blank "loading graph…" canvas.
"Near real time" here means *bounded, predictable latency*, not push updates; SSE already
exists for scans and is enough.

## 6. Axis 4 — making the UI informative

- **Name things the user names.** Containers labelled by directory (`sql-pool`), rungs
  labelled by what they contain ("8 modules", "sql-pool: 5 packages"), not "Depth 3".
- **Counts on edges and in containers** ("service-api → Tables ×412"); the size channel is
  degree, which on a bucket-dominated graph tells the user nothing.
- **Semantic zoom**: aggregate when zoomed out, reveal children when zoomed in — the wheel
  gesture already exists, tie it to expand/collapse rather than to a global rung jump.
- **Focus + context on hover/select** exists; extend to *containers* (hover `sql-pool` →
  highlight every edge into/out of it, fade the rest) and show the hover card for
  synthetic groups (member count, languages, top callers) instead of "this is a group".
- **Persistent "you are here"**: breadcrumb + minimap + the parent hull always visible.
- **Separate structure from status.** Confidence/claims are a *lens*, and should never
  compete with the structural read on first load; default lens on a fresh repo should be
  plain structure with buckets tucked into containers.
- **Empty and failure states that explain themselves** ("no dependencies extracted for
  `client-dotnet` — 4 files, no scan claims yet").

## 7. Phasing and what must be verified before each step

1. **Probe, no UI**: implement the path-based container tree server-side as a pure function
   over `inventory` + `xref` and print the rung sizes for `unified-store` and this repo.
   Gate: top rung ≤ 12 nodes, every drill-down ≤ ~60 nodes or hands off to a scoped L2 of
   ≤ ~800 nodes. If not, the stop rule is wrong — fix before touching the frontend.
2. **Layout gate**: run ELK/dagre on the real rung-1/rung-2 graphs; assert bbox aspect ≤ 3:1
   and zero overlapping labels *by measurement* (Playwright + `__atlasSigma` probe), not by
   eye.
3. **Freeze gate**: `performance.mark` around fetch / build / layout / first paint at every
   rung on `unified-store`; nothing > 200 ms on the main thread.
4. Then the container canvas (§3.2), then edge counts + legend filters, then caching.
5. Capture one real "loads forever" session (network tab + console) before claiming that
   bug fixed — the current fixes in `TODO.md` are still marked "not verified live".

## 8. External references (what best-in-class tools do; checked against vendor docs/papers)

- Containers + expand-in-place is the norm for code maps, force-directed flat graphs the
  exception: Structure101 Levelized Structure Map (nested boxes, deps levelized to flow
  downward, expand a package in place, in/out dots stand in for hidden edges) —
  [docs](https://www.sonarsource.com/structure101/docs/java/studio/Content/workspace_sa/Structure%20Map.htm);
  NDepend graph expands one level per click and double-clicking an *aggregated edge* opens the
  leaf coupling graph — [docs](https://www.ndepend.com/docs/class-dependency-diagram);
  CodeSee "maps begin with most folders collapsed" — [docs](https://docs.codesee.io/docs/explore-your-map);
  Lattix/NDepend DSM aggregate dependency *counts* per cell —
  [Lattix](https://docs.lattix.com/lattix/userGuide/Working_with_the_Dependency_Structure_Matrix_DSM.html).
- Why dagre makes one wide rank: every ranker minimises edge slack, so all children of a hub
  land on the next rank; network-simplex compacts it further — [dagre wiki](https://github.com/dagrejs/dagre/wiki).
  ELK layered supports compound graphs via `elk.hierarchyHandling: INCLUDE_CHILDREN` on the
  root — [ELK option](https://eclipse.dev/elk/reference/options/org-eclipse-elk-hierarchyHandling.html);
  gotcha: per-child `layoutOptions` breaks it ([elkjs #159](https://github.com/kieler/elkjs/issues/159)).
  Cytoscape fcose: compound-aware, benchmarked to 5,000 nodes —
  [TVCG 2022](https://yoksis.bilkent.edu.tr/pdf/files/15807.pdf).
- Rendering is not the bottleneck: Sigma v3 targets "thousands of nodes and edges" and 6k/14.6k
  is inside its envelope — [sigmajs.org](https://www.sigmajs.org/); LOD knobs are
  `hideEdgesOnMove`, `hideLabelsOnMove`, `labelDensity`, `labelRenderedSizeThreshold`. React
  Flow maintainers say it is not intended for 1,000+ nodes
  ([discussion](https://github.com/xyflow/xyflow/discussions/3003)). cosmos.gl (GPU layout) moved
  to OpenJS ([announcement](https://openjsf.org/blog/introducing-cosmos-gl)); the older
  `@cosmograph/cosmos` is CC-BY-NC — current engine licence **unverified**.
- UX literature: Shneiderman's overview→zoom/filter→details
  ([PDF](https://hci.stanford.edu/courses/cs448b/papers/shneiderman96eyes.pdf)); van Ham &
  Perer invert it for large graphs — *search, show context, expand on demand*, explicitly to
  tame very-high-degree hubs ([InfoVis 2009](https://perer.org/papers/adamPerer-DOIGraphs-InfoVis2009.pdf));
  Elmqvist & Fekete's hierarchical-aggregation guidelines: entity budget, aggregates must look
  different from leaves, aggregated edges carry counts ([TVCG 2010](https://www.cs.au.dk/~elm/pdf/hieragg.pdf)).
- Unverified this pass (fetch blocked): Sourcetrail's neighbour bundling, exact ELK
  compaction/wrapping option ids, Structure101 edge-count labels.
