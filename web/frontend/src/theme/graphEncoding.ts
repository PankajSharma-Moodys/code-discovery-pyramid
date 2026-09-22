/**
 * Visual encoding for both graph canvases (`ATLAS_REDESIGN.md` §3).
 *
 * Before this existed, both canvases ran Sigma's stock defaults --
 * `defaultNodeColor:"#999"`, `defaultEdgeColor:"#ccc"`, `defaultEdgeType:
 * "line"` -- because no node or edge attribute was ever set beyond a constant
 * `size`. One channel (position) carried data and five sat idle. This module
 * is the assignment table for all six.
 *
 * | channel | carries |
 * |---|---|
 * | node fill | type *family* (3 colours, capped) |
 * | node shape | type, within its family |
 * | node size | degree, log-scaled |
 * | node ring | claim confidence |
 * | edge colour | family of its **target** |
 * | edge width/alpha | extraction confidence |
 * | edge arrow | direction |
 *
 * The three-colour cap is §3's, and it is computed rather than taste: every
 * 4th hue tested fails the all-pairs CVD floor on this background (violet↔blue
 * ΔE 1.9 protan, magenta↔aqua ΔE 1.6 deutan, yellow↔orange ΔE 10.6 normal
 * vision). A graph is all-pairs by nature, so node type cannot be a hue.
 *
 * `type` and `family` are computed server-side (`web/api/encoding.py`) so the
 * L3 rollup and L2 typing cannot drift apart; this module only decides how
 * they *look*.
 */

export type Family = "code" | "runtime" | "state";

/** Sigma parses colours at WebGL init and never re-reads CSS, so these are
 * resolved from the custom properties once per mount rather than passed as
 * `var(...)` strings -- see {@link resolveCssColor}. */
export const FAMILY_VAR: Record<Family, string> = {
  code: "--atlas-family-code",
  runtime: "--atlas-family-runtime",
  state: "--atlas-family-state",
};

export const FAMILY_LABEL: Record<Family, string> = {
  code: "Code",
  runtime: "Runtime surface",
  state: "Persistent state",
};

/** One line each, for the legend. These are what make the canvas
 * self-explanatory without a separate key -- §5's "every tile answers what it
 * is for, unprompted". */
export const FAMILY_CAPTION: Record<Family, string> = {
  code: "modules and the libraries they import",
  runtime: "where the system is entered: processes, routes, ports",
  state: "what outlives a request: tables, entities, migrations, config",
};

/** §3 assigns shape as the primary, CVD-immune identity channel. Three shapes
 * are available from MIT Sigma plugins (filled circle, hollow circle, filled
 * square); the largest family has four types, so `config` and `migration` --
 * 8 nodes between them on this repo, and both "declarative state definitions"
 * -- share the hollow shape and are separated by label. That collision is
 * deliberate and is spelled out in the legend rather than papered over. */
export type NodeShape = "circle" | "ring" | "square";

export const SHAPE_OF_TYPE: Record<string, NodeShape> = {
  // code
  package: "circle",
  module: "circle",
  library: "ring",
  // runtime surface
  process: "square",
  route: "circle",
  port: "ring",
  // persistent state
  table: "square",
  entity: "circle",
  config: "ring",
  migration: "ring",
};

export const SHAPE_GLYPH: Record<NodeShape, string> = {
  circle: "●",
  ring: "○",
  square: "■",
};

export const DEFAULT_SHAPE: NodeShape = "circle";

export function shapeOf(type: string | null | undefined): NodeShape {
  return (type && SHAPE_OF_TYPE[type]) || DEFAULT_SHAPE;
}

export function familyOf(family: string | null | undefined): Family {
  return family === "runtime" || family === "state" ? family : "code";
}

/** Edge channels as extracted by `cdp` (`dataflow.edges[].channel`). Captions
 * are the reason the Flow lens exists: "persist" means nothing on its own. */
export const EDGE_KIND_LABEL: Record<string, string> = {
  call: "calls",
  persist: "writes to",
  read: "reads",
  http_in: "served by",
  process_boundary: "runs as",
  config_read: "reads config",
  schema_own: "defines schema for",
  import: "imports",
  // still emitted by the `graph`-artifact altitudes
  declared: "declared",
  observed: "observed",
  both: "declared + observed",
  coupling: "coupled to",
  link: "matched link",
  unmatched: "unmatched call",
  flow: "flows to",
};

