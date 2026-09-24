import { AnimatePresence, motion } from "framer-motion";
import type Graph from "graphology";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Sigma from "sigma";
import { useExpandedGraphs, useGraph, useNodesConfidence } from "../api/hooks.ts";
import type { Altitude } from "../api/nodeId.ts";
import { isGroupedAltitude } from "../api/nodeId.ts";
import { useRepoParams } from "../api/repoParams.ts";
import { useAtlasStore } from "../store/atlasStore.ts";
import { confidenceColor, type ConfidenceBucket } from "../theme/confidence.ts";
import {
  edgeAlpha,
  edgeWidth,
  FAMILY_VAR,
  luminanceStep,
  resolveCssColor,
  ROLE_HIDE_CLIENT_THRESHOLD,
  SHAPE_ZOOM_THRESHOLD,
  type Family,
} from "../theme/graphEncoding.ts";
import { AltitudeSwitcher } from "./AltitudeSwitcher.tsx";
import {
  buildGraph,
  collapseContainerInPlace,
  EXPAND_RADIUS,
  expandContainerInPlace,
  fitToViewport,
  layoutForceAtlas2Async,
  NESTED_RADIUS_FACTOR,
  persistPositions,
  setNodePinned,
  type ExpandedChildren,
  type PositionCacheKey,
} from "./graphLayout.ts";
import { GraphLegend } from "./GraphLegend.tsx";
import { Minimap } from "./Minimap.tsx";
import { sigmaSettings } from "./sigmaPrograms.ts";

/** Non-color redundancy for the Confidence lens (`WEB_RESEARCH.md` §5:
 * colour must never carry epistemic meaning alone). Matches `tokens.css`'s
 * documented glyphs per bucket. */
const CONFIDENCE_GLYPH: Record<string, string> = {
  high: " ✓",
  medium: " ~",
  low: " ?",
  contested: " ✕",
};

const DIM_EDGE = "#222834";

/** Altitude/scope-change node tween (`RESEARCH_PAIN_POINTS.md` §5): a node
 * present at both the old and new altitude eases between its two computed
 * positions instead of snapping, so drill-down/ascend reads as one
 * continuous map rather than a new unrelated graph. ~250ms per NN/g's
 * animation-duration guidance already cited in the research doc. */
const ALTITUDE_TRANSITION_MS = 250;
const easeOutCubic = (t: number) => 1 - (1 - t) ** 3;

/** Roles the legend's "Hide tests" toggle drops -- one role today, kept as a
 * list since `hide_roles`/`exclude_role` are already repeatable server-side. */
const HIDDEN_TEST_ROLES = ["test"];

/** Safety valve, not a real limit in practice -- `WEB_REDESIGN_RESEARCH.md`
 * §3.1's stop rule already bounds any one container's member count, so a
 * pathological repo would need several genuinely-nested nothing-but-
 * containers levels to ever hit this. Exists so a mis-clicked chain of
 * double-clicks can't recurse the sync layout pass indefinitely. */
const MAX_EXPANSION_DEPTH = 4;

/** One node in the currently-open expand-in-place set (`AtlasCanvas`'s
 * `expanded` map). `parentId: null` = a top-level container expanded
 * directly off the base graph; otherwise nested inside another open
 * expansion. `ownRung` is the altitude this container itself lives at
 * (the base `altitude` for a top-level one, or the `rung` attribute stamped
 * onto it by `expandContainerInPlace` if it's an already-injected node);
 * `childRung` is one rung deeper -- what its own children are fetched at. */
interface ExpansionNode {
  id: string;
  parentId: string | null;
  depth: number;
  ownRung: Altitude;
  childRung: Altitude;
}

/** The rung immediately deeper than `level`, per a `data.rungs`-shaped
 * ladder. `null` at the deepest rung (no next level to hand off to). Shared
 * by the base graph's `nextRung` and every open expansion's `childRung`
 * lookup, so both go through one definition of "what's next." */
function rungAfter(rungs: { level: Altitude }[], level: Altitude): Altitude | null {
  const index = rungs.findIndex((r) => r.level === level);
  return index >= 0 && index < rungs.length - 1 ? rungs[index + 1].level : null;
}

/** Every id in `expanded` that is `rootId` itself or transitively nested
 * inside it (following `parentId` chains) -- what a double-click-to-collapse
 * on `rootId` must remove in one state update so the apply effect's
 * depth-descending collapse pass sees the whole subtree gone at once,
 * rather than orphaning a nested expansion whose parent just vanished. */
function collectSubtreeIds(expanded: Map<string, ExpansionNode>, rootId: string): string[] {
  const ids = [rootId];
  // Bounded by `MAX_EXPANSION_DEPTH`, so a fixed-point loop (not recursion)
  // over the flat map is enough -- a child's entry always has strictly
  // greater `depth` than its parent's, so this terminates in at most that
  // many passes.
  let grew = true;
  while (grew) {
    grew = false;
    for (const node of expanded.values()) {
      if (node.parentId && ids.includes(node.parentId) && !ids.includes(node.id)) {
        ids.push(node.id);
        grew = true;
      }
    }
  }
  return ids;
}

/** Edge colour under the Flow lens. Seven channels is more than three hues
 * can hold, so this is the one place the three-family cap is relaxed -- and
 * it is safe precisely because the Flow lens shows *edges* against a legend
 * that is a vertical list, not an all-pairs canvas comparison. Node fills
 * still carry only the three families underneath. */
const FLOW_EDGE_VAR: Record<string, string> = {
  http_in: "--atlas-family-runtime",
  process_boundary: "--atlas-family-runtime",
  call: "--atlas-family-code",
  read: "--atlas-family-state",
  config_read: "--atlas-family-state",
  persist: "--atlas-family-state",
  schema_own: "--atlas-accent",
};

const FLOW_EDGE_WIDTH: Record<string, number> = {
  http_in: 2.2,
  process_boundary: 1.4,
  call: 1.4,
  read: 1.6,
  config_read: 1.2,
  persist: 2.2,
  schema_own: 2.2,
};

