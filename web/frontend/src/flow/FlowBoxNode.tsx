import { Handle, Position, type NodeProps } from "@xyflow/react";
import type { FlowNodeData } from "./flowGraph.ts";

const ROLE_BORDER = {
  source: "var(--atlas-verified)",
  sink: "var(--atlas-contested)",
  transform: "var(--atlas-border)",
} as const;

/** Leaf or collapsed-group box. */
export function FlowBoxNode({ data }: NodeProps) {
  const { node: n, tint } = data as FlowNodeData;
  return (
    <div
      className="flex h-full w-full items-center justify-between gap-2 rounded px-2 text-xs"
      style={{
        background: "var(--atlas-bg-2)",
        color: "var(--atlas-text)",
        border: `1px solid ${tint ?? ROLE_BORDER[n.role]}`,
        cursor: "pointer",
      }}
      title={n.label}
    >
      <Handle type="target" position={Position.Left} style={{ opacity: 0 }} />
      <span className="truncate">{n.label}</span>
      {n.isGroup && (
        <span className="rounded px-1" style={{ background: "var(--atlas-bg)", color: "var(--atlas-text-dim)" }}>
          +{n.count}
        </span>
      )}
      <Handle type="source" position={Position.Right} style={{ opacity: 0 }} />
    </div>
  );
}

/** Expanded group frame with a header label; clicking it collapses. */
export function FlowContainerNode({ data }: NodeProps) {
  const onCollapse = (data as FlowNodeData).onCollapse;
  const n = (data as FlowNodeData).node;
  return (
    <div
      className="h-full w-full rounded"
      style={{ border: `1px dashed ${ROLE_BORDER[n.role]}`, background: "rgba(127,127,127,0.06)" }}
    >
      <button
        type="button"
        aria-label={`Collapse ${n.label}`}
        className="px-2 py-1 text-left text-xs"
        style={{
          color: "var(--atlas-text-dim)",
          cursor: "pointer",
          font: "inherit",
          background: "transparent",
          border: "none",
        }}
        onClick={(e) => {
          e.stopPropagation();
          onCollapse?.();
        }}
      >
        {n.label} ▾
      </button>
    </div>
  );
}
