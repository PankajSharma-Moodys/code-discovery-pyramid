# PLAN — CDP web layer, phased

Source: `WEB_RESEARCH.md`. Design only, no code in this pass. Phases are
dependency-ordered, not date-ordered — each phase blocks the next.

| Phase | Contents | Score (wow/effort, §8) | Expectation (done = ) | Delivery |
|---|---|---|---|---|
| **0. Spine** | Read-only SQLite driver (`mode=ro`), manifest-pinned snapshot selection, `status()`/`doctor()`/`refresh(preview=True)` extracted from `cmd_*` as callables, node-ID namespacing (`module:`, `scope:`, `file:`, `sym:`, `route:`, `table:`) | ☆ / M — invisible but blocks 1, 3b, 4, 6 | `/api/status` and `cdp status --json` validate against one Pydantic model (contract test in CI); a `refresh` started mid-poll never surfaces a zero-claim graph (test asserts manifest-gated read); every artifact ID resolves through the new namespace with no ad-hoc string matching left in handlers | FastAPI app skeleton + Pydantic contract tests + node-ID module, no UI yet |
| **1. Atlas core** | Altitude canvas L3→L2→L1 (dagre-ranked from `graph.levels`), hover peek, click inspector, animated path trace | ★★★★ + ★★★★★ / M+S | Cold load → path-trace animation plays within 3 clicks, every hop resolves to a real `file:line` anchor; 60fps pan/zoom at this repo's scale (1,967 symbols) measured, not assumed | Working Atlas on this repo, demoable standalone |
| **2. Lenses + freshness backend** | Divergence + Confidence lenses (pure recolor); persisted `churn_cache` table populated at fold time; Freshness lens wired to it | ★★★★ / S (lenses) + M-backend (cache) | Switching lens never re-triggers layout (visually verify no node movement); Freshness lens renders in <200ms, not a multi-second `git log` spinner | 3 lens toggles shipped; churn cache migration |
| **3. Control Room core** | Run console over `snapshot_task` (SSE), repo health strip (`HEAD` vs `as_of`, one-click refresh), ask-bar with `xref.symbols` typeahead routed onto the canvas | ★★★★ ×3 / M | Dispatch a wave in Control Room → matching nodes animate live in the Atlas within one poll interval (the doc's core "wow" claim, §2) — test this end-to-end, not per-tile; ask-bar query always shows the literal `cdp query …` it ran | Control Room MVP + live cross-tab event wiring |
| **4. Reach** | Agent-layer hookup tab + liveness check; L4 cross-repo constellation; time scrubber (`diff --json` replay) | ★★★ / M, ★★★★ / M (needs ≥2-repo demo corpus), ★★★★ / M | Constellation only ships if a real ≥2-repo demo set exists — otherwise cut, don't fake it; scrubber replays at least 3 real commits from this repo's history with visible add/remove/pulse | Whichever of the three has real backing data by demo day |
| **5. Long tail** | Doctor heatmap, trajectory/lessons explorer, licence gate in CI, `LICENSE` file for CDP itself | ★★★ / M | Doctor heatmap matches `doctor.aggregate` output exactly (contract test like Phase 0); CI fails on any non-allowlisted licence appearing in `npm ls --json` | Narrowest-audience tiles + housekeeping, last |

## Cut lines (apply under time pressure, in order)
1. Phase 4's constellation and scrubber — both conditional on data that may not exist by demo day.
2. Phase 5 entirely — doctor/trajectory audience is narrowest per §8.
3. Freshness lens backend (2's churn cache) — ship Divergence/Confidence only, mark Freshness "coming soon."
Never cut: Phase 0 (nothing else is real without it), Phase 1's path trace (§9: "this single feature is the demo"), the manifest-gated-read fix (§9: the one failure mode that reads as "CDP lost everything").

## Stress test of this plan
- **If Phase 0's node-ID scheme slips, Phase 1 cannot start** — `/api/node/:id` and the inspector rail both need it (§7.3). Treat it as the literal first ticket, not a design footnote.
- **Phase 3's "wow" is unverifiable by tile-level testing** — a run console and an Atlas can each work in isolation while the live cross-tab wiring is still broken. Its acceptance test above is deliberately end-to-end, not per-component.
- **Phase 4 items are demo-data-gated, not effort-gated** — ranking them by wow/effort (as §8 does) hides that the constellation is worthless without a second repo. Gate on data existing, check that before scheduling engineering time.
- **No phase currently owns the licence/`LICENSE`-file gap (§6.4)** — it's a legal exposure larger than any dependency choice, sitting in Phase 5 (last) only because nothing else depends on it technically. Flag this explicitly: it should be fixed opportunistically before Phase 5 if anyone has an idle hour, not deferred by default.
