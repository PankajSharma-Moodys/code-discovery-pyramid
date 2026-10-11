"""Re-review cost (C2): a scope whose files changed is not re-read whole. The leaf gets the changed
files and the stale claims of the scope; every claim that is still live is carried forward by CDP.

Staleness stays per file (C1): a claim is stale when a file it cites changed since it was reviewed
(`freshness.claim_bucket`); a claim that counts things is also stale when any file of its scope changed.
A scope with no earlier leaf claims, or whose history cannot be walked, has no plan and is reviewed whole.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set

from . import freshness as freshness_mod, generations
from .util import run_git


class Plan:
    """What a re-review of one scope must cover."""

    def __init__(self, node: str, stale: List[Dict], files: List[str], carry: List[str]) -> None:
        self.node, self.stale, self.files, self.carry = node, stale, files, carry

    @property
    def empty(self) -> bool:
        return not self.stale and not self.files

    def as_prompt(self) -> Dict:
        return {"files": list(self.files), "stale": self.stale, "carried": len(self.carry)}

    def marker(self) -> Dict:
        return {"carry": list(self.carry), "stale": [c.get("id") for c in self.stale], "files": list(self.files)}


def _added_files(repo: Path, since: str, head: str) -> Optional[Set[str]]:
    out = run_git(repo, "diff", "--name-only", "--no-renames", "--diff-filter=A", "-z", "--relative",
                  since, head, "--", ".")
    return None if out is None else {p for p in out.split("\0") if p}


def plan_scope(store, repo: Path, node: str, head: str, cache: Optional[Dict] = None,
               live: Optional[Dict[str, Dict]] = None) -> Optional[Plan]:
    """The `Plan` for `node`, or None when it must be reviewed whole (never reviewed by a leaf, or
    the commit history between the review and `head` cannot be read)."""
    cache = cache if cache is not None else {}
    if live is None:
        live = generations.live_leaf_patches(store.backend.load_patches())
    patch = live.get(node)
    raw = [c for c in (patch or {}).get("claims") or [] if isinstance(c, dict) and c.get("id")]
    if not raw or not head or head == "unpinned":
        return None
    scope = next((s for s in store.partition["scopes"] if s["node"] == node), None)
    if scope is None:
        return None
    scope_files = set(scope["files"])
    in_state = {c["id"]: c for c in store.state.get("claims", []) if c.get("source_node") == node or node in (c.get("source_nodes") or [])}
    scopes = freshness_mod.scope_paths(store.partition)
    stale: List[Dict] = []
    carry: List[str] = []
    changed: Set[str] = set()
    reviewed = []
    for claim in raw:
        shown = in_state.get(claim["id"])
        probe = shown if shown is not None else claim
        bucket = freshness_mod.claim_bucket(probe, repo, head, cache, store=store.backend, scopes=scopes)
        since = probe.get("claim_reviewed_at") or claim.get("claim_reviewed_at")
        if since:
            reviewed.append(str(since))
        if bucket == freshness_mod.UNKNOWN_CHURN:
            return None
        if bucket == freshness_mod.LIVE:
            if shown is not None:
                carry.append(claim["id"])
            continue
        stale.append(probe)
        cited = [str(a.get("file")) for a in probe.get("evidence") or []]
        moved = set()
        if since:
            for rel in cited:
                if freshness_mod._resolve_churn(repo, rel, str(since), head, cache, store.backend):
                    moved.add(rel)
            if freshness_mod.is_count_claim(probe):
                paths = freshness_mod._changed_paths(repo, str(since), head, cache)
                if paths is None:
                    return None
                moved |= paths & scope_files
        changed |= (moved or set(cited)) & scope_files
    cited_before = {str(a.get("file")) for c in raw for a in c.get("evidence") or []}
    for since in sorted(set(reviewed)):  # files added since any review point (shas have no order)
        added = _added_files(repo, since, head)
        if added is None:
            return None
        changed |= (added & scope_files) - cited_before
    return Plan(node, stale, sorted(changed), carry)


def plans_for(store, repo: Path, nodes: Sequence[str]) -> Dict[str, Plan]:
    head = store.inventory.get("head")
    live = generations.live_leaf_patches(store.backend.load_patches())
    cache: Dict = {}
    out = {}
    for node in nodes:
        plan = plan_scope(store, repo, node, head, cache, live)
        if plan is not None:
            out[node] = plan
    return out


def carry_forward(patch: Dict, node: str, carry: Sequence[str], log: Sequence[Dict]) -> int:
    """Add to `patch` the still-live claims of the node's latest accepted patch named in `carry`
    (unchanged, with their original review stamp). Returns how many were added."""
    live = generations.live_leaf_patches(log).get(node)
    have = {c.get("id") for c in patch.get("claims") or []}
    added = [dict(c) for c in (live or {}).get("claims") or [] if c.get("id") in set(carry) and c.get("id") not in have]
    patch["claims"] = list(patch.get("claims") or []) + added
    return len(added)
