import { useEffect, useRef, useState } from "react";
import { useNodeAt } from "../api/hooks.ts";
import type { Altitude } from "../api/nodeId.ts";

const OPEN_DELAY_MS = 120;
const CURSOR_OFFSET = { x: 16, y: 16 };

interface PeekCardProps {
  altitude: Altitude;
  hoveredRawId: string | null;
  /** Server-resolved namespaced id (`GraphNodeResponse.node_id`). `null` for
   * an L3 package super-node, which is synthetic and has nothing to look up --
   * the card then shows what the canvas already knows instead of firing a
   * request that would 404. */
  hoveredApiNodeId: string | null;
}

/** Follows the cursor with a fixed offset so it never covers the hovered
 * node itself. 120ms open delay per `WEB_RESEARCH.md` §3 -- a fast pass-over
 * shouldn't flash a card. */
export function PeekCard({ altitude, hoveredRawId, hoveredApiNodeId }: PeekCardProps) {
  const [visible, setVisible] = useState(false);
  const [pos, setPos] = useState({ x: 0, y: 0 });
  const timerRef = useRef<number | null>(null);

  const { data, error, isLoading } = useNodeAt(altitude, null, visible ? hoveredApiNodeId : null);

  useEffect(() => {
    if (timerRef.current !== null) window.clearTimeout(timerRef.current);
    if (!hoveredRawId) {
      setVisible(false);
      return;
    }
    timerRef.current = window.setTimeout(() => setVisible(true), OPEN_DELAY_MS);
    return () => {
      if (timerRef.current !== null) window.clearTimeout(timerRef.current);
    };
  }, [hoveredRawId]);

  useEffect(() => {
    const onMove = (event: MouseEvent) => setPos({ x: event.clientX, y: event.clientY });
    window.addEventListener("mousemove", onMove);
    return () => window.removeEventListener("mousemove", onMove);
  }, []);

  if (!visible || !hoveredRawId) return null;

  // Synthetic super-node (or a node the store can't resolve): say what it is
  // rather than showing an empty card.
  if (!hoveredApiNodeId || !data) {
    return (
      <div
        className="atlas-card pointer-events-none fixed z-20 w-64 p-3 text-sm"
        style={{ left: pos.x + CURSOR_OFFSET.x, top: pos.y + CURSOR_OFFSET.y, color: "var(--atlas-text)" }}
      >
        <div className="mb-1 truncate font-medium">{hoveredRawId}</div>
        <div
          className="text-xs"
          style={{ color: error != null ? "var(--atlas-contested)" : "var(--atlas-text-dim)" }}
        >
          {!hoveredApiNodeId
            ? "a group — double-click to see what's inside"
            : error != null
              ? "couldn't load"
              : isLoading
                ? "loading…"
                : "not found"}
        </div>
      </div>
    );
  }

  return (
    <div
      className="atlas-card pointer-events-none fixed z-20 w-64 p-3 text-sm"
      style={{
        left: pos.x + CURSOR_OFFSET.x,
        top: pos.y + CURSOR_OFFSET.y,
        color: "var(--atlas-text)",
      }}
    >
      <div className="mb-1 truncate font-medium">{hoveredRawId}</div>
      <div className="flex flex-wrap gap-2 text-xs" style={{ color: "var(--atlas-text-dim)" }}>
        <span>{data.claims.length} claim{data.claims.length === 1 ? "" : "s"}</span>
        <span>{data.unknowns_count} unknown{data.unknowns_count === 1 ? "" : "s"}</span>
        <span>{data.edges_in.length} in / {data.edges_out.length} out</span>
      </div>
      {data.claims.length === 0 && (
        <div className="mt-1 text-xs" style={{ color: "var(--atlas-text-dim)" }}>
          not yet reviewed
        </div>
      )}
    </div>
  );
}
