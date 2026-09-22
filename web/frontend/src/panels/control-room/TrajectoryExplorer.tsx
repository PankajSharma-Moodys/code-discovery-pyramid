import { useMemo, useState } from "react";
import { useTrajectoryRuns } from "../../api/hookupHooks.ts";

const cardStyle = { color: "var(--atlas-text)" };

const fieldStyle = {
  background: "var(--atlas-bg-2)",
  borderColor: "var(--atlas-border)",
  color: "var(--atlas-text)",
};

type RegretFilter = "any" | "positive" | "zero";

/** Trajectory-run filter/explorer over `~/.cdp/trajectories.db`'s
 * `fact_leaf_run` (`WEB_RESEARCH.md` §4, Phase 5) -- read-only, no lesson
 * diff/holdout UI (those need `lesson_promotion`/`lesson_cut`, both empty
 * right now). `shape` re-queries the server (its one real filter param);
 * outcome (`state`) and elision-regret are filtered client-side. */
export function TrajectoryExplorer() {
  const [shape, setShape] = useState<string | null>(null);
  const [state, setState] = useState<string>("all");
  const [regret, setRegret] = useState<RegretFilter>("any");

  const trajectory = useTrajectoryRuns(shape, 500);
  const runs = trajectory.data?.runs ?? [];

  const shapes = useMemo(
    () => Array.from(new Set(runs.map((r) => r.scope_shape))).sort(),
    [runs],
  );
  const states = useMemo(
    () => Array.from(new Set(runs.map((r) => r.state).filter((s): s is string => Boolean(s)))).sort(),
    [runs],
  );

  const filtered = runs.filter((r) => {
    if (state !== "all" && r.state !== state) return false;
    if (regret === "positive" && !(r.elision_regret != null && r.elision_regret > 0)) return false;
    if (regret === "zero" && !(r.elision_regret != null && r.elision_regret === 0)) return false;
    return true;
  });

  return (
    <div className="atlas-card flex flex-col gap-4 p-4" style={cardStyle}>
      <div>
        <h2 className="text-sm font-medium">What did past runs cost, and what did they learn?</h2>
        <p className="text-xs" style={{ color: "var(--atlas-text-dim)" }}>
          One row per leaf agent run, from the shared trajectory store. Filter to find the runs that
          spent tokens without producing claims.
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-2 text-sm">
        <select
          value={shape ?? "all"}
          onChange={(e) => setShape(e.target.value === "all" ? null : e.target.value)}
          className="rounded border px-2 py-1 text-xs"
          style={fieldStyle}
        >
          <option value="all">all shapes</option>
          {shapes.map((s) => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>
        <select
          value={state}
          onChange={(e) => setState(e.target.value)}
          className="rounded border px-2 py-1 text-xs"
          style={fieldStyle}
        >
          <option value="all">all states</option>
          {states.map((s) => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>
        <select
          value={regret}
          onChange={(e) => setRegret(e.target.value as RegretFilter)}
          className="rounded border px-2 py-1 text-xs"
          style={fieldStyle}
        >
          <option value="any">any regret</option>
          <option value="positive">regret &gt; 0</option>
          <option value="zero">regret = 0</option>
        </select>
        <span className="text-xs" style={{ color: "var(--atlas-text-dim)" }}>
          {filtered.length} / {runs.length} runs
        </span>
      </div>

      {trajectory.isError && (
        <div className="rounded border p-2 text-xs" style={{ borderColor: "var(--atlas-border)", color: "var(--atlas-text-dim)" }}>
          trajectory corpus unavailable (no `cdp run` has recorded a leaf outcome yet, or the db is locked)
        </div>
      )}

      {!trajectory.isError && filtered.length === 0 && (
        <div className="rounded border p-2 text-xs" style={{ borderColor: "var(--atlas-border)", color: "var(--atlas-text-dim)" }}>
          no runs match this filter
        </div>
      )}

      {filtered.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs" style={{ color: "var(--atlas-text-dim)" }}>
            <thead>
              <tr style={{ color: "var(--atlas-text)" }}>
                <th className="pr-3 pb-1">node</th>
                <th className="pr-3 pb-1">model</th>
                <th className="pr-3 pb-1">shape</th>
                <th className="pr-3 pb-1">tier</th>
                <th className="pr-3 pb-1">task</th>
                <th className="pr-3 pb-1">state</th>
                <th className="pr-3 pb-1">attempts</th>
                <th className="pr-3 pb-1">wall ms</th>
                <th className="pr-3 pb-1">claims</th>
                <th className="pr-3 pb-1">unknowns</th>
                <th className="pr-3 pb-1">regret</th>
                <th className="pr-3 pb-1">entailment</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((r, i) => (
                // No column combination is a reliable unique id here: `run_id`
                // repeats across scopes in one run, and even `run_id`+`node`
                // repeats -- verified live against the real corpus, this
                // repo's dev-loop scans reused `run_id`s across genuinely
                // distinct rows (different `repo_id`, same timestamp) and a
                // few rows are exact duplicates. The list is read-only and
                // never reorders, so the array index is a safe tiebreaker.
                <tr key={`${r.run_id}:${r.node}:${i}`} className="border-t" style={{ borderColor: "var(--atlas-border)" }}>
                  <td className="py-1 pr-3 font-mono">{r.node}</td>
                  <td className="py-1 pr-3">{r.model}</td>
                  <td className="py-1 pr-3 font-mono">{r.scope_shape}</td>
                  <td className="py-1 pr-3">{r.tier}</td>
                  <td className="py-1 pr-3">{r.task_kind}</td>
                  <td className="py-1 pr-3">{r.state ?? "--"}</td>
                  <td className="py-1 pr-3">{r.attempts ?? "--"}</td>
                  <td className="py-1 pr-3">{r.wall_ms ?? "--"}</td>
                  <td className="py-1 pr-3">{r.claims_emitted ?? "--"}</td>
                  <td className="py-1 pr-3">{r.unknowns_emitted ?? "--"}</td>
                  <td className="py-1 pr-3">{r.elision_regret ?? "--"}</td>
                  <td className="py-1 pr-3">
                    {r.entailed ?? "--"}/{r.consistent ?? "--"}/{r.contradicted ?? "--"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
