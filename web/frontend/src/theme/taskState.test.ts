import { describe, expect, it } from "vitest";
import { taskStateColor, taskStateStroke } from "./taskState.ts";

describe("taskStateColor", () => {
  it("maps folded to verified/solid", () => {
    expect(taskStateColor("folded")).toBe("var(--atlas-verified)");
    expect(taskStateStroke("folded")).toBe("solid");
  });

  it("maps in-flight states to inferred/dashed", () => {
    for (const state of ["dispatched", "returned", "validated"]) {
      expect(taskStateColor(state)).toBe("var(--atlas-inferred)");
      expect(taskStateStroke(state)).toBe("dashed");
    }
  });

  it("maps retryable failures and abandoned to contested/dotted", () => {
    for (const state of ["expired", "invalid", "anchors_failed", "empty", "abandoned"]) {
      expect(taskStateColor(state)).toBe("var(--atlas-contested)");
      expect(taskStateStroke(state)).toBe("dotted");
    }
  });

  it("maps pending and unrecognized states to text-dim/dotted", () => {
    expect(taskStateColor("pending")).toBe("var(--atlas-text-dim)");
    expect(taskStateColor("something-new")).toBe("var(--atlas-text-dim)");
    expect(taskStateStroke("pending")).toBe("dotted");
  });
});
