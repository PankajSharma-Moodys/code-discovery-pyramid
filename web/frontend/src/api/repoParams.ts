import { useShallow } from "zustand/react/shallow";
import { useRepoStore } from "../store/repoStore.ts";

/** The `repo`/`state_dir` every query-hook below sends, read reactively so
 * picking a new repo in `RepoPicker` re-renders every hook that calls this
 * (new `queryKey` -> refetch) instead of leaving them on a stale closure.
 *
 * Must be called directly in the body of the hook that uses it (same rule
 * as any other hook) -- capture the returned object in a local, then use
 * that local both in `queryKey` and inside `queryFn`/`mutationFn`/effect
 * closures. Calling this a second time *inside* one of those closures would
 * call a hook outside of render. */
export function useRepoParams(): { repo: string; state_dir: string | undefined } {
  return useRepoStore(useShallow((s) => ({ repo: s.repo, state_dir: s.stateDir })));
}
