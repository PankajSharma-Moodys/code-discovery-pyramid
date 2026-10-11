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

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set, Tuple

from .inventory import DEFAULT_EXCLUDES, _is_excluded
from .store.registry import repo_identity, team_excludes
from .util import run_git, stable_hash


def exclusion_patterns(repo: Path, stored: Sequence[str] = ()) -> Tuple[str, ...]:
    """The path-segment patterns `inventory.build_inventory` drops for a scan of `repo`:
    its built-in list, `.cdp.toml`'s `exclude`, and `stored` (the last scan's `--exclude`,
    kept in the manifest). One list for the census and for every "is the tree dirty?"
    question, so a file the index never reads can never make it stale."""
    return tuple(DEFAULT_EXCLUDES) + tuple(team_excludes(repo)) + tuple(stored)


def _names(repo: Path, rev: str, stored: Sequence[str] = ()) -> List[str]:
    """Files under `repo` that differ from `rev` (staged, unstaged, or deleted), minus
    everything the inventory excludes: the one shared definition of "changed"."""
    out = run_git(repo, "diff", "--name-only", "--no-renames", "-z", "--relative", rev, "--", ".") or ""
    patterns = exclusion_patterns(repo, stored)
    return sorted(p for p in out.split("\0") if p and not _is_excluded(p, patterns))


def is_dirty(repo: Path, stored: Sequence[str] = ()) -> bool:
    """Whether a file the index reads differs from HEAD. Tracked files only: the
    inventory is built from `git ls-files`, so an untracked file cannot make it stale,
    and neither can a sibling module's edit (scoped to `repo`) or an excluded path."""
    return bool(_names(repo, "HEAD", stored))


def _tree_hash(repo: Path, stored: Sequence[str] = ()) -> str:
    """A hash of the uncommitted diff of the indexed files, not a real git object --
    cheap, and only ever used to tell one dirty tree from another."""
    names = _names(repo, "HEAD", stored)
    everything = run_git(repo, "diff", "--name-only", "--no-renames", "-z", "--relative", "HEAD", "--", ".") or ""
    if len(names) == len([p for p in everything.split("\0") if p]):
        return stable_hash(run_git(repo, "diff", "HEAD", "--", ".") or "")[:16]
    diff = "".join(run_git(repo, "diff", "HEAD", "--", *names[i:i + 200]) or "" for i in range(0, len(names), 200))
    return stable_hash(diff)[:16]


def current_sha(repo: Path, head: str, stored: Sequence[str] = ()) -> Tuple[str, bool]:
    """`(commit_sha, ephemeral)`: the identity a scan of `repo`'s tree as it is
    right now would be stored under."""
    if head == "unpinned":
        return "unpinned:%s" % _tree_hash(repo, stored), True
    if is_dirty(repo, stored):
        return "%s+dirty:%s" % (head, _tree_hash(repo, stored)), True
    return head, False


def resolve_snapshot(repo: Path, head: str, stored: Sequence[str] = ()) -> Tuple[str, str, bool]:
    """`(repo_id, commit_sha, ephemeral)` for a scan of `repo` at `head`.

    `head == "unpinned"` (no git, or `inventory.py`'s walk fallback) is treated
    as ephemeral by construction: there is no commit to re-identify the tree by.
    """
    sha, ephemeral = current_sha(repo, head, stored)
    return repo_identity(repo), sha, ephemeral


def _behind(repo: Path, sha: str) -> Optional[int]:
    """Commits HEAD has that `sha` lacks, or None when `sha` is not an ancestor of HEAD
    (another branch, a rebased-away commit, an object a shallow clone never fetched)."""
    out = run_git(repo, "rev-list", "--left-right", "--count", "%s...HEAD" % sha)
    if not out:
        return None
    left, right = out.split()
    return int(right) if int(left) == 0 else None


