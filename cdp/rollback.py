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

import re
from typing import Dict, FrozenSet, List, Sequence, Set, Tuple

from .util import CdpError, resolve_prefix

LEDGER_ARTIFACT = "rollback"


def resolve_run_id(value: str, patches=None, commits: Sequence[str] = ()) -> str:
    """A run id in the log names exactly that run. A commit -- a unique prefix (4+ hex digits), the 12
    digits a run id holds, or the full sha -- names its *latest* run, so `patches_up_to_run` gives the
    commit's whole accumulated state: a `-rN` run re-does only the scopes that changed, and the rest
    stay in the earlier run's patches. `commits` (full shas the store scanned), when given, must hold
    a value longer than 12 digits. Junk, an empty value or an ambiguous prefix raises."""
    if not isinstance(value, str) or not value.strip():
        raise CdpError("a run or commit is required: the value is empty")
    value = value.strip()
    if patches is None:
        return value if value.startswith("cdp-") else "cdp-" + value[:12]
    known = {str(p.get("run_id")) for p in patches if p.get("run_id")}
    if value in known:
        return value
    bare = (value[4:] if value.startswith("cdp-") else value).lower()
    if not re.fullmatch(r"[0-9a-f]{4,64}", bare):
        raise CdpError("%r is neither a run id in this store's log nor a commit sha" % value)
    if len(bare) > 12 and commits and not any(str(c).lower().startswith(bare) for c in commits):
        raise CdpError("commit %s is not one this store scanned" % value)
    by_commit: Dict[str, List[str]] = {}
    for r in known:
        if r.startswith("cdp-" + bare[:12]):
            by_commit.setdefault(re.sub(r"-r\d+$", "", r[4:]), []).append(r)
    if not by_commit:
        return "cdp-" + bare[:12]  # the caller reports that it never appears in the log
    runs = by_commit[resolve_prefix(bare[:12], sorted(by_commit), "run/commit")]
    last = {r: max(i for i, p in enumerate(patches) if str(p.get("run_id")) == r) for r in runs}
    return max(runs, key=last.get)


def scanned_commits(backend) -> List[str]:
    """Full commit shas of the store's snapshots (none on a backend that keeps no snapshot history)."""
    return [str(s.get("commit_sha")) for s in getattr(backend, "list_snapshots", list)() if s.get("commit_sha")]


class Exclusions:
    """What a fold leaves out: `(run_ids, lo, hi)` entries. A patch is out when its run is
    named and its patch number falls in the range, so a patch accepted *after* a rollback
    is live even though it carries the same run id (a run id is a commit; it recurs).
    A patch with no number, or a legacy entry with no range, matches on the run alone."""

    def __init__(self, entries=()) -> None:
        self.entries = [(frozenset(r), lo, hi) for r, lo, hi in entries]
        self.run_ids = frozenset().union(*[e[0] for e in self.entries]) if self.entries else frozenset()

    def __bool__(self) -> bool:
        return bool(self.entries)

    def __contains__(self, run_id: str) -> bool:
        return run_id in self.run_ids

    def __eq__(self, other) -> bool:
        return self.run_ids == (other.run_ids if isinstance(other, Exclusions) else other)

    __hash__ = None

    def matches(self, patch: Dict) -> bool:
        if patch.get("author_kind") == "python":
            return False  # the scan's own facts are regenerated, never rolled back
        run, no = str(patch.get("run_id")), patch.get("patch_no")
        return any(run in runs and (no is None or lo is None or lo <= no <= hi)
                   for runs, lo, hi in self.entries)


def as_exclusions(value) -> Exclusions:
    if isinstance(value, Exclusions):
        return value
    return Exclusions([(value, None, None)] if value else [])


def is_excluded(patch: Dict, exclusions) -> bool:
    return as_exclusions(exclusions).matches(patch)


def patch_numbers(patches: Sequence[Dict], run_ids: Set[str]) -> Tuple[int, int]:
    nos = [p["patch_no"] for p in patches if str(p.get("run_id")) in run_ids
           and p.get("patch_no") is not None and p.get("author_kind") != "python"]
    return (min(nos), max(nos)) if nos else (0, 0)


def patches_excluding_run(patches: Sequence[Dict], run_id: str) -> Tuple[List[Dict], Set[str]]:
    """`--to-run`: drop every patch stamped with `run_id`, keep everything else."""
    excluded = {run_id} if any(str(p.get("run_id")) == run_id for p in patches) else set()
    kept = [p for p in patches if str(p.get("run_id")) not in excluded]
    return kept, excluded


