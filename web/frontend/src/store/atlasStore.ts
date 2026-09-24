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

/** L1/L0 stay outside this ladder for the reason `ATLAS_REDESIGN.md` §7
 * found: file-level import extraction yields **2 edges across 413 files**,
 * both in a Java fixture -- Python imports never reach the file graph. §2's
 * instruction for that case is explicit: L1 should be *cut, not styled*. L0
 * is cut for the same reason (2 symbol-scoped edges over 2287 symbols).
 * Neither is deleted from the API: `/api/graph?level=L0` still backs the ask
 * bar's symbol typeahead, and both are still held to the renderable-edge
 * contract (`web/tests/test_graph_contract.py`).
 *
 * The rest of the ladder -- `"L3"` through however many `"P{n}"` rungs a
 * repo's real path depth supports, down to `"L2"` -- is no longer a fixed
 * lookup table: it varies per repo (`GraphResponse.rungs`,
 * `MONOREPO_HIERARCHY.md`), so `descend`/`jumpTo` below take the next rung
 * explicitly from whoever has the current `rungs` array (`AtlasCanvas`)
 * instead of consulting a static map. */

/** One step of the breadcrumb: the altitude shown, and what it's scoped to
 * (`null` only for the root, index 0). */
interface LadderEntry {
  level: Altitude;
  scope: string | null;
}

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
  focusNodeId: null,
} as const;

interface AtlasState {
  /** Breadcrumb stack: index 0 is always the unscoped root, the last entry
   * is the current view. `altitude`/`scope` below are that last entry,
   * kept redundantly in sync on every ladder mutation so existing readers
   * (`AtlasCanvas`, `AltitudeSwitcher`) don't need to reach into `ladder`
   * themselves for the common case. */
  ladder: LadderEntry[];
  altitude: Altitude;
  /** Raw (un-namespaced) graph id this altitude is scoped/filtered to, or
   * `null` for the unscoped root view. */
  scope: string | null;
  hoveredNodeId: string | null;
  selectedNodeId: string | null;
  /** The *namespaced* (`web/api/nodeid.py`) form of the hovered/selected node,
   * as `/api/graph` resolved it -- `null` for a package super-node, which
   * is synthetic and has no single subject to look up. Carried alongside the
   * raw id rather than re-derived on the client: the raw ids at L2 are
   * `dataflow` endpoints whose namespace depends on `xref.symbols`, which only
   * the server has. */
  hoveredApiNodeId: string | null;
  selectedApiNodeId: string | null;
  /** `WEB_REDESIGN_RESEARCH.md` §4's neighbourhood-focus toggle: when set,
   * `/api/graph` is asked to restrict its response to this raw node id's
   * neighbourhood (`focus=`) without moving the ladder/breadcrumb -- unlike
   * `descend`, this is reversible with one click and doesn't change
   * altitude. Cleared by `CLEAR_FOCUS` on every ladder mutation, same as
   * hover/select, since a focus target from the old altitude means nothing
   * at the new one. */
  focusNodeId: string | null;
  wheelAccumulator: number;
  activeTraceEntry: string | null;
  lens: Lens;
  /** Time scrubber's most recent `/api/diff` result, by (L3) module id --
   * `AtlasCanvas` pulses/fades matching nodes on the next render, then the
   * scrubber clears this after the pulse animation finishes. `null` means
   * no scrub is in flight. */
  diffHighlight: { added: string[]; removed: string[] } | null;

