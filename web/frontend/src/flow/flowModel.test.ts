import { describe, expect, it } from "vitest";
import { buildView, trace, type FlowPayload } from "./flowModel.ts";

const P: FlowPayload = {
  groups: [
    { id: "group:routes", label: "Routes", role: "source", count: 2 },
    { id: "code:api", label: "api", role: "transform", count: 2 },
    { id: "group:tables", label: "Tables", role: "sink", count: 1 },
  ],
  nodes: [
    { id: "r1", label: "GET /a", kind: "route", role: "source", group: "group:routes", node_id: "route:r1" },
    { id: "r2", label: "GET /b", kind: "route", role: "source", group: "group:routes", node_id: "route:r2" },
    { id: "m1", label: "A", kind: "module", role: "transform", group: "code:api", node_id: "sym:m1" },
    { id: "m2", label: "B", kind: "module", role: "transform", group: "code:api", node_id: "sym:m2" },
    { id: "t1", label: "users", kind: "table", role: "sink", group: "group:tables", node_id: "table:t1" },
  ],
  edges: [
    { source: "r1", target: "m1", kind: "http_in", count: 1 },
    { source: "r2", target: "m2", kind: "http_in", count: 1 },
    { source: "m1", target: "t1", kind: "persist", count: 3 },
    { source: "m2", target: "t1", kind: "persist", count: 2 },
    { source: "m1", target: "m2", kind: "call", count: 1 },
    { source: "m2", target: "m1", kind: "call", count: 1 },
  ],
};

describe("buildView", () => {
  it("collapsed: one box per group, edges aggregated, intra-group dropped", () => {
    const v = buildView(P, new Set());
    expect(v.nodes.map((n) => [n.id, n.isGroup, n.count])).toEqual([
      ["group:routes", true, 2], ["code:api", true, 2], ["group:tables", true, 1],
    ]);
    const persist = v.edges.find((e) => e.source === "code:api" && e.target === "group:tables")!;
    expect(persist.count).toBe(5);
    expect(persist.kinds).toEqual({ persist: 5 });
    expect(v.edges.some((e) => e.source === e.target)).toBe(false);
  });

  it("expanded group becomes a container with member children", () => {
    const v = buildView(P, new Set(["code:api"]));
    const container = v.nodes.find((n) => n.id === "code:api")!;
    expect(container.isContainer).toBe(true);
    expect(v.nodes.filter((n) => n.parent === "code:api").map((n) => n.id)).toEqual(["m1", "m2"]);
    expect(v.edges.find((e) => e.source === "m1" && e.target === "group:tables")?.count).toBe(3);
  });

  it("collapse after expand restores the collapsed view exactly", () => {
    buildView(P, new Set(["code:api"]));
    expect(buildView(P, new Set())).toEqual(buildView(P, new Set()));
    expect(buildView(P, new Set()).nodes.some((n) => n.parent !== null)).toBe(false);
  });
});

describe("trace", () => {
  it("splits upstream/downstream and survives cycles without self-marking", () => {
    const v = buildView(P, new Set(["code:api"]));
    const { upstream, downstream } = trace(v.edges, "m1");
    expect(upstream.has("m1")).toBe(false);
    expect(downstream.has("m1")).toBe(false);
    expect(upstream.has("group:routes")).toBe(true);
    expect(downstream.has("group:tables")).toBe(true);
    expect(downstream.has("m2")).toBe(true); // via call cycle m1 -> m2
  });
});
