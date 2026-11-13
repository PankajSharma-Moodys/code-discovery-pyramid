# context-tiers

An experiment in tiered context management for Claude Code. The mod scores every
exchange in the conversation on recency, how often later turns reference it, and
model-given ratings: value, urgency and staleness, reported per turn through the
`rate_context` tool and in a batch fork pass. When the context reaches 200K
tokens, it rewrites the transcript: HOT (newest ~30K and pinned) and WARM
(best-scoring, up to a 90K budget) stay verbatim, COLD exchanges become one-line
summaries that point at a raw archive under `~/.claude/context-tiers/<session>/`.

Commands: `/tiers` status, `/tiers on|off` (active or observe mode; observe is the
default), `/tiers dry` (fork-rate and plan, nothing moved), `/tiers run` (re-tier
now), `/tiers pane`.

## Requirements

- `sqlite3` CLI on `PATH`, version 3.33 or later, built with FTS5. macOS ships
  one at `/usr/bin/sqlite3`; on Linux install the `sqlite3` package. Check with
  `sqlite3 -version`.
- Without it, re-tiering and the markdown archives still work, but search is
  off: no automatic retrieval on prompts, and `search_archive` points the model
  at the archive files instead.
