import { create } from "zustand";
import type { Altitude } from "../api/nodeId.ts";

/** `WEB_RESEARCH.md` §3's lens segmented control. Only Structure,
 * Divergence and Confidence ship this cycle -- Freshness needs the backend
 * churn cache (`PLAN.md` item 3b) and is out of scope for the frontend
 * pass this cycle covers. */
export type Lens = "structure" | "divergence" | "confidence";

/** Wheel-driven altitude change crosses this many accumulated `deltaY`
 * pixels before firing -- large enough that a single trackpad flick or
 * mouse notch doesn't jump an altitude by accident. */
const WHEEL_THRESHOLD = 320;

const DESCEND_ORDER: Record<Altitude, Altitude | null> = { L3: "L2", L2: "L1", L1: null };
const ASCEND_ORDER: Record<Altitude, Altitude | null> = { L1: "L2", L2: "L3", L3: null };

interface AtlasState {
  altitude: Altitude;
  /** Raw (un-namespaced) graph id this altitude is scoped/filtered to, or
   * `null` for the unscoped root view. */
  scope: string | null;
  hoveredNodeId: string | null;
  selectedNodeId: string | null;
  wheelAccumulator: number;
  activeTraceEntry: string | null;
  lens: Lens;
  /** Time scrubber's most recent `/api/diff` result, by (L3) module id --
   * `AtlasCanvas` pulses/fades matching nodes on the next render, then the
   * scrubber clears this after the pulse animation finishes. `null` means
   * no scrub is in flight. */
  diffHighlight: { added: string[]; removed: string[] } | null;

  descend: (rawNodeId: string) => void;
  ascend: () => void;
  jumpTo: (altitude: Altitude) => void;
  selectNode: (id: string | null) => void;
  hoverNode: (id: string | null) => void;
  startTrace: (entry: string) => void;
  clearTrace: () => void;
  setLens: (lens: Lens) => void;
  setDiffHighlight: (highlight: { added: string[]; removed: string[] } | null) => void;
  /** Accumulates a wheel gesture's `deltaY`; returns the altitude change
   * (if the threshold was crossed this call) so the caller can also drive
   * a crossfade, without the store owning animation concerns itself. */
  accumulateWheel: (deltaY: number) => "descend" | "ascend" | null;
}

export const useAtlasStore = create<AtlasState>((set, get) => ({
  altitude: "L3",
  scope: null,
  hoveredNodeId: null,
  selectedNodeId: null,
  wheelAccumulator: 0,
  activeTraceEntry: null,
  lens: "structure",
  diffHighlight: null,

  descend: (rawNodeId) =>
    set((state) => {
      const next = DESCEND_ORDER[state.altitude];
      if (!next) return {};
      return { altitude: next, scope: rawNodeId, selectedNodeId: null, wheelAccumulator: 0 };
    }),

  ascend: () =>
    set((state) => {
      const next = ASCEND_ORDER[state.altitude];
      if (!next) return {};
      return { altitude: next, scope: null, selectedNodeId: null, wheelAccumulator: 0 };
    }),

  jumpTo: (altitude) => set({ altitude, scope: null, selectedNodeId: null, wheelAccumulator: 0 }),

  selectNode: (id) => set({ selectedNodeId: id }),
  hoverNode: (id) => set({ hoveredNodeId: id }),

  startTrace: (entry) => set({ activeTraceEntry: entry }),
  clearTrace: () => set({ activeTraceEntry: null }),
  setLens: (lens) => set({ lens }),
  setDiffHighlight: (highlight) => set({ diffHighlight: highlight }),

  accumulateWheel: (deltaY) => {
    const total = get().wheelAccumulator + deltaY;
    if (total >= WHEEL_THRESHOLD) {
      set({ wheelAccumulator: 0 });
      const next = DESCEND_ORDER[get().altitude];
      if (next) set({ altitude: next, scope: null });
      return "descend";
    }
    if (total <= -WHEEL_THRESHOLD) {
      set({ wheelAccumulator: 0 });
      const next = ASCEND_ORDER[get().altitude];
      if (next) set({ altitude: next, scope: null });
      return "ascend";
    }
    set({ wheelAccumulator: total });
    return null;
  },
}));
