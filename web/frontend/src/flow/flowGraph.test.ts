import { describe, expect, it } from "vitest";
import { toRfEdges, toRfNodes, UPSTREAM, DOWNSTREAM } from "./flowGraph.ts";
import type { ViewNode } from "./flowModel.ts";

const vn = (id: string, o: Partial<ViewNode> = {}): ViewNode => ({
  id, label: id, role: "transform", isGroup: false, isContainer: false, count: 1, parent: null, apiNodeId: null, ...o,
});

describe("flowGraph", () => {
  it("makes child positions parent-relative and puts containers first", () => {
    const nodes = [vn("a", { parent: "c" }), vn("c", { isContainer: true })];
    const boxes = new Map([
      ["a", { x: 130, y: 70, width: 200, height: 40 }],
      ["c", { x: 100, y: 50, width: 300, height: 120 }],
    ]);
    const rf = toRfNodes(nodes, boxes, null, null);
    expect(rf.map((n) => n.id)).toEqual(["c", "a"]);
    expect(rf[1].position).toEqual({ x: 30, y: 20 });
    expect(rf[1].parentId).toBe("c");
    expect(rf[0].position).toEqual({ x: 100, y: 50 });
  });

  it("tints upstream blue and downstream orange, selected keeps role colour", () => {
    const nodes = [vn("u"), vn("s"), vn("d")];
    const boxes = new Map(nodes.map((n) => [n.id, { x: 0, y: 0, width: 10, height: 10 }]));
    const rf = toRfNodes(nodes, boxes, { upstream: new Set(["u"]), downstream: new Set(["d"]) }, "s");
    expect(rf.map((n) => n.data.tint)).toEqual([UPSTREAM, null, DOWNSTREAM]);
  });

  it("colours trace edges and dims the rest", () => {
    const edges = [
      { id: "1", source: "u", target: "s", count: 3, kinds: {} },
      { id: "2", source: "s", target: "d", count: 1, kinds: {} },
      { id: "3", source: "x", target: "y", count: 1, kinds: {} },
    ];
    const tr = { upstream: new Set(["u"]), downstream: new Set(["d"]) };
    const rf = toRfEdges(edges, tr, "s");
    expect(rf[0].style?.stroke).toBe(UPSTREAM);
    expect(rf[1].style?.stroke).toBe(DOWNSTREAM);
    expect(rf[2].style?.opacity).toBe(0.2);
    expect(rf[0].style?.strokeWidth).toBe(3);
  });
});
