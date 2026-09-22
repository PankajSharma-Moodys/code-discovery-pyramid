import { createCdpClient } from "@cdp/web-client";

/**
 * `../api/client.ts`'s `cdp` is built once with no token (reads never need
 * one). Mutations need the token attached, and it can change at runtime
 * (`TokenGate` writes it after the page has already loaded), so this builds
 * a fresh client per call rather than baking the token in at module-load
 * time. `createCdpClient`'s `mutationToken` wires an `openapi-fetch`
 * middleware that sets `X-CDP-Web-Token` (`web/client/index.ts`).
 */
export function mutationClient(token: string | null) {
  return createCdpClient({ baseUrl: "", mutationToken: token ?? undefined });
}
