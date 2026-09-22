const STORAGE_KEY = "cdp-web-repo-selection";

/** Same in-memory fallback as `authToken.ts` -- the vitest (node) test
 * environment has no `localStorage` global. */
const memoryFallback = new Map<string, string>();
const storage: Pick<Storage, "getItem" | "setItem" | "removeItem"> =
  typeof localStorage === "undefined"
    ? {
        getItem: (key) => memoryFallback.get(key) ?? null,
        setItem: (key, value) => void memoryFallback.set(key, value),
        removeItem: (key) => void memoryFallback.delete(key),
      }
    : localStorage;

export interface RepoSelection {
  repo: string;
  stateDir: string | undefined;
  repoId: string | null;
}

/** The repo every hook queries by default before a picker selection is ever
 * made -- this repo's own working tree, resolved the same way the CLI falls
 * back when no `--state` is given (`web/api/store_reader.py:resolve_state_dir`). */
export const DEFAULT_REPO_SELECTION: RepoSelection = { repo: ".", stateDir: undefined, repoId: null };

/** Persisted across reloads (unlike `AtlasCanvas`'s session-only "Hide
 * tests" toggle): which repo you're looking at is a workspace-level
 * preference, not a per-visit one, and re-picking it on every reload would
 * be the actual annoyance here. */
export function getRepoSelection(): RepoSelection {
  const raw = storage.getItem(STORAGE_KEY);
  if (!raw) return DEFAULT_REPO_SELECTION;
  try {
    const parsed = JSON.parse(raw) as Partial<RepoSelection>;
    if (typeof parsed.repo !== "string") return DEFAULT_REPO_SELECTION;
    return {
      repo: parsed.repo,
      stateDir: typeof parsed.stateDir === "string" ? parsed.stateDir : undefined,
      repoId: typeof parsed.repoId === "string" ? parsed.repoId : null,
    };
  } catch {
    return DEFAULT_REPO_SELECTION;
  }
}

export function setRepoSelection(selection: RepoSelection): void {
  storage.setItem(STORAGE_KEY, JSON.stringify(selection));
}
