# Flow tab — design

Budget: ≤90 lines. Status: approved in chat 2026-10-08. Research basis:
deep-research report (lineage tools DataHub/Dataplex/Foundry/Validio,
NDepend, Sourcetrail; McGee & Dingliana 2012 on bundling).

## Goal

The Atlas graph (sigma.js, force layout) is an unreadable hairball on large
repos. Add a **Flow** tab that shows how data moves from sources to sinks,
left to right, starting small and expanding on click. The existing graph tab
stays unchanged.

## Decisions (user-approved)

- Flow is a new tab, **first** in the view switcher and the **default** view.
- Shows **data-flow edges only**; `call` and `config_read` edges hidden behind
  "+ calls" / "+ config" toggles (off by default).
- First view is **grouped and collapsed** (~20 boxes); click to expand.
- Layout **@dagrejs/dagre** (layered, MIT); rendering **React Flow** (@xyflow/react, MIT).
  ELK.js rejected: EPL-2.0/GPL-3.0 is outside `check-licenses.mjs`'s allowlist.

## Data model (verified against the RDL store's `/api/graph?level=L2`)

Built only from the deterministic scan's typed L2 graph; no AI.

| Role | Items | Evidence in L2 |
|---|---|---|
| source | routes | `http_in` edges are stored `module → route`; draw `route → module` |
| source | scheduled jobs | modules with a `schedule` edge (to e.g. `library:io.dropwizard.jobs`) |
| sink | tables, entities | `persist` targets of type `table` / `entity` |
| sink | outbound HTTP, metrics | `http_out` / `metric_emit` edges; their only target is the client **library**, so the sink is labelled by it ("HTTP out · okhttp") |
| transform | code modules | everything else on a data path |

- Edges ending at a library for `persist`/`http_in`/`schedule` are framework
  wiring, not data destinations — excluded from the flow.
- `schema_own` (migration → table), `map`, `process_boundary` are excluded.
- Test files (scan file role `test`) are excluded.
- Groups: each code module gets `group` = its top-level code module/directory
  (e.g. `risk-data-lake-api`), derived server-side from the scan's
  symbol → file data. The L3 `members` lists do NOT cover modules (0 of 1199),
  so they can't be used.

## Backend

`GET /api/flow?repo=&state_dir=&include=calls&include=config` returns
`nodes[{id, label, kind, role, group, node_id}]`, `groups[{id, label, role,
count}]`, `edges[{source, target, kind, count}]` with edges already oriented
source → sink. Read-only; same store resolution as other GETs.

## Frontend

- `FlowView` registered in `viewStore` as `"flow"`; default view; first tab.
- Grouping/expand/collapse/trace are pure client-side functions over the
  `/api/flow` payload (instant clicks, unit-testable).
- Collapsed view: source groups (Routes, Scheduled jobs) → code groups →
  sink groups (Tables, Entities, HTTP out, Metrics). Box badge = member count.
- dagre `rankdir: LR`. dagre has no layer pinning, so sources/sinks are kept at
  the ends by layout post-processing (sources → min rank x, sinks → max rank x).
- An expanded group is laid out as a dagre cluster (`setParent`) drawn as a
  React Flow group node; no deep nesting (one level of expansion per group).
- Edges: no permanent labels; stroke width scales with aggregated count;
  hover tooltip "persist · 12".
- Click group → expand in place (compound node); click again → collapse.
  Expanding >150 members asks for confirmation first.
- Click a leaf → trace: upstream blue, downstream orange, rest faded; opens
  the existing inspector rail for that node. Esc / background click clears.

## Testing

- Backend unittest on `tests/fixtures/minirepo` scan: role/group assignment,
  edge orientation, exclusions, `include` toggles.
- Frontend vitest for grouping, aggregation, expand/collapse, trace.
- Build + lint; manual check on the RDL store (`~/cdp-demo/.cdp`).

## Out of scope

Sankey, DSM/matrix, edge bundling (hurts path tracing), AI-inferred roles,
changes to the existing graph tab.
