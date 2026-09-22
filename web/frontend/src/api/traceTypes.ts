/**
 * `/api/trace` has no `response_model` on the FastAPI side -- it's a thin
 * pass-through of `cdp.query.q_trace`'s dict (`web/api/app.py:get_trace`,
 * `cdp/query.py:q_trace`), same posture as `/api/query`. `schema.ts` types
 * its body as `{[key: string]: unknown}` accordingly; this is the shape
 * `q_trace` actually returns, kept here instead of loosening types at each
 * call site.
 */
export interface TraceFileRow {
  file: string;
  module: string | null;
  why: string;
  /** `"file:line"`, or `null` when the row has no anchor. */
  at: string | null;
  confidence: string;
}

export interface TraceResult {
  query: "trace";
  entry: string;
  found: boolean;
  why?: string;
  caveat?: string;
  resolved_as?: unknown;
  hops_exhausted?: boolean;
  trail?: string;
  file_count?: number;
  files: TraceFileRow[];
  unknowns: unknown[];
}
