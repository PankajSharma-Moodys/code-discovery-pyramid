import { describe, expect, it, vi } from "vitest";
import Graph from "graphology";
import forceAtlas2 from "graphology-layout-forceatlas2";

// `graphLayout.ts` pulls in `@sigma/edge-curve` (for `buildGraph`'s parallel-
// edge indexing) which loads sigma's real WebGL renderer at module scope --
// undefined outside a browser (`WebGL2RenderingContext`). Neither function
// under test here (`layoutRanked`/`layoutForceAtlas2`) touches edge-curve,
// so stub it out rather than reaching for a browser/jsdom-with-WebGL test
// environment this project doesn't otherwise need.
vi.mock("@sigma/edge-curve", () => ({ indexParallelEdgesIndex: vi.fn() }));

const {
  layoutForceAtlas2,
  layoutRanked,
  buildGraph,
  persistPositions,
  expandContainerInPlace,
  collapseContainerInPlace,
  EXPAND_RADIUS,
  NESTED_RADIUS_FACTOR,
} = await import("./graphLayout.ts");
const { getCachedPositions, setCachedPositions } = await import("./positionCache.ts");

/**
 * Gate before touching `graphLayout.ts`'s dagre jitter or noverlap tuning
 * (`RESEARCH_PAIN_POINTS.md`). The jitter fix's only existing evidence was an
 * inline comment claiming "verified via a 7-node chain" -- this repo's own
 * real L2 graph is 353 nodes (`api/hooks.ts`'s comment), an order of
 * magnitude past that. These tests run the same code path at that scale
 * instead of trusting the comment.
 */

function addChain(graph: Graph, n: number): void {
  for (let i = 0; i < n; i++) graph.addNode(`n${i}`, { x: 0, y: 0 });
  for (let i = 0; i < n - 1; i++) graph.addEdge(`n${i}`, `n${i + 1}`);
}

/** A wide, branchy tree -- the shape most likely to stress FA2+noverlap's
 * anti-overlap pass, as distinct from the single-file-chain shape above that
 * stresses dagre's single-node-rank jitter. */
function addFanOutTree(graph: Graph, n: number, branching: number): void {
  graph.addNode("root", { x: 0, y: 0 });
  const queue = ["root"];
  let created = 1;
  while (created < n && queue.length > 0) {
    const parent = queue.shift()!;
    for (let i = 0; i < branching && created < n; i++) {
      const id = `n${created}`;
      graph.addNode(id, { x: 0, y: 0 });
      graph.addEdge(parent, id);
      queue.push(id);
      created += 1;
    }
  }
}

function positions(graph: Graph): { x: number; y: number }[] {
  const pts: { x: number; y: number }[] = [];
  graph.forEachNode((_node, attrs) => pts.push({ x: attrs.x as number, y: attrs.y as number }));
  return pts;
}

function spread(pts: { x: number; y: number }[]): { width: number; height: number } {
  const xs = pts.map((p) => p.x);
  const ys = pts.map((p) => p.y);
  return { width: Math.max(...xs) - Math.min(...xs), height: Math.max(...ys) - Math.min(...ys) };
}

function minPairwiseDistance(pts: { x: number; y: number }[]): number {
  let min = Infinity;
  for (let i = 0; i < pts.length; i++) {
    for (let j = i + 1; j < pts.length; j++) {
      const dx = pts[i].x - pts[j].x;
      const dy = pts[i].y - pts[j].y;
      min = Math.min(min, Math.hypot(dx, dy));
    }
  }
  return min;
}

const REAL_L2_SCALE = 353;