@dataclass
class Choice:
    """Which snapshot answers for the tree at `repo`, and how it differs from that tree."""

    repo_id: str
    head: Optional[str]
    row: Optional[Dict] = None
    behind: int = 0
    dirty_files: List[str] = field(default_factory=list)
    changed_files: List[str] = field(default_factory=list)
    reason: str = ""

    @property
    def scan_needed(self) -> bool:
        return self.row is None

    @property
    def commit(self) -> Optional[str]:
        """The commit the answer describes (a dirty snapshot's base commit)."""
        return self.row["commit_sha"].split("+dirty:")[0] if self.row else None

    @property
    def exact(self) -> bool:
        return self.row is not None and not self.behind and not self.changed_files

    def as_dict(self) -> Dict:
        return {"behind": self.behind, "dirty_files": self.dirty_files, "changed_files": self.changed_files,
                "head": self.head, "identity": self.repo_id,
                "snapshot_uncommitted": bool(self.row and self.row["ephemeral"])}

    def note(self) -> str:
        """One line for a human when the answer is not for exactly the tree on disk."""
        if self.row is None:
            return "scan needed: %s" % self.reason
        bits = []
        if self.behind:
            bits.append("%d commit(s) behind HEAD %s" % (self.behind, (self.head or "?")[:12]))
        if self.dirty_files:
            bits.append(("includes uncommitted: %s" if self.row["ephemeral"] else "uncommitted: %s")
                        % ", ".join(self.dirty_files[:5])
                        + (" (+%d)" % (len(self.dirty_files) - 5) if len(self.dirty_files) > 5 else ""))
        if self.changed_files and self.behind:
            bits.append("%d file(s) changed since" % len(self.changed_files))
        return ("index is of %s: %s" % ((self.commit or "?")[:12], "; ".join(bits))) if bits else ""


def choose_snapshot(repo: Path, repo_id: str, snapshots: List[Dict], durable: bool = False,
                    stored: Sequence[str] = ()) -> Choice:
    """The one rule for which snapshot answers (query, MCP, hooks, refresh, collect,
    prompts, docs, status all call this):

    1. the snapshot of HEAD whose working-tree state matches the tree on disk;
    2. else the nearest clean ancestor of HEAD (the tree may be dirty over it: `dirty_files`);
    3. never another branch's snapshot, nor a dirty snapshot of a different tree;
    4. else nothing: the caller must say "scan needed".

    `durable` (commands that add claims): only clean snapshots qualify, since a claim
    cannot be anchored to a dirty tree's identity.
    """
    repo = Path(repo)
    mine = [s for s in snapshots if s.get("repo_id") == repo_id and not (durable and s["ephemeral"])]
    head = run_git_head(repo)
    choice = Choice(repo_id=repo_id, head=head)
    have = ", ".join(s["commit_sha"][:12] + ("*" if s["ephemeral"] else "") for s in mine[-6:]) or "none"
    sha, _ = current_sha(repo, head or "unpinned", stored)
    dirty = sha != head
    if head:
        choice.dirty_files = _names(repo, "HEAD", stored) if dirty else []
    exact = next((s for s in mine if s["commit_sha"] == sha), None)
    if exact is not None:
        choice.row = exact
        return choice
    if head is None:
        choice.reason = "no scan of this repo" if not mine else "no git HEAD to match and the tree changed since the last scan (indexed: %s)" % have
        return choice
    best: Optional[Tuple[int, Dict]] = None
    for snap in mine:
        if snap["ephemeral"]:
            continue
        behind = _behind(repo, snap["commit_sha"])
        if behind is not None and (best is None or behind < best[0]):
            best = (behind, snap)
    if best is None:
        choice.reason = ("no snapshot of HEAD %s or of an ancestor of it (indexed: %s)"
                         % (head[:12], have)) if mine else "no scan of this repo"
        return choice
    choice.behind, choice.row = best
    choice.changed_files = _names(repo, choice.row["commit_sha"], stored)
    return choice


def stored_excludes(backend, repo_id: str, snapshots: List[Dict]) -> List[str]:
    """The `--exclude` patterns the latest scan of `repo_id` was given (its manifest)."""
    mine = [s for s in snapshots if s.get("repo_id") == repo_id]
    if not mine:
        return []
    try:
        backend.use_snapshot(repo_id, mine[-1]["commit_sha"])
        return [str(x) for x in (backend.read_artifact("manifest", {}) or {}).get("excludes") or []]
    except Exception:  # noqa: BLE001 -- a store without a manifest just has no stored excludes
        return []


def select(backend, repo: Path, repo_id: str, durable: bool = False) -> Choice:
    """Point `backend`'s reads at `choose_snapshot`'s answer (or at nothing)."""
    snapshots = backend.list_snapshots()
    choice = choose_snapshot(repo, repo_id, snapshots, durable, stored_excludes(backend, repo_id, snapshots))
    if choice.row is not None:
        backend.use_snapshot(repo_id, choice.row["commit_sha"])
    else:
        backend.select_none(repo_id, "%s; run `cdp scan`" % choice.reason, label=str(repo))
    backend.choice = choice
    return choice


def run_git_head(repo: Path) -> Optional[str]:
    out = run_git(repo, "rev-parse", "HEAD")
    return out.strip() if out and out.strip() else None


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
