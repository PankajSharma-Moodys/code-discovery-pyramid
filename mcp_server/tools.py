"""The six tools themselves, with no dependency on the `mcp` SDK.

Phase 9 (7.1): `cdp_query` (typed `kind`), `cdp_scan`, `cdp_refresh`, `cdp_status`, `cdp_help`, `cdp_link`. Kept
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

from cdp import pipeline as pipeline_mod
from cdp import session as session_mod
from cdp import dataflow as dataflow_mod
from cdp import freshness as freshness_mod
from cdp import partition as partition_mod
from cdp import query as query_mod
from cdp import schedule as schedule_mod
from cdp.store import registry as registry_mod
from cdp import lock as lock_mod
from cdp import refresh as refresh_mod
from cdp import linkview as linkview_mod
from cdp.util import ArgError, check_enum, check_limit, check_str


def _paths(repo: str):
    """The store is always the machine one (`CDP_HOME`): a tool call cannot point it
    elsewhere, so a model cannot create stores at paths of its choosing."""
    return session_mod.paths_for(check_str(repo, "repo", 4096))  # "" would mean the server's cwd


def _store(repo: str) -> "query_mod.Store":
    return query_mod.Store(session_mod.open_store(_paths(repo)))


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
    exclude_role: Optional[list] = None,
    exact: bool = False,
) -> Dict[str, Any]:
    """One typed tool, not thirteen (`phase_9_plan.md` 7.1) -- `kind` is the
    same closed vocabulary `query.QUERIES` already enforces for the CLI."""
    for arg, value in (("budget", budget), ("max_hops", max_hops)):
        if value is not None:
            check_limit(arg, value)
    for arg, value in (("term", term), ("claim_kind", claim_kind), ("module", module), ("subject", subject),
                       ("frm", frm), ("to", to), ("as_of", as_of), ("repo", repo), ("kind", kind)):
        if value is not None and not isinstance(value, str):
            raise ArgError("%s must be a string, got %s" % (arg, type(value).__name__))
    if exclude_role is not None and (not isinstance(exclude_role, list)
                                     or not all(isinstance(r, str) for r in exclude_role)):
        raise ArgError("exclude_role must be a list of strings")
    if not isinstance(exact, bool):
        raise ArgError("exact must be true or false, got %s" % type(exact).__name__)
    if kind not in query_mod.QUERIES:
        raise ValueError("unknown query kind %r -- one of %s" % (kind, sorted(query_mod.QUERIES)))
    paths, term, routed = _paths(repo), term, None
    if kind == "file":
        paths, term, routed = session_mod.route_path(paths, term)
    store = query_mod.Store(session_mod.open_store(paths))
    try:
        if as_of:
            session_mod.apply_as_of(store, as_of)
        result = query_mod.dispatch(
            store, kind, term, budget=budget, claim_kind=claim_kind, module=module,
            subject=subject, frm=frm, to=to, max_hops=max_hops, exclude_role=exclude_role,
            exact=exact,
        )
        if routed:
            result.setdefault("as_of", {})["routed"] = routed
        return result
    finally:
        store.close()


def _exclusive(repo: str):
    """The per-repo write lock `cdp scan`/`cdp refresh` take, so a tool call and a
    CLI run (or a git hook) never write one store at once."""
    paths = _paths(repo)
    kind, pg = session_mod.resolve_backend(paths.state)
    return lock_mod.repo_lock(paths, kind, pg, shared=False)


def cdp_refresh(repo: str) -> Dict[str, Any]:
    """Bring a stale index up to HEAD: the same code as `cdp refresh` (incremental
    extraction, claims re-verified, zero model calls, the shared snapshot rule picks
    the base). Needs a clean working tree and a prior scan; says so when it cannot."""
    lines = []
    with _exclusive(repo):
        rc = refresh_mod.refresh_repo(_paths(repo), say=lambda *a: lines.append(" ".join(str(x) for x in a)))
    return {"refreshed": rc == 0, "log": lines, "status": cdp_status(repo)}


def cdp_scan(
    repo: str,
    *,
    max_leaf_files: Optional[int] = None,
    max_leaf_loc: Optional[int] = None,
    max_concurrent: Optional[int] = None,
    max_hops: Optional[int] = None,
    workers: Optional[int] = None,
) -> Dict[str, Any]:
    """Runs a real scan through `pipeline.scan` (same code path as `cdp scan`,
    not a reimplementation) and returns `query stats`'s result against the
    fresh store -- a scan has no single natural return value of its own, and
    `stats` is what every other command already treats as the answer to
    "what does this store now hold?"."""
    given = {"max_leaf_files": max_leaf_files, "max_leaf_loc": max_leaf_loc, "max_concurrent": max_concurrent,
             "max_hops": max_hops, "workers": workers}
    for arg, value in given.items():
        if value is not None:
            check_limit(arg, value)  # a 0 must not quietly turn into the default
    with _exclusive(repo):
        pipeline_mod.scan(
            _paths(repo),
            max_leaf_files=partition_mod.DEFAULT_MAX_FILES if max_leaf_files is None else max_leaf_files,
            max_leaf_loc=partition_mod.DEFAULT_MAX_LOC if max_leaf_loc is None else max_leaf_loc,
            max_concurrent=schedule_mod.DEFAULT_MAX_CONCURRENT if max_concurrent is None else max_concurrent,
            max_hops=dataflow_mod.DEFAULT_MAX_HOPS if max_hops is None else max_hops,
            workers=workers,
            docs=False,
        )
    store = _store(repo)
    try:
        return query_mod.dispatch(store, "stats")
    finally:
        store.close()


def cdp_status(repo: str) -> Dict[str, Any]:
    """The dict `cdp status` prints as text, built directly from the same
    fields (`state.json` coverage, freshness buckets, this run's task rows)
    rather than shelling out and parsing that text back."""
    paths = _paths(repo)
    store = _store(repo)
    try:
        state = store.state
        choice = store.choice
        result: Dict[str, Any] = {
            "run_id": store.manifest.get("run_id"),
            "head": store.inventory.get("head"),
            "git_head": choice.head if choice else None,
            "behind": choice.behind if choice else 0,
            "dirty_files": choice.dirty_files if choice else [],
            "snapshot_uncommitted": bool(choice and choice.row and choice.row["ephemeral"]),
            "identity": paths.repo_id,
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


def cdp_link(action: str, service: Optional[str] = None) -> Dict[str, Any]:
    """Cross-repo links across every repo scanned into the machine store: the same matching as
    `cdp link scan` (`cdp/linkview.py`). `scan`/`query` only read; `scan_save` also persists the
    links (the CLI's `link scan --db`). The store is the machine one -- a call cannot point elsewhere."""
    check_enum(action, "action", linkview_mod.ACTIONS)
    if service is not None:
        check_str(service, "service")
    home = registry_mod.cdp_home()
    kind, pg = session_mod.resolve_backend(home)
    scope = SimpleNamespace(state=home, repo_id="links")
    with lock_mod.repo_lock(scope, kind, pg, shared=action != "scan_save", scope="links"):
        return linkview_mod.run(home, action, service)


def cdp_help(topic: Optional[str] = None) -> Dict[str, Any]:
    """The same text as `cdp help <topic>` (one function, `helpdoc.help_text`)."""
    from cdp import helpdoc

    return {"topic": topic or "overview", "text": helpdoc.help_text(topic or None)}


TOOLS = {
    "cdp_query": cdp_query,
    "cdp_refresh": cdp_refresh,
    "cdp_scan": cdp_scan,
    "cdp_status": cdp_status,
    "cdp_help": cdp_help,
    "cdp_link": cdp_link,
}
