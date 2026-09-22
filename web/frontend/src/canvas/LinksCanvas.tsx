import Graph from "graphology";
import { useEffect, useMemo, useRef, useState } from "react";
import Sigma from "sigma";
import { useLinks } from "../api/hooks.ts";
import {
  MIN_NODE_SIZE,
  nodeSize,
  resolveCssColor,
  SHAPE_ZOOM_THRESHOLD,
} from "../theme/graphEncoding.ts";
import { fitToViewport, layoutForceAtlas2 } from "./graphLayout.ts";
import { sigmaSettings } from "./sigmaPrograms.ts";

/** Intra-repo module-link constellation (Phase 4 item #1, shipped as
 * *intra-repo*, not cross-repo -- per the user's confirmed scope call:
 * this repo has no second registered repo to back a real cross-repo
 * edge honestly yet, so nodes here are this repo's own code entities and
 * edges are its own `persist`/channel-style calls, matched (`GET
 * /api/links`'s `links`) or dangling (`unmatched`). Architected to slot a
 * second real repo's nodes in later without a rewrite: nothing here
 * assumes single-repo `module` values. Deliberately a standalone canvas,
 * not a retrofit of `AtlasCanvas` -- L4 has no altitude/drill-down axis and
 * a different node/edge shape (code entities and their call targets, not
 * modules/scopes).
 *
 * `ATLAS_REDESIGN.md` §1 named this canvas as the other half of the problem:
 * it ran the same stock Sigma defaults and the same bare `inferSettings`
 * force layout, which is what produced the scattered star-field. It now
 * shares `graphLayout.ts`'s linLog settings, `sigmaPrograms.ts`'s arrowed
 * edges, and the degree-scaled node sizes -- so a fix to the encoding lands
 * on both canvases at once. */
