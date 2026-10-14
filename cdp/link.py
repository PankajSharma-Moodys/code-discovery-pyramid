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
they name a package, not a place data goes. Most `event_publish`/`event_subscribe`
edges still carry only a `library:` target, but `java_flow` does emit topic-specific
ones (`event_publish` -> `event:X`, lang/java_flow.py:155) that do match -- matching
the `library:` ones would produce links between import statements, not services.
"""

from __future__ import annotations

import json
from typing import Dict, List, Optional, Sequence, Tuple

from . import linkroute
from .linkid import anchor_of, link_id, reanchor
from .util import CdpError, read_json, stable_hash, write_text
from pathlib import Path
from . import query as query_mod

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

def _path_of(channel: str, target: str) -> str:
    return linkroute.path_of(channel, target)


def _normalise(channel: str, target: str) -> str:
    """The key two edges must share to be considered a match at all. HTTP paths
    compare segment-wise with every param spelling (`{id}`, `:id`, `<int:id>`,
    `${id}`) as `*` (cdp/linkroute.py); table/entity targets are a flat token
    and are never param-normalised (`prefix:name` would collapse -- F-link1)."""
    path = linkroute.path_of(channel, target)
    if channel in ("http_in", "http_out"):
        return linkroute.key_of(linkroute.segments(path))
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
        http = out_channel == "http_out"
        inbound_index: Dict[str, List[Tuple[int, Dict]]] = {}
        routes = linkroute.RouteIndex()
        for si, snap in enumerate(exploded):
            for edge in _edges_for(snap, in_channel):
                if http:
                    routes.add(linkroute.segments(_path_of(in_channel, edge["target"])), (si, edge))
                else:
                    inbound_index.setdefault(_normalise(in_channel, edge["target"]), []).append((si, edge))

        for so, snap in enumerate(exploded):
            for edge in _edges_for(snap, out_channel):
                out_id = (so, out_channel, edge["source"], edge["target"], edge["anchor"]["line"])
                out_path = _path_of(out_channel, edge["target"])
                if http:
                    out_verb = linkroute.verb_of(out_channel, edge["target"])
                    candidates = [c for c in routes.lookup(linkroute.segments(out_path))
                                  if linkroute.verbs_compatible(
                                      out_verb, linkroute.verb_of(in_channel, c[1]["target"]))]
                else:
                    candidates = inbound_index.get(_normalise(out_channel, edge["target"]), [])
                if not candidates:
                    continue
                matched_out_keys.add(out_id)
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


def known_services(edges: Sequence[Dict], extra: Sequence[str] = ()) -> set:
    known = set(extra)
    for e in edges:
        for side in ("caller", "callee", "outbound"):
            if side in e["data"]:
                known.add(e["data"][side]["repo"])
    return known


def _short(repo: str) -> str:
    return repo.rsplit("#", 1)[-1].rstrip("/").rsplit("/", 1)[-1]


def resolve_service(edges: Sequence[Dict], service: str, extra: Sequence[str] = (),
                    names: Optional[Dict[str, Dict]] = None) -> str:
    """A repo is named by its identity (a UUID, `github.com/acme/orders`, or
    `github.com/acme/mono#svc/api` for a folder of one). Nobody types that, so
    `service` may also be the repo's directory name, its checkout path, a unique
    trailing name, or a unique prefix of the identity (`names`: `repo_names()`).
    An exact identity always wins; an ambiguous name resolves to nothing (`link
    query` then reports it rather than guessing)."""
    return _match_service(known_services(edges, extra), service, names)[0] or service


def _match_service(known: set, service: str, names: Optional[Dict[str, Dict]]) -> Tuple[Optional[str], List[str]]:
    """`(identity, [])` for the one repo `service` names, `(None, hits)` otherwise."""
    if service in known:
        return service, []
    names = names or {}
    want = service.rstrip("/")
    as_path = str(Path(want).expanduser().resolve()) if ("/" in want or want.startswith("~")) else None
    tiers = (
        [r for r in known if names.get(r, {}).get("name") == want],
        [r for r in known if as_path and names.get(r, {}).get("path")
         and str(Path(names[r]["path"]).resolve()) == as_path],
        [r for r in known if _short(r) == want],
        [r for r in known if len(want) >= 3 and r.startswith(want)],
    )
    for hits in tiers:
        if len(hits) == 1:
            return hits[0], []
        if hits:
            return None, sorted(hits)
    return None, []


def repo_label(repo: str, names: Optional[Dict[str, Dict]] = None) -> str:
    """What to show for a repo identity: its directory name when known, else the
    identity's trailing part."""
    return (names or {}).get(repo, {}).get("name") or _short(repo)


