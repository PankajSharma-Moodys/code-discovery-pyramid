/**
 * Maps `snapshot_task.state` (`cdp/supervisor.py`'s state machine --
 * `PENDING -> DISPATCHED -> RETURNED -> VALIDATED -> FOLDED`, with retryable
 * failure states `EXPIRED|INVALID|ANCHORS_FAILED|EMPTY` and terminal
 * `ABANDONED`, confirmed against source rather than `WEB_RESEARCH.md` §4's
 * paraphrase) onto the existing epistemic CSS vars (`theme/tokens.css`) --
 * reused as the closest semantic mapping rather than inventing a second
 * color vocabulary for the Control Room.
 */
export type TaskState = string;

const RETRYABLE = new Set(["expired", "invalid", "anchors_failed", "empty"]);
const IN_FLIGHT = new Set(["dispatched", "returned", "validated"]);

export function taskStateColor(state: TaskState): string {
  if (state === "folded") return "var(--atlas-verified)";
  if (state === "abandoned" || RETRYABLE.has(state)) return "var(--atlas-contested)";
  if (IN_FLIGHT.has(state)) return "var(--atlas-inferred)";
  return "var(--atlas-text-dim)"; // pending, or any unrecognized state
}

export function taskStateStroke(state: TaskState): "solid" | "dashed" | "dotted" {
  if (state === "folded") return "solid";
  if (IN_FLIGHT.has(state)) return "dashed";
  return "dotted";
}
