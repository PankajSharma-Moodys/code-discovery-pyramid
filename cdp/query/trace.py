"""Flow queries: `paths` and `trace`."""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

from .budget import Budget
from .common import _finish, _matches, _role_index, cite
from .store import Store


def q_paths(
    store: Store,
    frm: Optional[str] = None,
    to: Optional[str] = None,
    budget: Optional[Budget] = None,
) -> Dict:
    budget = budget or Budget()
    paths = store.dataflow["paths"]
    if frm:
        paths = [p for p in paths if _matches(p["source"], frm) or _matches(p["trigger"], frm)]
    if to:
        paths = [p for p in paths if _matches(p["sink"], to)]
    return _finish(
        {
            "query": "paths",
            "count": len(paths),
            "paths": [
                {
                    "trigger": p["trigger"],
                    "modules": p["modules"],
                    "representation_chain": p["representation_chain"],
                    "confidence": p["min_confidence"],
                    "hops": [
                        {
                            "from": h["from"].rsplit(".", 1)[-1],
                            "to": h["to"].rsplit(".", 1)[-1],
                            "channel": h["channel"],
                            "at": cite(h["anchor"]),
                        }
                        for h in p["hops"]
                    ],
                }
                for p in budget.take(paths)
            ],
        },
        store,
        budget,
    )


#: What `trace` promises and, more importantly, what it does not.
TRACE_CAVEAT = (
    "This is a reading list, not an answer. CDP has no parameter or branch model: "
    "it collapses a wide grep into a small cited read whose completeness is stated "
    "by the `elided` count below — zero means the list is complete, anything else "
    "means it is qualified. Hops marked `medium` come from the import table: an "
    "import proves that a file *can* reach a symbol, not that it does."
)


def q_trace(
    store: Store,
    entry: str,
    max_hops: int = 8,
    budget: Optional[Budget] = None,
    exclude_role: Optional[Sequence[str]] = None,
) -> Dict:
    """The minimal cited file set needed to answer a question about an entry point.

    Composes three things CDP already has and never joined: the `dataflow.py`
    traversal, `resolve.py`'s `used_by` transpose, and the budget above. The
    join is the product: today a consumer answers "what do I read to understand
    `POST /v1/settle`?" by running `routes`, then `symbol`, then `paths`, and
    doing the set union by hand.

    Every file carries the edge that put it there. A file with no justifying
    edge is not in the list, which is the only reason the list can be called
    minimal.
    """
    budget = budget or Budget()
    resolved = _resolve_entry(store, entry)
    if not resolved:
        return _finish(
            {
                "query": "trace",
                "entry": entry,
                "found": False,
                "why": (
                    "No route, dataflow source or defined symbol matches %r. It may be "
                    "in a scope this run did not cover — check `query coverage` before "
                    "concluding it does not exist." % entry
                ),
                "caveat": TRACE_CAVEAT,
                "files": [],
                "unknowns": [],
            },
            store, budget,
        )

    adjacency: Dict[str, List[Dict]] = {}
    for edge in store.dataflow["edges"]:
        adjacency.setdefault(edge["source"], []).append(edge)

    # Entry points are named by whatever recorded them — a route as
    # `Class#method`, a dataflow source as its own node — while the edge graph
    # is keyed on the file's primary symbol. Left unnormalised, a real endpoint
    # on the validation target traced to exactly one file, which reads as "this
    # endpoint touches nothing" rather than "the key did not match".
    _pivot(store, resolved, adjacency)
    reached, exhausted = _walk(resolved["node"], adjacency, max_hops)
    callers = store.xref["used_by"].get(resolved["node"], [])

    rows = _trace_files(store, resolved, reached, callers)
    # The entry point itself is never budgeted away, and the same holds for
    # role exclusion: the caller named it explicitly, so dropping it would be
    # more surprising than a stray test-role hop further down the trail.
    head, rest = rows[:1], rows[1:]
    if exclude_role:
        roles = _role_index(store)
        rest = [r for r in rest if roles.get(r["file"]) not in exclude_role]
    files = head + budget.take(rest)
    paths_shown = {row["file"] for row in files}

    unknowns = budget.take([
        u for u in store.state.get("unknowns", [])
        if (u.get("anchor") or {}).get("file") in paths_shown
        or any(_matches(u.get("question", ""), n.rsplit(".", 1)[-1]) for n in reached)
    ])

    return _finish(
        {
            "query": "trace",
            "entry": entry,
            "found": True,
            "resolved_as": resolved,
            "max_hops": max_hops,
            # A walk that ran out of hops has not finished. Reporting it as
            # completion is how a cycle turns into a confident wrong answer.
            "hops_exhausted": exhausted,
            # Why the trail stops, stated. An entry point with no outgoing edge
            # renders as a one-file list, and a one-file list with no
            # explanation reads as "this touches nothing" rather than as
            # "CDP found no edge leaving here".
            "trail": (
                "%d node(s) reachable from %s" % (len(reached), resolved["node"])
                if reached
                else "No dataflow edge leaves %s, so the trail stops at its "
                     "defining file. That is an absence of an extracted edge, not "
                     "evidence that nothing is called: check `query coverage`, and "
                     "note that runtime wiring (DI, reflection, framework "
                     "registration) produces no import to follow."
                     % resolved["node"]
            ),
            "file_count": len(rows),
            "files": files,
            "unknowns": unknowns,
            "caveat": TRACE_CAVEAT,
        },
        store, budget,
    )


