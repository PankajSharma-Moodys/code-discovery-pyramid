const STORAGE_KEY = "cdp-web-token";

/** In-memory stand-in for the vitest (node) test environment, which has no
 * `localStorage` global -- there's no jsdom dependency in this project to
 * provide one. The app itself always runs in a browser, where the real
 * `localStorage` is used instead. */
const memoryFallback = new Map<string, string>();
const storage: Pick<Storage, "getItem" | "setItem" | "removeItem"> =
  typeof localStorage === "undefined"
    ? {
        getItem: (key) => memoryFallback.get(key) ?? null,
        setItem: (key, value) => void memoryFallback.set(key, value),
        removeItem: (key) => void memoryFallback.delete(key),
      }
    : localStorage;

/** The token `web/api/auth.py` prints to the `uvicorn` process's stdout at
 * startup -- there is no cookie/session, so the browser has nowhere else to
 * learn it. Paste-once, persisted locally; never sent to any other origin
 * since every request is same-origin via `vite.config.ts`'s proxy. */
export function getAuthToken(): string | null {
  return storage.getItem(STORAGE_KEY);
}

export function setAuthToken(token: string | null): void {
  if (token) storage.setItem(STORAGE_KEY, token);
  else storage.removeItem(STORAGE_KEY);
}
