import { RepoHealthStrip } from "./RepoHealthStrip.tsx";
import { RunConsole } from "./RunConsole.tsx";
import { TrajectoryExplorer } from "./TrajectoryExplorer.tsx";

/** Deep-analysis dashboard, pre/during-scan (`WEB_RESEARCH.md` §2, §4). Ships the
 * repo health strip, run console, and trajectory explorer. Agent setup and
 * model conformance checking live on the Setup tab. The L4 constellation/time
 * scrubber (Phase 4) is a separate, later pass -- see `web/frontend/TODO.md`.
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
        </div>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <div className="md:col-span-2">
            <RepoHealthStrip />
          </div>
          <div className="md:col-span-2">
            <RunConsole />
          </div>
          <div className="md:col-span-2">
            <TrajectoryExplorer />
          </div>
        </div>
      </div>
    </div>
  );
}