describe("layoutRanked at real scale", () => {
  it("does not collapse a long single-node-rank chain onto one x (the dead-straight-line bug)", () => {
    const graph = new Graph({ multi: true, type: "directed" });
    addChain(graph, REAL_L2_SCALE);

    const start = performance.now();
    layoutRanked(graph);
    const durationMs = performance.now() - start;

    const pts = positions(graph);
    const distinctX = new Set(pts.map((p) => Math.round(p.x))).size;
    const { width } = spread(pts);

    // Every node in this graph is sole-in-its-rank by construction (a chain),
    // so this is exactly the case the jitter fix targets. Before the fix,
    // the comment states every node landed at the same x.
    expect(distinctX).toBeGreaterThan(1);
    expect(width).toBeGreaterThan(50);
    // Sanity bound, not a strict perf assertion -- dagre ranking is meant to
    // stay well under a second even at this scale so it doesn't stack with
    // the "spins forever" bug this doc also flags.
    expect(durationMs).toBeLessThan(5000);
  });

  it("spreads a branchy tree across both axes, not just one", () => {
    const graph = new Graph({ multi: true, type: "directed" });
    addFanOutTree(graph, REAL_L2_SCALE, 6);

    layoutRanked(graph);

    const pts = positions(graph);
    const { width, height } = spread(pts);
    expect(width).toBeGreaterThan(50);
    expect(height).toBeGreaterThan(50);
  });

  it("keeps a hub-dominated graph's bbox aspect under control (WEB_REDESIGN_RESEARCH.md §3.3)", () => {
    // One hub with ~60 direct children -- a single rank of 60 nodes under the
    // default `rankdir: "TB"` bias, the shape that measured 284:1 on the real
    // `unified-store` L2 graph.
    const graph = new Graph({ multi: true, type: "directed" });
    addFanOutTree(graph, 61, 60);

    layoutRanked(graph);

    const pts = positions(graph);
    const { width, height } = spread(pts);
    const aspect = Math.max(width, height) / Math.min(width, height);
    expect(aspect).toBeLessThanOrEqual(3);
  });
});

describe("layoutForceAtlas2 + noverlap at real scale", () => {
  it("keeps nodes from stacking on a dense fan-out graph", () => {
    const graph = new Graph({ multi: true, type: "directed" });
    addFanOutTree(graph, REAL_L2_SCALE, 8);
    graph.forEachNode((node) => graph.setNodeAttribute(node, "size", 4));

    const start = performance.now();
    layoutForceAtlas2(graph);
    const durationMs = performance.now() - start;

    const pts = positions(graph);
    const minDist = minPairwiseDistance(pts);
    const { width, height } = spread(pts);

    // noverlap's whole job is "no two circles touch" -- a positive margin
    // between the two closest nodes is the direct check for that, not just
    // an overall bounding-box spread (which a single stacked pair wouldn't
    // move much).
    expect(minDist).toBeGreaterThan(0);
    expect(width).toBeGreaterThan(0);
    expect(height).toBeGreaterThan(0);
    expect(durationMs).toBeLessThan(15000);
  });

  it("leaves a fixed node's position untouched (WEB_REDESIGN_RESEARCH.md §3.3 pin/lock)", () => {
    // Exercises `graphology-layout-forceatlas2`'s own `fixed` attribute
    // contract directly, seeded the same way `AtlasCanvas`'s real pin path
    // does (`buildGraph`'s cache application, then `layoutForceAtlas2Async`
    // -- which, unlike the sync `layoutForceAtlas2` helper above, never
    // reseeds a node that already has a position).
    const graph = new Graph({ multi: true, type: "directed" });
    addFanOutTree(graph, 30, 4);
    graph.forEachNode((node) => graph.setNodeAttribute(node, "size", 4));
    graph.forEachNode((node) => {
      if (node !== "root") {
        const angle = Math.random() * 2 * Math.PI;
        graph.setNodeAttribute(node, "x", Math.cos(angle) * 200);
        graph.setNodeAttribute(node, "y", Math.sin(angle) * 200);
      }
    });
    graph.setNodeAttribute("root", "x", 123);
    graph.setNodeAttribute("root", "y", -45);
    graph.setNodeAttribute("root", "fixed", true);

    forceAtlas2.assign(graph, { iterations: 100, settings: forceAtlas2.inferSettings(graph) });

    expect(graph.getNodeAttribute("root", "x")).toBe(123);
    expect(graph.getNodeAttribute("root", "y")).toBe(-45);
  });
});

