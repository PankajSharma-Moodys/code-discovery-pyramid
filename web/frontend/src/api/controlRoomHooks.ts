import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { cdp } from "./client.ts";
import { useRepoParams } from "./repoParams.ts";
import { mutationClient } from "./mutationClient.ts";
import { useControlRoomStore, serializeTarget } from "../store/controlRoomStore.ts";

/** SSE fallback/complement per `WEB_RESEARCH.md` §9: a dropped connection or
 * sleeping tab must never be the only source of truth, so this also polls --
 * `useRunEvents` below is additive on top of it, not a replacement. */
const STATUS_POLL_MS = 4000;

export function useStatus() {
  const repoParams = useRepoParams();
  return useQuery({
    queryKey: ["status", repoParams],
    queryFn: async () => {
      const { data, error } = await cdp.GET("/api/status", { params: { query: repoParams } });
      if (error) throw error;
      return data;
    },
    refetchInterval: STATUS_POLL_MS,
  });
}

/** `repo`/`state_dir` here decide which registry entry `get_repos` guarantees
 * is index 0 (`app.py:get_repos`'s docstring), not just which one it lists --
 * so this has to track the picker's current selection, not always this
 * app's own cwd, or `RepoHealthStrip`/`RepoPicker` would show the wrong repo
 * as "current" the moment you switch away from it. */
export function useRepos() {
  const repoParams = useRepoParams();
  return useQuery({
    queryKey: ["repos", repoParams],
    queryFn: async () => {
      const { data, error } = await cdp.GET("/api/repos", { params: { query: repoParams } });
      if (error) throw error;
      return data;
    },
  });
}

/** `403` is distinguished from any other failure so callers can steer the
 * user to `TokenGate` instead of a generic error toast. */
export class MutationAuthError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "MutationAuthError";
  }
}

function raiseAuthOr<T>(result: { data?: T; error?: unknown; response: Response }): T {
  const { data, error, response } = result;
  if (error) {
    if (response.status === 403) throw new MutationAuthError("bad or missing X-CDP-Web-Token");
    throw error;
  }
  return data as T;
}

export function useRunMutation() {
  const queryClient = useQueryClient();
  const authToken = useControlRoomStore((s) => s.authToken);
  const repoParams = useRepoParams();

  return useMutation({
    mutationFn: async (vars: { target: import("../store/controlRoomStore.ts").DispatchTarget; resume: boolean }) => {
      const client = mutationClient(authToken);
      const result = await client.POST("/api/run", {
        params: { query: { ...repoParams, target: serializeTarget(vars.target), resume: vars.resume } },
      });
      return raiseAuthOr(result);
    },
    onSettled: () => queryClient.invalidateQueries({ queryKey: ["status"] }),
  });
}

export function useRefreshMutation() {
  const queryClient = useQueryClient();
  const authToken = useControlRoomStore((s) => s.authToken);
  const repoParams = useRepoParams();

  return useMutation({
    mutationFn: async (vars: { mode: string }) => {
      const client = mutationClient(authToken);
      const result = await client.POST("/api/refresh", {
        params: { query: { ...repoParams, mode: vars.mode } },
      });
      return raiseAuthOr(result);
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["status"] });
      queryClient.invalidateQueries({ queryKey: ["repos"] });
    },
  });
}

export interface RunTaskEvent {
  node: string;
  state: string;
  attempts: number;
  last_error: string | null;
}

export interface RunWaveEvent {
  done: number;
  total: number;
}

interface RunEventsState {
  tasks: Map<string, RunTaskEvent>;
  wave: RunWaveEvent | null;
  complete: boolean;
}

const EMPTY_EVENTS: RunEventsState = { tasks: new Map(), wave: null, complete: false };

/** Live overlay on top of `useStatus`'s poll -- `EventSource` against
 * `/api/events` (unauthenticated GET, `web/api/app.py`'s `get_events`).
 * Deliberately does not replace the poll: per `WEB_RESEARCH.md` §9 ("SSE
 * drops, tab sleeps, user closes laptop"), the lease table (via
 * `useStatus`) stays the source of truth on reconnect, this is only the
 * live-update path while a tab is open and connected. */
export function useRunEvents(enabled: boolean): RunEventsState {
  const [state, setState] = useState<RunEventsState>(EMPTY_EVENTS);
  const sourceRef = useRef<EventSource | null>(null);
  const { repo, state_dir } = useRepoParams();

  useEffect(() => {
    if (!enabled) {
      setState(EMPTY_EVENTS);
      return;
    }
    const params = new URLSearchParams({ repo });
    if (state_dir) params.set("state_dir", state_dir);
    const source = new EventSource(`/api/events?${params.toString()}`);
    sourceRef.current = source;
    setState(EMPTY_EVENTS);

    source.addEventListener("task", (event) => {
      const payload = JSON.parse((event as MessageEvent).data) as RunTaskEvent;
      setState((prev) => {
        const tasks = new Map(prev.tasks);
        tasks.set(payload.node, payload);
        return { ...prev, tasks };
      });
    });
    source.addEventListener("wave", (event) => {
      const payload = JSON.parse((event as MessageEvent).data) as RunWaveEvent;
      setState((prev) => ({ ...prev, wave: payload }));
    });
    source.addEventListener("complete", () => {
      setState((prev) => ({ ...prev, complete: true }));
      source.close();
    });
    source.onerror = () => {
      source.close();
    };

    return () => {
      source.close();
      sourceRef.current = null;
    };
    // Reconnects on a repo switch, not just on `enabled` -- an open
    // `EventSource` keeps streaming the *old* repo's task events otherwise.
  }, [enabled, repo, state_dir]);

  return state;
}
