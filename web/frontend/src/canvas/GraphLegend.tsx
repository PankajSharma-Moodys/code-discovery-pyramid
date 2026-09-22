import { useState } from "react";
import type { Lens } from "../store/atlasStore.ts";
import { confidenceColor, type ConfidenceBucket } from "../theme/confidence.ts";
import {
  EDGE_KIND_LABEL,
  FAMILY_CAPTION,
  FAMILY_LABEL,
  FAMILY_VAR,
  SHAPE_GLYPH,
  shapeOf,
  type Family,
} from "../theme/graphEncoding.ts";

export interface LegendEntry {
  type: string;
  label: string;
  family: string;
  count: number;
}

interface GraphLegendProps {
  lens: Lens;
  entries: LegendEntry[];
  edgeKinds: { kind: string; count: number }[];
  confidenceCounts: Partial<Record<ConfidenceBucket, number>>;
  divergence?: { declared_edges?: number; observed_edges?: number; declared_not_observed?: unknown[]; observed_not_declared?: unknown[] } | null;
  shapesResolved: boolean;
  /** How many nodes on this altitude carry a `test` role -- `0` hides the
   * toggle entirely rather than offering a control with nothing to do. */
  testNodeCount: number;
  hideTests: boolean;
  onToggleHideTests: (next: boolean) => void;
  /** `true` once the toggle crossed `ROLE_HIDE_CLIENT_THRESHOLD` and is
   * refetching a server-filtered graph instead of dimming client-side. */
  usingServerFilter: boolean;
}

const FAMILY_ORDER: Family[] = ["code", "runtime", "state"];

/**
 * The key for whatever the active lens is currently colouring.
 *
 * `ATLAS_REDESIGN.md` §5's complaint about the tiles applies doubly here: a
 * canvas that recolours on a lens switch and never says what the new colours
 * mean is worse than one that never recolours. Each section answers a
 * question rather than naming an internal concept.
 *
 * §7's stress test requires one more thing: shape stops resolving when zoomed
 * out, and the legend has to *say so* rather than let shape silently fail as
 * the primary identity channel. That is `shapesResolved`.
 */
