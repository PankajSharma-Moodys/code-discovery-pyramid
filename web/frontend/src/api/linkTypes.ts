/**
 * `/api/links`' `links`/`unmatched` entries are `dict`-typed on the FastAPI
 * side (straight passthrough of `link.scan_links`'s own output, see
 * `web/api/models.py`'s `LinksResponse` docstring), so `schema.ts` types
 * them as `{[key: string]: unknown}`. This is the shape `scan_links`
 * (`cdp/link.py:137`) actually returns, kept here instead of loosening
 * types at each call site -- same pattern as `traceTypes.ts`/`diffTypes.ts`.
 */
export interface LinkSide {
  repo: string;
  head: string;
  module: string;
  node: string;
  target: string;
  anchor?: { file: string; line: number; anchor?: string };
}

export interface LinkEntry {
  protocol: string;
  match_kind?: string;
  self_link?: boolean;
  caller: LinkSide;
  callee: LinkSide;
}

export interface UnmatchedEntry {
  protocol: string;
  outbound: LinkSide;
}
