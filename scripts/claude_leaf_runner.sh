#!/bin/sh
# Runner protocol adapter (cdp/runner.py's docstring): SubprocessRunner appends
# PROMPT_PATH PATCH_PATH to this command's own argv, so `--runner-cmd` must
# name MODEL and REPO up front:
#     scripts/claude_leaf_runner.sh <model> <repo-path>
# A leaf needs the same Read/Grep/Glob/Write access the cdp-leaf agent
# definition grants it (a prompt lists *paths*, not file contents -- the
# model must open them itself); `-p` alone with no tools cannot do the job
# and will fabricate a filesystem it never read (found running this against
# a real target, PHASE/FINDINGS.md).
#
# --tools, not --allowedTools: confirmed live (claude -p, haiku) that
# --allowedTools only pre-approves a tool for the permission prompt, it does
# not remove the tool from the model's toolset -- a leaf given only
# "--allowedTools Read Grep Glob Write" could still invoke Bash (and did:
# `date +%s%N` returned a real, live timestamp, not a fabrication). That
# silently broke this runner's entire safety premise -- "a leaf can only
# read and write, never execute" -- since the milestone this shipped in.
# `--tools` is the flag that actually restricts the available set; with it,
# the same Bash prompt gets "I don't have a Bash tool available."
#
# --add-dir "$(dirname "$ABS_PATCH_PATH")": the patch path is normally
# outside REPO (CDP's default state dir is outside the repo it scans --
# cdp/store/registry.py's own docstring), and --tools' file-boundary check
# confines Write to REPO's cwd unless the patch's directory is explicitly
# added -- confirmed live: the same Write that succeeds inside REPO is
# refused outside it ("outside the allowed working directories") without
# this flag.
#
# --permission-prompts none: `-p` is piped, non-interactive stdin -- any
# action that would otherwise raise a permission prompt (the out-of-REPO
# write above, without --add-dir; or anything acceptEdits itself doesn't
# cover) has no TTY to answer it and would hang until SubprocessRunner's own
# --timeout kills it, which is indistinguishable from a real empty yield
# (the sonnet/opus yield-collapse PHASE/FINDINGS.md's M6.1 entry flagged but
# did not disambiguate). `none` denies it immediately instead, so a blocked
# action surfaces as a fast, visible denial rather than a slow, silent
# timeout.
set -eu
MODEL="$1"
REPO="$2"
PROMPT_PATH="$3"
PATCH_PATH="$4"
HERE="$(cd "$(dirname "$0")" && pwd)"
AGENT_MD="$HERE/../.claude/agents/cdp-leaf.md"
ABS_PATCH_DIR="$(cd "$(dirname "$PATCH_PATH")" && pwd)"
ABS_PATCH_PATH="$ABS_PATCH_DIR/$(basename "$PATCH_PATH")"

{
  cat "$PROMPT_PATH"
  printf '\n\n---\nWrite the patch to exactly this path with the Write tool, and nothing else: %s\n' "$ABS_PATCH_PATH"
} | (cd "$REPO" && claude -p --model "$MODEL" --system-prompt-file "$AGENT_MD" \
      --tools "Read,Grep,Glob,Write" --permission-mode acceptEdits \
      --add-dir "$ABS_PATCH_DIR" --permission-prompts none \
      --output-format text) > /dev/null
