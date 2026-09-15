"""Phase 8a — the typed edge graph and path tracing (§6.5).

"How does data travel through this application, and where is this thing used?"
is the question a new joiner actually asks on day three, and the module
dependency graph does not answer it. On the validation target the module DAG
says `api -> service -> dal`, while what actually happens to a server record
crosses three representations and one process boundary that no import connects.

**The walk is deterministic Python; the LLM's only job is prose.** Graph
traversal is where a model's fluency becomes a liability: it will happily narrate
a plausible path with one invented hop, and an invented hop is undetectable in
prose. Letting Python own the topology means a hallucinated hop has nowhere to
hide — there is no edge in the graph for it to attach to. Every hop carries the
anchor of the edge it came from, or the path is emitted structure-only.

Call edges are derived from the import table rather than from call-site parsing.
That is a stated approximation: an import establishes that a file can reach a
symbol, not that it does. It is marked `confidence: medium` for exactly that
reason, and it is still far more than a dependency graph can say.
"""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

DEFAULT_MAX_HOPS = 8
MAX_PATHS = 2000

# §6.5 sources and sinks.
SOURCE_CHANNELS = frozenset(["http_in", "schedule", "event_subscribe", "process_boundary"])
SINK_CHANNELS = frozenset(
    ["persist", "http_out", "ssh_exec", "event_publish", "metric_emit", "schema_own"]
)
TRAVERSABLE = frozenset(["call", "map", "persist", "read", "http_out", "ssh_exec",
                         "event_publish", "metric_emit", "config_read"])

# A `library:` target records that a file imports something whose package prefix
# maps onto a channel. That is a real, citable dependency-surface fact and it
# feeds the side-effect claims — but it is not a place data goes.
#
# Left in the traversal it corrupts the walk from both ends: `library:org.quartz`
# becomes a *trigger* named after a jar, and `library:jakarta.persistence.*`
# becomes a *sink*, so the path list fills with walks that begin and end at
# import statements. The genuine triggers (routes, `main()`, scheduled jobs) and
# the genuine sinks (tables, entities, remote hosts) get buried under them.
LIBRARY_PREFIX = "library:"


def _is_library(target: str) -> bool:
    return target.startswith(LIBRARY_PREFIX)


def build_dataflow(
    extraction: Dict, xref: Dict, graph: Dict, max_hops: int = DEFAULT_MAX_HOPS
) -> Dict:
    edges = _edges(extraction, xref)
    adjacency: Dict[str, List[Dict]] = {}
    for edge in edges:
        adjacency.setdefault(edge["source"], []).append(edge)
    for key in adjacency:
        adjacency[key].sort(key=lambda e: (e["target"], e["channel"], e["anchor"]["file"]))

    sources = _sources(edges)
    paths, truncated = _trace(sources, adjacency, max_hops)
    boundaries = _process_boundaries(edges, graph)

    return {
        "head": extraction["head"],
        "edges": edges,
        "sources": sources,
        "paths": paths,
        "paths_truncated": truncated,
        "process_boundaries": boundaries,
        "totals": {
            "edges": len(edges),
            "nodes": len(set([e["source"] for e in edges] + [e["target"] for e in edges])),
            "sources": len(sources),
            "paths": len(paths),
        },
    }


def _edges(extraction: Dict, xref: Dict) -> List[Dict]:
    edges: List[Dict] = []
    seen: Set[Tuple[str, str, str]] = set()

    for row in extraction["io_edges"]:
        key = (row["source"], row["target"], row["channel"])
        if key in seen:
            continue
        seen.add(key)
        edges.append(
            {
                "source": row["source"],
                "target": row["target"],
                "channel": row["channel"],
                "module": row["module"],
                "anchor": row["anchor"],
                "confidence": "high",
            }
        )

    # Call edges from the resolved import table: the file's primary symbol can
    # reach the symbol it imports.
    primary_of = {rel: info.get("primary") for rel, info in extraction["files"].items()}
    for row in xref["uses"]:
        if row["resolved"] not in ("local", "matched"):
            continue
        source = primary_of.get(row["from_file"])
        if not source or source == row["fqn"] or row["fqn"].endswith(".*"):
            continue
        key = (source, row["fqn"], "call")
        if key in seen:
            continue
        seen.add(key)
        edges.append(
            {
                "source": source,
                "target": row["fqn"],
                "channel": "call",
                "module": row["from_module"],
                "anchor": row["anchor"],
                # An import proves reachability, not invocation (§6.7).
                "confidence": "medium",
            }
        )

    edges.sort(key=lambda e: (e["source"], e["channel"], e["target"], e["anchor"]["file"]))
    return edges


