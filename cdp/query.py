"""The query layer.

RESEARCH.md §7.2 describes the knowledge graph as "the queryable substrate:
'what breaks if I change this table' is a graph query, not a grep." This module
is that substrate's interface, and it is the reason the whole pipeline is worth
running: documents go stale, a queryable index pinned to a commit does not.

Every answer carries `file:line` citations, and every answer is computed from
verified state — never from a model. `used-by` is the transpose of the import
table, `routes` come from constant-resolved annotations, `table` comes from
migration DDL. Asking a model "where is DServer used?" is asking a question it
answers confidently and wrongly; asking this module is asking for an inversion
of data that was checked.

The queries are deliberately the ones a joiner actually asks, in the order they
ask them: what are the entry points, who owns this table, where does this symbol
go, what is still unknown.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from .util import CdpError, read_json, truncate


class Store:
    """Lazily-loaded view over a state directory."""

    def __init__(self, state_dir: Path) -> None:
        self.dir = Path(state_dir)
        if not self.dir.is_dir():
            raise CdpError("no CDP state at %s — run `scan` first" % self.dir)
        self._cache: Dict[str, Any] = {}

    def _load(self, name: str, default: Any = None) -> Any:
        if name not in self._cache:
            path = self.dir / (name + ".json")
            if not path.exists():
                if default is None:
                    raise CdpError("missing %s — run `scan` first" % path)
                self._cache[name] = default
            else:
                self._cache[name] = read_json(path)
        return self._cache[name]

    inventory = property(lambda self: self._load("inventory"))
    extraction = property(lambda self: self._load("extract"))
    graph = property(lambda self: self._load("graph"))
    partition = property(lambda self: self._load("partition"))
    xref = property(lambda self: self._load("xref"))
    state = property(lambda self: self._load("state", {"claims": [], "unknowns": [], "conflicts": []}))
    dataflow = property(lambda self: self._load("dataflow", {"edges": [], "paths": [], "process_boundaries": []}))
    manifest = property(lambda self: self._load("manifest", {}))

    def node_of(self, path: str) -> Optional[str]:
        for scope in self.partition["scopes"]:
            if path in scope["files"]:
                return scope["node"]
        return None


# --------------------------------------------------------------- formatting


def cite(anchor: Dict) -> str:
    return "%s:%s" % (anchor.get("file"), anchor.get("line"))


def _claim_lines(claim: Dict, indent: str = "  ") -> List[str]:
    out = ["%s%s" % (indent, claim.get("statement", ""))]
    for text in claim.get("statements", [])[1:]:
        out.append("%s  (also stated as) %s" % (indent, text))
    marks = [claim.get("confidence", "")]
    if claim.get("channel"):
        marks.append(claim["channel"])
    out.append(
        "%s  [%s] %s"
        % (indent, "/".join(m for m in marks if m), " ".join(cite(a) for a in claim.get("evidence", [])))
    )
    return out


def _matches(text: str, needle: str) -> bool:
    return needle.lower() in str(text).lower()


# ------------------------------------------------------------------ queries


def q_symbol(store: Store, name: str, limit: int = 40) -> Dict:
    """Definition sites, used-by, and collisions for a symbol.

    Accepts a fully-qualified name or a suffix — `DServer` finds
    `rms.unifiedstore.sqlpool.common.model.domain.DServer` — because nobody
    types the FQN.
    """
    xref = store.xref
    exact = xref["symbols"].get(name)
    keys = [name] if exact else [
        k for k in xref["symbols"] if k == name or k.rsplit(".", 1)[-1] == name or _matches(k, name)
    ]
    keys = sorted(keys, key=lambda k: (k.rsplit(".", 1)[-1] != name, len(k)))[:limit]
    if not keys:
        return {"query": "symbol", "name": name, "found": []}

    out = []
    for key in keys:
        entry = xref["symbols"][key]
        users = xref["used_by"].get(key, [])
        claims = [c for c in store.state["claims"] if c.get("subject") == key or _matches(c.get("statement", ""), key.rsplit(".", 1)[-1])]
        out.append(
            {
                "fqn": key,
                "kind": entry["kind"],
                "visibility": entry["visibility"],
                "modules": entry["modules"],
                "value": entry.get("value"),
                "defined_at": [cite(s["anchor"]) for s in entry["sites"]],
                "collision": bool(entry.get("collision")),
                "used_by_count": len(users),
                "used_by": [
                    {"module": u["module"], "at": cite(u["anchor"])} for u in users[:limit]
                ],
                "claims": claims[:6],
            }
        )
    return {"query": "symbol", "name": name, "found": out}


def q_file(store: Store, path: str) -> Dict:
    files = [f for f in store.inventory["files"] if f["path"] == path or _matches(f["path"], path)]
    if not files:
        return {"query": "file", "path": path, "found": []}
    out = []
    for entry in sorted(files, key=lambda f: (f["path"] != path, len(f["path"])))[:10]:
        rel = entry["path"]
        info = store.extraction["files"].get(rel, {})
        defines = [d for d in store.extraction["defines"] if d["file"] == rel]
        edges = [e for e in store.extraction["io_edges"] if e["file"] == rel]
        claims = [
            c for c in store.state["claims"]
            if any(a.get("file") == rel for a in c.get("evidence", []))
        ]
        out.append(
            {
                "path": rel,
                "module": entry["module"],
                "node": store.node_of(rel),
                "language": entry["language"],
                "role": entry["role"],
                "loc": entry["loc"],
                "package": info.get("package"),
                "primary": info.get("primary"),
                "signals": info.get("signals", []),
                "defines": [
                    {"fqn": d["fqn"], "kind": d["kind"], "at": cite(d["anchor"])} for d in defines[:40]
                ],
                "io_edges": [
                    {"channel": e["channel"], "target": e["target"], "at": cite(e["anchor"])}
                    for e in edges[:40]
                ],
                "claims": claims[:20],
            }
        )
    return {"query": "file", "path": path, "found": out}


def q_module(store: Store, name: str) -> Dict:
    modules = [m for m in store.inventory["modules"] if m["name"] == name or _matches(m["name"], name)]
    if not modules:
        return {"query": "module", "name": name, "found": []}
    graph = store.graph
    out = []
    for module in modules[:5]:
        key = module["name"]
        claims = [c for c in store.state["claims"] if _claim_module(c, store) == key]
        out.append(
            {
                "name": key,
                "files": module["files"],
                "loc": module["loc"],
                "on_disk": module.get("on_disk"),
                "generated_suspect": module.get("generated_suspect", False),
                "by_language": module["by_language"],
                "by_role": module["by_role"],
                "level": store.manifest.get("module_level", {}).get(key),
                "depends_on": [
                    {"module": e["to"], "weight": e["weight"]}
                    for e in graph["observed"] if e["from"] == key
                ],
                "depended_on_by": [
                    {"module": e["from"], "weight": e["weight"]}
                    for e in graph["observed"] if e["to"] == key
                ],
                "declared_only": [
                    e["to"] for e in graph["divergence"]["declared_not_observed"] if e["from"] == key
                ],
                "observed_only": [
                    e["to"] for e in graph["divergence"]["observed_not_declared"] if e["from"] == key
                ],
                "scopes": [s["node"] for s in store.partition["scopes"] if s["module"] == key],
                "claims_by_kind": _tally(c["kind"] for c in claims),
                "claims": claims,
            }
        )
    return {"query": "module", "name": name, "found": out}


def q_routes(store: Store, pattern: Optional[str] = None) -> Dict:
    routes = store.xref["routes"] + store.xref["unresolved_routes"]
    if pattern:
        routes = [r for r in routes if _matches(r["route"], pattern) or _matches(r["verb"], pattern)]
    return {
        "query": "routes",
        "count": len(routes),
        "routes": [
            {
                "verb": r["verb"],
                "route": r["route"],
                "handler": r["handler"],
                "module": r["module"],
                "declared_via": r.get("symbolic"),
                "unresolved_constants": r.get("unresolved_constants", []),
                "evidence": [cite(a) for a in r["evidence"]],
            }
            for r in routes
        ],
    }


def q_table(store: Store, name: Optional[str] = None) -> Dict:
    """Who owns, writes and reads each table.

    "What breaks if I change this table" reduces to the union of the three
    lists below, and every entry carries the line that put it there.
    """
    buckets: Dict[str, Dict[str, List[Dict]]] = {}
    for edge in store.extraction["io_edges"]:
        if not edge["target"].startswith("table:"):
            continue
        table = edge["target"][len("table:") :]
        if name and not _matches(table, name):
            continue
        slot = buckets.setdefault(table, {"schema_own": [], "persist": [], "read": []})
        if edge["channel"] in slot:
            slot[edge["channel"]].append(edge)

    out = []
    for table in sorted(buckets):
        slot = buckets[table]
        out.append(
            {
                "table": table,
                "schema_owned_by": sorted({e["module"] for e in slot["schema_own"]}),
                "migrations": [cite(e["anchor"]) for e in slot["schema_own"]][:12],
                "written_by": sorted({e["source"] for e in slot["persist"]}),
                "read_by": sorted({e["source"] for e in slot["read"]}),
                "evidence": [cite(e["anchor"]) for e in (slot["persist"] + slot["read"])][:8],
            }
        )
    return {"query": "table", "name": name, "count": len(out), "tables": out}


def q_config(store: Store, key: Optional[str] = None) -> Dict:
    rows: Dict[str, Dict] = {}
    for row in store.extraction["defines"]:
        if row["kind"] != "config_key" or not row["fqn"].startswith("config:"):
            continue
        name = row["fqn"][len("config:") :]
        if key and not _matches(name, key):
            continue
        slot = rows.setdefault(name, {"key": name, "declared": [], "read": [], "values": []})
        slot["declared"].append(cite(row["anchor"]))
        if row.get("value"):
            slot["values"].append(row["value"])
    for edge in store.extraction["io_edges"]:
        if edge["channel"] != "config_read" or not edge["target"].startswith("config:"):
            continue
        name = edge["target"][len("config:") :]
        if key and not _matches(name, key):
            continue
        if edge["source"].startswith("config-file:"):
            continue
        rows.setdefault(name, {"key": name, "declared": [], "read": [], "values": []})["read"].append(
            {"by": edge["source"], "at": cite(edge["anchor"])}
        )
    return {"query": "config", "count": len(rows), "keys": [rows[k] for k in sorted(rows)]}


def q_paths(
    store: Store, frm: Optional[str] = None, to: Optional[str] = None, limit: int = 25
) -> Dict:
    paths = store.dataflow["paths"]
    if frm:
        paths = [p for p in paths if _matches(p["source"], frm) or _matches(p["trigger"], frm)]
    if to:
        paths = [p for p in paths if _matches(p["sink"], to)]
    return {
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
            for p in paths[:limit]
        ],
    }


def q_search(store: Store, text: str, limit: int = 30) -> Dict:
    claims = [
        c for c in store.state["claims"]
        if _matches(c.get("subject", ""), text) or _matches(c.get("statement", ""), text)
    ]
    symbols = [k for k in store.xref["symbols"] if _matches(k, text)]
    unknowns = [u for u in store.state["unknowns"] if _matches(u.get("question", ""), text)]
    files = [f["path"] for f in store.inventory["files"] if _matches(f["path"], text)]
    return {
        "query": "search",
        "text": text,
        "claims": claims[:limit],
        "symbols": sorted(symbols, key=len)[:limit],
        "unknowns": unknowns[:limit],
        "files": sorted(files, key=len)[:limit],
    }


def q_claims(
    store: Store,
    kind: Optional[str] = None,
    module: Optional[str] = None,
    subject: Optional[str] = None,
    limit: int = 100,
) -> Dict:
    claims = store.state["claims"]
    if kind:
        claims = [c for c in claims if c.get("kind") == kind]
    if subject:
        claims = [c for c in claims if _matches(c.get("subject", ""), subject)]
    if module:
        claims = [c for c in claims if _matches(_claim_module(c, store) or "", module)]
    return {"query": "claims", "count": len(claims), "claims": claims[:limit]}


def q_unknowns(store: Store, module: Optional[str] = None) -> Dict:
    unknowns = store.state["unknowns"]
    if module:
        unknowns = [u for u in unknowns if _matches(str(u.get("source_node", "")), module)]
    grouped: Dict[str, List[Dict]] = {}
    for row in unknowns:
        grouped.setdefault(str(row.get("source_node", "(unattributed)")), []).append(row)
    return {
        "query": "unknowns",
        "count": len(unknowns),
        "by_node": {k: grouped[k] for k in sorted(grouped)},
    }


def q_conflicts(store: Store) -> Dict:
    state = store.state
    return {
        "query": "conflicts",
        "count": len(state.get("conflicts", [])),
        "near_miss_count": len(state.get("near_misses", [])),
        "conflicts": state.get("conflicts", []),
        "near_misses": state.get("near_misses", [])[:20],
    }


def q_stats(store: Store) -> Dict:
    inv = store.inventory
    state = store.state
    # The build's own name for itself, when it differs from the directory. On
    # the validation target `settings.gradle` says `rootProject.name = 'spm'`
    # while every directory is `sql-pool-*`, and that mismatch is the first
    # thing a newcomer trips over -- so it belongs in the first thing they run.
    build_name = None
    for row in store.extraction["defines"]:
        if row["fqn"] == "build:rootProject.name":
            build_name = row.get("value")
            break
    return {
        "query": "stats",
        "repo": inv["repo_name"],
        "build_name": build_name if build_name and build_name != inv["repo_name"] else None,
        "head": inv["head"],
        "census": inv["counts"],
        "inventory_source": inv["source"],
        "languages": inv["by_language"],
        "roles": inv["by_role"],
        "modules": len(inv["modules"]),
        "scopes": len(store.partition["scopes"]),
        "symbols": len(store.xref["symbols"]),
        "routes": len(store.xref["routes"]),
        "claims": len(state.get("claims", [])),
        "claims_by_kind": _tally(c["kind"] for c in state.get("claims", [])),
        "claims_by_confidence": _tally(c.get("confidence", "?") for c in state.get("claims", [])),
        "unknowns": len(state.get("unknowns", [])),
        "conflicts": len(state.get("conflicts", [])),
        "coverage": state.get("coverage", {}),
        "resolution": store.xref["resolution"],
        "divergence": {
            "declared": store.graph["divergence"]["declared_edges"],
            "observed": store.graph["divergence"]["observed_edges"],
            "declared_not_observed": store.graph["divergence"]["declared_not_observed"],
            "observed_not_declared": store.graph["divergence"]["observed_not_declared"],
        },
    }


def q_coverage(store: Store) -> Dict:
    state = store.state
    coverage = state.get("coverage", {})
    return {
        "query": "coverage",
        "coverage": coverage,
        "nodes": state.get("nodes", {}),
        "node_errors": state.get("node_errors", {}),
        "warning": (
            None
            if coverage.get("fraction", 0) >= 0.999
            else "This run covers %.1f%% of tracked files. Treat every absent fact as unexamined, "
            "not as absent from the codebase." % (100 * coverage.get("fraction", 0))
        ),
    }


def _claim_module(claim: Dict, store: Store) -> Optional[str]:
    nodes = claim.get("source_nodes") or ([claim["source_node"]] if claim.get("source_node") else [])
    for node in nodes:
        if node.startswith("root/"):
            return node.split("/")[1]
    for anchor in claim.get("evidence", []):
        for entry in store.inventory["files"]:
            if entry["path"] == anchor.get("file"):
                return entry["module"]
    return None


def _tally(values: Iterable[str]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))


# ------------------------------------------------------------------ rendering


def render(result: Dict) -> str:
    """Compact text rendering. `--json` gives the same data unabridged."""
    kind = result.get("query")
    lines: List[str] = []

    if kind == "symbol":
        if not result["found"]:
            return "No symbol matching %r. Try `search %s`." % (result["name"], result["name"])
        for entry in result["found"]:
            lines.append("%s  [%s %s]" % (entry["fqn"], entry["visibility"], entry["kind"]))
            if entry.get("value") is not None:
                lines.append("  value: %r" % entry["value"])
            lines.append("  defined in %s at %s" % (", ".join(entry["modules"]), ", ".join(entry["defined_at"])))
            if entry["collision"]:
                lines.append("  ! declared at more than one site; no winner is picked (§6.4)")
            lines.append("  used by %d site(s)" % entry["used_by_count"])
            for use in entry["used_by"][:12]:
                lines.append("    %-24s %s" % (use["module"], use["at"]))
            if entry["used_by_count"] > 12:
                lines.append("    ... %d more" % (entry["used_by_count"] - 12))
            for claim in entry["claims"]:
                lines.extend(_claim_lines(claim))
            lines.append("")

    elif kind == "file":
        if not result["found"]:
            return "No file matching %r." % result["path"]
        for entry in result["found"]:
            lines.append("%s" % entry["path"])
            lines.append(
                "  module %s | node %s | %s | %s | %d loc"
                % (entry["module"], entry["node"], entry["language"], entry["role"], entry["loc"])
            )
            if entry.get("package"):
                lines.append("  package %s" % entry["package"])
            if entry["signals"]:
                lines.append("  signals: %s" % ", ".join(entry["signals"]))
            if entry["defines"]:
                lines.append("  defines:")
                for d in entry["defines"][:20]:
                    lines.append("    %-9s %-60s %s" % (d["kind"], truncate(d["fqn"], 60), d["at"]))
            if entry["io_edges"]:
                lines.append("  edges:")
                for e in entry["io_edges"][:20]:
                    lines.append("    %-16s %-50s %s" % (e["channel"], truncate(e["target"], 50), e["at"]))
            for claim in entry["claims"][:10]:
                lines.extend(_claim_lines(claim))
            lines.append("")

    elif kind == "module":
        if not result["found"]:
            return "No module matching %r." % result["name"]
        for entry in result["found"]:
            lines.append("%s  (%d files, %d loc%s)" % (
                entry["name"], entry["files"], entry["loc"],
                ", %d on disk" % entry["on_disk"] if entry.get("on_disk") else ""))
            if entry["generated_suspect"]:
                lines.append("  ! generated at build time; described by contract, not read (§6.7)")
            lines.append("  languages: %s" % ", ".join("%s %d" % kv for kv in entry["by_language"].items()))
            lines.append("  depends on:   %s" % (", ".join(
                "%s(%d)" % (d["module"], d["weight"]) for d in entry["depends_on"]) or "-"))
            lines.append("  depended on:  %s" % (", ".join(
                "%s(%d)" % (d["module"], d["weight"]) for d in entry["depended_on_by"]) or "-"))
            if entry["declared_only"]:
                lines.append("  ! declared but never imported: %s" % ", ".join(entry["declared_only"]))
            if entry["observed_only"]:
                lines.append("  ! imported but not declared: %s" % ", ".join(entry["observed_only"]))
            lines.append("  scopes: %s" % ", ".join(entry["scopes"]))
            lines.append("  claims: %s" % ", ".join("%s %d" % kv for kv in entry["claims_by_kind"].items()))
            for claim in entry["claims"][:25]:
                lines.extend(_claim_lines(claim))
            lines.append("")

    elif kind == "routes":
        lines.append("%d route(s)" % result["count"])
        for r in result["routes"]:
            note = ""
            if r["unresolved_constants"]:
                note = "  ! constant unresolved: " + ", ".join(r["unresolved_constants"])
            elif r["declared_via"]:
                note = "  (declared as %s)" % r["declared_via"]
            lines.append("  %-7s %-40s %s" % (r["verb"], r["route"], r["handler"].rsplit(".", 1)[-1]))
            lines.append("          %s%s" % (" ".join(r["evidence"]), note))

    elif kind == "table":
        lines.append("%d table(s)" % result["count"])
        for t in result["tables"]:
            lines.append("  %s" % t["table"])
            lines.append("    schema owned by: %s" % (", ".join(t["schema_owned_by"]) or "(no migration found)"))
            if t["migrations"]:
                lines.append("    migrations: %s" % " ".join(t["migrations"][:6]))
            if t["written_by"]:
                lines.append("    written by: %s" % ", ".join(s.rsplit(".", 1)[-1] for s in t["written_by"]))
            if t["read_by"]:
                lines.append("    read by:    %s" % ", ".join(s.rsplit(".", 1)[-1] for s in t["read_by"]))
            if t["evidence"]:
                lines.append("    %s" % " ".join(t["evidence"][:6]))

    elif kind == "config":
        lines.append("%d config key(s)" % result["count"])
        for c in result["keys"]:
            lines.append("  %s%s" % (c["key"], "  = %r" % c["values"][0] if c["values"] else ""))
            if c["declared"]:
                lines.append("    declared: %s" % " ".join(c["declared"][:4]))
            for r in c["read"][:6]:
                lines.append("    read by %-50s %s" % (truncate(r["by"], 50), r["at"]))

    elif kind == "paths":
        lines.append("%d traced path(s)" % result["count"])
        for p in result["paths"]:
            lines.append("  %s   [%s]" % (p["trigger"], p["confidence"]))
            for h in p["hops"]:
                lines.append("    --%s--> %-40s %s" % (h["channel"], h["to"], h["at"]))
            if p["representation_chain"]:
                lines.append("    representations: %s" % " -> ".join(
                    r.rsplit(".", 1)[-1] for r in p["representation_chain"]))

    elif kind == "search":
        if result["symbols"]:
            lines.append("symbols:")
            lines += ["  " + s for s in result["symbols"]]
        if result["files"]:
            lines.append("files:")
            lines += ["  " + f for f in result["files"]]
        if result["claims"]:
            lines.append("claims:")
            for claim in result["claims"]:
                lines.extend(_claim_lines(claim))
        if result["unknowns"]:
            lines.append("unknowns:")
            for u in result["unknowns"]:
                lines.append("  %s" % u["question"])
        if not lines:
            lines.append("Nothing matched %r." % result["text"])

    elif kind == "claims":
        lines.append("%d claim(s)" % result["count"])
        for claim in result["claims"]:
            lines.append("  %-12s %s" % (claim["kind"], truncate(claim["subject"], 70)))
            lines.extend(_claim_lines(claim, indent="    "))

    elif kind == "unknowns":
        lines.append("%d unknown(s) — the tribal-knowledge inventory" % result["count"])
        for node, rows in result["by_node"].items():
            lines.append("  %s" % node)
            for row in rows:
                lines.append("    %s" % row["question"])
                lines.append("      why: %s" % row["why_unresolved"])
                if row.get("anchor"):
                    lines.append("      %s" % cite(row["anchor"]))

    elif kind == "conflicts":
        lines.append("%d conflict(s), %d near-miss(es)" % (result["count"], result["near_miss_count"]))
        for c in result["conflicts"]:
            lines.append("  %s (%s) — %s" % (c["subject"], c["kind"], c["resolved_by"] or "CONTESTED"))
            for pos in c["positions"]:
                lines.append("    %s%s  by %s  (%d anchors)" % (
                    pos["values"], "  <-- kept" if pos["won"] else "",
                    ", ".join(pos["nodes"]), pos["evidence_count"]))
        for n in result["near_misses"]:
            lines.append("  ~ %s: %d wordings, same enums" % (n["subject"], len(n["statements"])))

    elif kind == "stats":
        c = result["census"]
        lines += [
            "repo        %s @ %s%s" % (
                result["repo"], result["head"][:12],
                "   (the build calls itself '%s')" % result["build_name"]
                if result.get("build_name") else ""),
            "census      %d tracked / %d on disk (%.1fx) [%s]"
            % (c["tracked"], c["on_disk"], c["ratio"], result["inventory_source"]),
            "modules     %d in %d scopes" % (result["modules"], result["scopes"]),
            "symbols     %d" % result["symbols"],
            "routes      %d" % result["routes"],
            "claims      %d  (%s)" % (result["claims"], ", ".join("%s %d" % kv for kv in result["claims_by_kind"].items())),
            "confidence  %s" % ", ".join("%s %d" % kv for kv in result["claims_by_confidence"].items()),
            "unknowns    %d" % result["unknowns"],
            "conflicts   %d" % result["conflicts"],
            "coverage    %.1f%% of tracked files in complete scopes"
            % (100 * result["coverage"].get("fraction", 0)),
            "graph       declared %d / observed %d inter-module edges"
            % (result["divergence"]["declared"], result["divergence"]["observed"]),
        ]
        for e in result["divergence"]["declared_not_observed"]:
            lines.append("  declared but never imported: %s -> %s" % (e["from"], e["to"]))
        for e in result["divergence"]["observed_not_declared"]:
            lines.append("  imported but not declared:   %s -> %s" % (e["from"], e["to"]))

    elif kind == "coverage":
        cov = result["coverage"]
        lines.append("coverage %d/%d tracked files (%.1f%%)"
                     % (cov.get("files_complete", 0), cov.get("files_total", 0),
                        100 * cov.get("fraction", 0)))
        if result["warning"]:
            lines.append(result["warning"])
        for node in cov.get("incomplete_nodes", []):
            lines.append("  incomplete: %s (%s)" % (node, result["nodes"].get(node, "not run")))

    else:
        lines.append(str(result))

    return "\n".join(lines).rstrip()


QUERIES: Dict[str, Callable] = {
    "symbol": q_symbol,
    "file": q_file,
    "module": q_module,
    "routes": q_routes,
    "table": q_table,
    "config": q_config,
    "paths": q_paths,
    "search": q_search,
    "claims": q_claims,
    "unknowns": q_unknowns,
    "conflicts": q_conflicts,
    "stats": q_stats,
    "coverage": q_coverage,
}
