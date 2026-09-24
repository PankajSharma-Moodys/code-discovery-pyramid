import * as dagre from "@dagrejs/dagre";
import { indexParallelEdgesIndex } from "@sigma/edge-curve";
import Graph from "graphology";
import forceAtlas2 from "graphology-layout-forceatlas2";
import FA2LayoutSupervisor from "graphology-layout-forceatlas2/worker";
import noverlap from "graphology-layout-noverlap";
import NoverlapLayoutSupervisor from "graphology-layout-noverlap/worker";
import type Sigma from "sigma";
import type { Altitude } from "../api/nodeId.ts";
import {
  edgeWidth,
  familyOf,
  nodeSize,
  shapeOf,
  type Family,
} from "../theme/graphEncoding.ts";
import { getCachedPositions, setCachedPositions, type CachedPosition } from "./positionCache.ts";

export interface RawGraphNode {
  id: string;
  label: string;
  type?: string | null;
  family?: string | null;
  degree?: number | null;
  node_id?: string | null;
  members?: string[] | null;
  level?: number | null;
  /** `cdp` inventory file role (`source`/`test`/...), `null` when the node
   * has no single backing file. Powers the legend's "Hide tests" toggle. */
  role?: string | null;
}

export interface RawGraphEdge {
  source: string;
  target: string;
  kind: string;
  confidence?: string | null;
  count?: number | null;
  weight?: number | null;
}

export interface RawGraph {
  nodes: RawGraphNode[];
  edges: RawGraphEdge[];
}

/**
 * `ATLAS_REDESIGN.md` §4. Two bugs are fixed here, both of them layout:
 *
 * 1. Both canvases called bare `inferSettings`, which returns only
 *    `{barnesHutOptimize, strongGravityMode, gravity: 0.05, scalingRatio: 10,
 *    slowDown}` and leaves `linLogMode: false`. Low gravity with high scaling
 *    is the documented recipe for scattered dyads -- the Links star-field.
 * 2. Nothing ever fit the result to the viewport, and dagre drops isolated
 *    nodes into rank 0, which is the row of clipped labels along the bottom
 *    edge of the Atlas.
 *
 * The FA2 paper notes the LinLog variant converges more slowly and wants a
 * much smaller scaling, hence the iteration bump alongside `scalingRatio`.
 */
const FA2_ITERATIONS = 500;
// Post-FA2 anti-overlap pass, applied every time regardless of how well FA2
// converged: `adjustSizes` only keeps connected pairs apart *during* the
// simulation, it's not a hard guarantee at rest -- sparse/isolated nodes
// under `strongGravityMode` can still end up stacked on top of each other or
// strung along a line through the gravity center. `noverlap` is a cheap,
// separate algorithm whose only job is "no two circles touch", so it runs
// last and never fights FA2's attraction/repulsion balance.
const NOVERLAP_ITERATIONS = 250;
const NOVERLAP_SETTINGS = { margin: 6 };

// Deterministic seeding on a circle rather than `Math.random()`: the same
// graph then lays out the same way twice, so a lens switch or a refetch
// doesn't silently reshuffle the map under the user.
function seedCircle(graph: Graph, skip?: ReadonlySet<string>): void {
  const n = Math.max(1, graph.order);
  let i = 0;
  graph.forEachNode((node) => {
    if (skip?.has(node)) return;
    const angle = (2 * Math.PI * i) / n;
    const radius = 100 + 400 * ((i * 2654435761) % 1000) / 1000;
    graph.setNodeAttribute(node, "x", Math.cos(angle) * radius);
    graph.setNodeAttribute(node, "y", Math.sin(angle) * radius);
    i += 1;
  });
}

/** Groups every node id by connected component (ignoring edge direction),
 * sorted deterministically (by each component's own smallest member id, then
 * members within a component by id) so repeated calls on the same graph
 * agree regardless of node/edge insertion order. */
function componentGroups(graph: Graph): string[][] {
  const parent = new Map<string, string>();
  function find(x: string): string {
    let root = x;
    while (parent.get(root) !== root) root = parent.get(root)!;
    return root;
  }
  function union(a: string, b: string): void {
    const ra = find(a);
    const rb = find(b);
    if (ra !== rb) parent.set(ra, rb);
  }
  graph.forEachNode((node) => parent.set(node, node));
  graph.forEachEdge((_edge, _attrs, source, target) => union(source, target));

  const groups = new Map<string, string[]>();
  graph.forEachNode((node) => {
    const root = find(node);
    const list = groups.get(root);
    if (list) list.push(node);
    else groups.set(root, [node]);
  });

  return [...groups.values()]
    .map((ids) => ids.sort())
    .sort((a, b) => (a[0] < b[0] ? -1 : a[0] > b[0] ? 1 : 0));
}

