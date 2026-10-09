import "@xyflow/react/dist/style.css";
import { Background, Controls, ReactFlow, ReactFlowProvider, useReactFlow, type Edge, type Node } from "@xyflow/react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useFlow } from "../api/flowHooks.ts";
import { useRepoParams } from "../api/repoParams.ts";
import { InspectorRail } from "../panels/InspectorRail.tsx";
import { FlowBoxNode, FlowContainerNode } from "./FlowBoxNode.tsx";
import { toRfEdges, toRfNodes } from "./flowGraph.ts";
import { INITIAL_VIEW, popState, pushState, sameView, type FlowViewState } from "./flowHistory.ts";
import { layoutFlow } from "./flowLayout.ts";
import { buildView, trace, type ViewEdge, type ViewNode } from "./flowModel.ts";

const nodeTypes = { flowBox: FlowBoxNode, flowGroup: FlowContainerNode };
const EMPTY = "No data-flow edges in this scan — try “+ calls”, or run Scan on a repo with routes/tables.";

function FlowCanvas() {
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [history, setHistory] = useState<FlowViewState[]>([]);
  const [fitTick, setFitTick] = useState(0); // bumped by Back/Reset to refit the whole graph
  const [include, setInclude] = useState<string[]>([]);
  const [hoverEdge, setHoverEdge] = useState<{ edge: ViewEdge; x: number; y: number } | null>(null);
  const { data, error, isLoading } = useFlow(include);
  const repoKey = JSON.stringify(useRepoParams());
  const { fitView } = useReactFlow();
  const pendingFit = useRef<string | null>(null); // container id just expanded

  const model = useMemo(() => (data ? buildView(data, expanded) : null), [data, expanded]);
  const boxes = useMemo(() => (model && model.nodes.length ? layoutFlow(model) : null), [model]);
  // A selection that no longer exists (include toggle, refetch) is dropped.
  const live = (selectedId && model?.nodes.find((n) => n.id === selectedId)) || null;
  // A vanished node is cleared (not just hidden) so it is never silently re-selected.
  if (model && selectedId && !live) setSelectedId(null);
  const currentView = (): FlowViewState => ({ expanded: [...expanded].sort(), selectedId: live?.id ?? null });
  const record = () => setHistory((h) => pushState(h, currentView()));
  const clearSelection = () => {
    if (!live) return;
    record();
    setSelectedId(null);
  };
  const tr = useMemo(() => (model && live ? trace(model.edges, live.id) : null), [model, live]);
  const collapse = useCallback(
    (id: string) =>
      setExpanded((s) => {
        const next = new Set(s);
        next.delete(id);
        return next;
      }),
    [],
  );
  const collapseRecorded = (id: string) => {
    record();
    collapse(id);
  };
  const rfNodes = useMemo(
    () =>
      model && boxes
        ? toRfNodes(model.nodes, boxes, tr, live?.id ?? null).map((n) =>
            n.type === "flowGroup" ? { ...n, data: { ...n.data, onCollapse: () => collapseRecorded(n.id) } } : n,
          )
        : [],
    // eslint-disable-next-line react-hooks/exhaustive-deps -- collapseRecorded closes over current view
    [model, boxes, tr, live, collapse, expanded],
  );
  const rfEdges = useMemo(
    () => (model ? toRfEdges(model.edges, tr, live?.id ?? null) : []),
    [model, tr, live],
  );

  // Fit all on first load / collapse / include change; after an expand,
  // centre on the expanded container instead of zooming the whole graph out.
  useEffect(() => {
    if (!boxes) return;
    const target = pendingFit.current;
    pendingFit.current = null;
    requestAnimationFrame(() =>
      void fitView(target ? { nodes: [{ id: target }], padding: 0.1, maxZoom: 1 } : { padding: 0.15 }),
    );
  }, [boxes, fitView, fitTick]);

  // Old node ids may not exist under another repo / include set.
  useEffect(() => setHistory([]), [repoKey, include]);

  const restore = (v: FlowViewState) => {
    pendingFit.current = null;
    setExpanded(new Set(v.expanded));
    setSelectedId(v.selectedId); // dropped by `live` if the node no longer exists
    setFitTick((t) => t + 1);
  };
  const back = () => {
    const { history: rest, state } = popState(history);
    if (!state) return false;
    setHistory(rest);
    restore(state);
    return true;
  };
  const reset = () => {
    if (sameView(currentView(), INITIAL_VIEW)) return;
    record();
    restore(INITIAL_VIEW);
  };
  const atInitial = sameView(currentView(), INITIAL_VIEW);

  const keyRef = useRef({ back, clearSelection });
  keyRef.current = { back, clearSelection };
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") keyRef.current.clearSelection();
      else if (e.key === "Backspace" && !e.repeat && !e.metaKey && !e.ctrlKey && !e.altKey && !e.isComposing && !isEditable(e.target) && keyRef.current.back()) e.preventDefault();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const toggle = (key: string) =>
    setInclude((cur) => (cur.includes(key) ? cur.filter((k) => k !== key) : [...cur, key]));

  const onNodeClick = (_: unknown, rf: Node) => {
    const n = (rf.data as { node: ViewNode }).node;
    if (n.isGroup) {
      if (n.count > 150 && !window.confirm(`Expand ${n.count} items?`)) return;
      record();
      pendingFit.current = n.id;
      setExpanded((s) => new Set(s).add(n.id));
      setSelectedId(null);
    } else if (n.isContainer) {
      clearSelection(); // collapse is via the frame header only
    } else if (n.id !== live?.id) {
      record();
      setSelectedId(n.id);
    }
  };

  let body;
  if (isLoading) body = <Centered>loading flow…</Centered>;
  else if (error) body = <Centered>{errorText(error)}</Centered>;
  else if (!data || data.edges.length === 0 || !boxes) body = <Centered>{EMPTY}</Centered>;
  else
    body = (
      <ReactFlow
        nodes={rfNodes}
        edges={rfEdges as Edge[]}
        nodeTypes={nodeTypes}
        nodesDraggable={false}
        nodesConnectable={false}
        fitView
        minZoom={0.05}
        onNodeClick={onNodeClick}
        onPaneClick={clearSelection}
        onEdgeMouseEnter={(ev, e) =>
          setHoverEdge({ edge: (e.data as { edge: ViewEdge }).edge, x: ev.clientX, y: ev.clientY })
        }
        onEdgeMouseLeave={() => setHoverEdge(null)}
      >
        <Background />
        <Controls showInteractive={false} />
      </ReactFlow>
    );

  return (
    <div className="relative h-screen w-screen" style={{ background: "var(--atlas-bg)", color: "var(--atlas-text)" }}>
      {body}
      <div className="atlas-card absolute left-3 top-3 z-20 flex gap-3 px-3 py-2 text-sm">
        {(["calls", "config"] as const).map((k) => (
          <label key={k} className="flex items-center gap-1">
            <input type="checkbox" checked={include.includes(k)} onChange={() => toggle(k)} />+ {k}
          </label>
        ))}
        <span className="flex gap-2 border-l pl-3" style={{ borderColor: "var(--atlas-border)" }}>
          <HistoryButton label="Back" aria="Back" text="← Back" disabled={history.length === 0} onClick={back} />
          <HistoryButton label="Reset" aria="Reset" text="Reset" disabled={atInitial} onClick={reset} />
        </span>
      </div>
      {hoverEdge && (
        <div
          className="atlas-card pointer-events-none fixed z-40 px-2 py-1 text-xs"
          style={{ left: hoverEdge.x + 12, top: hoverEdge.y + 12 }}
        >
          {Object.entries(hoverEdge.edge.kinds).map(([k, c]) => `${k} · ${c}`).join(", ")}
        </div>
      )}
      {live && !live.isGroup && !live.isContainer && (
        <InspectorRail
          altitude="L2"
          selectedRawId={live.id}
          selectedApiNodeId={live.apiNodeId}
          onClose={clearSelection}
        />
      )}
    </div>
  );
}

function isEditable(t: EventTarget | null): boolean {
  const el = t as HTMLElement | null;
  return !!el && (/^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName) || el.isContentEditable);
}

function HistoryButton(p: { label: string; aria: string; text: string; disabled: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      aria-label={p.aria}
      title={p.label}
      disabled={p.disabled}
      onClick={p.onClick}
      style={{ opacity: p.disabled ? 0.4 : 1, cursor: p.disabled ? "default" : "pointer" }}
    >
      {p.text}
    </button>
  );
}

function errorText(error: unknown): string {
  const detail = (error as { detail?: unknown } | null)?.detail;
  if (typeof detail === "string") return detail;
  const message = (error as { message?: unknown } | null)?.message;
  return typeof message === "string" ? message : "failed to load flow";
}

function Centered({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex h-full w-full items-center justify-center px-8 text-center text-sm" style={{ color: "var(--atlas-text-dim)" }}>
      {children}
    </div>
  );
}

export function FlowView() {
  return (
    <ReactFlowProvider>
      <FlowCanvas />
    </ReactFlowProvider>
  );
}
