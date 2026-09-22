import { beforeEach, describe, expect, it } from "vitest";
import { useAtlasStore } from "./atlasStore.ts";

const initialState = useAtlasStore.getState();

beforeEach(() => {
  useAtlasStore.setState(initialState, true);
});

describe("descend / ascend", () => {
  it("descends L3 -> L2 -> L1 and stops at the floor", () => {
    useAtlasStore.getState().descend("mod-a");
    expect(useAtlasStore.getState().altitude).toBe("L2");
    expect(useAtlasStore.getState().scope).toBe("mod-a");

    useAtlasStore.getState().descend("scope-b");
    expect(useAtlasStore.getState().altitude).toBe("L1");

    useAtlasStore.getState().descend("file-c");
    expect(useAtlasStore.getState().altitude).toBe("L1");
  });

  it("ascends L1 -> L2 -> L3 and stops at the ceiling, clearing scope", () => {
    useAtlasStore.setState({ altitude: "L1", scope: "some-scope" });

    useAtlasStore.getState().ascend();
    expect(useAtlasStore.getState().altitude).toBe("L2");
    expect(useAtlasStore.getState().scope).toBeNull();

    useAtlasStore.getState().ascend();
    expect(useAtlasStore.getState().altitude).toBe("L3");

    useAtlasStore.getState().ascend();
    expect(useAtlasStore.getState().altitude).toBe("L3");
  });

  it("jumpTo resets scope and selection regardless of current altitude", () => {
    useAtlasStore.setState({ altitude: "L1", scope: "x", selectedNodeId: "n1" });
    useAtlasStore.getState().jumpTo("L2");
    const state = useAtlasStore.getState();
    expect(state.altitude).toBe("L2");
    expect(state.scope).toBeNull();
    expect(state.selectedNodeId).toBeNull();
  });
});

describe("accumulateWheel", () => {
  it("does not fire below the threshold", () => {
    const result = useAtlasStore.getState().accumulateWheel(100);
    expect(result).toBeNull();
    expect(useAtlasStore.getState().altitude).toBe("L3");
  });

  it("descends once accumulated deltaY crosses the threshold and resets the accumulator", () => {
    useAtlasStore.getState().accumulateWheel(200);
    const result = useAtlasStore.getState().accumulateWheel(150);
    expect(result).toBe("descend");
    expect(useAtlasStore.getState().altitude).toBe("L2");
    expect(useAtlasStore.getState().wheelAccumulator).toBe(0);
  });

  it("ascends on a large negative accumulated deltaY", () => {
    useAtlasStore.setState({ altitude: "L1" });
    const result = useAtlasStore.getState().accumulateWheel(-400);
    expect(result).toBe("ascend");
    expect(useAtlasStore.getState().altitude).toBe("L2");
  });

  it("stays at L3 when the threshold fires past the ceiling", () => {
    const result = useAtlasStore.getState().accumulateWheel(-400);
    expect(result).toBe("ascend");
    expect(useAtlasStore.getState().altitude).toBe("L3");
  });
});
