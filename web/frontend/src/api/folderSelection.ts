/** Registry id for a freshly scanned folder: the `/api/repos` row whose
 * `repo_path` is that folder if the registry already lists it, else the path
 * itself (the picker label falls back to it until the repos query refetches). */
export function repoIdForPath(path: string, repos: ReadonlyArray<{ repo_id: string; repo_path?: string | null }>): string {
  return repos.find((r) => r.repo_path === path)?.repo_id ?? path;
}
