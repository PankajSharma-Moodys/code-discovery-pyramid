import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  MutationAuthError,
  useDoctorReport,
  useJobStatus,
  useLivenessMutation,
} from "../../api/hookupHooks.ts";
import { useControlRoomStore } from "../../store/controlRoomStore.ts";
import { confidenceColor, type ConfidenceBucket } from "../../theme/confidence.ts";

const cardStyle = { color: "var(--atlas-text)" };

const fieldStyle = {
  background: "var(--atlas-bg-2)",
  borderColor: "var(--atlas-border)",
  color: "var(--atlas-text)",
};

function bucket(rate: number | null): ConfidenceBucket {
  if (rate === null) return "unreviewed";
  if (rate >= 0.9) return "high";
  if (rate >= 0.7) return "medium";
  if (rate >= 0.4) return "low";
  return "contested";
}

function pct(rate: number | null): string {
  return rate === null ? "?" : String(Math.round(rate * 100));
}

/** cell for a "higher is better" rate. */
function Cell({ rate }: { rate: number | null }) {
  return (
    <td className="py-1 pr-2 text-center font-mono" style={{ color: confidenceColor(bucket(rate)) }}>
      {pct(rate)}
    </td>
  );
}

/** cell for a "lower is better" rate -- bucketed on `1 - rate` so green stays "good". */
function InvertedCell({ rate }: { rate: number | null }) {
  const good = rate === null ? null : 1 - rate;
  return (
    <td className="py-1 pr-2 text-center font-mono" style={{ color: confidenceColor(bucket(good)) }}>
      {pct(rate)}
    </td>
  );
}

function avgAnchorSurvival(scopeReports: unknown): number | null {
  if (!Array.isArray(scopeReports)) return null;
  const values = scopeReports
    .map((r) => (r && typeof r === "object" ? (r as Record<string, unknown>).anchor_survival : null))
    .filter((v): v is number => typeof v === "number");
  if (values.length === 0) return null;
  return values.reduce((a, b) => a + b, 0) / values.length;
}

function entailmentRate(counts: unknown): number | null {
  if (!counts || typeof counts !== "object") return null;
  const c = counts as Record<string, number>;
  const entailed = c.entailed ?? 0;
  const consistent = c.consistent ?? 0;
  const contradicted = c.contradicted ?? 0;
  const denom = entailed + consistent + contradicted;
  return denom ? entailed / denom : null;
}

function ModelRow({ name, report }: { name: string; report: Record<string, unknown> }) {
  const authToken = useControlRoomStore((s) => s.authToken);
  const queryClient = useQueryClient();
  const [runnerCmd, setRunnerCmd] = useState("");
  const liveness = useLivenessMutation();
  const [jobId, setJobId] = useState<string | null>(null);
  const jobStatus = useJobStatus(jobId, jobId !== null);

  useEffect(() => {
    if (jobId && jobStatus.data && !jobStatus.data.running) {
      void queryClient.invalidateQueries({ queryKey: ["doctor", "."] });
      setJobId(null);
    }
  }, [jobId, jobStatus.data, queryClient]);

  const schemaValidity = report.schema_validity_rate as number | null;
  const anchorSurvival = avgAnchorSurvival(report.scope_reports);
  const entailment = entailmentRate(report.entailment_counts);
  const recall = report.recall as number | null;
  const falseUnknown = report.false_unknown_rate as number | null;

  return (
    <tr style={{ borderTop: "1px solid var(--atlas-border)" }}>
      <td className="py-1 pr-2 font-mono">{name}</td>
      <Cell rate={schemaValidity} />
      <Cell rate={anchorSurvival} />
      <Cell rate={entailment} />
      <Cell rate={recall} />
      <InvertedCell rate={falseUnknown} />
      <td className="py-1 pr-2">
        <div className="flex items-center gap-1">
          <input
            value={runnerCmd}
            onChange={(e) => setRunnerCmd(e.target.value)}
            placeholder="--runner-cmd"
            className="min-w-32 rounded border px-1.5 py-0.5 font-mono text-xs"
            style={fieldStyle}
          />
          <button
            onClick={() => {
              setJobId(null);
              liveness.mutate(
                { target: ".", runnerCmd, model: name },
                { onSuccess: (data) => setJobId(data.job_id) },
              );
            }}
            disabled={!authToken || !runnerCmd.trim() || liveness.isPending}
            className="atlas-btn-primary rounded border px-2 py-0.5 text-xs"
            style={{ borderColor: "var(--atlas-border)", color: "var(--atlas-text-dim)" }}
          >
            run liveness check
          </button>
        </div>
        {liveness.isError && (
          <span className="text-xs" style={{ color: "var(--atlas-contested)" }}>
            {liveness.error instanceof MutationAuthError ? "bad or missing mutation token" : "dispatch failed"}
          </span>
        )}
        {jobId && jobStatus.data?.running && (
          <span className="text-xs" style={{ color: "var(--atlas-inferred)" }}>probe running…</span>
        )}
      </td>
    </tr>
  );
}

/** Doctor / model-compatibility heatmap (`WEB_RESEARCH.md` §4 item 4) -- reads
 * `cdp/doctor.py`'s `aggregate()` output verbatim, adding only the client-side
 * anchor-survival average and entailment rate `aggregate()` doesn't compute.
 * Per-row "run liveness check" reuses `useLivenessMutation` -- there is no
 * backend endpoint for a full multi-scope re-run, so this is honestly a
 * single-scope liveness probe, not a "re-run doctor" button. */
export function DoctorHeatmap() {
  const doctorReport = useDoctorReport(".", true);

  if (doctorReport.isError) {
    return (
      <div className="atlas-card flex flex-col gap-2 p-4 text-sm" style={cardStyle}>
        <h2 className="text-sm font-medium">Doctor / model compatibility</h2>
        <span style={{ color: "var(--atlas-text-dim)" }}>
          no doctor reports yet -- run <span className="font-mono">cdp doctor --model &lt;name&gt;</span> first
        </span>
      </div>
    );
  }

  const models = doctorReport.data?.models ?? {};
  const names = Object.keys(models).sort();

  return (
    <div className="atlas-card flex flex-col gap-3 p-4" style={cardStyle}>
      <h2 className="text-sm font-medium">Doctor / model compatibility</h2>
      <table className="w-full text-left text-xs" style={{ color: "var(--atlas-text-dim)" }}>
        <thead>
          <tr style={{ color: "var(--atlas-text)" }}>
            <th className="pb-1 pr-2">model</th>
            <th className="pb-1 pr-2 text-center">schema valid</th>
            <th className="pb-1 pr-2 text-center">anchor survival</th>
            <th className="pb-1 pr-2 text-center">entailment</th>
            <th className="pb-1 pr-2 text-center">recall</th>
            <th className="pb-1 pr-2 text-center">false unknown</th>
            <th className="pb-1">liveness</th>
          </tr>
        </thead>
        <tbody>
          {names.map((name) => (
            <ModelRow key={name} name={name} report={models[name] as Record<string, unknown>} />
          ))}
        </tbody>
      </table>
      {names.length === 0 && (
        <div className="text-xs" style={{ color: "var(--atlas-text-dim)" }}>no models reported</div>
      )}
    </div>
  );
}
