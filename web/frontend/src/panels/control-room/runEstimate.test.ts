import { describe, expect, it } from "vitest";
import { formatSpend, remainingScopes } from "./runEstimate.ts";

describe("runEstimate", () => {
  it("counts scopes not yet done across waves", () => {
    expect(remainingScopes([{ done: 2, total: 5 }, { done: 0, total: 3 }])).toBe(6);
    expect(remainingScopes([])).toBe(0);
    expect(remainingScopes([{ done: 4, total: 3 }])).toBe(0);
  });
  it("formats spend as an estimate against the cap", () => {
    expect(formatSpend(1.234, 5)).toBe("$1.23 of $5.00 (estimate)");
  });
});
