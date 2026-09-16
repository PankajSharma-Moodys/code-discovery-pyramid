"""Phase 3, M3.7 -- rollback and `--as-of`.

R5 forbids deleting or rewriting a patch once appended. A bad run is therefore
never removed from `patches/`; it is *excluded* by a separate, append-only
ledger (`rollback.json`) naming the run's `run_id`, and `state.fold` treats a
run_id in that ledger as absent from the log without ever touching the patch
file that run_id names. "Marked, never deleted" (`phase_3_plan.md` M3.7) is
this ledger, not a field mutated on the patch itself.

Two operations, both expressed as "the set of run_ids to exclude":

- `--to-run R` excludes exactly the patches from run `R` (a bad run, wherever
  it sits in the log).
- `--to-snapshot S` excludes every run that appended *after* `S`'s run finished
  -- i.e. it walks the log back to how it read right after `S`. Ordering here
  is the log's own append order (`FileStore.load_patches()`'s sorted index
  prefix), because patches deliberately carry no timestamp (D8, `cli.py`
  `_run_id`): a commit sha in the run_id is the only ordering-free identity a
  patch has, and append order is the only "when" a commit-keyed log can offer
  beyond that.

`query --as-of <commit>` reuses the same "up to" cut: replaying the claim log
up to a commit's run against the *current* xref/partition is what makes it
"nearly free" (`phase_3_plan.md`'s own framing). `--as-of <time>` is not
implemented -- patches carry no timestamp by design (D8), so a wall-clock cut
would need one invented for this feature alone, which is the finding the plan
anticipated ("if it is not nearly free, the fold is not as pure as Phase 2
believes").
"""

from __future__ import annotations

from typing import Dict, FrozenSet, List, Sequence, Set, Tuple

from .util import stable_hash

LEDGER_ARTIFACT = "rollback"


def resolve_run_id(value: str) -> str:
    """Accept either a `cdp-<sha12>` run id or a bare commit sha."""
    if value.startswith("cdp-"):
        return value
    return "cdp-" + (value[:12] if value else stable_hash(value)[:12])


def patches_excluding_run(patches: Sequence[Dict], run_id: str) -> Tuple[List[Dict], Set[str]]:
    """`--to-run`: drop every patch stamped with `run_id`, keep everything else."""
    excluded = {run_id} if any(str(p.get("run_id")) == run_id for p in patches) else set()
    kept = [p for p in patches if str(p.get("run_id")) not in excluded]
    return kept, excluded


def patches_up_to_run(patches: Sequence[Dict], run_id: str) -> Tuple[List[Dict], Set[str], bool]:
    """`--to-snapshot` / `--as-of`: keep the log through `run_id`'s last patch.

    `run_id` may appear more than once (a scan's root patch plus every leaf
    `collect` patch from examining the same commit all share one run_id, by
    `_run_id`'s own construction). The cutoff is the *last* index it appears
    at, so every patch from that run is kept and every later run is excluded.

    Returns `(kept, excluded, found)`. `found` distinguishes "this run is
    already the most recent one -- nothing to exclude" (empty `excluded`,
    `found=True`, a legitimate no-op) from "this run never appended anything"
    (empty `excluded`, `found=False`, which callers must reject rather than
    silently returning the whole log unfiltered).
    """
    last = None
    for i, p in enumerate(patches):
        if str(p.get("run_id")) == run_id:
            last = i
    if last is None:
        return list(patches), set(), False
    kept = list(patches[: last + 1])
    excluded = {str(p.get("run_id")) for p in patches[last + 1 :]}
    return kept, excluded, True


def load_excluded_run_ids(store) -> FrozenSet[str]:
    """Union of every rollback event's exclusions ever recorded."""
    ledger = store.read_artifact(LEDGER_ARTIFACT, {"events": []})
    out: Set[str] = set()
    for event in ledger.get("events", []):
        out.update(event.get("excluded_run_ids", []))
    return frozenset(out)


def record_rollback(store, kind: str, target_run_id: str, excluded_run_ids: Set[str], reason: str) -> Dict:
    """Append one rollback event. Never rewrites or removes a prior event (R5's
    same append-only discipline applied to this ledger, not just `patches/`)."""
    ledger = store.read_artifact(LEDGER_ARTIFACT, {"events": []})
    event = {
        "kind": kind,
        "target_run_id": target_run_id,
        "excluded_run_ids": sorted(excluded_run_ids),
        "reason": reason,
    }
    ledger = {"events": list(ledger.get("events", [])) + [event]}
    store.write_artifact(LEDGER_ARTIFACT, ledger)
    return event