/** FA2 + noverlap already test as even *within* a connected component
 * (verified: nearest-neighbor p90/p10 stays under ~2 across chain/tree/hub/
 * dense-fanout/power-law fixtures at this repo's real 353-node scale). What
 * neither pass guarantees is spacing *between* disconnected components:
 * `scalingRatio` is deliberately low (0.2, tuned for legible connected
 * clusters) so repulsion between components sharing no edge is weak, and
 * `strongGravityMode` pulls every component toward the same shared center
 * regardless of whether it has any reason to sit near another one. Measured
 * live against this repo's own real L2 graph (353 nodes, 85 separate
 * components): component-centroid nearest-neighbor distance ranged from 1.2
 * to 80.8 (a 65x spread) -- some pairs of unrelated components end up
 * effectively coincident, which is the concrete mechanism behind "some nodes
 * clubbed together, some far apart".
 *
 * This runs once, after FA2 + noverlap have already settled each
 * component's *internal* shape, and only translates each component as a
 * rigid block (never touching relative positions within a component, so the
 * already-verified even spacing above is untouched) until no two components'
 * bounding circles are closer than `minGap`. Cheap: `graph.order` stays
 * small enough in practice (this repo: 353 nodes / 85 components) that an
 * O(components²) pairwise pass converges in well under this function's own
 * iteration cap. */
const COMPONENT_MIN_GAP = 30;
const COMPONENT_SEPARATION_ITERATIONS = 80;

function separateComponents(graph: Graph, minGap = COMPONENT_MIN_GAP, iterations = COMPONENT_SEPARATION_ITERATIONS): void {
  const groups = componentGroups(graph);
  if (groups.length <= 1) return;

  const boxes = groups.map((ids) => {
    let ox = 0;
    let oy = 0;
    for (const id of ids) {
      ox += graph.getNodeAttribute(id, "x") as number;
      oy += graph.getNodeAttribute(id, "y") as number;
    }
    ox /= ids.length;
    oy /= ids.length;
    let radius = 0;
    for (const id of ids) {
      const dx = (graph.getNodeAttribute(id, "x") as number) - ox;
      const dy = (graph.getNodeAttribute(id, "y") as number) - oy;
      const size = (graph.getNodeAttribute(id, "size") as number | undefined) ?? 4;
      radius = Math.max(radius, Math.hypot(dx, dy) + size);
    }
    return { ids, ox, oy, cx: ox, cy: oy, radius };
  });

  for (let iter = 0; iter < iterations; iter++) {
    let moved = false;
    for (let i = 0; i < boxes.length; i++) {
      for (let j = i + 1; j < boxes.length; j++) {
        const a = boxes[i];
        const b = boxes[j];
        let dx = b.cx - a.cx;
        let dy = b.cy - a.cy;
        let dist = Math.hypot(dx, dy);
        const minDist = a.radius + b.radius + minGap;
        if (dist >= minDist) continue;
        moved = true;
        if (dist < 1e-6) {
          // Coincident centroids -- push along a deterministic direction
          // rather than dividing by zero.
          dx = 1;
          dy = 0;
          dist = 1;
        }
        const push = (minDist - dist) / 2;
        const ux = dx / dist;
        const uy = dy / dist;
        a.cx -= ux * push;
        a.cy -= uy * push;
        b.cx += ux * push;
        b.cy += uy * push;
      }
    }
    if (!moved) break;
  }

  boxes.forEach((box) => {
    const dx = box.cx - box.ox;
    const dy = box.cy - box.oy;
    if (dx === 0 && dy === 0) return;
    for (const id of box.ids) {
      graph.setNodeAttribute(id, "x", (graph.getNodeAttribute(id, "x") as number) + dx);
      graph.setNodeAttribute(id, "y", (graph.getNodeAttribute(id, "y") as number) + dy);
    }
  });
}

function fa2Settings(graph: Graph) {
  const inferred = forceAtlas2.inferSettings(graph);
  return {
    ...inferred,
    linLogMode: true,
    outboundAttractionDistribution: true,
    adjustSizes: true,
    strongGravityMode: true,
    gravity: 1.2,
    scalingRatio: 0.2,
    slowDown: 8,
  };
}

