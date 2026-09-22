import * as dagre from "@dagrejs/dagre";
import { AnimatePresence, motion } from "framer-motion";
import forceAtlas2 from "graphology-layout-forceatlas2";
import Graph from "graphology";
import { useEffect, useMemo, useRef, useState } from "react";
import Sigma from "sigma";
import { useGraph, useNodesConfidence } from "../api/hooks.ts";
import type { Altitude } from "../api/nodeId.ts";
import { useAtlasStore } from "../store/atlasStore.ts";
import { confidenceColor } from "../theme/confidence.ts";

const STRUCTURE_NODE_COLOR = "#8b93a1";
const STRUCTURE_EDGE_COLOR = "#262c36";

/** `WEB_RESEARCH.md` §3's Divergence lens: only `_build_graph_l3`
 * (`web/api/app.py:476-489`) tags edges `declared`/`observed`/`both` --
 * other altitudes have no divergence signal, so the lens is a no-op there
 * (handled by falling back to the structure color when `kind` isn't one of
 * these three). Edge size is the redundant non-color channel (glyph/dash
 * stroke would need a custom sigma edge program, out of scope this pass;
 * flagged in the plan) -- `both` renders thickest since it's the most
 * corroborated case. */
const DIVERGENCE_EDGE_COLOR: Record<string, string> = {
  both: "var(--atlas-verified)",
  declared: "var(--atlas-inferred)",
  observed: "var(--atlas-unknown)",
};
const DIVERGENCE_EDGE_SIZE: Record<string, number> = { both: 2, declared: 1.4, observed: 1.4 };

/** Small glyph suffix on the node label is the non-color redundancy for the
 * Confidence lens (`WEB_RESEARCH.md` §5: colour must never carry epistemic
 * meaning alone). Matches `tokens.css`'s documented glyphs per bucket. */
const CONFIDENCE_GLYPH: Record<string, string> = {
  high: " ✓",
  medium: " ~",
  low: " ?",
  contested: " ✕",
};
const CONFIDENCE_SIZE: Record<string, number> = { high: 8, medium: 7, low: 6, contested: 6, unreviewed: 5 };

function resolveCssColor(value: string): string {
  if (!value.startsWith("var(")) return value;
  const varName = value.slice(4, -1).trim();
  return getComputedStyle(document.documentElement).getPropertyValue(varName).trim() || value;
}

const ALTITUDES: Altitude[] = ["L3", "L2", "L1"];

/** Dagre ranks straight from the same dependency edges `/api/graph` already
 * returns -- `graph.levels` (the server's own topological layering) isn't
 * fed into dagre directly since dagre has no public per-node rank-pinning
 * API; letting dagre rank a DAG from its edges reproduces the same
 * layering for any node with an edge, which is every non-isolated module.
 * Isolated nodes (no edges) fall into dagre's default rank 0, which is an
 * honest "unconstrained" position, not a wrong one. */
function layoutL3(graph: Graph): void {
  const g = new dagre.graphlib.Graph();
  g.setGraph({ rankdir: "TB", nodesep: 60, ranksep: 90 });
  g.setDefaultEdgeLabel(() => ({}));
  graph.forEachNode((node) => g.setNode(node, { width: 140, height: 40 }));
  graph.forEachEdge((_edge, _attrs, source, target) => {
    if (source !== target) g.setEdge(source, target);
  });
  dagre.layout(g);
  g.nodes().forEach((node) => {
    const { x, y } = g.node(node);
    graph.setNodeAttribute(node, "x", x);
    graph.setNodeAttribute(node, "y", y);
  });
}

const FA2_ITERATIONS = 200;

function layoutForceAtlas2(graph: Graph): void {
  graph.forEachNode((node) => {
    graph.setNodeAttribute(node, "x", Math.random() * 1000);
    graph.setNodeAttribute(node, "y", Math.random() * 1000);
  });
  const settings = forceAtlas2.inferSettings(graph);
  forceAtlas2.assign(graph, { iterations: FA2_ITERATIONS, settings });
}

function buildGraph(
  data: {
    nodes: { id: string; label: string }[];
    edges: { source: string; target: string; kind?: string }[];
  },
  level: Altitude,
): Graph {
  const graph = new Graph({ multi: true, type: "directed" });
  for (const node of data.nodes) {
    graph.addNode(node.id, { label: node.label, baseLabel: node.label, x: 0, y: 0, size: 8 });
  }
  for (const edge of data.edges) {
    if (!graph.hasNode(edge.source) || !graph.hasNode(edge.target)) continue;
    if (edge.source === edge.target) continue;
    graph.addEdge(edge.source, edge.target, { size: 1, kind: edge.kind });
  }
  if (level === "L3") layoutL3(graph);
  else layoutForceAtlas2(graph);
  return graph;
}

