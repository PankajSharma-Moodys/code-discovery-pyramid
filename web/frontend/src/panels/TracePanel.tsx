import { useMemo, useState } from "react";
import { useSourceFile, useSources, useTrace } from "../api/hooks.ts";
import { useAtlasStore } from "../store/atlasStore.ts";

const CONFIDENCE_COLOR: Record<string, string> = {
  high: "var(--atlas-verified)",
  medium: "var(--atlas-inferred)",
  low: "var(--atlas-unknown)",
};

/** `"file:line"` as returned by `cdp.query.cite()` -- the last `:` is the
 * split point since POSIX repo-relative paths never contain one. */
function parseAnchor(at: string | null): { file: string; line: number } | null {
  if (!at) return null;
  const idx = at.lastIndexOf(":");
  if (idx === -1) return null;
  const line = Number(at.slice(idx + 1));
  if (!Number.isFinite(line)) return null;
  return { file: at.slice(0, idx), line };
}

export function TracePanel() {
  const activeTraceEntry = useAtlasStore((s) => s.activeTraceEntry);
  const startTrace = useAtlasStore((s) => s.startTrace);
  const clearTrace = useAtlasStore((s) => s.clearTrace);
  const [openAnchor, setOpenAnchor] = useState<{ file: string; line: number } | null>(null);

  const { data: sources } = useSources();
  const { data: trace, isLoading } = useTrace(activeTraceEntry);
  const { data: source } = useSourceFile(openAnchor?.file ?? null, openAnchor?.line ?? null);

  const prefersReducedMotion = useMemo(
    () => window.matchMedia("(prefers-reduced-motion: reduce)").matches,
    [],
  );

  return (
    <div
      className="absolute bottom-0 left-0 z-20 max-h-[45%] w-[28rem] overflow-y-auto border-r border-t p-3 text-sm backdrop-blur-md"
      style={{
        background: "color-mix(in srgb, var(--atlas-bg-1) 92%, transparent)",
        borderColor: "var(--atlas-border)",
        color: "var(--atlas-text)",
        boxShadow: "var(--atlas-elev-2)",
      }}
    >
      <div className="mb-2 font-medium">Path trace</div>

      {!activeTraceEntry && (
        <>
          <div className="mb-1 text-xs" style={{ color: "var(--atlas-text-dim)" }}>
            pick a dataflow entry point ({sources?.count ?? 0} available)
          </div>
          <ul className="max-h-48 space-y-1 overflow-y-auto">
            {sources?.sources.map((s, i) => (
              <li key={i}>
                <button
                  onClick={() => startTrace(s.trigger || s.node)}
                  className="w-full truncate rounded border px-2 py-1 text-left text-xs"
                  style={{ borderColor: "var(--atlas-border)" }}
                >
                  {s.node} <span style={{ color: "var(--atlas-text-dim)" }}>({s.channel})</span>
                </button>
              </li>
            ))}
          </ul>
        </>
      )}

      {activeTraceEntry && (
        <>
          <div className="mb-2 flex items-center justify-between">
            <span className="truncate text-xs" style={{ color: "var(--atlas-text-dim)" }}>
              {activeTraceEntry}
            </span>
            <button onClick={clearTrace} className="text-xs" style={{ color: "var(--atlas-text-dim)" }}>
              clear
            </button>
          </div>

          {isLoading && <div style={{ color: "var(--atlas-text-dim)" }}>tracing…</div>}

          {trace && !trace.found && (
            <div className="text-xs" style={{ color: "var(--atlas-unknown)" }}>
              {trace.why}
            </div>
          )}

          {trace && trace.found && (
            <>
              <div className="mb-2 text-xs" style={{ color: "var(--atlas-text-dim)" }}>
                {trace.trail}
              </div>
              <ol className="space-y-1">
                {trace.files.map((row, i) => {
                  const anchor = parseAnchor(row.at ?? null);
                  return (
                    <li
                      key={i}
                      className="rounded border p-2 text-xs"
                      style={{
                        borderColor: "var(--atlas-border)",
                        borderStyle: row.confidence === "high" ? "solid" : row.confidence === "medium" ? "dashed" : "dotted",
                        animation:
                          !prefersReducedMotion && i > 0
                            ? `atlas-hop-in 400ms ease-out ${i * 120}ms both`
                            : undefined,
                      }}
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span className="truncate">{row.why}</span>
                        <span
                          className="shrink-0"
                          style={{ color: CONFIDENCE_COLOR[row.confidence] ?? "var(--atlas-text-dim)" }}
                        >
                          {row.confidence}
                        </span>
                      </div>
                      {anchor ? (
                        <button
                          onClick={() => setOpenAnchor(anchor)}
                          className="mt-1 underline"
                          style={{ color: "var(--atlas-accent)" }}
                        >
                          {row.file}:{anchor.line}
                        </button>
                      ) : (
                        <div className="mt-1" style={{ color: "var(--atlas-text-dim)" }}>
                          {row.file} (no line anchor)
                        </div>
                      )}
                    </li>
                  );
                })}
              </ol>
            </>
          )}

          {openAnchor && (
            <pre
              className="mt-2 max-h-40 overflow-auto rounded border p-2 font-mono text-xs"
              style={{ borderColor: "var(--atlas-border)", background: "var(--atlas-bg-0)" }}
            >
              {source?.lines.map((line, idx) => {
                const lineNo = (source.start_line ?? 1) + idx;
                const isTarget = lineNo === openAnchor.line;
                return (
                  <div
                    key={idx}
                    style={{ background: isTarget ? "color-mix(in srgb, var(--atlas-accent) 20%, transparent)" : undefined }}
                  >
                    {lineNo} {line}
                  </div>
                );
              }) ?? "loading…"}
            </pre>
          )}
        </>
      )}
    </div>
  );
}