def repo_names(backend) -> Dict[str, Dict]:
    """`{repo identity: {"name": directory name, "path": checkout path}}` for every
    repo in the store (from each repo's latest inventory)."""
    out: Dict[str, Dict] = {}
    for row in backend.latest_snapshots():
        backend.use_snapshot(row["repo_id"], row["commit_sha"])
        inv = backend.read_artifact("inventory", {}) or {}
        path = inv.get("repo")
        out[row["repo_id"]] = {"name": inv.get("repo_name") or (Path(path).name if path else None),
                               "path": path}
    return out


def snapshots_from_store(backend) -> List[Dict]:
    """One link snapshot per repo in the store: the snapshot that answers for that
    repo's tree (`snapshot.choose_snapshot`: HEAD or its nearest clean ancestor,
    never a dirty scan or another branch). A repo whose checkout is gone falls back
    to its newest clean snapshot; a repo with no qualifying snapshot is skipped."""
    from pathlib import Path
    from .snapshot import choose_snapshot

    everything = backend.list_snapshots()
    out: List[Dict] = []
    for row in backend.latest_snapshots():
        repo_id = row["repo_id"]
        mine = [s for s in everything if s.get("repo_id") == repo_id]
        clean = [s for s in mine if not s["ephemeral"]]
        backend.use_snapshot(repo_id, (clean[-1] if clean else row)["commit_sha"])
        repo_path = (backend.read_artifact("inventory", {}) or {}).get("repo")
        pick = clean[-1] if clean else None
        if repo_path and Path(repo_path).is_dir():
            choice = choose_snapshot(Path(repo_path), repo_id, mine)
            pick = choice.row
        if pick is None:
            continue
        backend.use_snapshot(repo_id, pick["commit_sha"])
        dataflow = backend.read_artifact("dataflow", None)
        if dataflow is None:
            continue
        manifest = backend.read_artifact("manifest", {}) or {}
        out.append({"repo": repo_id, "head": manifest.get("head") or pick["commit_sha"],
                    "dataflow": dataflow})
    return out


def require_known_service(edges: Sequence[Dict], service: str, extra: Sequence[str] = (),
                          names: Optional[Dict[str, Dict]] = None) -> None:
    """A service no scanned repo goes by is an error (exit non-zero), not an empty answer;
    the message lists the names a service may be given as."""
    known = known_services(edges, extra)
    found, hits = _match_service(known, service, names)
    if found:
        return
    label = lambda r: repo_label(r, names)
    if hits:
        raise CdpError("service %r is ambiguous: it could be %s -- give a longer prefix or the full identity"
                       % (service, ", ".join("%s (%s)" % (label(r), r) for r in hits)))
    raise CdpError("unknown service %r: no scanned repo has that name (known: %s)"
                   % (service, ", ".join(sorted("%s (%s)" % (label(r), r) if label(r) != r else r for r in known))
                      or "none"))


def query_service(edges: Sequence[Dict], service: str, extra: Sequence[str] = (),
                  names: Optional[Dict[str, Dict]] = None) -> Dict:
    """M8.2 (5.6): `edges` is `SqliteStore.read_link_edges()`'s return value --
    persisted rows from the last `link scan --db`, each `{"kind": "link"|
    "unmatched", "data": <link or unmatched dict from scan_links>}`.

    Filters to what touches `service` (a repo name/identifier, matched
    literally against `caller`/`callee`/`outbound`'s `repo` field): every link
    where `service` calls or is called, and every unmatched outbound call
    `service` itself makes -- rendered as a deliverable (5.6), not folded into
    "no results".
    """
    service = resolve_service(edges, service, extra, names)
    links = [e["data"] for e in edges if e["kind"] == "link"
             and (e["data"]["caller"]["repo"] == service or e["data"]["callee"]["repo"] == service)]
    unmatched = [e["data"] for e in edges if e["kind"] == "unmatched"
                 and e["data"]["outbound"]["repo"] == service]
    return {"service": service, "links": links, "unmatched": unmatched}


def _where(side: Dict) -> str:
    return "%s:%d" % (side["anchor"]["file"], side["anchor"]["line"])


