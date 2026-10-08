import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { cdp } from "./client.ts";
import { useRepoParams } from "./repoParams.ts";
import type { FlowPayload } from "../flow/flowModel.ts";

/** `/api/flow` for the Flow tab; `include` adds "calls"/"config" edges. */
export function useFlow(include: string[]) {
  const repoParams = useRepoParams();
  return useQuery({
    queryKey: ["flow", include, repoParams],
    placeholderData: keepPreviousData,
    queryFn: async ({ signal }) => {
      const { data, error } = await cdp.GET("/api/flow", {
        params: { query: { include: include.length ? include : undefined, ...repoParams } },
        signal,
      });
      if (error) throw error;
      return data as FlowPayload;
    },
  });
}
