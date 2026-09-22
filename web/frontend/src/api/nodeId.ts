/**
 * `/api/graph?level=` returns **raw** artifact keys as node ids -- a package
 * or type-bucket name at L3, a `dataflow` endpoint at L2, a file path at L1 --
 * while `/api/node/:id` requires the namespaced form (`module:`, `sym:`,
 * `table:`, `route:`, ... per `web/api/nodeid.py`).
 *
 * Since `ATLAS_REDESIGN.md` P0 made L2 the typed dataflow graph, that mapping
 * is **no longer derivable on the client**: whether a bare id like
 * `web.api.models.JobResponse` is a `sym:` or a `module:` depends on
 * `xref.symbols`, which only the server reads. So the server now resolves it
 * and ships it as `GraphNodeResponse.node_id`, and the canvas carries it
 * through `atlasStore`'s `hoveredApiNodeId`/`selectedApiNodeId`.
 *
 * {@link toNodeId} remains only for the altitudes whose ids *are* derivable
 * (L1 file paths) and as the fallback when a node has no server-resolved id.
 */
export type Altitude = "L3" | "L2" | "L1";

const PREFIX: Record<Altitude, string> = {
  L3: "module:",
  L2: "module:",
  L1: "file:",
};

export function toNodeId(level: Altitude, rawId: string): string {
  return PREFIX[level] + rawId;
}