function nearestNeighborDistances(pts: { x: number; y: number }[]): number[] {
  return pts.map((p, i) => {
    let min = Infinity;
    for (let j = 0; j < pts.length; j++) {
      if (i === j) continue;
      min = Math.min(min, Math.hypot(p.x - pts[j].x, p.y - pts[j].y));
    }
    return min;
  });
}

function percentile(sorted: number[], p: number): number {
  const idx = Math.min(sorted.length - 1, Math.floor(p * sorted.length));
  return sorted[idx];
}

/** A fragmented graph shaped like the real 353-node L2 repo graph (85
 * disconnected components: one big connected core plus many small,
 * mutually-unreachable clusters -- `import`/`call` graphs are like this
 * because plenty of modules only talk to a shared core, never to each
 * other). This is the fixture that exposed the actual "clubbed vs far
 * apart" defect: FA2's shared gravity center governs *inter*-component
 * placement, but nothing enforced a minimum gap between components, only
 * within one. */
function addFragmentedGraph(graph: Graph, componentSizes: number[]): void {
  componentSizes.forEach((size, ci) => {
    const prefix = `c${ci}_`;
    for (let i = 0; i < size; i++) graph.addNode(`${prefix}${i}`, { x: 0, y: 0, size: 4 });
    // Star-shaped internally so every component is connected but not dense.
    for (let i = 1; i < size; i++) graph.addEdge(`${prefix}0`, `${prefix}${i}`);
  });
}

describe("layoutForceAtlas2 inter-component spacing (fixes clumped-vs-far-apart nodes)", () => {
  it("keeps disconnected components' centroid spacing within a bounded ratio, not 65x apart", () => {
    // Mirrors the real repo's own L2 graph shape: one big component plus a
    // long tail of small ones (real top5 sizes were 171,7,6,4,4 across 85
    // components). Before `separateComponents` existed, this measured
    // min=1.2 max=80.8 ratio=65.3 on the real graph; after, min=110.2
    // max=654.8 ratio=5.9.
    const graph = new Graph({ multi: true, type: "directed" });
    const sizes = [40, 7, 6, 4, 4, 3, 3, 2, 2, 2, 2, 2, 2, 2, 2];
    addFragmentedGraph(graph, sizes);

    layoutForceAtlas2(graph);

    const idsInOrder: string[] = [];
    graph.forEachNode((id) => idsInOrder.push(id));
    const pts = positions(graph);
    const centroids = new Map<string, { x: number; y: number; n: number }>();
    idsInOrder.forEach((id, i) => {
      const compKey = id.split("_")[0];
      const c = centroids.get(compKey) ?? { x: 0, y: 0, n: 0 };
      c.x += pts[i].x;
      c.y += pts[i].y;
      c.n += 1;
      centroids.set(compKey, c);
    });
    const centroidPts = [...centroids.values()].map((c) => ({ x: c.x / c.n, y: c.y / c.n }));
    const cnnd = nearestNeighborDistances(centroidPts).sort((a, b) => a - b);
    const ratio = cnnd[cnnd.length - 1] / Math.max(0.001, cnnd[0]);

    // The unfixed baseline measured 65.3x on the real graph; 10x leaves
    // headroom for fixture-shape variance while still catching a
    // regression back to "ungoverned" inter-component spacing.
    expect(ratio).toBeLessThan(10);

    // And within a single component, node-level evenness must stay intact
    // -- `separateComponents` only rigidly translates each component, so it
    // must not distort the FA2 layout it already computed internally.
    const bigCompPts = idsInOrder
      .map((id, i) => ({ id, i }))
      .filter(({ id }) => id.startsWith("c0_"))
      .map(({ i }) => pts[i]);
    // Star-shaped internally (one hub + leaves), so nnd variance is higher
    // than a fanout tree by construction -- the hub-and-pendants fixture
    // above measured p90/p10 up to 3.26 for the same shape; 5 leaves margin
    // while still catching a real regression back to "ungoverned" spacing.
    const nnd = nearestNeighborDistances(bigCompPts).sort((a, b) => a - b);
    expect(percentile(nnd, 0.9) / Math.max(0.001, percentile(nnd, 0.1))).toBeLessThan(5);
  });
});

