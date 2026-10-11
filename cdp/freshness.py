"""Phase 3 (0.8, 0.9, 3.6) -- two dates, and what staleness actually means.

**Decision, recorded because the plan's own wording ("dates") suggests
wall-clock timestamps and this repository cannot have those inside anything
that feeds `fold_hash`.** `_run_id` (`cli.py`) already establishes the rule:
*"derived from the commit, not the clock ... a timestamp ... would leak into
every patch and defeat the reproducibility gate."* `manifest.json` is the one
place a real timestamp is allowed, and it is explicitly excluded from the
determinism check (`VOLATILE_FIELDS`) for that reason. A wall-clock
`claim_reviewed_at` inside a claim would sit in `patches/` and `state.json`,
which are neither excluded nor volatile-tolerant, so two scans of the same
commit would diverge. Since this system's own notion of "when" is already
`(repo_id, commit_sha)` (`snapshot.py`), both dates are stored as **commit
shas**: `anchor_verified_at` is the commit at which a claim's anchors were last
confirmed to resolve; `claim_reviewed_at` is the commit at which a model (or,
for structural claims, the deterministic deriver) last affirmed the claim's
evidence. Both are free to compare and fully deterministic per commit.

Staleness is churn in the anchored file *between* `claim_reviewed_at` and the
commit being asked about -- `git log <reviewed>..<head> -- file` -- never
elapsed wall-clock time and never commit count (R8): a claim about a file
untouched for two years is live, not stale.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import TYPE_CHECKING, Dict, Optional, Sequence, Set, Tuple

from .util import run_git

if TYPE_CHECKING:
    from .store import WorkspaceStore

LIVE = "live"
STALE = "stale"
UNREVIEWED = "anchored_unreviewed"
UNKNOWN_CHURN = "unknown_churn"


def file_churned_between(repo: Path, rel_path: str, since_sha: str, head_sha: str) -> Optional[bool]:
    """Whether `rel_path` has real content churn in `(since_sha, head_sha]`.

    `--follow -M100%` plus reading the actual numstat counts, not just whether
    a commit touched the path, is load-bearing: without them a pure rename
    shows up as one commit adding N lines at the new path (git's default
    single-path history simplification does not apply rename detection to its
    own filter), which would report a `git mv` as churn and demote a claim
    that never actually changed. With `--follow -M100%` the same commit's
    numstat line reads `0 0 {old => new}` -- zero churn, matching R9's rename
    exception exactly.

    `None` means the range cannot be walked at all -- `since_sha` fell off a
    shallow clone, or history was rewritten out from under it (rebase /
    force-push). Callers must report that explicitly rather than assume "no
    churn found" means "not stale".
    """
    if since_sha == head_sha:
        return False
    out = run_git(repo, "log", "--follow", "-M100%", "%s..%s" % (since_sha, head_sha),
                   "--numstat", "--format=", "--", rel_path)
    if out is None:
        return None
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split("\t", 2)
        if len(parts) < 2:
            continue
        added, removed = parts[0], parts[1]
        if added == "-" or removed == "-":
            return True  # binary: can't quantify the change, but it is one
        if int(added) or int(removed):
            return True
    return False


ChurnCache = Dict[Tuple[str, str, str], Optional[bool]]


def _resolve_churn(
    repo: Path, rel: str, since_sha: str, head_sha: str,
    cache: ChurnCache, store: Optional["WorkspaceStore"],
) -> Optional[bool]:
    """One `(rel, since_sha, head_sha)` answer, checked in this order: the
    in-process `cache` dict (cheapest, scoped to one `bucket_counts` call),
    then `store`'s persistent `churn_cache` table if the backend has one
    (survives across processes/requests), and only on a miss in both does
    this actually shell out to `git log` -- then writes the answer back to
    both, so the next caller (in this process or another) never re-pays for
    the same commit pair."""
    key = (rel, since_sha, head_sha)
    if key in cache:
        return cache[key]
    if store is not None and store.supports_churn_cache():
        hit, churned = store.churn_lookup(rel, since_sha, head_sha)
        if hit:
            cache[key] = churned
            return churned
    result = file_churned_between(repo, rel, since_sha, head_sha)
    cache[key] = result
    if store is not None and store.supports_churn_cache():
        store.write_churn_cache([(rel, since_sha, head_sha, result)])
    return result


#: "77 files declare ...", "used at 12 call sites": a number counting things. Such a claim
#: describes a whole scope, not the few lines it cites, so any change to the scope can
#: falsify it (C3). Version-like and identifier-like numbers (`Java 17`, `v2`, `404`) do
#: not match: the number must be followed by a plural noun within three words.
_COUNT_CLAIM = re.compile(
    r"(?<![\w.#/:@$-])\d{1,3}(?:,\d{3})*\+?(?![\w.%:/-])\s+(?:[A-Za-z][\w-]*\s+){0,2}[A-Za-z][\w-]*s\b")


def is_count_claim(claim: Dict) -> bool:
    return bool(_COUNT_CLAIM.search(str(claim.get("statement") or "")))


def scope_paths(partition: Optional[Dict]) -> Dict[str, Tuple[Set[str], Set[str]]]:
    """`{scope node: (its files, their directories)}`, from the partition artifact."""
    out: Dict[str, Tuple[Set[str], Set[str]]] = {}
    for scope in (partition or {}).get("scopes", []):
        files = set(scope.get("files") or [])
        out[scope["node"]] = (files, {os.path.dirname(f) for f in files})
    return out


def _changed_paths(repo: Path, since_sha: str, head_sha: str, cache: ChurnCache) -> Optional[Set[str]]:
    key = ("\0changed", since_sha, head_sha)
    if key not in cache:
        out = run_git(repo, "diff", "--name-only", "--no-renames", "-z", "--relative",
                      since_sha, head_sha, "--", ".")
        cache[key] = None if out is None else {p for p in out.split("\0") if p}  # type: ignore[assignment]
    return cache[key]  # type: ignore[return-value]


SCOPE_KEY = "scope:"  # churn-cache rows for "did anything in this scope change" use `scope:<node>` as the path


def _scope_changed(claim: Dict, repo: Path, reviewed_at: str, head_sha: str, cache: ChurnCache,
                   scopes: Dict[str, Tuple[Set[str], Set[str]]], store: Optional["WorkspaceStore"] = None) -> Optional[bool]:
    """Whether any file of the claim's scope (or one removed from its directories) changed since
    the claim was reviewed; None when the history cannot be walked. Answers are kept in the
    churn cache under `scope:<node>`, so a read-only reader (the web status) can use them."""
    owners = claim.get("source_nodes") or ([claim["source_node"]] if claim.get("source_node") else [])
    if reviewed_at == head_sha:
        return False
    verdicts = []
    for node in (n for n in owners if n in scopes):
        key = (SCOPE_KEY + node, reviewed_at, head_sha)
        if key not in cache and store is not None and store.supports_churn_cache():
            hit, cached = store.churn_lookup(*key)
            if hit:
                cache[key] = cached
        if key not in cache:
            changed = _changed_paths(repo, reviewed_at, head_sha, cache)
            files, dirs = scopes[node]
            cache[key] = None if changed is None else any(p in files or os.path.dirname(p) in dirs for p in changed)
            if store is not None and store.supports_churn_cache():
                store.write_churn_cache([(key[0], key[1], key[2], cache[key])])
        verdicts.append(cache[key])
    if any(v for v in verdicts):
        return True
    return None if any(v is None for v in verdicts) else False


def claim_bucket(
    claim: Dict, repo: Path, head_sha: str,
    cache: Optional[ChurnCache] = None, store: Optional["WorkspaceStore"] = None,
    scopes: Optional[Dict[str, Tuple[Set[str], Set[str]]]] = None,
) -> str:
    """LIVE / STALE / UNREVIEWED / UNKNOWN_CHURN for one kept (non-demoted) claim. A claim that
    counts things (`is_count_claim`) is also STALE when any file of its scope changed (C3)."""
    reviewed_at = claim.get("claim_reviewed_at")
    if not reviewed_at:
        return UNREVIEWED
    cache = cache if cache is not None else {}
    churned = False
    unknown = False
    for anchor in claim.get("evidence") or []:
        rel = str(anchor.get("file"))
        result = _resolve_churn(repo, rel, str(reviewed_at), head_sha, cache, store)
        if result is None:
            unknown = True
        elif result:
            churned = True
    if scopes and not churned and is_count_claim(claim):
        result = _scope_changed(claim, repo, str(reviewed_at), head_sha, cache, scopes, store)
        if result is None:
            unknown = True
        elif result:
            churned = True
    if churned:
        return STALE
    if unknown:
        return UNKNOWN_CHURN
    return LIVE


def partition_scopes(store: Optional["WorkspaceStore"]) -> Dict[str, Tuple[Set[str], Set[str]]]:
    """The scope table for `claim_bucket`, read from the selected snapshot ({} if there is none)."""
    if store is None:
        return {}
    try:
        return scope_paths(store.read_artifact("partition", {}))
    except Exception:  # noqa: BLE001 -- staleness must still report without a readable partition
        return {}


def bucket_counts(
    claims: Sequence[Dict], repo: Path, head_sha: str, store: Optional["WorkspaceStore"] = None,
) -> Dict[str, int]:
    cache: ChurnCache = {}
    scopes = partition_scopes(store)
    counts = {LIVE: 0, STALE: 0, UNREVIEWED: 0, UNKNOWN_CHURN: 0}
    for claim in claims:
        counts[claim_bucket(claim, repo, head_sha, cache, store, scopes)] += 1
    return counts
