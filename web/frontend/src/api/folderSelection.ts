/** Registry id for a freshly scanned folder: the `/api/repos` row whose
 * `repo_path` is that folder if the registry already lists it, else the path
 * itself (the picker label falls back to it until the repos query refetches). */
export function repoIdForPath(path: string, repos: ReadonlyArray<{ repo_id: string; repo_path?: string | null }>): string {
  return repos.find((r) => r.repo_path === path)?.repo_id ?? path;
}

/** The registry row the picker treats as active. A null `repoId` means the
 * user never picked, so the server's default store (listed first) is the
 * current one; a non-null id with no matching row (just-opened folder) stays
 * unmatched rather than mislabelling another repo. */
export function currentRepoRow<T extends { repo_id: string }>(repos: ReadonlyArray<T>, repoId: string | null): T | undefined {
  return repoId == null ? repos[0] : repos.find((r) => r.repo_id === repoId);
}
