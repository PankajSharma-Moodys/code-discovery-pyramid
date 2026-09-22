"""Node-ID namespacing (`PLAN.md` Phase 0; `WEB_RESEARCH.md` §7.3).

Four artifacts today carry node identity with no join key between them:
`graph.modules` (module names), `partition.scopes[].node` (`root/…` paths),
`xref.symbols` (FQNs), and a claim's `subject` (an FQN *or* table *or* route
*or* config key, `schema/patch-1.0.0.json:59`). This module is the one place
that decides which namespace (`module:`, `scope:`, `file:`, `sym:`, plus the
`dataflow` node types) an identifier belongs to, so no handler does its own
ad-hoc string matching.

The `dataflow` types (`route`, `table`, `process`, `entity`, `config`,
`library`, `migration`, `port`) are *both* namespaces here and the literal
prefixes `dataflow.edges` already uses for its endpoints. That coincidence is
deliberate and load-bearing since `ATLAS_REDESIGN.md` P0 made the typed
dataflow graph the L2 canvas: a `table:churn_cache` node id round-trips
between the graph and `/api/node/{id}` unchanged, with no re-derivation.

Pure functions over artifact dicts, no I/O -- `/api/node/:id` is the caller.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Set

#: Namespaces whose identifier is *also* a `dataflow` endpoint id verbatim
#: (prefix included) -- see the module docstring.
DATAFLOW_NAMESPACES = (
    "route",
    "table",
    "process",
    "entity",
    "config",
    "library",
    "migration",
    "port",
)

NAMESPACES = ("module", "scope", "file", "sym") + DATAFLOW_NAMESPACES


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


def from_dataflow_id(raw_id: str, symbols: Optional[Set[str]] = None) -> Optional[str]:
    """Maps a `dataflow.edges` endpoint to the namespaced id `/api/node/{id}`
    accepts, or `None` when nothing can resolve it.

    A `type:`-prefixed endpoint is already in namespaced form and is returned
    unchanged. A bare endpoint is a symbol when `xref.symbols` knows it and a
    module otherwise -- checking the symbol table rather than looking for a
    `#` is what keeps class-style ids (`web.api.models.JobResponse`, no `#`
    but a real symbol) from being mislabelled as modules."""
    ns, sep, _rest = raw_id.partition(":")
    if sep and ns in DATAFLOW_NAMESPACES:
        return raw_id
    if symbols and raw_id in symbols:
        return sym_id(raw_id)
    return module_id(raw_id)


def dataflow_id(node_id: str) -> str:
    """Inverse of {@link from_dataflow_id}: the `dataflow.edges` endpoint a
    namespaced id corresponds to. `dataflow`-namespace ids keep their prefix
    (that *is* the endpoint string); `sym:`/`module:` ids drop theirs."""
    ns, sep, rest = node_id.partition(":")
    if sep and ns in DATAFLOW_NAMESPACES:
        return node_id
    return rest if sep else node_id


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
