"""Lookups by name: symbol, file, module, routes, table, config."""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence

from .budget import Budget
from .common import _claim_module, _finish, _matches, _role_index, _tally, cite
from .store import Store


def q_symbol(store: Store, name: str, budget: Optional[Budget] = None,
             exclude_role: Optional[Sequence[str]] = None) -> Dict:
    """Definition sites, used-by, and collisions for a symbol.

    Accepts a fully-qualified name or a suffix — `DServer` finds
    `rms.unifiedstore.sqlpool.common.model.domain.DServer` — because nobody
    types the FQN.
    """
    budget = budget or Budget()
    roles = _role_index(store) if exclude_role else {}
    xref = store.xref
    exact = xref["symbols"].get(name)
    keys = [name] if exact else [
        k for k in xref["symbols"] if k == name or k.rsplit(".", 1)[-1] == name or _matches(k, name)
    ]
    keys = sorted(keys, key=lambda k: (k.rsplit(".", 1)[-1] != name, len(k)))
    keys = budget.take(keys)
    if not keys:
        return _finish({"query": "symbol", "name": name, "found": []}, store, budget)

    out = []
    for key in keys:
        entry = xref["symbols"][key]
        sites = entry["sites"]
        if exclude_role:
            # A symbol drops from the answer only once every one of its
            # definition sites is excluded-role -- one real site is enough
            # to keep it.
            sites = [s for s in sites if roles.get(s["anchor"].get("file")) not in exclude_role]
            if not sites:
                continue
        users = xref["used_by"].get(key, [])
        claims = [c for c in store.state["claims"] if c.get("subject") == key or _matches(c.get("statement", ""), key.rsplit(".", 1)[-1])]
        out.append(
            {
                "fqn": key,
                "kind": entry["kind"],
                "visibility": entry["visibility"],
                "modules": entry["modules"],
                "value": entry.get("value"),
                "defined_at": [cite(s["anchor"]) for s in sites],
                "collision": bool(entry.get("collision")),
                # The true total, kept alongside the budgeted list, so the
                # renderer states "used by 47 site(s)" even when it shows 12.
                "used_by_count": len(users),
                "used_by": [
                    {"module": u["module"], "at": cite(u["anchor"])}
                    for u in budget.take(users)
                ],
                "claims": budget.take(claims),
            }
        )
    return _finish({"query": "symbol", "name": name, "found": out}, store, budget)


def q_file(store: Store, path: str, budget: Optional[Budget] = None,
           exclude_role: Optional[Sequence[str]] = None) -> Dict:
    budget = budget or Budget()
    files = [
        f for f in store.inventory["files"]
        if (f["path"] == path or _matches(f["path"], path))
        and not (exclude_role and f["role"] in exclude_role)
    ]
    if not files:
        return _finish({"query": "file", "path": path, "found": []}, store, budget)
    out = []
    for entry in budget.take(sorted(files, key=lambda f: (f["path"] != path, len(f["path"])))):
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
                "defines_count": len(defines),
                "defines": [
                    {"fqn": d["fqn"], "kind": d["kind"], "at": cite(d["anchor"])}
                    for d in budget.take(defines)
                ],
                "io_edges_count": len(edges),
                "io_edges": [
                    {"channel": e["channel"], "target": e["target"], "at": cite(e["anchor"])}
                    for e in budget.take(edges)
                ],
                "claims": budget.take(claims),
            }
        )
    return _finish({"query": "file", "path": path, "found": out}, store, budget)


def q_module(store: Store, name: str, budget: Optional[Budget] = None) -> Dict:
    budget = budget or Budget()
    modules = [m for m in store.inventory["modules"] if m["name"] == name or _matches(m["name"], name)]
    if not modules:
        return _finish({"query": "module", "name": name, "found": []}, store, budget)
    graph = store.graph
    out = []
    for module in budget.take(modules):
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
                # The tally is over *every* claim, not the budgeted list: a
                # count that shrinks with the budget would understate the module.
                "claims_count": len(claims),
                "claims_by_kind": _tally(c["kind"] for c in claims),
                "claims": budget.take(claims),
            }
        )
    return _finish({"query": "module", "name": name, "found": out}, store, budget)