/** Synchronous, main-thread FA2 -- fine for the small `LinksCanvas` graph.
 * `AtlasCanvas` uses `layoutForceAtlas2Async` instead: at hundreds of nodes,
 * 500 synchronous iterations is the freeze users reported as "lag/blips" on
 * every altitude/scope change. */
export function layoutForceAtlas2(graph: Graph): void {
  seedCircle(graph);
  forceAtlas2.assign(graph, { iterations: FA2_ITERATIONS, settings: fa2Settings(graph) });
  noverlap.assign(graph, { maxIterations: NOVERLAP_ITERATIONS, settings: NOVERLAP_SETTINGS });
  separateComponents(graph);
}

/** Runs `noverlap` in its own web worker rather than `noverlap.assign` on the
 * main thread -- `WEB_REDESIGN_RESEARCH.md` §5 item 1: measured **4.8s
 * synchronous freeze** on the real `unified-store` L2 graph (6,064 nodes),
 * entirely from this one call. Resolves on `onConverged` or a size-scaled
 * wall-clock budget, whichever comes first, so a graph that never fully
 * settles still bounds how long a scope change stays in its loading state. */
function runNoverlapAsync(graph: Graph): Promise<void> {
  return new Promise((resolve) => {
    let settled = false;
    const supervisor = new NoverlapLayoutSupervisor(graph, {
      settings: NOVERLAP_SETTINGS,
      onConverged: () => finish(),
    });
    function finish(): void {
      if (settled) return;
      settled = true;
      supervisor.stop();
      supervisor.kill();
      resolve();
    }
    supervisor.start();
    const budgetMs = Math.min(3000, Math.max(200, graph.order * 4));
    setTimeout(finish, budgetMs);
  });
}

/** Same algorithm, run in a web worker so the main thread (and therefore
 * scroll/hover/click) never blocks on it. Runs for a size-scaled wall-clock
 * budget rather than a fixed iteration count -- the worker reports positions
 * as it goes but doesn't expose an iteration counter to the caller, and a
 * time budget is also what actually bounds how long a scope change stays in
 * its loading state. Caller must have already seeded positions (`buildGraph`
 * does this for the non-ranked case) since the worker starts from whatever
 * x/y is already on the graph. */
export function layoutForceAtlas2Async(graph: Graph): Promise<void> {
  const settings = fa2Settings(graph);
  return new Promise((resolve) => {
    const supervisor = new FA2LayoutSupervisor(graph, { settings });
    supervisor.start();
    const budgetMs = Math.min(1200, Math.max(200, graph.order * 3));
    setTimeout(() => {
      supervisor.stop();
      supervisor.kill();
      runNoverlapAsync(graph).then(() => {
        separateComponents(graph);
        resolve();
      });
    }, budgetMs);
  });
}

interface RankedLayout {
  positions: Map<string, { x: number; y: number }>;
  width: number;
  height: number;
}

