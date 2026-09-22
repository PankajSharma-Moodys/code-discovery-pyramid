import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useMemo, useRef, useState } from "react";
import Sigma from "sigma";
import { useGraph, useNodesConfidence } from "../api/hooks.ts";
import type { Altitude } from "../api/nodeId.ts";
import { useAtlasStore } from "../store/atlasStore.ts";
import { confidenceColor, type ConfidenceBucket } from "../theme/confidence.ts";
import {
  edgeAlpha,
  edgeWidth,
  FAMILY_VAR,
  resolveCssColor,
  SHAPE_ZOOM_THRESHOLD,
  type Family,
} from "../theme/graphEncoding.ts";
import { AltitudeSwitcher } from "./AltitudeSwitcher.tsx";
import { buildGraph, fitToViewport } from "./graphLayout.ts";
import { GraphLegend } from "./GraphLegend.tsx";
import { sigmaSettings } from "./sigmaPrograms.ts";

/** Non-color redundancy for the Confidence lens (`WEB_RESEARCH.md` §5:
 * colour must never carry epistemic meaning alone). Matches `tokens.css`'s
 * documented glyphs per bucket. */
const CONFIDENCE_GLYPH: Record<string, string> = {
  high: " ✓",
  medium: " ~",
  low: " ?",
  contested: " ✕",
};

const DIM_EDGE = "#222834";

/** Edge colour under the Flow lens. Seven channels is more than three hues
 * can hold, so this is the one place the three-family cap is relaxed -- and
 * it is safe precisely because the Flow lens shows *edges* against a legend
 * that is a vertical list, not an all-pairs canvas comparison. Node fills
 * still carry only the three families underneath. */
const FLOW_EDGE_VAR: Record<string, string> = {
  http_in: "--atlas-family-runtime",
  process_boundary: "--atlas-family-runtime",
  call: "--atlas-family-code",
  read: "--atlas-family-state",
  config_read: "--atlas-family-state",
  persist: "--atlas-family-state",
  schema_own: "--atlas-accent",
};

const FLOW_EDGE_WIDTH: Record<string, number> = {
  http_in: 2.2,
  process_boundary: 1.4,
  call: 1.4,
  read: 1.6,
  config_read: 1.2,
  persist: 2.2,
  schema_own: 2.2,
};

/** Resolved once per mount. Sigma parses colours into WebGL float buffers, so
 * handing it a `var(...)` string silently yields black. */
interface Palette {
  family: Record<Family, string>;
  hollow: string;
  dimEdge: string;
  accent: string;
  border: string;
  confidence: Record<string, string>;
}

