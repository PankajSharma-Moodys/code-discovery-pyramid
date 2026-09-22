import { createCdpClient } from "@cdp/web-client";

/**
 * Relative base URL: `vite.config.ts` proxies `/api` to the FastAPI dev
 * server, so the browser only ever talks to its own origin -- no CORS
 * handling needed client-side. No mutation token here: `POST /api/run`/
 * `/api/refresh` (token-gated, `web/api/auth.py`) are out of scope for
 * Phase 1's read-only Atlas.
 */
export const cdp = createCdpClient({ baseUrl: "" });

/** Fixed for this pass -- no repo picker yet, single-repo demo (this
 * repo's own `.cdp/index.db`). Every hook below threads these through so
 * adding a picker later is a matter of lifting this into view state, not
 * touching each call site. */
export const DEFAULT_REPO_PARAMS = { repo: ".", state_dir: undefined as string | undefined };
