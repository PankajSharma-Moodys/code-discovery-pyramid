import { keepPreviousData, useQueries, useQuery } from "@tanstack/react-query";
import { useMemo } from "react";
import { cdp } from "./client.ts";
import { useRepoParams } from "./repoParams.ts";
import type { Altitude } from "./nodeId.ts";
import { toNodeId } from "./nodeId.ts";
import type { DiffShape } from "./diffTypes.ts";
import type { LinkEntry, UnmatchedEntry } from "./linkTypes.ts";
import type { TraceResult } from "./traceTypes.ts";
import type { AskQuery } from "../store/askBarStore.ts";
import { type ConfidenceBucket } from "../theme/confidence.ts";

/** Bounds a request that would otherwise hang forever if the backend never
 * responds (no server-side timeout on `/api/graph`/`/api/node`, per
 * `RESEARCH_PAIN_POINTS.md`) -- composed with react-query's own abort signal
 * so unmount/re-key cancellation still works. */
const REQUEST_TIMEOUT_MS = 15_000;

function withTimeout(signal?: AbortSignal): AbortSignal {
  const timeout = AbortSignal.timeout(REQUEST_TIMEOUT_MS);
  return signal ? AbortSignal.any([signal, timeout]) : timeout;
}

type RepoParams = ReturnType<typeof useRepoParams>;

/** Shared fetch body behind {@link useGraph} and {@link useExpandedGraphs} --
 * factored out so both go through the same timeout wrapper and `too_large`
 * passthrough instead of drifting apart. */
async function fetchGraph(
  level: Altitude,
  scope: string | null,
  hideRoles: string[],
  focus: string | null,
  repoParams: RepoParams,
  signal?: AbortSignal,
) {
  if (import.meta.env.DEV) performance.mark("atlas:fetch-start");
  const { data, error } = await cdp.GET("/api/graph", {
    params: {
      query: {
        level,
        scope: scope ?? undefined,
        hide_roles: hideRoles.length ? hideRoles : undefined,
        focus: focus ?? undefined,
        ...repoParams,
      },
    },
    signal: withTimeout(signal),
  });
  if (import.meta.env.DEV) {
    performance.mark("atlas:fetch-end");
    performance.measure("atlas:fetch", "atlas:fetch-start", "atlas:fetch-end");
  }
  if (error) throw error;
  return data;
}

/** `hideRoles`: the server-side escape hatch (`hide_roles=`) for graphs too
 * big to filter client-side -- `AtlasCanvas` only passes it once its
 * already-fetched node count crosses `ROLE_HIDE_CLIENT_THRESHOLD`, and
 * `enabled: false` (via `options.enabled`) until then so this stays a no-op
 * second query rather than firing on every mount. */
export function useGraph(
  level: Altitude,
  scope: string | null,
  options?: { hideRoles?: string[]; enabled?: boolean; focus?: string | null },
) {
  const repoParams = useRepoParams();
  const hideRoles = options?.hideRoles ?? [];
  const focus = options?.focus ?? null;
  return useQuery({
    queryKey: ["graph", level, scope, hideRoles, focus, repoParams],
    enabled: options?.enabled ?? true,
    retry: 2,
    // `WEB_REDESIGN_RESEARCH.md` §5 item 5: the old graph stays on screen
    // (still interactive) while the next altitude/scope's fetch is in
    // flight, instead of `AtlasCanvas` briefly rendering a blank "loading
    // graph…" canvas between every drill-down click.
    placeholderData: keepPreviousData,
    queryFn: ({ signal }) => fetchGraph(level, scope, hideRoles, focus, repoParams, signal),
  });
}

/** One scoped `/api/graph` query per currently-expanded container
 * (`AtlasCanvas.tsx`'s nested/multi expand-in-place) -- `useQueries` supports
 * a *dynamic-length* query array in one hook call, which is what lets the
 * number of open expansions change across renders without breaking the
 * rules of hooks. Same `queryKey` shape as {@link useGraph} (`hideRoles`/
 * `focus` always empty here -- an expansion never needs either), so a
 * container that gets expanded, collapsed, and expanded again reuses the
 * cache instead of refetching. */
