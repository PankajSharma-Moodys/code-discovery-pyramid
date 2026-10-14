# `filter`: grep built into `cdp_query` for wide ("blind") queries

**Status:** implemented (2026-10-14); `next` also repeats `term`/`match`/`format`, and a pattern matches the full or the displayed name. Separate from `CONTEXT_PLAN.md`, which it does not modify.

## Context
On sql-pool, piping CDP's CLI into grep (`run.py query config --max-tokens 0 | grep S3_`) gives CDP's accuracy
at grep's context cost: about 25k chars go into the pipe, but only the matching lines reach context. It has
three problems:
- **Not available over MCP.** MCP is the primary channel, and its output can't be piped.
- **The cap trap.** With the default cap, `| grep mssql-metadata` found 7 of 12 rows. The cap cut the rest
  before grep ran, and grep threw away the `next:` line that would have warned.
- **No honest counts.** `grep -c` counts lines, not rows, and can't say how many rows there were in total.

Agreed with the user: filtering is for **wide, blind queries**. Targeted queries (`compact` for one known
name) stay exactly as they are.

## Design
**New parameter `filter`** (MCP `filter`, CLI `--filter`): a regex matched against each row's `list` line.
- **The line it matches:** `name → to  path:line  note`, using **full** names (not the short display names),
  so a pattern on a package or path also hits. It behaves like `grep -E`: case-sensitive, `(?i)` to ignore case.
- **Where it runs:** in `views.apply` (`cdp/query/views.py:327`), on `all_rows`, **before** `totals`, the cap
  and `offset`.
  - The cap and paging then work over matched rows only, so the cap trap can't happen.
  - `count` reports true matched totals.
- **Views:** only `count` and `list`.
  - With no view given, `filter` means `list`.
  - With `compact` or `detail`, it is an error: "filter narrows wide list answers; for one row use
    term=<name> match=exact". Targeted queries stay as they are.
- **Answer:** gains `filter: "<pattern>"` and `matched: N of M rows`.
  - `next` keeps the filter (`view=list filter=... offset=N`), so pages stay consistent.
  - Zero matches still states `0 of M`, so an empty result is never mistaken for "nothing exists".
- **Format parity:** text and JSON match the same line, so they return the same rows.
- **Guards:** reuse `compile_regex` (`cdp/query/common.py:249`) for the pattern-length error. Reuse
  `REGEX_MAX_LINE` for over-long lines, which are skipped and named in `not_searched`. No time budget is
  needed, because rows are already in memory.
- **Kinds:** every kind `views` projects (`UNPROJECTED` stats/coverage excluded). It's added to `APPLIES`
  through the existing loop in `cdp/guide_kinds.py:332`.
- **Not in `.cdp.toml`:** a repo-wide default filter would hide rows from every answer.

## Constraint: the MCP schema token budget
The schema is at about 1,991 of 2,000 tokens (`mcp_server/tests/test_mcp_server.py:47`; 7,965 chars / 4).
Adding `filter` will go over, so the same change must trim at least as much elsewhere. Candidates:
- the `exact` description ("alias for `match=exact`"), or drop the alias from the MCP schema only, keeping
  it on the CLI;
- tighter `view` and `budget` wording.

The test limit stays at 2000.

## Files
- **`cdp/query/views.py`:** `_filter_rows(kind, rows, pattern)`. It builds lines with `_list_row`, plus a
  full-name variant of `_row_lines`. Applied in `apply`, with `filter`/`matched` added to the answer and to
  `next`.
- **`cdp/query/__init__.py`:** `dispatch` takes `filter`, validates the view, and makes `filter` imply `list`.
- **`cdp/commands/core/query.py`** (`--filter`), **`mcp_server/tools.py`** (arg check).
- **`cdp/guide_kinds.py`:** `PARAMS["filter"]` and `APPLIES`. **`cdp/guide.py`:** `mcp_properties()` plus
  the trim above, and one line in `USAGE` (session digest and SKILL.md).
- **Hand-written surfaces:** `AGENTS.md` (CLI form), the CLAUDE.md rule 6 sentence (`install_extras.py`),
  and `.cdp.toml.example` (a note that filter is per call only).
- **`FILTER_PLAN.md`** (new; this plan). `CONTEXT_PLAN.md` is left unchanged. `docs/CDP_REFERENCE.md` and
  `SKILL.md` are regenerated with `scripts/gen_guide.py`.

## Tests (`tests/test_query_views.py`)
- **Equals grep:** `filter=P` rows equal `--max-tokens 0 --view list` output piped through Python
  `re.search(P)` on full-name lines, for routes, config and search.
- **Cap after filter:** a filter whose matches come after the default cap returns all of them. This
  mirrors sql-pool's `mssql-metadata`, which found 12 rows rather than 7.
- **Counts:** `view=count filter=P` gives the matched total, and `matched: N of M` is right.
- **Paging:** pages over a filtered answer join up to exactly the matched set, and `next` carries the filter.
- **Rejected on compact/detail:** both are errors. With no view, filter means list. Zero matches reports `0 of M`.
- **Parity and guards:** text and JSON give the same rows. An over-long pattern is an error, and an
  over-long line is named in `not_searched`.
- **Schema:** the existing 2000-token test still passes.

## Verification
1. Run the focused suites, then the full suite (`python3 -m pytest -q tests mcp_server/tests`),
   `run.py install --self`, `gen_guide.py`, and the golden check (expect no golden change, since it uses no
   filter).
2. **sql-pool, MCP:** `cdp_query(kind="config", filter="mssql-metadata")` returns 12 rows under the default
   cap, the same as `--max-tokens 0 | grep -c`. `kind="routes", filter="reservations"` returns 5 rows.
3. **Live:** re-sync sql-pool, **fully restart** Claude Code (a stale MCP server ignores new parameters), and
   ask something blind, e.g. "which config keys mention S3 or metadata, and who reads them?". Check that it
   uses `filter` and that the tool output is small.
