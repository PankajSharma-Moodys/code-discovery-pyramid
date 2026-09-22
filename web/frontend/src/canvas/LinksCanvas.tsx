import forceAtlas2 from "graphology-layout-forceatlas2";
import Graph from "graphology";
import { useEffect, useMemo, useRef } from "react";
import Sigma from "sigma";
import { useLinks } from "../api/hooks.ts";

const NODE_COLOR = "#8b93a1";
const LINK_EDGE_COLOR = "#3ddc97";
const UNMATCHED_EDGE_COLOR = "#4b5563";

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
 * modules/scopes). */
export function LinksCanvas() {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const sigmaRef = useRef<Sigma | null>(null);
  const { data, isLoading, error } = useLinks();

  const graph = useMemo(() => {
    if (!data) return null;
    const g = new Graph({ multi: true, type: "directed" });
    const ensureNode = (id: string, label: string) => {
      if (!g.hasNode(id)) g.addNode(id, { label, x: Math.random() * 1000, y: Math.random() * 1000, size: 6 });
    };
    for (const link of data.links) {
      ensureNode(link.caller.node, link.caller.node);
      ensureNode(link.callee.node, link.callee.node);
      if (link.caller.node !== link.callee.node) {
        g.addEdge(link.caller.node, link.callee.node, { color: LINK_EDGE_COLOR, size: 2, kind: "link" });
      }
    }
    for (const u of data.unmatched) {
      ensureNode(u.outbound.node, u.outbound.node);
      ensureNode(u.outbound.target, u.outbound.target);
      if (u.outbound.node !== u.outbound.target) {
        g.addEdge(u.outbound.node, u.outbound.target, { color: UNMATCHED_EDGE_COLOR, size: 1, kind: "unmatched" });
      }
    }
    g.forEachNode((node) => {
      g.setNodeAttribute(node, "size", 4 + Math.min(12, g.degree(node)));
    });
    if (g.order > 0) {
      const settings = forceAtlas2.inferSettings(g);
      forceAtlas2.assign(g, { iterations: 200, settings });
    }
    return g;
  }, [data]);

  useEffect(() => {
    if (!graph || !containerRef.current) return;
    const sigma = new Sigma(graph, containerRef.current, {
      defaultNodeColor: NODE_COLOR,
      defaultEdgeColor: UNMATCHED_EDGE_COLOR,
      labelColor: { color: "#d7dbe0" },
    });
    sigmaRef.current = sigma;
    return () => {
      sigma.kill();
      sigmaRef.current = null;
    };
  }, [graph]);

  const linkCount = data?.links.length ?? 0;
  const unmatchedCount = data?.unmatched.length ?? 0;

  return (
    <div className="relative h-full w-full">
      <div
        className="absolute left-3 top-3 z-10 max-w-md rounded px-3 py-2 text-xs"
        style={{ background: "var(--atlas-bg-2)", color: "var(--atlas-text-dim)", border: "1px solid var(--atlas-border)" }}
      >
        <div className="font-medium" style={{ color: "var(--atlas-text)" }}>
          Module links (intra-repo)
        </div>
        <div className="mt-1">
          {linkCount} matched link{linkCount === 1 ? "" : "s"} (
          <span style={{ color: LINK_EDGE_COLOR }}>green</span>), {unmatchedCount} unmatched outbound call
          {unmatchedCount === 1 ? "" : "s"} (<span style={{ color: "#9ca3af" }}>grey</span>) -- from this repo's own
          `cdp link scan`, not a fabricated cross-repo dataset.
        </div>
      </div>
      {isLoading && (
        <div className="absolute inset-0 flex items-center justify-center text-sm text-[var(--atlas-text-dim)]">
          loading links…
        </div>
      )}
      {error && (
        <div className="absolute inset-0 flex items-center justify-center text-sm text-red-400">{String(error)}</div>
      )}
      {data && linkCount === 0 && unmatchedCount === 0 && (
        <div className="absolute inset-0 flex items-center justify-center text-sm text-[var(--atlas-text-dim)]">
          no link data yet -- run `cdp link scan &lt;state_dir&gt; --db &lt;index.db&gt;`
        </div>
      )}
      <div ref={containerRef} className="h-full w-full" />
    </div>
  );
}
