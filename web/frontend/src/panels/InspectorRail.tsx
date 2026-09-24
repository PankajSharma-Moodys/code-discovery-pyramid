import { useState } from "react";
import { useNodeAt, useSourceFile } from "../api/hooks.ts";
import type { Altitude } from "../api/nodeId.ts";
import { confidenceColor, type ConfidenceBucket } from "../theme/confidence.ts";

interface InspectorRailProps {
  altitude: Altitude;
  selectedRawId: string | null;
  /** Server-resolved namespaced id -- see `PeekCard`'s equivalent. `null` for
   * an L3 package super-node. */
  selectedApiNodeId: string | null;
  onClose: () => void;
}

/** Pinned on click (vs. `PeekCard`'s hover-follow). Every evidence row is a
 * button that fetches the real file content via `/api/source` -- "show in
 * code" is this pane, not a separate route, so a claim's anchor is always
 * one click from the actual bytes it cites. */
export function InspectorRail({
  altitude,
  selectedRawId,
  selectedApiNodeId,
  onClose,
}: InspectorRailProps) {
  const { data: node, error, isLoading, refetch } = useNodeAt(altitude, null, selectedApiNodeId);
  const [openEvidence, setOpenEvidence] = useState<{ file: string; line: number } | null>(null);
  const { data: source } = useSourceFile(openEvidence?.file ?? null, openEvidence?.line ?? null);

  if (!selectedRawId) return null;

  return (
    // `pointer-events-none` on the panel + `pointer-events-auto` on the
    // actual controls below: this panel opens synchronously on select, so a
    // node positioned under its footprint would otherwise have the second
    // click of a double-click gesture intercepted by blank rail padding
    // instead of reaching the canvas underneath (confirmed live via
    // `document.elementFromPoint` -- the rail, not Sigma's MouseCaptor, was
    // eating the click).
    <div
      className="pointer-events-none absolute right-0 top-0 z-20 flex h-full w-96 flex-col border-l p-4 text-sm backdrop-blur-md"
      style={{
        background: "color-mix(in srgb, var(--atlas-bg-1) 92%, transparent)",
        borderColor: "var(--atlas-border)",
        color: "var(--atlas-text)",
        boxShadow: "var(--atlas-elev-2)",
      }}
    >
      <div className="pointer-events-auto mb-3 flex items-start justify-between gap-2">
        <div className="truncate font-medium">{selectedRawId}</div>
        <button onClick={onClose} className="text-xs" style={{ color: "var(--atlas-text-dim)" }}>
          close
        </button>
      </div>

      {!selectedApiNodeId && !node && (
        <div style={{ color: "var(--atlas-text-dim)" }}>
          This is a group of nodes, not a single one — double-click it on the canvas to open what's inside.
        </div>
      )}

      {selectedApiNodeId && isLoading && (
        <div style={{ color: "var(--atlas-text-dim)" }}>loading…</div>
      )}

      {selectedApiNodeId && !isLoading && error != null && (
        <div className="pointer-events-auto">
          <div className="mb-2" style={{ color: "var(--atlas-contested)" }}>
            Couldn't load this node — {error instanceof Error ? error.message : "request failed"}.
          </div>
          <button
            onClick={() => refetch()}
            className="rounded border px-2 py-1 text-xs"
            style={{ borderColor: "var(--atlas-border)" }}
          >
            retry
          </button>
        </div>
      )}

      {selectedApiNodeId && !isLoading && error == null && !node && (
        <div style={{ color: "var(--atlas-text-dim)" }}>Not found.</div>
      )}

      {node && (
        <>
          <div className="mb-2 text-xs" style={{ color: "var(--atlas-text-dim)" }}>
            {node.unknowns_count} unknown{node.unknowns_count === 1 ? "" : "s"} ·{" "}
            {node.edges_in.length} in / {node.edges_out.length} out
          </div>

          <div className="mb-1 font-medium">Claims</div>
          {node.claims.length === 0 && (
            <div className="mb-3 text-xs" style={{ color: "var(--atlas-text-dim)" }}>
              0 claims — not yet reviewed.
            </div>
          )}
          <ul className="pointer-events-auto mb-3 space-y-2 overflow-y-auto">
            {node.claims.map((claim, i) => (
              <li key={i} className="rounded border p-2" style={{ borderColor: "var(--atlas-border)" }}>
                <div className="flex items-center justify-between">
                  <span className="truncate">{claim.subject}</span>
                  <span
                    className="ml-2 shrink-0 rounded px-1.5 py-0.5 text-[10px]"
                    style={{ color: confidenceColor(claim.confidence as ConfidenceBucket) }}
                  >
                    {claim.confidence}
                  </span>
                </div>
                <div className="mt-1 text-xs" style={{ color: "var(--atlas-text-dim)" }}>
                  {claim.kind}
                </div>
                <div className="mt-1 flex flex-wrap gap-1">
                  {claim.evidence.map((ev, j) => (
                    <button
                      key={j}
                      onClick={() => setOpenEvidence({ file: ev.file, line: ev.line })}
                      className="rounded border px-1.5 py-0.5 text-[11px]"
                      style={{ borderColor: "var(--atlas-border)" }}
                    >
                      {ev.file}:{ev.line}
                    </button>
                  ))}
                </div>
              </li>
            ))}
          </ul>

          {openEvidence && (
            <div className="pointer-events-auto flex min-h-0 flex-1 flex-col">
              <div className="mb-1 text-xs" style={{ color: "var(--atlas-text-dim)" }}>
                {openEvidence.file}:{openEvidence.line}
              </div>
              <pre
                className="min-h-0 flex-1 overflow-auto rounded border p-2 font-mono text-xs"
                style={{ borderColor: "var(--atlas-border)", background: "var(--atlas-bg-0)" }}
              >
                {source?.lines.map((line, idx) => {
                  const lineNo = (source.start_line ?? 1) + idx;
                  const isTarget = lineNo === openEvidence.line;
                  return (
                    <div
                      key={idx}
                      style={{ background: isTarget ? "color-mix(in srgb, var(--atlas-accent) 20%, transparent)" : undefined }}
                    >
                      {lineNo} {line}
                    </div>
                  );
                }) ?? "loading…"}
              </pre>
            </div>
          )}
        </>
      )}
    </div>
  );
}