def _tags(link: Dict) -> str:
    res = link.get("resolution")
    return "%s%s%s" % (link["match_kind"], ", self" if link["self_link"] else "",
                       ", %s" % res["verdict"] if res else "")


def summarise_query(result: Dict, names: Optional[Dict[str, Dict]] = None) -> List[str]:
    """Each link as `caller -> callee`, both ends named; `calls`/`called by` says which end the
    queried service is."""
    service = result["service"]
    lines = ["link query %s: %d link(s), %d unmatched outbound call(s)"
             % (repo_label(service, names), len(result["links"]), len(result["unmatched"]))]
    for link in result["links"]:
        caller, callee = link["caller"], link["callee"]
        direction = "calls" if caller["repo"] == service else "called by"
        lines.append("  %-6s %s: [%s] %s %s -> [%s] %s %s [%s]"
                     % (link["protocol"], direction, repo_label(caller["repo"], names), caller["target"],
                        _where(caller), repo_label(callee["repo"], names), callee["target"], _where(callee),
                        _tags(link)))
    if result["unmatched"]:
        lines.append("unmatched %d outbound call(s) from %s with no registered callee:"
                      % (len(result["unmatched"]), repo_label(service, names)))
        for u in result["unmatched"]:
            o = u["outbound"]
            lines.append("  %-6s %s %s" % (u["protocol"], o["target"], _where(o)))
    return lines


_link_id = link_id  # one id per pairing across scans and commits (cdp/linkid.py)


def _candidates(links: List[Dict]) -> List[Dict]:
    """One candidate per link id, listing every call site (and callee site) that shares it: two
    calls to one endpoint from one method are one pairing with two sites, not one dropped."""
    by_id: Dict[str, Dict] = {}
    for link in links:
        c = by_id.setdefault(_link_id(link), {"link_id": _link_id(link), "caller": link["caller"],
                                              "callee": link["callee"], "caller_sites": [], "callee_sites": []})
        for key, side in (("caller_sites", "caller"), ("callee_sites", "callee")):
            site = anchor_of(link[side])
            if site not in c[key]:
                c[key].append(site)
    for c in by_id.values():
        for key in ("caller_sites", "callee_sites"):
            c[key].sort(key=lambda a: (a["file"], a["line"]))
    return list(by_id.values())


def build_tasks(report: Dict, unresolved_only: bool = False) -> List[Dict]:
    """M8.3 (5.2): the LLM tier fires only on ambiguous matches. `scan_links`
    already names the ambiguous case at scan time -- `match_kind == "heuristic"`
    -- so no second ambiguity detector is invented here.

    One task per *distinct caller target string*, not per link: several call
    sites sharing one raw ambiguous string are one question, answered once.
    With `unresolved_only`, a link that already has a verdict is left out (a task
    whose every link has one disappears), so nothing is asked twice.
    """
    groups: Dict[Tuple[str, str], List[Dict]] = {}
    for link in report["links"]:
        if link["match_kind"] != "heuristic" or (unresolved_only and link.get("resolution")):
            continue
        groups.setdefault((link["protocol"], link["caller"]["target"]), []).append(link)

    tasks = []
    for (protocol, target), links in sorted(groups.items()):
        task_id = "link-" + stable_hash({"protocol": protocol, "target": target})[:16]
        tasks.append({"task_id": task_id, "protocol": protocol, "target": target,
                      "candidates": _candidates(links)})
    return tasks


def _example_patch(task: Dict) -> Dict:
    c = task["candidates"][0]
    return {"task_id": task["task_id"], "resolutions": [
        {"link_id": c["link_id"], "verdict": "match", "reason": "one sentence of evidence",
         "anchor": c["caller_sites"][0]}]}


def render_task_prompt(task: Dict) -> str:
    lines = [
        "# Link task %s" % task["task_id"],
        "",
        "Protocol: %s" % task["protocol"],
        "Ambiguous target (same raw string, matched only after path-param",
        "normalisation or a missing context prefix, at every site below): `%s`" % task["target"],
        "",
        "For EACH candidate below, decide whether the caller genuinely calls",
        "that callee. Cite only anchors already shown here -- do not invent one.",
        "",
    ]
    for c in task["candidates"]:
        caller, callee = c["caller"], c["callee"]
        lines.append("## candidate %s" % c["link_id"])
        for label, side, sites in (("caller", caller, c["caller_sites"]), ("callee", callee, c["callee_sites"])):
            lines.append("  %s  [%s] %s %s %s" % (label, side["repo"], side["module"], side["target"],
                                                 ", ".join("%s:%d" % (a["file"], a["line"]) for a in sites)))
        lines.append("")
    lines.append("Respond with exactly one JSON object, no other keys, e.g.:")
    lines.append("")
    lines.append(json.dumps(_example_patch(task), indent=2))
    lines.append("")
    lines.append(
        "`verdict` is one of match, no_match, uncertain. `anchor` is {repo, file, line} of one "
        "caller or callee site of THAT candidate, as shown above (repo is optional; if given it "
        "must be that site's repo). One resolution per candidate. A citation not shown here, or "
        "from another repo, is rejected."
    )
    return "\n".join(lines)


