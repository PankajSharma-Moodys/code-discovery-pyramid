import * as dagre from "@dagrejs/dagre";
import { indexParallelEdgesIndex } from "@sigma/edge-curve";
import Graph from "graphology";
import forceAtlas2 from "graphology-layout-forceatlas2";
import type Sigma from "sigma";
import {
  edgeWidth,
  familyOf,
  nodeSize,
  shapeOf,
  type Family,
} from "../theme/graphEncoding.ts";

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

export function layoutForceAtlas2(graph: Graph): void {
  // Deterministic seeding on a circle rather than `Math.random()`: the same
  // graph then lays out the same way twice, so a lens switch or a refetch
  // doesn't silently reshuffle the map under the user.
  const n = Math.max(1, graph.order);
  let i = 0;
  graph.forEachNode((node) => {
    const angle = (2 * Math.PI * i) / n;
    const radius = 100 + 400 * ((i * 2654435761) % 1000) / 1000;
    graph.setNodeAttribute(node, "x", Math.cos(angle) * radius);
    graph.setNodeAttribute(node, "y", Math.sin(angle) * radius);
    i += 1;
  });

  const inferred = forceAtlas2.inferSettings(graph);
  forceAtlas2.assign(graph, {
    iterations: FA2_ITERATIONS,
    settings: {
      ...inferred,
      linLogMode: true,
      outboundAttractionDistribution: true,
      adjustSizes: true,
      strongGravityMode: true,
      gravity: 1.2,
      scalingRatio: 0.2,
      slowDown: 8,
    },
  });
}

/** Dagre ranks straight from the dependency edges. `nodesep`/`ranksep` scale
 * with the node count so a 6-node L3 doesn't spread across three screens and
 * a 30-node one doesn't overlap -- the old fixed 60/90 did both.
 *
 * `ranksep` is deliberately ~4x `nodesep`. Sigma scales a graph to fit its
 * longest axis, so a short wide DAG gets letterboxed into a band with dead
 * space above and below it -- which is what the first pass produced. Biasing
 * the layout taller uses the viewport instead of the void. */
export function layoutRanked(graph: Graph): void {
  const g = new dagre.graphlib.Graph();
  const spread = Math.max(0.6, Math.min(1.8, 18 / Math.max(1, graph.order)));
  g.setGraph({ rankdir: "TB", nodesep: 55 * spread, ranksep: 210 * spread, marginx: 40, marginy: 40 });
  g.setDefaultEdgeLabel(() => ({}));
  graph.forEachNode((node) => g.setNode(node, { width: 150, height: 44 }));
  graph.forEachEdge((_edge, _attrs, source, target) => {
    if (source !== target) g.setEdge(source, target);
  });
  dagre.layout(g);
  g.nodes().forEach((node) => {
    const pos = g.node(node);
    if (!pos) return;
    graph.setNodeAttribute(node, "x", pos.x);
    // dagre's y grows downward; flip so rank 0 (entry points) sits at the top
    // of the screen rather than the bottom.
    graph.setNodeAttribute(node, "y", -pos.y);
  });
}

/**
 * Builds the graphology graph with every encoding channel attached as a raw
 * attribute. Nothing here decides a *colour* -- `AtlasCanvas`'s reducers do
 * that per lens, so switching lenses never touches graph identity and never
 * re-triggers layout.
 */
export function buildGraph(data: RawGraph, ranked: boolean): Graph {
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
    });
  }

  for (const edge of data.edges) {
    if (!graph.hasNode(edge.source) || !graph.hasNode(edge.target)) continue;
    if (edge.source === edge.target) continue;
    graph.addEdge(edge.source, edge.target, {
      kind: edge.kind,
      confidence: edge.confidence ?? null,
      count: edge.count ?? 1,
      targetFamily: graph.getNodeAttribute(edge.target, "family") as Family,
      size: edgeWidth(edge.confidence),
      type: "arrow",
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

  if (ranked) layoutRanked(graph);
  else layoutForceAtlas2(graph);

  return graph;
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
