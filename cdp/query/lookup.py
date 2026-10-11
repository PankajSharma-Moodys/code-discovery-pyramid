"""Lookups by name: symbol, file, module, routes, table, config."""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence

from .budget import Budget
from .common import _claim_module, _finish, _matches, _role_index, _tally, cite
from .store import Store


def _type_index(store: Store):
    idx = getattr(store, "_type_index", None)
    if idx is None:
        from ..pytypes import PyIndex
        idx = PyIndex(store.extraction, store.xref["symbols"], [f["path"] for f in store.inventory["files"]])
        store._type_index = idx
    return idx


def _cs_index(store: Store):
    idx = getattr(store, "_cs_index", None)
    if idx is None:
        from ..cstypes import CsTypeIndex
        idx = CsTypeIndex(store.extraction, store.xref["symbols"])
        store._cs_index = idx
    return idx


def _member_keys(store: Store, name: str) -> Dict[str, str]:
    """`Class#method` -> {symbol key: how it was reached}. The method is looked
    up on the class and, failing that, up its superclass/interface chain, then
    its enclosing classes. Never a prefix or substring match: `setServerHint`
    must not answer for `setServerHintApplied`."""
    owner_part, _, member = name.partition("#")
    symbols = store.xref["symbols"]
    owners = [k for k, e in symbols.items()
              if e["kind"] in ("class", "interface", "enum", "record", "annotation")
              and (k == owner_part or k.endswith("." + owner_part))]
    found: Dict[str, str] = {}
    types = _type_index(store)
    for owner in sorted(owners):
        simple = owner.rsplit(".", 1)[-1]
        wanted = "<init>" if member in (simple, "<init>") else member
        is_cs = symbols[owner]["sites"][0]["file"].endswith(".cs")
        decl = (_cs_index(store) if is_cs else types).declaring(owner, wanted)
        if decl:
            declaring = decl.split("#", 1)[0]
            found[decl] = "" if declaring == owner else \
                "%s does not declare it; it inherits it from %s" % (owner, declaring)
    return found