def _line_of(value) -> Optional[int]:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def _repo_matches(cited: str, repo: str) -> bool:
    return cited == repo or cited == _short(repo)


PATCH_KEYS = {"task_id", "resolutions"}
RESOLUTION_KEYS = {"link_id", "verdict", "reason", "anchor"}
ANCHOR_KEYS = {"repo", "file", "line"}


def validate_task_patch(patch: Dict, task: Dict) -> List[str]:
    """M8.3's validate+verify+entail step: closed schema (an unknown key is an error), the closed
    verdict vocabulary, one resolution per link (a repeat with another verdict is a contradiction),
    and a citation that is one of THAT link's own sites -- repo, file and line (a numeric string
    line is accepted). No fabricated or wrong-repo citation is trusted."""
    errors: List[str] = []
    if not isinstance(patch, dict):
        return ["/: a link patch is a JSON object, got %s" % type(patch).__name__]
    if patch.get("task_id") != task["task_id"]:
        return ["/task_id: %r does not match task %r" % (patch.get("task_id"), task["task_id"])]
    for key in sorted(set(patch) - PATCH_KEYS):
        errors.append("/%s: unknown key (allowed: %s)" % (key, ", ".join(sorted(PATCH_KEYS))))
    resolutions = patch.get("resolutions")
    if not isinstance(resolutions, list) or not resolutions:
        return errors + ["/resolutions: must be a non-empty list"]
    known = {c["link_id"]: c for c in task["candidates"]}
    seen: Dict[str, str] = {}
    for i, res in enumerate(resolutions):
        if not isinstance(res, dict):
            errors.append("/resolutions/%d: must be an object, got %s" % (i, type(res).__name__))
            continue
        for key in sorted(set(res) - RESOLUTION_KEYS):
            errors.append("/resolutions/%d/%s: unknown key (allowed: %s)" % (i, key, ", ".join(sorted(RESOLUTION_KEYS))))
        cand = known.get(res.get("link_id")) if isinstance(res.get("link_id"), str) else None
        if cand is None:
            errors.append("/resolutions/%d/link_id: %r is not a candidate this task showed" % (i, res.get("link_id")))
            continue
        if res.get("verdict") not in VERDICTS:
            errors.append("/resolutions/%d/verdict: %r is not one of %s" % (i, res.get("verdict"), sorted(VERDICTS)))
        if not isinstance(res.get("reason"), str) or not res["reason"].strip():
            errors.append("/resolutions/%d/reason: a non-empty string is required" % i)
        if res["link_id"] in seen and seen[res["link_id"]] != res.get("verdict"):
            errors.append("/resolutions/%d/link_id: %r is resolved twice with different verdicts (%s, %s)"
                          % (i, res["link_id"], seen[res["link_id"]], res.get("verdict")))
        seen.setdefault(res["link_id"], res.get("verdict"))
        anchor = res.get("anchor")
        if not isinstance(anchor, dict):
            errors.append("/resolutions/%d/anchor: an object {repo, file, line} is required" % i)
            continue
        for key in sorted(set(anchor) - ANCHOR_KEYS):
            errors.append("/resolutions/%d/anchor/%s: unknown key" % (i, key))
        line = _line_of(anchor.get("line"))
        cited_repo = anchor.get("repo")
        ok = any(a["file"] == anchor.get("file") and a["line"] == line
                 and (cited_repo is None or (isinstance(cited_repo, str) and _repo_matches(cited_repo, a["repo"])))
                 for a in (cand.get("caller_sites") or [anchor_of(cand["caller"])])
                 + (cand.get("callee_sites") or [anchor_of(cand["callee"])]))
        if not ok:
            errors.append("/resolutions/%d/anchor: %r is not a site of this link as shown to the model "
                          "(repo, file and line must all match) -- fabricated citation rejected" % (i, anchor))
    return errors


