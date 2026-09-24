import { beforeEach, describe, expect, it } from "vitest";
import { useAtlasStore } from "./atlasStore.ts";

const initialState = useAtlasStore.getState();

beforeEach(() => {
  useAtlasStore.setState(initialState, true);
});

describe("descend / ascend", () => {
  // The ladder is no longer a fixed L3<->L2 pair: `descend` takes the next
  // rung explicitly (as `AtlasCanvas` would look up from `GraphResponse.rungs`),
  // and pushes a breadcrumb entry rather than overwriting a flat `altitude`.
  it("descends through however many rungs the caller supplies, and stops when there's nowhere further to go", () => {
    useAtlasStore.getState().descend("mod-a", "P2");
    expect(useAtlasStore.getState().altitude).toBe("P2");
    expect(useAtlasStore.getState().scope).toBe("mod-a");

    useAtlasStore.getState().descend("mod-a-sub", "L2");
    expect(useAtlasStore.getState().altitude).toBe("L2");
    expect(useAtlasStore.getState().scope).toBe("mod-a-sub");
  });

  it("ascend pops one breadcrumb at a time, restoring the prior scope rather than clearing it", () => {
    useAtlasStore.getState().descend("mod-a", "P2");
    useAtlasStore.getState().descend("mod-a-sub", "L2");

    useAtlasStore.getState().ascend();
    expect(useAtlasStore.getState().altitude).toBe("P2");
    expect(useAtlasStore.getState().scope).toBe("mod-a");

    useAtlasStore.getState().ascend();
    expect(useAtlasStore.getState().altitude).toBe("L3");
    expect(useAtlasStore.getState().scope).toBeNull();

    useAtlasStore.getState().ascend();
    expect(useAtlasStore.getState().altitude).toBe("L3");
    expect(useAtlasStore.getState().scope).toBeNull();
  });

  it("ascendTo jumps straight back to a chosen breadcrumb, keeping its scope", () => {
    useAtlasStore.getState().descend("mod-a", "P2");
    useAtlasStore.getState().descend("mod-a-sub", "P3");
    useAtlasStore.getState().descend("mod-a-sub-leaf", "L2");

    useAtlasStore.getState().ascendTo(1);
    expect(useAtlasStore.getState().altitude).toBe("P2");
    expect(useAtlasStore.getState().scope).toBe("mod-a");
    expect(useAtlasStore.getState().ladder).toHaveLength(2);
  });

  it("jumpTo resets scope and selection to an unscoped root, discarding the ladder", () => {
    useAtlasStore.getState().descend("mod-a", "P2");
    useAtlasStore.getState().selectNode("n1");

    useAtlasStore.getState().jumpTo("L2");
    const state = useAtlasStore.getState();
    expect(state.altitude).toBe("L2");
    expect(state.scope).toBeNull();
    expect(state.selectedNodeId).toBeNull();
    expect(state.ladder).toHaveLength(1);
  });
});

describe("accumulateWheel", () => {
  it("does not fire below the threshold", () => {
    const result = useAtlasStore.getState().accumulateWheel(100, "L2");
    expect(result).toBeNull();
    expect(useAtlasStore.getState().altitude).toBe("L3");
  });

  it("descends once accumulated deltaY crosses the threshold and resets the accumulator", () => {
    useAtlasStore.getState().accumulateWheel(200, "L2");
    const result = useAtlasStore.getState().accumulateWheel(150, "L2");
    expect(result).toBe("descend");
    expect(useAtlasStore.getState().altitude).toBe("L2");
    expect(useAtlasStore.getState().wheelAccumulator).toBe(0);
  });

  it("is a no-op when the threshold fires with no deeper rung to go to", () => {
    const result = useAtlasStore.getState().accumulateWheel(400, null);
    expect(result).toBeNull();
    expect(useAtlasStore.getState().altitude).toBe("L3");
  });

  it("ascends on a large negative accumulated deltaY", () => {
    useAtlasStore.getState().descend("mod-a", "L2");
    const result = useAtlasStore.getState().accumulateWheel(-400, null);
    expect(result).toBe("ascend");
    expect(useAtlasStore.getState().altitude).toBe("L3");
  });

  it("stays at the root when the threshold fires past the ceiling", () => {
    const result = useAtlasStore.getState().accumulateWheel(-400, null);
    expect(result).toBe("ascend");
    expect(useAtlasStore.getState().altitude).toBe("L3");
  });
});

describe("toggleFocus", () => {
  it("focuses an unfocused node, and clears it on a second toggle of the same id", () => {
    useAtlasStore.getState().toggleFocus("n1");
    expect(useAtlasStore.getState().focusNodeId).toBe("n1");

    useAtlasStore.getState().toggleFocus("n1");
    expect(useAtlasStore.getState().focusNodeId).toBeNull();
  });

  it("switches focus straight to a different node without needing an intermediate clear", () => {
    useAtlasStore.getState().toggleFocus("n1");
    useAtlasStore.getState().toggleFocus("n2");
    expect(useAtlasStore.getState().focusNodeId).toBe("n2");
  });

  it("is cleared by descend/ascend/jumpTo, same as hover/select", () => {
    useAtlasStore.getState().toggleFocus("n1");
    useAtlasStore.getState().descend("mod-a", "L2");
    expect(useAtlasStore.getState().focusNodeId).toBeNull();
  });
});