function readPalette(): Palette {
  const bucket = (b: ConfidenceBucket) => resolveCssColor(confidenceColor(b).replace(/^var\(|\)$/g, ""));
  return {
    family: {
      code: resolveCssColor(FAMILY_VAR.code, "#3987e5"),
      runtime: resolveCssColor(FAMILY_VAR.runtime, "#d95926"),
      state: resolveCssColor(FAMILY_VAR.state, "#199e70"),
    },
    hollow: resolveCssColor("--atlas-node-hollow", "#0b0f14"),
    dimEdge: DIM_EDGE,
    accent: resolveCssColor("--atlas-accent", "#22e0ff"),
    border: resolveCssColor("--atlas-border", "#262c36"),
    confidence: {
      high: bucket("high"),
      medium: bucket("medium"),
      low: bucket("low"),
      contested: bucket("contested"),
      unreviewed: resolveCssColor("--atlas-border", "#262c36"),
    },
  };
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

/**
 * Wheel gesture is only treated as an altitude change when the pointer is
 * over the canvas *and* the canvas has focus (`WEB_RESEARCH.md` §3 rule 3) --
 * otherwise an incidental page-scroll wheel event while the mouse happens to
 * pass over the canvas would silently change altitude. A `ctrlKey` wheel
 * event is a trackpad pinch and is left alone so sigma's native camera zoom
 * handles it.
 *
 * All visual encoding runs through Sigma's node/edge **reducers** rather than
 * by mutating graph attributes. That is what makes a lens switch, a hover
 * highlight, a diff pulse and a zoom-driven shape change all free of layout:
 * the graph object is never touched after `buildGraph`, so FA2/dagre cannot
 * re-run (`PLAN.md`'s acceptance test, now enforced by construction rather
 * than by remembering to mutate carefully).
 */
export function AtlasCanvas() {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const sigmaRef = useRef<Sigma | null>(null);
  const [hasFocus, setHasFocus] = useState(false);
  const [shapesResolved, setShapesResolved] = useState(true);

  const altitude = useAtlasStore((s) => s.altitude);
  const scope = useAtlasStore((s) => s.scope);
  const descend = useAtlasStore((s) => s.descend);
  const ascend = useAtlasStore((s) => s.ascend);
  const hoveredNodeId = useAtlasStore((s) => s.hoveredNodeId);
  const selectedNodeId = useAtlasStore((s) => s.selectedNodeId);
  const hoverNode = useAtlasStore((s) => s.hoverNode);
  const selectNode = useAtlasStore((s) => s.selectNode);
  const accumulateWheel = useAtlasStore((s) => s.accumulateWheel);
  const lens = useAtlasStore((s) => s.lens);
  const diffHighlight = useAtlasStore((s) => s.diffHighlight);

  const { data, isLoading, error } = useGraph(altitude, scope);
  const confidenceById = useNodesConfidence(altitude, scope, lens === "confidence");

  const graph = useMemo(() => {
    if (!data) return null;
    // L3 is a small ranked DAG (packages); L2 is a 353-node force layout.
    return buildGraph(data, altitude === "L3");
  }, [data, altitude]);

  /** Reducer inputs, held in a ref so changing one never re-creates Sigma --
   * only a `refresh()`. */
  const stateRef = useRef({
    lens,
    confidenceById,
    hoveredNodeId,
    selectedNodeId,
    diffHighlight,
    shapesResolved: true,
    palette: null as Palette | null,
  });
  useEffect(() => {
    if (!graph || !containerRef.current) return;
    const palette = readPalette();
    stateRef.current.palette = palette;

    const sigma = new Sigma(
      graph,
      containerRef.current,
      sigmaSettings({
        // A small ranked graph (L3 is ~18 packages) should label everything --
        // a degree threshold there hides half the map for no benefit. The
        // threshold only earns its keep once labels start colliding.
        labelRenderedSizeThreshold: graph.order <= 60 ? 0 : 9,
        labelDensity: graph.order <= 60 ? 1 : 0.25,

        nodeReducer: (node, attrs) => {
          const s = stateRef.current;
          const family = attrs.family as Family;
          const bucket = s.confidenceById.get(node) ?? "unreviewed";
          const isFocus = node === s.hoveredNodeId || node === s.selectedNodeId;
          const isDiffAdded = s.diffHighlight?.added.includes(node) ?? false;

          const res: Record<string, unknown> = { ...attrs };
          res.type = s.shapesResolved ? (attrs.shape as string) : "dot";

          if (s.lens === "confidence") {
            res.color = palette.confidence[bucket] ?? palette.confidence.unreviewed;
            res.ringColor = palette.border;
            res.label = (attrs.baseLabel as string) + (CONFIDENCE_GLYPH[bucket] ?? "");
          } else {
            res.color = palette.family[family] ?? palette.family.code;
            // Status on the ring, structure in the fill -- never mixed.
            res.ringColor = bucket === "unreviewed" ? palette.border : palette.confidence[bucket];
            res.label = attrs.baseLabel as string;
          }

          res.hollowColor = palette.hollow;

          if (isDiffAdded) {
            res.color = palette.accent;
            res.ringColor = palette.accent;
            res.size = (attrs.size as number) * 1.7;
            res.zIndex = 3;
            res.forceLabel = true;
          } else if (isFocus) {
            res.ringColor = palette.accent;
            res.size = (attrs.size as number) * 1.25;
            res.zIndex = 2;
            res.forceLabel = true;
          }

          return res;
        },

        edgeReducer: (edge, attrs) => {
          const s = stateRef.current;
          const source = graph.source(edge);
          const target = graph.target(edge);
          // Only a focus id that exists *in this graph* counts. An id left
          // over from another altitude would otherwise put every edge in the
          // dimmed branch with nothing highlighted -- a canvas that looks
          // broken rather than focused.
          const hovered = s.hoveredNodeId && graph.hasNode(s.hoveredNodeId) ? s.hoveredNodeId : null;
          const selected =
            s.selectedNodeId && graph.hasNode(s.selectedNodeId) ? s.selectedNodeId : null;
          const touchesFocus =
            source === hovered || target === hovered || source === selected || target === selected;
          const someFocus = hovered !== null || selected !== null;

          const res: Record<string, unknown> = { ...attrs };
          const kind = attrs.kind as string;
          const confidence = attrs.confidence as string | null;

          if (s.lens === "flow") {
            const varName = FLOW_EDGE_VAR[kind];
            res.color =
              (varName ? resolveCssColor(varName, palette.family.code) : palette.dimEdge) +
              edgeAlpha(confidence);
            res.size = FLOW_EDGE_WIDTH[kind] ?? 1.2;
          } else if (s.lens === "confidence") {
            res.color = palette.dimEdge;
            res.size = 0.9;
          } else {
            // Structure: an edge takes the family of what it *reaches*, so a
            // glance reads "blue code through orange boundaries into aqua
            // state" -- which is the actual architecture.
            res.color =
              (palette.family[attrs.targetFamily as Family] ?? palette.family.code) +
              edgeAlpha(confidence);
            res.size = edgeWidth(confidence);
          }

          if (someFocus) {
            if (touchesFocus) {
              res.color = palette.accent;
              res.size = (res.size as number) * 1.6;
              res.zIndex = 2;
            } else {
              res.color = palette.dimEdge + "40";
            }
          }

          return res;
        },
      }),
    );
    sigmaRef.current = sigma;
    fitToViewport(sigma);
    // Dev-only handle. §4's "fit to viewport" claim is geometric -- no unit
    // test can see whether a node landed outside the frame -- so this exists
    // to make it checkable from a browser console or a Playwright probe:
    //   __atlasSigma.getGraph().forEachNode(n =>
    //     __atlasSigma.framedGraphToViewport(__atlasSigma.getNodeDisplayData(n)))
    // Measured 0 offscreen nodes at both altitudes on this repo.
    if (import.meta.env.DEV) {
      (window as unknown as { __atlasSigma?: Sigma }).__atlasSigma = sigma;
    }

    sigma.on("enterNode", ({ node }) =>
      hoverNode(node, (graph.getNodeAttribute(node, "nodeId") as string | null) ?? null),
    );
    sigma.on("leaveNode", () => hoverNode(null, null));
    sigma.on("clickNode", ({ node }) =>
      selectNode(node, (graph.getNodeAttribute(node, "nodeId") as string | null) ?? null),
    );
    sigma.on("doubleClickNode", ({ node, event }) => {
      event.preventSigmaDefault();
      descend(node);
    });
    sigma.on("clickStage", () => selectNode(null, null));

    // Shape stops carrying identity once nodes are a few pixels across
    // (`ATLAS_REDESIGN.md` §7). Swap every node to a plain dot past the
    // threshold and tell the legend to say so. Changing a node's program
    // needs a full re-index, so this fires only on threshold *crossings*,
    // not per frame.
    const camera = sigma.getCamera();
    const onCameraUpdate = () => {
      const resolved = camera.ratio <= SHAPE_ZOOM_THRESHOLD;
      if (resolved === stateRef.current.shapesResolved) return;
      stateRef.current.shapesResolved = resolved;
      setShapesResolved(resolved);
      sigma.refresh();
    };
    camera.on("updated", onCameraUpdate);

    return () => {
      camera.off("updated", onCameraUpdate);
      sigma.kill();
      sigmaRef.current = null;
    };
  }, [graph, hoverNode, selectNode, descend]);

  /** Every reducer input change is a repaint, never a rebuild. The inputs are
   * published to `stateRef` here (not during render, which would be a ref
   * write in render) and then `refresh({skipIndexation})` re-runs only the
   * reducers, keeping the WebGL buffers -- so a lens switch on a 353-node
   * graph costs a frame, not a relayout. */
  useEffect(() => {
    const s = stateRef.current;
    s.lens = lens;
    s.confidenceById = confidenceById;
    s.hoveredNodeId = hoveredNodeId;
    s.selectedNodeId = selectedNodeId;
    s.diffHighlight = diffHighlight;
    sigmaRef.current?.refresh({ skipIndexation: true });
  }, [lens, confidenceById, hoveredNodeId, selectedNodeId, diffHighlight]);

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

  const edgeKinds = useMemo(() => {
    const counts = new Map<string, number>();
    for (const edge of data?.edges ?? []) {
      counts.set(edge.kind, (counts.get(edge.kind) ?? 0) + (edge.count ?? 1));
    }
    return [...counts.entries()]
      .map(([kind, count]) => ({ kind, count }))
      .sort((a, b) => b.count - a.count);
  }, [data]);

  const confidenceCounts = useMemo(() => {
    const counts: Partial<Record<ConfidenceBucket, number>> = {};
    let seen = 0;
    for (const bucket of confidenceById.values()) {
      counts[bucket] = (counts[bucket] ?? 0) + 1;
      seen += 1;
    }
    counts.unreviewed = Math.max(0, (data?.nodes.length ?? 0) - seen);
    return counts;
  }, [confidenceById, data]);

  const fps = useFpsOverlay(import.meta.env.DEV);
  const prefersReducedMotion = useMemo(
    () => window.matchMedia("(prefers-reduced-motion: reduce)").matches,
    [],
  );
  const canvasKey = `${altitude}:${scope ?? ""}`;
  const isEmpty = !isLoading && !error && (data?.edges.length ?? 0) === 0;

  return (
    <div className="relative h-full w-full">
      <AltitudeSwitcher
        altitude={altitude}
        scope={scope}
        nodeCount={data?.nodes.length ?? 0}
        edgeCount={data?.edges.length ?? 0}
      />

      {import.meta.env.DEV && (
        // Bottom-centre: the top-right corner belongs to the view switcher
        // and the legend.
        <div className="absolute bottom-3 left-1/2 z-10 -translate-x-1/2 rounded bg-black/40 px-2 py-1 font-mono text-xs text-white">
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
      {isEmpty && (
        <div className="absolute inset-0 flex items-center justify-center px-8 text-center text-sm text-[var(--atlas-text-dim)]">
          Nothing to map yet — this snapshot has no extracted connections. Run a scan from the
          Control Room, then come back.
        </div>
      )}

      {data && !isEmpty && (
        <GraphLegend
          lens={lens}
          entries={data.legend ?? []}
          edgeKinds={edgeKinds}
          confidenceCounts={confidenceCounts}
          divergence={altitude === "L3" ? (data.divergence as never) : null}
          shapesResolved={shapesResolved}
        />
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

export type { Altitude };
