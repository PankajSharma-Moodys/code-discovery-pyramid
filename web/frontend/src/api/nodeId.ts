/**
 * `/api/graph?level=` returns **raw** artifact keys as node ids -- a bare
 * module name at L3, a `partition` scope node string (`"root/foo"`) at L2,
 * a file path at L1 -- never namespace-prefixed. `/api/node/:id` requires
 * the namespaced form (`module:`, `scope:`, `file:`, per
 * `web/api/nodeid.py`). Verified against the running backend while
 * planning this: calling `/api/node/module:(root)` (namespaced) resolves;
 * calling it with the raw graph id alone does not. Centralized here so no
 * call site has to remember the mapping.
 */
export type Altitude = "L3" | "L2" | "L1";

const PREFIX: Record<Altitude, string> = {
  L3: "module:",
  L2: "scope:",
  L1: "file:",
};

export function toNodeId(level: Altitude, rawId: string): string {
  return PREFIX[level] + rawId;
}