def _sources(edges: Sequence[Dict]) -> List[Dict]:
    out: List[Dict] = []
    seen: Set[Tuple[str, str]] = set()
    for edge in edges:
        if edge["channel"] not in SOURCE_CHANNELS or _is_library(edge["target"]):
            continue
        # An http_in edge points *at* the route; the traversal starts from the
        # handler, which is the edge's source.
        entry = (edge["source"], edge["channel"])
        if entry in seen:
            continue
        seen.add(entry)
        out.append(
            {
                "node": edge["source"],
                "trigger": edge["target"],
                "channel": edge["channel"],
                "module": edge["module"],
                "anchor": edge["anchor"],
            }
        )
    return sorted(out, key=lambda s: (s["channel"], s["trigger"], s["node"]))


def _trace(
    sources: Sequence[Dict], adjacency: Dict[str, List[Dict]], max_hops: int
) -> Tuple[List[Dict], bool]:
    """Bounded BFS from each source to each reachable sink.

    Cycle detection is per-path rather than global: a symbol may legitimately
    appear on two different paths, and excluding it globally would silently
    delete whichever path happened to be walked second.
    """
    paths: List[Dict] = []
    truncated = False

    for source in sources:
        frontier: List[Tuple[str, List[Dict], Set[str]]] = [
            (source["node"], [], {source["node"]})
        ]
        hops = 0
        while frontier and hops < max_hops:
            hops += 1
            nxt: List[Tuple[str, List[Dict], Set[str]]] = []
            for node, walked, visited in frontier:
                for edge in adjacency.get(node, ()):
                    if edge["channel"] not in TRAVERSABLE or _is_library(edge["target"]):
                        continue
                    if edge["target"] in visited:
                        continue
                    trail = walked + [edge]
                    # Only a real sink terminates a path. An earlier version also
                    # terminated on "no outgoing edges", which turned every leaf
                    # of the import graph into a reported path and saturated the
                    # cap with 400 walks to nowhere. A walk that reaches a symbol
                    # with no side effect has not found anything.
                    if edge["channel"] in SINK_CHANNELS:
                        if len(paths) >= MAX_PATHS:
                            truncated = True
                        else:
                            paths.append(_path_record(source, trail))
                    if adjacency.get(edge["target"]):
                        nxt.append((edge["target"], trail, visited | {edge["target"]}))
            frontier = nxt
            if len(paths) >= MAX_PATHS:
                truncated = True
                break

    paths.sort(key=lambda p: (p["trigger"], p["source"], p["sink"], len(p["hops"])))
    return _dedupe_paths(paths), truncated


def _path_record(source: Dict, trail: Sequence[Dict]) -> Dict:
    hops = [
        {
            "from": edge["source"],
            "to": edge["target"],
            "channel": edge["channel"],
            "module": edge["module"],
            "anchor": edge["anchor"],
            "confidence": edge["confidence"],
        }
        for edge in trail
    ]
    return {
        "trigger": source["trigger"],
        "trigger_channel": source["channel"],
        "source": source["node"],
        "sink": trail[-1]["target"],
        "modules": sorted({source["module"]} | {h["module"] for h in hops}),
        "hops": hops,
        # The `map` edges along the path: how the record is re-represented on
        # the way through. This is what turns `EServer -> DServer -> Server`
        # from something a reader has to notice into a citable artifact.
        #
        # The chain includes the *first* hop's origin, not just its targets:
        # a chain rendered as "EServer" alone says a transformation happened
        # without saying what was transformed, which is the half of the fact
        # that was already obvious.
        "representation_chain": _chain(hops),
        # A path narrated in prose must have an anchor on every hop; one without
        # is emitted structure-only.
        "fully_anchored": all(h["anchor"] for h in hops),
        "min_confidence": "medium" if any(h["confidence"] == "medium" for h in hops) else "high",
    }


def _chain(hops: Sequence[Dict]) -> List[str]:
    out: List[str] = []
    for hop in hops:
        if hop["channel"] != "map":
            continue
        if not out:
            out.append(hop["from"])
        out.append(hop["to"])
    return out


def _dedupe_paths(paths: Sequence[Dict]) -> List[Dict]:
    """Keep the shortest path per (trigger, source, sink).

    A longer walk to a sink already reached is the same finding with extra
    hops, and reporting both buries the short one. Ties are broken on the hop
    sequence so the choice is deterministic rather than dependent on BFS order.
    """
    best: Dict[Tuple[str, str, str], Dict] = {}
    for path in paths:
        key = (path["trigger"], path["source"], path["sink"])
        current = best.get(key)
        candidate = (len(path["hops"]), tuple((h["from"], h["to"], h["channel"]) for h in path["hops"]))
        if current is None or candidate < (
            len(current["hops"]),
            tuple((h["from"], h["to"], h["channel"]) for h in current["hops"]),
        ):
            best[key] = path
    return [best[k] for k in sorted(best)]


