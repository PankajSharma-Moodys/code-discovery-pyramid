import { useRefreshMutation, useRepos, useStatus } from "../../api/controlRoomHooks.ts";
import { useControlRoomStore } from "../../store/controlRoomStore.ts";

const FRESHNESS_ORDER = [
  { key: "live", label: "live", color: "var(--atlas-verified)" },
  { key: "stale", label: "stale", color: "var(--atlas-inferred)" },
  { key: "unreviewed", label: "unreviewed", color: "var(--atlas-unknown)" },
  { key: "unknown_churn", label: "unknown churn", color: "var(--atlas-contested)" },
] as const;

/** HEAD vs `as_of`, coverage, freshness buckets, one-click refresh --
 * `WEB_RESEARCH.md` §4.3. No live diff preview of decaying claims here:
 * that's a separate, larger feature (§4.3's "live diff preview of which
 * claims decay") out of scope for this pass. */
export function RepoHealthStrip() {
  const { data: repos } = useRepos();
  const { data: status } = useStatus();
  const refreshMode = useControlRoomStore((s) => s.refreshMode);
  const refresh = useRefreshMutation();

  // `RepoPicker` (global, `App.tsx`) is the actual switcher now -- this strip
  // just shows whichever repo `store/repoStore.ts` currently points at.
  // `/api/repos` (`app.py:get_repos`) resolves the active `repo`/`state_dir`
  // itself and guarantees index 0 is that repo's row, even when its registry
  // entry is missing entirely or another repo sorts first alphabetically --
  // so this is never "whichever repo happens to be first in the registry".
  const repo = repos?.repos[0];

  const coverage = status?.coverage;
  const freshness = status?.freshness;
  const freshnessTotal = freshness
    ? freshness.live + freshness.stale + freshness.unreviewed + freshness.unknown_churn
    : 0;

  return (
    <div
      className="atlas-card atlas-card--hero flex flex-col gap-3 p-4"
      style={{ color: "var(--atlas-text)" }}
    >
      <div className="flex items-center justify-between gap-4">
        <div className="text-sm">
          <span className="font-medium">HEAD</span>{" "}
          <span className="font-mono text-xs" style={{ color: "var(--atlas-text-dim)" }}>
            {repo?.head?.slice(0, 10) ?? "unknown"}
          </span>
          {" vs as_of "}
          <span className="font-mono text-xs" style={{ color: "var(--atlas-text-dim)" }}>
            {repo?.as_of_commit?.slice(0, 10) ?? "unknown"}
          </span>
          {repo?.behind != null && repo.behind > 0 && (
            <span className="ml-2 rounded px-1.5 py-0.5 text-xs" style={{ background: "var(--atlas-inferred)", color: "#07090c" }}>
              {repo.behind} commit{repo.behind === 1 ? "" : "s"} behind
            </span>
          )}
          {repo?.error && (
            <span className="ml-2 text-xs" style={{ color: "var(--atlas-contested)" }}>
              {repo.error}
            </span>
          )}
        </div>

        <button
          onClick={() => refresh.mutate({ mode: refreshMode })}
          disabled={refresh.isPending}
          className="atlas-btn-primary rounded px-3 py-1 text-sm"
          style={{ background: "var(--atlas-accent)", color: "#07090c", opacity: refresh.isPending ? 0.6 : 1 }}
        >
          {refresh.isPending ? "refreshing…" : "refresh"}
        </button>
      </div>

      {coverage && (
        <div className="flex flex-col gap-1">
          <div className="flex items-baseline gap-2 text-xs" style={{ color: "var(--atlas-text-dim)" }}>
            <span>How much of the repo has been read?</span>
            <span
              className="atlas-stat-display"
              style={{ fontSize: "1.25rem", color: "var(--atlas-text)" }}
            >
              {Math.round(coverage.fraction * 100)}%
            </span>
            <span>
              {coverage.files_complete.toLocaleString()} of {coverage.files_total.toLocaleString()}{" "}
              files
            </span>
          </div>

          <div className="h-2 w-full overflow-hidden rounded" style={{ background: "var(--atlas-bg-2)" }}>
            <div
              className={refresh.isPending ? "atlas-bar-fill--pending h-full" : "h-full"}
              style={{
                width: `${Math.max(coverage.fraction * 100, coverage.files_complete > 0 ? 2 : 0)}%`,
                background: "var(--atlas-verified)",
              }}
            />
          </div>

          {/* ATLAS_REDESIGN.md sec 5: an empty bar at 0% used to read as an
              alarm -- something broken -- when it only ever means no wave has
              run against this snapshot. Say that, and make the next action the
              thing right next to it. */}
          {coverage.files_complete === 0 && (
            <div className="text-xs" style={{ color: "var(--atlas-text-dim)" }}>
              Nothing read yet — this isn't an error. Dispatch a wave below to start filling this
              in.
            </div>
          )}
        </div>
      )}

      {freshness && freshnessTotal > 0 && (
        <div className="flex flex-col gap-1">
          <span className="text-xs" style={{ color: "var(--atlas-text-dim)" }}>
            How much of what we know is still true?
          </span>
          <div className="flex h-2 overflow-hidden rounded">
            {FRESHNESS_ORDER.map(({ key, color, label }) => {
              const count = freshness[key];
              if (count === 0) return null;
              return (
                <div
                  key={key}
                  title={`${label}: ${count}`}
                  style={{ width: `${(count / freshnessTotal) * 100}%`, background: color }}
                />
              );
            })}
          </div>
          <div className="flex flex-wrap gap-x-3 text-xs" style={{ color: "var(--atlas-text-dim)" }}>
            {FRESHNESS_ORDER.map(({ key, color, label }) =>
              freshness[key] === 0 ? null : (
                <span key={key}>
                  <span style={{ color }}>■</span> {freshness[key]} {label}
                </span>
              ),
            )}
          </div>

          {/* Same trap as the coverage bar (ATLAS_REDESIGN.md sec 5): before
              any wave runs, every claim is `unknown_churn`, which paints the
              whole bar in the contested colour and reads as "176 things are
              broken". It means the opposite -- nothing has been checked yet. */}
          {freshness.unknown_churn === freshnessTotal && (
            <div className="text-xs" style={{ color: "var(--atlas-text-dim)" }}>
              Every claim is unchecked against the current commit, which is why this bar is one
              colour — not because anything failed. Refresh to sort them.
            </div>
          )}
        </div>
      )}

      {refresh.isError && (
        <div className="text-xs" style={{ color: "var(--atlas-contested)" }}>
          refresh failed -- check the mutation token below
        </div>
      )}
    </div>
  );
}