function runDagre(graph: Graph, rankdir: "TB" | "LR", spread: number): RankedLayout {
  const g = new dagre.graphlib.Graph();
  g.setGraph({ rankdir, nodesep: 55 * spread, ranksep: 210 * spread, marginx: 40, marginy: 40 });
  g.setDefaultEdgeLabel(() => ({}));
  graph.forEachNode((node) => g.setNode(node, { width: 150, height: 44 }));
  graph.forEachEdge((_edge, _attrs, source, target) => {
    if (source !== target) g.setEdge(source, target);
  });
  dagre.layout(g);

  // Which raw dagre axis is "rank depth" (progression between ranks) vs.
  // "order within a rank" flips with `rankdir` -- for `TB` it's y/x, for
  // `LR` it's x/y. Reading `pos.x`/`pos.y` unconditionally as if `TB` always
  // held (an earlier version of this function did) silently mixed the two
  // axes whenever the aspect-ratio guard below chose the `LR` rerun,
  // producing nonsense coordinates instead of a real transpose.
  const rankAxis = (pos: { x: number; y: number }) => (rankdir === "LR" ? pos.x : pos.y);
  const orderAxis = (pos: { x: number; y: number }) => (rankdir === "LR" ? pos.y : pos.x);
  const toXY = (rankCoord: number, orderCoord: number): { x: number; y: number } =>
    // dagre's rank axis grows away from rank 0 in the positive direction;
    // for `TB` that's downward, so flip it to put rank 0 at the top of the
    // screen. For `LR` growing rightward already reads left-to-right.
    rankdir === "LR" ? { x: rankCoord, y: orderCoord } : { x: orderCoord, y: -rankCoord };

  const byRank = new Map<number, { node: string; order: number }[]>();
  const rankCoordOf = new Map<number, number>();
  g.nodes().forEach((node) => {
    const pos = g.node(node);
    if (!pos) return;
    const rank = pos.rank ?? 0;
    const list = byRank.get(rank) ?? [];
    list.push({ node, order: orderAxis(pos) });
    byRank.set(rank, list);
    rankCoordOf.set(rank, rankAxis(pos));
  });

  const step = 55 * spread;
  const positions = new Map<string, { x: number; y: number }>();

  // Ranks bucket into three shapes, each needing a different fix:
  //  - exactly one node: no order-axis signal at all, dagre centers it on
  //    the same coordinate as every other sole rank, so a single-file chain
  //    (measured: real L3/package rollups on this repo are often close to
  //    one) renders as a dead-straight line. Fixed with a deterministic
  //    zigzag, not random, for the same stability reason as FA2's circular
  //    seed. Verified via a 7-node chain through this exact code path before
  //    this fix: every node landed at the same coordinate.
  //  - a merely-wide rank: dagre's own within-rank spread is fine, recentred
  //    to 0 (see note below) but otherwise used as-is.
  //  - a very wide rank (`WEB_REDESIGN_RESEARCH.md` §3.3: a hub with dozens
  //    of direct children collapses onto one rank, one node deep -- measured
  //    284:1 on the real `unified-store` L2 graph): reflow that rank into a
  //    roughly square grid instead of one long line, so the hub's fan-out
  //    gains a second axis instead of stretching the first one further.
  //    (Rerunning dagre transposed, `layoutRanked`'s other guard, cannot fix
  //    this shape on its own -- rotating a 1xN line just produces an Nx1
  //    line instead; the grid wrap is what actually squares it up.)
  //
  // Every branch centres its rank's order axis on 0 rather than trusting
  // dagre's own absolute coordinate for it. dagre computes each rank's raw
  // order-axis spread independently based on that rank's own member count and
  // node width, so once one rank gets rewritten into a compact grid its
  // frame no longer lines up with an untouched rank's much wider raw
  // spread -- a lone hub sitting at dagre's original (and, next to a
  // several-thousand-pixel-wide unwrapped rank, enormous) coordinate is
  // exactly the bug the grid wrap would otherwise reintroduce one level up.
  const GRID_WRAP_THRESHOLD = 12;
  byRank.forEach((members, rank) => {
    const rankCoord = rankCoordOf.get(rank) ?? 0;
    if (members.length === 1) {
      const jitter = Math.sin(rank * 1.4) * step;
      positions.set(members[0].node, toXY(rankCoord, jitter));
    } else if (members.length > GRID_WRAP_THRESHOLD) {
      const sorted = [...members].sort((a, b) => a.order - b.order);
      const cols = Math.ceil(Math.sqrt(sorted.length));
      const rows = Math.ceil(sorted.length / cols);
      sorted.forEach((m, i) => {
        const col = i % cols;
        const row = Math.floor(i / cols);
        const orderCoord = (col - (cols - 1) / 2) * step;
        const rankOffset = (row - (rows - 1) / 2) * step;
        positions.set(m.node, toXY(rankCoord + rankOffset, orderCoord));
      });
    } else {
      const mean = members.reduce((sum, m) => sum + m.order, 0) / members.length;
      members.forEach((m) => positions.set(m.node, toXY(rankCoord, m.order - mean)));
    }
  });

  let minX = Infinity;
  let maxX = -Infinity;
  let minY = Infinity;
  let maxY = -Infinity;
  positions.forEach(({ x, y }) => {
    minX = Math.min(minX, x);
    maxX = Math.max(maxX, x);
    minY = Math.min(minY, y);
    maxY = Math.max(maxY, y);
  });

  return { positions, width: Math.max(1, maxX - minX), height: Math.max(1, maxY - minY) };
}

function aspectOf(layout: RankedLayout): number {
  return Math.max(layout.width, layout.height) / Math.min(layout.width, layout.height);
}

/** Dagre ranks straight from the dependency edges. `nodesep`/`ranksep` scale
 * with the node count so a 6-node L3 doesn't spread across three screens and
 * a 30-node one doesn't overlap -- the old fixed 60/90 did both.
 *
 * `ranksep` is deliberately ~4x `nodesep`. Sigma scales a graph to fit its
 * longest axis, so a short wide DAG gets letterboxed into a band with dead
 * space above and below it -- which is what the first pass produced. Biasing
 * the layout taller uses the viewport instead of the void.
 *
 * `WEB_REDESIGN_RESEARCH.md` §3.3: a hub-dominated graph (one node with
 * dozens of children) still produces an extreme aspect ratio under the
 * default `rankdir: "TB"` bias above -- measured 284:1 on the real
 * `unified-store` L2 graph. If the primary layout's bbox comes out worse
 * than 4:1, rerun once with `rankdir: "LR"` (transposing which axis absorbs
 * the fan-out) and keep whichever bbox is actually more square. */
