const STORAGE_PREFIX = "cdp-web-atlas-positions:";

/** Same in-memory fallback as `api/authToken.ts`/`api/repoSelection.ts` --
 * the vitest (node) test environment has no `sessionStorage` global.
 * `sessionStorage`, not `localStorage`: cached positions are a per-visit
 * convenience (instant re-layout on revisiting a scope this session), not a
 * workspace preference worth surviving a reload into a possibly-stale
 * snapshot. */
const memoryFallback = new Map<string, string>();
const storage: Pick<Storage, "getItem" | "setItem"> =
  typeof sessionStorage === "undefined"
    ? {
        getItem: (key) => memoryFallback.get(key) ?? null,
        setItem: (key, value) => void memoryFallback.set(key, value),
      }
    : sessionStorage;

export interface CachedPosition {
  x: number;
  y: number;
  /** Excluded from FA2 movement on rebuild (`graphology-layout-forceatlas2`'s
   * `fixed` node attribute) -- unpinned cached positions are still applied as
   * a seed but remain free to move once the next layout pass runs. */
  pinned: boolean;
}

/** `WEB_REDESIGN_RESEARCH.md` §3.3: revisiting a scope should be instant, not
 * a fresh FA2 run every time. Keyed by exactly what changes the layout: a
 * different repo/snapshot, level, or scope has no reason to reuse another
 * one's coordinates. `repoKey` is `repo:state_dir` (`useRepoParams`) rather
 * than a snapshot id -- `GraphResponse` doesn't carry one to the client, and
 * a repo/state_dir pair is a good-enough proxy for "same pinned snapshot"
 * within one browser session (`sessionStorage` already bounds the blast
 * radius of that assumption going stale). */
function keyFor(repoKey: string, level: string, scope: string | null): string {
  return `${STORAGE_PREFIX}${repoKey}:${level}:${scope ?? "-"}`;
}

export function getCachedPositions(
  repoKey: string,
  level: string,
  scope: string | null,
): Record<string, CachedPosition> {
  const raw = storage.getItem(keyFor(repoKey, level, scope));
  if (!raw) return {};
  try {
    const parsed = JSON.parse(raw) as Record<string, CachedPosition>;
    return typeof parsed === "object" && parsed !== null ? parsed : {};
  } catch {
    return {};
  }
}

export function setCachedPositions(
  repoKey: string,
  level: string,
  scope: string | null,
  positions: Record<string, CachedPosition>,
): void {
  storage.setItem(keyFor(repoKey, level, scope), JSON.stringify(positions));
}
