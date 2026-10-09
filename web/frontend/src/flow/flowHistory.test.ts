import { describe, expect, it } from "vitest";
import { INITIAL_VIEW, popState, pushState, type FlowViewState } from "./flowHistory.ts";

const st = (n: number): FlowViewState => ({ expanded: [`g${n}`], selectedId: null });

describe("flowHistory", () => {
  it("push appends", () => {
    expect(pushState([st(1)], st(2))).toEqual([st(1), st(2)]);
  });
  it("push of an identical state is a no-op", () => {
    const h = [st(1)];
    expect(pushState(h, st(1))).toEqual([st(1)]);
  });
  it("caps at 50, dropping the oldest", () => {
    let h: FlowViewState[] = [];
    for (let i = 0; i < 55; i++) h = pushState(h, st(i));
    expect(h).toHaveLength(50);
    expect(h[0]).toEqual(st(5));
    expect(h[49]).toEqual(st(54));
  });
  it("pop returns last and shrinks", () => {
    expect(popState([st(1), st(2)])).toEqual({ history: [st(1)], state: st(2) });
  });
  it("pop on empty returns null", () => {
    expect(popState([])).toEqual({ history: [], state: null });
  });
  it("INITIAL_VIEW is empty", () => {
    expect(INITIAL_VIEW).toEqual({ expanded: [], selectedId: null });
  });
});