def q_symbol(store: Store, name: str, budget: Optional[Budget] = None,
             exclude_role: Optional[Sequence[str]] = None, exact: bool = False) -> Dict:
    """Definition sites, used-by, and collisions for a symbol.

    A bare name matches by substring (exact last-name matches first); `exact`
    keeps only exact names. `Class#method` is always exact: the method on the
    class, or the superclass/interface that declares what the class inherits.
    """
    budget = budget or Budget()
    roles = _role_index(store) if exclude_role else {}
    xref = store.xref
    exact_hit = xref["symbols"].get(name)
    via: Dict[str, str] = {}
    if exact_hit:
        keys, mode = [name], "exact"
    elif "#" in name:
        via = _member_keys(store, name)
        keys = list(via)
        by_suffix = [k for k in xref["symbols"] if k.endswith("." + name)]
        keys += [k for k in by_suffix if k not in via]
        mode = "exact"
    elif exact:
        keys = [k for k in xref["symbols"] if k == name or k.rsplit(".", 1)[-1] == name
                or k.rsplit("#", 1)[-1] == name]
        mode = "exact"
    else:
        keys = [k for k in xref["symbols"]
                if k == name or k.rsplit(".", 1)[-1] == name or _matches(k, name)]
        mode = "substring"
    # An exact match on the last name first -- a class or, for `Class#method`,
    # the method -- so a bare method name finds the method and its callers
    # before any class whose name merely contains it.
    def tier(k: str) -> int:
        last = k.rsplit(".", 1)[-1]
        return 0 if last == name or last.rsplit("#", 1)[-1] == name else 1

    keys = sorted(keys, key=lambda k: (tier(k), len(k)))
    keys = budget.take(keys)
    if not keys:
        return _finish({"query": "symbol", "name": name, "match": mode, "found": []}, store, budget)

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
        users = list(xref["used_by"].get(key, []))
        if entry["kind"] in ("class", "enum", "record"):
            users += xref["used_by"].get(key + "#<init>", [])   # `new X(..)` on a declared constructor
            users.sort(key=lambda u: (u["module"], u["file"], u["anchor"]["line"]))
        # a site is a line: two uses on one line (`X x = new X()`) are one site
        seen_sites: set = set()
        users = [u for u in users if not ((u["file"], u["anchor"]["line"]) in seen_sites
                                          or seen_sites.add((u["file"], u["anchor"]["line"])))]
        if exclude_role:
            users = [u for u in users if roles.get(u.get("file")) not in exclude_role]
        claims = [c for c in store.state["claims"] if c.get("subject") == key or _matches(c.get("statement", ""), key.rsplit(".", 1)[-1])]
        out.append(
            {
                "fqn": key,
                "kind": entry["kind"],
                "visibility": entry["visibility"],
                "via": via.get(key) or None,
                "modules": entry["modules"],
                "value": entry.get("value"),
                "defined_at": [cite(s["anchor"]) for s in sites],
                # `file:start-end` where the extent is known, so a read can be
                # exactly the member.
                "defined_range": [
                    cite(s["anchor"]) + ("-%d" % s["end_line"]
                                         if s.get("end_line") and s["end_line"] != s["anchor"]["line"] else "")
                    for s in sites
                ],
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
    return _finish({"query": "symbol", "name": name, "match": mode, "found": out}, store, budget)


def _short_name(fqn: str) -> str:
    """`pkg.Outer.Inner#method` -> `Inner#method`; `pkg.Type` -> `Type`."""
    owner, sep, member = fqn.partition("#")
    return owner.rsplit(".", 1)[-1] + sep + member


def q_file(store: Store, path: str, budget: Optional[Budget] = None,
           exclude_role: Optional[Sequence[str]] = None, exact: bool = False) -> Dict:
    """One file's outline. A term matches a path by case-insensitive substring;
    `exact` keeps only the path itself or a path ending in `/<term>`."""
    budget = budget or Budget()
    mode = "exact" if exact else "substring"
    hit = (lambda p: p == path or p.endswith("/" + path)) if exact else \
        (lambda p: p == path or _matches(p, path))
    files = [
        f for f in store.inventory["files"]
        if hit(f["path"]) and not (exclude_role and f["role"] in exclude_role)
    ]
    if not files:
        return _finish({"query": "file", "path": path, "match": mode, "found": []}, store, budget)
    out = []
    for entry in budget.take(sorted(files, key=lambda f: (f["path"] != path, len(f["path"])))):
        rel = entry["path"]
        info = store.extraction["files"].get(rel, {})
        defines = sorted((d for d in store.extraction["defines"] if d["file"] == rel),
                         key=lambda d: d["anchor"]["line"])
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
                    {"fqn": d["fqn"], "kind": d["kind"], "at": cite(d["anchor"]),
                     "name": _short_name(d["fqn"]), "visibility": d.get("visibility"),
                     "line": d["anchor"]["line"], "end_line": d.get("end_line")}
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
    return _finish({"query": "file", "path": path, "match": mode, "found": out}, store, budget)


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
             exclude_role: Optional[Sequence[str]] = None, exact: bool = False) -> Dict:
    """The HTTP surface. A pattern matches the route path or the verb, never the
    handler; by case-insensitive substring, or with `exact` the whole path/verb."""
    budget = budget or Budget()
    mode = "exact" if exact else "substring"
    routes = store.xref["routes"] + store.xref["unresolved_routes"]
    if pattern:
        same = (lambda a: a.lower() == pattern.lower()) if exact else (lambda a: _matches(a, pattern))
        routes = [r for r in routes if same(r["route"]) or same(r["verb"])]
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
            "match": mode if pattern else "all",
            "matched_on": "route path or verb" if pattern else None,
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
            exclude_role: Optional[Sequence[str]] = None, exact: bool = False) -> Dict:
    """Who owns, writes and reads each table.

    "What breaks if I change this table" reduces to the union of the three
    lists below, and every entry carries the line that put it there.

    `RESEARCH_GRAPHIFY.md §10` calls this and `q_config` the worst of the silent
    truncations, and it is right: "who writes this table" is exactly the
    question where a partial list reads as a complete one and a wrong
    blast-radius conclusion follows directly from it.
    """
    budget = budget or Budget()
    mode = "exact" if exact else "substring"
    same = (lambda t: t.lower() == name.lower()) if exact else (lambda t: _matches(t, name or ""))
    roles = _role_index(store) if exclude_role else {}
    buckets: Dict[str, Dict[str, List[Dict]]] = {}
    for edge in store.extraction["io_edges"]:
        if not edge["target"].startswith("table:"):
            continue
        table = edge["target"][len("table:") :]
        if name and not same(table):
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
        {"query": "table", "name": name, "match": mode if name else "all", "count": len(buckets), "tables": out},
        store, budget,
    )


