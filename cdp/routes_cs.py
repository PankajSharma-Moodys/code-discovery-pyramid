"""ASP.NET attribute routes: join a handler's template with its class's `[Route]`.

The C# extractor reads one file, but a controller's `[Route]` may sit on another part of a
`partial` class or on a base class. It therefore emits each handler's own template with
`route_class`/`route_action` on the `http_in` edge, and the class-level templates as `route` (and
`route_parent`, the candidate base-class names) on the class's define rows. This module applies
what ASP.NET does with them: every class template of the class (all partial parts, else the
nearest base class that has one) is combined with the handler template; an absolute handler
template (`/x`, `~/x`) ignores the class's; `[controller]` is the class name without `Controller`
and `[action]` the handler's name.
"""

from __future__ import annotations

from typing import Dict, Iterator, List, Optional, Set
from .rules import all_edges


def _class_tables(extraction: Dict):
    routes: Dict[str, List[str]] = {}
    parents: Dict[str, List[str]] = {}
    known: Set[str] = set()
    for d in extraction["defines"]:
        if not d["file"].endswith(".cs") or d["kind"] != "class":
            continue
        known.add(d["fqn"])
        for t in d.get("route") or ():
            if t not in routes.setdefault(d["fqn"], []):
                routes[d["fqn"]].append(t)
        if d.get("route_parent"):
            parents.setdefault(d["fqn"], d["route_parent"])
    return routes, parents, known


def _templates(fqn: str, routes, parents, known) -> List[str]:
    seen = set()
    while fqn and fqn not in seen:
        seen.add(fqn)
        if routes.get(fqn):
            return routes[fqn]
        nxt: Optional[str] = None
        for cand in parents.get(fqn, ()):
            if cand in known:
                nxt = cand
                break
        fqn = nxt or ""
    return []


def joined(base: Optional[str], sub: str, controller: str, action: str) -> str:
    if sub.startswith(("/", "~/")):
        path = sub.lstrip("~")
    elif base is None:
        path = sub
    elif not sub:
        path = base
    else:
        path = base.rstrip("/") + "/" + sub.lstrip("/")
    path = path.replace("[controller]", controller).replace("[action]", action)
    return "/" + path.strip("/") if path.strip("/") else "/"


def expand_routes(extraction: Dict) -> Iterator[Dict]:
    """The `io_edges` of the extraction with each C# `route_class` edge replaced by one edge per
    class template, its target holding the full path."""
    tables = None
    for edge in all_edges(extraction):
        cls = edge.get("route_class")
        if not cls or edge["channel"] != "http_in":
            yield edge
            continue
        if tables is None:
            tables = _class_tables(extraction)
        verb, _, sub = edge["target"][len("route:"):].partition(" ")
        name = cls.rsplit(".", 1)[-1]
        controller = name[:-len("Controller")] if name.endswith("Controller") and name != "Controller" else name
        bases: List[Optional[str]] = list(_templates(cls, *tables)) or [None]
        for base in bases:
            out = dict(edge)
            out["target"] = "route:%s %s" % (verb, joined(base, sub, controller, edge.get("route_action", "")))
            yield out
