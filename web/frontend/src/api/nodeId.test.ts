import { describe, expect, it } from "vitest";
import { toNodeId } from "./nodeId.ts";

/** `toNodeId` is now the *fallback* path only. Since ATLAS_REDESIGN.md P0,
 * L2 raw ids are `dataflow` endpoints whose namespace depends on
 * `xref.symbols`, which the client cannot see -- the server resolves them and
 * ships the answer as `GraphNodeResponse.node_id`, which the canvas carries
 * through `atlasStore`'s `selectedApiNodeId`. L2's old `scope:` prefix
 * belonged to the `partition`-scope node set that altitude no longer serves. */
describe("toNodeId", () => {
  it("prefixes L3 raw ids with module:", () => {
    expect(toNodeId("L3", "(root)")).toBe("module:(root)");
  });

  it("falls back to module: at L2, where the real id comes from the server", () => {
    expect(toNodeId("L2", "cdp.cli")).toBe("module:cdp.cli");
  });

  it("prefixes L1 raw ids with file:", () => {
    expect(toNodeId("L1", "src/app.py")).toBe("file:src/app.py");
  });
});
