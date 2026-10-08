import type { Edge, Node } from "@xyflow/react";
import type { Box } from "./flowLayout.ts";
import type { ViewEdge, ViewNode } from "./flowModel.ts";

export const UPSTREAM = "#5b9bff";
export const DOWNSTREAM = "#ff9f43";
const DIM = 0.2;

export interface FlowNodeData extends Record<string, unknown> {
  node: ViewNode;
}

/** Boxes -> React Flow nodes. Children use parent-relative positions and
 * containers come first (React Flow requires parents before children). */
export function toRfNodes(
  nodes: ViewNode[],
  boxes: Map<string, Box>,
  tr: { upstream: Set<string>; downstream: Set<string> } | null,
  selectedId: string | null,
): Node<FlowNodeData>[] {
  const out = nodes.map((n) => {
    const b = boxes.get(n.id)!;
    const pb = n.parent ? boxes.get(n.parent) : undefined;
    const lit = !tr || n.id === selectedId || tr.upstream.has(n.id) || tr.downstream.has(n.id);
    const node: Node<FlowNodeData> = {
      id: n.id,
      type: n.isContainer ? "group" : "flowBox",
      position: { x: b.x - (pb?.x ?? 0), y: b.y - (pb?.y ?? 0) },
      data: { node: n },
      style: { width: b.width, height: b.height, opacity: lit ? 1 : DIM },
      ...(n.parent ? { parentId: n.parent } : {}),
    };
    return node;
  });
  return out.sort((a, b) => Number(b.type === "group") - Number(a.type === "group"));
}

export function toRfEdges(
  edges: ViewEdge[],
  tr: { upstream: Set<string>; downstream: Set<string> } | null,
  selectedId: string | null,
): Edge[] {
  return edges.map((e) => {
    let stroke: string | undefined;
    let lit = !tr;
    if (tr && selectedId) {
      const up = (id: string) => id === selectedId || tr.upstream.has(id);
      const down = (id: string) => id === selectedId || tr.downstream.has(id);
      if (up(e.source) && up(e.target)) { stroke = UPSTREAM; lit = true; }
      else if (down(e.source) && down(e.target)) { stroke = DOWNSTREAM; lit = true; }
    }
    return {
      id: e.id,
      source: e.source,
      target: e.target,
      data: { edge: e },
      style: { strokeWidth: 1 + Math.log2(e.count + 1), opacity: lit ? 1 : DIM, ...(stroke ? { stroke } : {}) },
    };
  });
}
