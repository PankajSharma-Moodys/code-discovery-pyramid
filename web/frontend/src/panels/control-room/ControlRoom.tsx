import { DoctorHeatmap } from "./DoctorHeatmap.tsx";
import { HookupTab } from "./HookupTab.tsx";
import { RepoHealthStrip } from "./RepoHealthStrip.tsx";
import { RunConsole } from "./RunConsole.tsx";
import { TokenGate } from "./TokenGate.tsx";
import { TrajectoryExplorer } from "./TrajectoryExplorer.tsx";

/** Bento dashboard, pre/during-scan (`WEB_RESEARCH.md` §2, §4). Ships the
 * repo health strip, run console, the agent-layer hookup tab, the doctor
 * heatmap, and the trajectory explorer. The L4 constellation/time scrubber
 * (Phase 4) is a separate, later pass -- see `web/frontend/TODO.md`.
 * Collapses to one column on narrow viewports rather than duplicating the
 * DOM (§5). */
export function ControlRoom() {
  return (
    <div className="h-screen w-screen overflow-y-auto p-6" style={{ background: "var(--atlas-bg-0)" }}>
      <div className="mx-auto flex max-w-5xl flex-col gap-4">
        <div className="flex items-center justify-between">
          <h1 className="text-lg font-medium" style={{ color: "var(--atlas-text)" }}>
            Control Room
          </h1>
          <TokenGate />
        </div>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <div className="md:col-span-2">
            <RepoHealthStrip />
          </div>
          <RunConsole />
          <HookupTab />
          <DoctorHeatmap />
          <TrajectoryExplorer />
        </div>
      </div>
    </div>
  );
}
