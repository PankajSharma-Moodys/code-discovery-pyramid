import type { Altitude } from "../api/nodeId.ts";
import { useAtlasStore } from "../store/atlasStore.ts";

/**
 * `ATLAS_REDESIGN.md` §5, first row: the altitude control used to be three
 * buttons reading `L3` / `L2` / `L1` — jargon with no referent, next to a
 * scope label like `root/(agent_adapter+5)`. Every control here now carries
 * the question it answers, a human name, and a live count, and the scope
 * chip spells its contents out instead of printing a machine string.
 *
 * L1/L0 are gone from the ladder, not hidden: §7 measured 2 import edges
 * across 413 files and §2's instruction for that case is "cut, not styled".
 *
 * The button row itself is no longer a static two-entry array:
 * `MONOREPO_HIERARCHY.md`'s ladder varies per repo, so `rungs` comes from
 * the current `GraphResponse` (`AtlasCanvas`) instead of a local constant.
 */
export interface Rung {
  level: Altitude;
  depth: number | null;
  label: string;
}

interface AltitudeSwitcherProps {
  altitude: Altitude;
  /** The full breadcrumb stack, root first -- one chip per entry beyond the
   * root, each restoring the ladder back to that point when clicked. */
  ladder: { level: Altitude; scope: string | null }[];
  rungs: Rung[];
  nodeCount: number;
  edgeCount: number;
}

export function AltitudeSwitcher({ altitude, ladder, rungs, nodeCount, edgeCount }: AltitudeSwitcherProps) {
  const jumpTo = useAtlasStore((s) => s.jumpTo);
  const ascendTo = useAtlasStore((s) => s.ascendTo);
  const active = rungs.find((r) => r.level === altitude) ?? rungs[0];

  return (
    <div className="absolute left-3 top-3 z-10 flex flex-col gap-1.5">
      <div className="flex items-center gap-2">
        <span className="text-xs" style={{ color: "var(--atlas-text-dim)" }}>
          Altitude — how far out the map is zoomed
        </span>
      </div>

      <div className="flex flex-wrap items-center gap-2 text-sm">
        {rungs.map(({ level, label, depth }) => (
          <button
            key={level}
            onClick={() => jumpTo(level)}
            title={depth == null ? "every module, route, table and process, individually" : label}
            className="atlas-btn-primary rounded px-2.5 py-1"
            style={{
              background: level === altitude ? "var(--atlas-accent)" : "var(--atlas-bg-2)",
              color: level === altitude ? "#07090c" : "var(--atlas-text-dim)",
              border: "1px solid var(--atlas-border)",
            }}
          >
            {label}
          </button>
        ))}

        {ladder.slice(1).map((entry, i) => (
          <button
            key={`${entry.level}:${entry.scope}`}
            onClick={() => ascendTo(i + 1)}
            title={`Showing only ${entry.scope} and what it touches. Click to go back to this point.`}
            className="rounded px-2 py-1 text-xs"
            style={{
              background: "var(--atlas-bg-2)",
              color: "var(--atlas-text)",
              border: "1px solid var(--atlas-border)",
            }}
          >
            inside <span className="font-medium">{entry.scope}</span> ✕
          </button>
        ))}
      </div>

      <div className="text-xs" style={{ color: "var(--atlas-text-dim)" }}>
        {nodeCount.toLocaleString()} node{nodeCount === 1 ? "" : "s"}, {edgeCount.toLocaleString()} connection
        {edgeCount === 1 ? "" : "s"}
        {active?.depth != null && " · double-click a node to go inside it"}
      </div>
    </div>
  );
}