#: Citations each key is guaranteed before any key gets more (H1).
CITES_PER_KEY = 3


def q_config(store: Store, key: Optional[str] = None,
             budget: Optional[Budget] = None,
             exclude_role: Optional[Sequence[str]] = None, exact: bool = False) -> Dict:
    """Config keys and env vars: where declared, every site that reads them.

    The budget is spent on citations, not just names: keys are ranked by how
    many sites read them, and each key shown is charged one row plus up to
    `CITES_PER_KEY` citations; whatever is left tops keys up to *every* site.
    What does not fit is counted (`keys_elided`, per-key `read_elided`), never
    dropped silently. Keys read through a constant are resolved to the key's
    value; a key computed at run time is listed as `(dynamic)`.
    """
    from ..resolve import config_reads

    budget = budget or Budget()
    mode = "exact" if exact else "substring"
    same = (lambda n: n.lower() == key.lower()) if exact else (lambda n: _matches(n, key or ""))
    roles = _role_index(store) if exclude_role else {}
    rows: Dict[str, Dict] = {}

    def slot_of(name: str) -> Dict:
        return rows.setdefault(name, {"key": name, "declared": [], "read": [], "values": []})

    for row in store.extraction["defines"]:
        if row["kind"] != "config_key" or not row["fqn"].startswith("config:"):
            continue
        name = row["fqn"][len("config:") :]
        if key and not same(name):
            continue
        if exclude_role and roles.get(row["anchor"].get("file")) in exclude_role:
            continue
        slot = slot_of(name)
        slot["declared"].append(cite(row["anchor"]))
        if row.get("value") and row["value"] not in slot["values"]:
            slot["values"].append(row["value"])
    for read in config_reads(store.extraction, store.xref.get("constants", {}),
                         store.xref.get("config_wrapped", ())):
        if key and not same(read["key"]):
            continue
        if exclude_role and roles.get(read["file"]) in exclude_role:
            continue
        site = {"by": read["by"], "at": cite(read["anchor"])}
        if read.get("symbolic"):
            site["via_constant"] = read["symbolic"]
        slot_of(read["key"])["read"].append(site)

    ranked = sorted(rows.values(), key=lambda s: (-len(s["read"]), -len(s["declared"]), s["key"]))
    room = budget.limit - budget.spent
    shown: List[Dict] = []
    for slot in ranked:
        sites = len(slot["read"]) + len(slot["declared"])
        # A key is never shown bare when it has sites: with less room than the usual
        # charge it takes the citations that fit (at least one).
        cites = min(CITES_PER_KEY, sites, room - 1)
        if room >= 1 and (cites >= 1 or sites == 0):
            room -= 1 + max(cites, 0)
            n_read = min(cites, len(slot["read"]))
            shown.append({"slot": slot, "reads": n_read,
                          "decls": min(cites - n_read, len(slot["declared"]))})
    for item in shown:  # top up toward every site, reads first
        slot = item["slot"]
        more = min(room, len(slot["read"]) - item["reads"])
        item["reads"] += more
        room -= more
        more = min(room, len(slot["declared"]) - item["decls"])
        item["decls"] += more
        room -= more

    out = []
    sites_elided = 0
    for item in shown:
        slot = item["slot"]
        sites_elided += len(slot["read"]) - item["reads"] + len(slot["declared"]) - item["decls"]
        out.append({
            "key": slot["key"],
            "values": slot["values"],
            "declared_count": len(slot["declared"]),
            "declared": slot["declared"][:item["decls"]],
            "read_count": len(slot["read"]),
            "read": slot["read"][:item["reads"]],
        })
    shown_keys = {item["slot"]["key"] for item in shown}
    hidden = [s for s in ranked if s["key"] not in shown_keys]
    budget.spent = budget.limit - room
    budget.elided += len(hidden) + sum(len(s["read"]) + len(s["declared"]) for s in hidden) + sites_elided
    result = {"query": "config", "match": mode if key else "all", "count": len(rows), "keys": out,
              "keys_elided": len(hidden), "sites_elided": sites_elided
              + sum(len(s["read"]) + len(s["declared"]) for s in hidden)}
    if hidden:
        result["elided_keys"] = [s["key"] for s in hidden[:20]]
    return _finish(result, store, budget)
