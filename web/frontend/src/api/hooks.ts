import { useQueries, useQuery } from "@tanstack/react-query";
import { cdp, DEFAULT_REPO_PARAMS } from "./client.ts";
import type { Altitude } from "./nodeId.ts";
import { toNodeId } from "./nodeId.ts";
import type { DiffShape } from "./diffTypes.ts";
import type { LinkEntry, UnmatchedEntry } from "./linkTypes.ts";
import type { TraceResult } from "./traceTypes.ts";
import type { AskQuery } from "../store/askBarStore.ts";
import { dominantConfidence, type ConfidenceBucket } from "../theme/confidence.ts";

const repoParams = () => ({
  repo: DEFAULT_REPO_PARAMS.repo,
  state_dir: DEFAULT_REPO_PARAMS.state_dir,
});

export function useGraph(level: Altitude, scope: string | null) {
  return useQuery({
    queryKey: ["graph", level, scope, repoParams()],
    queryFn: async () => {
      const { data, error } = await cdp.GET("/api/graph", {
        params: { query: { level, scope: scope ?? undefined, ...repoParams() } },
      });
      if (error) throw error;
      return data;
    },
  });
}

export function useNode(nodeId: string | null) {
  return useQuery({
    queryKey: ["node", nodeId, repoParams()],
    enabled: nodeId !== null,
    queryFn: async () => {
      const { data, error } = await cdp.GET("/api/node/{node_id}", {
        params: { path: { node_id: nodeId! }, query: repoParams() },
      });
      if (error) throw error;
      return data;
    },
  });
}

/** `level`/`rawId` version of {@link useNode} -- callers with a raw
 * `/api/graph` id (never namespace-prefixed, see `nodeId.ts`) don't need to
 * remember the mapping at the call site. */
export function useNodeAt(level: Altitude, rawId: string | null) {
  return useNode(rawId === null ? null : toNodeId(level, rawId));
}

/** Confidence lens data: one `/api/node/:id` per currently-loaded node,
 * rolled up to a single `ConfidenceBucket` per node via
 * `dominantConfidence`. Only meant to be mounted while the Confidence lens
 * is active and scoped to one altitude's node set (tens of nodes at this
 * repo's scale, not the whole graph) -- see `PLAN.md`'s lens design. */
export function useNodesConfidence(level: Altitude, rawIds: string[]): Map<string, ConfidenceBucket> {
  const results = useQueries({
    queries: rawIds.map((rawId) => ({
      queryKey: ["node", toNodeId(level, rawId), repoParams()],
      queryFn: async () => {
        const { data, error } = await cdp.GET("/api/node/{node_id}", {
          params: { path: { node_id: toNodeId(level, rawId) }, query: repoParams() },
        });
        if (error) throw error;
        return data;
      },
    })),
  });

  const byId = new Map<string, ConfidenceBucket>();
  rawIds.forEach((rawId, i) => {
    const node = results[i]?.data;
    if (!node) return;
    byId.set(rawId, dominantConfidence(node.claims.map((c) => c.confidence)));
  });
  return byId;
}

export function useSources() {
  return useQuery({
    queryKey: ["sources", repoParams()],
    queryFn: async () => {
      const { data, error } = await cdp.GET("/api/sources", {
        params: { query: repoParams() },
      });
      if (error) throw error;
      return data;
    },
  });
}

export function useTrace(entry: string | null) {
  return useQuery({
    queryKey: ["trace", entry, repoParams()],
    enabled: entry !== null,
    queryFn: async () => {
      const { data, error } = await cdp.GET("/api/trace", {
        params: { query: { entry: entry!, ...repoParams() } },
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
  return useQuery({
    queryKey: ["ask-query", query, repoParams()],
    enabled: query !== null,
    queryFn: async () => {
      const { data, error } = await cdp.GET("/api/query", {
        params: {
          query: {
            kind: query!.kind,
            term: query!.term,
            from: query!.frm,
            to: query!.to,
            ...repoParams(),
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
  return useQuery({
    queryKey: ["symbol-typeahead", repoParams()],
    staleTime: Infinity,
    queryFn: async () => {
      const { data, error } = await cdp.GET("/api/graph", {
        params: { query: { level: "L0", ...repoParams() } },
      });
      if (error) throw error;
      return (data?.nodes ?? []).map((n) => n.id);
    },
  });
}

/** Time scrubber's timeline -- ordered (oldest-first) real scanned commits
 * from `snapshot_meta`, via `GET /api/snapshots`. */
export function useSnapshots() {
  return useQuery({
    queryKey: ["snapshots", repoParams()],
    queryFn: async () => {
      const { data, error } = await cdp.GET("/api/snapshots", {
        params: { query: repoParams() },
      });
      if (error) throw error;
      return data;
    },
  });
}

/** Structural delta between two scanned commits (`cdp.diffs.diff_snapshots`,
 * passed through as-is) -- the time scrubber's per-scrub payload. */
export function useDiff(oldSha: string | null, newSha: string | null) {
  return useQuery({
    queryKey: ["diff", oldSha, newSha, repoParams()],
    enabled: oldSha !== null && newSha !== null && oldSha !== newSha,
    queryFn: async () => {
      const { data, error } = await cdp.GET("/api/diff", {
        params: { query: { old: oldSha!, new: newSha!, ...repoParams() } },
      });
      if (error) throw error;
      return data ? { ...data, diff: data.diff as unknown as DiffShape } : data;
    },
  });
}

/** All persisted intra-repo link edges (`GET /api/links`), unfiltered --
 * the module-link constellation view's data source. */
export function useLinks() {
  return useQuery({
    queryKey: ["links", repoParams()],
    queryFn: async () => {
      const { data, error } = await cdp.GET("/api/links", {
        params: { query: repoParams() },
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
  return useQuery({
    queryKey: ["source", file, line, repoParams()],
    enabled: file !== null,
    queryFn: async () => {
      const { data, error } = await cdp.GET("/api/source", {
        params: { query: { file: file!, line: line ?? undefined, repo: repoParams().repo } },
      });
      if (error) throw error;
      return data;
    },
  });
}
