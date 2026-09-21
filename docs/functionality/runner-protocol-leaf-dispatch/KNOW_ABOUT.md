# Know About — Runner Protocol & Leaf Dispatch (`runner.py`, `supervisor.py`, `scripts/claude_leaf_runner.sh`)

- `--allowedTools` on `claude -p` is a permission **pre-approval** list (skip
  the prompt for these), not an allow-*list* — it does not restrict the
  model's toolset. Only `--tools`/`--disallowedTools` actually restrict what's
  available. A leaf runner intended to sandbox a model to Read/Grep/Glob/Write
  must use `--tools`, not `--allowedTools`, or the model can run arbitrary
  Bash.
- Digest mode inlines full file text into the prompt (capped per-file,
  truncation stated in-prompt); it does **not** make anchors digest-relative
  — anchors are still verified by re-opening the real file. Fabrication is
  therefore still only detectable, not structurally prevented, despite that
  being digest mode's stated long-term goal.
- A runner-level failure (non-zero exit, timeout, crash) is `ok=False` at the
  `RunResult` level; classifying *why* a patch is bad (schema violation,
  empty yield, fabricated anchor) is `collect`'s job, never the runner's.
- One `cdp run` process dispatches its wave **sequentially**, not in
  parallel — real per-scope concurrency requires running a *second* `cdp run`
  process on a different scope, made safe only by the lease mechanism.
- Leases are held by the supervisor via a background heartbeat thread (not a
  between-attempts check) — a runner call can block for an unbounded time, so
  only a live heartbeat keeps a long-but-alive dispatch from having its lease
  stolen by another supervisor.
- A crash-and-resume does **not** preserve attempt-count continuity: a scope
  that crashed on attempt 2 of 3 gets a fresh 3-attempt budget on `--resume`,
  not "one more attempt."
- Dispatching a leaf against AI-tool/editor scaffolding directories wastes a
  real model call for zero signal — excluded by `DEFAULT_EXCLUDES` at the
  inventory layer (see Scanning above), not by a runner-side check.