describe("buildGraph position caching (positionCache.ts)", () => {
  it("re-applies a pinned cached position after a ranked (dagre) rebuild", () => {
    const cacheKey = { repoKey: "test-repo:", level: "L2", scope: null };
    setCachedPositions(cacheKey.repoKey, cacheKey.level, cacheKey.scope, {
      a: { x: 777, y: -333, pinned: true },
    });

    const graph = buildGraph(
      {
        nodes: [
          { id: "a", label: "a" },
          { id: "b", label: "b" },
        ],
        edges: [{ source: "a", target: "b", kind: "calls" }],
      },
      true,
      cacheKey,
    );

    expect(graph.getNodeAttribute("a", "x")).toBe(777);
    expect(graph.getNodeAttribute("a", "y")).toBe(-333);
    expect(graph.getNodeAttribute("a", "fixed")).toBe(true);
  });

  it("persistPositions writes every node's current position and pin state back to the cache", () => {
    const cacheKey = { repoKey: "test-repo:", level: "P2", scope: null };
    const graph = new Graph({ multi: true, type: "directed" });
    graph.addNode("x", { x: 10, y: 20, pinned: false });
    graph.addNode("y", { x: 30, y: 40, pinned: true });

    persistPositions(graph, cacheKey);

    const stored = getCachedPositions(cacheKey.repoKey, cacheKey.level, cacheKey.scope);
    expect(stored.x).toEqual({ x: 10, y: 20, pinned: false });
    expect(stored.y).toEqual({ x: 30, y: 40, pinned: true });
  });
});