/** Ordered for the Flow legend: entry points first, then calls, then the
 * state writes -- reading top to bottom traces a request. */
export const EDGE_KIND_ORDER = [
  "http_in",
  "process_boundary",
  "call",
  "read",
  "config_read",
  "persist",
  "schema_own",
];

/** Log-scaled so a degree-36 hub is legibly bigger than a degree-2 leaf
 * without a degree-1 node vanishing. `ATLAS_REDESIGN.md` §3: "makes hubs
 * findable" -- the single most useful thing size can do on a 353-node graph. */
export const MIN_NODE_SIZE = 3.5;
export const MAX_NODE_SIZE = 18;

export function nodeSize(degree: number, maxDegree: number): number {
  if (maxDegree <= 1) return MIN_NODE_SIZE + 2;
  const t = Math.log1p(Math.max(0, degree)) / Math.log1p(maxDegree);
  return MIN_NODE_SIZE + t * (MAX_NODE_SIZE - MIN_NODE_SIZE);
}

/** Edge width by extraction confidence. §3 asks for solid/dashed/dotted, which
 * no WebGL edge program in the Sigma ecosystem supports without a custom
 * shader; width plus alpha is the substitute, and it is a *redundant* channel
 * (colour already carries target family) rather than the sole carrier of
 * anything, so nothing is lost but the texture. */
export const EDGE_CONFIDENCE_WIDTH: Record<string, number> = {
  high: 1.8,
  medium: 1.1,
  low: 0.8,
  contested: 0.8,
};

export const EDGE_CONFIDENCE_ALPHA: Record<string, string> = {
  high: "cc",
  medium: "80",
  low: "59",
  contested: "59",
};

export function edgeWidth(confidence: string | null | undefined): number {
  return (confidence ? EDGE_CONFIDENCE_WIDTH[confidence] : undefined) ?? 1.1;
}

export function edgeAlpha(confidence: string | null | undefined): string {
  return (confidence ? EDGE_CONFIDENCE_ALPHA[confidence] : undefined) ?? "80";
}

/** Below this camera ratio (i.e. zoomed out past it) every node collapses to
 * a plain dot and shape stops carrying identity. §7's stress test is explicit
 * that shape must not be the sole identity channel without this threshold and
 * without saying so — colour and size still carry below it, and the legend
 * says exactly that. Sigma's `ratio` grows as you zoom *out*. */
export const SHAPE_ZOOM_THRESHOLD = 1.35;

/** Above this many already-fetched nodes, the legend's "Hide tests" toggle
 * stops dimming client-side and refetches via `/api/graph?hide_roles=test`
 * instead (`AtlasCanvas`).
 *
 * Not measured against a live Sigma canvas: this environment had no browser
 * automation available to drive the real dev server (the Playwright
 * convention this repo otherwise uses for canvas work), so this is a
 * documented estimate, not a live measurement. What *was* measured: the
 * reducer-side cost of the hidden-set membership check itself (a `Set.has`
 * per node/edge) is under 3ms even at 50,000 nodes -- negligible next to
 * Sigma's WebGL repaint, which is the actual bottleneck and scales with node
 * + edge count. 2,000 is picked conservatively inside the range Sigma's own
 * docs and community benchmarks describe as comfortably interactive for
 * force-directed WebGL rendering (smooth well past this on modern hardware,
 * degrading well beyond it too), while every graph this repo itself produces
 * today (L2 tops out at 353 nodes) stays far under it either way. Revisit
 * with a live Playwright run against a larger real repo before trusting this
 * number at the edges. */
export const ROLE_HIDE_CLIENT_THRESHOLD = 2000;

export function resolveCssColor(value: string, fallback = "#8b93a1"): string {
  if (typeof document === "undefined") return fallback;
  if (!value.startsWith("--")) return value;
  return getComputedStyle(document.documentElement).getPropertyValue(value).trim() || fallback;
}