def _resolution(res: Dict, task: Dict, run_id: str, link: Dict) -> Dict:
    cited = res["anchor"]
    out = {"verdict": res["verdict"], "reason": res["reason"], "task_id": task["task_id"],
           "author_kind": "llm", "run_id": run_id,
           "anchor": {k: v for k, v in (("repo", cited.get("repo")), ("file", cited["file"]),
                                        ("line", _line_of(cited["line"]))) if v is not None}}
    return reanchor(link, out)  # records which end it cites, so it follows that end when it moves


def fold_resolutions(report: Dict, task: Dict, patch: Dict, run_id: str, store=None) -> int:
    """Attributes each valid resolution onto its link in `report["links"]` by
    `link_id`. Never touches `match_kind` -- adds a `resolution` alongside it. A link that already
    has a verdict keeps it (a second answer does not overwrite the first). With `store`, each
    resolution is saved right away, so a later failure in the same run cannot lose it. Returns
    the count newly folded."""
    by_id: Dict[str, List[Dict]] = {}
    for link in report["links"]:
        by_id.setdefault(_link_id(link), []).append(link)
    n = 0
    done = set()
    for res in patch["resolutions"]:
        links = by_id.get(res["link_id"])
        if not links or res["link_id"] in done or any(l.get("resolution") for l in links):
            continue
        done.add(res["link_id"])
        resolution = _resolution(res, task, run_id, links[0])
        for link in links:
            link["resolution"] = resolution
        if store is not None:
            store.save_link_resolution(res["link_id"], resolution)
        n += 1
    return n


def unresolved_tasks(report: Dict) -> List[Dict]:
    """Tasks for the links that have no verdict yet."""
    return build_tasks(report, unresolved_only=True)


def link_task_shape_key(task: Dict) -> str:
    """Post-Phase-9 item 5: `trajectory.scope_shape_key`'s counterpart for a
    link task -- bucketed candidate count plus protocol, coarse for the same
    reason `scope_shape_key` is coarse (M9.2's routing prior groups on this to
    find shape-alike neighbours, which only works if the key generalises)."""
    n = len(task.get("candidates") or [])
    bucket = 1
    while bucket < max(n, 1):
        bucket *= 2
    return "protocol=%s|candidates<=%d" % (task["protocol"], bucket)


def _classify_link_returned(patch_path, task: Dict):
    """`supervisor._classify_returned`'s counterpart for one link task: no
    schema/anchor-liveness check (a link patch has no claims to verify against
    a repo's live source), just `validate_task_patch`'s own closed shape and
    citation check -- a fabricated anchor is already an `/resolutions/.../anchor`
    validation error, not a separate gate."""
    from . import supervisor as supervisor_mod
    if not patch_path.exists():
        return supervisor_mod.EMPTY, "runner returned ok but wrote no patch", None
    try:
        patch = read_json(patch_path)
    except (ValueError, OSError) as exc:
        return supervisor_mod.INVALID, "not valid JSON: %s" % exc, None
    try:
        errors = validate_task_patch(patch, task)
    except Exception as exc:  # noqa: BLE001 -- a malformed patch abandons its own task, nothing else
        return supervisor_mod.INVALID, "malformed patch: %s: %s" % (type(exc).__name__, exc), None
    if errors:
        return supervisor_mod.INVALID, "; ".join(errors[:6]), None
    return supervisor_mod.VALIDATED, None, patch


def reject_patch(patch_path: Path) -> None:
    """Move a failed patch to `inbox/rejected/`, out of the directory `link collect` reads."""
    if patch_path.exists():
        dest = patch_path.parent / "rejected"
        dest.mkdir(exist_ok=True)
        patch_path.replace(dest / patch_path.name)


