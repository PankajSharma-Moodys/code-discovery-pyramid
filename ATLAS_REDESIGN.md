# ATLAS_REDESIGN — why the graph looks poor, and what to do

**Budget: ≤200 lines. Design only, no implementation in this pass.**
**Supersedes `UI_DESIGN_PLAN.md` for the two canvases.** That doc's chrome work
(mesh, elevation, glow, card base) shipped and stands — see §1 for why it did
not help.

## 0. Verdict

**Do not rewrite the renderer.** Sigma v3 + graphology is the right engine and
is not the problem. The problem is, in order of blast radius:

1. **There is almost no graph to draw.** ≤2 renderable edges at every altitude.
2. **The real graph exists in the store and is never rendered.** 353 nodes,
   371 edges, fully typed, zero isolated.
3. **Both canvases run Sigma's stock defaults.** Grey dots, grey hairlines,
   no direction — because no attributes are ever set.

A from-scratch rewrite would reproduce all three. Fix the data, then the
encoding; the "beautiful" part is mostly a consequence.

## 1. Evidence

Measured against the running backend on this repo, counting edges whose *both*
endpoints resolve to a rendered node:

| Altitude | nodes | edges | renderable | nodes on an edge |
|---|---|---|---|---|
| L0 symbols | 2287 | 371 | **2** | 4 (0%) |
| L1 files | 413 | 2 | **2** | 3 (0%) |
| L2 territory | 20 | 1 | **1** | 2 (10%) |
| L3 modules | 7 | 2 | **2** | 3 (42%) |

A force layout on 99%-isolated nodes *must* produce the Links star-field; a rank
layout on 7 nodes *must* produce the Atlas voids. Both screenshots are the
correct rendering of broken input. This is why the previous pass — which only
touched cards and glow — changed nothing: **neither canvas consumes any of those
tokens**, and 75% of the screen is canvas.

**Cause at L0:** two node namespaces are mixed. Nodes are symbols
(`agent_adapter#_command_summaries`); edges are modules
(`agent_adapter → cdp.cli`). 369 of 371 edges dangle. This is the exact failure
`PLAN.md` Phase 0 was written to prevent.

**What those "dangling" edges actually are** — a complete architecture graph:

- **9 node types:** module 172, process 76, entity 38, table 27, route 25,
  config 6, library 6, migration 2, port 1
- **7 edge kinds:** call 123, persist 79, process_boundary 76, http_in 43,
  read 39, config_read 9, schema_own 2
- **Structure:** zero isolated; `cdp.store.sqlite_backend` degree 36,
  `cdp.cli` 19, `web.api.app` 16

**Cause at the renderer** (read from `node_modules/sigma/dist/` and the canvases):
Sigma's defaults are `defaultNodeColor:"#999"`, `defaultEdgeColor:"#ccc"`,
`defaultEdgeType:"line"`. `AtlasCanvas.tsx:92` sets `size: 8` on every node and
no colour; `:97` sets `size: 1` on every edge and no type — so although the
graph is `type:"directed"`, **direction is never drawn**. No
`nodeProgramClasses`/`edgeProgramClasses` are passed to either `new Sigma(...)`.

**Cause of the scatter:** both canvases call bare `inferSettings`, which returns
only `{barnesHutOptimize, strongGravityMode, gravity:0.05, scalingRatio:10,
slowDown}` and leaves `linLogMode:false`. Low gravity + high scaling is the
documented recipe for scattered dyads.

**Cause of the clipping:** `AtlasCanvas.tsx:58` sets fixed `nodesep/ranksep` and
never fits the result to the viewport; dagre drops isolated nodes into rank 0 —
the row of clipped labels along the Atlas bottom edge.

## 2. Fix 1 — make the graph exist (blocks everything else)

Serve one node namespace per altitude, and make the altitudes roll up the
*typed* graph rather than the directory tree:

| Altitude | Nodes | Built from |
|---|---|---|
| **L3** Packages | ~8 super-nodes | dotted modules rolled up to first segment |
| **L2** Modules | 353 typed nodes | the real graph, as-is |
| **L1** Files | files | needs file-level edges — see risk in §7 |
| **L0** Symbols | symbols | symbol-scoped edges only, or cut |

Acceptance: at every altitude, `renderable_edges / edges ≥ 0.95`. Assert it in a
contract test — this is the metric that was silently zero.

## 3. Fix 2 — make every channel carry something

Today: one channel (position) carries data; five sit idle. Assignment:

| Channel | Carries | Notes |
|---|---|---|
| Node **shape** | node type (9→ grouped) | primary identity; CVD-immune |
| Node **size** | degree, log-scaled | makes hubs findable |
| Node **fill** | type *family* (3) | redundant with shape, by design |
| Node **ring** | claim status | `@sigma/node-border`, MIT |
| Edge **colour** | family of its target | the map reads as code→state |
| Edge **style** | confidence | solid / dashed / dotted |
| Edge **taper** | direction | `edge-triangle`, already bundled |
| Edge **curve** | parallel separation | `@sigma/edge-curve`, MIT |
| Background **hull** | package membership | `@sigma/layer-webgl`, MIT |

