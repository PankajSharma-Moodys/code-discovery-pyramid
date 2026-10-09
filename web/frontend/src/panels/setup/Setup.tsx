import { DoctorHeatmap } from "../control-room/DoctorHeatmap.tsx";
import { HookupTab } from "../control-room/HookupTab.tsx";
import { TokenGate } from "../control-room/TokenGate.tsx";

/** One-time setup page for agent integration. Setup is a one-off task --
 * connecting cdp to agent tools, checking model conformance -- separate
 * from the Control Room's deep-analysis workflow. */
export function Setup() {
  return (
    <div className="h-screen w-screen overflow-y-auto p-6" style={{ background: "var(--atlas-bg-0)" }}>
      <div className="mx-auto flex max-w-5xl flex-col gap-4">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-lg font-medium" style={{ color: "var(--atlas-text)" }}>
              Setup
            </h1>
            <p className="text-xs" style={{ color: "var(--atlas-text-dim)" }}>
              Connect cdp to your agent tools and check which models qualify.
            </p>
          </div>
          <TokenGate />
        </div>
        <div className="flex flex-col gap-4">
          <HookupTab />
          <DoctorHeatmap />
        </div>
      </div>
    </div>
  );
}
