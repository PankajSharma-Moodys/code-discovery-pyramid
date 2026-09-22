import { create } from "zustand";

export type View = "atlas" | "control-room" | "links";

/** Lifted out of `App.tsx`'s local `useState` so `AskBar` -- mounted once,
 * shared by both rooms per `WEB_RESEARCH.md` §2 ("same cmd-K, same ask-bar,
 * same theme") -- can switch to the Atlas when a query result routes onto
 * the canvas, without prop-drilling a setter through both view trees. */
interface ViewState {
  view: View;
  setView: (view: View) => void;
}

export const useViewStore = create<ViewState>((set) => ({
  view: "atlas",
  setView: (view) => set({ view }),
}));