/** Resolved once per mount. Sigma parses colours into WebGL float buffers, so
 * handing it a `var(...)` string silently yields black. */
interface Palette {
  family: Record<Family, string>;
  hollow: string;
  dimEdge: string;
  accent: string;
  border: string;
  confidence: Record<string, string>;
}

function readPalette(): Palette {
  const bucket = (b: ConfidenceBucket) => resolveCssColor(confidenceColor(b).replace(/^var\(|\)$/g, ""));
  return {
    family: {
      code: resolveCssColor(FAMILY_VAR.code, "#3987e5"),
      runtime: resolveCssColor(FAMILY_VAR.runtime, "#d95926"),
      state: resolveCssColor(FAMILY_VAR.state, "#199e70"),
    },
    hollow: resolveCssColor("--atlas-node-hollow", "#0b0f14"),
    dimEdge: DIM_EDGE,
    accent: resolveCssColor("--atlas-accent", "#22e0ff"),
    border: resolveCssColor("--atlas-border", "#262c36"),
    confidence: {
      high: bucket("high"),
      medium: bucket("medium"),
      low: bucket("low"),
      contested: bucket("contested"),
      unreviewed: resolveCssColor("--atlas-border", "#262c36"),
    },
  };
}

function useFpsOverlay(enabled: boolean): number {
  const [fps, setFps] = useState(0);
  useEffect(() => {
    if (!enabled) return;
    let frames = 0;
    let lastSampleAt = performance.now();
    let raf = 0;
    const tick = () => {
      frames += 1;
      const now = performance.now();
      if (now - lastSampleAt >= 500) {
        setFps(Math.round((frames * 1000) / (now - lastSampleAt)));
        frames = 0;
        lastSampleAt = now;
      }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [enabled]);
  return fps;
}

/**
 * Wheel gesture is only treated as an altitude change when the pointer is
 * over the canvas *and* the canvas has focus (`WEB_RESEARCH.md` §3 rule 3) --
 * otherwise an incidental page-scroll wheel event while the mouse happens to
 * pass over the canvas would silently change altitude. A `ctrlKey` wheel
 * event is a trackpad pinch and is left alone so sigma's native camera zoom
 * handles it.
 *
 * All visual encoding runs through Sigma's node/edge **reducers** rather than
 * by mutating graph attributes. That is what makes a lens switch, a hover
 * highlight, a diff pulse and a zoom-driven shape change all free of layout:
 * the graph object is never touched after `buildGraph`, so FA2/dagre cannot
 * re-run (`PLAN.md`'s acceptance test, now enforced by construction rather
 * than by remembering to mutate carefully).
 */
export function AtlasCanvas() {
  const containerRef = useRef<HTMLDivElement | null>(null);
  // `AnimatePresence` keeps the outgoing `motion.div` mounted for its exit
  // transition (`ALTITUDE`/scope change -> new `displayKey`), so the outgoing
  // and incoming container elements briefly coexist. Both wire up through
  // this same `containerRef` object, so a bare `ref={containerRef}` on each
  // would let whichever element unmounts *last* null the ref out from under
  // whichever one is actually current -- and since the outgoing element's
  // removal is deferred until its ~0.48s exit animation finishes, that
  // "last" element is almost always the *old* one, arriving well after the
  // new one already attached. Found live: on a graph whose async FA2+noverlap
  // layout (`layoutForceAtlas2Async`) takes longer than that exit transition
  // (any graph in the low thousands of nodes -- trivial on this repo's own
  // fixtures, but the unified-store L2 graph in `WEB_REDESIGN_RESEARCH.md`
  // is 6,064 nodes), the container ref is already null by the time the
  // layout resolves, so the Sigma-mount effect below silently no-ops and the
  // canvas stays permanently blank -- no console error, no failed request,
  // nothing to show it happened short of instrumenting the effect itself.
  // `containerKeyRef` tracks which `displayKey`'s element currently owns the
  // ref so a stale exit's cleanup can't clobber a newer element's claim.
  const containerKeyRef = useRef<string | null>(null);
  const bindContainer = useCallback(
    (key: string) => (el: HTMLDivElement | null) => {
      if (el) {
        containerRef.current = el;
        containerKeyRef.current = key;
      } else if (containerKeyRef.current === key) {
        containerRef.current = null;
        containerKeyRef.current = null;
      }
    },
    [],
  );
  const sigmaRef = useRef<Sigma | null>(null);
  const [hasFocus, setHasFocus] = useState(false);
  const [shapesResolved, setShapesResolved] = useState(true);

  const altitude = useAtlasStore((s) => s.altitude);
  const scope = useAtlasStore((s) => s.scope);
  const ladder = useAtlasStore((s) => s.ladder);
  const descendTo = useAtlasStore((s) => s.descend);
  const ascend = useAtlasStore((s) => s.ascend);
  const hoveredNodeId = useAtlasStore((s) => s.hoveredNodeId);
  const selectedNodeId = useAtlasStore((s) => s.selectedNodeId);
  const hoverNode = useAtlasStore((s) => s.hoverNode);
  const selectNode = useAtlasStore((s) => s.selectNode);
  const accumulateWheel = useAtlasStore((s) => s.accumulateWheel);
  const lens = useAtlasStore((s) => s.lens);
  const diffHighlight = useAtlasStore((s) => s.diffHighlight);
  const focusNodeId = useAtlasStore((s) => s.focusNodeId);
  const toggleFocus = useAtlasStore((s) => s.toggleFocus);
  const repoParams = useRepoParams();
  const repoKey = `${repoParams.repo}:${repoParams.state_dir ?? ""}`;

  // Session-only, component state (`web/frontend/TODO.md`'s level 3): not
  // persisted to localStorage or the backend, resets on reload.
  const [hideTests, setHideTests] = useState(false);
  // Legend-as-filter (`WEB_REDESIGN_RESEARCH.md` §6): purely a client-side
  // dim, same as `hideClientSide` below -- there's no server-side family
  // filter, so this doesn't get the `ROLE_HIDE_CLIENT_THRESHOLD` server-fetch
  // fallback `hideTests` has.
  const [hiddenFamilies, setHiddenFamilies] = useState<Set<Family>>(() => new Set());
  const toggleFamily = useCallback((family: Family) => {
    setHiddenFamilies((prev) => {
      const next = new Set(prev);
      if (next.has(family)) next.delete(family);
      else next.add(family);
      return next;
    });
  }, []);

  const baseline = useGraph(altitude, scope, { focus: focusNodeId });
  const baselineNodeCount = baseline.data?.nodes.length ?? 0;
  // Below the threshold, hiding is instant client-side dimming off data
  // already in memory (no second request). Above it, that same dimming would
  // mean shipping and holding a mostly-hidden payload just to throw most of
  // it away in the reducer, so the toggle instead refetches the smaller,
  // pre-filtered graph the server already knows how to build.
  const overThreshold = baselineNodeCount > ROLE_HIDE_CLIENT_THRESHOLD;
  const filtered = useGraph(altitude, scope, {
    hideRoles: HIDDEN_TEST_ROLES,
    enabled: hideTests && overThreshold,
    focus: focusNodeId,
  });
  const useServerFilter = hideTests && overThreshold;
  const { data, isLoading, error, isPlaceholderData, isFetching } = useServerFilter ? filtered : baseline;
  // Client-side dimming only applies when the server hasn't already dropped
  // the rows -- otherwise a `test`-role node simply isn't in `data` at all.
  const hideClientSide = hideTests && !overThreshold;

  const testNodeCount = useMemo(
    () => (baseline.data?.nodes ?? []).filter((n) => HIDDEN_TEST_ROLES.includes(n.role ?? "")).length,
    [baseline.data],
  );

  const confidenceById = useNodesConfidence(altitude, scope, lens === "confidence");

  // Layout used to run synchronously inside this `useMemo` -- fine for a
  // ranked DAG (dagre, still sync below), but FA2's 500 iterations blocked
  // the main thread on every altitude/scope change once the breadcrumb
  // ladder made those changes frequent, which read as the reported lag.
  // The graph is built (and, if ranked, laid out) synchronously here; the
  // non-ranked FA2 pass runs off-thread in `layoutForceAtlas2Async` and only
  // then is `graph` published, so Sigma is never constructed mid-layout.
  const [graph, setGraph] = useState<Graph | null>(null);
  const [layoutReady, setLayoutReady] = useState(false);
  // Mirrors each node's `pinned` graph attribute so `GraphLegend`'s pin
  // toggle re-renders on click -- graphology attribute writes don't trigger
  // React re-renders on their own.
  const [pinnedIds, setPinnedIds] = useState<Set<string>>(() => new Set());
  // Bumped whenever `sigmaRef.current` is (re)assigned -- a plain ref
  // mutation doesn't itself trigger a re-render, and `Minimap` needs to pick
  // up the live `Sigma` instance (or its teardown) to (un)subscribe from the
  // camera.
  const [, setSigmaTick] = useState(0);

  const handleTogglePin = useCallback(() => {
    if (!selectedNodeId || !graph || !graph.hasNode(selectedNodeId)) return;
    const next = !graph.getNodeAttribute(selectedNodeId, "pinned");
    setNodePinned(graph, selectedNodeId, next, { repoKey, level: altitude, scope });
    setPinnedIds((prev) => {
      const copy = new Set(prev);
      if (next) copy.add(selectedNodeId);
      else copy.delete(selectedNodeId);
      return copy;
    });
  }, [selectedNodeId, graph, repoKey, altitude, scope]);
  // The `AnimatePresence`/container key actually mounted right now -- kept
  // one render behind `altitude`/`scope` while `isPlaceholderData` is true,
  // so a drill-down click doesn't retrigger the exit/enter crossfade (and
  // the container-remount it drives) until the *new* graph is actually
  // ready to show. Without this, the stale-data-stays-visible behaviour
  // below would fight this same key: the old Sigma canvas would start
  // fading out on click while the still-empty new container waited for the
  // real fetch, i.e. the exact blank flash `placeholderData` exists to
  // avoid.
  const [displayKey, setDisplayKey] = useState(() => `${altitude}:${scope ?? ""}`);
  // Previous graph, kept only long enough for the next build to read
  // starting positions off it -- updated after Sigma has already consumed
  // the current `graph` (see the ref-sync effect below), never read during
  // render.
  const prevGraphRef = useRef<Graph | null>(null);
  // Populated by the build below, consumed once by the tween effect after
  // Sigma mounts the new graph; `null` means "nothing to tween" (first
  // load, or reduced motion, where positions should just be the target).
  const transitionRef = useRef<
    { id: string; from: { x: number; y: number }; to: { x: number; y: number } }[] | null
  >(null);
  // Captures a tween from `prevGraphRef`'s positions to `built`'s *final*
  // layout positions (must run after dagre/FA2 have both already settled --
  // capturing straight off `buildGraph`'s return would grab the FA2 seed
  // circle for non-ranked altitudes, not the real target, since that layout
  // resolves later, off-thread). Rewrites `built` to start at the old
  // positions and stashes the real targets in `transitionRef` for the tween
  // effect to ease toward once Sigma mounts.
  const prepareTransition = useCallback((built: Graph) => {
    const prev = prevGraphRef.current;
    const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (!prev || prefersReducedMotion) {
      transitionRef.current = null;
      return;
    }
    const transitions: { id: string; from: { x: number; y: number }; to: { x: number; y: number } }[] = [];
    built.forEachNode((node, attrs) => {
      if (!prev.hasNode(node)) return;
      const to = { x: attrs.x as number, y: attrs.y as number };
      const from = { x: prev.getNodeAttribute(node, "x"), y: prev.getNodeAttribute(node, "y") };
      transitions.push({ id: node, from, to });
      // Paint at the old position first -- the tween effect below eases
      // from here to `to` once Sigma mounts the new graph, instead of the
      // new layout's position ever being on screen instantly.
      built.setNodeAttribute(node, "x", from.x);
      built.setNodeAttribute(node, "y", from.y);
    });
    transitionRef.current = transitions.length > 0 ? transitions : null;
  }, []);

  useEffect(() => {
    // `isPlaceholderData` (`useGraph`'s `placeholderData: keepPreviousData`)
    // means `data` is still the *previous* altitude/scope's graph, reused so
    // `AtlasCanvas` never blanks between clicks -- rebuilding it now would
    // apply the new altitude's ranked/force layout choice to the old graph's
    // shape, a wrong-looking flash. Bail and leave whatever's already on
    // screen (and `layoutReady`) untouched; this effect fires again once the
    // real fetch for the new key resolves and `data` is a fresh object.
    if (isPlaceholderData) return;
    const key = `${altitude}:${scope ?? ""}`;
    // `too_large`: the server deliberately withheld the node/edge list
    // (`app.py`'s `GRAPH_SIZE_CEILING`) rather than shipping an unbounded
    // unscoped L2 -- attempting a layout on an empty graph here would just
    // flash a blank canvas. The "pick a module" empty state below handles
    // this case instead.
    if (!data || data.too_large) {
      setGraph(null);
      setLayoutReady(false);
      setDisplayKey(key);
      return;
    }
    // Any grouped rung (L3, P2, P3, ...) is a small ranked DAG of packages;
    // only the raw L2/L1/L0 graphs get the force layout.
    const ranked = isGroupedAltitude(altitude);
    const cacheKey: PositionCacheKey = { repoKey, level: altitude, scope };
    if (import.meta.env.DEV) performance.mark("atlas:build-start");
    const built = buildGraph(data, ranked, cacheKey);
    const initialPinned = new Set<string>();
    built.forEachNode((node, attrs) => {
      if (attrs.pinned) initialPinned.add(node);
    });
    if (ranked) {
      if (import.meta.env.DEV) {
        performance.mark("atlas:build-end");
        // Ranked layout (dagre) runs synchronously inside `buildGraph`
        // itself, so there's no separate "layout" phase to measure here.
        performance.measure("atlas:build+layout (ranked)", "atlas:build-start", "atlas:build-end");
      }
      prepareTransition(built);
      setGraph(built);
      setLayoutReady(true);
      setDisplayKey(key);
      setPinnedIds(initialPinned);
      persistPositions(built, cacheKey);
      return;
    }
    if (import.meta.env.DEV) {
      performance.mark("atlas:build-end");
      performance.measure("atlas:build", "atlas:build-start", "atlas:build-end");
      performance.mark("atlas:layout-start");
    }
    let cancelled = false;
    setLayoutReady(false);
    layoutForceAtlas2Async(built).then(() => {
      if (cancelled) return;
      if (import.meta.env.DEV) {
        performance.mark("atlas:layout-end");
        performance.measure("atlas:layout", "atlas:layout-start", "atlas:layout-end");
      }
      prepareTransition(built);
      setGraph(built);
      setLayoutReady(true);
      setDisplayKey(key);
      setPinnedIds(initialPinned);
      persistPositions(built, cacheKey);
    });
    return () => {
      cancelled = true;
    };
  }, [data, altitude, scope, prepareTransition, isPlaceholderData, repoKey]);

  /** The rung immediately deeper than the current one, per this repo's own
   * ladder (`data.rungs`) -- there's no static next-rung table anymore
   * (`MONOREPO_HIERARCHY.md`), so `descend`/wheel-descend look it up here
   * instead of the store owning a fixed map. `null` once already at the
   * deepest rung (`"L2"`). */
  const nextRung = useMemo(() => rungAfter(data?.rungs ?? [], altitude), [data?.rungs, altitude]);

  const descend = useCallback(
    (rawNodeId: string) => {
      if (nextRung) descendTo(rawNodeId, nextRung);
    },
    [descendTo, nextRung],
  );

  /** `WEB_REDESIGN_RESEARCH.md` §3.2's expand-in-place, extended to multiple
   * simultaneous top-level containers plus nested (container-within-a-
   * container) expansion -- see `ExpansionNode`/`rungAfter`/
   * `collectSubtreeIds` above. Cleared on every altitude/scope change since a
   * raw id from the old rung means nothing at the new one (same convention
   * `CLEAR_FOCUS` already uses in the store). Double-click on a grouped
   * altitude's node toggles an entry instead of always descending -- see the
   * `doubleClickNode`/`rightClickNode` handlers below. */
  const [expanded, setExpanded] = useState<Map<string, ExpansionNode>>(new Map());
  useEffect(() => {
    setExpanded(new Map());
  }, [altitude, scope]);
  const expandedGraphs = useExpandedGraphs(
    useMemo(
      () => [...expanded.values()].map((e) => ({ id: e.id, childRung: e.childRung })),
      [expanded],
    ),
  );
  // What's actually mutated into the live `graph` object right now, keyed by
  // *graph identity* (not just `expanded`'s keys) so a full graph rebuild
  // (new altitude/scope, or any other reason `buildGraph` reran for the same
  // key) doesn't skip re-applying an expansion that's stale against the new
  // object, and keyed by expansion id within that so multiple simultaneous
  // and/or nested expansions are each tracked (and torn down) independently.
  // Never read during render.
  const appliedRef = useRef<{
    graph: Graph;
    byId: Map<string, { info: ExpandedChildren; depth: number }>;
  } | null>(null);

  /** Reducer inputs, held in a ref so changing one never re-creates Sigma --
   * only a `refresh()`. */
  const stateRef = useRef({
    lens,
    confidenceById,
    hoveredNodeId,
    selectedNodeId,
    diffHighlight,
    hideClientSide,
    hiddenFamilies,
    shapesResolved: true,
    palette: null as Palette | null,
  });
  useEffect(() => {
    if (!graph || !containerRef.current) return;
    const palette = readPalette();
    stateRef.current.palette = palette;

    // Denominator for the hub/leaf luminance step below -- static per graph
    // build, so computed once here rather than per reducer call.
    let maxNodeSize = 1;
    graph.forEachNode((_, attrs) => {
      maxNodeSize = Math.max(maxNodeSize, attrs.size as number);
    });

    const sigma = new Sigma(
      graph,
      containerRef.current,
      sigmaSettings({
        // A small ranked graph (L3 is ~18 packages) should label everything --
        // a degree threshold there hides half the map for no benefit. The
        // threshold only earns its keep once labels start colliding.
        labelRenderedSizeThreshold: graph.order <= 60 ? 0 : 9,
        labelDensity: graph.order <= 60 ? 1 : 0.25,
        // Edge labels are only ever set (in `buildGraph`) on ranked/grouped
        // altitudes, but Sigma's `renderEdgeLabels` is a hard global gate --
        // without it a leaf L2 rebuild that happens to reuse this same Sigma
        // instance would never have been asked to draw the ones it does have.
        renderEdgeLabels: isGroupedAltitude(altitude),

        nodeReducer: (node, attrs) => {
          const s = stateRef.current;
          const family = attrs.family as Family;
          const bucket = s.confidenceById.get(node) ?? "unreviewed";
          const isFocus = node === s.hoveredNodeId || node === s.selectedNodeId;
          const isDiffAdded = s.diffHighlight?.added.includes(node) ?? false;
          const isHiddenRole =
            s.hideClientSide && HIDDEN_TEST_ROLES.includes((attrs.role as string | null) ?? "");
          const isHiddenFamily = s.hiddenFamilies.has(family);

          const res: Record<string, unknown> = { ...attrs };
          if (isHiddenRole || isHiddenFamily) {
            res.hidden = true;
            return res;
          }
          res.type = s.shapesResolved ? (attrs.shape as string) : "dot";

          if (s.lens === "confidence") {
            res.color = palette.confidence[bucket] ?? palette.confidence.unreviewed;
            res.ringColor = palette.border;
            res.label = (attrs.baseLabel as string) + (CONFIDENCE_GLYPH[bucket] ?? "");
          } else {
            res.color = palette.family[family] ?? palette.family.code;
            // Status on the ring, structure in the fill -- never mixed. The
            // confidence lens is off here, so `useNodesConfidence` never
            // fetched anything and every node falls back to "unreviewed" --
            // drawing that fallback as a ring painted every node with the
            // same solid grey halo (looked like a drop shadow on the whole
            // canvas). Only draw a ring when there is a real, fetched
            // bucket for this node; otherwise leave it at the border
            // program's transparent default.
            res.ringColor = s.confidenceById.has(node) && bucket !== "unreviewed"
              ? palette.confidence[bucket]
              : "#00000000";
            res.label = attrs.baseLabel as string;
          }

          res.hollowColor = palette.hollow;

          // Hubs read as brighter, not just bigger -- a luminance step within
          // the family hue rather than a 4th colour (§3/§7 already ruled that
          // out on CVD grounds). Skipped for the confidence lens, where the
          // colour already carries a different meaning entirely.
          if (s.lens !== "confidence") {
            const t = Math.min(1, (attrs.size as number) / maxNodeSize);
            res.color = luminanceStep(res.color as string, t);
          }

          if (isDiffAdded) {
            res.color = palette.accent;
            res.ringColor = palette.accent;
            res.size = (attrs.size as number) * 1.7;
            res.zIndex = 3;
            res.forceLabel = true;
          } else if (isFocus) {
            res.ringColor = palette.accent;
            res.size = (attrs.size as number) * 1.25;
            res.zIndex = 2;
            res.forceLabel = true;
          }

          return res;
        },

        edgeReducer: (edge, attrs) => {
          const s = stateRef.current;
          const source = graph.source(edge);
          const target = graph.target(edge);

          if (s.hideClientSide) {
            const srcRole = graph.getNodeAttribute(source, "role") as string | null;
            const tgtRole = graph.getNodeAttribute(target, "role") as string | null;
            if (HIDDEN_TEST_ROLES.includes(srcRole ?? "") || HIDDEN_TEST_ROLES.includes(tgtRole ?? "")) {
              return { ...attrs, hidden: true };
            }
          }
          if (s.hiddenFamilies.size > 0) {
            const srcFamily = graph.getNodeAttribute(source, "family") as Family;
            const tgtFamily = graph.getNodeAttribute(target, "family") as Family;
            if (s.hiddenFamilies.has(srcFamily) || s.hiddenFamilies.has(tgtFamily)) {
              return { ...attrs, hidden: true };
            }
          }

          // Only a focus id that exists *in this graph* counts. An id left
          // over from another altitude would otherwise put every edge in the
          // dimmed branch with nothing highlighted -- a canvas that looks
          // broken rather than focused.
          const hovered = s.hoveredNodeId && graph.hasNode(s.hoveredNodeId) ? s.hoveredNodeId : null;
          const selected =
            s.selectedNodeId && graph.hasNode(s.selectedNodeId) ? s.selectedNodeId : null;
          const touchesFocus =
            source === hovered || target === hovered || source === selected || target === selected;
          const someFocus = hovered !== null || selected !== null;

          const res: Record<string, unknown> = { ...attrs };
          const kind = attrs.kind as string;
          const confidence = attrs.confidence as string | null;

          if (s.lens === "flow") {
            const varName = FLOW_EDGE_VAR[kind];
            res.color =
              (varName ? resolveCssColor(varName, palette.family.code) : palette.dimEdge) +
              edgeAlpha(confidence);
            res.size = FLOW_EDGE_WIDTH[kind] ?? 1.2;
          } else if (s.lens === "confidence") {
            res.color = palette.dimEdge;
            res.size = 0.9;
          } else {
            // Structure: an edge takes the family of what it *reaches*, so a
            // glance reads "blue code through orange boundaries into aqua
            // state" -- which is the actual architecture.
            res.color =
              (palette.family[attrs.targetFamily as Family] ?? palette.family.code) +
              edgeAlpha(confidence);
            res.size = edgeWidth(confidence);
          }

          if (someFocus) {
            if (touchesFocus) {
              res.color = palette.accent;
              res.size = (res.size as number) * 1.6;
              res.zIndex = 2;
            } else {
              res.color = palette.dimEdge + "40";
            }
          }

          return res;
        },
      }),
    );
    sigmaRef.current = sigma;
    setSigmaTick((t) => t + 1);
    fitToViewport(sigma);

    if (import.meta.env.DEV) {
      performance.mark("atlas:first-paint");
      try {
        performance.measure("atlas:fetch-to-paint", "atlas:fetch-start", "atlas:first-paint");
      } catch {
        // `atlas:fetch-start` may be absent on a placeholder-data render
        // that never re-fetched -- not a real gap, skip this one measure.
      }
      const rows = performance
        .getEntriesByType("measure")
        .filter((m) => m.name.startsWith("atlas:"))
        .map((m) => ({ name: m.name, durationMs: Math.round(m.duration) }));
      if (rows.length > 0) console.table(rows);
      performance.clearMarks();
      performance.clearMeasures();
    }

    // Dev-only handle. §4's "fit to viewport" claim is geometric -- no unit
    // test can see whether a node landed outside the frame -- so this exists
    // to make it checkable from a browser console or a Playwright probe:
    //   __atlasSigma.getGraph().forEachNode(n =>
    //     __atlasSigma.framedGraphToViewport(__atlasSigma.getNodeDisplayData(n)))
    // Measured 0 offscreen nodes at both altitudes on this repo.
    if (import.meta.env.DEV) {
      (window as unknown as { __atlasSigma?: Sigma }).__atlasSigma = sigma;
    }

    sigma.on("enterNode", ({ node }) => {
      hoverNode(node, (graph.getNodeAttribute(node, "nodeId") as string | null) ?? null);
      // Discoverability: nothing else signals a node is double-clickable
      // (`RESEARCH_PAIN_POINTS.md` §2) -- only show it when double-click
      // would actually do something (`nextRung` is null at a leaf altitude).
      if (containerRef.current) containerRef.current.style.cursor = nextRung ? "pointer" : "default";
    });
    sigma.on("leaveNode", () => {
      hoverNode(null, null);
      if (containerRef.current) containerRef.current.style.cursor = "default";
    });
    sigma.on("clickNode", ({ node }) => {
      selectNode(node, (graph.getNodeAttribute(node, "nodeId") as string | null) ?? null);
    });
    sigma.on("doubleClickNode", ({ node, event }) => {
      event.preventSigmaDefault();
      // `WEB_REDESIGN_RESEARCH.md` §3.2: plain double-click on a grouped
      // altitude expands the container in place (children appear inside its
      // former footprint, siblings stay put); ⌘/Ctrl-double-click is the
      // doc's escape hatch to the old "focus this container" behaviour
      // (change the ladder/breadcrumb), same as the `rightClickNode` gesture
      // right below. A leaf altitude (`nextRung === null`) has no container
      // to expand, so it always falls back to `descend` (a no-op there).
      // An already-injected node (has `expandedParent`, unconditionally
      // stamped by `expandContainerInPlace`) carries its own altitude in its
      // `rung` attribute -- `null` there means "this child is a leaf, not
      // itself a container" and must NOT fall back to the canvas's
      // `altitude` (that would wrongly treat a leaf as a top-level
      // container and attempt to expand it, 404ing against the server).
      // A genuinely top-level node has no `expandedParent` at all, and its
      // own altitude is just the canvas's current `altitude`.
      const isInjected = graph.getNodeAttribute(node, "expandedParent") != null;
      const ownRung: Altitude | null = isInjected
        ? (graph.getNodeAttribute(node, "rung") as Altitude | null)
        : altitude;
      const childRung = ownRung ? rungAfter(data?.rungs ?? [], ownRung) : null;
      if (
        childRung &&
        ownRung &&
        isGroupedAltitude(ownRung) &&
        !event.original.metaKey &&
        !event.original.ctrlKey
      ) {
        setExpanded((prev) => {
          if (prev.has(node)) {
            const next = new Map(prev);
            for (const id of collectSubtreeIds(prev, node)) next.delete(id);
            return next;
          }
          const parentId = (graph.getNodeAttribute(node, "expandedParent") as string | null) ?? null;
          const parentEntry = parentId ? prev.get(parentId) : undefined;
          const depth = parentEntry ? parentEntry.depth + 1 : 0;
          if (depth >= MAX_EXPANSION_DEPTH) return prev;
          const next = new Map(prev);
          next.set(node, { id: node, parentId, depth, ownRung, childRung });
          return next;
        });
      } else {
        descend(node);
      }
    });
    sigma.on("rightClickNode", ({ node, event }) => {
      event.preventSigmaDefault();
      descend(node);
    });
    sigma.on("clickStage", () => selectNode(null, null));

    // Shape stops carrying identity once nodes are a few pixels across
    // (`ATLAS_REDESIGN.md` §7). Swap every node to a plain dot past the
    // threshold and tell the legend to say so. Changing a node's program
    // needs a full re-index, so this fires only on threshold *crossings*,
    // not per frame.
    const camera = sigma.getCamera();
    const onCameraUpdate = () => {
      const resolved = camera.ratio <= SHAPE_ZOOM_THRESHOLD;
      if (resolved === stateRef.current.shapesResolved) return;
      stateRef.current.shapesResolved = resolved;
      setShapesResolved(resolved);
      sigma.refresh();
    };
    camera.on("updated", onCameraUpdate);

    return () => {
      camera.off("updated", onCameraUpdate);
      // This `graph` object (and the Sigma instance drawing it) is going
      // away -- any expand-in-place mutation applied to it goes with it.
      // Not restoring the parent's attributes here (there's nothing left to
      // restore them on); just drop the stale ref so the merge effect below
      // re-expands cleanly against whatever graph object (if any) replaces
      // this one.
      appliedRef.current = null;
      sigma.kill();
      sigmaRef.current = null;
      setSigmaTick((t) => t + 1);
    };
  }, [graph, hoverNode, selectNode, descend, nextRung, altitude, data?.rungs]);

  /** Applies/removes the expand-in-place mutation (`graphLayout.ts`) against
   * whichever graph object is currently live. Runs after the mount effect
   * above (declared later => committed later), so `sigmaRef.current` and
   * `stateRef.current.palette` are already set by the time this reads them. */
  useEffect(() => {
    if (!graph || !sigmaRef.current) return;
    // A stale ref (from a graph object this effect never tore down, e.g. the
    // mount effect's own cleanup already ran against it) has nothing left to
    // collapse against -- drop it and start this graph's bookkeeping fresh.
    if (appliedRef.current && appliedRef.current.graph !== graph) {
      appliedRef.current = null;
    }
    const byId = appliedRef.current?.byId ?? new Map();
    appliedRef.current = { graph, byId };

    // Collapse pass: anything applied that's no longer wanted, deepest first
    // -- a nested expansion's own collapse must run before its ancestor's,
    // since `collapseContainerInPlace` restores the parent container node
    // and a child expansion centered on that parent needs it still present.
    const toCollapse = [...byId.entries()]
      .filter(([id]) => !expanded.has(id))
      .sort(([, a], [, b]) => b.depth - a.depth);
    for (const [id, entry] of toCollapse) {
      collapseContainerInPlace(graph, id, entry.info);
      byId.delete(id);
    }

    // Apply pass: anything wanted that isn't applied yet, shallowest first --
    // a nested expansion's parent container must already have its children
    // injected before this centers the nested one among them.
    const toApply = [...expanded.entries()]
      .filter(([id]) => !byId.has(id))
      .sort(([, a], [, b]) => a.depth - b.depth);
    for (const [id, entry] of toApply) {
      if (!graph.hasNode(id)) continue;
      const childGraph = expandedGraphs.get(id);
      if (!childGraph?.data || childGraph.isPlaceholderData) continue;
      const info = expandContainerInPlace(graph, id, childGraph.data, {
        rung: entry.childRung,
        radius: EXPAND_RADIUS * NESTED_RADIUS_FACTOR ** entry.depth,
      });
      byId.set(id, { info, depth: entry.depth });
    }

    // `expandContainerInPlace` packs a container's children into a small,
    // fixed-radius circle -- far denser than the graph's overall node count
    // implies, so the order-based label heuristic set at Sigma construction
    // (`graph.order <= 60` above) under-culls badly here (the crowded-label
    // regression flagged live in TODO.md). Force the same tighter settings
    // used for a large graph whenever any expansion is open, regardless of
    // overall order; restore the order-based heuristic once none are.
    const anyExpanded = byId.size > 0;
    sigmaRef.current.setSetting(
      "labelRenderedSizeThreshold",
      anyExpanded ? 9 : graph.order <= 60 ? 0 : 9,
    );
    sigmaRef.current.setSetting("labelDensity", anyExpanded ? 0.25 : graph.order <= 60 ? 1 : 0.25);

    sigmaRef.current.refresh({ skipIndexation: false });
  }, [graph, expanded, expandedGraphs]);

  /** Eases every persisting node from `transitionRef`'s captured start
   * position to its newly-laid-out target over `ALTITUDE_TRANSITION_MS`,
   * once Sigma has actually mounted this `graph` (the effect above already
   * ran). Cancel-and-replace, not queued: a second altitude change before
   * this finishes cancels this effect's `rafId` in cleanup and the next
   * `graph` value starts its own fresh tween from wherever positions
   * actually landed -- never stacking. */
  useEffect(() => {
    const transitions = transitionRef.current;
    transitionRef.current = null;
    if (!graph || !transitions || transitions.length === 0) return;
    let rafId = 0;
    const start = performance.now();
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / ALTITUDE_TRANSITION_MS);
      const eased = easeOutCubic(t);
      for (const { id, from, to } of transitions) {
        if (!graph.hasNode(id)) continue;
        graph.setNodeAttribute(id, "x", from.x + (to.x - from.x) * eased);
        graph.setNodeAttribute(id, "y", from.y + (to.y - from.y) * eased);
      }
      sigmaRef.current?.refresh({ skipIndexation: true });
      if (t < 1) rafId = requestAnimationFrame(tick);
    };
    rafId = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(rafId);
  }, [graph]);

  // Tracks the most recently mounted graph so the *next* build effect run
  // can read its node positions as tween starting points -- never read
  // during render, only by the build effect above.
  useEffect(() => {
    prevGraphRef.current = graph;
  }, [graph]);

  /** Every reducer input change is a repaint, never a rebuild. The inputs are
   * published to `stateRef` here (not during render, which would be a ref
   * write in render) and then `refresh({skipIndexation})` re-runs only the
   * reducers, keeping the WebGL buffers -- so a lens switch on a 353-node
   * graph costs a frame, not a relayout. */
  useEffect(() => {
    const s = stateRef.current;
    s.lens = lens;
    s.confidenceById = confidenceById;
    s.hoveredNodeId = hoveredNodeId;
    s.selectedNodeId = selectedNodeId;
    s.diffHighlight = diffHighlight;
    s.hideClientSide = hideClientSide;
    s.hiddenFamilies = hiddenFamilies;
    sigmaRef.current?.refresh({ skipIndexation: true });
  }, [lens, confidenceById, hoveredNodeId, selectedNodeId, diffHighlight, hideClientSide, hiddenFamilies]);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const onWheel = (event: WheelEvent) => {
      if (event.ctrlKey || !hasFocus) return;
      event.preventDefault();
      accumulateWheel(event.deltaY, nextRung);
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") ascend();
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    el.addEventListener("keydown", onKeyDown);
    return () => {
      el.removeEventListener("wheel", onWheel);
      el.removeEventListener("keydown", onKeyDown);
    };
  }, [hasFocus, accumulateWheel, ascend, nextRung]);

  const edgeKinds = useMemo(() => {
    const counts = new Map<string, number>();
    for (const edge of data?.edges ?? []) {
      counts.set(edge.kind, (counts.get(edge.kind) ?? 0) + (edge.count ?? 1));
    }
    return [...counts.entries()]
      .map(([kind, count]) => ({ kind, count }))
      .sort((a, b) => b.count - a.count);
  }, [data]);

  const confidenceCounts = useMemo(() => {
    const counts: Partial<Record<ConfidenceBucket, number>> = {};
    let seen = 0;
    for (const bucket of confidenceById.values()) {
      counts[bucket] = (counts[bucket] ?? 0) + 1;
      seen += 1;
    }
    counts.unreviewed = Math.max(0, (data?.nodes.length ?? 0) - seen);
    return counts;
  }, [confidenceById, data]);

  const fps = useFpsOverlay(import.meta.env.DEV);
  const prefersReducedMotion = useMemo(
    () => window.matchMedia("(prefers-reduced-motion: reduce)").matches,
    [],
  );
  const isTooLarge = !isLoading && !error && Boolean(data?.too_large);
  const isEmpty = !isLoading && !error && !isTooLarge && (data?.edges.length ?? 0) === 0;
  // Layout compute is now off-thread and can outlast the fetch, so the
  // loading state has to cover both -- otherwise the last frame's stale
  // graph would sit on screen while FA2 quietly repositions everything.
  // `isPlaceholderData` never reaches here true at the same time as
  // `!layoutReady`, since the build effect above skips rebuilding (and so
  // never flips `layoutReady` false) while placeholder data is showing.
  const showLoading = isLoading || (!!data && !isEmpty && !isTooLarge && !layoutReady);
  // The old graph's own fetch is done -- what's showing is deliberately
  // stale (`placeholderData: keepPreviousData`) while the new
  // altitude/scope loads in the background. Distinct from `showLoading`,
  // which covers "nothing to show yet at all".
  const showUpdating = isFetching && isPlaceholderData;

  return (
    <div className="relative h-full w-full">
      <AltitudeSwitcher
        altitude={altitude}
        ladder={ladder}
        rungs={(data?.rungs ?? []).map((r) => ({ ...r, depth: r.depth ?? null }))}
        nodeCount={data?.nodes.length ?? 0}
        edgeCount={data?.edges.length ?? 0}
      />

      {import.meta.env.DEV && (
        // Bottom-centre: the top-right corner belongs to the view switcher
        // and the legend.
        <div className="absolute bottom-3 left-1/2 z-10 -translate-x-1/2 rounded bg-black/40 px-2 py-1 font-mono text-xs text-white">
          {fps} fps
        </div>
      )}

      {showLoading && (
        <div className="absolute inset-0 flex items-center justify-center text-sm text-[var(--atlas-text-dim)]">
          {isLoading ? "loading graph…" : "laying out the map…"}
        </div>
      )}
      {showUpdating && (
        <div className="absolute right-3 top-3 z-10 rounded bg-black/40 px-2 py-1 text-xs text-[var(--atlas-text-dim)]">
          updating…
        </div>
      )}
      {error && (
        <div className="absolute inset-0 flex items-center justify-center text-sm text-red-400">
          {String(error)}
        </div>
      )}
      {isEmpty && (
        <div className="absolute inset-0 flex items-center justify-center px-8 text-center text-sm text-[var(--atlas-text-dim)]">
          Nothing to map yet — this snapshot has no extracted connections. Run a scan from the
          Control Room, then come back.
        </div>
      )}

      {isTooLarge && (
        <div className="absolute inset-0 flex flex-col items-center justify-center gap-4 px-8 text-center text-sm text-[var(--atlas-text-dim)]">
          <p>
            This repo's full module graph is too large to lay out at once. Pick one of its
            biggest packages to start from instead:
          </p>
          <div className="flex max-w-2xl flex-wrap justify-center gap-2">
            {(data?.suggested_scopes ?? []).map((id) => (
              <button
                key={id}
                onClick={() => descendTo(id, "L2")}
                className="atlas-btn-primary rounded-full px-3 py-1.5 text-xs"
              >
                {id}
              </button>
            ))}
          </div>
        </div>
      )}

      {data && !isEmpty && !isTooLarge && (
        <GraphLegend
          lens={lens}
          entries={data.legend ?? []}
          edgeKinds={edgeKinds}
          confidenceCounts={confidenceCounts}
          divergence={isGroupedAltitude(altitude) ? (data.divergence as never) : null}
          shapesResolved={shapesResolved}
          testNodeCount={testNodeCount}
          hideTests={hideTests}
          onToggleHideTests={setHideTests}
          usingServerFilter={useServerFilter}
          hiddenFamilies={hiddenFamilies}
          onToggleFamily={toggleFamily}
          focusable={selectedNodeId !== null}
          isFocused={focusNodeId !== null && focusNodeId === selectedNodeId}
          onToggleFocus={() => selectedNodeId && toggleFocus(selectedNodeId)}
          pinnable={selectedNodeId !== null}
          isPinned={selectedNodeId !== null && pinnedIds.has(selectedNodeId)}
          onTogglePin={handleTogglePin}
        />
      )}

      {graph && graph.order > 0 && <Minimap graph={graph} sigma={sigmaRef.current} />}

      <AnimatePresence>
        <motion.div
          key={displayKey}
          className={`absolute inset-0 ${isTooLarge || isEmpty || error ? "pointer-events-none" : ""}`}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: prefersReducedMotion ? 0 : 0.48, ease: [0.2, 0.8, 0.2, 1] }}
        >
          <div
            ref={bindContainer(displayKey)}
            tabIndex={0}
            onFocus={() => setHasFocus(true)}
            onBlur={() => setHasFocus(false)}
            className="h-full w-full outline-none transition-opacity"
            style={{ opacity: showUpdating ? 0.6 : 1 }}
          />
        </motion.div>
      </AnimatePresence>
    </div>
  );
}

export type { Altitude };
