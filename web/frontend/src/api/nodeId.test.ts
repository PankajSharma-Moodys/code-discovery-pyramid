import { describe, expect, it } from "vitest";
import { toNodeId } from "./nodeId.ts";

describe("toNodeId", () => {
  it("prefixes L3 raw ids with module:", () => {
    expect(toNodeId("L3", "(root)")).toBe("module:(root)");
  });

  it("prefixes L2 raw ids with scope:", () => {
    expect(toNodeId("L2", "root/foo")).toBe("scope:root/foo");
  });

  it("prefixes L1 raw ids with file:", () => {
    expect(toNodeId("L1", "src/app.py")).toBe("file:src/app.py");
  });
});
