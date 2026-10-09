import { useMutation, useQuery } from "@tanstack/react-query";
import { cdp } from "./client.ts";
import { mutationClient } from "./mutationClient.ts";
import { raiseAuthOr } from "./controlRoomHooks.ts";
import { useControlRoomStore } from "../store/controlRoomStore.ts";

const JOB_POLL_MS = 1500;

/** Read-only directory listing; `path` undefined lets the server pick home. */
export function useFsList(path: string | undefined) {
  return useQuery({
    queryKey: ["fs-list", path ?? null],
    queryFn: async () => {
      const { data, error, response } = await cdp.GET("/api/fs/list", { params: { query: path ? { path } : {} } });
      if (error) throw new Error(response.status === 403 ? "folder is not readable" : "folder not found");
      return data;
    },
    retry: false,
  });
}

/** `POST /api/scan` always writes `<folder>/.cdp` server-side, so the caller
 * derives the state dir from the folder it passed in. */
export function useScanMutation() {
  const authToken = useControlRoomStore((s) => s.authToken);
  return useMutation({
    mutationFn: async (folder: string) => {
      const client = mutationClient(authToken);
      return raiseAuthOr(await client.POST("/api/scan", { params: { query: { repo: folder } } }));
    },
  });
}

/** Polls until the job stops running; `log_tail` is only set after that. */
export function useJob(jobId: string | null) {
  return useQuery({
    queryKey: ["job", jobId],
    enabled: jobId != null,
    queryFn: async () => {
      const { data, error } = await cdp.GET("/api/job/{job_id}", { params: { path: { job_id: jobId as string } } });
      if (error) throw error;
      return data;
    },
    refetchInterval: (query) => (query.state.data?.running === false ? false : JOB_POLL_MS),
  });
}
