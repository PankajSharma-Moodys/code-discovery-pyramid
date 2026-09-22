import { create } from "zustand";
import {
  DEFAULT_REPO_SELECTION,
  getRepoSelection,
  setRepoSelection as persistRepoSelection,
  type RepoSelection,
} from "../api/repoSelection.ts";
import { useAtlasStore } from "./atlasStore.ts";

interface RepoState extends RepoSelection {
  /** `repo`/`stateDir` together, not just `stateDir`: `state_dir` alone
   * resolves the index -- an explicit one always wins in
   * `resolve_state_dir` -- but endpoints that read the *working tree*
   * directly (`/api/source`) or derive a registry id from the *path*
   * (`/api/snapshots`) both key off `repo`, independently of `state_dir`.
   * Switching only one would leave those endpoints pointed at the old repo
   * while the graph/query endpoints moved to the new one. */
  setRepo: (selection: RepoSelection) => void;
}

export const useRepoStore = create<RepoState>((set) => ({
  ...getRepoSelection(),

  setRepo: (selection) => {
    persistRepoSelection(selection);
    set(selection);
    // A selected/hovered node id or scope from the old repo's graph means
    // nothing in the new one -- `jumpTo` (re-jumping to the current
    // altitude) is the existing "clear scope + focus" reset, reused here
    // rather than adding a second copy of `CLEAR_FOCUS` in this store.
    useAtlasStore.getState().jumpTo(useAtlasStore.getState().altitude);
  },
}));

export { DEFAULT_REPO_SELECTION };