export function layoutRanked(graph: Graph): void {
  const spread = Math.max(0.6, Math.min(1.8, 18 / Math.max(1, graph.order)));
  const primary = runDagre(graph, "TB", spread);

  let chosen = primary;
  if (aspectOf(primary) > 4) {
    const alternate = runDagre(graph, "LR", spread);
    if (aspectOf(alternate) < aspectOf(primary)) chosen = alternate;
  }

  chosen.positions.forEach((pos, node) => {
    graph.setNodeAttribute(node, "x", pos.x);
    graph.setNodeAttribute(node, "y", pos.y);
  });
}

/** Identifies which cached position bucket a graph belongs to
 * (`positionCache.ts`) -- a different repo/snapshot, level, or scope has no
 * reason to reuse another one's coordinates. `repoKey` is the caller's
 * `repo:state_dir` (`useRepoParams`). */
export interface PositionCacheKey {
  repoKey: string;
  level: string;
  scope: string | null;
}

/** Re-applies a cache entry's `{x, y, pinned}` onto a graph node, also
 * setting `fixed` (the attribute `graphology-layout-forceatlas2` itself
 * checks to skip a node during simulation) so a pinned node stops moving
 * without the caller having to know FA2's attribute name. */
function applyCachedPosition(graph: Graph, nodeId: string, pos: CachedPosition): void {
  if (!graph.hasNode(nodeId)) return;
  graph.setNodeAttribute(nodeId, "x", pos.x);
  graph.setNodeAttribute(nodeId, "y", pos.y);
  graph.setNodeAttribute(nodeId, "pinned", pos.pinned);
  graph.setNodeAttribute(nodeId, "fixed", pos.pinned);
}

/** Writes every node's current position (and pin state) back to
 * `positionCache.ts` so the next visit to this exact repo/level/scope seeds
 * from (near-)final coordinates instead of a fresh circle/dagre run. Called
 * once a layout pass (ranked or FA2) has actually settled. */
export function persistPositions(graph: Graph, cacheKey: PositionCacheKey): void {
  const positions: Record<string, CachedPosition> = {};
  graph.forEachNode((node, attrs) => {
    positions[node] = {
      x: attrs.x as number,
      y: attrs.y as number,
      pinned: Boolean(attrs.pinned),
    };
  });
  setCachedPositions(cacheKey.repoKey, cacheKey.level, cacheKey.scope, positions);
}

/** Toggles a single node's pin state and immediately persists it -- pinning
 * only has to survive this node's own entry, not a full relayout, so this
 * writes the cache directly rather than waiting for the next `buildGraph`. */
export function setNodePinned(graph: Graph, nodeId: string, pinned: boolean, cacheKey: PositionCacheKey): void {
  if (!graph.hasNode(nodeId)) return;
  graph.setNodeAttribute(nodeId, "pinned", pinned);
  graph.setNodeAttribute(nodeId, "fixed", pinned);
  persistPositions(graph, cacheKey);
}

/**
 * Builds the graphology graph with every encoding channel attached as a raw
 * attribute. Nothing here decides a *colour* -- `AtlasCanvas`'s reducers do
 * that per lens, so switching lenses never touches graph identity and never
 * re-triggers layout.
 *
 * `cacheKey`, when given, seeds any previously-cached node positions
 * (`positionCache.ts`) before layout runs, and re-applies *pinned* ones
 * again afterward -- ranked layout (`layoutRanked`, dagre) recomputes every
 * node's coordinates from scratch regardless of what was already on the
 * graph, so a pin would otherwise be silently discarded on every ranked
 * rebuild.
 */
