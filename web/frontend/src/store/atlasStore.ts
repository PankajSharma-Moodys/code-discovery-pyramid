import { create } from "zustand";
import type { Altitude } from "../api/nodeId.ts";

/** `WEB_RESEARCH.md` §3's lens segmented control.
 *
 * `divergence` was replaced by `flow` in the `ATLAS_REDESIGN.md` pass. The
 * divergence lens coloured edges `declared`/`observed`/`both`, which only
 * `_build_graph_l3`'s old `graph`-artifact edges ever carried -- and that
 * builder was the 7-node/2-edge canvas the redesign removed. Those tags do
 * not exist on the typed `dataflow` edges that replaced them, so the lens
 * would have been a no-op at every altitude. `flow` colours the same edges by
 * extraction channel instead, which is a real signal on the new data. The
 * divergence *counts* are not lost: they are still returned on the L3
 * response and surfaced as a line in the legend.
 *
 * Freshness still needs the backend churn cache (`PLAN.md` item 3b). */
export type Lens = "structure" | "flow" | "confidence";

/** Wheel-driven altitude change crosses this many accumulated `deltaY`
 * pixels before firing -- large enough that a single trackpad flick or
 * mouse notch doesn't jump an altitude by accident. */
const WHEEL_THRESHOLD = 320;

/** The ladder is L3 <-> L2 only.
 *
 * `ATLAS_REDESIGN.md` §7 checked L1 before scheduling work against it and
 * found file-level import extraction yields **2 edges across 413 files**,
 * both in a Java fixture -- Python imports never reach the file graph. §2's
 * instruction for that case is explicit: L1 should be *cut, not styled*. L0
 * is cut for the same reason (2 symbol-scoped edges over 2287 symbols).
 *
 * Neither is deleted from the API: `/api/graph?level=L0` still backs the ask
 * bar's symbol typeahead, and both are still held to the renderable-edge
 * contract (`web/tests/test_graph_contract.py`), so if the backend ever grows
 * real file-level edges they can be put back by extending this record. */
const DESCEND_ORDER: Record<Altitude, Altitude | null> = { L3: "L2", L2: null, L1: null };
const ASCEND_ORDER: Record<Altitude, Altitude | null> = { L1: "L2", L2: "L3", L3: null };

/** Hover and selection are *per altitude*: a node id from L3 means nothing at
 * L2, and leaving it set dims every edge on the new canvas (the edge reducer
 * sees "something is focused" but nothing matches). Sigma's `leaveNode` never
 * fires across an altitude change because the renderer is torn down, so every
 * altitude transition has to clear this explicitly. */
const CLEAR_FOCUS = {
  selectedNodeId: null,
  selectedApiNodeId: null,
  hoveredNodeId: null,
  hoveredApiNodeId: null,
} as const;

interface AtlasState {
  altitude: Altitude;
  /** Raw (un-namespaced) graph id this altitude is scoped/filtered to, or
   * `null` for the unscoped root view. */
  scope: string | null;
  hoveredNodeId: string | null;
  selectedNodeId: string | null;
  /** The *namespaced* (`web/api/nodeid.py`) form of the hovered/selected node,
   * as `/api/graph` resolved it -- `null` for an L3 package super-node, which
   * is synthetic and has no single subject to look up. Carried alongside the
   * raw id rather than re-derived on the client: the raw ids at L2 are
   * `dataflow` endpoints whose namespace depends on `xref.symbols`, which only
   * the server has. */
  hoveredApiNodeId: string | null;
  selectedApiNodeId: string | null;
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
  selectNode: (id: string | null, apiNodeId?: string | null) => void;
  hoverNode: (id: string | null, apiNodeId?: string | null) => void;
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
  hoveredApiNodeId: null,
  selectedApiNodeId: null,
  wheelAccumulator: 0,
  activeTraceEntry: null,
  lens: "structure",
  diffHighlight: null,

  descend: (rawNodeId) =>
    set((state) => {
      const next = DESCEND_ORDER[state.altitude];
      if (!next) return {};
      return { altitude: next, scope: rawNodeId, ...CLEAR_FOCUS, wheelAccumulator: 0 };
    }),

  ascend: () =>
    set((state) => {
      const next = ASCEND_ORDER[state.altitude];
      if (!next) return {};
      return { altitude: next, scope: null, ...CLEAR_FOCUS, wheelAccumulator: 0 };
    }),

  jumpTo: (altitude) => set({ altitude, scope: null, ...CLEAR_FOCUS, wheelAccumulator: 0 }),

  selectNode: (id, apiNodeId = null) => set({ selectedNodeId: id, selectedApiNodeId: apiNodeId }),
  hoverNode: (id, apiNodeId = null) => set({ hoveredNodeId: id, hoveredApiNodeId: apiNodeId }),

  startTrace: (entry) => set({ activeTraceEntry: entry }),
  clearTrace: () => set({ activeTraceEntry: null }),
  setLens: (lens) => set({ lens }),
  setDiffHighlight: (highlight) => set({ diffHighlight: highlight }),

  accumulateWheel: (deltaY) => {
    const total = get().wheelAccumulator + deltaY;
    if (total >= WHEEL_THRESHOLD) {
      set({ wheelAccumulator: 0 });
      const next = DESCEND_ORDER[get().altitude];
      if (next) set({ altitude: next, scope: null, ...CLEAR_FOCUS });
      return "descend";
    }
    if (total <= -WHEEL_THRESHOLD) {
      set({ wheelAccumulator: 0 });
      const next = ASCEND_ORDER[get().altitude];
      if (next) set({ altitude: next, scope: null, ...CLEAR_FOCUS });
      return "ascend";
    }
    set({ wheelAccumulator: total });
    return null;
  },
}));
