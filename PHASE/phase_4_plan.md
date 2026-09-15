# Phase 4 — Trust gates & human knowledge

**Goal.** A second gate beyond "does the anchor resolve": **does the
deterministic layer agree?** Plus the four gates that stop `unknowns[]` from
being an unchecked array, and `cdp answer`, which lets a human put what only they
know into the same pipeline under the same rules.

`verify.py:16-20` states the current boundary honestly: it confirms cited text
exists where a claim says it does, and does *not* confirm the text supports the
statement. This phase narrows that gap as far as determinism can, and says
plainly where it stops.

## Scope items

| id | Item |
|---|---|
| 6.1 | Entailment validation — `entailed` · `consistent` · `contradicted` |
| 6.1b | Negative entailment, applied to unknowns |
| 1.5 | `cdp answer` |
| — | Four unknown gates, `needs_*` vocabulary, R12 ratchet |

## Preconditions

Phase 2 (provenance columns, verdict column, `tasks` table) and Phase 3
(refresh, so a human claim can decay like any other). The `tasks` table matters
specifically: it is what separates `unexamined` from `unknown` from `abandoned`,
which today look identical.

## Why this precedes the runner

Phase 5's supervisor runs `validate → verify anchors → ADJUDICATE → fold`
(`ARCHITECTURE.md`). Adjudication is this phase. Building the supervisor first
means building it around a gate that does not exist and retrofitting the gate
into a dispatch loop afterwards.

## Milestones

### M4.1 — Entailment validation (6.1)

Three verdicts, assigned deterministically against extraction:

| Verdict | Meaning |
|---|---|
| `entailed` | Backed by an existing `io_edge` / `defines`. Python already knew it — you paid for a paraphrase. |
| `consistent` | No opinion. Normal and expected for intent claims. |
| `contradicted` | Rejected and logged. |

**The contradicted bucket is gold.** Every entry is either an agent error or an
extractor gap, and it is the reward signal every learning mechanism in Phase 9
depends on. Store it, do not just count it.

`entailed` is not a failure state — it is a cost signal. A scope whose claims are
all `entailed` did not need an expensive model, which is precisely the residue
question `CDP_CLI_SCOPE.md §N` defers. Emit the per-scope ratio now so Phase 6's
tiering has data to reason from.

**Acceptance.** Verdict on every claim. On `$TARGET_REPO`'s derived patch
(`derive.py`, zero model calls), claims are `entailed` or `consistent` by
construction and **never** `contradicted` — a contradicted deterministic claim
means the entailment checker disagrees with the extractor that produced it, which
is a bug in one of them and must be found before any model output is judged.

### M4.2 — The four unknown gates (6.1b + unknown discipline)

The asymmetry, stated in `CDP_CLI_SCOPE.md`: claims are falsifiable, unknowns are
not. You cannot validate an unknown's *content*; you validate everything around
it. Four gates, all free, all in `collect`:

