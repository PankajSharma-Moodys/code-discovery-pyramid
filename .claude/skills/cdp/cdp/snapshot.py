"""Snapshot identity (Phase 2, M2.4/M2.6 — `PHASE/phase_2_plan.md` 0.6/0.7/2.3).

A snapshot is `(repo_id, commit_sha)`. A clean tree's `commit_sha` is the real
git HEAD; a dirty tree is **allowed**, but its identity is the HEAD plus a hash
of the uncommitted diff, marked `ephemeral` — never citable by a durable claim
(`store.WorkspaceStore.mark_durable`), because nothing else can reproduce that
exact tree.

`repo_id` is `store.registry.repo_identity` (declared id -> normalised origin
remote -> a UUID persisted in `.git/`), never the filesystem path — so two
clones of the same repo resolve to one identity and a moved repo keeps its own.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Set, Tuple

from .store.registry import repo_identity
from .util import run_git, stable_hash


def is_dirty(repo: Path) -> bool:
    """Tracked modifications only, matching `hook.is_dirty`'s reasoning:
    the inventory is built from `git ls-files`, so an untracked file cannot
    make it stale."""
    status = run_git(repo, "status", "--porcelain", "--untracked-files=no")
    return bool(status and status.strip())


def _tree_hash(repo: Path) -> str:
    """A hash of the uncommitted diff, not a real git object — cheap, and only
    ever used to distinguish two dirty scans of the same HEAD from each other."""
    diff = run_git(repo, "diff", "HEAD") or ""
    status = run_git(repo, "status", "--porcelain") or ""
    return stable_hash(diff + "\x00" + status)[:16]


def resolve_snapshot(repo: Path, head: str) -> Tuple[str, str, bool]:
    """`(repo_id, commit_sha, ephemeral)` for a scan of `repo` at `head`.

    `head == "unpinned"` (no git, or `inventory.py`'s walk fallback) is treated
    as ephemeral by construction: there is no commit to re-identify the tree by.
    """
    repo_id = repo_identity(repo)
    if head == "unpinned":
        return repo_id, "unpinned:%s" % _tree_hash(repo), True
    if is_dirty(repo):
        return repo_id, "%s+dirty:%s" % (head, _tree_hash(repo)), True
    return repo_id, head, False


def snapshots_to_keep(snapshots: List[Dict], repo_id: str, head_sha: str, cited_shas: Set[str]) -> Set[int]:
    """M3.6/0.10: a snapshot is kept iff HEAD, pinned, or cited by a live
    claim's `anchor_verified_at`/`claim_reviewed_at` -- one sentence, fully
    determining (`PHASE/phase_3_plan.md`). The plan's own wording names a
    `last_verified` field that does not exist in this schema; `cited_shas` is
    the caller's union of both real freshness fields (D8, `PHASE/FINDINGS.md`),
    since either can be the reason an old snapshot is still load-bearing.
    """
    return {
        s["id"] for s in snapshots
        if s.get("repo_id") == repo_id
        and (s.get("commit_sha") == head_sha or s.get("pinned") or s.get("commit_sha") in cited_shas)
    }
