"""Flow queries: `paths` and `trace`."""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Sequence, Set, Tuple

from .budget import Budget
from .common import _finish, _matches, _role_index, cite
from .store import Store
from .trace_entry import resolve_entry


def q_paths(
    store: Store,
    frm: Optional[str] = None,
    to: Optional[str] = None,
    budget: Optional[Budget] = None,
) -> Dict:
    budget = budget or Budget()
    paths = store.dataflow["paths"]
    # `--from`/`--to` match any node on a path, not only its two ends (H2): the
    # paths *through* a node answer "what does X reach / what reaches X". With
    # both, `--from` must come at or before `--to`. A `Class#member` term also
    # matches the class, because dataflow nodes are classes, not members.
    if frm or to:
        paths = [p for p in paths if _through(p, frm, to)]
    return _finish(
        {
            "query": "paths",
            "match": "any node on the path (source, hops, sink)" if frm or to else "all",
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


def _nodes(path: Dict) -> List[str]:
    """A path's nodes in order: trigger, source, each hop's `to`, the sink."""
    out = [path["trigger"], path["source"]]
    out += [h["to"] for h in path["hops"]]
    out.append(path["sink"])
    return out


def _node_hit(node: str, needle: str) -> bool:
    if _matches(node, needle):
        return True
    owner = needle.partition("#")[0]
    return owner != needle and bool(owner) and _matches(node, owner)


def _through(path: Dict, frm: Optional[str], to: Optional[str]) -> bool:
    nodes = _nodes(path)
    first = 0
    if frm:
        hits = [i for i, n in enumerate(nodes) if _node_hit(n, frm)]
        if not hits:
            return False
        first = hits[0]
    if to:
        return any(_node_hit(n, to) for n in nodes[first:])
    return True


#: What `trace` promises and, more importantly, what it does not.
TRACE_CAVEAT = (
    "This is a reading list, not an answer. CDP has no parameter or branch model: "
    "it collapses a wide grep into a small cited read whose completeness is stated "
    "by the `elided` count below — zero means the list is complete, anything else "
    "means it is qualified. Hops marked `medium` come from the import table: an "
    "import proves that a file *can* reach a symbol, not that it does."
)


#: Files a class term (`trace TenantController`) may list. A class is not one entry point: it
#: is every public member, and the union of their chains is most of a codebase. Each member is
#: walked, nearest edges first and round-robin across members, until this many files; the rest
#: are counted in `capped`, never dropped silently.
CLASS_TRACE_FILES = 40


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

    A route path shared by several verbs is walked once per verb, from that verb's handler
    member (`VERB /path` narrows to one); a class term is walked once per public member and
    capped at `CLASS_TRACE_FILES`. Files reached only through the class's imports, which no
    member's calls justify, come last and are tagged as class-level.
    """
    budget = budget or Budget()
    adjacency: Dict[str, List[Dict]] = {}
    for edge in store.dataflow["edges"]:
        adjacency.setdefault(edge["source"], []).append(edge)
    resolved = resolve_entry(store, entry, adjacency)
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

    # Entry points are named by whatever recorded them — a route as
    # `Class#method`, a dataflow source as its own node — while the edge graph
    # is keyed on the file's primary symbol. Left unnormalised, a real endpoint
    # on the validation target traced to exactly one file, which reads as "this
    # endpoint touches nothing" rather than "the key did not match".
    _pivot(store, resolved, adjacency)
    walks = _walks(resolved, adjacency, max_hops)
    reached: Dict[str, Dict] = {}
    for _tag, got, _ in walks:
        for node, edge in got.items():
            reached.setdefault(node, edge)
    exhausted = any(ex for _, _, ex in walks)
    callers = store.xref["used_by"].get(resolved["node"], [])

    rows = _merge_rows(store, resolved, walks, callers)
    # The entry point itself is never budgeted away, and the same holds for
    # role exclusion: the caller named it explicitly, so dropping it would be
    # more surprising than a stray test-role hop further down the trail.
    n_entry = sum(1 for r in rows if r["why"].startswith("entry point"))
    head, rest = rows[:n_entry], rows[n_entry:]
    if exclude_role:
        roles = _role_index(store)
        rest = [r for r in rest if roles.get(r["file"]) not in exclude_role]
    capped = None
    if resolved.get("scope") == "class":
        cap = max(0, CLASS_TRACE_FILES - len(head))
        capped = {"cap": CLASS_TRACE_FILES, "members": len(resolved["members"]),
                  "classes": len(resolved["classes"]), "reachable": len(head) + len(rest),
                  "elided": max(0, len(rest) - cap)}
        budget.elided += capped["elided"]
        rest = rest[:cap]
    files = head + budget.take_head(rest)
    paths_shown = {row["file"] for row in files}

    unknowns = budget.take([
        u for u in store.state.get("unknowns", [])
        if (u.get("anchor") or {}).get("file") in paths_shown
        or any(_matches(u.get("question", ""), n.rsplit(".", 1)[-1]) for n in reached)
    ])

    result = {
        "query": "trace",
        "entry": entry,
        "found": True,
        "resolved_as": {k: v for k, v in resolved.items() if k not in ("handlers", "members", "classes")},
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
    }
    if resolved.get("handlers"):
        result["verbs"] = [h["verb"] for h in resolved["handlers"]]
    if capped:
        result["capped"] = capped
        result["resolved_as"]["members"] = resolved["members"]
        result["resolved_as"]["classes"] = resolved["classes"]
    result = _finish(result, store, budget)
    if capped and capped["elided"]:
        # Printed in the footer in place of "--budget <bigger N>": a bigger budget does not lift the cap.
        result["budget_note"] = ("class term capped at %d files (%d reachable): `--budget` does not lift "
                                 "it; trace one member (`Class#method`) or a route." % (capped["cap"], capped["reachable"]))
    return result


def _walks(resolved: Dict, adjacency: Dict[str, List[Dict]], max_hops: int) -> List[Tuple[Optional[str], Dict, bool]]:
    """`(tag, reached, exhausted)` per start: one per verb handler of a route, one per public
    member of a class, then the class-level walk (tag None) from the file's primary symbol."""
    starts: List[Tuple[Optional[str], str]] = []
    for h in resolved.get("handlers", ()):
        if h["handler"] in adjacency:
            starts.append((h["verb"], h["handler"]))
    for member in resolved.get("members", ()):
        starts.append((member.rsplit("#", 1)[-1], member))
    starts.append((None, resolved["node"]))
    out = []
    for tag, node in starts:
        got, exhausted = _walk(node, adjacency, max_hops)
        out.append((tag, got, exhausted))
    return out


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
                reached[target] = dict(edge, hop=hops)
                nxt.append(target)
        frontier = nxt
    return reached, bool(frontier)


_ACCESSOR = re.compile(r"#(?:get|set|is|has)[A-Z]\w*$|#(?:toString|equals|hashCode|builder|build|<init>)$")
_ACCESSOR_MAX_LINES = 3


def _is_boilerplate(store: Store, target: str) -> bool:
    """A getter, setter or `toString`: named like one and no longer than a few
    lines. Extent matters because `getInstance` or `getConnection` carry logic."""
    if not _ACCESSOR.search(target):
        return False
    for site in store.xref["symbols"].get(target, {}).get("sites", [])[:1]:
        end = site.get("end_line")
        return end is None or end - site["anchor"]["line"] <= _ACCESSOR_MAX_LINES
    return True


def _edge_rows(store: Store, reached: Dict[str, Dict]) -> List[Dict]:
    """One row per file a walk reached, each with the edge that justified it, nearest first.

    Plain accessors go last: a reading list is cut from the end, and a getter should go
    before the service that matters."""
    rows: List[Dict] = []
    seen: Set[str] = set()

    def add(path: Optional[str], module: Optional[str], why: str,
            at: Optional[str], confidence: str) -> None:
        if not path or path in seen:
            return
        seen.add(path)
        rows.append({"file": path, "module": module, "why": why, "at": at,
                     "confidence": confidence})

    order = sorted(reached, key=lambda t: (_is_boilerplate(store, t), reached[t].get("hop", 0), t))
    for target in order:
        edge = reached[target]
        add(edge["anchor"]["file"], edge.get("module"),
            "%s --%s--> %s" % (edge["source"].rsplit(".", 1)[-1], edge["channel"],
                               target.rsplit(".", 1)[-1]),
            cite(edge["anchor"]), edge.get("confidence", "medium"))
        for site in store.xref["symbols"].get(target, {}).get("sites", []):
            why = "defines %s" % target
            if edge["channel"] == "event":
                # The subscriber is reached through the event type it handles, not by a call.
                why = "%s --event--> %s (subscribes to an event %s posts)" % (
                    edge["source"].rsplit(".", 1)[-1], target.rsplit(".", 1)[-1],
                    edge["source"].rsplit(".", 1)[-1])
            add(site["file"], site["module"], why, cite(site["anchor"]), "high")
    return rows


def _merge_rows(store: Store, resolved: Dict, walks: Sequence, callers: Sequence[Dict]) -> List[Dict]:
    """Entry rows, then the walks' rows interleaved (nearest of each walk first), then callers.

    Deduplicated on the file, because a reading list that names the same file three times for
    three edges is longer than the grep it replaced. A file keeps the tags (verbs of a route,
    members of a class) of every walk that reached it; a file only the class-level walk reached
    is tagged `scope: class` and, for a route, with every verb."""
    rows: List[Dict] = []
    by_file: Dict[str, Dict] = {}
    handlers = resolved.get("handlers", ())
    verbs = [h["verb"] for h in handlers]
    tag_key = "verbs" if handlers else "members"
    # Tags say which verb/member reaches a file; with one verb and no member walks there is
    # nothing to tell apart, so none are written.
    tagged = len(handlers) > 1 or any(t is not None for t, _, _ in walks) and not handlers

    def entry(path: Optional[str], module: Optional[str], why: str, at: Optional[str]) -> None:
        if path and path not in by_file:
            row = {"file": path, "module": module, "why": why, "at": at, "confidence": "high"}
            by_file[path] = row
            rows.append(row)

    if handlers:
        # One entry row per handler file, naming every verb served from it.
        per_file: Dict[str, List[Dict]] = {}
        for h in handlers:
            per_file.setdefault((h["at"] or "").rsplit(":", 1)[0], []).append(h)
        path_part = resolved["label"].split(" ", 1)[-1]
        for path, hs in per_file.items():
            entry(path or None, hs[0]["module"],
                  "entry point (http_in) %s %s" % (",".join(h["verb"] for h in hs), path_part), hs[0]["at"])
            if path in by_file:
                by_file[path]["verbs"] = [h["verb"] for h in hs]
    else:
        entry((resolved.get("at") or "").rsplit(":", 1)[0] or None, resolved.get("module"),
              "entry point (%s) %s" % (resolved["channel"], resolved["label"]), resolved.get("at"))
    for row in rows:
        if tagged:
            row["scope"] = "entry"
        else:
            row.pop("verbs", None)

    lists = [(tag, _edge_rows(store, got)) for tag, got, _ in walks]
    depth = max((len(r) for _, r in lists), default=0)
    for i in range(depth):
        for tag, got in lists:
            if i >= len(got):
                continue
            cand = got[i]
            row = by_file.get(cand["file"])
            if row is None:
                row = dict(cand, scope="class" if tag is None else "member") if tagged else dict(cand)
                by_file[cand["file"]] = row
                rows.append(row)
            if tag is not None and tagged:
                if tag not in row.setdefault(tag_key, []):
                    row[tag_key].append(tag)
                if row["scope"] == "class":
                    row["scope"] = "member"
    for row in rows:
        if tagged and row["scope"] == "class" and handlers:
            row["verbs"] = list(verbs)

    for caller in callers:
        path = caller["file"]
        if path in by_file:
            continue
        row = {"file": path, "module": caller["module"],
               "why": "references %s" % resolved["node"].rsplit(".", 1)[-1],
               "at": cite(caller["anchor"]), "confidence": "high"}
        if tagged:
            row["scope"] = "class"
            if handlers:
                row["verbs"] = list(verbs)
        by_file[path] = row
        rows.append(row)
    return rows
