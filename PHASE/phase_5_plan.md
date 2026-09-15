# Phase 5 — Runner & supervisor

**Goal.** Turn the wave loop from a procedure a human follows in `SKILL.md` into
`cdp run` — a component that dispatches, retries, resumes and records why
anything failed. And define the runner protocol so that anything able to turn a
prompt into patch JSON is a valid backend.

`CDP_CLI_SCOPE.md §F` is blunt about what this is: **a map-reduce with a
validation gate, not an agent graph.** Stdlib, no framework. Core imports no
framework, ever — that is the entire de-vendoring job.

## Scope items

| id | Item |
|---|---|
| 4.1 | Runner protocol — ~50-line documented interface |
| 4.3 | `cdp run` |
| 4.4 | Task state machine |
| 4.5 | Leases, supervisor-held |
| 4.6 | `--resume` + partition-drift guard |
| 4.7 | `--max-attempts` default 3 |
| 4.9 | Measure fixed overhead, then decide on batching |

## Preconditions

Phase 2 (`runs` + `tasks` tables, 0.12) and Phase 4 (adjudication — the
supervisor's fold step calls it). Phase 3's scope-hash cache (3.3) is what makes
`run --stale-only` meaningful.

## Milestones

### M5.1 — The runner protocol (4.1)

```
prompts → [any LLM, any framework] → inbox → collect
```

A documented interface of about 50 lines: input is a prompt file, output is
patch JSON at a known path, plus a wall-time and token report. `prompts` and
`collect` keep working standalone — `cdp run` merely drives them
(`ARCHITECTURE.md`).

Two reference runners in-tree: a **subprocess runner** (shell out to any CLI) and
a **file runner** (drop prompts, wait for files — this is today's manual loop,
made explicit). The LiteLLM adapter (7.2) is Phase 9 and lives outside core.

**Acceptance.** `runner.py` exists with two implementations, neither importing
anything outside stdlib. A conformance test drives both. A third-party runner can
be written against the doc alone, with no source reading — verify by writing one
against the doc and not the code.

### M5.2 — Task state machine (4.4)

```
pending → dispatched → returned → validated → folded
```

with `expired` / `invalid` / `anchors_failed` / `empty` → retry → `abandoned`.

**Each failure has a different remedy, and conflating them is why failures are
undiagnosable today.** `invalid` means fix the schema violation. `anchors_failed`
means the model fabricated or the file moved. `empty` means yield collapse —
possibly a bad model (Phase 6's `doctor` catches it), possibly a prompt
regression. `expired` means the supervisor died. One retry policy over four
distinct causes is four wrong policies.

Transitions are recorded in `tasks` with `last_error`. R6 binds: **a failed scope
becomes an `unknown`, never a silent gap.** Coverage must not lie.

**Acceptance.** Each terminal state reachable and provoked by a test. `status`
renders a per-run task table. An `abandoned` scope shows as an `unknown` in
state, with the `tasks` provenance state `abandoned` from Phase 4's gate 3.

### M5.3 — `cdp run` (4.3)

Read schedule → dispatch a wave → collect → adjudicate → fold → next wave.
`--wave N`, `--wave-all`, `--stale-only` (the bucket Phase 3 M3.1 defines),
`--scope <selector>`.

Waves stay ordered: wave N+1 inherits the verified facts wave N established,
which is why a shared common module is scheduled before the modules importing it
(`SKILL.md:133-136`).

**Acceptance.** `cdp run --wave-all` on `$TARGET_REPO` completes a full pyramid
with no human in the loop, and its output matches what the manual `SKILL.md` loop
produces for the same scopes at the same template version.

### M5.4 — Leases (4.5)

**Held by the supervisor, not the leaf.** Heartbeat 30s, lease 90s → supervisor
death is detected in 90s regardless of tier. A leaf on a slow frontier model does
not need to know about leases at all, which is what keeps the runner protocol
text-in/JSON-out.

Fallback for stateless runners: a tier-derived ceiling **learned empirically**
from `dispatched_at` + `wall_ms` p99 per `dim_tier`, not guessed. Until Phase 9's
star exists there is no p99 — so v1 ships a conservative constant and records the
wall times that will later replace it. Say so in the code rather than presenting
the constant as considered.

**Acceptance.** Kill the supervisor mid-wave; within 90s the in-flight tasks are
reclaimable. Wall times recorded per task from day one.

### M5.5 — `--resume` and the partition-drift guard (4.6, 4.7)

`runs.partition_hash` matches → true resume: reclaim tasks past lease as
`expired`, re-dispatch, leave folded tasks untouched and unpaid-for again.

Differs → **new run**, inheriting completed scopes whose own *scope hash* is
unchanged and re-queueing the rest. This is what prevents stale work from being
folded against a changed partition, and it is also the answer to Phase 3's open
interaction — a refresh landing mid-run changes the partition, and the guard
catches it rather than silently corrupting the fold.

`--max-attempts` defaults to 3, configurable. On exhaustion the scope surfaces as
an honest `unknown` (R6), not as missing coverage.

**Acceptance.** Reproduce the `ARCHITECTURE.md` crash scenario exactly: 2 tasks
past lease reclaimed, 1 pending dispatched, 13 folded untouched. Then change a
file, resume, and confirm a *new* run opens inheriting unchanged scopes.

### M5.6 — Measure fixed overhead, then decide (4.9)

Each leaf pays a system prompt plus tool definitions before reading anything. If
that is ~10k tokens, 17 leaves is ~170k of overhead scaling with **scope count,
not code size** — which would mean CDP's cost curve is wrong in a way no amount
of prompt tuning fixes.

`CDP_CLI_SCOPE.md` marks this **unverified — measure first.** So: measure it.
Report tokens by section from the input fingerprint. If it holds, batch 6–8
scopes per call; bounded scope is a property of the prompt, not of the process.

**Do not implement batching before the measurement.** If overhead is 1k rather
than 10k, batching adds a failure mode (one bad scope poisoning seven others) to
buy nothing.

**Acceptance.** A measured number, recorded, with the batching decision following
from it and written down either way.

## Modules touched

`runner.py` (new), `supervisor.py` (new), `store/` (task lifecycle, leases),
`prompts.py` (input fingerprint groundwork), `cli.py` (`run`), `query.py` /
`status` (per-run task table).

## Stress tests

| Case | Expectation |
|---|---|
| Runner returns malformed JSON | `invalid`, retry, distinct from `anchors_failed`. |
| Runner returns valid JSON with zero claims | `empty`. This is yield collapse and must be visible, not counted as success. |
| Runner hangs forever | Lease expiry is the only thing that saves the run. Test with a runner that never returns. |
| Two supervisors, same run | Lease acquisition must be atomic in SQLite. Second supervisor takes nothing. |
| Machine sleeps for 4 hours | Every lease expired; resume reclaims all. Verify it does not instead open a new run for no reason. |
| Partition changes mid-run | New run, inherited unchanged scopes. The Phase 3 interaction, closed here. |
| Scope fails 3× on a schema violation the prompt causes | 3 attempts burned per scope across every scope. `status` must make a *systemic* failure look systemic — a per-error-message clustering in the task table, or the operator sees 17 unrelated failures. |
| `--stale-only` with an empty stale set | Exit cleanly saying zero scopes need review. Not an error, not a full run. |
| Supervisor dies between fold and task-state write | Patch content-addressing (0.3) makes the re-fold a no-op by hash. Verify — this is the case where idempotency-for-free actually pays. |

## Exit criteria

- `cdp run --wave-all` completes the full pyramid on `$TARGET_REPO` unattended.
- Every task state reachable, provoked by test, and distinguishable in `status`.
- Crash-and-resume scenario reproduced exactly as `ARCHITECTURE.md` specifies.
- Two runners pass one conformance suite; core imports no framework — enforced by test.
- Fixed overhead measured; batching decided on evidence and recorded.
- R6 holds: no failure produces a silent coverage gap.

## Out of scope

Digest-first leaves (4.2) and tiering (4.8) — both Phase 6, both gated on the
`doctor` harness that does not exist yet. Model selection and provider adapters
(7.2) — Phase 9. Trajectory writes (6.3) — Phase 9, though `tasks` shares its
grain by design: one writes for recovery, the other for learning.