| Gate | Check |
|---|---|
| Subject exists | Names a subject present in `defines[]` / `io_edges`. If not, it is about nothing. |
| Negative entailment (6.1b) | If extraction can already answer it, reject. Agent says "I don't know what table this writes" while a `persist` io_edge sits in xref for that scope → reject. |
| Provenance state | `unexamined` (no agent ran) vs `unknown` (agent ran, couldn't tell) vs `abandoned` (agent ran, failed 3×). Read from `tasks` (0.12). |
| Clustering | The same unknown across 40 scopes is one systemic gap — a weak extractor — not 40 findings. |

**No verification service.** An LLM judging another LLM's "I don't know" is
unverifiable all the way down. Grounding is deterministic, human (M4.4), or
runtime — and the runtime join lives in an RCA agent, outside CDP core.

**Acceptance.** Gates run in `collect`. A hand-written unknown about a
nonexistent subject is rejected. An unknown answerable from xref is rejected with
the answering edge cited in the rejection — telling an agent *why* it was
rejected is what makes the rejection a lesson.

### M4.3 — `needs_*` and the R12 ratchet

An unknown is cheap to emit, impossible to falsify, and CDP *praises* honest
absence. The incentive is perverse. Countermeasure: **an unknown must state what
would resolve it**, from a closed vocabulary:

`needs_runtime` · `needs_external_doc` · `needs_human` · `needs_wider_scope` ·
`needs_other_repo`

One that cannot say is **malformed and rejected**. This raises the price of the
easy out and makes unknowns *routable*: `needs_wider_scope` escalates the tier
(Phase 6), `needs_other_repo` becomes a `link` task (Phase 8).

The ratchet (R12):

| Rule | |
|---|---|
| Only an **adjudicated claim** discharges an unknown | agent re-run or `cdp answer` — both pass validate → verify → entail → fold |
| **Silence never discharges** | a later patch that simply omits it does not resolve it |
| Subject disappears → `moot`, **not** `resolved` | different outcome, recorded separately, matters for audit |
| Discharge is attributed | `resolved_by(claim_id, author_kind, at_snapshot)` |
| Rollback restores unknowns | it is a re-fold; nothing special needed |

Schema change: `needs_*` becomes required. Existing unknowns without it need a
migration decision — grandfather them as `needs_human` with a marker, or reject
on read. Grandfathering with a marker is the honest option; silently backfilling
is not.

**Acceptance.** An unknown without `needs_*` is rejected. A patch omitting a
prior unknown leaves it open. Deleting the subject marks it `moot`. Rollback
restores the unknown set exactly.

### M4.4 — `cdp answer` (1.5)

```bash
cdp answer <scope> --subject X --kind Y --claim "..." --anchor <file:line>
```

Reuses the **entire** pipeline — validate → verify anchor → entail → fold. No
bypass. `author_kind=human` plus an identity column.

R11: **humans outrank models on interpretation, never on structure.** A human
claim contradicted by extraction is `contested`, not accepted. `author_kind`
changes merge precedence, never the gate.

And it decays. `ARCHITECTURE.md` makes the case: the engineer who wrote the note
may have left; three months later the code is rewritten, `refresh` invalidates
the review, and the note lands in "anchored but unreviewed" and asks to be
re-confirmed. That is the whole point — institutional knowledge that expires
visibly instead of rotting quietly in a wiki.

**Acceptance.** Reproduce the `ARCHITECTURE.md` `RetryPolicy.execute` scenario
end to end on `$TARGET_REPO`: answer an unknown, see it discharged with
attribution, edit the anchored file, refresh, and watch the human claim move to
anchored-but-unreviewed. A human claim contradicted by an `io_edge` comes out
`contested`.

## Modules touched

`verify.py` (entailment gates join anchor verification inside the fold),
`schema.py` (`needs_*` required, verdict, resolved_by), `state.py` /
`store/` (verdict column, unknown lifecycle, discharge attribution),
`cli.py` (`answer`), `query.py` (`unknowns` renderer gains `needs_*` and
provenance state; `claims` gains verdict).

## Stress tests

| Case | Expectation |
|---|---|
| Entailment checker is too strict | Legitimate intent claims marked `contradicted` and thrown away. Measure the rate on `$TARGET_REPO` **before** making `contradicted` a rejection — if it exceeds a few percent, log without rejecting until calibrated. Do not ship a gate that silently deletes good work. |
| Entailment checker is too loose | Everything is `consistent`; the gate buys nothing. The derived-patch test in M4.1 is the canary. |
| Claim paraphrases an edge with different wording | Entailment is over structure, not strings. Match on subject + channel + target, never on statement text. |
| Unknown legitimately about something not in `defines[]` | e.g. "why is there no retry here" — a subject that does not exist is the *content*. Gate 1 rejects it. This is a real false-positive class: allow a scope-level subject, and test it. |
| Same unknown across 40 scopes | One clustered finding. Verify clustering does not also collapse 40 genuinely distinct unknowns that share a phrasing. |
| `cdp answer` with a fabricated anchor | Anchor verification rejects it. Humans are not exempt. |
| Human and model disagree on a closed-vocabulary field | R11: human wins on interpretation. Human contradicted by *extraction*: `contested`. Two different rules; test both. |
| Unknown discharged, then rollback | Unknown returns, discharge attribution is gone with the rolled-back run. |

## Exit criteria

- Every claim carries a verdict; the `contradicted` bucket is stored and inspectable.
- Four gates run in `collect`; each demonstrated rejecting a real case with a cited reason.
- `needs_*` required; malformed unknowns rejected; the migration decision recorded, not silent.
- R12 ratchet holds under every case in the table above.
- `cdp answer` works, decays, and is refused on a bad anchor.
- Contradiction rate on `$TARGET_REPO` measured and recorded — the calibration number Phase 6 needs.

## Out of scope

Reflection and learning over the `contradicted` bucket (Phase 9). Tier
escalation driven by `needs_wider_scope` (Phase 6). `link` tasks from
`needs_other_repo` (Phase 8). **Completeness of unknowns is out of scope
permanently** — whether an agent failed to notice something it did not know it
did not know is unknowable by construction. The only proxies are coverage and
`doctor`'s recall against a golden set. `CDP_CLI_SCOPE.md` says this belongs in
user-facing docs, not only in design notes; add it to `cdp help` in this phase.
