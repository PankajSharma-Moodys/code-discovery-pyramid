import { createEdgeCurveProgram, EdgeCurvedArrowProgram } from "@sigma/edge-curve";
import { createNodeBorderProgram } from "@sigma/node-border";
import { NodeSquareProgram } from "@sigma/node-square";
import { EdgeArrowProgram, NodeCircleProgram } from "sigma/rendering";
import type { Settings } from "sigma/settings";

/**
 * The renderer half of `ATLAS_REDESIGN.md` §1's second cause: neither canvas
 * passed `nodeProgramClasses`/`edgeProgramClasses` to `new Sigma(...)`, so
 * both ran stock defaults -- grey dots, grey hairlines, and no direction at
 * all despite the graph being `type: "directed"`.
 *
 * Every program here comes from an MIT `@sigma/*` package or Sigma's own
 * bundle; `scripts/check-licenses.mjs` gates that and was re-run after these
 * were added. `@cosmograph/cosmos` -- the obvious "GPU graphs" pick -- is
 * CC-BY-NC-4.0 and would fail that gate, which is why it is not here.
 */

/** Claim-status ring, drawn outside the family fill. §3 keeps the semantic
 * triad on the ring and structure in the fill so the two never mix. */
const RING = { color: { attribute: "ringColor", defaultValue: "#00000000" }, size: { value: 0.14 } };

/** Filled disc: the default node. */
export const NodeCircleBorderProgram = createNodeBorderProgram({
  borders: [RING, { color: { attribute: "color" }, size: { fill: true } }],
});

/** Hollow disc: same hue, punched through to the canvas backdrop. Reads as
 * "same family, different type" at a glance without spending a hue. */
export const NodeRingProgram = createNodeBorderProgram({
  borders: [
    RING,
    { color: { attribute: "color" }, size: { value: 0.26 } },
    { color: { attribute: "hollowColor", defaultValue: "#0b0f14" }, size: { fill: true } },
  ],
});

/** Plain dot, used below `SHAPE_ZOOM_THRESHOLD` where shapes are smaller than
 * the difference between them (§7's stress test). */
export const NodeDotProgram = NodeCircleProgram;

export const NODE_PROGRAMS = {
  circle: NodeCircleBorderProgram,
  ring: NodeRingProgram,
  square: NodeSquareProgram,
  dot: NodeDotProgram,
};

/** Parallel edges get a curvature so a `call` and a `persist` between the same
 * pair stop drawing on top of each other -- at L3 especially, where up to
 * seven channels can collapse onto one package pair. */
export const EdgeCurvedProgram = createEdgeCurveProgram({
  arrowHead: { extremity: "target", lengthToThicknessRatio: 2.5, widenessToThicknessRatio: 2 },
  curvatureAttribute: "curvature",
  defaultCurvature: 0.25,
});

export const EDGE_PROGRAMS = {
  arrow: EdgeArrowProgram,
  curve: EdgeCurvedProgram,
  curvedArrow: EdgeCurvedArrowProgram,
};

/** Shared Sigma settings for both canvases. The label settings are §4's
 * "raise `labelRenderedSizeThreshold` so only hubs label when zoomed out":
 * since node size is degree, a size threshold *is* a degree threshold. The
 * grid is coarse and the density low because the first pass at 353 nodes
 * still stacked `store.sqlite_backend` on top of `cdp.schema`. */
export function sigmaSettings(overrides: Partial<Settings> = {}): Partial<Settings> {
  return {
    nodeProgramClasses: NODE_PROGRAMS,
    edgeProgramClasses: EDGE_PROGRAMS,
    defaultNodeType: "circle",
    defaultEdgeType: "arrow",
    labelColor: { color: "#d7dbe0" },
    labelFont: "ui-sans-serif, system-ui, sans-serif",
    labelSize: 11,
    labelWeight: "500",
    labelDensity: 0.25,
    labelGridCellSize: 150,
    labelRenderedSizeThreshold: 9,
    edgeLabelColor: { color: "#8b93a1" },
    edgeLabelSize: 10,
    zIndex: true,
    minCameraRatio: 0.05,
    maxCameraRatio: 8,
    ...overrides,
  };
}
