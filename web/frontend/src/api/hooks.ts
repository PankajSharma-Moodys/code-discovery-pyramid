import { useQuery } from "@tanstack/react-query";
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

/** `hideRoles`: the server-side escape hatch (`hide_roles=`) for graphs too
 * big to filter client-side -- `AtlasCanvas` only passes it once its
 * already-fetched node count crosses `ROLE_HIDE_CLIENT_THRESHOLD`, and
 * `enabled: false` (via `options.enabled`) until then so this stays a no-op
 * second query rather than firing on every mount. */
export function useGraph(
  level: Altitude,
  scope: string | null,
  options?: { hideRoles?: string[]; enabled?: boolean },
) {
  const repoParams = useRepoParams();
  const hideRoles = options?.hideRoles ?? [];
  return useQuery({
    queryKey: ["graph", level, scope, hideRoles, repoParams],
    enabled: options?.enabled ?? true,
    queryFn: async () => {
      const { data, error } = await cdp.GET("/api/graph", {
        params: {
          query: {
            level,
            scope: scope ?? undefined,
            hide_roles: hideRoles.length ? hideRoles : undefined,
            ...repoParams,
          },
        },
      });
      if (error) throw error;
      return data;
    },
  });
}

export function useNode(nodeId: string | null) {
  const repoParams = useRepoParams();
  return useQuery({
    queryKey: ["node", nodeId, repoParams],
    enabled: nodeId !== null,
    queryFn: async () => {
      const { data, error } = await cdp.GET("/api/node/{node_id}", {
        params: { path: { node_id: nodeId! }, query: repoParams },
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

/** All symbol FQNs (`xref.symbols`, via the L0 altitude graph) for the
 * ask-bar's typeahead. Fetched once and cached indefinitely -- it's a
 * snapshot-scoped list (1,967 entries at this repo's scale), not something
 * that changes within a session (`WEB_RESEARCH.md` §7.1 pins `snapshot_id`
 * per session already). Bypasses `useGraph`/`Altitude` deliberately: L0 has
 * no canvas altitude in this pass (`store/atlasStore.ts`'s `ALTITUDES` is
 * L3-L1 only), this just needs the name list. */
export function useSymbolTypeahead() {
  const repoParams = useRepoParams();
  return useQuery({
    queryKey: ["symbol-typeahead", repoParams],
    staleTime: Infinity,
    queryFn: async () => {
      const { data, error } = await cdp.GET("/api/graph", {
        params: { query: { level: "L0", ...repoParams } },
      });
      if (error) throw error;
      return (data?.nodes ?? []).map((n) => n.id);
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