export function buildGraph(data: RawGraph, ranked: boolean, cacheKey?: PositionCacheKey): Graph {
  const graph = new Graph({ multi: true, type: "directed" });

  let maxDegree = 1;
  for (const node of data.nodes) maxDegree = Math.max(maxDegree, node.degree ?? 0);

  for (const node of data.nodes) {
    const family: Family = familyOf(node.family);
    const degree = node.degree ?? 0;
    graph.addNode(node.id, {
      label: node.label,
      baseLabel: node.label,
      rawId: node.id,
      nodeId: node.node_id ?? null,
      kind: node.type ?? "module",
      family,
      shape: shapeOf(node.type),
      degree,
      memberCount: node.members?.length ?? 0,
      role: node.role ?? null,
      x: 0,
      y: 0,
      size: nodeSize(degree, maxDegree),
      type: shapeOf(node.type),
      pinned: false,
      fixed: false,
    });
  }

  for (const edge of data.edges) {
    if (!graph.hasNode(edge.source) || !graph.hasNode(edge.target)) continue;
    if (edge.source === edge.target) continue;
    const count = edge.count ?? 1;
    graph.addEdge(edge.source, edge.target, {
      kind: edge.kind,
      confidence: edge.confidence ?? null,
      count,
      targetFamily: graph.getNodeAttribute(edge.target, "family") as Family,
      size: edgeWidth(edge.confidence),
      type: "arrow",
      // Only ranked (L3/P*) graphs are small and rolled-up enough for an
      // edge label to add signal rather than clutter -- `_build_graph_grouped`
      // is the only builder that aggregates multiple raw edges into one
      // `count`, so a leaf L2 edge (count always 1) never gets a "×1" label.
      label: ranked && count > 1 ? `×${count}` : undefined,
    });
  }

  // Curve anything parallel so overlapping channels stay countable.
  indexParallelEdgesIndex(graph, {
    edgeIndexAttribute: "parallelIndex",
    edgeMinIndexAttribute: "parallelMinIndex",
    edgeMaxIndexAttribute: "parallelMaxIndex",
  });
  graph.forEachEdge((edge, attrs) => {
    const index = attrs.parallelIndex as number | null;
    const max = attrs.parallelMaxIndex as number | undefined;
    if (typeof index !== "number" || !max) return;
    graph.setEdgeAttribute(edge, "type", "curve");
    graph.setEdgeAttribute(edge, "curvature", (0.6 * index) / Math.max(1, max));
  });

  const cached = cacheKey ? getCachedPositions(cacheKey.repoKey, cacheKey.level, cacheKey.scope) : {};
  for (const [nodeId, pos] of Object.entries(cached)) applyCachedPosition(graph, nodeId, pos);

  // Ranked (dagre) layouts are cheap and synchronous, so they run here.
  // Non-ranked graphs are only seeded here -- the caller (`AtlasCanvas`) runs
  // `layoutForceAtlas2Async` afterward so the FA2 pass can go through the
  // worker instead of blocking this synchronous build. Either way, a pinned
  // node's cached position was just overwritten by that pass (dagre
  // recomputes everything; `seedCircle` only skips nodes it's never seen
  // before) -- reapply it so a pin actually holds across a rebuild.
  if (ranked) {
    layoutRanked(graph);
    for (const [nodeId, pos] of Object.entries(cached)) {
      if (pos.pinned) applyCachedPosition(graph, nodeId, pos);
    }
  } else {
    // Cached (already-applied) positions are excluded from the circular
    // seed entirely -- not just pinned ones -- so a revisit gives FA2 a
    // near-final starting point instead of always restarting from scratch.
    seedCircle(graph, new Set(Object.keys(cached)));
  }

  return graph;
}

/** `WEB_REDESIGN_RESEARCH.md` §3.2's "one-level-deep expand-in-place" option
 * (a): Sigma has no compound-node primitive, so a container's children are
 * injected as ordinary nodes into the *same* graphology graph, confined to a
 * fixed-radius circle centred on the parent's own position, and the parent
 * shrinks to an (almost invisible, but not `hidden`) point -- `hidden` nodes
 * also hide every edge touching them in Sigma, which would silently drop the
 * parent's already-existing aggregated edges to *other* containers. Kept
 * visible-but-tiny instead, so those edges still draw, anchored where the
 * cluster now sits.
 *
 * Originally shipped as one container expanded at a time; since extended
 * (still squarely option (a), no Cytoscape/ELK swap -- a deliberate,
 * user-confirmed choice) to multiple simultaneous top-level expansions and
 * nested expansion of a child that is itself a container. Bookkeeping for
 * *which* containers are open and in what order to apply/collapse them
 * lives entirely in the caller (`AtlasCanvas.tsx`'s `expanded` map); this
 * function stays a pure single-container primitive -- it has no idea
 * whether `parentId` is itself nested inside another expansion. */
