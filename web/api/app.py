"""FastAPI app -- Phase 0 spine (`PLAN.md`) plus this cycle's read-only
backend API layer.

`GET /api/status` (Phase 0), `/api/query` + `/api/trace` (thin wrappers over
`cdp.query.dispatch`), `/api/graph` (L0/L1/L2/L3 -- there is no L4 altitude
in the module/scope graph; the L4 module-link constellation is a separate
concept, served unfiltered by `/api/links` below and rendered by its own
standalone frontend canvas, not a drill-down level of this endpoint),
`/api/node/{id}` (node-ID resolution via `web/api/nodeid.py`), `/api/source`
(repo-tree file reads, path-traversal confined), `/api/repos` (registry
listing + freshness), and the read wrappers `/api/doctor`, `/api/link`,
`/api/links` (all persisted intra-repo link edges, unfiltered -- backs the
module-link constellation view), `/api/trajectory`, `/api/diff`,
`/api/snapshots` (scanned-commit timeline -- backs the time scrubber). No
mutation endpoints yet -- those need the single-flight semantics
`WEB_RESEARCH.md` §7.2.4 still leaves open.

Handlers are `def`, not `async def` (§6.1.1): everything below touches
`sqlite3` or `subprocess`, both blocking, so Starlette runs them in the
threadpool.
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
import time
import tomllib
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from sse_starlette.sse import EventSourceResponse
from starlette.middleware.gzip import GZipMiddleware

from cdp import diffs as diffs_mod
from cdp import freshness as freshness_mod
from cdp import link as link_mod
from cdp import query as query_mod
from cdp import util as cdp_util
from cdp.store import registry as registry_mod

from . import encoding
from . import hookup as hookup_mod
from . import jobs as jobs_mod
from . import nodeid
from .auth import require_mutation_auth
from .models import (
    ConfidenceResponse,
    DiffResponse,
    DoctorResponse,
    GraphResponse,
    InstallPreviewResponse,
    InstallResultResponse,
    JobResponse,
    JobStatusResponse,
    LinkQueryResponse,
    LinksResponse,
    McpToolsResponse,
    NodeResponse,
    ReposResponse,
    RepoInfoResponse,
    SearchResponse,
    SearchResultResponse,
    SnapshotsResponse,
    SourceResponse,
    SourcesResponse,
    StatusResponse,
    TrajectoryResponse,
)
from .query_store import ReadOnlyWorkspaceStore
from .store_reader import ReadOnlyConnection, StoreLocked, StoreUnavailable, resolve_state_dir
from .trajectory_reader import ReadOnlyTrajectoryConnection, TrajectoryLocked, TrajectoryUnavailable

app = FastAPI(title="cdp web api")

#: No compression/timing middleware existed at all before this pass
#: (`WEB_REDESIGN_RESEARCH.md` §5 items 2/3) -- `minimum_size` keeps small
#: JSON (`/api/status`, single-node `/api/node`) uncompressed, since gzip
#: overhead loses on tiny payloads; the multi-MB `/api/graph` L2 responses
#: this doc measured are exactly what it's for.
app.add_middleware(GZipMiddleware, minimum_size=1024)


@app.middleware("http")
async def _add_server_timing(request: Request, call_next):
    """`Server-Timing` response header -- §5/§7's "instrument first, fix
    second" gate, made permanent instead of the earlier one-off Playwright
    longtask probe. No logging framework exists in this service; a header is
    the least additive way to make request latency inspectable (devtools'
    Network panel surfaces `Server-Timing` natively) without introducing one."""
    start = time.perf_counter()
    response = await call_next(request)
    duration_ms = (time.perf_counter() - start) * 1000
    response.headers["Server-Timing"] = "total;dur=%.1f" % duration_ms
    return response


def _open_query_store(repo: Path, state_dir: Optional[str]) -> query_mod.Store:
    """Resolve `repo`/`state_dir` to a manifest-pinned, read-only
    `cdp.query.Store` -- the shared open used by `/api/query` and
    `/api/trace`. Raises `StoreUnavailable`/`StoreLocked`, same as
    `_build_status`; callers translate those to 404/503."""
    resolved_state_dir = resolve_state_dir(repo, state_dir)
    db_path = resolved_state_dir / "index.db"
    conn = ReadOnlyConnection(db_path)
    snapshot_id = conn.latest_pinned_snapshot()
    adapter = ReadOnlyWorkspaceStore(conn, snapshot_id)
    return query_mod.Store(adapter, use_latest=False)


def _bucket_counts_cache_only(conn: ReadOnlyConnection, claims: list, head: str) -> dict:
    """Same LIVE/STALE/UNREVIEWED/UNKNOWN_CHURN bucketing as
    `freshness.bucket_counts`, but reading `churn_cache` only
    (`ReadOnlyConnection.churn_lookup`) -- a request handler must never shell
    out to `git log` per-anchor on every `/api/status` poll. A cache miss
    buckets as `unknown_churn` rather than blocking on a `git log` subprocess;
    `cdp scan`/`refresh`/`status` (`cdp/cli.py`) are what populate the cache,
    via `freshness.bucket_counts(..., store=backend)`."""
    counts = {
        freshness_mod.LIVE: 0, freshness_mod.STALE: 0,
        freshness_mod.UNREVIEWED: 0, freshness_mod.UNKNOWN_CHURN: 0,
    }
    for claim in claims:
        reviewed_at = claim.get("claim_reviewed_at")
        if not reviewed_at:
            counts[freshness_mod.UNREVIEWED] += 1
            continue
        churned = False
        unknown = False
        for anchor in claim.get("evidence") or []:
            rel = str(anchor.get("file"))
            hit, result = conn.churn_lookup(rel, str(reviewed_at), head)
            if not hit or result is None:
                unknown = True
            elif result:
                churned = True
        if churned:
            counts[freshness_mod.STALE] += 1
        elif unknown:
            counts[freshness_mod.UNKNOWN_CHURN] += 1
        else:
            counts[freshness_mod.LIVE] += 1
    return counts


def _build_status(repo: Path, state_dir: Optional[str]) -> dict:
    resolved_state_dir = resolve_state_dir(repo, state_dir)
    db_path = resolved_state_dir / "index.db"
    conn = ReadOnlyConnection(db_path)
    snapshot_id = conn.latest_pinned_snapshot()

    manifest = conn.read_artifact(snapshot_id, "manifest", default={})
    inventory = conn.read_artifact(snapshot_id, "inventory")
    schedule = conn.read_artifact(snapshot_id, "schedule")
    partition = conn.read_artifact(snapshot_id, "partition")
    state = conn.read_artifact(
        snapshot_id, "state", default={"claims": [], "nodes": {}, "coverage": {
            "fraction": 0.0, "files_complete": 0, "files_total": 0,
        }},
    )

    run_id = str(manifest.get("run_id", "cdp"))
    head = inventory.get("head")
    statuses = state.get("nodes", {})

    result: dict = {
        "run_id": run_id,
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
        buckets = _bucket_counts_cache_only(conn, state["claims"], head)
        result["freshness"] = {
            "live": buckets[freshness_mod.LIVE],
            "stale": buckets[freshness_mod.STALE],
            "unreviewed": buckets[freshness_mod.UNREVIEWED],
            "unknown_churn": buckets[freshness_mod.UNKNOWN_CHURN],
        }

    for wave in schedule["waves"]:
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

    rows = conn.task_rows(run_id)
    if rows:
        node_of_hash = {s.get("scope_hash"): s["node"] for s in partition["scopes"]}
        for row in rows:
            result["tasks"].append({
                "node": node_of_hash.get(row["scope_hash"], row["scope_hash"]),
                "state": row["state"] or "pending",
                "attempts": row["attempts"] or 0,
                "last_error": row["last_error"],
            })

    return result


@app.get("/api/status", response_model=StatusResponse)
def get_status(
    repo: str = Query(".", description="repo path to resolve state for"),
    state_dir: Optional[str] = Query(None, alias="state_dir"),
) -> StatusResponse:
    try:
        result = _build_status(Path(repo), state_dir)
    except StoreUnavailable as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except StoreLocked as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return StatusResponse(**result)


@app.get("/api/query")
def get_query(
    kind: str = Query(..., description="one of cdp.query.QUERIES"),
    term: Optional[str] = Query(None),
    budget: Optional[int] = Query(None),
    claim_kind: Optional[str] = Query(None),
    module: Optional[str] = Query(None),
    subject: Optional[str] = Query(None),
    frm: Optional[str] = Query(None, alias="from"),
    to: Optional[str] = Query(None),
    max_hops: Optional[int] = Query(None, alias="max-hops"),
    exclude_role: Optional[List[str]] = Query(
        None, description="drop rows whose file role matches (repeatable) -- mirrors `cdp query --exclude-role`"
    ),
    repo: str = Query(".", description="repo path to resolve state for"),
    state_dir: Optional[str] = Query(None, alias="state_dir"),
) -> dict:
    """Thin wrapper over `cdp.query.dispatch` -- the query layer is never
    reimplemented (`WEB_RESEARCH.md` §7.0/§7.2.1). Response shape varies by
    `kind` (each `QUERIES[kind]` returns its own dict), so there is
    deliberately no fixed `response_model` here -- same posture as
    `cdp query --json`, which prints this same raw dict."""
    if kind not in query_mod.QUERIES:
        raise HTTPException(
            status_code=400,
            detail="unknown kind %r -- one of %s" % (kind, sorted(query_mod.QUERIES)),
        )
    try:
        store = _open_query_store(Path(repo), state_dir)
    except StoreUnavailable as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except StoreLocked as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    try:
        return query_mod.dispatch(
            store, kind, term,
            budget=budget, claim_kind=claim_kind, module=module,
            subject=subject, frm=frm, to=to, max_hops=max_hops,
            exclude_role=exclude_role,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/search", response_model=SearchResponse)
def get_search(
    q: str = Query(..., min_length=2, description="search term, matched against symbol fqns and file paths"),
    limit: int = Query(20, ge=1, le=100),
    repo: str = Query(".", description="repo path to resolve state for"),
    state_dir: Optional[str] = Query(None, alias="state_dir"),
) -> SearchResponse:
    """`WEB_REDESIGN_RESEARCH.md` §4's server-side search-to-focus, replacing
    the ask-bar's client-side substring filter over a full L0 fetch
    (`useSymbolTypeahead`, 6.8MB on `unified-store`). Not a new search
    algorithm -- `cdp.query.q_search` (`kind="search"`, already reachable via
    `/api/query`) already matches symbols/files/claims/unknowns with
    budget-based elision; this is a thin, UI-shaped reformatting of just its
    `symbols`/`files` buckets (`claims`/`unknowns` aren't graph-focusable, so
    dropped here) into one flat, rank-preserved list the ask-bar's typeahead
    can render directly."""
    try:
        store = _open_query_store(Path(repo), state_dir)
    except StoreUnavailable as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except StoreLocked as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    # `q_search`'s `Budget` is a single row allowance spent in construction
    # order across claims, symbols, unknowns, files (`Budget.take`) -- passing
    # the UI's own `limit` (e.g. 20) straight through as that budget let
    # `claims` alone (graph-unfocusable and dropped below anyway) exhaust it
    # before `symbols`/`files` ever got a turn: empirically, `q=app` against
    # this repo's own index has 26 matching claims and returned 0 results
    # end-to-end despite 80 matching symbols existing. Use `q_search`'s own
    # default row budget (200) for the underlying query and apply `limit`
    # only to the flattened symbol+file list this endpoint actually returns.
    result = query_mod.dispatch(store, "search", q)
    results = [
        SearchResultResponse(id=fqn, label=encoding.short_label(fqn), kind="symbol")
        for fqn in result.get("symbols", [])
    ] + [
        SearchResultResponse(id=path, label=path, kind="file")
        for path in result.get("files", [])
    ]
    results = results[:limit]
    return SearchResponse(count=len(results), results=results)


@app.get("/api/trace")
def get_trace(
    entry: Optional[str] = Query(None, description="dataflow entry point"),
    frm: Optional[str] = Query(None, alias="from"),
    to: Optional[str] = Query(None),
    max_hops: Optional[int] = Query(None, alias="max-hops"),
    repo: str = Query(".", description="repo path to resolve state for"),
    state_dir: Optional[str] = Query(None, alias="state_dir"),
) -> dict:
    """`WEB_RESEARCH.md` §7.1's literal `/api/trace?from=&to=&max-hops=`
    surface, as a convenience alias over `/api/query` rather than a second
    dispatch path: `entry` maps to `kind=trace`, `frm`/`to` (without `entry`)
    maps to `kind=paths` -- the two query kinds the Atlas path-trace feature
    (`WEB_RESEARCH.md` §3, "this single feature is the demo") needs."""
    if entry:
        kind, term = "trace", entry
    elif frm or to:
        kind, term = "paths", None
    else:
        raise HTTPException(
            status_code=400,
            detail="/api/trace needs either `entry` or `from`/`to`",
        )
    return get_query(
        kind=kind, term=term, budget=None, claim_kind=None, module=None,
        subject=None, frm=frm, to=to, max_hops=max_hops,
        exclude_role=None, repo=repo, state_dir=state_dir,
    )


@app.get("/api/sources", response_model=SourcesResponse)
def get_sources(
    repo: str = Query(".", description="repo path to resolve state for"),
    state_dir: Optional[str] = Query(None, alias="state_dir"),
) -> SourcesResponse:
    """`dataflow.sources[]` listing -- there is no `kind=sources` in
    `cdp.query.QUERIES` (`trace`/`paths` consume sources internally via
    `_resolve_entry`, but nothing lists them for a picker). Same posture as
    `get_link`/`get_doctor`: read the artifact directly rather than invent
    a query-dispatch kind for a plain listing."""
    try:
        store = _open_query_store(Path(repo), state_dir)
    except StoreUnavailable as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except StoreLocked as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    sources = store.dataflow.get("sources", [])
    return SourcesResponse(count=len(sources), sources=sources)


_SOURCE_CTX_MAX = 500


@app.get("/api/source", response_model=SourceResponse)
def get_source(
    repo: str = Query(".", description="repo root to confine reads to"),
    file: str = Query(..., description="path, repo-relative POSIX string"),
    line: Optional[int] = Query(None, description="1-indexed line to center on"),
    ctx: int = Query(20, description="lines of context around `line` (clamped)"),
) -> SourceResponse:
    """Reads the repo working tree directly -- not the CDP store/index.db
    (`WEB_RESEARCH.md` §7.1: net-new capability, no other endpoint serves raw
    file bytes). `file` is attacker-controllable input from a browser, so
    this is a new trust boundary: containment is checked via `resolve()` +
    `is_relative_to()` *before* any file I/O, never via a caught exception
    after an attempted open. A 400 (not 403) is used for escapes, so the
    response doesn't distinguish "outside the root" from "doesn't exist" and
    can't be used to probe the filesystem.
    """
    ctx = max(0, min(ctx, _SOURCE_CTX_MAX))
    repo_root = Path(repo).expanduser().resolve()
    candidate = (repo_root / file).resolve()
    try:
        is_contained = candidate.is_relative_to(repo_root)
    except AttributeError:  # pragma: no cover -- py<3.9 fallback (requires-python >=3.9)
        import os
        is_contained = os.path.commonpath([str(candidate), str(repo_root)]) == str(repo_root)
    if not is_contained:
        raise HTTPException(status_code=400, detail="`file` escapes `repo`")

    if not candidate.is_file():
        raise HTTPException(status_code=404, detail="file not found")

    try:
        text = candidate.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=422, detail="not a text file") from exc

    all_lines = text.splitlines()
    total_lines = len(all_lines)

    if line is None:
        # Choice: no `line` given -> return the file's head, `ctx*2` lines
        # (documented here since the plan left this ambiguous by design).
        start_line = 1
        end_line = min(total_lines, ctx * 2)
    else:
        start_line = max(1, line - ctx)
        end_line = min(total_lines, line + ctx)

    selected = all_lines[start_line - 1:end_line] if total_lines else []

    return SourceResponse(
        path=file,
        start_line=start_line if total_lines else 0,
        end_line=end_line if total_lines else 0,
        total_lines=total_lines,
        lines=selected,
    )


def _parse_grouped_level(level: str) -> Optional[int]:
    """`"L3"` -> 1, `"P{n}"` -> n, else `None` (not a grouped-rollup level --
    `L0`/`L1`/`L2` are handled separately, they aren't path-depth rollups)."""
    if level == "L3":
        return 1
    if level.startswith("P") and level[1:].isdigit():
        return int(level[1:])
    return None


def _graph_rungs(file_of: "Dict[str, Optional[str]]") -> List[dict]:
    """The full altitude ladder for this repo, computed from the same
    node -> owning-file map already resolved for the response (
    `WEB_REDESIGN_RESEARCH.md` §3.1) -- always consistent with whatever
    `level` was actually served this request, never a stale static list.
    Depth 1 (`"L3"`) is always present; a repo with no real path
    substructure reports exactly `["L3", "L2"]`, matching today's ladder."""
    resolved = {raw_id: path for raw_id, path in file_of.items() if path}
    rungs = [
        {"level": "L3" if d == 1 else "P%d" % d, "depth": d, "label": "Packages" if d == 1 else "Depth %d" % d}
        for d in encoding.real_container_depths(resolved)
    ]
    rungs.append({"level": "L2", "depth": None, "label": "Modules"})
    return rungs


def _role_index(conn: ReadOnlyConnection, snapshot_id: int) -> Dict[str, str]:
    """`path -> role`, off the `inventory` artifact -- the web-connection
    equivalent of `cdp.query._role_index(store)`, which reads the same
    `store.inventory["files"]` off a `Store` rather than a `ReadOnlyConnection`."""
    inventory = conn.read_artifact(snapshot_id, "inventory", default={"files": []})
    return {f["path"]: f["role"] for f in inventory.get("files", []) or []}


def _drop_roles(nodes: list, edges: list, hide_roles: "set[str]") -> "tuple[list, list]":
    """Drops every node whose `role` matches `hide_roles`, and any edge
    touching a dropped node -- the server-side escape hatch for graphs too
    big to filter client-side. A node with `role=None` (no single backing
    file -- a synthetic L3 super-node or a `type:`-prefixed L2 node) is never
    dropped: `hide_roles` names roles to hide, not "everything unresolved"."""
    keep_ids = {n["id"] for n in nodes if n.get("role") not in hide_roles}
    nodes = [n for n in nodes if n["id"] in keep_ids]
    edges = [e for e in edges if e["source"] in keep_ids and e["target"] in keep_ids]
    return nodes, edges


class UnsupportedGraphLevel(Exception):
    """`level` is a recognised altitude (`WEB_RESEARCH.md` §3) this cycle's
    plan explicitly excludes (L0/L1/L4), or an unrecognised string. The route
    turns this into a 501 naming the levels that *do* exist, rather than a
    silently-empty 200 graph that would read as a bug."""


def _graph_node_from_scope(scope: dict) -> dict:
    return {
        "id": scope["node"],
        "label": scope.get("module", scope["node"]),
        "level": None,
        "file_count": scope.get("file_count"),
        "by_role": scope.get("by_role"),
        "by_language": scope.get("by_language"),
        "oversized": scope.get("oversized"),
    }


def _build_graph_l0(conn: ReadOnlyConnection, snapshot_id: int, scope: Optional[str]) -> dict:
    """Symbols (`xref.symbols`, keyed by fqn) as nodes, `dataflow.edges` as
    edges -- the finest altitude, one node per function/route/table rather
    than per module. `scope=` filters to symbols whose `modules` list
    contains it (a symbol can appear in more than one module via re-export)."""
    xref = conn.read_artifact(snapshot_id, "xref", default={"symbols": {}})
    dataflow = conn.read_artifact(snapshot_id, "dataflow", default={"edges": []})
    symbols: dict = xref.get("symbols", {}) or {}

    if scope is not None:
        symbols = {fqn: s for fqn, s in symbols.items() if scope in (s.get("modules") or [])}

    nodes = [
        {
            "id": fqn,
            "label": fqn,
            "level": None,
            "file_count": None,
            "by_role": {"kind": s.get("kind"), "visibility": s.get("visibility")},
            "by_language": None,
            "oversized": None,
        }
        for fqn, s in symbols.items()
    ]

    # Only edges whose *both* endpoints are symbols in this node set. The old
    # code emitted every `dataflow` edge here, but those name modules, not
    # symbols -- 369 of 371 dangled and the canvas rendered a star-field of
    # isolated dots (`ATLAS_REDESIGN.md` §1). Keeping the dangling ones out is
    # the "symbol-scoped edges only" option from §2's table: fewer edges, but
    # every one of them draws.
    edges = []
    for edge in dataflow.get("edges", []) or []:
        src, tgt = edge.get("source"), edge.get("target")
        if src not in symbols or tgt not in symbols:
            continue
        edges.append({
            "source": src, "target": tgt,
            "kind": edge.get("channel", "flow"), "weight": None,
            "confidence": edge.get("confidence"), "count": 1,
        })

    return {
        "level": "L0",
        "scope": scope,
        "nodes": nodes,
        "edges": edges,
        "levels": [],
        "cycles": [],
        "divergence": None,
    }


def _build_graph_l1(conn: ReadOnlyConnection, snapshot_id: int, scope: Optional[str]) -> dict:
    """Files as nodes (`partition.scopes[].files`, plain path strings), edges
    from `extract.imports[]` resolved to a target file via
    `xref.symbols[fqn].sites[0].file` (an import row only carries the
    imported fqn, not its file). `scope=` filters to one scope's own files."""
    partition = conn.read_artifact(snapshot_id, "partition")
    extract = conn.read_artifact(snapshot_id, "extract", default={"imports": []})
    xref = conn.read_artifact(snapshot_id, "xref", default={"symbols": {}})
    symbols: dict = xref.get("symbols", {}) or {}
    roles = _role_index(conn, snapshot_id)

    scopes = partition.get("scopes", [])
    if scope is not None:
        scopes = [s for s in scopes if s["node"] == scope]
    files = {f for s in scopes for f in s.get("files", [])}

    nodes = [{"id": f, "label": f, "level": None, "role": roles.get(f)} for f in sorted(files)]

    edges = []
    for imp in extract.get("imports", []) or []:
        src_file = imp.get("file")
        sym = symbols.get(imp.get("fqn"))
        if not sym or not sym.get("sites"):
            continue
        tgt_file = sym["sites"][0].get("file")
        if not tgt_file or tgt_file == src_file:
            continue
        if scope is not None and src_file not in files and tgt_file not in files:
            continue
        edges.append({"source": src_file, "target": tgt_file, "kind": "import", "weight": None})
        if src_file not in files:
            nodes.append({"id": src_file, "label": src_file, "level": None, "role": roles.get(src_file)})
            files.add(src_file)
        if tgt_file not in files:
            nodes.append({"id": tgt_file, "label": tgt_file, "level": None, "role": roles.get(tgt_file)})
            files.add(tgt_file)

    return {
        "level": "L1",
        "scope": scope,
        "nodes": nodes,
        "edges": edges,
        "levels": [],
        "cycles": [],
        "divergence": None,
    }


def _build_graph_grouped(conn: ReadOnlyConnection, snapshot_id: int, depth: int, scope: Optional[str]) -> dict:
    """Packages, and every rung above them: `ATLAS_REDESIGN.md` §2's L3 was
    the *same* typed `dataflow` graph L2 serves, rolled up so every node is
    either a code package (first path segment of a module/symbol id) or a
    type bucket for the node kinds that have no package of their own
    (`Tables`, `Routes`, `Processes`, ...). `depth=1` is exactly that L3
    rollup; `depth>1` is `MONOREPO_HIERARCHY.md`'s generalization -- the same
    rollup at a deeper path prefix, for repos whose directory structure has a
    real fork past the first segment. Buckets ignore `depth` entirely
    (`encoding.package_of`), so they render identically at every rung.

    Rolling up the typed graph rather than `graph.modules`/`graph.levels` is
    the whole point of the redesign: the old builder paired 7 module nodes
    with 2 edges because `graph.declared`/`observed` barely populate on this
    corpus, while `dataflow.edges` is dense and fully typed. The `graph`
    artifact's `levels`/`cycles`/`divergence` are still passed through --
    they are about modules, which remain a subset of this graph's nodes."""
    graph_art = conn.read_artifact(snapshot_id, "graph", default={})
    base = _dataflow_graph(conn, snapshot_id)
    base_nodes, base_edges = base["nodes"], base["edges"]
    if scope is not None:
        base_nodes, base_edges = _restrict_dataflow_to_scope(base_nodes, base_edges, scope)

    file_of = {node["id"]: node.get("file") for node in base_nodes}
    group_of = {node["id"]: encoding.container_group(node["id"], depth, file_of) for node in base_nodes}
    role_of = {node["id"]: node.get("role") for node in base_nodes}

    members: dict = {}
    for raw_id, group in group_of.items():
        members.setdefault(group, []).append(raw_id)

    agg: dict = {}
    for edge in base_edges:
        src, tgt = group_of[edge["source"]], group_of[edge["target"]]
        if src == tgt:
            continue  # intra-package detail belongs at L2, not here
        key = (src, tgt, edge["kind"])
        agg[key] = agg.get(key, 0) + 1

    edges = [
        {"source": src, "target": tgt, "kind": kind, "weight": count,
         "confidence": None, "count": count}
        for (src, tgt, kind), count in sorted(agg.items())
    ]

    degree: dict = {}
    for edge in edges:
        degree[edge["source"]] = degree.get(edge["source"], 0) + edge["count"]
        degree[edge["target"]] = degree.get(edge["target"], 0) + edge["count"]

    nodes = []
    for group in sorted(members):
        kind = encoding.package_type(group, members[group])
        # Uniform only: if every member that resolves a role agrees, the
        # package inherits it (a "tests" package rolls up to role=test); any
        # disagreement -- or no member resolving one at all -- leaves it
        # `None` rather than picking a majority that would misreport the rest.
        member_roles = {role_of.get(m) for m in members[group]} - {None}
        role = next(iter(member_roles)) if len(member_roles) == 1 else None
        nodes.append({
            "id": group,
            "label": encoding.package_label(group),
            "level": None,
            "type": kind,
            "family": encoding.FAMILY_OF_TYPE.get(kind),
            "degree": degree.get(group, 0),
            "node_id": None,  # synthetic super-node: no single resolvable subject
            "members": sorted(members[group]),
            "file_count": len(members[group]),
            "role": role,
        })

    return {
        "level": "L3" if depth == 1 else "P%d" % depth,
        "scope": scope,
        "nodes": nodes,
        "edges": edges,
        "levels": graph_art.get("levels", []),
        "cycles": graph_art.get("cycles", []),
        "divergence": graph_art.get("divergence"),
        "legend": _legend(nodes),
    }


def _restrict_dataflow_to_scope(nodes: list, edges: list, scope: str) -> "tuple[list, list]":
    """`scope=` filter shared by every rolled-up altitude and L2: keep every
    node that is `scope` itself or one of its descendants
    (`encoding.is_descendant`, depth-agnostic -- it derives `scope`'s own
    depth from its id), every edge touching that set, and the nodes on the
    far end of those edges. An unknown/empty `scope` leaves the graph
    untouched rather than returning an empty canvas that would read as "this
    package has nothing in it". Replaces the two near-duplicate scope
    filters this used to be (`_build_graph_l2`'s inline
    `package_of(id) == scope`, and the old `_restrict_to_neighborhood`'s
    exact-id match on an already-rolled-up graph) with one rule usable at
    any depth transition, including straight into raw L2.

    `scope` is now a container group (`WEB_REDESIGN_RESEARCH.md` §3.1) rather
    than an id-string package, so descent is checked file-path-aware via
    `encoding.container_descendant`, using each node's own resolved `file`
    (present on every node `_dataflow_graph` builds)."""
    file_of = {n["id"]: n.get("file") for n in nodes}
    keep = {n["id"] for n in nodes if n["id"] == scope or encoding.container_descendant(n["id"], scope, file_of)}
    if not keep:
        return nodes, edges
    kept_edges = [e for e in edges if e["source"] in keep or e["target"] in keep]
    reachable = set(keep)
    for edge in kept_edges:
        reachable.add(edge["source"])
        reachable.add(edge["target"])
    return [n for n in nodes if n["id"] in reachable], kept_edges


#: `WEB_REDESIGN_RESEARCH.md` §3.1: "unscoped L2 should not be reachable from
#: the UI; if kept, [it needs bounding]." This is that bound -- only the
#: *unscoped* L2 request (the one with no natural size limit) is checked;
#: every scoped L2 request is already bounded by `_restrict_dataflow_to_scope`
#: to one container's neighbourhood. 2000 sits above this repo's real L2
#: (353 nodes) and below `unified-store`'s measured unscoped L2 (6,064 nodes,
#: the doc's own repro case), so real small repos are never affected and the
#: doc's flagged pathological case is.
GRAPH_SIZE_CEILING = 2000


def _build_graph_l2(conn: ReadOnlyConnection, snapshot_id: int, scope: Optional[str]) -> dict:
    """Modules: the typed `dataflow` graph as-is (`ATLAS_REDESIGN.md` §2).
    `scope=` is any grouped-altitude id and filters to that group's members
    plus their immediate neighbours, so double-clicking a super-node
    descends into exactly what it rolled up (plus its boundary)."""
    base = _dataflow_graph(conn, snapshot_id)
    nodes, edges = base["nodes"], base["edges"]

    if scope is not None:
        nodes, edges = _restrict_dataflow_to_scope(nodes, edges, scope)
    elif len(nodes) > GRAPH_SIZE_CEILING:
        top_rung = _build_graph_grouped(conn, snapshot_id, 1, None)
        suggested = sorted(
            top_rung["nodes"], key=lambda n: n.get("degree") or 0, reverse=True
        )[:8]
        return {
            "level": "L2",
            "scope": scope,
            "nodes": [],
            "edges": [],
            "levels": [],
            "cycles": [],
            "divergence": None,
            "legend": [],
            "too_large": True,
            "suggested_scopes": [n["id"] for n in suggested],
        }

    return {
        "level": "L2",
        "scope": scope,
        "nodes": nodes,
        "edges": edges,
        "levels": [],
        "cycles": [],
        "divergence": None,
        "legend": _legend(nodes),
    }


def _legend(nodes: list) -> list:
    """Counts per display type, in the encoding module's own declared order --
    so the legend lists what is actually on this canvas, never a static list
    that can drift from the render. A rolled-up node counts for the number of
    L2 nodes inside it, so "Tables 27" reads the same at both altitudes
    instead of collapsing to "Tables 1"."""
    counts: dict = {}
    for node in nodes:
        kind = node.get("type")
        if kind:
            counts[kind] = counts.get(kind, 0) + len(node.get("members") or [None])
    return [
        {
            "type": kind,
            "label": encoding.TYPE_LABEL.get(kind, kind),
            "family": encoding.FAMILY_OF_TYPE.get(kind, "code"),
            "count": counts[kind],
        }
        for kind in encoding.TYPE_ORDER
        if kind in counts
    ]


def _dataflow_graph(conn: ReadOnlyConnection, snapshot_id: int) -> dict:
    """The one real architecture graph in the store: `dataflow.edges` and the
    node set they induce. Every node id here is a `dataflow` id -- bare for a
    module/symbol, `type:`-prefixed otherwise -- so source and target always
    live in the *same* namespace. The old L0 builder mixed namespaces (symbol
    nodes, module edges) and 369 of 371 edges dangled; that is the bug
    `ATLAS_REDESIGN.md` §1 measured and this function exists to prevent.

    `xref.symbols` is consulted only to decide whether a bare id resolves as
    `sym:` or `module:` for `/api/node`, never to add nodes."""
    dataflow = conn.read_artifact(snapshot_id, "dataflow", default={"edges": []})
    xref = conn.read_artifact(snapshot_id, "xref", default={"symbols": {}})
    symbol_table: dict = xref.get("symbols") or {}
    symbols = set(symbol_table.keys())
    roles = _role_index(conn, snapshot_id)

    raw_edges = dataflow.get("edges", []) or []

    degree: dict = {}
    ids: set = set()
    for edge in raw_edges:
        src, tgt = edge.get("source"), edge.get("target")
        if not src or not tgt:
            continue
        ids.add(src)
        ids.add(tgt)
        degree[src] = degree.get(src, 0) + 1
        degree[tgt] = degree.get(tgt, 0) + 1

    nodes = []
    for raw_id in sorted(ids):
        kind = encoding.type_of(raw_id)
        sym = symbol_table.get(raw_id)
        sym_file = sym["sites"][0].get("file") if sym and sym.get("sites") else None
        nodes.append({
            "id": raw_id,
            "label": encoding.short_label(raw_id),
            "level": None,
            "type": kind,
            "family": encoding.FAMILY_OF_TYPE.get(kind),
            "degree": degree.get(raw_id, 0),
            "node_id": nodeid.from_dataflow_id(raw_id, symbols),
            "members": None,
            # Only resolvable for a bare id backed by an `xref` symbol (a
            # function/route/table *definition*, not a `type:`-prefixed
            # reference node like `table:`/`config:` which has no file of its
            # own) -- `None` otherwise, never guessed from a caller's file.
            "role": roles.get(sym_file) if sym_file else None,
        })

    edges = [
        {
            "source": e["source"],
            "target": e["target"],
            "kind": e.get("channel", "flow"),
            "weight": None,
            "confidence": e.get("confidence"),
            "count": 1,
        }
        for e in raw_edges
        if e.get("source") and e.get("target")
    ]

    # Owning file per node -- `WEB_REDESIGN_RESEARCH.md` §3.1's container
    # hierarchy key. Attached here (not recomputed by callers) since this is
    # the one place both `symbol_table` and `edges` are already in scope.
    # `sorted_symbol_keys` computed once here (not inside the per-node call)
    # so the descendant-fallback `bisect` probe stays O(log n) per node
    # rather than O(n log n) per node.
    sorted_symbol_keys = sorted(symbol_table)
    # Precomputed once per call (O(edges)) instead of letting
    # `resolve_owner_file` re-scan all of `edges` per node (O(nodes × edges) --
    # profiling against the real `unified-store` index found this the
    # dominant cost of `/api/graph`, 7.9s of an 8.2s request).
    owner_edge_map = encoding.build_owner_edge_map(edges, symbol_table)
    for node in nodes:
        node["file"] = encoding.resolve_owner_file(
            node["id"], symbol_table, edges, sorted_symbol_keys, owner_edge_map
        )

    return {"nodes": nodes, "edges": edges}


def _build_graph(
    repo: Path,
    state_dir: Optional[str],
    level: str,
    scope: Optional[str],
    hide_roles: Optional[List[str]] = None,
    focus: Optional[str] = None,
) -> dict:
    resolved_state_dir = resolve_state_dir(repo, state_dir)
    db_path = resolved_state_dir / "index.db"
    conn = ReadOnlyConnection(db_path)
    snapshot_id = conn.latest_pinned_snapshot()

    base_file_of = {node["id"]: node.get("file") for node in _dataflow_graph(conn, snapshot_id)["nodes"]}
    rungs = _graph_rungs(base_file_of)
    valid_levels = {rung["level"] for rung in rungs} | {"L0", "L1"}

    if level not in valid_levels:
        raise UnsupportedGraphLevel(
            "level %r is not a graph altitude for this repo -- levels available: %s "
            "(the module-link constellation is a separate concept, served "
            "unfiltered by /api/links, not an altitude of this endpoint)"
            % (level, ", ".join(sorted(valid_levels)))
        )

    if level == "L0":
        result = _build_graph_l0(conn, snapshot_id, scope)
    elif level == "L1":
        result = _build_graph_l1(conn, snapshot_id, scope)
    elif level == "L2":
        result = _build_graph_l2(conn, snapshot_id, scope)
    else:
        result = _build_graph_grouped(conn, snapshot_id, _parse_grouped_level(level), scope)

    result["rungs"] = rungs

    if hide_roles:
        result["nodes"], result["edges"] = _drop_roles(result["nodes"], result["edges"], set(hide_roles))
        if result.get("legend"):
            result["legend"] = _legend(result["nodes"])

    # `focus=` -- `WEB_REDESIGN_RESEARCH.md` §4's "neighbourhood focus as a
    # first-class action, not only via double-click". Applied *after* the
    # level/scope build and *without* touching `level`/`scope` in the
    # response, so it restricts what's drawn without moving the breadcrumb
    # the way a real `scope=` descent would. Reuses the same
    # `_restrict_dataflow_to_scope` rule (scope + descendants + one-hop
    # boundary) already proven for scoped descent; `focus` not present in
    # this altitude's own node set is a no-op (empty `keep` -> unchanged),
    # same "don't blank the canvas on an unknown id" behavior as `scope`.
    if focus and not result.get("too_large") and result["nodes"]:
        result["nodes"], result["edges"] = _restrict_dataflow_to_scope(result["nodes"], result["edges"], focus)
        if result.get("legend"):
            result["legend"] = _legend(result["nodes"])
    return result


@app.get("/api/graph", response_model=GraphResponse)
def get_graph(
    level: str = Query(..., description="altitude: L0 (symbols), L1 (files), L2 (typed dataflow nodes), L3 (packages)"),
    scope: Optional[str] = Query(None, description="filter to one package's/scope's neighborhood"),
    hide_roles: Optional[List[str]] = Query(
        None, description="drop nodes whose file role matches (repeatable), plus any edge touching one"
    ),
    focus: Optional[str] = Query(
        None, description="restrict to this node's neighbourhood without changing level/scope (breadcrumb-free descent)"
    ),
    repo: str = Query(".", description="repo path to resolve state for"),
    state_dir: Optional[str] = Query(None, alias="state_dir"),
) -> GraphResponse:
    try:
        result = _build_graph(Path(repo), state_dir, level, scope, hide_roles, focus)
    except UnsupportedGraphLevel as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc
    except StoreUnavailable as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except StoreLocked as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return GraphResponse(**result)


#: Most-conservative-wins, mirroring `theme/confidence.ts`'s `dominantConfidence`
#: -- a node with any low/contested claim is not "high confidence" just because
#: it also has a high-confidence one.
_CONFIDENCE_RANK = {"contested": 0, "low": 1, "medium": 2, "high": 3}


def _build_confidence(repo: Path, state_dir: Optional[str], level: str, scope: Optional[str]) -> dict:
    """One bulk `{raw graph id -> bucket}` map for a whole altitude.

    The confidence lens used to issue one `/api/node/{id}` per visible node.
    That was defensible at the old L2 (20 scope nodes) and is not at the L2
    `ATLAS_REDESIGN.md` P0 introduced (353 typed nodes) -- 353 requests per
    lens toggle, each re-reading and re-classifying the same three artifacts.
    This reads them once, classifies every claim once, and rolls the result
    up to whatever ids the requested altitude actually renders.

    Nodes with no claim are simply absent from `buckets`; the client treats a
    missing key as `unreviewed` rather than this endpoint inventing a row for
    every node in the graph."""
    graph = _build_graph(repo, state_dir, level, scope)

    resolved_state_dir = resolve_state_dir(repo, state_dir)
    conn = ReadOnlyConnection(resolved_state_dir / "index.db")
    snapshot_id = conn.latest_pinned_snapshot()
    xref = conn.read_artifact(snapshot_id, "xref", default={})
    partition = conn.read_artifact(snapshot_id, "partition", default={})
    dataflow = conn.read_artifact(snapshot_id, "dataflow", default={})
    state = conn.read_artifact(snapshot_id, "state", default={"claims": []})

    index = nodeid.SubjectIndex(xref, partition, dataflow)
    # Members as well as node ids: at L3 a claim's subject is an L2 id
    # (`config:CDP_STORE`), never the super-node it rolls into (`Config`), so
    # matching on node ids alone would leave every package unreviewed.
    graph_ids = {node["id"] for node in graph["nodes"]}
    for node in graph["nodes"]:
        graph_ids.update(node.get("members") or [])

    by_raw_id: dict = {}
    for claim in state.get("claims", []) or []:
        bucket = claim.get("confidence")
        if bucket not in _CONFIDENCE_RANK:
            continue
        raw = _subject_to_graph_id(str(claim.get("subject", "")), graph_ids, index)
        if raw is None:
            continue
        current = by_raw_id.get(raw)
        if current is None or _CONFIDENCE_RANK[bucket] < _CONFIDENCE_RANK[current]:
            by_raw_id[raw] = bucket

    buckets: dict = {}
    for node in graph["nodes"]:
        # L3 super-nodes stand for their members; roll those up the same
        # most-conservative-wins way a single node rolls up its own claims.
        candidates = [node["id"]] + list(node.get("members") or [])
        worst = None
        for candidate in candidates:
            found = by_raw_id.get(candidate)
            if found and (worst is None or _CONFIDENCE_RANK[found] < _CONFIDENCE_RANK[worst]):
                worst = found
        if worst is not None:
            buckets[node["id"]] = worst

    return {"level": graph["level"], "buckets": buckets}


def _subject_to_graph_id(subject: str, graph_ids: set, index: "nodeid.SubjectIndex") -> Optional[str]:
    """Which rendered node a claim's `subject` belongs to, or `None`.

    A claim `subject` is *already* a `dataflow`-style id on this corpus
    (`config:CDP_STORE`, `entity:web.api.models.DiffResponse`) -- 168 of 176
    claims match a graph node verbatim. The two fallbacks handle the rest:
    a symbol fqn rolls up to the module it lives in (`cdp.cli#main` ->
    `cdp.cli`), and `SubjectIndex` still gets the last word for the
    `scope:`/`file:` subjects it was written for. Claims that match nothing
    are dropped rather than attributed to a guess."""
    if subject in graph_ids:
        return subject
    owner = subject.split("#")[0]
    if owner != subject and owner in graph_ids:
        return owner
    classified = index.classify(subject)
    if classified is not None:
        stripped = nodeid.dataflow_id(classified)
        if stripped in graph_ids:
            return stripped
    return None


@app.get("/api/confidence", response_model=ConfidenceResponse)
def get_confidence(
    level: str = Query(..., description="altitude, same vocabulary as /api/graph"),
    scope: Optional[str] = Query(None, description="same scope filter as /api/graph"),
    repo: str = Query(".", description="repo path to resolve state for"),
    state_dir: Optional[str] = Query(None, alias="state_dir"),
) -> ConfidenceResponse:
    try:
        result = _build_confidence(Path(repo), state_dir, level, scope)
    except UnsupportedGraphLevel as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc
    except StoreUnavailable as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except StoreLocked as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return ConfidenceResponse(**result)


def _all_registry_entries() -> dict:
    """Every `repo_id -> state_path` entry `cdp.store.registry` knows about,
    read straight from `registry_mod.REGISTRY_PATH` (same file, same `[repos]`
    TOML shape `registry_mod._read_registry()` reads) -- there is no public
    "list everything" function on that module (`lookup` is one-at-a-time by
    id) and this item's scope is web-layer-only, so the read is duplicated
    here rather than adding a new public function to `cdp/store/registry.py`.
    """
    path = registry_mod.REGISTRY_PATH
    if not path.is_file():
        return {}
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {str(k): str(v) for k, v in data.get("repos", {}).items()}


def _build_repo_info(repo_id: str, state_path_str: str) -> dict:
    """One registry entry's freshness row. `as_of_commit` is the commit the
    pinned snapshot's `inventory` was built against -- the same source
    `cdp.query._as_of` reads (`inventory.get("head")`). `head` is the
    *current* HEAD of the repo's working tree, read fresh via `git
    rev-parse HEAD` in `inventory["repo"]` (the repo path recorded at scan
    time -- the registry itself only maps id -> state path, not repo path).
    Raises `StoreUnavailable`/`StoreLocked` on a broken state dir; the caller
    turns either into an `error` row rather than a 500 for the whole list."""
    # The registry value already names an exact state dir (highest-priority
    # branch of `store_reader.resolve_state_dir`'s fallback chain), so it's
    # used directly rather than re-run through repo-identity resolution.
    state_dir = Path(state_path_str).expanduser().resolve()
    db_path = state_dir / "index.db"
    conn = ReadOnlyConnection(db_path)
    snapshot_id = conn.latest_pinned_snapshot()
    inventory = conn.read_artifact(snapshot_id, "inventory")

    as_of_commit = inventory.get("head")
    repo_path = inventory.get("repo")

    current_head = None
    if repo_path and Path(repo_path).is_dir():
        current_head = cdp_util.git_head(Path(repo_path))

    behind: Optional[int] = None
    if current_head and as_of_commit and as_of_commit != "unpinned":
        if current_head == as_of_commit:
            behind = 0
        else:
            count_out = cdp_util.run_git(
                Path(repo_path), "rev-list", "--count", "%s..%s" % (as_of_commit, current_head),
            )
            if count_out is not None:
                try:
                    behind = int(count_out.strip())
                except ValueError:
                    behind = None

    return {
        "repo_id": repo_id,
        "state_dir": str(state_dir),
        "repo_path": repo_path,
        "head": current_head,
        "as_of_commit": as_of_commit,
        "behind": behind,
        "error": None,
    }


class NodeNotFound(Exception):
    """`node_id` is well-formed and namespaced correctly, but resolves to
    nothing in the current pinned snapshot -- no claims, no dataflow edges,
    no scope/file match, and (for `sym`/`route`/`table`/`module`) no entry in
    the artifact that would name it either. The route turns this into a real
    404, never an empty-but-200 body (`PLAN.md` item 3)."""


def _build_node(repo: Path, state_dir: Optional[str], node_id: str) -> dict:
    """Resolves one namespaced `node_id` (`web/api/nodeid.py`) to everything
    the current snapshot knows about it: claims whose `subject` classifies to
    this same id (`nodeid.SubjectIndex`), an honest unknowns count, in/out
    `dataflow.edges` for `sym:`/`route:`/`table:` ids, and the owning
    `partition` scope for `file:`/`scope:` ids. Raises `ValueError` (bad
    `node_id`, -> 400 at the route) or `NodeNotFound` (well-formed but absent,
    -> 404) same posture as `StoreUnavailable`/`StoreLocked` elsewhere in this
    module."""
    ns, rest = nodeid.parse(node_id)  # raises ValueError on a malformed id

    resolved_state_dir = resolve_state_dir(repo, state_dir)
    db_path = resolved_state_dir / "index.db"
    conn = ReadOnlyConnection(db_path)
    snapshot_id = conn.latest_pinned_snapshot()

    xref = conn.read_artifact(snapshot_id, "xref", default={})
    partition = conn.read_artifact(snapshot_id, "partition", default={})
    dataflow = conn.read_artifact(snapshot_id, "dataflow", default={})
    graph = conn.read_artifact(snapshot_id, "graph", default={})
    state = conn.read_artifact(snapshot_id, "state", default={"claims": [], "unknowns": []})

    index = nodeid.SubjectIndex(xref, partition, dataflow)

    # A claim's `subject` is a `dataflow`-style id on real corpora
    # (`config:CDP_STORE`, `entity:web.api.models.DiffResponse`), which
    # `SubjectIndex` -- written for `sym:`/`route:`/`table:`/`scope:` subjects
    # before those types existed -- classifies as `None`. Comparing against
    # the dataflow id first is what makes the inspector show claims for the
    # typed nodes `ATLAS_REDESIGN.md` P0 put on the canvas; `classify` still
    # gets the last word for the subjects it does handle.
    df_id = nodeid.dataflow_id(node_id)

    def _is_subject_of(subject: str) -> bool:
        return subject == df_id or index.classify(subject) == node_id

    claims = [
        c for c in state.get("claims", []) or []
        if _is_subject_of(str(c.get("subject", "")))
    ]

    unknowns = state.get("unknowns", []) or []
    unknowns_count = 0
    for u in unknowns:
        subject = u.get("subject")
        if subject and _is_subject_of(str(subject)):
            unknowns_count += 1
        elif ns == "scope" and u.get("source_node") == rest:
            unknowns_count += 1

    # `dataflow.edges` names a typed endpoint *with* its prefix
    # (`table:churn_cache`), so matching on the stripped `rest` silently found
    # nothing for every `route:`/`table:` id -- the neighbourhood pane was
    # empty for exactly the nodes it was built for. `nodeid.dataflow_id` is
    # the one place that mapping lives now.
    edges_in: list = []
    edges_out: list = []
    if ns in ("sym", "module") + nodeid.DATAFLOW_NAMESPACES:
        for edge in dataflow.get("edges", []) or []:
            if edge.get("target") == df_id:
                edges_in.append(edge)
            if edge.get("source") == df_id:
                edges_out.append(edge)

    scope = None
    if ns == "scope":
        for s in partition.get("scopes", []) or []:
            if s.get("node") == rest:
                scope = s
                break
    elif ns == "file":
        for s in partition.get("scopes", []) or []:
            if rest in (s.get("files") or []):
                scope = s
                break

    found = bool(claims) or bool(edges_in) or bool(edges_out) or scope is not None
    if not found:
        if ns == "module":
            found = rest in set(graph.get("modules", []) or [])
        elif ns == "sym":
            found = rest in (xref.get("symbols", {}) or {})
        elif ns == "route":
            all_routes = (xref.get("routes", []) or []) + (xref.get("unresolved_routes", []) or [])
            found = any(r.get("route") == rest for r in all_routes) or any(
                df_id in (edge.get("source"), edge.get("target"))
                for edge in (dataflow.get("edges", []) or [])
            )
        elif ns in nodeid.DATAFLOW_NAMESPACES:
            # A typed node exists iff some dataflow edge names it. Checking
            # the prefixed id (not `rest`) is the same fix as the edge scan
            # above; the old `channel == "db"` filter also never matched,
            # since this corpus's table edges use `persist`/`read`/`schema_own`.
            found = any(
                df_id in (edge.get("source"), edge.get("target"))
                for edge in (dataflow.get("edges", []) or [])
            )

    if not found:
        raise NodeNotFound("node id %r does not resolve to anything in the current snapshot" % node_id)

    return {
        "node_id": node_id,
        "namespace": ns,
        "claims": claims,
        "unknowns_count": unknowns_count,
        "edges_in": edges_in,
        "edges_out": edges_out,
        "scope": {
            "node": scope["node"],
            "module": scope.get("module", ""),
            "file_count": scope.get("file_count", 0),
            "loc": scope.get("loc", 0),
        } if scope is not None else None,
    }


@app.get("/api/node/{node_id:path}", response_model=NodeResponse)
def get_node(
    node_id: str,
    repo: str = Query(".", description="repo path to resolve state for"),
    state_dir: Optional[str] = Query(None, alias="state_dir"),
) -> NodeResponse:
    try:
        result = _build_node(Path(repo), state_dir, node_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except NodeNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except StoreUnavailable as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except StoreLocked as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return NodeResponse(**result)


@app.get("/api/repos", response_model=ReposResponse)
def get_repos(
    repo: str = Query(".", description="repo path to resolve state for"),
    state_dir: Optional[str] = Query(None, alias="state_dir"),
) -> ReposResponse:
    """Every state dir this machine's `cdp` registry knows about, with
    per-repo freshness (current git HEAD vs. the pinned snapshot's
    `as_of` commit). A registry entry whose state dir vanished, whose
    `index.db` is missing/locked, or whose git call fails gets its own
    `error` row instead of 500ing the whole list (mirrors `get_status`'s
    `StoreUnavailable`/`StoreLocked` -> per-request handling, just scoped
    to one row here instead of the whole response).

    The registry only maps a repo's *git-remote identity* to a state dir
    (`cdp.store.registry.register`, called from `cmd_scan`) -- a repo
    scanned before that identity existed in the registry (e.g. this repo,
    whose origin was never `register`ed under its current remote) has no
    entry at all, even though `/api/status` resolves its state dir fine via
    the same `resolve_state_dir` fallback chain every other endpoint uses.
    Without this, `repos.repos[0]` (the frontend's single-repo assumption,
    `RepoHealthStrip.tsx`) would silently show whichever *other* repo
    happens to sort first in the registry. So: resolve the caller's actual
    `repo`/`state_dir` the normal way, and put that entry first -- matching
    an existing registry row by resolved state dir if one names the same
    directory, else synthesizing one so the current repo is never invisible
    or shadowed by an unrelated stale entry."""
    entries = _all_registry_entries()

    current_state_dir = resolve_state_dir(Path(repo), state_dir)
    current_repo_id: Optional[str] = None
    for repo_id, state_path_str in entries.items():
        if Path(state_path_str).expanduser().resolve() == current_state_dir:
            current_repo_id = repo_id
            break
    if current_repo_id is None:
        current_repo_id = registry_mod.repo_identity(Path(repo).expanduser().resolve())

    ordered_ids = [current_repo_id] + sorted(rid for rid in entries if rid != current_repo_id)
    state_dirs = dict(entries)
    state_dirs.setdefault(current_repo_id, str(current_state_dir))

    repos = []
    for repo_id in ordered_ids:
        state_path_str = state_dirs[repo_id]
        try:
            repos.append(RepoInfoResponse(**_build_repo_info(repo_id, state_path_str)))
        except (StoreUnavailable, StoreLocked) as exc:
            repos.append(RepoInfoResponse(
                repo_id=repo_id, state_dir=state_path_str, error=str(exc),
            ))
        except Exception as exc:  # noqa: BLE001 -- one bad entry must not 500 the list
            repos.append(RepoInfoResponse(
                repo_id=repo_id, state_dir=state_path_str, error=str(exc),
            ))
    return ReposResponse(repos=repos)


@app.get("/api/doctor", response_model=DoctorResponse)
def get_doctor(
    repo: str = Query(".", description="repo path to resolve state for"),
    state_dir: Optional[str] = Query(None, alias="state_dir"),
) -> DoctorResponse:
    """`<state>/doctor/*.json` is a plain filesystem directory
    (`cli.py:1858,1885`), not an `index.db` artifact -- no `ReadOnlyConnection`
    involved, no backend-polymorphism risk. 404 if the directory doesn't
    exist or has no reports yet (nobody has run `cdp doctor` here)."""
    from cdp import doctor as doctor_mod

    resolved_state_dir = resolve_state_dir(Path(repo), state_dir)
    doctor_dir = resolved_state_dir / "doctor"
    if not doctor_dir.is_dir():
        raise HTTPException(
            status_code=404,
            detail="no %s -- run `cdp doctor` first" % doctor_dir,
        )
    models: dict = {}
    for f in sorted(doctor_dir.glob("*.json")):
        data = cdp_util.read_json(f)
        if isinstance(data, dict) and "model" in data:
            models[data["model"]] = data
    if not models:
        raise HTTPException(
            status_code=404,
            detail="%s has no model reports -- run `cdp doctor` first" % doctor_dir,
        )
    table = doctor_mod.compatibility_table(models) if len(models) > 1 else None
    return DoctorResponse(models=models, table=table)


@app.get("/api/link", response_model=LinkQueryResponse)
def get_link(
    service: str = Query(..., description="repo/service identifier to filter to"),
    repo: str = Query(".", description="repo path to resolve state for"),
    state_dir: Optional[str] = Query(None, alias="state_dir"),
) -> LinkQueryResponse:
    """Thin wrapper over the existing pure `link.query_service`
    (`cdp/link.py:217`) -- `link_edge` is a disposable, fully-replaced-on-scan
    table (`sqlite_backend.py:356`'s docstring), so no manifest-pinning
    concern here, just a plain read."""
    resolved_state_dir = resolve_state_dir(Path(repo), state_dir)
    db_path = resolved_state_dir / "index.db"
    conn = ReadOnlyConnection(db_path)
    try:
        edges = conn.read_link_edges()
    except StoreUnavailable as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except StoreLocked as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    result = link_mod.query_service(edges, service)
    return LinkQueryResponse(service=service, links=result["links"], unmatched=result["unmatched"])


@app.get("/api/links", response_model=LinksResponse)
def get_links(
    repo: str = Query(".", description="repo path to resolve state for"),
    state_dir: Optional[str] = Query(None, alias="state_dir"),
) -> LinksResponse:
    """All persisted link edges, unfiltered -- the constellation view's data
    source (`/api/link?service=` is a single-service lookup, not a listing).
    Same store/error handling as `/api/link` above."""
    resolved_state_dir = resolve_state_dir(Path(repo), state_dir)
    db_path = resolved_state_dir / "index.db"
    conn = ReadOnlyConnection(db_path)
    try:
        edges = conn.read_link_edges()
    except StoreUnavailable as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except StoreLocked as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    links = [e["data"] for e in edges if e.get("kind") == "link"]
    unmatched = [e["data"] for e in edges if e.get("kind") == "unmatched"]
    return LinksResponse(links=links, unmatched=unmatched)


@app.get("/api/trajectory", response_model=TrajectoryResponse)
def get_trajectory(
    shape: Optional[str] = Query(None, description="exact scope_shape_key to filter to"),
    budget: int = Query(100, description="max rows, newest first"),
) -> TrajectoryResponse:
    """`~/.cdp/trajectories.db` is a separate, cross-workspace, cumulative
    corpus (`cdp/trajectory.py` module docstring) -- not scoped to `repo=`/
    `state_dir=` the way every other endpoint above is."""
    trajectory_conn = ReadOnlyTrajectoryConnection()
    try:
        runs = trajectory_conn.query_leaf_runs(shape=shape, budget=budget)
    except TrajectoryUnavailable as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except TrajectoryLocked as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return TrajectoryResponse(shape=shape, runs=runs)


@app.get("/api/snapshots", response_model=SnapshotsResponse)
def get_snapshots(
    repo: str = Query(".", description="repo path to resolve state for"),
    state_dir: Optional[str] = Query(None, alias="state_dir"),
) -> SnapshotsResponse:
    """This repo's scanned-commit history (`snapshot_meta`), oldest first --
    the time scrubber's timeline and the valid `/api/diff` `old`/`new`
    values."""
    resolved_state_dir = resolve_state_dir(Path(repo), state_dir)
    db_path = resolved_state_dir / "index.db"
    conn = ReadOnlyConnection(db_path)
    repo_id = registry_mod.repo_identity(Path(repo).expanduser().resolve())
    try:
        history = conn.snapshot_history(repo_id)
    except StoreUnavailable:
        history = []
    except StoreLocked as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return SnapshotsResponse(repo_id=repo_id, snapshots=history)


def _diff_side(conn: ReadOnlyConnection, snapshot_id: int) -> tuple:
    graph = conn.read_artifact(snapshot_id, "graph")
    xref = conn.read_artifact(snapshot_id, "xref", default={})
    state = conn.read_artifact(snapshot_id, "state", default={"claims": []})
    return graph, xref, state


@app.get("/api/diff", response_model=DiffResponse)
def get_diff(
    old_sha: str = Query(..., alias="old"),
    new_sha: str = Query(..., alias="new"),
    repo: str = Query(".", description="repo path to resolve state for"),
    state_dir: Optional[str] = Query(None, alias="state_dir"),
) -> DiffResponse:
    """Sha-mode only (`WEB_RESEARCH.md` §7.1's `/api/diff?old=&new=`) --
    dir-mode needs two arbitrary filesystem state directories, out of scope
    for a repo-scoped read endpoint. Delegates to the existing pure
    `diffs_mod.diff_snapshots` (`cdp/diffs.py:30`); the query-semantics
    invariant (§7.2.1) is preserved since that function is the same one
    `cmd_diff --old-sha/--new-sha` calls (`cli.py:2058-2107`)."""
    resolved_state_dir = resolve_state_dir(Path(repo), state_dir)
    db_path = resolved_state_dir / "index.db"
    conn = ReadOnlyConnection(db_path)
    repo_id = registry_mod.repo_identity(Path(repo).expanduser().resolve())

    try:
        old_id = conn.snapshot_id_for_sha(repo_id, old_sha)
        new_id = conn.snapshot_id_for_sha(repo_id, new_sha)
    except StoreLocked as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    if old_id is None or new_id is None:
        known = conn.known_shas(repo_id)
        missing = old_sha if old_id is None else new_sha
        raise HTTPException(
            status_code=400,
            detail="commit %r was never scanned for this repo -- known shas: %s"
            % (missing, ", ".join(known) or "(none -- run `cdp scan`)"),
        )

    try:
        old_graph, old_xref, old_state = _diff_side(conn, old_id)
        new_graph, new_xref, new_state = _diff_side(conn, new_id)
    except StoreUnavailable as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except StoreLocked as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    result = diffs_mod.diff_snapshots(old_graph, old_xref, old_state, new_graph, new_xref, new_state)
    return DiffResponse(old_sha=old_sha, new_sha=new_sha, diff=result)


_EVENTS_POLL_SECONDS = 1.0


async def _events_stream(conn: ReadOnlyConnection, run_id: str, request: Request, node_of_hash: dict):
    """The only `async def` handler in the app (§6.1.1) -- everything it
    touches is a blocking `sqlite3` call, run off the event loop via
    `run_in_threadpool` each poll rather than blocking it. Diffs successive
    `task_rows` polls by `scope_hash` so a client only gets an event for a
    row that actually changed, not a full resend every second; a periodic
    `wave` event carries the aggregate done/total regardless of whether any
    single task changed, so a slow client can still show progress.

    Emits the resolved `node` name (not the raw `scope_hash`) in each task
    event, same translation `_build_status` does via `node_of_hash` -- the
    frontend's live overlay (`useRunEvents`) keys off `StatusResponse.tasks[].node`,
    so a mismatched key here silently drops every live update in favor of
    the 4s poll."""
    prev: dict = {}
    while True:
        if await request.is_disconnected():
            return
        rows = await run_in_threadpool(conn.task_rows, run_id)
        current = {r["scope_hash"]: (r["state"], r["attempts"], r["last_error"]) for r in rows}
        for scope_hash, value in current.items():
            if prev.get(scope_hash) != value:
                state, attempts, last_error = value
                yield {
                    "event": "task",
                    "data": json.dumps({
                        "node": node_of_hash.get(scope_hash, scope_hash), "state": state,
                        "attempts": attempts, "last_error": last_error,
                    }),
                }
        prev = current
        done = sum(1 for state, _, _ in current.values() if state == "complete")
        yield {"event": "wave", "data": json.dumps({"done": done, "total": len(current)})}

        status = await run_in_threadpool(conn.run_status, run_id)
        if status == "complete":
            yield {"event": "complete", "data": json.dumps({"run_id": run_id})}
            return
        await asyncio.sleep(_EVENTS_POLL_SECONDS)


@app.get("/api/events")
async def get_events(
    request: Request,
    repo: str = Query(".", description="repo path to resolve state for"),
    state_dir: Optional[str] = Query(None, alias="state_dir"),
    run_id: Optional[str] = Query(None, description="defaults to the latest snapshot's manifest run_id"),
) -> EventSourceResponse:
    resolved_state_dir = resolve_state_dir(Path(repo), state_dir)
    db_path = resolved_state_dir / "index.db"
    conn = ReadOnlyConnection(db_path)
    try:
        snapshot_id = conn.latest_pinned_snapshot()
        if run_id is None:
            manifest = conn.read_artifact(snapshot_id, "manifest", default={})
            run_id = str(manifest.get("run_id", "cdp"))
        partition = conn.read_artifact(snapshot_id, "partition", default={"scopes": []})
    except StoreUnavailable as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except StoreLocked as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    node_of_hash = {s.get("scope_hash"): s["node"] for s in partition["scopes"]}
    return EventSourceResponse(_events_stream(conn, run_id, request, node_of_hash))


def _run_extra_args(target: str, resume: bool) -> list:
    """Translate the web layer's `target=` param into `cdp run`'s mutually
    exclusive `--wave-all`/`--stale-only`/`--scope`/`--wave` group
    (`cli.py:209-234`) -- one of those four is required, so `target` is
    required too rather than picking a silent default."""
    if target == "wave-all":
        extra = ["--wave-all"]
    elif target == "stale-only":
        extra = ["--stale-only"]
    elif target.startswith("scope:"):
        extra = ["--scope", target.split(":", 1)[1]]
    elif target.startswith("wave:"):
        extra = ["--wave", target.split(":", 1)[1]]
    else:
        raise HTTPException(
            status_code=400,
            detail="unknown target %r -- one of wave-all, stale-only, scope:<node>, wave:<n>" % target,
        )
    if resume:
        extra.append("--resume")
    return extra


@app.post("/api/run", response_model=JobResponse, dependencies=[Depends(require_mutation_auth)])
def post_run(
    repo: str = Query(".", description="repo path to resolve state for"),
    state_dir: Optional[str] = Query(None, alias="state_dir"),
    target: str = Query("wave-all", description="wave-all | stale-only | scope:<node> | wave:<n>"),
    resume: bool = Query(True, description="pass --resume through so a restarted job can rejoin"),
) -> JobResponse:
    """Shells out to `cdp run` (`web/api/jobs.py`'s `spawn_or_join`) rather
    than calling `supervisor` in-process -- the subprocess inherits the real
    lock, `--resume`'s lease logic, and the repo-mismatch guard for free. A
    second POST while one is in flight for this `(repo, state_dir)` returns
    the same job's handle (`status="joined"`), not a second process."""
    resolved_state_dir = str(resolve_state_dir(Path(repo), state_dir))
    extra_args = _run_extra_args(target, resume)
    job, joined = jobs_mod.spawn_or_join("run", repo, resolved_state_dir, extra_args)
    return JobResponse(
        job_id=job.job_id, status="joined" if joined else "started",
        pid=job.pid, kind=job.kind, repo=repo, state_dir=resolved_state_dir,
    )


@app.post("/api/refresh", response_model=JobResponse, dependencies=[Depends(require_mutation_auth)])
def post_refresh(
    repo: str = Query(".", description="repo path to resolve state for"),
    state_dir: Optional[str] = Query(None, alias="state_dir"),
    mode: str = Query("strict", description="cdp refresh --mode"),
) -> JobResponse:
    resolved_state_dir = str(resolve_state_dir(Path(repo), state_dir))
    job, joined = jobs_mod.spawn_or_join("refresh", repo, resolved_state_dir, ["--mode", mode])
    return JobResponse(
        job_id=job.job_id, status="joined" if joined else "started",
        pid=job.pid, kind=job.kind, repo=repo, state_dir=resolved_state_dir,
    )


@app.get("/api/job/{job_id}", response_model=JobStatusResponse)
def get_job(job_id: str) -> JobStatusResponse:
    """Poll for a job's completion when there is no task table to watch --
    `POST /api/hookup/liveness`'s `cdp doctor` subprocess is the first such
    caller; `/api/run`/`/api/refresh` instead poll `/api/status`."""
    job = jobs_mod.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="unknown job_id %r (server restart loses these)" % job_id)
    return JobStatusResponse(
        job_id=job.job_id, kind=job.kind, repo=job.repo, state_dir=job.state_dir,
        running=job.is_running(), returncode=job.returncode,
    )


@app.get("/api/hookup/preview", response_model=InstallPreviewResponse)
def get_hookup_preview(
    target: str = Query(..., description="repository to install into"),
    framework: str = Query("claude-code", description="claude-code | langgraph | adk | none"),
) -> InstallPreviewResponse:
    """`WEB_RESEARCH.md` §4 item 1: "shows the exact files it will copy and
    the `--runner-cmd` it will wire" -- the file-list half, read-only."""
    target_path = Path(target).expanduser().resolve()
    if not target_path.is_dir():
        raise HTTPException(status_code=400, detail="not a directory: %s" % target_path)
    if framework not in ("claude-code", "langgraph", "adk", "none"):
        raise HTTPException(status_code=400, detail="unknown framework %r" % framework)
    return InstallPreviewResponse(**hookup_mod.preview_install(target_path, framework))


@app.post("/api/hookup/install", response_model=InstallResultResponse, dependencies=[Depends(require_mutation_auth)])
def post_hookup_install(
    target: str = Query(..., description="repository to install into"),
    framework: str = Query("claude-code", description="claude-code | langgraph | adk | none"),
    hook: bool = Query(False, description="also install the PreToolUse nudge (claude-code only)"),
) -> InstallResultResponse:
    """Shells out to `cdp install`, same posture as `/api/run`/`/api/refresh`
    (`register_leaf_agent`/`copy_distribution`, `cli.py:2754-2864`) -- but
    unlike those, a file copy is fast and idempotent, so this runs
    synchronously rather than through `jobs_mod.spawn_or_join`."""
    target_path = Path(target).expanduser().resolve()
    if not target_path.is_dir():
        raise HTTPException(status_code=400, detail="not a directory: %s" % target_path)
    command = [sys.executable, "-m", "cdp", "install", str(target_path), "--framework", framework]
    if hook:
        command.append("--hook")
    try:
        proc = subprocess.run(command, capture_output=True, text=True, timeout=30)
    except subprocess.TimeoutExpired as exc:
        raise HTTPException(status_code=504, detail="cdp install timed out after 30s") from exc
    return InstallResultResponse(returncode=proc.returncode, stdout=proc.stdout, stderr=proc.stderr)


@app.get("/api/hookup/mcp-tools", response_model=McpToolsResponse)
def get_hookup_mcp_tools() -> McpToolsResponse:
    """The three `mcp_server` tools with a copy-to-clipboard client config
    (`WEB_RESEARCH.md` §4 item 1) -- read from `mcp_server/schemas.py`, never
    restated (§7.2's "client of the CLI's semantics, not a second
    implementation")."""
    return McpToolsResponse(tools=hookup_mod.mcp_tools(), client_config=hookup_mod.MCP_CLIENT_CONFIG)


@app.post("/api/hookup/liveness", response_model=JobResponse, dependencies=[Depends(require_mutation_auth)])
def post_hookup_liveness(
    target: str = Query(..., description="already-scanned repository to probe"),
    state_dir: Optional[str] = Query(None, alias="state_dir"),
    runner_cmd: str = Query(..., description="cdp doctor --runner-cmd"),
    model: str = Query(..., description="cdp doctor --model label"),
    node: Optional[str] = Query(None, description="scope to probe; defaults to the cheapest one"),
    timeout: float = Query(300.0, description="cdp doctor --timeout"),
) -> JobResponse:
    """"Is it alive?" (`WEB_RESEARCH.md` §4 item 1): dispatches `cdp doctor`
    at one throwaway scope. Reuses `jobs_mod.spawn_or_join` (already generic
    over `kind`) so a second liveness POST while one is in flight joins
    rather than races it, same single-flight semantics as `/api/run`. Result
    is read back through the existing `GET /api/doctor` once the job
    (`GET /api/job/:id`) finishes."""
    resolved_state_dir = resolve_state_dir(Path(target), state_dir)
    db_path = resolved_state_dir / "index.db"
    conn = ReadOnlyConnection(db_path)
    try:
        snapshot_id = conn.latest_pinned_snapshot()
        partition = conn.read_artifact(snapshot_id, "partition")
    except StoreUnavailable as exc:
        raise HTTPException(status_code=404, detail="%s -- run `cdp scan` first" % exc) from exc
    except StoreLocked as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    probe_node = node or hookup_mod.cheapest_scope_node(partition)
    extra_args = ["--runner-cmd", runner_cmd, "--model", model, "--node", probe_node, "--timeout", str(timeout)]
    job, joined = jobs_mod.spawn_or_join("doctor", target, str(resolved_state_dir), extra_args)
    return JobResponse(
        job_id=job.job_id, status="joined" if joined else "started",
        pid=job.pid, kind=job.kind, repo=target, state_dir=str(resolved_state_dir),
    )