def dispatch_link_task(
    task: Dict, run_id: str, runner, backend, prompts_dir,
    lease_seconds: float = 90.0, heartbeat_seconds: float = 30.0, max_attempts: int = 3,
) -> Optional[Dict]:
    """Post-Phase-9 item 5: `supervisor.dispatch_scope`'s retry loop, reused
    for one link task instead of a scope -- same states/leases (`link_task`,
    not `snapshot_task`, so R3's non-entanglement holds), so link work is no
    longer invisible to `cdp run`'s wave machinery or to trajectory learning
    (`dim_task_kind=link`). Returns `None` if another supervisor already holds
    this task's lease, the same "not mine to dispatch" convention
    `dispatch_scope` uses."""
    from . import supervisor as supervisor_mod
    task_id = task["task_id"]
    prompt_path = prompts_dir / (task_id + ".md")
    write_text(prompt_path, render_task_prompt(task))
    # Link patches have their own inbox beside their prompts, never the scope inbox `cdp collect` reads.
    patch_path = prompts_dir / "inbox" / (task_id + ".json")
    patch_path.parent.mkdir(parents=True, exist_ok=True)

    state = supervisor_mod.PENDING
    last_error: Optional[str] = None
    patch: Optional[Dict] = None
    attempt = 0
    for attempt in range(1, max_attempts + 1):
        if not backend.acquire_link_lease(run_id, task_id, lease_seconds):
            return None
        try:
            if patch_path.exists():
                patch_path.unlink()
            backend.upsert_link_task(
                run_id, task_id, state=supervisor_mod.DISPATCHED, attempts=attempt,
                dispatched_at=supervisor_mod._now(), last_error=None,
            )
            heartbeat = supervisor_mod._LeaseHeartbeat(
                lambda: backend.heartbeat_link_lease(run_id, task_id, lease_seconds), heartbeat_seconds
            ).start()
            try:
                result = runner.run(prompt_path, patch_path)
            finally:
                heartbeat.stop()
            if not result.ok:
                state, last_error, patch = supervisor_mod.EXPIRED, result.error or "runner reported failure with no message", None
            else:
                backend.upsert_link_task(run_id, task_id, state=supervisor_mod.RETURNED, wall_ms=result.wall_ms)
                state, last_error, patch = _classify_link_returned(patch_path, task)
            backend.upsert_link_task(run_id, task_id, state=state, last_error=last_error, wall_ms=result.wall_ms)
        finally:
            backend.release_link_lease(run_id, task_id)  # whatever happened, the next run may take it
        if state != supervisor_mod.VALIDATED:
            reject_patch(patch_path)  # never left where a later `link collect` could take it
        if state not in supervisor_mod.RETRY_STATES:
            break
    if state in supervisor_mod.RETRY_STATES:
        state = supervisor_mod.ABANDONED
        backend.upsert_link_task(run_id, task_id, state=state, last_error=last_error)
        patch = None
    return {
        "task_id": task_id, "state": state, "attempts": attempt,
        "last_error": last_error, "patch": patch,
    }


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


def summarise(report: Dict, names: Optional[Dict[str, Dict]] = None) -> List[str]:
    t = report["totals"]
    selfs = sum(1 for l in report["links"] if l["self_link"])
    lines = [
        "link      %d snapshot(s), %d module(s), %d link(s) (%d exact, %d heuristic), %d unmatched"
        % (t["snapshots"], t["modules"], t["links"], t["exact"], t["heuristic"], t["unmatched"])
    ]
    if selfs:
        lines.append("          %d of those are `self` links (both ends in the same module: not cross-module); "
                     "%d cross-module" % (selfs, t["links"] - selfs))
    for link in report["links"]:
        caller, callee = link["caller"], link["callee"]
        lines.append("  %-6s caller [%s:%s] %s %s -> callee [%s:%s] %s %s [%s]"
                     % (link["protocol"], repo_label(caller["repo"], names), caller["module"], caller["target"],
                        _where(caller), repo_label(callee["repo"], names), callee["module"], callee["target"],
                        _where(callee), _tags(link)))
    if report["unmatched"]:
        lines.append("unmatched %d outbound call(s) with no registered callee:" % len(report["unmatched"]))
        for u in report["unmatched"]:
            o = u["outbound"]
            lines.append("  %-6s [%s] %s %s" % (u["protocol"], repo_label(o["repo"], names), o["target"], _where(o)))
    return lines


def snapshots_from_dirs(state_dirs) -> List[Dict]:
    """Stand-alone state directories, each with its own `index.db` -- the
    layout before there was one store per machine."""
    snapshots = []
    for d in state_dirs:
        store = query_mod.Store(Path(d).expanduser().resolve())
        try:
            snapshots.append({"repo": store.manifest.get("repo", d),
                              "head": store.manifest.get("head", "?"),
                              "dataflow": store.dataflow})
        finally:
            store.close()
    return snapshots


def read_link_report(store) -> Dict:
    edges = store.read_link_edges()
    return {
        "links": [e["data"] for e in edges if e["kind"] == "link"],
        "unmatched": [e["data"] for e in edges if e["kind"] == "unmatched"],
    }