def q_routes(store: Store, pattern: Optional[str] = None,
             budget: Optional[Budget] = None,
             exclude_role: Optional[Sequence[str]] = None) -> Dict:
    budget = budget or Budget()
    routes = store.xref["routes"] + store.xref["unresolved_routes"]
    if pattern:
        routes = [r for r in routes if _matches(r["route"], pattern) or _matches(r["verb"], pattern)]
    if exclude_role:
        roles = _role_index(store)
        # Dropped only if every evidence anchor is excluded-role.
        routes = [
            r for r in routes
            if any(roles.get(a.get("file")) not in exclude_role for a in r["evidence"])
        ]
    return _finish(
        {
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
                for r in budget.take(routes)
            ],
        },
        store,
        budget,
    )


def q_table(store: Store, name: Optional[str] = None,
            budget: Optional[Budget] = None,
            exclude_role: Optional[Sequence[str]] = None) -> Dict:
    """Who owns, writes and reads each table.

    "What breaks if I change this table" reduces to the union of the three
    lists below, and every entry carries the line that put it there.

    `RESEARCH_GRAPHIFY.md §10` calls this and `q_config` the worst of the silent
    truncations, and it is right: "who writes this table" is exactly the
    question where a partial list reads as a complete one and a wrong
    blast-radius conclusion follows directly from it.
    """
    budget = budget or Budget()
    roles = _role_index(store) if exclude_role else {}
    buckets: Dict[str, Dict[str, List[Dict]]] = {}
    for edge in store.extraction["io_edges"]:
        if not edge["target"].startswith("table:"):
            continue
        table = edge["target"][len("table:") :]
        if name and not _matches(table, name):
            continue
        if exclude_role and roles.get(edge["anchor"].get("file")) in exclude_role:
            continue
        slot = buckets.setdefault(table, {"schema_own": [], "persist": [], "read": []})
        if edge["channel"] in slot:
            slot[edge["channel"]].append(edge)

    out = []
    for table in budget.take(sorted(buckets)):
        slot = buckets[table]
        evidence = slot["persist"] + slot["read"]
        out.append(
            {
                "table": table,
                "schema_owned_by": sorted({e["module"] for e in slot["schema_own"]}),
                "migration_count": len(slot["schema_own"]),
                "migrations": [cite(e["anchor"]) for e in budget.take(slot["schema_own"])],
                "written_by": sorted({e["source"] for e in slot["persist"]}),
                "read_by": sorted({e["source"] for e in slot["read"]}),
                "evidence_count": len(evidence),
                "evidence": [cite(e["anchor"]) for e in budget.take(evidence)],
            }
        )
    return _finish(
        {"query": "table", "name": name, "count": len(buckets), "tables": out},
        store, budget,
    )


def q_config(store: Store, key: Optional[str] = None,
             budget: Optional[Budget] = None,
             exclude_role: Optional[Sequence[str]] = None) -> Dict:
    budget = budget or Budget()
    roles = _role_index(store) if exclude_role else {}
    rows: Dict[str, Dict] = {}
    for row in store.extraction["defines"]:
        if row["kind"] != "config_key" or not row["fqn"].startswith("config:"):
            continue
        name = row["fqn"][len("config:") :]
        if key and not _matches(name, key):
            continue
        if exclude_role and roles.get(row["anchor"].get("file")) in exclude_role:
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
        if exclude_role and roles.get(edge["anchor"].get("file")) in exclude_role:
            continue
        rows.setdefault(name, {"key": name, "declared": [], "read": [], "values": []})["read"].append(
            {"by": edge["source"], "at": cite(edge["anchor"])}
        )

    out = []
    for name in budget.take(sorted(rows)):
        slot = rows[name]
        out.append(
            {
                "key": name,
                "values": slot["values"],
                "declared_count": len(slot["declared"]),
                "declared": budget.take(slot["declared"]),
                "read_count": len(slot["read"]),
                "read": budget.take(slot["read"]),
            }
        )
    return _finish({"query": "config", "count": len(rows), "keys": out}, store, budget)
