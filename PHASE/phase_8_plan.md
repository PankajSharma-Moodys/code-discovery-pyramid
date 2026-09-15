# Phase 8 — Cross-repo link

**Goal.** Answer "who calls this service" and "what publishes to this topic"
across a microservice estate, by matching the channel edges CDP already extracts
across registered snapshots — and treat a call to something outside the scanned
set as a **deliverable, not an error**.

This phase mirrors the core loop exactly and reuses the runner protocol. It adds
no new epistemics; it adds a second axis.

R3 is the binding constraint: **`scan` writes, `link` reads.** `link` never
mutates snapshot data.

## Scope items

| id | Item |
|---|---|
| 5.1 | `cdp link scan` |
| 5.2 | `cdp link prompts` / `collect` |
| 5.3 | `cdp link refresh` / `query` |
| 5.4 | Link schema |
| 5.5 | Links are between *snapshots* |
| 5.6 | `unmatched http_out` is a deliverable |
| 5.7 | Non-entanglement test |

## Preconditions

Phase 2 (`link.*` namespace and `link_runs` / `link_tasks` created), Phase 5
(runner protocol — `link prompts`/`collect` reuse it wholesale), Phase 3
(snapshots to link *between*, and refresh semantics to mirror).

At least two real repositories that genuinely talk to each other. Without them
this phase is untestable on real input, and a fixture pair of toy services will
validate the matcher against exactly the cases the matcher was written for.

## Milestones

### M8.1 — `cdp link scan` (5.1, 5.4, 5.5)

Deterministic. Gather `http_out` / `http_in`, `event_publish` / `event_subscribe`
and `persist` / `schema_own` edges across registered snapshots; match on path ·
topic · table.

`match_kind`: `exact` | `heuristic` | `unmatched`. The contract carries protocol,
path/topic/table, direction and payload shape, plus findings, unknowns and
metadata.

**Links are between snapshots, not repos.** Repo A@X talks to repo B@Y. This is
not a graph over repositories — it is a graph over pinned commits, which is what
makes a link re-verifiable at all.

**Acceptance.** Across two real registered snapshots, `link scan` produces exact
matches on at least one route and one topic, and classifies the rest. Zero model
calls.

### M8.2 — `unmatched` as output (5.6)

A call to something outside the scanned set is often **the most interesting
output on a microservice estate** — it is the boundary of what anyone has
mapped. Render it as a finding with its citation, not as a matcher failure, and
never as an empty row.

**Acceptance.** `link query` surfaces unmatched outbound calls as a named section
with `file:line` for each. A vendor endpoint appears there rather than being
dropped.

### M8.3 — `link prompts` / `collect` (5.2)

The LLM tier fires **only on ambiguous matches** — a base URL assembled from an
env var, a topic built by concatenation. Everything exact stays free.

Reuses `runner.py` and the Phase 4 gates unchanged. `dim_task_kind = link`
distinguishes these tasks in the analytical star (Phase 9) while sharing every
operational mechanism.

Phase 4's `needs_other_repo` unknowns route here — that is the routing payoff the
closed `needs_*` vocabulary was introduced for.

**Acceptance.** An ambiguous `${BILLING_URL}/charge` edge becomes a link task,
gets adjudicated through the same validate → verify → entail → fold pipeline, and
its resolution is attributed.

### M8.4 — `link refresh` / `query` (5.3)

Re-verify link contracts against new snapshots, mirroring Phase 3's refresh
semantics: a contract whose anchor survives carries forward, one whose endpoint
vanished decays. `link query --service <s>` answers who calls it and what it
publishes.

**Acceptance.** Advance one repo by a commit that removes a route; `link refresh`
demotes the corresponding contract with a reason, and the *other* repo's snapshot
is unchanged.

### M8.5 — Non-entanglement test (5.7)

Assert executably: **drop every `link.*` row → no snapshot changes.** R3 as a
test, not a promise.

Phase 2 M2.5 shipped a first version of this against empty link tables. This
milestone re-runs it against fully populated ones, which is the only version that
proves anything.

**Acceptance.** With link data present, dropping all `link.*` rows leaves
`snapshot.*` and `claim.*` byte-identical. In CI, every phase after this one.

## Modules touched

`link/` (new — scan, prompts, collect, refresh, query), `store/` (link namespace
queries), `cli.py` (`link` subcommand group), `dataflow.py` (read-only source of
channel edges).

## Stress tests

| Case | Expectation |
|---|---|
| Two services with the same route path, different services | Path alone is ambiguous. Match must consider direction and service identity, or it will confidently link the wrong pair. |
| A service calls itself | Self-link. Valid, and must not be filtered as noise or counted as a cross-repo dependency. |
| Repo B not registered | Every `http_out` to it is `unmatched` — correct, and the deliverable per 5.6. It must not read as "B has no callers". |
| Snapshot A@X linked, A advances to A@Y | Links are to X. Either re-link at Y or report the link as pinned-and-stale. Silently following HEAD would violate 5.5. |
| 50 registered snapshots | Matching is pairwise. Verify the cost curve before anyone registers an estate. |
| Topic built by string concatenation in three places | Ambiguous → LLM tier. Verify the three do not become three unrelated tasks when they are one question. |
| Link contract contradicted by extraction | Phase 4's entailment applies unchanged. `contested`, not accepted. |
| Someone drops the workspace store | Link rows die with it. That is correct — links are derived. The *trajectory* store is separate (0.17) precisely so it does not. Confirm the separation holds. |

## Exit criteria

- `link scan` across two real repositories produces exact, heuristic and unmatched classifications with citations.
- Unmatched outbound calls render as a named deliverable.
- Ambiguous matches route through the runner and the Phase 4 gates unchanged.
- `link refresh` decays contracts without touching either snapshot.
- Non-entanglement test green **with link data present**, and in CI thereafter.
- `needs_other_repo` unknowns become link tasks end to end.

## Out of scope

A global graph over repositories — 5.5 is explicit that this is a graph over
pinned commits, and generalising it would make links unverifiable. Any link
operation that writes to `snapshot.*`.
