import { describe, expect, it } from "vitest";
import { dominantConfidence } from "./confidence.ts";

describe("dominantConfidence", () => {
  it("is unreviewed with no claims", () => {
    expect(dominantConfidence([])).toBe("unreviewed");
  });

  it("is high when every claim is high", () => {
    expect(dominantConfidence(["high", "high"])).toBe("high");
  });

  it("most-conservative-wins: one low claim drags a mostly-high node down", () => {
    expect(dominantConfidence(["high", "high", "low"])).toBe("low");
  });

  it("contested outranks even low as the worst bucket", () => {
    expect(dominantConfidence(["low", "contested", "high"])).toBe("contested");
  });

  it("ignores unrecognized confidence strings rather than crashing", () => {
    expect(dominantConfidence(["bogus", "medium"])).toBe("medium");
  });
});