**Colour is capped at three, and this is computed, not taste.** On this dark
surface only blue/orange/aqua clear the all-pairs CVD floor; every 4th slot
tested fails hard (violet↔blue ΔE 1.9 protan; magenta↔aqua ΔE 1.6 deutan;
yellow↔orange ΔE 10.6 normal-vision). A graph canvas is inherently all-pairs, so
node type **cannot** be colour-encoded. Three families:

| Family | Colour | Types | Count |
|---|---|---|---|
| **Code** | blue `#3987e5` | module, library | 178 |
| **Runtime surface** | orange `#d95926` | process, route, port | 102 |
| **Persistent state** | aqua `#199e70` | table, entity, migration, config | 73 |

Shape disambiguates *within* a family (module=circle, library=hollow circle;
process=square, route=triangle; table=diamond, entity=hollow diamond). Edges take
their target family's colour, so the dominant visual story becomes "blue code
reaching through orange boundaries into aqua state" — which is the actual
architecture.

Semantic triad (`tokens.css:16-21`) stays reserved for claim status on the node
ring only. Status on the ring, structure in the fill, flow on the edge — never
mixed (the Datadog service-map convention; vendor docs, not independently
verified).

## 4. Fix 3 — layout

- `linLogMode: true` + `outboundAttractionDistribution: true`, then **rescale**
  (the FA2 paper used scaling ~0.1 for the LinLog variant and notes slower
  convergence → raise iterations). Tightens clusters, pushes hubs to the rim.
- **Fit to viewport** after layout. Non-negotiable; fixes the clipping directly.
- Contour hulls per package behind the nodes — this is what gives the "mesh"
  visual weight it currently lacks.
- Raise `labelRenderedSizeThreshold` so only hubs label when zoomed out.

Hierarchical edge bundling is the right long-term family for the Atlas
(`partition.scopes[]` supplies the hierarchy) but there is **no maintained
WebGL implementation** — treat it as a bespoke build, not a drop-in. Out of
scope here.

## 5. Fix 4 — tiles that say what they are for

The complaint is accurate: tiles name internal concepts and stop. Every tile
gets three things — a **question it answers**, a **value**, and an **empty state
that teaches the next action**.

| Now | Problem | Becomes |
|---|---|---|
| `L3 / L2 / L1` | jargon, no referent | `Altitude — Packages / Modules / Files`, with "how far out the map is zoomed" |
| `Structure / Divergence / Confidence` | no indication these recolour | `Lens — what colour means right now`, each with a one-line caption |
| `root/(agent_adapter+5)` | unreadable machine string | `agent_adapter +5 more`, tooltip lists them |
| `Doctor / model compatibility` | internal name | `Which models can CDP trust?` |
| `Trajectory explorer` | internal name | `What did past runs cost and learn?` |
| `coverage 0/413 0%` + full red bar | reads as an alarm | it means "no wave has run yet" — say that, and make the CTA the bar |

## 6. Phasing

| Phase | Contents | Done = |
|---|---|---|
| **P0 Data** | one namespace per altitude | `renderable/total ≥ 0.95` in a contract test |
| **P1 Encoding** | shape, size, ring, 3-colour, taper, curve | a stranger names the three families without a legend |
| **P2 Layout** | linLog + rescale, fit-to-viewport, hulls | nothing clipped at any zoom; no scattered dyads |
| **P3 Tiles** | labels, subtitles, empty states | every tile answers "what is this for" unprompted |
| **P4 Polish** | vignette, `saturate(165%)` on panels, LOD labels | cut first |

**Cut line:** P4, then P2's hulls. **Never cut P0** — every other phase is
cosmetics on an empty canvas.

**Rejected:** `@cosmograph/cosmos` — the obvious "GPU graphs" pick, but it is
**CC-BY-NC-4.0 and would fail this repo's own licence gate**
(`scripts/check-licenses.mjs`). Flagging so nobody rediscovers it later.
`@antv/g6` (MIT) and `reagraph` (Apache-2.0) are viable but are full rewrites
for a problem that is configuration.

## 7. Stress test of this design

- **P0 is not a one-line swap, and I should not imply it is.** The directory
  namespace (`tests/fixtures/minirepo/core`) and the dotted namespace
  (`cdp.store.sqlite_backend`) are genuinely different partitions of the repo,
  not two spellings. Reconciling them is the real work; budget for it.
- **L1 may have no fix.** File-level import extraction found 2 edges across 413
  files, both in a Java fixture — Python imports appear not to feed the file
  graph at all. If that is a backend gap, L1 should be **cut**, not styled.
  Verify before scheduling P1 work against it.
- **353 nodes / 371 edges is still sparse** (mean degree 2.1). linLog may
  scatter it anyway. Test before committing; fall back to the L3 package
  rollup (~8 super-nodes) as the default altitude if so.
- **Shape encoding fails at small sizes.** At 353 nodes zoomed out, every shape
  is a dot and §3's primary identity channel silently stops working. Shape must
  resolve only past a zoom threshold; below it colour+size carry, and the legend
  must say so. Do not ship shape as the sole identity channel without this.
- **Three hues may read as monotonous** against a "make it beautiful" goal. The
  answer is depth, not more hues — hulls, ring contrast, size range, vignette.
  If it still feels flat after P2, add luminance steps within a family before
  reaching for a fourth hue, which the validator will reject.
