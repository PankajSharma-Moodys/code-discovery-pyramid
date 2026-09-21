# Know About — Trajectory Learning & Distribution (`trajectory.py`, `reflect.py`, Phase 9)

- The trajectory store is a **separate SQLite file** (`~/.cdp/trajectories.db`,
  override `CDP_TRAJECTORY_DB`), deliberately independent of whichever
  `WorkspaceStore` backend a workspace uses — deleting the whole workspace
  state directory must leave trajectory data intact (verified literally).
- R10 is enforced structurally, not by convention: a "promotion" (lesson) has
  a fixed, small, closed field allowlist per kind
  (`import_channel_hint`/`prompt_fix`/`budget_change`); any extra key is
  rejected outright, so a model cannot smuggle claim-shaped content
  (subject/anchor/evidence) through a lesson even if it tried. This holds
  through the cut/load round-trip too, not just at validation time.
- Lesson-sets are cut and versioned, never live: `cut_lessons()` freezes the
  currently-pending promotions into an immutable version number; a run pins
  `--lessons vN` (reproducible exactly) or resolves the latest *promoted*
  cut by default. An unpromoted cut is invisible to default resolution.
- A promotion only steers routing (import-channel hints, budget), never claim
  content — this is R10 made concrete. A `prompt_fix` promotion renders as an
  appended `**Lesson:** <text>` line in a named prompt section, general
  across all 7 prompt sections, not special-cased.
- Holdout gating enforces "learn on A–E, benchmark on F": `cdp holdout`
  refuses outright if the target repo already appears in the cut's own
  learning corpus.
- The deterministic T3-rate holdout can only ever show non-increasing T3 rate
  for an `import_channel_hint`-only lesson (a hint can only resolve an import,
  never un-resolve one) — the REJECT branch of that specific promotion bar
  is structurally unreachable with today's only lesson kind.
- A live-model coverage-based holdout needs a much larger question count to
  be trustworthy — an n=3 result showing "lessons hurt" was explicitly
  documented as unable to support that claim, not treated as a verdict.
- Core (`cdp/`) must import no optional framework, ever — enforced by an
  AST-based test (`test_core_purity.py`) that fails naming file:line for any
  forbidden import, not by discipline alone.
