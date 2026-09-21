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

from pathlib import Path
from typing import TYPE_CHECKING, Dict, Optional, Sequence, Tuple

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


def claim_bucket(
    claim: Dict, repo: Path, head_sha: str,
    cache: Optional[ChurnCache] = None, store: Optional["WorkspaceStore"] = None,
) -> str:
    """LIVE / STALE / UNREVIEWED / UNKNOWN_CHURN for one kept (non-demoted) claim."""
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
    if churned:
        return STALE
    if unknown:
        return UNKNOWN_CHURN
    return LIVE


def bucket_counts(
    claims: Sequence[Dict], repo: Path, head_sha: str, store: Optional["WorkspaceStore"] = None,
) -> Dict[str, int]:
    cache: ChurnCache = {}
    counts = {LIVE: 0, STALE: 0, UNREVIEWED: 0, UNKNOWN_CHURN: 0}
    for claim in claims:
        counts[claim_bucket(claim, repo, head_sha, cache, store)] += 1
    return counts