export const EXPAND_RADIUS = 90;
/** Each nesting level shrinks the circle so a depth-N cluster has a chance
 * of staying inside its ancestor's hull instead of overflowing it. Not
 * exact containment (this is a bounded simulation, not a real compound
 * layout) -- just enough that nesting reads as "smaller, inside" rather
 * than "same size, overlapping." */
export const NESTED_RADIUS_FACTOR = 0.45;
// Small, size-capped passes -- this is a synchronous, main-thread layout
// (unlike the FA2 worker `layoutForceAtlas2Async` uses for the main graph),
// deliberately: it only ever runs over one container's already-bounded
// children (`WEB_REDESIGN_RESEARCH.md` §3.1's stop rule caps a container at
// ~60 nodes, or hands off to a scoped L2 of ≤ ~800), triggered by a single
// user click, not on every render.
const EXPAND_FA2_ITERATIONS = 200;
const EXPAND_NOVERLAP_ITERATIONS = 100;
// A container this doc's own §3.1 stop rule lets through can still hand off
// to a scoped L2 of up to ~800 nodes -- past this size, the sync FA2+noverlap
// pass below (a deliberate main-thread call, unlike the worker-based one the
// primary graph uses) would itself become the freeze this whole redesign
// pass was fixing elsewhere. Above the cap, children keep the circular seed
// only -- less legible, but a click that responds beats one that hangs.
const EXPAND_SYNC_LAYOUT_CAP = 150;

export interface ExpandedChildren {
  childIds: string[];
  edgeIds: string[];
  parentOriginal: { size: number; label: string; baseLabel: string; forceLabel: unknown };
}

/** Mutates `graph` in place: adds `children`'s nodes/edges positioned inside
 * a circle around `parentId`'s current position, and shrinks `parentId` down
 * to an edge-anchor point. Returns exactly what {@link collapseContainerInPlace}
 * needs to undo it. Skips any child id that collides with an existing
 * top-level node (rare -- would mean the same id appears at two rungs).
 *
 * `opts.radius` overrides {@link EXPAND_RADIUS} -- the caller shrinks this
 * per nesting depth. `opts.rung` is stamped onto every injected child as a
 * `rung` attribute: the altitude *that child's own children* live at, so a
 * later double-click on an injected node can tell it's itself expandable
 * (and at what level to fetch) without the graph needing to track nesting
 * depth anywhere else. */