def patches_up_to_run(patches: Sequence[Dict], run_id: str, commits: Sequence[str] = ()) -> Tuple[List[Dict], Set[str], bool]:
    """`--to-snapshot` / `--as-of`: keep the log through `run_id`'s last patch.

    `run_id` may appear more than once (a scan's root patch plus every leaf
    `collect` patch from examining the same commit all share one run_id, by
    `_run_id`'s own construction). The cutoff is `cut_index`: the run's last
    leaf patch, so every patch from that run is kept and every later run is
    excluded; the scan's own patch is always kept.

    Returns `(kept, excluded, found)`. `found` distinguishes "this run is
    already the most recent one -- nothing to exclude" (empty `excluded`,
    `found=True`, a legitimate no-op) from "this run never appended anything"
    (empty `excluded`, `found=False`, which callers must reject rather than
    silently returning the whole log unfiltered).
    """
    cut = cut_index(patches, run_id, commits)
    if cut is None:
        return list(patches), set(), False
    kept = list(patches[: cut + 1]) + [p for p in patches[cut + 1:] if _structural(p)]
    excluded = {str(p.get("run_id")) for p in patches[cut + 1:] if not _structural(p)}
    return kept, excluded, True


def _structural(patch: Dict) -> bool:
    """The scan's own patch (slot 0): regenerated for the current tree, never cut or rolled back."""
    return patch.get("author_kind") == "python"


def cut_index(patches: Sequence[Dict], run_id: str, commits: Sequence[str] = ()) -> "int | None":
    """The last log index that belongs to `run_id`'s state, or None if the run never appears.

    The scan's own patch carries the current commit's run id but sits in slot 0, so it never marks where
    a run ends. A run with only that patch (the current commit, no leaf run yet) ends after the leaf
    claims carried from an earlier scanned commit: `carry_leaf_log` copies them, as one block right
    after slot 0, into a snapshot that has no leaf patch of its own. `commits` (full shas the store
    scanned) tells a carried patch from a foreign one; without it the block's position alone does."""
    runs = [(i, str(p.get("run_id")), _structural(p)) for i, p in enumerate(patches)]
    own = [i for i, r, s in runs if r == run_id and not s]
    if own:
        return own[-1]
    if not any(r == run_id for _, r, _ in runs):
        return None
    commit = re.sub(r"-r\d+$", "", run_id)
    scanned = {str(c)[:12] for c in commits}
    cut = -1
    for i, r, s in runs:
        if s:
            cut = i
            continue
        base = re.sub(r"-r\d+$", "", r)
        if base == commit or (scanned and base[4:] not in scanned):
            break  # this commit's own (later) run, or a run of no scanned commit: not carried
        cut = i
    return cut


def _live_indexes(ledger: Dict) -> List[int]:
    """Indexes of the events not undone by a later `undo`."""
    events = list(ledger.get("events", []))
    undone = {e["undoes"] for e in events if e.get("kind") == "undo"}
    return [i for i, e in enumerate(events) if e.get("kind") != "undo" and i not in undone]


def load_excluded_run_ids(store) -> Exclusions:
    """Every rollback event not undone (the name is historical: it returns `Exclusions`)."""
    ledger = store.read_artifact(LEDGER_ARTIFACT, {"events": []})
    events = ledger.get("events", [])
    return Exclusions([(events[i].get("excluded_run_ids", []), *(events[i].get("patch_range") or (None, None)))
                       for i in _live_indexes(ledger)])


def record_rollback(store, kind: str, target_run_id: str, excluded_run_ids: Set[str], reason: str,
                    patch_range=None) -> Dict:
    """Append one rollback event. Never rewrites or removes a prior event (R5's
    same append-only discipline applied to this ledger, not just `patches/`)."""
    ledger = store.read_artifact(LEDGER_ARTIFACT, {"events": []})
    event = {
        "kind": kind,
        "target_run_id": target_run_id,
        "excluded_run_ids": sorted(excluded_run_ids),
        "reason": reason,
    }
    if patch_range:
        event["patch_range"] = list(patch_range)
    ledger = {"events": list(ledger.get("events", [])) + [event]}
    store.write_artifact(LEDGER_ARTIFACT, ledger)
    return event


def undo_last_rollback(store, reason: str = "") -> Dict:
    """Append an `undo` of the latest rollback still in force; its patches are live again."""
    ledger = store.read_artifact(LEDGER_ARTIFACT, {"events": []})
    live = _live_indexes(ledger)
    if not live:
        raise CdpError("no rollback in force to undo")
    index = live[-1]
    target = ledger["events"][index]
    event = {"kind": "undo", "undoes": index, "target_run_id": target.get("target_run_id"),
             "excluded_run_ids": [], "reason": reason or "undo rollback %s" % target.get("target_run_id")}
    store.write_artifact(LEDGER_ARTIFACT, {"events": list(ledger["events"]) + [event]})
    return dict(event, restored_run_ids=list(target.get("excluded_run_ids") or []))  # not in the ledger: derived
