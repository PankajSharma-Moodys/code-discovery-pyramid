# CDP query efficiency — findings and tasks

**Budget:** 70 lines. Every number below was measured on 2026-10-12 on sql-pool (371 Java files) by
running `cdp query` at commit 85e5821 (before annotation work, "old") and at HEAD ("new"); tokens are
not measured, only bytes (≈ bytes/4). Anything not measured is marked **(unmeasured)**.

## 1. Measured

Text output (`cdp query`), bytes, old → new, 20 queries: every content query grew 1.06–2.7x
(`search AutoScaleJob` 1.1 KB → 3.1 KB; `routes` 6.6 KB → 15.2 KB; `table server` 2.1 KB → 5.1 KB;
`file X.java` 1.6 KB → 3.0 KB). `stats`/`coverage` unchanged. The baseline was already heavy for broad
terms: `symbol ServerService` 44 KB → 67 KB, `search server` 26 KB → 39 KB, `claims` 55 KB → 59 KB.

**What the agent actually receives is JSON, not that text.** `mcp_server/server.py:82` returns
`json.dumps(result)` as the tool text, so the compact `render()` output is never what the model sees
over MCP (the primary channel). Same query, same state, text vs JSON bytes:

| query | text | JSON | JSON/text |
|---|---|---|---|
| search AutoScaleJob | 3.1 KB | 4.8 KB | 1.6x |
| search server | 39 KB | 65 KB | 1.7x |
| symbol AutoScaleJob | 12 KB | 26 KB | 2.1x |
| symbol ServerService | 67 KB | 119 KB | 1.8x |
| file AutoScaleJob.java | 3.0 KB | 5.7 KB | 1.9x |
| routes (16 routes) | 15 KB | 108 KB | 7.1x |
| trace GET …/v1/pools | 15 KB | 37 KB | 2.4x |

Composition of the big results (JSON bytes):
- `symbol ServerService` = 83 substring matches (`elided 295`): claims 22%, per-method `body`
  (calls/throws/literals, P12) 13%, `class_annotations` 13% (the owner class's annotations repeated on
  every member), `used_by` 10%, `defined_at` + `defined_range` 15%.
- `search server`: claims 56%, `code` bucket 18%, `annotations` bucket 14%. Rows are split fairly over 7
  buckets (was 5), so the two new buckets each take a full share even when they say little.
- `routes`: JSON carries every annotation row of handler + class + params for each route; the text view
  caps them at 6 per route, JSON does not.

Static context per session/prompt: MCP tool description 1,583 B (unchanged); the UserPromptSubmit hook
appends `STANDING_RULE` + `RECIPE` ≈ 1.25 KB to every prompt in a scanned repo (cdp/hook.py:723-753).

## 2. Cause, ranked by measured effect

1. MCP sends full JSON (1.6–7.1x the rendered text). Largest single lever.
2. Budgets count rows, not bytes: 200 rows can be 100+ KB.
3. Substring `symbol`/`search` return many matches with repeated per-match detail.
4. Annotation work added data (class annotations per member, bodies, two search buckets).
5. Per-prompt hook text, ~300 tokens/prompt **(unmeasured in tokens; frequency per the hook docstring)**.

## 3. Tasks (each: change → success check measured the same way)

- **E1 MCP returns rendered text by default**, `format="json"` opt-in. Check: `routes` ≤ 20 KB, `symbol
  ServerService` ≤ 70 KB, no kind loses a field the text view needs; run mcp_server and agent_adapter
  tests. Risk: `render()` is lossy by design (annotation caps); decide which caps stay.
- **E2 Byte/token budget.** `budget` bounds output size; rows are cut by size, true `counts` kept. Check:
  no query over N KB at default settings.
- **E3 `symbol`:** per-member `class_annotations` once per class (or only on exact match); `body` only on
  an exact/single match or with a flag. Check: `symbol ServerService` JSON −25% or more.
- **E4 `search`:** cap each bucket at a small default with true counts shown; run `code`/`annotations`
  buckets only past a minimum term length; shorten claim rows to one evidence cite. Check: `search server`
  ≤ 40 KB JSON, `search @Every` still returns all 12 jobs.
- **E5 `routes`/`table`/`config`:** own annotations by default, class annotations on request. Check: `routes`
  JSON ≤ 30 KB.
- **E6 Hook:** put `RECIPE` in session start or the tool description, keep a one-line rule per prompt.
  Check: per-prompt injected bytes ≤ 300 B; `tests/test_hook.py` green. **(unmeasured: whether agents
  follow the one-line rule as well as the full recipe — run scripts/harness_eval.py before and after.)**
- **E7 Re-measure** old/new/after table above with the same 20 queries and record it here.

Not investigated: `claims` kind size (55–59 KB), exact tokenizer counts, `cdp_help` output size.