function useFpsOverlay(enabled: boolean): number {
  const [fps, setFps] = useState(0);
  useEffect(() => {
    if (!enabled) return;
    let frames = 0;
    let lastSampleAt = performance.now();
    let raf = 0;
    const tick = () => {
      frames += 1;
      const now = performance.now();
      if (now - lastSampleAt >= 500) {
        setFps(Math.round((frames * 1000) / (now - lastSampleAt)));
        frames = 0;
        lastSampleAt = now;
      }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [enabled]);
  return fps;
}

/** Wheel gesture is only treated as an altitude change when the pointer is
 * over the canvas *and* the canvas has focus (`WEB_RESEARCH.md` §3 rule 3)
 * -- otherwise an incidental page-scroll wheel event while the mouse
 * happens to pass over the canvas would silently change altitude. A
 * `ctrlKey` wheel event is a trackpad pinch and is left alone so sigma's
 * native camera zoom handles it. */
export function AtlasCanvas() {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const sigmaRef = useRef<Sigma | null>(null);
  const [hasFocus, setHasFocus] = useState(false);

  const altitude = useAtlasStore((s) => s.altitude);
  const scope = useAtlasStore((s) => s.scope);
  const descend = useAtlasStore((s) => s.descend);
  const ascend = useAtlasStore((s) => s.ascend);
  const jumpTo = useAtlasStore((s) => s.jumpTo);
  const hoverNode = useAtlasStore((s) => s.hoverNode);
  const selectNode = useAtlasStore((s) => s.selectNode);
  const accumulateWheel = useAtlasStore((s) => s.accumulateWheel);
  const lens = useAtlasStore((s) => s.lens);
  const diffHighlight = useAtlasStore((s) => s.diffHighlight);

  const { data, isLoading, error } = useGraph(altitude, scope);

  const confidenceRawIds = useMemo(
    () => (lens === "confidence" ? data?.nodes.map((n) => n.id) ?? [] : []),
    [lens, data],
  );
  const confidenceById = useNodesConfidence(altitude, confidenceRawIds);

  const graph = useMemo(() => {
    if (!data) return null;
    return buildGraph(data, altitude);
  }, [data, altitude]);

  useEffect(() => {
    if (!graph || !containerRef.current) return;
    const sigma = new Sigma(graph, containerRef.current, {
      defaultNodeColor: STRUCTURE_NODE_COLOR,
      defaultEdgeColor: STRUCTURE_EDGE_COLOR,
      labelColor: { color: "#d7dbe0" },
    });
    sigmaRef.current = sigma;

    sigma.on("enterNode", ({ node }) => hoverNode(node));
    sigma.on("leaveNode", () => hoverNode(null));
    sigma.on("clickNode", ({ node }) => selectNode(node));
    sigma.on("doubleClickNode", ({ node, event }) => {
      event.preventSigmaDefault();
      descend(node);
    });
    sigma.on("clickStage", () => selectNode(null));

    return () => {
      sigma.kill();
      sigmaRef.current = null;
    };
  }, [graph, hoverNode, selectNode, descend]);

  /** Pure recolor: mutates the *existing* `graph`'s attributes and asks
   * sigma to redraw -- never rebuilds `graph` or the `Sigma` instance, so
   * switching lenses cannot re-trigger layout (`WEB_RESEARCH.md` §3,
   * `PLAN.md`'s acceptance test). */
  useEffect(() => {
    if (!graph) return;

    if (lens === "structure") {
      graph.forEachNode((node) => {
        graph.removeNodeAttribute(node, "color");
        graph.setNodeAttribute(node, "size", 8);
        graph.setNodeAttribute(node, "label", graph.getNodeAttribute(node, "baseLabel"));
      });
      graph.forEachEdge((edge) => {
        graph.removeEdgeAttribute(edge, "color");
        graph.setEdgeAttribute(edge, "size", 1);
      });
    } else if (lens === "divergence") {
      graph.forEachNode((node) => {
        graph.removeNodeAttribute(node, "color");
        graph.setNodeAttribute(node, "size", 8);
        graph.setNodeAttribute(node, "label", graph.getNodeAttribute(node, "baseLabel"));
      });
      graph.forEachEdge((edge) => {
        const kind = graph.getEdgeAttribute(edge, "kind") as string | undefined;
        const color = kind && DIVERGENCE_EDGE_COLOR[kind];
        graph.setEdgeAttribute(edge, "color", color ? resolveCssColor(color) : STRUCTURE_EDGE_COLOR);
        graph.setEdgeAttribute(edge, "size", (kind && DIVERGENCE_EDGE_SIZE[kind]) ?? 1);
      });
    } else if (lens === "confidence") {
      graph.forEachNode((node) => {
        const bucket = confidenceById.get(node) ?? "unreviewed";
        const baseLabel = graph.getNodeAttribute(node, "baseLabel") as string;
        graph.setNodeAttribute(node, "color", resolveCssColor(confidenceColor(bucket)));
        graph.setNodeAttribute(node, "size", CONFIDENCE_SIZE[bucket]);
        graph.setNodeAttribute(node, "label", baseLabel + (CONFIDENCE_GLYPH[bucket] ?? ""));
      });
      graph.forEachEdge((edge) => {
        graph.removeEdgeAttribute(edge, "color");
        graph.setEdgeAttribute(edge, "size", 1);
      });
    }

    sigmaRef.current?.refresh();
  }, [graph, lens, confidenceById]);

  /** Time scrubber's pulse/fade: mutates the same mounted graph's node
   * colors/sizes in place (same non-relayout pattern as the lens effect
   * above) whenever `atlasStore.diffHighlight` is set. Only L3 module ids
   * from `/api/diff` line up with this altitude's node ids, so this is a
   * no-op elsewhere; a removed module (gone from the *current* graph by
   * definition) can't be pulsed on it, only added/still-present ones. */
  useEffect(() => {
    if (!graph || altitude !== "L3" || !diffHighlight) return;
    const addedColor = resolveCssColor("var(--atlas-verified)");
    for (const id of diffHighlight.added) {
      if (graph.hasNode(id)) {
        graph.setNodeAttribute(id, "color", addedColor);
        graph.setNodeAttribute(id, "size", 14);
      }
    }
    sigmaRef.current?.refresh();
    return () => {
      if (!graph) return;
      for (const id of diffHighlight.added) {
        if (!graph.hasNode(id)) continue;
        graph.removeNodeAttribute(id, "color");
        graph.setNodeAttribute(id, "size", 8);
      }
      sigmaRef.current?.refresh();
    };
  }, [graph, altitude, diffHighlight]);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const onWheel = (event: WheelEvent) => {
      if (event.ctrlKey || !hasFocus) return;
      event.preventDefault();
      accumulateWheel(event.deltaY);
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") ascend();
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    el.addEventListener("keydown", onKeyDown);
    return () => {
      el.removeEventListener("wheel", onWheel);
      el.removeEventListener("keydown", onKeyDown);
    };
  }, [hasFocus, accumulateWheel, ascend]);

  const fps = useFpsOverlay(import.meta.env.DEV);
  const prefersReducedMotion = useMemo(
    () => window.matchMedia("(prefers-reduced-motion: reduce)").matches,
    [],
  );
  const canvasKey = `${altitude}:${scope ?? ""}`;

  return (
    <div className="relative h-full w-full">
      <div className="absolute left-3 top-3 z-10 flex gap-2 text-sm">
        {ALTITUDES.map((level) => (
          <button
            key={level}
            onClick={() => jumpTo(level)}
            className="rounded px-2 py-1"
            style={{
              background: level === altitude ? "var(--atlas-accent)" : "var(--atlas-bg-2)",
              color: level === altitude ? "#07090c" : "var(--atlas-text-dim)",
              border: "1px solid var(--atlas-border)",
            }}
          >
            {level}
          </button>
        ))}
      </div>
      {import.meta.env.DEV && (
        <div className="absolute right-3 top-3 z-10 rounded bg-black/40 px-2 py-1 font-mono text-xs text-white">
          {fps} fps
        </div>
      )}
      {isLoading && (
        <div className="absolute inset-0 flex items-center justify-center text-sm text-[var(--atlas-text-dim)]">
          loading graph…
        </div>
      )}
      {error && (
        <div className="absolute inset-0 flex items-center justify-center text-sm text-red-400">
          {String(error)}
        </div>
      )}
      {lens === "divergence" && altitude !== "L3" && (
        <div
          className="absolute bottom-3 left-3 z-10 rounded px-2 py-1 text-xs"
          style={{ background: "var(--atlas-bg-2)", color: "var(--atlas-text-dim)", border: "1px solid var(--atlas-border)" }}
        >
          Divergence data is only computed at L3 (module dependency) today.
        </div>
      )}
      <AnimatePresence>
        <motion.div
          key={canvasKey}
          className="absolute inset-0"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: prefersReducedMotion ? 0 : 0.48, ease: [0.2, 0.8, 0.2, 1] }}
        >
          <div
            ref={containerRef}
            tabIndex={0}
            onFocus={() => setHasFocus(true)}
            onBlur={() => setHasFocus(false)}
            className="h-full w-full outline-none"
          />
        </motion.div>
      </AnimatePresence>
    </div>
  );
}
