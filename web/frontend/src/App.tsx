import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useLinks } from "./api/hooks.ts";
import { AtlasCanvas } from "./canvas/AtlasCanvas.tsx";
import { LinksCanvas } from "./canvas/LinksCanvas.tsx";
import { AskBar } from "./panels/AskBar.tsx";
import { ControlRoom } from "./panels/control-room/ControlRoom.tsx";
import { InspectorRail } from "./panels/InspectorRail.tsx";
import { LensSwitcher } from "./panels/LensSwitcher.tsx";
import { PeekCard } from "./panels/PeekCard.tsx";
import { TimeScrubber } from "./panels/TimeScrubber.tsx";
import { TracePanel } from "./panels/TracePanel.tsx";
import { useAtlasStore } from "./store/atlasStore.ts";
import { useViewStore, type View } from "./store/viewStore.ts";

const queryClient = new QueryClient();

/** No router in the project (two top-level views don't need one) --
 * `WEB_RESEARCH.md` §2's "same cmd-K, same ask-bar, same theme" seam, kept
 * as local state rather than a new dependency. */
function ViewSwitcher({
  view,
  setView,
  showLinks,
}: {
  view: View;
  setView: (v: View) => void;
  showLinks: boolean;
}) {
  const VIEWS: { id: View; label: string }[] = [
    { id: "atlas", label: "Atlas" },
    { id: "control-room", label: "Control Room" },
    ...(showLinks ? [{ id: "links" as View, label: "Links" }] : []),
  ];
  return (
    <div className="absolute right-3 top-3 z-30 flex gap-2 text-sm">
      {VIEWS.map(({ id, label }) => (
        <button
          key={id}
          onClick={() => setView(id)}
          className="rounded px-2 py-1"
          style={{
            background: id === view ? "var(--atlas-accent)" : "var(--atlas-bg-2)",
            color: id === view ? "#07090c" : "var(--atlas-text-dim)",
            border: "1px solid var(--atlas-border)",
          }}
        >
          {label}
        </button>
      ))}
    </div>
  );
}

function Atlas() {
  const altitude = useAtlasStore((s) => s.altitude);
  const hoveredNodeId = useAtlasStore((s) => s.hoveredNodeId);
  const hoveredApiNodeId = useAtlasStore((s) => s.hoveredApiNodeId);
  const selectedNodeId = useAtlasStore((s) => s.selectedNodeId);
  const selectedApiNodeId = useAtlasStore((s) => s.selectedApiNodeId);
  const selectNode = useAtlasStore((s) => s.selectNode);

  return (
    <div className="relative h-screen w-screen overflow-hidden">
      <AtlasCanvas />
      <LensSwitcher />
      <PeekCard
        altitude={altitude}
        hoveredRawId={hoveredNodeId}
        hoveredApiNodeId={hoveredApiNodeId}
      />
      <InspectorRail
        altitude={altitude}
        selectedRawId={selectedNodeId}
        selectedApiNodeId={selectedApiNodeId}
        onClose={() => selectNode(null, null)}
      />
      <TracePanel />
      <TimeScrubber />
    </div>
  );
}

function AppShell() {
  const view = useViewStore((s) => s.view);
  const setView = useViewStore((s) => s.setView);
  const { data: links } = useLinks();
  const showLinks = (links?.links.length ?? 0) + (links?.unmatched.length ?? 0) > 0;

  return (
    <div className="relative h-screen w-screen overflow-hidden">
      {view === "atlas" && <Atlas />}
      {view === "control-room" && <ControlRoom />}
      {view === "links" && <LinksCanvas />}
      <ViewSwitcher view={view} setView={setView} showLinks={showLinks} />
      <AskBar />
    </div>
  );
}

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AppShell />
    </QueryClientProvider>
  );
}

export default App;
