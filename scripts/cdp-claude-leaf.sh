#!/usr/bin/env bash
# A `cdp run --runner-cmd` for Claude Code: one headless `cdp-leaf` session per scope.
#
#   python3 .claude/skills/cdp/run.py run --wave-all --parallel 5 --timeout 900 \\
#       --runner-cmd /path/to/cdp-claude-leaf.sh
#
# `cdp run` calls this as `cdp-claude-leaf.sh <prompt-path> <patch-path>`; the patch
# must exist when it exits 0.
#
#   CDP_LEAF_MODEL     model for the leaf (default: sonnet)
#   CDP_LEAF_BUDGET    max USD per scope (default: 2)
#   CDP_LEAF_DRYRUN=1  print the command instead of running it
set -euo pipefail

# The repo's CDP hooks would gate this leaf's own reads; they check this and stand down.
export CDP_LEAF_SESSION=1

prompt="${1:?usage: cdp-claude-leaf.sh <prompt-path> <patch-path>}"
patch="${2:?usage: cdp-claude-leaf.sh <prompt-path> <patch-path>}"
# <work>/patches/inbox/<node>.json -> <work>, the directory the leaf must read and write.
work="$(dirname "$(dirname "$(dirname "$patch")")")"

cmd=(
  claude -p
  --output-format json
  --agent cdp-leaf
  --model "${CDP_LEAF_MODEL:-sonnet}"
  --permission-mode dontAsk
  --allowedTools "Read Grep Glob Write"
  --add-dir "$work"
  --max-budget-usd "${CDP_LEAF_BUDGET:-2}"
  --no-session-persistence
  --
  "Read ${prompt} and follow it. Read only the files it lists. Write your patch to ${patch}."
)

if [ "${CDP_LEAF_DRYRUN:-}" = "1" ]; then
  printf '%q ' "${cmd[@]}"
  echo
  exit 0
fi
# Claude result JSON (cost, duration, tokens) goes beside the patch for cdp run to record.
# Not `exec`ed: the patch check below must run after claude. `cdp run`'s SubprocessRunner starts this
# script in its own process group and kills the whole group on timeout or Ctrl-C, so no claude outlives it.
"${cmd[@]}" > "${patch%.json}.usage"
test -s "$patch" || { echo "cdp-leaf wrote no patch at $patch" >&2; exit 1; }
