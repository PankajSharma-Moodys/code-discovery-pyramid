import { beforeEach, describe, expect, it } from "vitest";
import { getAuthToken } from "../api/authToken.ts";
import { serializeTarget, useControlRoomStore } from "./controlRoomStore.ts";

const initialState = useControlRoomStore.getState();

beforeEach(() => {
  useControlRoomStore.getState().setAuthToken(null);
  useControlRoomStore.setState(initialState, true);
});

describe("serializeTarget", () => {
  it("serializes each target shape to the /api/run target= form", () => {
    expect(serializeTarget({ kind: "wave-all" })).toBe("wave-all");
    expect(serializeTarget({ kind: "stale-only" })).toBe("stale-only");
    expect(serializeTarget({ kind: "scope", node: "root/foo" })).toBe("scope:root/foo");
    expect(serializeTarget({ kind: "wave", wave: 2 })).toBe("wave:2");
  });
});

describe("controlRoomStore", () => {
  it("defaults to wave-all with resume on", () => {
    expect(useControlRoomStore.getState().dispatchTarget).toEqual({ kind: "wave-all" });
    expect(useControlRoomStore.getState().resume).toBe(true);
  });

  it("setDispatchTarget/setResume/setRefreshMode update state", () => {
    useControlRoomStore.getState().setDispatchTarget({ kind: "wave", wave: 3 });
    useControlRoomStore.getState().setResume(false);
    useControlRoomStore.getState().setRefreshMode("full");

    const state = useControlRoomStore.getState();
    expect(state.dispatchTarget).toEqual({ kind: "wave", wave: 3 });
    expect(state.resume).toBe(false);
    expect(state.refreshMode).toBe("full");
  });

  it("setAuthToken persists to and clears from storage", () => {
    useControlRoomStore.getState().setAuthToken("secret-token");
    expect(useControlRoomStore.getState().authToken).toBe("secret-token");
    expect(getAuthToken()).toBe("secret-token");

    useControlRoomStore.getState().setAuthToken(null);
    expect(useControlRoomStore.getState().authToken).toBeNull();
    expect(getAuthToken()).toBeNull();
  });
});
