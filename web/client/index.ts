/**
 * Typed client for `web/api/app.py`. Wraps `openapi-fetch` (not hand-rolled
 * fetch calls) so every request/response shape is checked against
 * `schema.ts` -- regenerate that file via `npm run generate` whenever a
 * route or Pydantic model in `web/api/` changes; do not hand-edit it.
 */
import createFetchClient, { type Middleware } from "openapi-fetch";
import type { paths } from "./schema.ts";

export type { paths } from "./schema.ts";

export interface CdpClientOptions {
  /** e.g. "http://127.0.0.1:8000" */
  baseUrl: string;
  /**
   * Value of the `X-CDP-Web-Token` header the server prints to stdout at
   * startup (`web/api/auth.py`). Only `POST /api/run` and `POST
   * /api/refresh` check it -- attaching it to every request is harmless,
   * since GET handlers never read the header.
   */
  mutationToken?: string;
}

export function createCdpClient({ baseUrl, mutationToken }: CdpClientOptions) {
  const client = createFetchClient<paths>({ baseUrl });

  if (mutationToken) {
    const authMiddleware: Middleware = {
      onRequest({ request }) {
        request.headers.set("X-CDP-Web-Token", mutationToken);
        return request;
      },
    };
    client.use(authMiddleware);
  }

  return client;
}
