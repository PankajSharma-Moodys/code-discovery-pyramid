import { useState } from "react";
import {
  MutationAuthError,
  useDoctorReport,
  useInstallMutation,
  useInstallPreview,
  useJobStatus,
  useLivenessMutation,
  useMcpTools,
} from "../../api/hookupHooks.ts";
import { useControlRoomStore } from "../../store/controlRoomStore.ts";

type Framework = "claude-code" | "langgraph" | "adk" | "none";

const cardStyle = { color: "var(--atlas-text)" };

const fieldStyle = {
  background: "var(--atlas-bg-2)",
  borderColor: "var(--atlas-border)",
  color: "var(--atlas-text)",
};

/** Agent-layer hookup tab (`WEB_RESEARCH.md` §4 item 1) -- a web seam over
 * `cdp install --framework`, `cdp doctor --node` (repurposed as an "is it
 * alive?" liveness probe) and `mcp_server`'s three tools. Nothing here
 * reimplements those; every mutation shells out to the real CLI. */
export function HookupTab() {
  const authToken = useControlRoomStore((s) => s.authToken);

  const [target, setTarget] = useState("");
  const [framework, setFramework] = useState<Framework>("claude-code");
  const [hook, setHook] = useState(false);
  const preview = useInstallPreview(target, framework);
  const install = useInstallMutation();

  const [runnerCmd, setRunnerCmd] = useState("");
  const [model, setModel] = useState("");
  const liveness = useLivenessMutation();
  const [jobId, setJobId] = useState<string | null>(null);
  const jobStatus = useJobStatus(jobId, jobId !== null);
  const doctorReport = useDoctorReport(target, jobStatus.data?.running === false);

  const mcpTools = useMcpTools();
  const [copied, setCopied] = useState(false);

  return (
    <div className="atlas-card flex flex-col gap-4 p-4" style={cardStyle}>
      <div>
        <h2 className="text-sm font-medium">How do I wire CDP into my agent?</h2>
        <p className="text-xs" style={{ color: "var(--atlas-text-dim)" }}>
          Preview and install the adapter for a framework, then check it answers back.
        </p>
      </div>

      {/* 1. Preview + install */}
      <section className="flex flex-col gap-2 text-sm">
        <div className="flex flex-wrap items-center gap-2">
          <input
            value={target}
            onChange={(e) => setTarget(e.target.value)}
            placeholder="target repo path"
            className="min-w-64 rounded border px-2 py-1 font-mono text-xs"
            style={fieldStyle}
          />
          <select
            value={framework}
            onChange={(e) => setFramework(e.target.value as Framework)}
            className="rounded border px-2 py-1"
            style={fieldStyle}
          >
            <option value="claude-code">claude-code</option>
            <option value="langgraph">langgraph</option>
            <option value="adk">adk</option>
            <option value="none">none</option>
          </select>
          {framework === "claude-code" && (
            <label className="flex items-center gap-1 text-xs" style={{ color: "var(--atlas-text-dim)" }}>
              <input type="checkbox" checked={hook} onChange={(e) => setHook(e.target.checked)} />
              also install PreToolUse hook
            </label>
          )}
          <button
            onClick={() => install.mutate({ target, framework, hook })}
            disabled={!authToken || !target.trim() || install.isPending}
            className="atlas-btn-primary rounded px-3 py-1"
            style={{ background: "var(--atlas-accent)", color: "#07090c", opacity: !authToken || !target.trim() ? 0.5 : 1 }}
          >
            install
          </button>
        </div>

        {preview.data && (
          <div className="rounded border p-2 text-xs" style={{ borderColor: "var(--atlas-border)", color: "var(--atlas-text-dim)" }}>
            <div>skill dest: <span className="font-mono">{preview.data.skill_dest}</span></div>
            <div>members: {preview.data.skill_members.join(", ")}</div>
            {preview.data.leaf_agent_file && <div>leaf agent: <span className="font-mono">{preview.data.leaf_agent_file}</span></div>}
            {preview.data.framework_note && <div className="whitespace-pre-wrap">{preview.data.framework_note}</div>}
            <div>AGENTS.md: {preview.data.agents_md_action} ({preview.data.agents_md_path})</div>
          </div>
        )}

        {install.isError && (
          <span className="text-xs" style={{ color: "var(--atlas-contested)" }}>
            {install.error instanceof MutationAuthError ? "bad or missing mutation token" : "install failed"}
          </span>
        )}
        {install.data && (
          <div className="rounded border p-2 text-xs font-mono" style={{ borderColor: "var(--atlas-border)", color: "var(--atlas-text-dim)" }}>
            exit {install.data.returncode}
            {install.data.stdout && <pre className="whitespace-pre-wrap">{install.data.stdout}</pre>}
            {install.data.stderr && <pre className="whitespace-pre-wrap">{install.data.stderr}</pre>}
          </div>
        )}
      </section>

      {/* 2. Is it alive? */}
      <section className="flex flex-col gap-2 border-t pt-3 text-sm" style={{ borderColor: "var(--atlas-border)" }}>
        <div className="text-xs" style={{ color: "var(--atlas-text-dim)" }}>Is it alive?</div>
        <div className="flex flex-wrap items-center gap-2">
          <input
            value={runnerCmd}
            onChange={(e) => setRunnerCmd(e.target.value)}
            placeholder="--runner-cmd"
            className="min-w-56 rounded border px-2 py-1 font-mono text-xs"
            style={fieldStyle}
          />
          <input
            value={model}
            onChange={(e) => setModel(e.target.value)}
            placeholder="--model label"
            className="rounded border px-2 py-1 text-xs"
            style={fieldStyle}
          />
          <button
            onClick={() => {
              setJobId(null);
              liveness.mutate(
                { target, runnerCmd, model },
                { onSuccess: (data) => setJobId(data.job_id) },
              );
            }}
            disabled={!authToken || !target.trim() || !runnerCmd.trim() || !model.trim() || liveness.isPending}
            className="atlas-btn-primary rounded border px-3 py-1 text-xs"
            style={{ borderColor: "var(--atlas-border)", color: "var(--atlas-text-dim)" }}
          >
            run liveness check
          </button>
          <span className="text-xs" style={{ color: "var(--atlas-text-dim)" }}>
            node defaults to the cheapest scope when omitted
          </span>
        </div>

        {liveness.isError && (
          <span className="text-xs" style={{ color: "var(--atlas-contested)" }}>
            {liveness.error instanceof MutationAuthError ? "bad or missing mutation token" : "dispatch failed"}
          </span>
        )}
        {jobId && jobStatus.data?.running && (
          <span className="text-xs" style={{ color: "var(--atlas-inferred)" }}>probe running (job {jobId})…</span>
        )}
        {jobId && jobStatus.data && !jobStatus.data.running && (
          <div className="text-xs" style={{ color: "var(--atlas-text-dim)" }}>
            job finished, exit {jobStatus.data.returncode}
            {Boolean(doctorReport.data?.models[model]) && (
              <pre className="mt-1 whitespace-pre-wrap">{JSON.stringify(doctorReport.data!.models[model], null, 2)}</pre>
            )}
          </div>
        )}
      </section>

      {/* 3. MCP tools */}
      <section className="flex flex-col gap-2 border-t pt-3 text-sm" style={{ borderColor: "var(--atlas-border)" }}>
        <div className="flex items-center justify-between text-xs" style={{ color: "var(--atlas-text-dim)" }}>
          <span>MCP tools</span>
          {mcpTools.data && (
            <button
              onClick={() => {
                void navigator.clipboard.writeText(mcpTools.data!.client_config);
                setCopied(true);
                setTimeout(() => setCopied(false), 1500);
              }}
              className="rounded border px-2 py-0.5"
              style={{ borderColor: "var(--atlas-border)" }}
            >
              {copied ? "copied" : "copy config"}
            </button>
          )}
        </div>
        <ul className="flex flex-col gap-1 text-xs" style={{ color: "var(--atlas-text-dim)" }}>
          {mcpTools.data?.tools.map((tool) => (
            <li key={tool.name}>
              <span className="font-mono" style={{ color: "var(--atlas-text)" }}>{tool.name}</span> -- {tool.description}
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
