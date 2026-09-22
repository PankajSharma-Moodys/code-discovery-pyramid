import { useState } from "react";
import { useRepos } from "../api/controlRoomHooks.ts";
import { useRepoStore } from "../store/repoStore.ts";

/** Global repo switcher -- every hook in `api/hooks.ts`/`controlRoomHooks.ts`
 * reads the active repo reactively off `store/repoStore.ts`
 * (`api/repoParams.ts`), so picking a row here refetches the whole app (Atlas
 * canvas, Control Room, Links) against the new repo, not just this panel.
 *
 * Lists every state dir the local `cdp` registry knows about
 * (`GET /api/repos`) -- the same source `RepoHealthStrip` already reads for
 * the "current" row, just offered as a full list instead of only its first
 * entry. */
export function RepoPicker() {
  const [open, setOpen] = useState(false);
  const { data, isLoading } = useRepos();
  const repoId = useRepoStore((s) => s.repoId);
  const setRepo = useRepoStore((s) => s.setRepo);

  const repos = data?.repos ?? [];
  const current = repos.find((r) => r.repo_id === repoId) ?? repos[0];
  const currentLabel = current?.repo_id ?? "this repo";

  return (
    <div className="absolute left-3 top-3 z-30 text-sm">
      <button
        onClick={() => setOpen((v) => !v)}
        className="atlas-card flex max-w-64 items-center gap-2 truncate rounded px-2 py-1"
        style={{ color: "var(--atlas-text)" }}
        title={current?.state_dir}
      >
        <span
          className="h-1.5 w-1.5 shrink-0 rounded-full"
          style={{ background: current?.error ? "var(--atlas-contested)" : "var(--atlas-verified)" }}
        />
        <span className="truncate font-medium">{currentLabel}</span>
        <span style={{ color: "var(--atlas-text-dim)" }}>{open ? "▲" : "▼"}</span>
      </button>

      {open && (
        <div
          className="atlas-card absolute left-0 top-full mt-1 flex max-h-96 w-80 flex-col gap-1 overflow-y-auto p-1"
          style={{ color: "var(--atlas-text)" }}
        >
          {isLoading && (
            <div className="px-2 py-1.5 text-xs" style={{ color: "var(--atlas-text-dim)" }}>
              loading repos…
            </div>
          )}
          {!isLoading && repos.length === 0 && (
            <div className="px-2 py-1.5 text-xs" style={{ color: "var(--atlas-text-dim)" }}>
              no repos registered -- run `cdp scan` somewhere
            </div>
          )}
          {repos.map((repo) => {
            const isCurrent = repo.repo_id === (current?.repo_id ?? repoId);
            const selectable = !repo.error;
            return (
              <button
                key={repo.repo_id}
                disabled={!selectable}
                onClick={() => {
                  setRepo({
                    repo: repo.repo_path ?? ".",
                    stateDir: repo.state_dir,
                    repoId: repo.repo_id,
                  });
                  setOpen(false);
                }}
                className="flex flex-col items-start gap-0.5 rounded px-2 py-1.5 text-left text-xs"
                style={{
                  background: isCurrent ? "color-mix(in srgb, var(--atlas-accent) 14%, transparent)" : "transparent",
                  opacity: selectable ? 1 : 0.5,
                  cursor: selectable ? "pointer" : "not-allowed",
                }}
              >
                <span className="flex w-full items-center justify-between gap-2">
                  <span className="truncate font-medium" style={{ color: "var(--atlas-text)" }}>
                    {repo.repo_id}
                  </span>
                  {isCurrent && <span style={{ color: "var(--atlas-accent)" }}>current</span>}
                </span>
                {repo.error ? (
                  <span style={{ color: "var(--atlas-contested)" }}>{repo.error}</span>
                ) : (
                  <span style={{ color: "var(--atlas-text-dim)" }}>
                    HEAD {repo.head?.slice(0, 10) ?? "unknown"}
                    {repo.behind != null && repo.behind > 0 ? ` — ${repo.behind} behind` : ""}
                    {!repo.repo_path && " — no working-tree path recorded, source browsing may not work"}
                  </span>
                )}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
