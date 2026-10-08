import { useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useFsList, useJob, useScanMutation } from "../api/folderHooks.ts";
import { MutationAuthError, useRepos } from "../api/controlRoomHooks.ts";
import { useRepoParams } from "../api/repoParams.ts";
import { repoIdForPath } from "../api/folderSelection.ts";
import { useRepoStore } from "../store/repoStore.ts";
import { useViewStore } from "../store/viewStore.ts";
import { useControlRoomStore } from "../store/controlRoomStore.ts";
import { TokenGate } from "./control-room/TokenGate.tsx";

const dim = { color: "var(--atlas-text-dim)" } as const;

function Badge({ children }: { children: string }) {
  return (
    <span className="rounded px-1 text-[10px]" style={{ border: "1px solid var(--atlas-border)", ...dim }}>
      {children}
    </span>
  );
}

/** Folder chooser inside the RepoPicker dropdown: browse -> scan -> open. */
export function FolderBrowser({ onClose }: { onClose: () => void }) {
  const [path, setPath] = useState<string | undefined>(undefined);
  const [draft, setDraft] = useState("");
  const [jobId, setJobId] = useState<string | null>(null);
  const [scanned, setScanned] = useState<string | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const handled = useRef<string | null>(null);

  const list = useFsList(path);
  const authToken = useControlRoomStore((s) => s.authToken);
  const scan = useScanMutation();
  const job = useJob(jobId);
  const queryClient = useQueryClient();
  const repoParams = useRepoParams();
  const setRepo = useRepoStore((s) => s.setRepo);
  const setView = useViewStore((s) => s.setView);

  const cur = list.data;
  const repos = useRepos().data?.repos ?? [];
  const scanning = scan.isPending || (jobId != null && !job.isError && job.data?.running !== false);

  useEffect(() => {
    if (!scanning) return;
    const t0 = Date.now();
    const id = setInterval(() => setElapsed(Math.floor((Date.now() - t0) / 1000)), 1000);
    return () => clearInterval(id);
  }, [scanning]);

  const open = (folder: string, repos: ReadonlyArray<{ repo_id: string; repo_path?: string | null }>) => {
    setRepo({ repo: folder, stateDir: folder + "/.cdp", repoId: repoIdForPath(folder, repos) });
  };

  // Completion path: refetch the repos list first so the id is resolved from
  // post-scan data (the new folder is registered server-side by then), not
  // the stale pre-scan list.
  const finished = job.data && !job.data.running ? job.data : null;
  useEffect(() => {
    if (!finished || finished.returncode !== 0 || !scanned || handled.current === finished.job_id) return;
    handled.current = finished.job_id;
    void (async () => {
      await queryClient.invalidateQueries({ queryKey: ["repos"] });
      void queryClient.invalidateQueries({ queryKey: ["fs-list"] });
      const fresh = queryClient.getQueryData<{ repos: { repo_id: string; repo_path?: string | null }[] }>(["repos", repoParams]);
      open(scanned, fresh?.repos ?? []);
    })();
    // `open` only closes over stable store setters.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [finished, scanned, queryClient, repoParams]);

  const go = (p: string | undefined) => {
    setPath(p);
    setDraft("");
    setJobId(null);
    setScanned(null);
    scan.reset();
  };

  const startScan = (folder: string) => {
    setScanned(folder);
    setElapsed(0);
    scan.mutate(folder, { onSuccess: (r) => setJobId(r.job_id) });
  };

  const done = job.data && !job.data.running;
  const failed = done && job.data?.returncode !== 0;

  return (
    <div className="flex flex-col gap-1 p-1 text-xs">
      <div className="flex items-center justify-between px-1">
        <button onClick={onClose} className="underline" style={dim}>← repos</button>
        {cur?.parent && (
          <button onClick={() => go(cur.parent as string)} className="underline" style={dim}>↑ parent</button>
        )}
      </div>
      <form
        className="flex gap-1"
        onSubmit={(e) => {
          e.preventDefault();
          if (draft.trim()) go(draft.trim());
        }}
      >
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder={cur?.path ?? "/path/to/folder"}
          className="min-w-0 flex-1 rounded border px-2 py-1"
          style={{ background: "var(--atlas-bg-2)", borderColor: "var(--atlas-border)", color: "var(--atlas-text)" }}
        />
        <button type="submit" className="rounded px-2 py-1" style={{ border: "1px solid var(--atlas-border)" }}>Go</button>
      </form>

      {list.isError && <div className="px-1" style={{ color: "var(--atlas-contested)" }}>{(list.error as Error).message}</div>}

      {cur && (
        <div className="flex flex-col gap-1 px-1 py-1">
          <div className="truncate font-medium" title={cur.path}>{cur.path}</div>
          {cur.has_scan ? (
            <button
              onClick={() => { open(cur.path, repos); onClose(); }}
              className="rounded px-2 py-1"
              style={{ background: "var(--atlas-accent)", color: "#07090c" }}
            >
              Open
            </button>
          ) : authToken ? (
            <button
              disabled={scanning}
              onClick={() => startScan(cur.path)}
              className="rounded px-2 py-1"
              style={{ background: "var(--atlas-accent)", color: "#07090c", opacity: scanning ? 0.6 : 1 }}
            >
              {scanning ? `scanning… ${elapsed}s` : "Scan this folder"}
            </button>
          ) : (
            <TokenGate />
          )}
          {scan.error instanceof MutationAuthError && (
            <div style={{ color: "var(--atlas-contested)" }}>bad or missing token -- re-enter it above</div>
          )}
          {scan.error && !(scan.error instanceof MutationAuthError) && (
            <div style={{ color: "var(--atlas-contested)" }}>could not start scan</div>
          )}
          {job.isError && <div style={{ color: "var(--atlas-contested)" }}>lost track of the scan job -- check the server</div>}
          {scanning && cur.has_scan && <div style={dim}>scanning… {elapsed}s</div>}
          {failed && (
            <>
              <div style={{ color: "var(--atlas-contested)" }}>scan failed (exit {job.data?.returncode ?? "?"})</div>
              <pre className="max-h-32 overflow-auto whitespace-pre-wrap text-[10px]" style={dim}>{job.data?.log_tail ?? ""}</pre>
            </>
          )}
          {done && !failed && (
            <button
              onClick={() => { setView("control-room"); onClose(); }}
              className="rounded px-2 py-1 text-left"
              style={{ border: "1px solid var(--atlas-accent)", color: "var(--atlas-accent)" }}
            >
              Run deep analysis →
            </button>
          )}
        </div>
      )}

      {list.isLoading && <div className="px-1" style={dim}>loading…</div>}
      {cur?.entries.map((e) => (
        <button
          key={e.path}
          onClick={() => go(e.path)}
          className="flex items-center justify-between gap-2 rounded px-2 py-1 text-left"
        >
          <span className="truncate">{e.name}</span>
          <span className="flex gap-1">
            {e.is_git && <Badge>git</Badge>}
            {e.has_scan && <Badge>scanned</Badge>}
          </span>
        </button>
      ))}
    </div>
  );
}