export function LinksCanvas() {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const sigmaRef = useRef<Sigma | null>(null);
  const [hovered, setHovered] = useState<string | null>(null);
  const { data, isLoading, error } = useLinks();

  const palette = useMemo(
    () => ({
      matched: resolveCssColor("--atlas-verified", "#34d97a"),
      // Not `--atlas-border`: at #262c36 the 73 unmatched edges were very
      // nearly invisible on this backdrop, which made the canvas read as
      // emptier than the data is. Dim enough to recede behind the one
      // matched link, bright enough to trace by eye.
      unmatched: "#465162",
      dim: resolveCssColor("--atlas-border", "#262c36"),
      node: resolveCssColor("--atlas-family-code", "#3987e5"),
      accent: resolveCssColor("--atlas-accent", "#22e0ff"),
      hollow: resolveCssColor("--atlas-node-hollow", "#0b0f14"),
    }),
    [],
  );

  const graph = useMemo(() => {
    if (!data) return null;
    const g = new Graph({ multi: true, type: "directed" });
    const ensureNode = (id: string, matched: boolean) => {
      if (!g.hasNode(id)) {
        g.addNode(id, {
          label: id,
          baseLabel: id,
          size: MIN_NODE_SIZE,
          type: "circle",
          matched,
        });
      } else if (matched) {
        g.setNodeAttribute(id, "matched", true);
      }
    };

    for (const link of data.links) {
      ensureNode(link.caller.node, true);
      ensureNode(link.callee.node, true);
      if (link.caller.node !== link.callee.node) {
        g.addEdge(link.caller.node, link.callee.node, {
          color: palette.matched,
          size: 2.2,
          kind: "link",
          type: "arrow",
        });
      }
    }
    for (const u of data.unmatched) {
      ensureNode(u.outbound.node, false);
      ensureNode(u.outbound.target, false);
      if (u.outbound.node !== u.outbound.target) {
        g.addEdge(u.outbound.node, u.outbound.target, {
          color: palette.unmatched,
          size: 1,
          kind: "unmatched",
          type: "arrow",
        });
      }
    }

    // Size by degree, same log scale as the Atlas: the hubs in an unmatched
    // call fan-out are the ones worth looking at.
    let maxDegree = 1;
    g.forEachNode((node) => {
      maxDegree = Math.max(maxDegree, g.degree(node));
    });
    g.forEachNode((node) => {
      const matched = g.getNodeAttribute(node, "matched") as boolean;
      g.setNodeAttribute(node, "size", nodeSize(g.degree(node), maxDegree));
      // A matched link is corroborated from both ends -- filled; an unmatched
      // outbound call has only one end and reads hollow.
      g.setNodeAttribute(node, "type", matched ? "circle" : "ring");
      g.setNodeAttribute(node, "color", matched ? palette.matched : palette.node);
      g.setNodeAttribute(node, "hollowColor", palette.hollow);
    });

    if (g.order > 0) layoutForceAtlas2(g);
    return g;
  }, [data, palette]);

  const hoveredRef = useRef<string | null>(null);

  useEffect(() => {
    if (!graph || !containerRef.current) return;
    const sigma = new Sigma(
      graph,
      containerRef.current,
      sigmaSettings({
        nodeReducer: (node, attrs) => {
          if (hoveredRef.current === null) return attrs;
          if (node !== hoveredRef.current && !graph.neighbors(hoveredRef.current).includes(node)) {
            return { ...attrs, color: palette.dim, label: "" };
          }
          return { ...attrs, forceLabel: true, zIndex: 2 };
        },
        edgeReducer: (edge, attrs) => {
          if (hoveredRef.current === null) return attrs;
          const touches =
            graph.source(edge) === hoveredRef.current || graph.target(edge) === hoveredRef.current;
          return touches
            ? { ...attrs, color: palette.accent, size: (attrs.size as number) * 1.6, zIndex: 2 }
            : { ...attrs, color: palette.dim + "60" };
        },
      }),
    );
    sigmaRef.current = sigma;
    fitToViewport(sigma);

    sigma.on("enterNode", ({ node }) => setHovered(node));
    sigma.on("leaveNode", () => setHovered(null));

    const camera = sigma.getCamera();
    const onCameraUpdate = () => {
      const resolved = camera.ratio <= SHAPE_ZOOM_THRESHOLD;
      graph.forEachNode((node, attrs) => {
        const want = resolved ? ((attrs.matched as boolean) ? "circle" : "ring") : "dot";
        if (attrs.type !== want) graph.setNodeAttribute(node, "type", want);
      });
    };
    camera.on("updated", onCameraUpdate);

    return () => {
      camera.off("updated", onCameraUpdate);
      sigma.kill();
      sigmaRef.current = null;
    };
  }, [graph, palette]);

  useEffect(() => {
    hoveredRef.current = hovered;
    sigmaRef.current?.refresh({ skipIndexation: true });
  }, [hovered]);

  const linkCount = data?.links.length ?? 0;
  const unmatchedCount = data?.unmatched.length ?? 0;

  return (
    <div className="relative h-full w-full">
      <div className="atlas-card absolute left-3 top-3 z-10 max-w-md p-3 text-xs">
        <div className="font-medium" style={{ color: "var(--atlas-text)" }}>
          Which calls actually land somewhere we can see?
        </div>
        <div className="mt-1" style={{ color: "var(--atlas-text-dim)" }}>
          <span style={{ color: palette.matched }}>●</span> {linkCount} matched link
          {linkCount === 1 ? "" : "s"} — both ends resolved. <span>○</span> {unmatchedCount} outbound
          call{unmatchedCount === 1 ? "" : "s"} with nothing on the far end yet. From this repo's own
          <code className="mx-1">cdp link scan</code>, not a fabricated cross-repo dataset.
        </div>
      </div>

      {isLoading && (
        <div className="absolute inset-0 flex items-center justify-center text-sm text-[var(--atlas-text-dim)]">
          loading links…
        </div>
      )}
      {error && (
        <div className="absolute inset-0 flex items-center justify-center text-sm text-red-400">
          {String(error)}
        </div>
      )}
      {data && linkCount === 0 && unmatchedCount === 0 && (
        <div className="absolute inset-0 flex items-center justify-center px-8 text-center text-sm text-[var(--atlas-text-dim)]">
          No cross-module links recorded yet. Run{" "}
          <code className="mx-1">cdp link scan &lt;state_dir&gt; --db &lt;index.db&gt;</code> to
          populate this map.
        </div>
      )}
      <div ref={containerRef} className="h-full w-full" />
    </div>
  );
}
