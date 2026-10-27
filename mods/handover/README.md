# handover (v0.5.0)

`/handover` opens a pane that hands a long-running supervisor session to a fresh context: context-window and usage bars, a table of background agents, an animated Collect state / Write brief / Seed fresh context sequence. Where the pane cannot be placed, a compact band above the prompt is used.

Buttons: Refresh, Write brief (never clears), Clear and seed (refuses during a turn with a "try again when idle" note; needs a second press within 8 s when agents are active or deliveries arrived after the brief), Seed now and Reset (shown when they apply), Close.

## Handover as a state machine (v0.3)

Each session has a record `handover:<id>` in the plugin store; a clear creates `lineage:<new id> = {from, n}`, so you can hand over any number of times (A -> B -> C ...). The pane and band show the state in words, e.g. `handover #3, from 8a1f…`.

| state | meaning | new handover allowed |
|---|---|---|
| idle / ready / writing | no attempt yet / brief written / brief being written | yes |
| clearing | `/clear` requested, waiting for the session to go idle (countdown shown) | no, for 45 s (a clear may still be queued) |
| stalled | still clearing after 45 s | yes (Retry clear) |
| seeded | the fresh context received the seed | yes |
| failed | `/clear` was rejected | yes |

A repeat Clear press within 3 s of a clear is ignored. Nothing is ever refused permanently.

## Commands

- `/handover` opens the pane.
- `/handover seed` sends the pending seed into the current context (also the Seed now button).
- `/handover inbox` shows the last 10 ledger entries; `/handover inbox <seq>` one stored excerpt.
- `/handover reset` sets the current session back to idle and drops a pending seed (the Reset button asks for a second press).

## Inbox ledger (v0.4): visible and recoverable, never interfering

Answer to "is the receiving queue transferred?": NO. The engine queues deliveries (subagent completion notices = `task-notification`, `peer`, `coordinator`, `bridge`, scheduled triggers, ...) for the old conversation, and the docs do not say what happens to ones that arrive around or after a `/clear`: NOT DETERMINED. This mod does not move or touch them. It only records them.

- `on('session.receive')` is observe-only: it awaits `next(e)` with the same `e`, returns that result, and only then queues the ledger write without awaiting it. It never returns `consumed` and never rewrites text, origin, event or agentId. Any ledger failure (fs, store) is swallowed and logged to debug. Validate lists the hook as gating, so it carries a `.catch` that passes the delivery on.
- Ledger: `~/.claude/state/handover/ledger-<first session of the chain>.jsonl`, one file for A -> B -> C. Per delivery: seq, ts, origin kind, plugin, agent id, text excerpt (1500 chars), full length. Last 300 entries kept. Counters (total, by origin, last 15) live in the plugin store.
- Pane INBOX section and band `inbox N (M new)`; Clear and seed warns when deliveries arrived after the brief (press Write brief again, or press again within 8 s). The brief has an `## Inbox` section and receipt item 4b; the seed adds `; inbox: M deliveries arrived after the brief, read <ledger> first` when M > 0.
- Privacy: the ledger stores excerpts of what others send you (peer messages, relays, phone prompts) in plain text under `~/.claude/state/handover/`. Turn it off with `LEDGER_ENABLED = false` in `hooks/lib.ts` (no recording, no inbox UI); delete files yourself when done. Cap: 300 entries x 1500 chars per chain.
- Best-effort forward (UNTESTED LIVE): in the fresh context, `turn.complete` for an agent id that was active at handover writes the answer excerpt to the ledger (origin `handover-forward`) first, then appends ONE meta row (`$.session.append`, user role) holding only facts the mod computed: `agent <id> (active at handover #n) completed. Its answer is NOT included here (N chars)... run /handover inbox <seq>`. Answers are kept out of the model-visible row because they are model output that may carry untrusted file text, and a user-role row would give it user authority; `/handover inbox <seq>` prints it under `UNTRUSTED DATA`. Never twice per id; the pane shows a `FORWARD` line. It fires only if the engine still delivers those events after the clear (not determined).
- NOT recovered: deliveries the engine drops at the clear are not replayed; the ledger shows only what reached `session.receive`.

## Seeded right after the clear (v0.5): the post-clear watcher

The seed does not wait for a session-start hook or for you to type. In the live test of v0.4.1 the plugin that sits above this mod bypassed `classic.SessionStart`, so the seed went out only at your first prompt (42 s after the clear). Now, the moment `/clear` is requested, a watcher runs `$.clock.every(250)`: each tick reads `$.session.id()`; when it differs from the old id the fresh context exists, the watcher stops and the seed is submitted at once. The watcher lives up to 120 s (longer than the 45 s `stalled` mark, so a late clear is still seeded); after that use Seed now or Reset. A hot reload restarts it from the store (`seed-pending` + record `clearing`/`stalled`, younger than 120 s); if the id already changed it seeds immediately. Ticks never overlap.

Every trigger calls one idempotent `trySeed`: the watcher, `classic.SessionStart` (source `clear`), `session.end` (reason `clear`, checked from timers at 50 and 500 ms), the first `turn.start` / `prompt.submit` in the new context, `/handover seed`, Seed now. The nonce is claimed synchronously, so exactly one submits. The submit always runs from a clock callback, never inside a hook frame. If `$.prompt.submit` resolves `{ drop }` or throws, the claim is released and it retries after 0, 300, 700, 1500, 3000, 6000, 10000 ms, then every 10 s, up to 60 s; the old pane/band shows `STATUS Seed retry k (reason: ...)` and each failure is logged to debug. `done` and state `seeded` are written only after the submit is accepted.

`seedPath` (record and lineage) says which trigger got the seed accepted: `watcher`, `session.start`, `session.end`, `first-turn` (turn.start or prompt.submit), `manual` (command or button). `seedLatencyMs` is clear-requested to accepted. The band reads `✓ handed over #1 · from 8a1f77c0 · seeded in 1.2 s via watcher · brief 66 lines · 0 agents active`, the toast `handed over: seed sent in 1.2 s via watcher (...)`, and the pane STATUS of the new session `..., seeded in 1.2 s via watcher`. `watcher` with about 0.3 s means the hooks were not needed; `first-turn` means the watcher did not see the id change.

## If a handover stalls

Still `clearing` after 45 s shows `stalled`; the watcher keeps running. Wait, press Retry clear, or `/handover reset`. If it did clear but nothing was seeded: `/handover seed`. A retry plus a late original clear can clear twice; the seed goes to the first fresh context only. The mod never clears by itself.

## Use it in this repo

1. Load for one session: `cd /Users/sharmp49/hackathon/code_scanner && claude --plugin-dir ./mods/handover`
2. Every session from this repo: `CLAUDE_CODE_PLUGIN_DIRS` (absolute paths) in the process environment or `~/.claude/settings.json` `env` (never read from project settings).
3. Validate and test (mocked engine only): `claude plugin validate mods/handover`, `claude plugin test mods/handover`.
4. Safe use: open `/handover`, Refresh, Write brief, read the brief. Try Clear and seed in a throwaway session first.
5. NOT tested live: a real `/clear`, when `$.session.id()` changes after it, the real engine's timing, real deliveries, the forward path, plugins above this mod, subagents across a clear (not determined), terminal rendering, narrative quality.
7. Briefs: `~/.claude/state/handover/<session-id>.md`; the Takeover protocol section names `Handover #n in chain` and the previous sessions.
