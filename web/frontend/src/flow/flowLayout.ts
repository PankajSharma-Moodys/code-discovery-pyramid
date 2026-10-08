import * as dagre from "@dagrejs/dagre";
import type { FlowViewModel, ViewNode } from "./flowModel.ts";

/** dagre LR layout for the Flow tab. dagre can't pin ranks, so after layout
 * every top-level source unit moves to the leftmost column and every sink
 * unit to the rightmost, then each of those columns is re-stacked so nothing
 * overlaps. A "unit" is a top-level node or an expanded container (its
 * members move with it). Returns absolute top-left boxes. */
export interface Box { x: number; y: number; width: number; height: number }

export const NODE_W = 200;
export const NODE_H = 40;
const GAP = 16;
const PAD = 24;
const PAD_TOP = PAD + 8;

export function layoutFlow(model: FlowViewModel): Map<string, Box> {
  const g = new dagre.graphlib.Graph({ compound: true });
  g.setGraph({ rankdir: "LR", nodesep: GAP, ranksep: 90, marginx: PAD, marginy: PAD });
  g.setDefaultEdgeLabel(() => ({}));
  for (const n of model.nodes) g.setNode(n.id, n.isContainer ? {} : { width: NODE_W, height: NODE_H });
  for (const n of model.nodes) if (n.parent) g.setParent(n.id, n.parent);
  for (const e of model.edges) g.setEdge(e.source, e.target);
  dagre.layout(g);

  const box = new Map<string, Box>();
  for (const n of model.nodes) {
    if (n.isContainer) continue;
    const d = g.node(n.id);
    box.set(n.id, { x: d.x - NODE_W / 2, y: d.y - NODE_H / 2, width: NODE_W, height: NODE_H });
  }
  // Container frames are computed here (dagre's cluster sizing ignores padding):
  // bounding box of members plus padding.
  const fitContainers = () => {
    for (const c of model.nodes) {
      if (!c.isContainer) continue;
      const ms = model.nodes.filter((m) => m.parent === c.id).map((m) => box.get(m.id)!);
      if (!ms.length) { box.set(c.id, { x: 0, y: 0, width: NODE_W + 2 * PAD, height: NODE_H + PAD + PAD_TOP }); continue; }
      const x = Math.min(...ms.map((b) => b.x)) - PAD;
      const y = Math.min(...ms.map((b) => b.y)) - PAD_TOP;
      box.set(c.id, {
        x, y,
        width: Math.max(...ms.map((b) => b.x + b.width)) + PAD - x,
        height: Math.max(...ms.map((b) => b.y + b.height)) + PAD - y,
      });
    }
  };
  fitContainers();

  const units = model.nodes.filter((n) => n.parent === null);
  const minX = Math.min(...units.map((n) => box.get(n.id)!.x));
  const maxRight = Math.max(...units.map((n) => box.get(n.id)!.x + box.get(n.id)!.width));
  const move = (n: ViewNode, dx: number, dy: number) => {
    for (const m of model.nodes) {
      if (m.id === n.id || m.parent === n.id) {
        const b = box.get(m.id)!;
        box.set(m.id, { ...b, x: b.x + dx, y: b.y + dy });
      }
    }
  };
  const pin = (role: "source" | "sink") => {
    const col = units.filter((n) => n.role === role);
    for (const n of col) {
      const b = box.get(n.id)!;
      move(n, (role === "source" ? minX : maxRight - b.width) - b.x, 0);
    }
    // Everything already in that column, pinned or not, gets re-stacked.
    const x0 = role === "source" ? minX : maxRight;
    const inCol = units.filter((n) => {
      const b = box.get(n.id)!;
      return role === "source" ? b.x <= x0 + 1 : b.x + b.width >= x0 - 1;
    }).sort((p, q) => box.get(p.id)!.y - box.get(q.id)!.y);
    let nextY = -Infinity;
    for (const n of inCol) {
      const b = box.get(n.id)!;
      const y = Math.max(b.y, nextY);
      move(n, 0, y - b.y);
      nextY = y + b.height + GAP;
    }
  };
  pin("source");
  pin("sink");
  return box;
}
