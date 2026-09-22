/**
 * `/api/diff`'s `diff` field is `dict`-typed on the FastAPI side (passed
 * through as-is from `cdp.diffs.diff_snapshots`, see `web/api/models.py`'s
 * `DiffResponse` docstring), so `schema.ts` types it as
 * `{[key: string]: unknown}`. This is the shape `diff_snapshots` (`cdp/
 * diffs.py:30`) actually returns, kept here instead of loosening types at
 * each call site -- same pattern as `traceTypes.ts`.
 */
export interface DiffShape {
  modules: { added: string[]; removed: string[] };
  declared_edges: { added: [string, string][]; removed: [string, string][] };
  observed_edges: { added: [string, string][]; removed: [string, string][] };
  undeclared_dependencies: { appeared: [string, string][]; resolved: [string, string][] };
  routes: { added: [string, string][]; removed: [string, string][] };
  claims: { added: string[]; removed: string[]; anchor_moved: unknown[] };
  coverage: { old: number | null; new: number | null; regressed: boolean };
  findings: string[];
}
