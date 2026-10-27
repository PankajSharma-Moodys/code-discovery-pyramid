# handover (v0.3.0)

`/handover` opens a pane that hands a long-running supervisor session to a fresh context: context-window and usage bars, a table of background agents, an animated Collect state / Write brief / Seed fresh context sequence. Where the pane cannot be placed, a compact band above the prompt is used.

Buttons: Refresh, Write brief (never clears), Clear and seed (refuses during a turn with a "try again when idle" note; needs a second press within 8 s when agents are active), Seed now and Reset (shown when they apply), Close.

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
- `/handover reset` sets the current session back to idle and drops a pending seed (the Reset button asks for a second press).

## If a handover stalls

The seed is sent by the first of: `classic.SessionStart` (source `clear`), the first `turn.start` or `prompt.submit` in the new context, `/handover seed`, Seed now. A plugin above this mod can continue past a hook with `next.to` ("bypassed by <plugin>" in `claude --debug`), which is why SessionStart can be skipped. Each seed is sent once. If the conversation did not clear: wait for the stall countdown, press Retry clear, or use `/handover reset`. If it did clear but nothing was seeded: `/handover seed`. A retry plus a late original clear can clear twice; the seed goes to the first fresh context only.

## Use it in this repo

1. Load for one session: `cd /Users/sharmp49/hackathon/code_scanner && claude --plugin-dir ./mods/handover`
2. Every session from this repo: `CLAUDE_CODE_PLUGIN_DIRS` (absolute paths) in the process environment or `~/.claude/settings.json` `env` (never read from project settings).
3. Validate and test (mocked engine only): `claude plugin validate mods/handover`, `claude plugin test mods/handover`.
4. Safe use: open `/handover`, Refresh, Write brief, read the brief. Try Clear and seed in a throwaway session first.
5. NOT tested live: a real `/clear`, the real behaviour of plugins above this mod, subagents across a clear (not determined), terminal rendering, real narrative quality.
6. Briefs: `~/.claude/state/handover/<session-id>.md`; the Takeover protocol section names `Handover #n in chain` and the previous sessions.
