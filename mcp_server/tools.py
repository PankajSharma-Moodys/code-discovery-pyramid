"""The three tools themselves, with no dependency on the `mcp` SDK.

Phase 9 (7.1): `cdp_query` (typed `kind`), `cdp_scan`, `cdp_status`. Kept
importable and testable with zero optional dependencies installed -- `server.py`
is the thin layer that hands these functions to the real MCP `Server`; nothing
here imports `mcp`.

Repo/state-dir resolution reuses `cdp.cli`'s own `_paths`/`_open_store` (same
`.cdp.toml` -> registry -> cwd/.cdp order every CLI command uses, D3), so a
tool answers from the same store a `cdp` invocation in that directory would.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Dict, Optional

from cdp import cli as cdp_cli
from cdp import dataflow as dataflow_mod
from cdp import freshness as freshness_mod
from cdp import partition as partition_mod
from cdp import query as query_mod
from cdp import schedule as schedule_mod


def _paths(repo: str, state_dir: Optional[str] = None):
    args = SimpleNamespace(repo=repo, state_dir=state_dir, in_repo=False)
    return cdp_cli._paths(args)


def _store(repo: str, state_dir: Optional[str] = None) -> "query_mod.Store":
    return query_mod.Store(cdp_cli._open_store(_paths(repo, state_dir)))


def cdp_query(
    repo: str,
    kind: str,
    term: Optional[str] = None,
    *,
    budget: Optional[int] = None,
    claim_kind: Optional[str] = None,
    module: Optional[str] = None,
    subject: Optional[str] = None,
    frm: Optional[str] = None,
    to: Optional[str] = None,
    max_hops: Optional[int] = None,
    as_of: Optional[str] = None,
    state_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """One typed tool, not thirteen (`phase_9_plan.md` 7.1) -- `kind` is the
    same closed vocabulary `query.QUERIES` already enforces for the CLI."""
    if kind not in query_mod.QUERIES:
        raise ValueError("unknown query kind %r -- one of %s" % (kind, sorted(query_mod.QUERIES)))
    store = _store(repo, state_dir)
    try:
        if as_of:
            cdp_cli._apply_as_of(store, as_of)
        return query_mod.dispatch(
            store, kind, term, budget=budget, claim_kind=claim_kind, module=module,
            subject=subject, frm=frm, to=to, max_hops=max_hops,
        )
    finally:
        store.close()


def cdp_scan(
    repo: str,
    *,
    state_dir: Optional[str] = None,
    max_leaf_files: Optional[int] = None,
    max_leaf_loc: Optional[int] = None,
    max_concurrent: Optional[int] = None,
    max_hops: Optional[int] = None,
    workers: Optional[int] = None,
) -> Dict[str, Any]:
    """Runs a real scan through `cli.cmd_scan` (same code path as `cdp scan`,
    not a reimplementation) and returns `query stats`'s result against the
    fresh store -- a scan has no single natural return value of its own, and
    `stats` is what every other command already treats as the answer to
    "what does this store now hold?"."""
    args = SimpleNamespace(
        repo=repo,
        state_dir=state_dir,
        in_repo=False,
        max_leaf_files=max_leaf_files or partition_mod.DEFAULT_MAX_FILES,
        max_leaf_loc=max_leaf_loc or partition_mod.DEFAULT_MAX_LOC,
        max_concurrent=max_concurrent or schedule_mod.DEFAULT_MAX_CONCURRENT,
        max_hops=max_hops or dataflow_mod.DEFAULT_MAX_HOPS,
        workers=workers,
        exclude=None,
        docs=False,
        quiet=True,
    )
    cdp_cli.cmd_scan(args)
    store = _store(repo, state_dir)
    try:
        return query_mod.dispatch(store, "stats")
    finally:
        store.close()


def cdp_status(repo: str, *, state_dir: Optional[str] = None) -> Dict[str, Any]:
    """The dict `cdp status` prints as text, built directly from the same
    fields (`state.json` coverage, freshness buckets, this run's task rows)
    rather than shelling out and parsing that text back."""
    paths = _paths(repo, state_dir)
    store = _store(repo, state_dir)
    try:
        state = store.state
        result: Dict[str, Any] = {
            "run_id": store.manifest.get("run_id"),
            "head": store.inventory.get("head"),
            "coverage": state.get("coverage", {}),
        }
        head = store.inventory.get("head")
        if head and head != "unpinned" and state.get("claims"):
            buckets = freshness_mod.bucket_counts(state["claims"], paths.repo, head)
            result["freshness"] = {
                "live": buckets[freshness_mod.LIVE],
                "stale": buckets[freshness_mod.STALE],
                "anchored_but_unreviewed": buckets[freshness_mod.UNREVIEWED],
                "unknown_churn": buckets[freshness_mod.UNKNOWN_CHURN],
            }
        run_id = str(store.manifest.get("run_id", "cdp"))
        rows = store.backend.task_rows(run_id)
        if rows:
            node_of_hash = {s.get("scope_hash"): s["node"] for s in store.partition["scopes"]}
            result["tasks"] = [
                {
                    "node": node_of_hash.get(row["scope_hash"], row["scope_hash"]),
                    "state": row["state"] or "pending",
                    "attempts": row["attempts"] or 0,
                    "last_error": row["last_error"],
                }
                for row in rows
            ]
        return result
    finally:
        store.close()


TOOLS = {
    "cdp_query": cdp_query,
    "cdp_scan": cdp_scan,
    "cdp_status": cdp_status,
}
