import { createCdpClient } from "@cdp/web-client";

/**
 * Relative base URL: `vite.config.ts` proxies `/api` to the FastAPI dev
 * server, so the browser only ever talks to its own origin -- no CORS
 * handling needed client-side. No mutation token here: `POST /api/run`/
 * `/api/refresh` (token-gated, `web/api/auth.py`) are out of scope for
 * Phase 1's read-only Atlas.
 */
export const cdp = createCdpClient({ baseUrl: "" });

/** The active repo now lives in `store/repoStore.ts` (the picker) --
 * `useRepoParams` (`api/repoParams.ts`) is the reactive read every hook
 * uses instead of this. */
