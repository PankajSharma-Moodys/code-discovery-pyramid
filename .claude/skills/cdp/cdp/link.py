"""Phase 8 (M8.1) -- cross-snapshot channel matching (5.1, 5.4, 5.5).

`scan` writes, `link` reads (R3). This module never mutates a snapshot's own
`dataflow.json`/`state.json`; it reads several snapshots' already-computed
`dataflow.edges` and produces a *separate* link report matching `http_out` to
`http_in`, `event_publish` to `event_subscribe`, and `persist` to `schema_own`
across them.

Links are between snapshots, not repos (5.5): each side of a link names the
`(repo, head)` pair it was scanned at, not just a repo name, so a link is
re-verifiable against the exact tree it was computed from.

**A snapshot is exploded by its own edges' `module` field before matching**
(`_explode_by_module`). A single `cdp scan --repo <monorepo>` already produces
one `dataflow.json` whose edges are pooled across every module it found, each
one tagged with the module it came from (`dataflow.py`'s `row["module"]`) --
that tag already exists regardless of whether the repo was scanned whole or
one module at a time. Matching only ever across whole snapshots (as a first
version of this module did) meant a single full-repo scan could never surface
a link between two of its own modules, which defeats the point for anyone who
scans a monorepo once rather than one module at a time. Exploding first makes
both cases the same code path: two separately-scanned single-module repos are
just two one-module explosions; a 63-module monorepo scan is 63. `self_link`
is therefore `(repo, head, module)` equality, not just `(repo, head)` -- two
edges in different modules of the *same* scan are a real cross-module link,
not a self-link.

`library:`-prefixed targets (`dataflow.py`'s own `LIBRARY_PREFIX`) are excluded
from matching for the same reason `dataflow.py` excludes them from traversal:
they name a package, not a place data goes, and today they are the *only*
targets `event_publish`/`event_subscribe` edges ever carry (no extractor in
this codebase emits a topic-specific event edge) -- matching them would produce
links between import statements, not services.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Sequence, Tuple

from .util import stable_hash

LIBRARY_PREFIX = "library:"

# M8.3 (5.2): the closed verdict vocabulary a link-task patch may state --
# mirrors the closed `needs_*` vocabulary's own shape (gates.py), not a free
# string an agent could widen.
VERDICTS = {"match", "no_match", "uncertain"}

# Directional pairs this scan matches. `persist -> schema_own` is written last
# because it is the most common self-link in a single monolith (a module
# persists to a table its own migration owns) -- exercising the "self-link is
# valid" stress test even with only one snapshot registered.
DIRECTIONS = [
    ("http_out", "http_in"),
    ("event_publish", "event_subscribe"),
    ("persist", "schema_own"),
]

_ROUTE_PARAM_RE = re.compile(r"\{[^{}]*\}|:[A-Za-z_][A-Za-z0-9_]*")
_URL_PATH_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*://[^/]+(/.*)?$")


def _path_of(channel: str, target: str) -> str:
    """The bare path/table a raw edge target names, verb/scheme/host stripped."""
    if channel == "http_in":
        # "route:GET /orders/{id}" -> "/orders/{id}"
        path = target.split(" ", 1)[1] if " " in target else target
        path = path[len("route:"):] if path.startswith("route:") else path
    elif channel == "http_out":
        raw = target[len("http:"):] if target.startswith("http:") else target
        m = _URL_PATH_RE.match(raw)
        path = (m.group(1) or "/") if m else raw
    else:
        path = target
    return path.lower() if channel in ("persist", "schema_own") else path


def _normalise(channel: str, target: str) -> str:
    """The key two edges must share to be considered a match at all. Path
    params (`{id}`, `:id`) become `*` so `/orders/{id}` and `/orders/:id`
    compare equal -- the ambiguity is real (5.7's stress test: "path alone is
    ambiguous"), this only removes syntactic noise, not the ambiguity itself.

    HTTP channels only: a `table:`/`entity:` target is a single flat token,
    not a URL path, and the same `:identifier` pattern that denotes a path
    param in a route also matches that token's own `prefix:name` separator --
    applying it there collapsed every distinct table name onto one key
    (found live against two real modules of $TARGET_REPO, F-link1).
    """
    path = _path_of(channel, target)
    if channel in ("http_in", "http_out"):
        path = _ROUTE_PARAM_RE.sub("*", path)
    return path


def _is_library(target: str) -> bool:
    return target.startswith(LIBRARY_PREFIX)


def _edges_for(snapshot: Dict, channel: str) -> List[Dict]:
    out = []
    for edge in snapshot["dataflow"].get("edges", []):
        if edge["channel"] != channel or _is_library(edge["target"]):
            continue
        out.append(edge)
    return out


def _side(snapshot: Dict, edge: Dict) -> Dict:
    return {
        "repo": snapshot["repo"],
        "head": snapshot["head"],
        "module": snapshot["module"],
        "node": edge["source"],
        "target": edge["target"],
        "anchor": edge["anchor"],
    }


def _explode_by_module(snapshot: Dict) -> List[Dict]:
    """One `(repo, head)` snapshot's pooled edges, split into one pseudo-
    snapshot per `module` tag its edges already carry. An edge with no module
    (rare -- files outside any detected module) groups under `"?"` rather than
    being dropped.
    """
    by_module: Dict[str, List[Dict]] = {}
    for edge in snapshot["dataflow"].get("edges", []):
        by_module.setdefault(edge.get("module") or "?", []).append(edge)
    return [
        {"repo": snapshot["repo"], "head": snapshot["head"], "module": module,
         "dataflow": {"edges": edges}}
        for module, edges in by_module.items()
    ]


def scan_links(snapshots: Sequence[Dict]) -> Dict:
    """`snapshots`: `[{"repo": str, "head": str, "dataflow": <dataflow.json>}, ...]`.

    Each snapshot is exploded into one pseudo-snapshot per module before
    matching (see module docstring), so a single whole-monorepo scan and N
    separately-scanned single-module repos take the same code path below.

    Returns a link report: `links` (matched pairs, `match_kind` in
    `exact`/`heuristic`), `unmatched` (an outbound edge with no inbound
    counterpart in *any* registered snapshot -- 5.6, a deliverable, not a
    matcher failure), and `totals`.
    """
    exploded: List[Dict] = []
    for snap in snapshots:
        exploded.extend(_explode_by_module(snap))

    links: List[Dict] = []
    matched_out_keys = set()

    for out_channel, in_channel in DIRECTIONS:
        inbound_index: Dict[str, List[Tuple[int, Dict]]] = {}
        for si, snap in enumerate(exploded):
            for edge in _edges_for(snap, in_channel):
                key = _normalise(in_channel, edge["target"])
                inbound_index.setdefault(key, []).append((si, edge))

        for so, snap in enumerate(exploded):
            for edge in _edges_for(snap, out_channel):
                key = _normalise(out_channel, edge["target"])
                out_id = (so, out_channel, edge["source"], edge["target"], edge["anchor"]["line"])
                candidates = inbound_index.get(key, [])
                if not candidates:
                    continue
                matched_out_keys.add(out_id)
                out_path = _path_of(out_channel, edge["target"])
                for si, in_edge in candidates:
                    in_path = _path_of(in_channel, in_edge["target"])
                    kind = "exact" if out_path == in_path else "heuristic"
                    callee = exploded[si]
                    links.append(
                        {
                            "protocol": out_channel,
                            "match_kind": kind,
                            "self_link": snap["repo"] == callee["repo"]
                            and snap["head"] == callee["head"]
                            and snap["module"] == callee["module"],
                            "caller": _side(snap, edge),
                            "callee": _side(callee, in_edge),
                        }
                    )

    unmatched: List[Dict] = []
    for out_channel, _ in DIRECTIONS:
        for so, snap in enumerate(exploded):
            for edge in _edges_for(snap, out_channel):
                out_id = (so, out_channel, edge["source"], edge["target"], edge["anchor"]["line"])
                if out_id in matched_out_keys:
                    continue
                unmatched.append({"protocol": out_channel, "outbound": _side(snap, edge)})

    links.sort(key=lambda l: (l["protocol"], l["caller"]["repo"], l["caller"]["anchor"]["file"],
                               l["caller"]["anchor"]["line"]))
    unmatched.sort(key=lambda u: (u["protocol"], u["outbound"]["repo"], u["outbound"]["anchor"]["file"],
                                  u["outbound"]["anchor"]["line"]))

    return {
        "snapshots": [{"repo": s["repo"], "head": s["head"]} for s in snapshots],
        "links": links,
        "unmatched": unmatched,
        "totals": {
            "snapshots": len(snapshots),
            "modules": len(exploded),
            "links": len(links),
            "exact": sum(1 for l in links if l["match_kind"] == "exact"),
            "heuristic": sum(1 for l in links if l["match_kind"] == "heuristic"),
            "unmatched": len(unmatched),
        },
    }


def query_service(edges: Sequence[Dict], service: str) -> Dict:
    """M8.2 (5.6): `edges` is `SqliteStore.read_link_edges()`'s return value --
    persisted rows from the last `link scan --db`, each `{"kind": "link"|
    "unmatched", "data": <link or unmatched dict from scan_links>}`.

    Filters to what touches `service` (a repo name/identifier, matched
    literally against `caller`/`callee`/`outbound`'s `repo` field): every link
    where `service` calls or is called, and every unmatched outbound call
    `service` itself makes -- rendered as a deliverable (5.6), not folded into
    "no results".
    """
    links = [e["data"] for e in edges if e["kind"] == "link"
             and (e["data"]["caller"]["repo"] == service or e["data"]["callee"]["repo"] == service)]
    unmatched = [e["data"] for e in edges if e["kind"] == "unmatched"
                 and e["data"]["outbound"]["repo"] == service]
    return {"service": service, "links": links, "unmatched": unmatched}


def summarise_query(result: Dict) -> List[str]:
    service = result["service"]
    lines = ["link query %s: %d link(s), %d unmatched outbound call(s)"
             % (service, len(result["links"]), len(result["unmatched"]))]
    for link in result["links"]:
        direction = "calls" if link["caller"]["repo"] == service else "called by"
        other = link["callee"] if link["caller"]["repo"] == service else link["caller"]
        lines.append(
            "  %-6s %s [%s] %s %s:%d [%s%s]"
            % (link["protocol"], direction, other["repo"], other["target"],
               other["anchor"]["file"], other["anchor"]["line"], link["match_kind"],
               ", self" if link["self_link"] else "")
        )
    if result["unmatched"]:
        lines.append("unmatched %d outbound call(s) from %s with no registered callee:"
                      % (len(result["unmatched"]), service))
        for u in result["unmatched"]:
            o = u["outbound"]
            lines.append("  %-6s %s %s:%d" % (u["protocol"], o["target"], o["anchor"]["file"], o["anchor"]["line"]))
    return lines


def _link_id(link: Dict) -> str:
    """A stable identifier for one candidate pairing, independent of list
    position, so `collect` can find the same link again after a report has
    been read back from the store and possibly reordered."""
    return stable_hash({
        "protocol": link["protocol"], "caller": link["caller"], "callee": link["callee"],
    })[:16]


def build_tasks(report: Dict) -> List[Dict]:
    """M8.3 (5.2): the LLM tier fires only on ambiguous matches. `scan_links`
    already names the ambiguous case at scan time -- `match_kind == "heuristic"`
    (the normalised key matched; the raw path/topic/table did not) -- so no
    second ambiguity detector is invented here, one already exists.

    One task per *distinct caller target string*, not per link: the stress
    test ("a topic built by string concatenation in three places... must not
    become three unrelated tasks") means several call sites sharing one raw
    ambiguous string are one question, answered once. `report["links"]`
    already carries every candidate callee for that string as a separate
    entry (multiple inbound matches on the same normalised key), so grouping
    by `(protocol, caller.target)` collects them all under one task.
    """
    groups: Dict[Tuple[str, str], List[Dict]] = {}
    for link in report["links"]:
        if link["match_kind"] != "heuristic":
            continue
        key = (link["protocol"], link["caller"]["target"])
        groups.setdefault(key, []).append(link)

    tasks = []
    for (protocol, target), links in sorted(groups.items()):
        task_id = "link-" + stable_hash({"protocol": protocol, "target": target})[:16]
        tasks.append({
            "task_id": task_id,
            "protocol": protocol,
            "target": target,
            "candidates": [
                {"link_id": _link_id(link), "caller": link["caller"], "callee": link["callee"]}
                for link in links
            ],
        })
    return tasks


def render_task_prompt(task: Dict) -> str:
    lines = [
        "# Link task %s" % task["task_id"],
        "",
        "Protocol: %s" % task["protocol"],
        "Ambiguous target (same raw string, matched only after path-param",
        "normalisation, at every site below): `%s`" % task["target"],
        "",
        "For EACH candidate below, decide whether the caller genuinely calls",
        "that callee. Cite only anchors already shown here -- do not invent one.",
        "",
    ]
    for c in task["candidates"]:
        caller, callee = c["caller"], c["callee"]
        lines.append("## candidate %s" % c["link_id"])
        lines.append("  caller  [%s] %s %s %s:%d" % (
            caller["repo"], caller["module"], caller["target"],
            caller["anchor"]["file"], caller["anchor"]["line"]))
        lines.append("  callee  [%s] %s %s %s:%d" % (
            callee["repo"], callee["module"], callee["target"],
            callee["anchor"]["file"], callee["anchor"]["line"]))
        lines.append("")
    lines.append(
        "Respond with a JSON patch: {\"task_id\": %r, \"resolutions\": "
        "[{\"link_id\": ..., \"verdict\": \"match\"|\"no_match\"|\"uncertain\", "
        "\"reason\": str, \"anchor\": {\"file\": str, \"line\": int}}]}. "
        "`anchor` must be one of the caller/callee anchors shown above -- a "
        "citation not shown here is rejected, not trusted." % task["task_id"]
    )
    return "\n".join(lines)


def validate_task_patch(patch: Dict, task: Dict) -> List[str]:
    """M8.3's validate+verify+entail step, kept in one function since a link
    patch is a handful of fields, not a full claim: schema shape, the closed
    verdict vocabulary (validate), then a citation check -- every `anchor` in
    the response must equal a caller or callee anchor this task actually
    showed the model (entail: no fabricated citation is trusted, the same
    spirit as Phase 4's negative-entailment gate, applied to a cross-repo
    verdict instead of a single repo's extraction index).
    """
    errors: List[str] = []
    if patch.get("task_id") != task["task_id"]:
        errors.append("/task_id: %r does not match task %r" % (patch.get("task_id"), task["task_id"]))
        return errors
    resolutions = patch.get("resolutions")
    if not isinstance(resolutions, list) or not resolutions:
        errors.append("/resolutions: must be a non-empty list")
        return errors
    known_links = {c["link_id"]: c for c in task["candidates"]}
    known_anchors = set()
    for c in task["candidates"]:
        known_anchors.add((c["caller"]["anchor"]["file"], c["caller"]["anchor"]["line"]))
        known_anchors.add((c["callee"]["anchor"]["file"], c["callee"]["anchor"]["line"]))
    for i, res in enumerate(resolutions):
        if res.get("link_id") not in known_links:
            errors.append("/resolutions/%d/link_id: %r is not a candidate this task showed"
                           % (i, res.get("link_id")))
            continue
        if res.get("verdict") not in VERDICTS:
            errors.append("/resolutions/%d/verdict: %r is not one of %s"
                           % (i, res.get("verdict"), sorted(VERDICTS)))
        if not res.get("reason"):
            errors.append("/resolutions/%d/reason: required" % i)
        anchor = res.get("anchor") or {}
        if (anchor.get("file"), anchor.get("line")) not in known_anchors:
            errors.append("/resolutions/%d/anchor: %r was not shown to the model for this task -- "
                           "fabricated citation rejected" % (i, anchor))
    return errors


def fold_resolutions(report: Dict, task: Dict, patch: Dict, run_id: str) -> int:
    """Attributes each valid resolution onto its link in `report["links"]` by
    `link_id`. Never touches `match_kind` (M8.1's closed vocabulary, already
    shipped and tested) -- adds a `resolution` field alongside it, so an
    adjudicated heuristic link is still queryable by its original
    classification plus what the LLM tier decided about it. Returns the
    count folded.
    """
    by_id = {_link_id(link): link for link in report["links"]}
    n = 0
    for res in patch["resolutions"]:
        link = by_id.get(res["link_id"])
        if link is None:
            continue
        link["resolution"] = {
            "verdict": res["verdict"], "reason": res["reason"], "anchor": res["anchor"],
            "task_id": task["task_id"], "author_kind": "llm", "run_id": run_id,
        }
        n += 1
    return n


_INBOUND_OF = dict(DIRECTIONS)  # http_out->http_in, event_publish->event_subscribe, persist->schema_own


def refresh_links(old_report: Dict, new_snapshots: Sequence[Dict]) -> Dict:
    """M8.4 (5.3): re-verify a prior `link scan`'s contracts against freshly
    scanned snapshots for the repos named in `new_snapshots`, mirroring Phase
    3's refresh semantics (D10): a contract whose endpoint still exists in
    the fresh scan carries forward re-anchored to it; one whose endpoint
    vanished decays with a stated reason rather than silently disappearing.

    Only repos named in `new_snapshots` are re-verified. A link or unmatched
    row that touches none of them is returned byte-identical -- 5.5's "the
    other repo's snapshot is unchanged" holds because this function never
    reads or re-derives anything about a repo it wasn't given fresh data for.
    """
    exploded: List[Dict] = []
    for snap in new_snapshots:
        exploded.extend(_explode_by_module(snap))
    refreshed_repos = {snap["repo"] for snap in new_snapshots}

    fresh_edges: Dict[Tuple[str, str, str, str], List[Tuple[Dict, Dict]]] = {}
    for snap in exploded:
        for channel in ("http_out", "http_in", "event_publish", "event_subscribe", "persist", "schema_own"):
            for edge in _edges_for(snap, channel):
                key = (snap["repo"], snap["module"], channel, _normalise(channel, edge["target"]))
                fresh_edges.setdefault(key, []).append((snap, edge))

    def _still_present(side: Dict, channel: str) -> Optional[Tuple[Dict, Dict]]:
        key = (side["repo"], side["module"], channel, _normalise(channel, side["target"]))
        candidates = fresh_edges.get(key)
        return candidates[0] if candidates else None

    links: List[Dict] = []
    for link in old_report["links"]:
        caller, callee = link["caller"], link["callee"]
        if caller["repo"] not in refreshed_repos and callee["repo"] not in refreshed_repos:
            links.append(link)
            continue
        new_link = dict(link)
        decayed_sides = []
        for side_name, channel in (("caller", link["protocol"]), ("callee", _INBOUND_OF[link["protocol"]])):
            side = link[side_name]
            if side["repo"] not in refreshed_repos:
                continue
            found = _still_present(side, channel)
            if found is None:
                decayed_sides.append(side_name)
            else:
                snap, edge = found
                new_link[side_name] = _side(snap, edge)
        if decayed_sides:
            new_link["status"] = "decayed"
            new_link["decay_reason"] = (
                "%s endpoint no longer present after refreshing %s"
                % (" and ".join(decayed_sides),
                   ", ".join(sorted({link[s]["repo"] for s in decayed_sides})))
            )
        else:
            new_link["status"] = "live"
        links.append(new_link)

    unmatched = [u for u in old_report["unmatched"] if u["outbound"]["repo"] not in refreshed_repos]

    fresh_report = scan_links(new_snapshots)
    old_link_ids = {_link_id(l) for l in old_report["links"]}
    for l in fresh_report["links"]:
        if _link_id(l) not in old_link_ids:
            l = dict(l)
            l["status"] = "live"
            links.append(l)
    unmatched.extend(fresh_report["unmatched"])

    links.sort(key=lambda l: (l["protocol"], l["caller"]["repo"], l["caller"]["anchor"]["file"],
                               l["caller"]["anchor"]["line"]))
    unmatched.sort(key=lambda u: (u["protocol"], u["outbound"]["repo"], u["outbound"]["anchor"]["file"],
                                  u["outbound"]["anchor"]["line"]))

    return {
        "refreshed": sorted(refreshed_repos),
        "links": links,
        "unmatched": unmatched,
        "totals": {
            "links": len(links),
            "exact": sum(1 for l in links if l["match_kind"] == "exact"),
            "heuristic": sum(1 for l in links if l["match_kind"] == "heuristic"),
            "decayed": sum(1 for l in links if l.get("status") == "decayed"),
            "unmatched": len(unmatched),
        },
    }


def summarise_refresh(report: Dict) -> List[str]:
    t = report["totals"]
    lines = [
        "link refresh  refreshed %s -- %d link(s) (%d exact, %d heuristic, %d decayed), %d unmatched"
        % (", ".join(report["refreshed"]), t["links"], t["exact"], t["heuristic"], t["decayed"], t["unmatched"])
    ]
    for link in report["links"]:
        if link.get("status") != "decayed":
            continue
        lines.append(
            "  DECAYED %-6s [%s] %s -> [%s] %s -- %s"
            % (link["protocol"], link["caller"]["repo"], link["caller"]["target"],
               link["callee"]["repo"], link["callee"]["target"], link["decay_reason"])
        )
    return lines


def summarise(report: Dict) -> List[str]:
    t = report["totals"]
    lines = [
        "link      %d snapshot(s), %d module(s), %d link(s) (%d exact, %d heuristic), %d unmatched"
        % (t["snapshots"], t["modules"], t["links"], t["exact"], t["heuristic"], t["unmatched"])
    ]
    for link in report["links"]:
        lines.append(
            "  %-6s [%s] %s %s:%d -> [%s] %s %s:%d [%s%s]"
            % (
                link["protocol"],
                link["caller"]["module"],
                link["caller"]["target"],
                link["caller"]["anchor"]["file"],
                link["caller"]["anchor"]["line"],
                link["callee"]["module"],
                link["callee"]["target"],
                link["callee"]["anchor"]["file"],
                link["callee"]["anchor"]["line"],
                link["match_kind"],
                ", self" if link["self_link"] else "",
            )
        )
    if report["unmatched"]:
        lines.append("unmatched %d outbound call(s) with no registered callee:" % len(report["unmatched"]))
        for u in report["unmatched"]:
            o = u["outbound"]
            lines.append("  %-6s %s %s:%d" % (u["protocol"], o["target"], o["anchor"]["file"], o["anchor"]["line"]))
    return lines