describe("expand-in-place (WEB_REDESIGN_RESEARCH.md §3.2)", () => {
  function buildContainerGraph() {
    return buildGraph(
      {
        nodes: [
          { id: "sql-pool", label: "sql-pool", degree: 3 },
          { id: "service-api", label: "service-api", degree: 2 },
        ],
        edges: [{ source: "sql-pool", target: "service-api", kind: "call", count: 4 }],
      },
      true,
    );
  }

  it("adds every child node/edge, positioned inside the parent's former footprint", () => {
    const graph = buildContainerGraph();
    graph.setNodeAttribute("sql-pool", "x", 500);
    graph.setNodeAttribute("sql-pool", "y", -200);
    const originalSize = graph.getNodeAttribute("sql-pool", "size") as number;

    const children = {
      nodes: [
        { id: "a.py", label: "a.py", degree: 1 },
        { id: "b.py", label: "b.py", degree: 2 },
        { id: "c.py", label: "c.py", degree: 1 },
      ],
      edges: [
        { source: "a.py", target: "b.py", kind: "call" },
        { source: "b.py", target: "c.py", kind: "call" },
      ],
    };

    const expanded = expandContainerInPlace(graph, "sql-pool", children);

    expect(expanded.childIds.sort()).toEqual(["a.py", "b.py", "c.py"]);
    expect(expanded.edgeIds).toHaveLength(2);
    for (const id of expanded.childIds) {
      expect(graph.hasNode(id)).toBe(true);
      // Every child lands within a bounded radius of where the parent used
      // to sit -- this is the "expand in place" contract, not a relayout of
      // the whole map.
      const dx = (graph.getNodeAttribute(id, "x") as number) - 500;
      const dy = (graph.getNodeAttribute(id, "y") as number) - (-200);
      expect(Math.hypot(dx, dy)).toBeLessThan(300);
    }

    // The parent shrinks to a near-invisible edge anchor but is not removed
    // (its own aggregated edges to sibling containers must keep drawing --
    // a `hidden: true` node would silently hide those edges too).
    expect(graph.getNodeAttribute("sql-pool", "size")).toBeLessThan(originalSize * 0.3);
    expect(graph.getNodeAttribute("sql-pool", "baseLabel")).toBe("");
    expect(graph.hasNode("sql-pool")).toBe(true);
    expect(graph.hasEdge("sql-pool", "service-api")).toBe(true);
  });

  it("collapse restores the parent and drops every injected child, even after other edits", () => {
    const graph = buildContainerGraph();
    const originalSize = graph.getNodeAttribute("sql-pool", "size") as number;
    const originalLabel = graph.getNodeAttribute("sql-pool", "baseLabel") as string;

    const expanded = expandContainerInPlace(graph, "sql-pool", {
      nodes: [{ id: "a.py", label: "a.py" }],
      edges: [],
    });
    collapseContainerInPlace(graph, "sql-pool", expanded);

    expect(graph.hasNode("a.py")).toBe(false);
    expect(graph.getNodeAttribute("sql-pool", "size")).toBe(originalSize);
    expect(graph.getNodeAttribute("sql-pool", "baseLabel")).toBe(originalLabel);
  });

  it("separates a container's children when they form multiple disconnected clusters", () => {
    const graph = buildContainerGraph();
    graph.setNodeAttribute("sql-pool", "x", 0);
    graph.setNodeAttribute("sql-pool", "y", 0);

    // Two disconnected clusters -- nothing here shares an edge across the
    // "cluster1"/"cluster2" split, the exact shape `separateComponents`
    // exists to keep apart (previously only applied to the top-level graph,
    // not this scratch layout).
    const children = {
      nodes: [
        { id: "cluster1-a", label: "cluster1-a" },
        { id: "cluster1-b", label: "cluster1-b" },
        { id: "cluster2-a", label: "cluster2-a" },
        { id: "cluster2-b", label: "cluster2-b" },
      ],
      edges: [
        { source: "cluster1-a", target: "cluster1-b", kind: "call" },
        { source: "cluster2-a", target: "cluster2-b", kind: "call" },
      ],
    };

    const expanded = expandContainerInPlace(graph, "sql-pool", children);
    expect(expanded.childIds.sort()).toEqual(["cluster1-a", "cluster1-b", "cluster2-a", "cluster2-b"]);

    const centroid = (ids: string[]) => {
      let x = 0;
      let y = 0;
      for (const id of ids) {
        x += graph.getNodeAttribute(id, "x") as number;
        y += graph.getNodeAttribute(id, "y") as number;
      }
      return { x: x / ids.length, y: y / ids.length };
    };
    const c1 = centroid(["cluster1-a", "cluster1-b"]);
    const c2 = centroid(["cluster2-a", "cluster2-b"]);
    // Not a tight bound (the whole thing is rescaled into a small fixed
    // radius around the parent) -- just confirms the two clusters don't land
    // on top of each other, the failure mode without `separateComponents`.
    expect(Math.hypot(c2.x - c1.x, c2.y - c1.y)).toBeGreaterThan(1);
  });

  it("collapse is a safe no-op against a graph that no longer has the parent", () => {
    const graph = buildContainerGraph();
    const expanded = expandContainerInPlace(graph, "sql-pool", {
      nodes: [{ id: "a.py", label: "a.py" }],
      edges: [],
    });
    graph.dropNode("sql-pool");

    expect(() => collapseContainerInPlace(graph, "sql-pool", expanded)).not.toThrow();
  });

  it("skips a child id that collides with an existing top-level node", () => {
    const graph = buildContainerGraph();
    const expanded = expandContainerInPlace(graph, "sql-pool", {
      // "service-api" already exists as a sibling container at this rung --
      // must not be clobbered by a same-named child.
      nodes: [{ id: "service-api", label: "service-api (child)" }],
      edges: [],
    });

    expect(expanded.childIds).toEqual([]);
    expect(graph.getNodeAttribute("service-api", "label")).toBe("service-api");
  });

  it("expands two sibling containers independently, without either's children bleeding into the other", () => {
    const graph = buildContainerGraph();
    graph.setNodeAttribute("sql-pool", "x", -500);
    graph.setNodeAttribute("sql-pool", "y", 0);
    graph.setNodeAttribute("service-api", "x", 500);
    graph.setNodeAttribute("service-api", "y", 0);

    const left = expandContainerInPlace(graph, "sql-pool", {
      nodes: [{ id: "a.py", label: "a.py" }],
      edges: [],
    });
    const right = expandContainerInPlace(graph, "service-api", {
      nodes: [{ id: "b.py", label: "b.py" }],
      edges: [],
    });

    expect(left.childIds).toEqual(["a.py"]);
    expect(right.childIds).toEqual(["b.py"]);
    // Each child stays bounded around its own parent, not the other's.
    expect(Math.hypot(
      (graph.getNodeAttribute("a.py", "x") as number) - -500,
      graph.getNodeAttribute("a.py", "y") as number,
    )).toBeLessThan(300);
    expect(Math.hypot(
      (graph.getNodeAttribute("b.py", "x") as number) - 500,
      graph.getNodeAttribute("b.py", "y") as number,
    )).toBeLessThan(300);

    // Collapsing one leaves the other fully intact -- independent teardown.
    collapseContainerInPlace(graph, "sql-pool", left);
    expect(graph.hasNode("a.py")).toBe(false);
    expect(graph.hasNode("b.py")).toBe(true);
  });

  it("nests a child expansion inside a smaller radius and stamps it with its own rung", () => {
    const graph = buildContainerGraph();
    graph.setNodeAttribute("sql-pool", "x", 0);
    graph.setNodeAttribute("sql-pool", "y", 0);

    const outer = expandContainerInPlace(graph, "sql-pool", {
      nodes: [{ id: "pkg-a", label: "pkg-a" }],
      edges: [],
    });
    expect(outer.childIds).toEqual(["pkg-a"]);

    // "pkg-a" is itself a container -- expand its children one level deeper,
    // at a shrunk radius, the way `AtlasCanvas`'s apply pass does for depth 1.
    const nested = expandContainerInPlace(
      graph,
      "pkg-a",
      { nodes: [{ id: "mod.py", label: "mod.py" }], edges: [] },
      { rung: "L2", radius: EXPAND_RADIUS * NESTED_RADIUS_FACTOR },
    );

    expect(nested.childIds).toEqual(["mod.py"]);
    expect(graph.getNodeAttribute("mod.py", "rung")).toBe("L2");
    const dx = (graph.getNodeAttribute("mod.py", "x") as number) - (graph.getNodeAttribute("pkg-a", "x") as number);
    const dy = (graph.getNodeAttribute("mod.py", "y") as number) - (graph.getNodeAttribute("pkg-a", "y") as number);
    // Bounded by the *nested* radius, not the full-size one -- a depth-1
    // cluster should read as "smaller, inside" its ancestor's hull.
    expect(Math.hypot(dx, dy)).toBeLessThan(EXPAND_RADIUS);
  });

  it("collapsing a nested expansion after its ancestor already collapsed is a safe no-op", () => {
    const graph = buildContainerGraph();
    const outer = expandContainerInPlace(graph, "sql-pool", {
      nodes: [{ id: "pkg-a", label: "pkg-a" }],
      edges: [],
    });
    const nested = expandContainerInPlace(
      graph,
      "pkg-a",
      { nodes: [{ id: "mod.py", label: "mod.py" }], edges: [] },
      { rung: "L2", radius: EXPAND_RADIUS * NESTED_RADIUS_FACTOR },
    );

    // Simulate the deepest-first collapse ordering the apply/collapse effect
    // commits to, then a second collapse call for the (already-vanished)
    // nested id, as would happen if a stale ref entry were ever processed
    // out of order -- `collapseContainerInPlace`'s own `hasNode` guards must
    // make this safe rather than throwing.
    collapseContainerInPlace(graph, "pkg-a", nested);
    collapseContainerInPlace(graph, "sql-pool", outer);
    expect(() => collapseContainerInPlace(graph, "pkg-a", nested)).not.toThrow();

    expect(graph.hasNode("mod.py")).toBe(false);
    expect(graph.hasNode("pkg-a")).toBe(false);
  });
});