export function useExpandedGraphs(entries: { id: string; childRung: Altitude }[]) {
  const repoParams = useRepoParams();
  const results = useQueries({
    queries: entries.map((e) => ({
      queryKey: ["graph", e.childRung, e.id, [], null, repoParams],
      retry: 2,
      placeholderData: keepPreviousData,
      queryFn: ({ signal }: { signal?: AbortSignal }) =>
        fetchGraph(e.childRung, e.id, [], null, repoParams, signal),
    })),
  });
  return useMemo(() => new Map(entries.map((e, i) => [e.id, results[i]])), [entries, results]);
}

export function useNode(nodeId: string | null) {
  const repoParams = useRepoParams();
  return useQuery({
    queryKey: ["node", nodeId, repoParams],
    enabled: nodeId !== null,
    retry: 2,
    queryFn: async ({ signal }) => {
      const { data, error } = await cdp.GET("/api/node/{node_id}", {
        params: { path: { node_id: nodeId! }, query: repoParams },
        signal: withTimeout(signal),
      });
      if (error) throw error;
      return data;
    },
  });
}

/** `level`/`rawId` version of {@link useNode} -- callers with a raw
 * `/api/graph` id (never namespace-prefixed, see `nodeId.ts`) don't need to
 * remember the mapping at the call site. */
export function useNodeAt(level: Altitude, rawId: string | null, apiNodeId?: string | null) {
  // Prefer the id the server already resolved (`GraphNodeResponse.node_id`) --
  // since ATLAS_REDESIGN.md P0, a raw L2 id's namespace depends on
  // `xref.symbols` and cannot be derived here. `toNodeId` stays as the
  // fallback for altitudes whose ids are derivable (L1 file paths) and for
  // callers that never had a server-resolved id to pass.
  const resolved =
    apiNodeId !== undefined ? apiNodeId : rawId === null ? null : toNodeId(level, rawId);
  return useNode(resolved);
}

/**
 * Confidence lens data: one bulk `/api/confidence` call per altitude.
 *
 * This used to issue one `/api/node/:id` per visible node, with a comment
 * noting that was fine at "tens of nodes". `ATLAS_REDESIGN.md` P0 made L2 the
 * 353-node typed dataflow graph, which turned every lens toggle into 353
 * requests that each re-read and re-classified the same three artifacts. The
 * server now does that classification once (`_build_confidence`).
 *
 * A node absent from `buckets` has no claim about it and is `unreviewed` --
 * the endpoint deliberately omits those rather than emitting a row per node.
 */
export function useNodesConfidence(
  level: Altitude,
  scope: string | null,
  enabled: boolean,
): Map<string, ConfidenceBucket> {
  const repoParams = useRepoParams();
  const { data } = useQuery({
    queryKey: ["confidence", level, scope, repoParams],
    enabled,
    queryFn: async () => {
      const { data, error } = await cdp.GET("/api/confidence", {
        params: { query: { level, scope: scope ?? undefined, ...repoParams } },
      });
      if (error) throw error;
      return data;
    },
  });

  return useMemo(() => {
    const byId = new Map<string, ConfidenceBucket>();
    for (const [rawId, bucket] of Object.entries(data?.buckets ?? {})) {
      byId.set(rawId, bucket as ConfidenceBucket);
    }
    return byId;
  }, [data]);
}

export function useSources() {
  const repoParams = useRepoParams();
  return useQuery({
    queryKey: ["sources", repoParams],
    queryFn: async () => {
      const { data, error } = await cdp.GET("/api/sources", {
        params: { query: repoParams },
      });
      if (error) throw error;
      return data;
    },
  });
}

export function useTrace(entry: string | null) {
  const repoParams = useRepoParams();
  return useQuery({
    queryKey: ["trace", entry, repoParams],
    enabled: entry !== null,
    queryFn: async () => {
      const { data, error } = await cdp.GET("/api/trace", {
        params: { query: { entry: entry!, ...repoParams } },
      });
      if (error) throw error;
      return data as unknown as TraceResult;
    },
  });
}