def _pivot(store: Store, resolved: Dict, adjacency: Dict[str, List[Dict]]) -> None:
    """Move `resolved["node"]` onto a key the edge graph actually has.

    Tries the member's owning class, then the primary symbol of the file the
    entry point was cited in. Records what it did in `resolved["pivoted_from"]`
    rather than silently substituting a different subject.
    """
    node = resolved["node"]
    if node in adjacency:
        return
    candidates: List[str] = []
    if "#" in node:
        candidates.append(node.split("#", 1)[0])
    at = resolved.get("at") or ""
    primary = store.extraction["files"].get(at.rsplit(":", 1)[0], {}).get("primary")
    if primary:
        candidates.append(primary)
    for candidate in candidates:
        if candidate in adjacency:
            resolved["pivoted_from"] = node
            resolved["node"] = candidate
            return


def _resolve_entry(store: Store, entry: str) -> Optional[Dict]:
    """Route path, dataflow source, or symbol — in that order of specificity."""
    for route in store.xref["routes"] + store.xref["unresolved_routes"]:
        if route["route"] == entry or _matches(route["route"], entry):
            # A route handler is recorded as `Class#method`, while the dataflow
            # graph is keyed on the file's primary symbol. Walking from the raw
            # handler string finds no adjacency and silently returns a one-file
            # trace, which reads as "this endpoint touches nothing".
            info = store.extraction["files"].get(route["file"], {})
            node = info.get("primary") or route["handler"].split("#", 1)[0]
            return {
                "kind": "route",
                "node": node,
                "handler": route["handler"],
                "label": "%s %s" % (route["verb"], route["route"]),
                "channel": "http_in",
                "module": route["module"],
                "at": cite(route["evidence"][0]) if route["evidence"] else None,
            }
    for source in store.dataflow.get("sources", []):
        if source["node"] == entry or source["trigger"] == entry or _matches(source["node"], entry):
            return {
                "kind": "source",
                "node": source["node"],
                "label": source["trigger"],
                "channel": source["channel"],
                "module": source["module"],
                "at": cite(source["anchor"]),
            }
    symbols = store.xref["symbols"]
    keys = [k for k in symbols if k == entry or k.rsplit(".", 1)[-1] == entry]
    keys = keys or [k for k in symbols if _matches(k, entry)]
    if keys:
        key = sorted(keys, key=lambda k: (len(k), k))[0]
        sites = symbols[key]["sites"]
        return {
            "kind": "symbol",
            "node": key,
            "label": key,
            "channel": "defines",
            "module": sites[0]["module"] if sites else None,
            "at": cite(sites[0]["anchor"]) if sites else None,
        }
    return None


def _walk(
    start: str, adjacency: Dict[str, List[Dict]], max_hops: int
) -> Tuple[Dict[str, Dict], bool]:
    """Breadth-first from `start`, keeping the first edge that reached each node.

    First-reaching rather than shortest-overall because the question is *why is
    this file in my reading list*, and the answer should be the shortest
    justification. Deterministic: the frontier is sorted at every level.
    """
    reached: Dict[str, Dict] = {}
    frontier = [start]
    seen = {start}
    hops = 0
    while frontier and hops < max_hops:
        hops += 1
        nxt: List[str] = []
        for node in frontier:
            for edge in sorted(
                adjacency.get(node, ()),
                key=lambda e: (e["channel"], e["target"], e["anchor"]["file"], e["anchor"]["line"]),
            ):
                target = edge["target"]
                if target in seen:
                    continue
                seen.add(target)
                reached[target] = edge
                nxt.append(target)
        frontier = nxt
    return reached, bool(frontier)


def _trace_files(
    store: Store, resolved: Dict, reached: Dict[str, Dict], callers: Sequence[Dict]
) -> List[Dict]:
    """One row per file, each with the single edge that justified including it.

    Deduplicated on the file, because a reading list that names the same file
    three times for three edges is longer than the grep it replaced.
    """
    rows: List[Dict] = []
    seen: Set[str] = set()

    def add(path: Optional[str], module: Optional[str], why: str,
            at: Optional[str], confidence: str) -> None:
        if not path or path in seen:
            return
        seen.add(path)
        rows.append({"file": path, "module": module, "why": why, "at": at,
                     "confidence": confidence})

    entry_file = (resolved.get("at") or "").rsplit(":", 1)[0] or None
    add(entry_file, resolved.get("module"),
        "entry point (%s) %s" % (resolved["channel"], resolved["label"]),
        resolved.get("at"), "high")

    for target in sorted(reached):
        edge = reached[target]
        add(edge["anchor"]["file"], edge.get("module"),
            "%s --%s--> %s" % (edge["source"].rsplit(".", 1)[-1], edge["channel"],
                               target.rsplit(".", 1)[-1]),
            cite(edge["anchor"]), edge.get("confidence", "medium"))
        for site in store.xref["symbols"].get(target, {}).get("sites", []):
            add(site["file"], site["module"], "defines %s" % target,
                cite(site["anchor"]), "high")

    for caller in callers:
        add(caller["file"], caller["module"],
            "references %s" % resolved["node"].rsplit(".", 1)[-1],
            cite(caller["anchor"]), "high")
    return rows