def _process_boundaries(edges: Sequence[Dict], graph: Dict) -> List[Dict]:
    """Data edges that cross a deployable unit with no code coupling.

    §6.1's third fact: `SqlPoolQuartzJobsApplication` writes rows the
    `SqlPoolApplication` process later serves. That is a real data edge with
    zero import connecting the two; it exists only through the database.

    Two formulations fail before this one, and both failures are instructive.

    *Which modules touch this table* reports nothing: on the validation target
    only `dal` declares entities and only `setup` writes migrations, so every
    table has exactly one toucher while the fact is plainly true.

    *What can each `main()` reach through the call graph* also reports nothing,
    for the reason §6.7 names: the runtime DI graph is not the import graph.
    `SqlPoolApplication` imports its Dropwizard bootstrap and nothing else; the
    resources that reach the database are registered by Spring at startup, by
    type. Following imports out of a `main()` finds the wiring, not the work.

    What is actually true and actually checkable: **a deployable contains its
    module's transitive dependency closure.** That is what `implementation
    project(':...')` means, it is derived from the observed graph rather than
    guessed, and the persist edges inside that closure are anchored facts. So
    the claim is "these two processes both link code that writes this table",
    which is exactly the claim §6.1 makes — and it is honest about being a
    statement over packaged code rather than an observed runtime call.
    """
    processes: Dict[str, Dict] = {}
    for edge in edges:
        if edge["channel"] != "process_boundary":
            continue
        # A module yields at most one process. Both the `main()` method and the
        # Dockerfile mark it; the `main()` is the better label because it names
        # the class an engineer would open.
        slot = processes.setdefault(edge["module"], {"module": edge["module"], "anchors": []})
        slot["anchors"].append(edge["anchor"])
        if "." in edge["source"] and "label" not in slot:
            slot["label"] = edge["source"]
    if len(processes) < 2:
        return []

    deps: Dict[str, Set[str]] = {}
    for edge in graph.get("observed", []):
        deps.setdefault(edge["from"], set()).add(edge["to"])

    storage: Dict[str, List[Dict]] = {}
    for edge in edges:
        if edge["channel"] in ("persist", "read") and edge["target"].startswith(("table:", "entity:")):
            storage.setdefault(edge["module"], []).append(edge)

    reach: Dict[str, Dict[str, List[Dict]]] = {}
    for module, meta in processes.items():
        closure = _closure(module, deps)
        hits: Dict[str, List[Dict]] = {}
        for member in sorted(closure):
            for edge in storage.get(member, []):
                hits.setdefault(edge["target"], []).append(edge)
        meta["closure"] = sorted(closure)
        reach[module] = hits

    targets: Dict[str, List[str]] = {}
    for module, hits in reach.items():
        for target in hits:
            targets.setdefault(target, []).append(module)

    out: List[Dict] = []
    for target in sorted(targets):
        touching = sorted(targets[target])
        if len(touching) < 2:
            continue
        evidence: List[Dict] = []
        for module in touching:
            evidence.append(processes[module]["anchors"][0])
            evidence.append(reach[module][target][0]["anchor"])
        labels = [processes[m].get("label", m) for m in touching]
        out.append(
            {
                "shared": target,
                "processes": labels,
                "modules": touching,
                "via": {m: sorted({e["module"] for e in reach[m][target]}) for m in touching},
                "evidence": evidence[:8],
                "note": (
                    "%s are separate deployable units whose dependency closures both contain "
                    "code that touches %s. No import connects the two application classes; the "
                    "data edge exists only through shared storage. This is reachability over "
                    "packaged code, not an observed runtime call."
                    % (" and ".join(l.rsplit(".", 1)[-1] for l in labels), target)
                ),
            }
        )
    return out


def _closure(module: str, deps: Dict[str, Set[str]]) -> Set[str]:
    seen = {module}
    frontier = [module]
    while frontier:
        node = frontier.pop()
        for dep in deps.get(node, ()):
            if dep not in seen:
                seen.add(dep)
                frontier.append(dep)
    return seen


def summarise(dataflow: Dict) -> List[str]:
    t = dataflow["totals"]
    return [
        "dataflow  %d edges over %d nodes, %d sources, %d traced paths%s"
        % (t["edges"], t["nodes"], t["sources"], t["paths"],
           " (truncated)" if dataflow["paths_truncated"] else ""),
        "          %d shared-storage boundaries" % len(dataflow["process_boundaries"]),
    ]
