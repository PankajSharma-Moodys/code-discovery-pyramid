/** Pure Flow-tab model over the `/api/flow` payload (spec
 * 2026-10-08-flow-tab-design.md): which boxes are visible for a given set of
 * expanded groups, the aggregated edges between them, and click-trace. Kept
 * free of React so every rule is unit-testable. */
export type FlowRole = "source" | "transform" | "sink";

export interface FlowPayload {
  nodes: { id: string; label: string; kind: string; role: FlowRole; group: string; node_id?: string | null }[];
  groups: { id: string; label: string; role: FlowRole; count: number }[];
  edges: { source: string; target: string; kind: string; count: number }[];
}

export interface ViewNode {
  id: string;
  label: string;
  role: FlowRole;
  /** A collapsed group box (click expands). */
  isGroup: boolean;
  /** An expanded group's frame; members point at it via `parent`. */
  isContainer: boolean;
  count: number;
  parent: string | null;
  apiNodeId: string | null;
}

export interface ViewEdge {
  id: string;
  source: string;
  target: string;
  count: number;
  kinds: Record<string, number>;
}

export interface FlowViewModel {
  nodes: ViewNode[];
  edges: ViewEdge[];
}

export function buildView(p: FlowPayload, expanded: ReadonlySet<string>): FlowViewModel {
  const groupOf = new Map(p.nodes.map((n) => [n.id, n.group]));
  const visible = (id: string) => {
    const g = groupOf.get(id) ?? id;
    return expanded.has(g) ? id : g;
  };
  const nodes: ViewNode[] = [];
  for (const g of p.groups) {
    const open = expanded.has(g.id);
    nodes.push({ id: g.id, label: g.label, role: g.role, isGroup: !open, isContainer: open,
                 count: g.count, parent: null, apiNodeId: null });
    if (!open) continue;
    for (const n of p.nodes.filter((m) => m.group === g.id)) {
      nodes.push({ id: n.id, label: n.label, role: n.role, isGroup: false, isContainer: false,
                   count: 1, parent: g.id, apiNodeId: n.node_id ?? null });
    }
  }
  const agg = new Map<string, ViewEdge>();
  for (const e of p.edges) {
    const s = visible(e.source);
    const t = visible(e.target);
    if (s === t) continue;
    const id = `${s}->${t}`;
    const cur = agg.get(id) ?? { id, source: s, target: t, count: 0, kinds: {} };
    cur.count += e.count;
    cur.kinds[e.kind] = (cur.kinds[e.kind] ?? 0) + e.count;
    agg.set(id, cur);
  }
  return { nodes, edges: [...agg.values()] };
}

export function trace(edges: ViewEdge[], start: string): { upstream: Set<string>; downstream: Set<string> } {
  const walk = (next: (e: ViewEdge) => [string, string]) => {
    const seen = new Set<string>();
    const queue = [start];
    while (queue.length) {
      const cur = queue.shift()!;
      for (const e of edges) {
        const [from, to] = next(e);
        if (from === cur && to !== start && !seen.has(to)) {
          seen.add(to);
          queue.push(to);
        }
      }
    }
    return seen;
  };
  return { downstream: walk((e) => [e.source, e.target]), upstream: walk((e) => [e.target, e.source]) };
}
