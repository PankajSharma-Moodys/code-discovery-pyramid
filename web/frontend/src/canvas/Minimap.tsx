import { useEffect, useMemo, useRef, useState } from "react";
import type Graph from "graphology";
import type Sigma from "sigma";

const WIDTH = 140;
const HEIGHT = 100;
const PADDING = 6;

interface MinimapProps {
  graph: Graph;
  sigma: Sigma | null;
}

interface Bounds {
  minX: number;
  maxX: number;
  minY: number;
  maxY: number;
}

function graphBounds(graph: Graph): Bounds {
  let minX = Infinity;
  let maxX = -Infinity;
  let minY = Infinity;
  let maxY = -Infinity;
  graph.forEachNode((_node, attrs) => {
    const x = attrs.x as number;
    const y = attrs.y as number;
    minX = Math.min(minX, x);
    maxX = Math.max(maxX, x);
    minY = Math.min(minY, y);
    maxY = Math.max(maxY, y);
  });
  if (!Number.isFinite(minX)) return { minX: -1, maxX: 1, minY: -1, maxY: 1 };
  return { minX, maxX, minY, maxY };
}

/**
 * `WEB_REDESIGN_RESEARCH.md` §4's minimap: a small SVG overview of every
 * node's position, plus a rectangle for the camera's current viewport.
 * Bottom-right is the one corner none of the other chrome (`AltitudeSwitcher`
 * top-left, `GraphLegend` top-right, `TracePanel` bottom-left) already owns.
 *
 * Sigma's own camera `x`/`y`/`ratio` live in its internally-normalised
 * "framed graph" space (the same space `fitToViewport` centres at
 * `(0.5, 0.5)`), not this component's raw `graph` node coordinates. Rather
 * than reaching into Sigma's private normalisation, this draws its own
 * bbox-fit-centered projection of the raw coordinates (same convention Sigma
 * itself uses: uniform scale to fit, centered) and reads the camera state
 * directly in that same normalised space -- an approximation good enough for
 * a wayfinding minimap, not a claim of pixel-exact alignment.
 */
export function Minimap({ graph, sigma }: MinimapProps) {
  const [camera, setCamera] = useState<{ x: number; y: number; ratio: number } | null>(null);
  const containerRef = useRef<SVGSVGElement | null>(null);

  useEffect(() => {
    if (!sigma) {
      setCamera(null);
      return;
    }
    const update = () => {
      const state = sigma.getCamera().getState();
      setCamera({ x: state.x, y: state.y, ratio: state.ratio });
    };
    update();
    sigma.getCamera().on("updated", update);
    return () => {
      sigma.getCamera().off("updated", update);
    };
  }, [sigma]);

  const bounds = useMemo(() => graphBounds(graph), [graph]);
  const span = Math.max(1, bounds.maxX - bounds.minX, bounds.maxY - bounds.minY);
  const cx = (bounds.minX + bounds.maxX) / 2;
  const cy = (bounds.minY + bounds.maxY) / 2;
  const innerW = WIDTH - PADDING * 2;
  const innerH = HEIGHT - PADDING * 2;
  const scale = Math.min(innerW, innerH) / span;

  // Same bbox-fit-centered convention as the node projection above, so the
  // rectangle drawn from `camera` lines up with the dots -- this is the
  // approximation this component documents up top, not an exact readback.
  const toMinimap = (x: number, y: number) => ({
    x: WIDTH / 2 + (x - cx) * scale,
    y: HEIGHT / 2 + (y - cy) * scale,
  });

  const points = useMemo(() => {
    const pts: { x: number; y: number }[] = [];
    graph.forEachNode((_node, attrs) => {
      pts.push(toMinimap(attrs.x as number, attrs.y as number));
    });
    return pts;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [graph, bounds]);

  const viewportRect = useMemo(() => {
    if (!camera) return null;
    // `camera.ratio` above 1 means "zoomed out past a full fit" -- the
    // visible half-extent grows with it, same direction `fitToViewport`'s
    // `padding` argument already relies on.
    const halfExtent = (camera.ratio * Math.max(innerW, innerH)) / 2;
    const center = toMinimap((camera.x - 0.5) * span + cx, (camera.y - 0.5) * span + cy);
    return {
      x: center.x - halfExtent / 2,
      y: center.y - halfExtent / 2,
      size: halfExtent,
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [camera, span, cx, cy, innerW, innerH]);

  const handlePan = (event: React.MouseEvent<SVGSVGElement>) => {
    if (!sigma || !containerRef.current) return;
    const rect = containerRef.current.getBoundingClientRect();
    const px = event.clientX - rect.left;
    const py = event.clientY - rect.top;
    // Invert `toMinimap`/the camera projection above to land back in
    // Sigma's normalised camera space for a single click-to-pan gesture.
    const graphX = (px - WIDTH / 2) / scale + cx;
    const graphY = (py - HEIGHT / 2) / scale + cy;
    const normX = (graphX - cx) / span + 0.5;
    const normY = (graphY - cy) / span + 0.5;
    sigma.getCamera().setState({ ...sigma.getCamera().getState(), x: normX, y: normY });
  };

  return (
    <div
      className="atlas-card absolute bottom-3 right-3 z-10 overflow-hidden p-1"
      style={{ width: WIDTH, height: HEIGHT }}
    >
      <svg
        ref={containerRef}
        width={WIDTH}
        height={HEIGHT}
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        onClick={handlePan}
        style={{ cursor: "pointer" }}
        aria-label="Minimap: click to pan"
      >
        {points.map((p, i) => (
          <circle key={i} cx={p.x} cy={p.y} r={1.4} fill="var(--atlas-text-dim)" />
        ))}
        {viewportRect && (
          <rect
            x={viewportRect.x}
            y={viewportRect.y}
            width={viewportRect.size}
            height={viewportRect.size}
            fill="none"
            stroke="var(--atlas-accent)"
            strokeWidth={1.5}
          />
        )}
      </svg>
    </div>
  );
}