export function GraphLegend({
  lens,
  entries,
  edgeKinds,
  confidenceCounts,
  divergence,
  shapesResolved,
  testNodeCount,
  hideTests,
  onToggleHideTests,
  usingServerFilter,
}: GraphLegendProps) {
  const [open, setOpen] = useState(true);

  const byFamily = new Map<Family, LegendEntry[]>();
  for (const entry of entries) {
    const family = (entry.family as Family) ?? "code";
    if (!byFamily.has(family)) byFamily.set(family, []);
    byFamily.get(family)!.push(entry);
  }

  return (
    <div
      // Top-right, not bottom-left: `TracePanel` owns the bottom-left corner
      // and was clipping the family list off the bottom of this card, which
      // is exactly the failure mode this card exists to prevent.
      className="atlas-card absolute right-3 top-14 z-10 flex max-h-[calc(100%-4.5rem)] w-72 flex-col overflow-hidden text-xs"
      style={{ color: "var(--atlas-text)" }}
    >
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex w-full shrink-0 items-center justify-between px-3 py-2 text-left"
        style={{ color: "var(--atlas-text)" }}
      >
        <span className="font-medium">{LENS_TITLE[lens]}</span>
        <span style={{ color: "var(--atlas-text-dim)" }}>{open ? "hide" : "show"}</span>
      </button>

      {open && (
        <div className="flex flex-col gap-3 overflow-y-auto px-3 pb-3">
          <p style={{ color: "var(--atlas-text-dim)" }}>{LENS_CAPTION[lens]}</p>

          {testNodeCount > 0 && (
            <button
              onClick={() => onToggleHideTests(!hideTests)}
              className="flex items-center justify-between gap-2 rounded-md px-2 py-1.5 text-left transition-colors"
              style={{
                background: hideTests ? "color-mix(in srgb, var(--atlas-accent) 14%, transparent)" : "transparent",
                border: `1px solid ${hideTests ? "var(--atlas-accent)" : "var(--atlas-border)"}`,
              }}
              aria-pressed={hideTests}
            >
              <span className="flex flex-col">
                <span className="font-medium" style={{ color: "var(--atlas-text)" }}>
                  Hide tests
                </span>
                <span style={{ color: "var(--atlas-text-dim)" }}>
                  {testNodeCount} node{testNodeCount === 1 ? "" : "s"}
                  {usingServerFilter ? " — refetching filtered graph" : ""}
                </span>
              </span>
              <span
                className="relative h-4 w-7 shrink-0 rounded-full transition-colors"
                style={{ background: hideTests ? "var(--atlas-accent)" : "var(--atlas-border)" }}
              >
                <span
                  className="absolute top-0.5 h-3 w-3 rounded-full bg-white transition-transform"
                  style={{ transform: hideTests ? "translateX(0.85rem)" : "translateX(0.15rem)" }}
                />
              </span>
            </button>
          )}

          {lens !== "confidence" &&
            FAMILY_ORDER.filter((family) => byFamily.has(family)).map((family) => (
              <div key={family}>
                <div className="flex items-center gap-2">
                  <span
                    className="inline-block h-2.5 w-2.5 rounded-full"
                    style={{ background: `var(${FAMILY_VAR[family]})` }}
                  />
                  <span className="font-medium">{FAMILY_LABEL[family]}</span>
                </div>
                <div className="mt-0.5 pl-[18px]" style={{ color: "var(--atlas-text-dim)" }}>
                  {FAMILY_CAPTION[family]}
                </div>
                <div className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5 pl-[18px]">
                  {byFamily.get(family)!.map((entry) => (
                    <span key={entry.type} style={{ color: "var(--atlas-text-dim)" }}>
                      <span style={{ color: `var(${FAMILY_VAR[family]})` }}>
                        {SHAPE_GLYPH[shapeOf(entry.type)]}
                      </span>{" "}
                      {entry.label} {entry.count}
                    </span>
                  ))}
                </div>
              </div>
            ))}

          {lens === "flow" && edgeKinds.length > 0 && (
            <div>
              <div className="font-medium">Edges, by how the call was found</div>
              <div className="mt-1 flex flex-col gap-0.5" style={{ color: "var(--atlas-text-dim)" }}>
                {edgeKinds.map(({ kind, count }) => (
                  <div key={kind} className="flex items-center justify-between gap-2">
                    <span>{EDGE_KIND_LABEL[kind] ?? kind}</span>
                    <span className="font-mono">{count}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {lens === "confidence" && (
            <div>
              <div className="font-medium">How sure CDP is about each node</div>
              <div className="mt-1 flex flex-col gap-0.5">
                {CONFIDENCE_ROWS.map(({ bucket, label, glyph }) => (
                  <div key={bucket} className="flex items-center justify-between gap-2">
                    <span style={{ color: "var(--atlas-text-dim)" }}>
                      <span style={{ color: confidenceColor(bucket) }}>{glyph}</span> {label}
                    </span>
                    <span className="font-mono" style={{ color: "var(--atlas-text-dim)" }}>
                      {confidenceCounts[bucket] ?? 0}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {lens !== "confidence" && (
            <p style={{ color: "var(--atlas-text-dim)" }}>
              Ring colour is claim confidence; size is how many edges touch the node.
            </p>
          )}

          {!shapesResolved && (
            <p style={{ color: "var(--atlas-inferred)" }}>
              Zoomed out — every node is drawn as a dot. Colour and size still apply; zoom in to
              tell types apart by shape.
            </p>
          )}

          {divergence && (divergence.declared_edges ?? 0) + (divergence.observed_edges ?? 0) > 0 && (
            <p style={{ color: "var(--atlas-text-dim)" }}>
              Declared vs observed: {divergence.declared_edges ?? 0} declared,{" "}
              {divergence.observed_edges ?? 0} observed,{" "}
              {(divergence.declared_not_observed?.length ?? 0) +
                (divergence.observed_not_declared?.length ?? 0)}{" "}
              disagree.
            </p>
          )}
        </div>
      )}
    </div>
  );
}

const LENS_TITLE: Record<Lens, string> = {
  structure: "What colour means: where code lives",
  flow: "What colour means: how things connect",
  confidence: "What colour means: how sure we are",
};

const LENS_CAPTION: Record<Lens, string> = {
  structure:
    "Fill is the node's family, shape is its type, and every edge takes the colour of what it reaches — so the map reads as code reaching through boundaries into state.",
  flow: "Edges are coloured by the channel they were extracted from — how CDP knows the connection exists.",
  confidence:
    "Each node takes the colour of its least-confident claim. A node with no claim is unreviewed, not wrong.",
};

const CONFIDENCE_ROWS: { bucket: ConfidenceBucket; label: string; glyph: string }[] = [
  { bucket: "high", label: "high — corroborated", glyph: "✓" },
  { bucket: "medium", label: "medium — inferred", glyph: "~" },
  { bucket: "low", label: "low — weak evidence", glyph: "?" },
  { bucket: "contested", label: "contested — sources disagree", glyph: "✕" },
  { bucket: "unreviewed", label: "unreviewed — no claim yet", glyph: "·" },
];
