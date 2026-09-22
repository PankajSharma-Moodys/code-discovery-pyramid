import { useEffect, useState } from "react";
import { MutationAuthError, useRunEvents, useRunMutation, useStatus } from "../../api/controlRoomHooks.ts";
import { useControlRoomStore, type DispatchTarget } from "../../store/controlRoomStore.ts";
import { taskStateColor, taskStateStroke } from "../../theme/taskState.ts";

type TargetKind = DispatchTarget["kind"];

/** Live wave board over `snapshot_task`/`snapshot_run` -- `WEB_RESEARCH.md`
 * §4.2. `useStatus`'s poll is the state of record; `useRunEvents` only
 * overlays faster, additive updates while a job is in flight and the tab is
 * open (see its own doc comment for why it never fully replaces the poll). */
export function RunConsole() {
  const { data: status } = useStatus();
  const dispatchTarget = useControlRoomStore((s) => s.dispatchTarget);
  const setDispatchTarget = useControlRoomStore((s) => s.setDispatchTarget);
  const resume = useControlRoomStore((s) => s.resume);
  const setResume = useControlRoomStore((s) => s.setResume);
  const run = useRunMutation();
  const [scopeDraft, setScopeDraft] = useState("");
  const [waveDraft, setWaveDraft] = useState("0");

  // Stays enabled from dispatch through the SSE `complete` event; a fresh
  // dispatch re-enables it (the effect below flips it back on whenever a
  // mutation successfully starts/joins a job), even if the prior run had
  // already completed.
  const [jobInFlight, setJobInFlight] = useState(false);
  useEffect(() => {
    if (run.isSuccess) setJobInFlight(true);
  }, [run.isSuccess, run.data]);
  const events = useRunEvents(jobInFlight);
  useEffect(() => {
    if (events.complete) setJobInFlight(false);
  }, [events.complete]);

  const taskState = (node: string, fallback: string) => events.tasks.get(node)?.state ?? fallback;

  return (
    <div className="atlas-card flex flex-col gap-4 p-4" style={{ color: "var(--atlas-text)" }}>
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <select
          value={dispatchTarget.kind}
          onChange={(e) => {
            const kind = e.target.value as TargetKind;
            if (kind === "scope") setDispatchTarget({ kind: "scope", node: scopeDraft });
            else if (kind === "wave") setDispatchTarget({ kind: "wave", wave: Number(waveDraft) || 0 });
            else setDispatchTarget({ kind });
          }}
          className="rounded border px-2 py-1"
          style={{ background: "var(--atlas-bg-2)", borderColor: "var(--atlas-border)", color: "var(--atlas-text)" }}
        >
          <option value="wave-all">wave-all</option>
          <option value="stale-only">stale-only</option>
          <option value="scope">scope:…</option>
          <option value="wave">wave:N</option>
        </select>

        {dispatchTarget.kind === "scope" && (
          <input
            value={scopeDraft}
            onChange={(e) => {
              setScopeDraft(e.target.value);
              setDispatchTarget({ kind: "scope", node: e.target.value });
            }}
            placeholder="node id"
            className="rounded border px-2 py-1"
            style={{ background: "var(--atlas-bg-2)", borderColor: "var(--atlas-border)", color: "var(--atlas-text)" }}
          />
        )}
        {dispatchTarget.kind === "wave" && (
          <input
            type="number"
            value={waveDraft}
            onChange={(e) => {
              setWaveDraft(e.target.value);
              setDispatchTarget({ kind: "wave", wave: Number(e.target.value) || 0 });
            }}
            className="w-16 rounded border px-2 py-1"
            style={{ background: "var(--atlas-bg-2)", borderColor: "var(--atlas-border)", color: "var(--atlas-text)" }}
          />
        )}

        <label className="flex items-center gap-1 text-xs" style={{ color: "var(--atlas-text-dim)" }}>
          <input type="checkbox" checked={resume} onChange={(e) => setResume(e.target.checked)} />
          resume
        </label>

        <button
          onClick={() => run.mutate({ target: dispatchTarget, resume })}
          disabled={run.isPending}
          className="atlas-btn-primary rounded px-3 py-1"
          style={{ background: "var(--atlas-accent)", color: "#07090c", opacity: run.isPending ? 0.6 : 1 }}
        >
          dispatch
        </button>

        <button
          onClick={() => run.mutate({ target: { kind: "wave-all" }, resume: true })}
          disabled={run.isPending}
          className="rounded border px-3 py-1 text-xs"
          style={{ borderColor: "var(--atlas-border)", color: "var(--atlas-text-dim)" }}
        >
          resume run
        </button>

        {run.data?.status === "joined" && (
          <span className="text-xs" style={{ color: "var(--atlas-inferred)" }}>
            already running (job {run.data.job_id})
          </span>
        )}
        {run.isError && (
          <span className="text-xs" style={{ color: "var(--atlas-contested)" }}>
            {run.error instanceof MutationAuthError ? "bad or missing mutation token" : "dispatch failed"}
          </span>
        )}
      </div>

      <div className="flex flex-col gap-2">
        {status?.waves.map((wave) => (
          <div key={wave.wave} className="flex flex-col gap-1">
            <div className="flex items-center justify-between text-xs" style={{ color: "var(--atlas-text-dim)" }}>
              <span>
                wave {wave.wave} (L{wave.level}) -- {wave.done}/{wave.total}
              </span>
              <span>{wave.file_count} files, {wave.loc} loc</span>
            </div>
            <div className="flex flex-wrap gap-1">
              {wave.nodes.map((node) => {
                const state = taskState(node.node, node.status);
                return (
                  <span
                    key={node.node}
                    title={`${node.node}: ${state}`}
                    className="rounded border px-1.5 py-0.5 text-xs"
                    style={{
                      borderColor: taskStateColor(state),
                      borderStyle: taskStateStroke(state),
                      color: taskStateColor(state),
                    }}
                  >
                    {node.node}
                  </span>
                );
              })}
            </div>
          </div>
        ))}
        {status?.waves.length === 0 && (
          <div className="text-xs" style={{ color: "var(--atlas-text-dim)" }}>
            no waves scheduled yet
          </div>
        )}
      </div>

      <table className="w-full text-left text-xs" style={{ color: "var(--atlas-text-dim)" }}>
        <thead>
          <tr style={{ color: "var(--atlas-text)" }}>
            <th className="pb-1 pr-2">node</th>
            <th className="pb-1 pr-2">state</th>
            <th className="pb-1 pr-2">attempts</th>
            <th className="pb-1">last error</th>
          </tr>
        </thead>
        <tbody>
          {status?.tasks.map((task) => {
            const state = taskState(task.node, task.state);
            const lastError = events.tasks.get(task.node)?.last_error ?? task.last_error;
            return (
              <tr key={task.node} style={{ borderTop: "1px solid var(--atlas-border)" }}>
                <td className="py-1 pr-2 font-mono">{task.node}</td>
                <td className="py-1 pr-2" style={{ color: taskStateColor(state) }}>
                  {state}
                </td>
                <td className="py-1 pr-2">{task.attempts}</td>
                <td className="py-1">{lastError ?? ""}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
