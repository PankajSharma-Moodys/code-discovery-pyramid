import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { cdp, DEFAULT_REPO_PARAMS } from "./client.ts";
import { mutationClient } from "./mutationClient.ts";
import { MutationAuthError } from "./controlRoomHooks.ts";
import { useControlRoomStore } from "../store/controlRoomStore.ts";

export { MutationAuthError };

function raiseAuthOr<T>(result: { data?: T; error?: unknown; response: Response }): T {
  const { data, error, response } = result;
  if (error) {
    if (response.status === 403) throw new MutationAuthError("bad or missing X-CDP-Web-Token");
    throw error;
  }
  return data as T;
}

export function useInstallPreview(target: string, framework: string) {
  return useQuery({
    queryKey: ["hookup-preview", target, framework],
    queryFn: async () => {
      const { data, error } = await cdp.GET("/api/hookup/preview", {
        params: { query: { target, framework } },
      });
      if (error) throw error;
      return data;
    },
    enabled: target.trim().length > 0,
    retry: false,
  });
}

export function useInstallMutation() {
  const queryClient = useQueryClient();
  const authToken = useControlRoomStore((s) => s.authToken);

  return useMutation({
    mutationFn: async (vars: { target: string; framework: string; hook: boolean }) => {
      const client = mutationClient(authToken);
      const result = await client.POST("/api/hookup/install", {
        params: { query: { target: vars.target, framework: vars.framework, hook: vars.hook } },
      });
      return raiseAuthOr(result);
    },
    onSettled: () => queryClient.invalidateQueries({ queryKey: ["hookup-preview"] }),
  });
}

export function useMcpTools() {
  return useQuery({
    queryKey: ["hookup-mcp-tools"],
    queryFn: async () => {
      const { data, error } = await cdp.GET("/api/hookup/mcp-tools");
      if (error) throw error;
      return data;
    },
  });
}

export function useLivenessMutation() {
  const authToken = useControlRoomStore((s) => s.authToken);

  return useMutation({
    mutationFn: async (vars: {
      target: string; runnerCmd: string; model: string; node?: string; timeout?: number;
    }) => {
      const client = mutationClient(authToken);
      const result = await client.POST("/api/hookup/liveness", {
        params: {
          query: {
            target: vars.target,
            state_dir: DEFAULT_REPO_PARAMS.state_dir,
            runner_cmd: vars.runnerCmd,
            model: vars.model,
            node: vars.node,
            timeout: vars.timeout ?? 300,
          },
        },
      });
      return raiseAuthOr(result);
    },
  });
}

/** Polls `GET /api/job/:id` every ~1.5s while `enabled` -- `cdp doctor` has
 * no task table to stream (unlike `run`/`refresh`'s `useStatus`), so this is
 * poll-only, no SSE overlay. */
export function useJobStatus(jobId: string | null, enabled: boolean) {
  return useQuery({
    queryKey: ["job-status", jobId],
    queryFn: async () => {
      const { data, error } = await cdp.GET("/api/job/{job_id}", {
        params: { path: { job_id: jobId as string } },
      });
      if (error) throw error;
      return data;
    },
    enabled: enabled && !!jobId,
    refetchInterval: (query) => (query.state.data?.running ? 1500 : false),
  });
}

export function useDoctorReport(target: string, enabled: boolean) {
  return useQuery({
    queryKey: ["doctor", target],
    queryFn: async () => {
      const { data, error } = await cdp.GET("/api/doctor", {
        params: { query: { repo: target, state_dir: DEFAULT_REPO_PARAMS.state_dir } },
      });
      if (error) throw error;
      return data;
    },
    enabled,
    retry: false,
  });
}

/** `GET /api/trajectory` -- cross-workspace `~/.cdp/trajectories.db`, not
 * scoped to `repo=`/`state_dir=` (see `web/api/app.py`'s `get_trajectory`).
 * `shape` re-queries server-side (the one real filter param); outcome/
 * elision-regret filtering happens client-side over `runs`. */
export function useTrajectoryRuns(shape: string | null, budget = 500) {
  return useQuery({
    queryKey: ["trajectory", shape, budget],
    queryFn: async () => {
      const { data, error } = await cdp.GET("/api/trajectory", {
        params: { query: { shape: shape ?? undefined, budget } },
      });
      if (error) throw error;
      return data;
    },
    retry: false,
  });
}
