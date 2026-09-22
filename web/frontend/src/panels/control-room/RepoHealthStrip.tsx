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

  // Single-repo demo (`DEFAULT_REPO_PARAMS`, `client.ts`) -- no picker yet.
  // `/api/repos` (`app.py:get_repos`) resolves `DEFAULT_REPO_PARAMS` itself
  // and guarantees index 0 is that repo's row, even when its registry entry
  // is missing entirely or another repo sorts first alphabetically -- so
  // this is never "whichever repo happens to be first in the registry".
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
        <div className="flex items-center gap-2 text-xs" style={{ color: "var(--atlas-text-dim)" }}>
          <span>
            coverage {coverage.files_complete}/{coverage.files_total}{" "}
          </span>
          <span className="atlas-stat-display" style={{ fontSize: "1.25rem", color: "var(--atlas-text)" }}>
            {Math.round(coverage.fraction * 100)}%
          </span>
          <div className="h-2 flex-1 overflow-hidden rounded" style={{ background: "var(--atlas-bg-2)" }}>
            <div
              className={refresh.isPending ? "atlas-bar-fill--pending h-full" : "h-full"}
              style={{ width: `${Math.round(coverage.fraction * 100)}%`, background: "var(--atlas-verified)" }}
            />
          </div>
        </div>
      )}

      {freshness && freshnessTotal > 0 && (
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
      )}

      {refresh.isError && (
        <div className="text-xs" style={{ color: "var(--atlas-contested)" }}>
          refresh failed -- check the mutation token below
        </div>
      )}
    </div>
  );
}