  /** `nextLevel` is the rung immediately deeper than the current one, per
   * this repo's `GraphResponse.rungs` -- the caller (`AtlasCanvas`) looks
   * it up since there's no static next-rung table anymore. Pushes onto the
   * ladder rather than replacing it, so `ascend()` can come back to exactly
   * this scope. */
  descend: (rawNodeId: string, nextLevel: Altitude) => void;
  /** Pops one entry off the ladder, restoring the *prior* scope -- not
   * always the unscoped root, which was the bug: descending three levels
   * deep and ascending twice used to drop straight to `null` instead of
   * the intermediate scope. */
  ascend: () => void;
  /** One breadcrumb chip's worth of `ascend()`: truncates the ladder to
   * `index` (inclusive), restoring whatever scope was current at that
   * point in the stack rather than popping one entry at a time. */
  ascendTo: (index: number) => void;
  /** A ladder-button click: jumps to an unscoped root view at `level`,
   * discarding the rest of the stack (matches the pre-breadcrumb `jumpTo`
   * semantics -- a direct rung pick, not a "back" gesture). */
  jumpTo: (level: Altitude) => void;
  selectNode: (id: string | null, apiNodeId?: string | null) => void;
  hoverNode: (id: string | null, apiNodeId?: string | null) => void;
  startTrace: (entry: string) => void;
  clearTrace: () => void;
  setLens: (lens: Lens) => void;
  setDiffHighlight: (highlight: { added: string[]; removed: string[] } | null) => void;
  /** Toggles focus on `id`: focusing the already-focused node clears it,
   * matching the "aria-pressed toggle button" convention every other
   * legend row uses (`GraphLegend.tsx`'s "Hide tests"/family rows). */
  toggleFocus: (id: string) => void;
  /** Accumulates a wheel gesture's `deltaY`; returns the altitude change
   * (if the threshold was crossed this call) so the caller can also drive
   * a crossfade, without the store owning animation concerns itself.
   * `nextLevel` is the same next-rung lookup `descend` needs -- `null` when
   * already at the deepest rung, in which case a downward flick is a no-op
   * rather than an error. */
  accumulateWheel: (deltaY: number, nextLevel: Altitude | null) => "descend" | "ascend" | null;
}

/** Derives the redundant `altitude`/`scope` fields from a ladder so every
 * setter only has to build the stack, not remember to keep both in sync. */
function fromLadder(ladder: LadderEntry[]): Pick<AtlasState, "ladder" | "altitude" | "scope"> {
  const top = ladder[ladder.length - 1];
  return { ladder, altitude: top.level, scope: top.scope };
}

export const useAtlasStore = create<AtlasState>((set, get) => ({
  ...fromLadder([{ level: "L3", scope: null }]),
  hoveredNodeId: null,
  selectedNodeId: null,
  hoveredApiNodeId: null,
  selectedApiNodeId: null,
  focusNodeId: null,
  wheelAccumulator: 0,
  activeTraceEntry: null,
  lens: "structure",
  diffHighlight: null,

  descend: (rawNodeId, nextLevel) =>
    set((state) => ({
      ...fromLadder([...state.ladder, { level: nextLevel, scope: rawNodeId }]),
      ...CLEAR_FOCUS,
      wheelAccumulator: 0,
    })),

  ascend: () =>
    set((state) => {
      if (state.ladder.length <= 1) return {};
      return { ...fromLadder(state.ladder.slice(0, -1)), ...CLEAR_FOCUS, wheelAccumulator: 0 };
    }),

  ascendTo: (index) =>
    set((state) => {
      if (index < 0 || index >= state.ladder.length - 1) return {};
      return { ...fromLadder(state.ladder.slice(0, index + 1)), ...CLEAR_FOCUS, wheelAccumulator: 0 };
    }),

  jumpTo: (level) => set({ ...fromLadder([{ level, scope: null }]), ...CLEAR_FOCUS, wheelAccumulator: 0 }),

  selectNode: (id, apiNodeId = null) => set({ selectedNodeId: id, selectedApiNodeId: apiNodeId }),
  hoverNode: (id, apiNodeId = null) => set({ hoveredNodeId: id, hoveredApiNodeId: apiNodeId }),

  startTrace: (entry) => set({ activeTraceEntry: entry }),
  clearTrace: () => set({ activeTraceEntry: null }),
  setLens: (lens) => set({ lens }),
  setDiffHighlight: (highlight) => set({ diffHighlight: highlight }),
  toggleFocus: (id) => set((state) => ({ focusNodeId: state.focusNodeId === id ? null : id })),

  accumulateWheel: (deltaY, nextLevel) => {
    const total = get().wheelAccumulator + deltaY;
    if (total >= WHEEL_THRESHOLD) {
      set({ wheelAccumulator: 0 });
      if (!nextLevel) return null;
      set((state) => ({ ...fromLadder([...state.ladder, { level: nextLevel, scope: null }]), ...CLEAR_FOCUS }));
      return "descend";
    }
    if (total <= -WHEEL_THRESHOLD) {
      set({ wheelAccumulator: 0 });
      set((state) => {
        if (state.ladder.length <= 1) return {};
        return { ...fromLadder(state.ladder.slice(0, -1)), ...CLEAR_FOCUS };
      });
      return "ascend";
    }
    set({ wheelAccumulator: total });
    return null;
  },
}));
