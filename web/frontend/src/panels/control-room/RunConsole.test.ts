import { describe, expect, it } from "vitest";
import { scopeLabel } from "./RunConsole.tsx";

/** Inputs are the real scope node ids this repo's own `partition` artifact
 * produces (read off the running backend), not invented shapes. */
describe("scopeLabel", () => {
  it("unfolds a `(name+N)` roll-up into something readable", () => {
    expect(scopeLabel("root/(agent_adapter+5)")).toBe("agent_adapter +5 more");
    expect(scopeLabel("root/(files+5)")).toBe("files +5 more");
  });

  it("keeps the path when the roll-up is nested under one", () => {
    expect(scopeLabel("root/docs/functionality/(anchoring-diffs+5)")).toBe(
      "docs/functionality/anchoring-diffs +5 more",
    );
  });

  it("drops the parens on a single-child scope", () => {
    expect(scopeLabel("root/cdp/(files)")).toBe("cdp/files");
    expect(scopeLabel("root/tests/(files)")).toBe("tests/files");
  });

  it("passes plain scope ids through, minus the `root/` prefix", () => {
    expect(scopeLabel("root/PHASE")).toBe("PHASE");
    expect(scopeLabel("root/tests/fixtures/minirepo/core")).toBe("tests/fixtures/minirepo/core");
  });

  it("leaves an id it does not recognise alone rather than mangling it", () => {
    expect(scopeLabel("weird-id")).toBe("weird-id");
  });
});
