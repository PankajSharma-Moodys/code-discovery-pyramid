"""Source -> sink view of the typed dataflow graph for the Atlas Flow tab
(`docs/superpowers/specs/2026-10-08-flow-tab-design.md`). Pure: takes
`_dataflow_graph`'s node/edge lists, returns the `/api/flow` payload, so the
role/orientation rules are testable without a scan.

Roles come from node *type*, not edge direction: `http_in` is stored
`module -> route` but data enters at the route, so it is reversed here."""
from __future__ import annotations

from typing import Dict, Iterable, List, Tuple

from . import encoding

DEFAULT_KINDS = {"http_in", "persist", "http_out", "metric_emit"}
OPTIONAL_KINDS = {"calls": "call", "config": "config_read"}
CODE_TYPES = {"module", "sql", "migration"}
_ROLE_ORDER = {"source": 0, "transform": 1, "sink": 2}
_SINK_OF_TYPE = {"table": ("group:tables", "Tables"), "entity": ("group:entities", "Entities")}
_LIB_SINK = {"http_out": ("group:http-out", "HTTP out"), "metric_emit": ("group:metrics", "Metrics")}


def build_flow(nodes: List[dict], edges: List[dict], include: Iterable[str] = ()) -> dict:
    by_id = {node["id"]: node for node in nodes}
    wanted = DEFAULT_KINDS | {OPTIONAL_KINDS[k] for k in include}

    def typ(raw_id: str):
        return by_id[raw_id].get("type")

    def is_test(raw_id: str) -> bool:
        return by_id[raw_id].get("role") == "test"

    def label(raw_id: str) -> str:
        return by_id[raw_id].get("label") or raw_id

    # A scheduled job is the module a `schedule` edge marks: the target when
    # it's a module (a config registering a job class), else the source (a
    # job class pointing at its scheduler library).
    jobs = set()
    for edge in edges:
        s, t = edge["source"], edge["target"]
        if edge["kind"] != "schedule" or s not in by_id or t not in by_id or is_test(s) or is_test(t):
            continue
        job = t if typ(t) == "module" else s
        if typ(job) == "module":
            jobs.add(job)

    out: Dict[str, dict] = {}
    groups: Dict[str, dict] = {}
    agg: Dict[Tuple[str, str, str], int] = {}

    def add(raw_id, text, kind, role, group_id, group_label, api_id) -> str:
        out.setdefault(raw_id, {"id": raw_id, "label": text, "kind": kind, "role": role,
                                "group": group_id, "node_id": api_id})
        groups.setdefault(group_id, {"id": group_id, "label": group_label, "role": role, "members": set()})
        groups[group_id]["members"].add(raw_id)
        return raw_id

    def add_code(raw_id: str) -> str:
        node = by_id[raw_id]
        if raw_id in jobs:
            return add(raw_id, label(raw_id), "job", "source", "group:jobs", "Scheduled jobs", node.get("node_id"))
        name = encoding.path_group_of(node["file"], 1) if node.get("file") else "(other)"
        return add(raw_id, label(raw_id), node.get("type") or "module", "transform", "code:" + name, name, node.get("node_id"))

    for edge in edges:
        kind, s, t = edge["kind"], edge["source"], edge["target"]
        # A job's first hop is a call; keep it so jobs reach data by default.
        if (kind not in wanted and not (kind == "call" and s in jobs)) or s not in by_id or t not in by_id or is_test(s) or is_test(t):
            continue
        # `http:<url>` ids are typed `module` but are outbound endpoints, not code.
        if typ(s) not in CODE_TYPES or s.startswith("http:"):
            continue
        tt = typ(t)
        t_is_url = t.startswith("http:")
        if kind == "http_in" and tt == "route":
            pair = (add(t, label(t), "route", "source", "group:routes", "Routes", by_id[t].get("node_id")), add_code(s))
        elif kind == "config_read" and tt == "config":
            pair = (add(t, label(t), "config", "source", "group:config", "Config", by_id[t].get("node_id")), add_code(s))
        elif kind == "persist" and tt in _SINK_OF_TYPE:
            gid, glabel = _SINK_OF_TYPE[tt]
            pair = (add_code(s), add(t, label(t), tt, "sink", gid, glabel, by_id[t].get("node_id")))
        elif kind == "http_out" and t_is_url:
            gid, glabel = _LIB_SINK[kind]
            sink = add(t, "%s · %s" % (glabel, t[len("http:"):]), kind, "sink", gid, glabel, by_id[t].get("node_id"))
            pair = (add_code(s), sink)
        elif kind in _LIB_SINK and tt == "library":
            gid, glabel = _LIB_SINK[kind]
            sink = add("flow-sink:%s:%s" % (kind, t), "%s · %s" % (glabel, label(t)), kind, "sink", gid, glabel, None)
            pair = (add_code(s), sink)
        elif kind == "call" and tt in CODE_TYPES and not t_is_url and s != t:
            pair = (add_code(s), add_code(t))
        else:
            continue
        key = (pair[0], pair[1], kind)
        agg[key] = agg.get(key, 0) + int(edge.get("count") or 1)

    return {
        "nodes": sorted(out.values(), key=lambda node: node["id"]),
        "groups": sorted(
            ({"id": g["id"], "label": g["label"], "role": g["role"], "count": len(g["members"])} for g in groups.values()),
            key=lambda g: (_ROLE_ORDER[g["role"]], g["id"]),
        ),
        "edges": [{"source": s, "target": t, "kind": k, "count": c} for (s, t, k), c in sorted(agg.items())],
    }