export function expandContainerInPlace(
  graph: Graph,
  parentId: string,
  children: RawGraph,
  opts?: { rung?: Altitude; radius?: number },
): ExpandedChildren {
  const radius = opts?.radius ?? EXPAND_RADIUS;
  const parentX = graph.getNodeAttribute(parentId, "x") as number;
  const parentY = graph.getNodeAttribute(parentId, "y") as number;

  const scratch = new Graph({ multi: true, type: "directed" });
  let maxDegree = 1;
  for (const n of children.nodes) maxDegree = Math.max(maxDegree, n.degree ?? 0);
  for (const n of children.nodes) {
    if (!graph.hasNode(n.id)) scratch.addNode(n.id);
  }
  for (const e of children.edges) {
    if (!scratch.hasNode(e.source) || !scratch.hasNode(e.target) || e.source === e.target) continue;
    scratch.addEdge(e.source, e.target);
  }
  seedCircle(scratch);
  if (scratch.order > 1 && scratch.order <= EXPAND_SYNC_LAYOUT_CAP) {
    forceAtlas2.assign(scratch, { iterations: EXPAND_FA2_ITERATIONS, settings: fa2Settings(scratch) });
    noverlap.assign(scratch, { maxIterations: EXPAND_NOVERLAP_ITERATIONS, settings: NOVERLAP_SETTINGS });
    // A container's children can themselves be a fragmented graph (multiple
    // disconnected clusters) -- same gap `separateComponents` already closes
    // for the top-level layout, otherwise unrelated child clusters can land
    // coincident. Runs pre-rescale, in the scratch graph's own FA2-native
    // coordinate scale (same as `layoutForceAtlas2`'s call site), so the
    // default `COMPONENT_MIN_GAP` applies unchanged -- the subsequent
    // `scale`/`centerX`/`centerY` step below rescales everything, separated
    // clusters included, into the fixed-radius circle around the parent.
    separateComponents(scratch);
  }

  let minX = Infinity;
  let maxX = -Infinity;
  let minY = Infinity;
  let maxY = -Infinity;
  scratch.forEachNode((_, a) => {
    minX = Math.min(minX, a.x as number);
    maxX = Math.max(maxX, a.x as number);
    minY = Math.min(minY, a.y as number);
    maxY = Math.max(maxY, a.y as number);
  });
  const span = Math.max(1, maxX - minX, maxY - minY);
  const scale = (radius * 2) / span;
  const centerX = (minX + maxX) / 2;
  const centerY = (minY + maxY) / 2;

  const childIds: string[] = [];
  for (const n of children.nodes) {
    if (!scratch.hasNode(n.id)) continue; // collided with an existing top-level node id
    const family: Family = familyOf(n.family);
    const degree = n.degree ?? 0;
    const sx = scratch.getNodeAttribute(n.id, "x") as number;
    const sy = scratch.getNodeAttribute(n.id, "y") as number;
    graph.addNode(n.id, {
      label: n.label,
      baseLabel: n.label,
      rawId: n.id,
      nodeId: n.node_id ?? null,
      kind: n.type ?? "module",
      family,
      shape: shapeOf(n.type),
      degree,
      memberCount: n.members?.length ?? 0,
      role: n.role ?? null,
      x: parentX + (sx - centerX) * scale,
      y: parentY + (sy - centerY) * scale,
      // Smaller than a top-level node of the same degree -- this is a
      // zoomed-in cluster inside another node's former footprint, not a peer
      // of the containers still shown around it.
      size: Math.max(2, nodeSize(degree, maxDegree) * 0.55),
      type: shapeOf(n.type),
      pinned: false,
      fixed: false,
      expandedParent: parentId,
      rung: opts?.rung ?? null,
    });
    childIds.push(n.id);
  }

  const edgeIds: string[] = [];
  for (const e of children.edges) {
    if (!graph.hasNode(e.source) || !graph.hasNode(e.target) || e.source === e.target) continue;
    const count = e.count ?? 1;
    const key = graph.addEdge(e.source, e.target, {
      kind: e.kind,
      confidence: e.confidence ?? null,
      count,
      targetFamily: graph.getNodeAttribute(e.target, "family") as Family,
      size: edgeWidth(e.confidence),
      type: "arrow",
      expandedParent: parentId,
    });
    edgeIds.push(key);
  }

  const parentOriginal = {
    size: graph.getNodeAttribute(parentId, "size") as number,
    label: graph.getNodeAttribute(parentId, "label") as string,
    baseLabel: graph.getNodeAttribute(parentId, "baseLabel") as string,
    forceLabel: graph.getNodeAttribute(parentId, "forceLabel"),
  };
  // Not `hidden: true` -- a hidden node's edges are hidden too (Sigma), which
  // would drop this container's real aggregated edges to its siblings.
  // Shrunk to a near-invisible anchor point instead, label cleared (both
  // `label` and `baseLabel` -- the node reducer always renders off
  // `baseLabel`, never the raw `label` attribute) so it doesn't overlap the
  // cluster now centred on it.
  graph.mergeNodeAttributes(parentId, {
    size: Math.max(1.5, parentOriginal.size * 0.2),
    label: "",
    baseLabel: "",
    forceLabel: false,
    expandedInto: true,
  });

  return { childIds, edgeIds, parentOriginal };
}

/** Undoes {@link expandContainerInPlace}: drops every injected child node/edge
 * and restores the parent's original size/label. Safe to call after the
 * graph itself has already been torn down/rebuilt (every mutation is guarded
 * by `hasNode`/`hasEdge`). */
export function collapseContainerInPlace(graph: Graph, parentId: string, expanded: ExpandedChildren): void {
  for (const id of expanded.edgeIds) if (graph.hasEdge(id)) graph.dropEdge(id);
  for (const id of expanded.childIds) if (graph.hasNode(id)) graph.dropNode(id);
  if (graph.hasNode(parentId)) {
    graph.mergeNodeAttributes(parentId, {
      size: expanded.parentOriginal.size,
      label: expanded.parentOriginal.label,
      baseLabel: expanded.parentOriginal.baseLabel,
      forceLabel: expanded.parentOriginal.forceLabel,
      expandedInto: false,
    });
  }
}

/**
 * §4's "fit to viewport after layout -- non-negotiable". Sigma normalises
 * node positions into a unit box, so the fix is not a bounding-box walk but
 * backing the camera off enough that the outermost *labels* clear the frame
 * too. Ratio 1 exactly touches the extreme nodes, which is what clipped them.
 */
export function fitToViewport(sigma: Sigma, padding = 1.18): void {
  sigma.getCamera().setState({ x: 0.5, y: 0.5, ratio: padding, angle: 0 });
}
