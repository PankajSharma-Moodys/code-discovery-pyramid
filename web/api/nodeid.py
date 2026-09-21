"""Node-ID namespacing (`PLAN.md` Phase 0; `WEB_RESEARCH.md` §7.3).

Four artifacts today carry node identity with no join key between them:
`graph.modules` (module names), `partition.scopes[].node` (`root/…` paths),
`xref.symbols` (FQNs), and a claim's `subject` (an FQN *or* table *or* route
*or* config key, `schema/patch-1.0.0.json:59`). This module is the one place
that decides which of the six namespaces (`module:`, `scope:`, `file:`,
`sym:`, `route:`, `table:`) an identifier belongs to, so no handler does its
own ad-hoc string matching.

Pure functions over artifact dicts, no I/O -- `/api/node/:id` (not built this
cycle) is the eventual caller.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

NAMESPACES = ("module", "scope", "file", "sym", "route", "table")


def module_id(name: str) -> str:
    return "module:%s" % name


def scope_id(node: str) -> str:
    return "scope:%s" % node


def file_id(path: str) -> str:
    return "file:%s" % path


def sym_id(fqn: str) -> str:
    return "sym:%s" % fqn


def route_id(route: str) -> str:
    return "route:%s" % route


def table_id(name: str) -> str:
    return "table:%s" % name


def parse(node_id: str) -> "tuple[str, str]":
    """`"sym:pkg.Foo.bar"` -> `("sym", "pkg.Foo.bar")`. Raises `ValueError`
    on an unnamespaced or unknown-namespace id -- callers should never see a
    raw artifact key leak into a response without going through the
    constructors above first."""
    if ":" not in node_id:
        raise ValueError("not a namespaced node id: %r" % node_id)
    ns, _, rest = node_id.partition(":")
    if ns not in NAMESPACES:
        raise ValueError("unknown namespace %r in node id %r" % (ns, node_id))
    return ns, rest


class SubjectIndex:
    """Classifies a claim's `subject` string against one snapshot's `xref`,
    `partition` and `dataflow` artifacts, resolving the ambiguity
    `schema/patch-1.0.0.json:61` documents but does not disambiguate.

    Built once per request/snapshot from the artifacts already fetched for
    other reasons -- the classification itself is three dict/set lookups,
    not a rescan.
    """

    def __init__(self, xref: Dict[str, Any], partition: Dict[str, Any],
                 dataflow: Optional[Dict[str, Any]] = None) -> None:
        self._symbols = set((xref or {}).get("symbols", {}).keys())
        self._routes = {
            r["route"] for r in ((xref or {}).get("routes", []) or []) if r.get("route")
        }
        self._scope_nodes = {
            scope["node"] for scope in (partition or {}).get("scopes", [])
        }
        self._tables = set()
        for edge in ((dataflow or {}).get("edges", []) or []):
            if edge.get("channel") == "db" and edge.get("target"):
                self._tables.add(edge["target"])
            if edge.get("channel") == "db" and edge.get("source"):
                self._tables.add(edge["source"])

    def classify(self, subject: str) -> Optional[str]:
        """Returns a namespaced node id, or `None` if `subject` matches none
        of the known namespaces (an unresolved subject -- the honest answer,
        not a guess)."""
        if subject in self._symbols:
            return sym_id(subject)
        if subject in self._routes:
            return route_id(subject)
        if subject in self._tables:
            return table_id(subject)
        if subject in self._scope_nodes:
            return scope_id(subject)
        return None
