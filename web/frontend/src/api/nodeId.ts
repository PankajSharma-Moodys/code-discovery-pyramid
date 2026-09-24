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
/** Was a fixed 3-member union (`"L3"|"L2"|"L1"`); now open, since the server
 * mints a variable-length ladder per repo (`"L3"`, then `"P2"`, `"P3"`, ...
 * for however many real path-depth forks that repo has, then `"L2"`) --
 * see `MONOREPO_HIERARCHY.md` and `GraphResponse.rungs`. */
export type Altitude = string;

/** `"L3"` (depth 1) or any deeper grouped rung (`"P2"`, `"P3"`, ...) -- every
 * one of them is a package-style rollup, as opposed to `"L2"`/`"L1"`/`"L0"`
 * which are raw, unrolled graphs. Used where the client needs "is this a
 * rollup" rather than "is this exactly the old fixed L3". */
export function isGroupedAltitude(altitude: Altitude): boolean {
  return altitude === "L3" || /^P\d+$/.test(altitude);
}

const PREFIX: Record<string, string> = {
  L3: "module:",
  L2: "module:",
  L1: "file:",
};

export function toNodeId(level: Altitude, rawId: string): string {
  return (isGroupedAltitude(level) ? "module:" : PREFIX[level] ?? "module:") + rawId;
}
