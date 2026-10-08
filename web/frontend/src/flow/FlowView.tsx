import "@xyflow/react/dist/style.css";
import { Background, Controls, ReactFlow, ReactFlowProvider, useReactFlow, type Edge, type Node } from "@xyflow/react";
import { useEffect, useMemo, useState } from "react";
import { useFlow } from "../api/flowHooks.ts";
import { InspectorRail } from "../panels/InspectorRail.tsx";
import { FlowBoxNode, FlowContainerNode } from "./FlowBoxNode.tsx";
import { toRfEdges, toRfNodes } from "./flowGraph.ts";
import { layoutFlow } from "./flowLayout.ts";
import { buildView, trace, type ViewEdge, type ViewNode } from "./flowModel.ts";

const nodeTypes = { flowBox: FlowBoxNode, group: FlowContainerNode };
const EMPTY = "No data-flow edges in this scan — try “+ calls”, or run Scan on a repo with routes/tables.";

function FlowCanvas() {
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [selected, setSelected] = useState<ViewNode | null>(null);
  const [include, setInclude] = useState<string[]>([]);
  const [hoverEdge, setHoverEdge] = useState<{ edge: ViewEdge; x: number; y: number } | null>(null);
  const { data, error, isLoading } = useFlow(include);
  const { fitView } = useReactFlow();

  const model = useMemo(() => (data ? buildView(data, expanded) : null), [data, expanded]);
  const boxes = useMemo(() => (model && model.nodes.length ? layoutFlow(model) : null), [model]);
  const tr = useMemo(() => (model && selected ? trace(model.edges, selected.id) : null), [model, selected]);
  const rfNodes = useMemo(
    () => (model && boxes ? toRfNodes(model.nodes, boxes, tr, selected?.id ?? null) : []),
    [model, boxes, tr, selected],
  );
  const rfEdges = useMemo(
    () => (model ? toRfEdges(model.edges, tr, selected?.id ?? null) : []),
    [model, tr, selected],
  );

  // Re-fit after the layout changes (expand/collapse, include toggles).
  useEffect(() => {
    if (boxes) requestAnimationFrame(() => void fitView({ padding: 0.15 }));
  }, [boxes, fitView]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setSelected(null);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const toggle = (key: string) =>
    setInclude((cur) => (cur.includes(key) ? cur.filter((k) => k !== key) : [...cur, key]));

  const onNodeClick = (_: unknown, rf: Node) => {
    const n = (rf.data as { node: ViewNode }).node;
    if (n.isGroup) {
      if (n.count > 150 && !window.confirm(`Expand ${n.count} items?`)) return;
      setExpanded((s) => new Set(s).add(n.id));
      setSelected(null);
    } else if (n.isContainer) {
      setExpanded((s) => {
        const next = new Set(s);
        next.delete(n.id);
        return next;
      });
      setSelected(null);
    } else {
      setSelected(n);
    }
  };

  let body;
  if (isLoading) body = <Centered>loading flow…</Centered>;
  else if (error) body = <Centered>{error instanceof Error ? error.message : JSON.stringify(error)}</Centered>;
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
        onPaneClick={() => setSelected(null)}
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
      </div>
      {hoverEdge && (
        <div
          className="atlas-card pointer-events-none fixed z-40 px-2 py-1 text-xs"
          style={{ left: hoverEdge.x + 12, top: hoverEdge.y + 12 }}
        >
          {Object.entries(hoverEdge.edge.kinds).map(([k, c]) => `${k} · ${c}`).join(", ")}
        </div>
      )}
      {selected && !selected.isGroup && !selected.isContainer && (
        <InspectorRail
          altitude="L2"
          selectedRawId={selected.id}
          selectedApiNodeId={selected.apiNodeId}
          onClose={() => setSelected(null)}
        />
      )}
    </div>
  );
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
