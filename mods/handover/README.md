# handover (v0.2.0)

`/handover` opens a pane that hands a long-running supervisor session to a fresh context: context-window and usage bars, a table of background agents, an animated Collect state / Write brief / Seed fresh context sequence. Buttons: Refresh, Write brief (writes the brief, never clears), Clear and seed (guarded: refuses during a turn, needs a second press within 8 s when agents are active, once per session), Close. Where the pane cannot be placed, a compact band above the prompt is used.

v0.2: the brief copies HANDOVER.md's State and READY lines, summarises `git status`, adds `Verify before trusting` and `Takeover protocol` sections, and flags hashes and figures a model wrote that are not in the code-written facts. The seed asks the new agent to open with a seven-item takeover receipt. After a clear: a toast and an above-prompt line `✓ handed over · from <id> · brief <N> lines · <K> agents active` until the first user prompt.

## Use it in this repo

1. Load for one session (documented in reference.md; not run live by the author):
   `cd /Users/sharmp49/hackathon/code_scanner && claude --plugin-dir ./mods/handover`
2. Load in every session started from this repo only: no project-level setting was found. reference.md documents `CLAUDE_CODE_PLUGIN_DIRS` (absolute paths) from the process environment or the `env` block of `~/.claude/settings.json`, and says it is never read from a project's settings. Per-repo option (untested): `export CLAUDE_CODE_PLUGIN_DIRS=$PWD/mods/handover` in a shell or direnv file used only in this repo.
3. Validate and test (both run for this version, all tests pass; mocked engine only):
   `claude plugin validate mods/handover`
   `claude plugin test mods/handover`
4. Safe use: open `/handover`, press Refresh, press Write brief, read the brief. Do NOT press Clear and seed in a session you care about. Try the clear in a throwaway session first.
5. NOT tested live: a real `/clear`, subagents across a clear (whether their results reach the fresh context is not determined), real terminal rendering of the pane and band, real model quality of the narrative sections. The tests mock the engine, the model and the file system.
6. Briefs are written to `~/.claude/state/handover/<session-id>.md`.
