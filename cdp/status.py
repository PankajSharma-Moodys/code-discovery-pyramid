"""Wave, node and coverage status."""

from __future__ import annotations

from . import freshness as freshness_mod, query as query_mod
from .session import open_store
from typing import Dict


def status(paths: "Paths") -> Dict:
    """Pure computation behind `cmd_status` -- no printing, no locking.

    This is the seam `web/api` reads through indirectly (via its own
    read-only driver, not this function -- see `web/api/store_reader.py`'s
    docstring for why) and the seam `cdp status --json` calls directly.
    Extracted verbatim from the loop that used to be `cmd_status`'s body;
    the text report below is now a formatter over this dict, not a second
    computation of it.
    """
    store = query_mod.Store(open_store(paths))
    sched = store._load("schedule")
    state = store.state
    statuses = state.get("nodes", {})
    head = store.inventory.get("head")

    result: Dict = {
        "run_id": store.manifest.get("run_id", "?"),
        "head": head,
        "coverage": {
            "fraction": state["coverage"]["fraction"],
            "files_complete": state["coverage"]["files_complete"],
            "files_total": state["coverage"]["files_total"],
        },
        "freshness": None,
        "waves": [],
        "tasks": [],
    }

    if head and head != "unpinned" and state.get("claims"):
        # 0.9/3.6: three buckets over live claims, none a subset of the others --
        # "anchored but unreviewed" is what `run --stale-only` (Phase 5) targets.
        buckets = freshness_mod.bucket_counts(state["claims"], paths.repo, head, store=store.backend)
        result["freshness"] = {
            "live": buckets[freshness_mod.LIVE],
            "stale": buckets[freshness_mod.STALE],
            "unreviewed": buckets[freshness_mod.UNREVIEWED],
            "unknown_churn": buckets[freshness_mod.UNKNOWN_CHURN],
        }

    for wave in sched["waves"]:
        done = sum(1 for n in wave["nodes"] if statuses.get(n) == "complete")
        result["waves"].append({
            "wave": wave["wave"],
            "level": wave["level"],
            "done": done,
            "total": len(wave["nodes"]),
            "file_count": wave["file_count"],
            "loc": wave["loc"],
            "nodes": [{"node": n, "status": statuses.get(n, "pending")} for n in wave["nodes"]],
        })

    # M5.2: `cdp run`'s per-run task table -- `snapshot_task`, not `nodes[]`
    # above (that is the patch log's own status; this is the supervisor's
    # dispatch bookkeeping for the run named on the first line).
    run_id = str(store.manifest.get("run_id", "cdp"))
    result["run_id"] = run_id
    rows = store.backend.task_rows(run_id)
    if rows:
        node_of_hash = {s.get("scope_hash"): s["node"] for s in store.partition["scopes"]}
        for row in rows:
            result["tasks"].append({
                "node": node_of_hash.get(row["scope_hash"], row["scope_hash"]),
                "state": row["state"] or "pending",
                "attempts": row["attempts"] or 0,
                "last_error": row["last_error"],
            })

    store.close()
    return result
