import { describe, expect, it } from "vitest";
import { buildView, type FlowPayload } from "./flowModel.ts";
import { layoutFlow } from "./flowLayout.ts";

const P: FlowPayload = {
  groups: [
    { id: "src", label: "Routes", role: "source", count: 1 },
    { id: "a", label: "a", role: "transform", count: 2 },
    { id: "b", label: "b", role: "transform", count: 1 },
    { id: "sink", label: "Tables", role: "sink", count: 2 },
  ],
  nodes: [
    { id: "r", label: "r", kind: "route", role: "source", group: "src" },
    { id: "a1", label: "a1", kind: "module", role: "transform", group: "a" },
    { id: "a2", label: "a2", kind: "module", role: "transform", group: "a" },
    { id: "b1", label: "b1", kind: "module", role: "transform", group: "b" },
    { id: "t1", label: "t1", kind: "table", role: "sink", group: "sink" },
    { id: "t2", label: "t2", kind: "table", role: "sink", group: "sink" },
  ],
  edges: [
    { source: "r", target: "a1", kind: "http_in", count: 1 },
    { source: "a1", target: "t1", kind: "persist", count: 1 },  // short path: t1 would sit mid-graph
    { source: "a2", target: "b1", kind: "call", count: 1 },
    { source: "b1", target: "t2", kind: "persist", count: 1 },
  ],
};

const overlaps = (p: { x: number; y: number; width: number; height: number }, q: typeof p) =>
  p.x < q.x + q.width && q.x < p.x + p.width && p.y < q.y + q.height && q.y < p.y + p.height;

describe("layoutFlow", () => {
  it("sources are leftmost, sinks rightmost, top-level boxes never overlap", () => {
    const m = buildView(P, new Set());
    const box = layoutFlow(m);
    const xs = (role: string) => m.nodes.filter((n) => n.role === role).map((n) => box.get(n.id)!.x);
    expect(Math.max(...xs("source"))).toBeLessThan(Math.min(...xs("transform")));
    expect(Math.min(...xs("sink"))).toBeGreaterThan(Math.max(...xs("transform")));
    const tops = m.nodes.map((n) => box.get(n.id)!);
    for (let i = 0; i < tops.length; i++) for (let j = i + 1; j < tops.length; j++) expect(overlaps(tops[i], tops[j])).toBe(false);
  });

  it("expanded container encloses its members", () => {
    const m = buildView(P, new Set(["a"]));
    const box = layoutFlow(m);
    const c = box.get("a")!;
    for (const id of ["a1", "a2"]) {
      const b = box.get(id)!;
      expect(b.x).toBeGreaterThanOrEqual(c.x);
      expect(b.y).toBeGreaterThanOrEqual(c.y);
      expect(b.x + b.width).toBeLessThanOrEqual(c.x + c.width);
      expect(b.y + b.height).toBeLessThanOrEqual(c.y + c.height);
    }
  });

  it.each([["a"], ["a", "b"], ["src", "a", "b", "sink"]])("expanded %s: top-level units (incl. containers) don't overlap; ends stay pinned", (...ex) => {
    const m = buildView(P, new Set(ex));
    const box = layoutFlow(m);
    const tops = m.nodes.filter((n) => n.parent === null);
    for (let i = 0; i < tops.length; i++)
      for (let j = i + 1; j < tops.length; j++)
        expect(overlaps(box.get(tops[i].id)!, box.get(tops[j].id)!), `${tops[i].id} vs ${tops[j].id}`).toBe(false);
    const xs = (role: string) => tops.filter((n) => n.role === role).map((n) => box.get(n.id)!.x);
    expect(Math.max(...xs("source"))).toBeLessThan(Math.min(...xs("transform")));
    expect(Math.min(...xs("sink"))).toBeGreaterThan(Math.max(...xs("transform")));
  });
});
