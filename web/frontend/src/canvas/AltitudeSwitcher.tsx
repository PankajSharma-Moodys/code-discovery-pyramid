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
 */
const ALTITUDES: { id: Altitude; name: string; caption: string }[] = [
  { id: "L3", name: "Packages", caption: "one node per top-level package or external surface" },
  { id: "L2", name: "Modules", caption: "every module, route, table and process, individually" },
];

interface AltitudeSwitcherProps {
  altitude: Altitude;
  scope: string | null;
  nodeCount: number;
  edgeCount: number;
}

export function AltitudeSwitcher({ altitude, scope, nodeCount, edgeCount }: AltitudeSwitcherProps) {
  const jumpTo = useAtlasStore((s) => s.jumpTo);
  const ascend = useAtlasStore((s) => s.ascend);
  const active = ALTITUDES.find((a) => a.id === altitude) ?? ALTITUDES[0];

  return (
    <div className="absolute left-3 top-3 z-10 flex flex-col gap-1.5">
      <div className="flex items-center gap-2">
        <span className="text-xs" style={{ color: "var(--atlas-text-dim)" }}>
          Altitude — how far out the map is zoomed
        </span>
      </div>

      <div className="flex items-center gap-2 text-sm">
        {ALTITUDES.map(({ id, name, caption }) => (
          <button
            key={id}
            onClick={() => jumpTo(id)}
            title={caption}
            className="atlas-btn-primary rounded px-2.5 py-1"
            style={{
              background: id === altitude ? "var(--atlas-accent)" : "var(--atlas-bg-2)",
              color: id === altitude ? "#07090c" : "var(--atlas-text-dim)",
              border: "1px solid var(--atlas-border)",
            }}
          >
            {name}
          </button>
        ))}

        {scope && (
          <button
            onClick={ascend}
            title={`Showing only ${scope} and what it touches. Click to go back to everything.`}
            className="rounded px-2 py-1 text-xs"
            style={{
              background: "var(--atlas-bg-2)",
              color: "var(--atlas-text)",
              border: "1px solid var(--atlas-border)",
            }}
          >
            inside <span className="font-medium">{scope}</span> ✕
          </button>
        )}
      </div>

      <div className="text-xs" style={{ color: "var(--atlas-text-dim)" }}>
        {active.caption} · {nodeCount.toLocaleString()} node{nodeCount === 1 ? "" : "s"},{" "}
        {edgeCount.toLocaleString()} connection{edgeCount === 1 ? "" : "s"}
        {altitude === "L3" && " · double-click a node to go inside it"}
      </div>
    </div>
  );
}