/** The ask-bar's dispatch: a thin pass-through of `/api/query`, same
 * no-fixed-shape posture as `useTrace` above (`web/api/app.py:get_query`
 * deliberately has no `response_model` -- kind picks the shape). */
export function useAskQuery(query: AskQuery | null) {
  const repoParams = useRepoParams();
  return useQuery({
    queryKey: ["ask-query", query, repoParams],
    enabled: query !== null,
    queryFn: async () => {
      const { data, error } = await cdp.GET("/api/query", {
        params: {
          query: {
            kind: query!.kind,
            term: query!.term,
            from: query!.frm,
            to: query!.to,
            ...repoParams,
          },
        },
      });
      if (error) throw error;
      return data as Record<string, unknown>;
    },
  });
}

/** `WEB_REDESIGN_RESEARCH.md` §4's server-side search-to-focus: a thin,
 * ranked symbol+file typeahead over `GET /api/search`, replacing the
 * 6.8MB-on-`unified-store` full-L0 fetch `useSymbolTypeahead` below does for
 * the same job. `enabled` also gates on `q.length >= 2` -- the endpoint's own
 * `min_length=2` -- so a one-character query never fires a request that would
 * just 422. */
export function useSearch(q: string, enabled = true) {
  const repoParams = useRepoParams();
  return useQuery({
    queryKey: ["search", q, repoParams],
    enabled: enabled && q.length >= 2,
    queryFn: async () => {
      const { data, error } = await cdp.GET("/api/search", {
        params: { query: { q, ...repoParams } },
      });
      if (error) throw error;
      return data.results;
    },
  });
}

/** Time scrubber's timeline -- ordered (oldest-first) real scanned commits
 * from `snapshot_meta`, via `GET /api/snapshots`. */
export function useSnapshots() {
  const repoParams = useRepoParams();
  return useQuery({
    queryKey: ["snapshots", repoParams],
    queryFn: async () => {
      const { data, error } = await cdp.GET("/api/snapshots", {
        params: { query: repoParams },
      });
      if (error) throw error;
      return data;
    },
  });
}

/** Structural delta between two scanned commits (`cdp.diffs.diff_snapshots`,
 * passed through as-is) -- the time scrubber's per-scrub payload. */
export function useDiff(oldSha: string | null, newSha: string | null) {
  const repoParams = useRepoParams();
  return useQuery({
    queryKey: ["diff", oldSha, newSha, repoParams],
    enabled: oldSha !== null && newSha !== null && oldSha !== newSha,
    queryFn: async () => {
      const { data, error } = await cdp.GET("/api/diff", {
        params: { query: { old: oldSha!, new: newSha!, ...repoParams } },
      });
      if (error) throw error;
      return data ? { ...data, diff: data.diff as unknown as DiffShape } : data;
    },
  });
}

/** All persisted intra-repo link edges (`GET /api/links`), unfiltered --
 * the module-link constellation view's data source. */
export function useLinks() {
  const repoParams = useRepoParams();
  return useQuery({
    queryKey: ["links", repoParams],
    queryFn: async () => {
      const { data, error } = await cdp.GET("/api/links", {
        params: { query: repoParams },
      });
      if (error) throw error;
      if (!data) return data;
      return {
        links: data.links as unknown as LinkEntry[],
        unmatched: data.unmatched as unknown as UnmatchedEntry[],
      };
    },
  });
}

export function useSourceFile(file: string | null, line: number | null) {
  const repoParams = useRepoParams();
  return useQuery({
    queryKey: ["source", file, line, repoParams],
    enabled: file !== null,
    queryFn: async () => {
      const { data, error } = await cdp.GET("/api/source", {
        params: { query: { file: file!, line: line ?? undefined, repo: repoParams.repo } },
      });
      if (error) throw error;
      return data;
    },
  });
}
