import { create } from "zustand";
import { getAuthToken, setAuthToken as persistAuthToken } from "../api/authToken.ts";

/** `POST /api/run`'s `target=` -- mirrors `_run_extra_args` in `web/api/app.py`,
 * which requires exactly one of these four shapes. */
export type DispatchTarget =
  | { kind: "wave-all" }
  | { kind: "stale-only" }
  | { kind: "scope"; node: string }
  | { kind: "wave"; wave: number };

/** Serializes a {@link DispatchTarget} to the `target=` query string
 * `POST /api/run` expects. */
export function serializeTarget(target: DispatchTarget): string {
  switch (target.kind) {
    case "wave-all":
      return "wave-all";
    case "stale-only":
      return "stale-only";
    case "scope":
      return `scope:${target.node}`;
    case "wave":
      return `wave:${target.wave}`;
  }
}

interface ControlRoomState {
  dispatchTarget: DispatchTarget;
  resume: boolean;
  refreshMode: string;
  authToken: string | null;

  setDispatchTarget: (target: DispatchTarget) => void;
  setResume: (resume: boolean) => void;
  setRefreshMode: (mode: string) => void;
  setAuthToken: (token: string | null) => void;
}

export const useControlRoomStore = create<ControlRoomState>((set) => ({
  dispatchTarget: { kind: "wave-all" },
  resume: true,
  refreshMode: "strict",
  authToken: getAuthToken(),

  setDispatchTarget: (dispatchTarget) => set({ dispatchTarget }),
  setResume: (resume) => set({ resume }),
  setRefreshMode: (refreshMode) => set({ refreshMode }),
  setAuthToken: (authToken) => {
    persistAuthToken(authToken);
    set({ authToken });
  },
}));
