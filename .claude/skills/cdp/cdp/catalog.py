"""What the machine store holds: every repo, and each repo's snapshots.

The repo picker, `link scan` with no arguments and the hook all start from the
same question -- "which repos has this machine scanned?" -- and the answer
lives in one place, `CDP_HOME/index.db`. Plain functions, no argv, no printing.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List

from .store import SqliteStore, has_scanned


def list_repos(home: Path) -> List[Dict]:
    """`[{repo_id, latest, snapshots: [{commit_sha, created_at, ephemeral,
    pinned}]}]`, one row per repo sorted by identity; `latest` is the commit
    scanned most recently. Empty if nothing was ever scanned under `home`.
    Opens the store read-only: listing never creates or migrates anything."""
    home = Path(home)
    if not has_scanned(home):
        return []
    store = SqliteStore(home / "index.db", readonly=True, busy_timeout_ms=5000)
    try:
        latest = {row["repo_id"]: row["commit_sha"] for row in store.latest_snapshots()}
        by_repo: Dict[str, List[Dict]] = {}
        for snap in store.list_snapshots():
            if not snap["repo_id"]:
                continue  # the empty placeholder row a store starts with
            by_repo.setdefault(snap["repo_id"], []).append({
                "commit_sha": snap["commit_sha"], "created_at": snap["created_at"],
                "ephemeral": snap["ephemeral"], "pinned": snap["pinned"],
            })
    finally:
        store.close()
    return [{"repo_id": rid, "latest": latest.get(rid), "snapshots": snaps}
            for rid, snaps in sorted(by_repo.items())]
