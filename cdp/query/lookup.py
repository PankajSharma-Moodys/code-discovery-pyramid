"""Lookups by name: symbol, file, module, routes, table, config."""

from __future__ import annotations

import json
import re
from typing import Dict, List, Optional, Sequence, Tuple

from .. import codeindex, sigs
from .budget import Budget
from .common import visible_signals, ann_view, annotations_of, _claim_module, _fair_split_budget, _finish, _matches, make_matcher, _role_index, _tally, cite, route_inputs
from .views import state_rows, state_section
from .store import LazyMap, Store, code_text, edges_where, extract_where, file_edges, file_rows, prefetch_symbols, symbols_of, used_by_of, xref_field, xref_get, xref_uses_of
from ..rules import all_edges


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
    symbols = symbols_of(store)
    named = [k for k in symbols if k == owner_part or k.endswith("." + owner_part)]
    prefetch_symbols(store, named, owners=False)
    owners = [k for k in named if symbols[k]["kind"] in ("class", "interface", "enum", "record", "annotation")]
    found: Dict[str, str] = {}
    for owner in sorted(owners):
        simple = owner.rsplit(".", 1)[-1]
        wanted = "<init>" if member in (simple, "<init>") else member
        if owner + "#" + wanted in symbols:
            # every `declaring` (Java, C#, Python) looks at the owner itself first: no index needed
            decl = owner + "#" + wanted
        else:
            is_cs = symbols[owner]["sites"][0]["file"].endswith(".cs")
            decl = (_cs_index(store) if is_cs else _type_index(store)).declaring(owner, wanted)
        if decl:
            declaring = decl.split("#", 1)[0]
            found[decl] = "" if declaring == owner else \
                "%s does not declare it; it inherits it from %s" % (owner, declaring)
    return found


#: Uses (or claims) each matched symbol is guaranteed before any gets more.
MIN_USES_PER_MATCH = 3


def q_symbol(store: Store, name: str, budget: Optional[Budget] = None,
             exclude_role: Optional[Sequence[str]] = None, exact: bool = False, regex: bool = False,
             include_library: bool = True) -> Dict:
    """Definition sites, used-by, and collisions for a symbol.

    A bare name matches by substring (exact last-name matches first); `exact`
    keeps only exact names. `Class#method` is always exact: the method on the
    class, or the superclass/interface that declares what the class inherits.
    The embedded claims get the same filters as `q_claims`: `library:` subjects unless
    `include_library`, and claims whose every evidence anchor is an excluded role.
    """
    budget = budget or Budget()
    roles = _role_index(store) if exclude_role else {}
    symbols, used_by = symbols_of(store), used_by_of(store)
    exact_hit = None if regex else symbols.get(name)
    via: Dict[str, str] = {}
    if regex:
        rx = make_matcher(name, "regex")
        keys, mode = [k for k in symbols if rx(k)], "regex"
    elif exact_hit:
        keys, mode = [name], "exact"
    elif "#" in name:
        via = _member_keys(store, name)
        keys = list(via)
        by_suffix = [k for k in symbols if k.endswith("." + name)]
        keys += [k for k in by_suffix if k not in via]
        mode = "exact"
    elif exact:
        keys = [k for k in symbols if k == name or k.rsplit(".", 1)[-1] == name
                or k.rsplit("#", 1)[-1] == name]
        mode = "exact"
    else:
        keys = [k for k in symbols
                if k == name or k.rsplit(".", 1)[-1] == name or _matches(k, name)]
        mode = "substring"
    # An exact match on the last name first -- a class or, for `Class#method`,
    # the method -- so a bare method name finds the method and its callers
    # before any class whose name merely contains it.
    def tier(k: str) -> int:
        last = k.rsplit(".", 1)[-1]
        return 0 if last == name or last.rsplit("#", 1)[-1] == name else 1

    keys = sorted(keys, key=lambda k: (tier(k), len(k)))
    if not keys:
        return _finish({"query": "symbol", "name": name, "match": mode, "found": []}, store, budget)

    pending = []
    for key in keys:
        entry = symbols[key]
        sites = entry["sites"]
        if exclude_role:
            # A symbol drops from the answer only once every one of its
            # definition sites is excluded-role -- one real site is enough
            # to keep it.
            sites = [s for s in sites if roles.get(s["anchor"].get("file")) not in exclude_role]
            if not sites:
                continue
        users = list(used_by.get(key, []))
        # D4a: one row per enum value used, so taken before the per-line site merge below
        evidence = [u for u in users if u.get("access") and roles.get(u.get("file")) not in (exclude_role or ())]
        if entry["kind"] in ("class", "enum", "record"):
            users += used_by.get(key + "#<init>", [])   # `new X(..)` on a declared constructor
            users.sort(key=lambda u: (u["module"], u["file"], u["anchor"]["line"]))
        # a site is a line: two uses on one line (`X x = new X()`) are one site
        seen_sites: set = set()
        users = [u for u in users if not ((u["file"], u["anchor"]["line"]) in seen_sites
                                          or seen_sites.add((u["file"], u["anchor"]["line"])))]
        if exclude_role:
            users = [u for u in users if roles.get(u.get("file")) not in exclude_role]
        claims = [c for c in store.state["claims"] if c.get("subject") == key or _matches(c.get("statement", ""), key.rsplit(".", 1)[-1])]
        if not include_library:
            claims = [c for c in claims if "library:" not in c.get("subject", "")]
        if exclude_role:
            claims = [c for c in claims
                      if any(roles.get(a.get("file")) not in exclude_role for a in c.get("evidence", []))]
        pending.append((key, entry, sites, users, claims,
                        state_rows(_role_index(store) if evidence else {}, evidence)))

    # One allowance, shared fairly: with several matches the first must not spend
    # the whole budget on its own use list and leave the rest "N more". Each match
    # gets an equal share of what is left (a short list returns its unused rows).
    # Each match reserves its own row plus a few uses; matches that do not fit even
    # that are counted as elided (re-run with a longer term or a bigger budget).
    room, chosen = budget.limit - budget.spent, []
    for item in pending:
        cost = 1 + min(len(item[3]) + len(item[4]) + len(item[5][0]), MIN_USES_PER_MATCH)
        if cost > room and (chosen or room < 1):
            break
        room -= cost
        chosen.append(item)
    budget.elided += len(pending) - len(chosen)
    budget.items = ("match", len(pending), len(pending) - len(chosen))  # a dropped match's uses go uncounted
    budget.spent += len(chosen)
    pending = chosen
    shares = _fair_split_budget(budget.limit - budget.spent,
                                [len(u) + len(c) + len(st[0]) for _, _, _, u, c, st in pending])
    out = []
    for (key, entry, sites, users, claims, (states, tally)), share in zip(pending, shares):
        # an enum's write/guard sites come first: they are what a lifecycle diagram is drawn from
        shown_states = states[:share]
        budget.spent, budget.elided, share = (budget.spent + len(shown_states), budget.elided + len(states)
                                              - len(shown_states), share - len(shown_states))
        n_users = min(len(users), share)
        n_claims = min(len(claims), share - n_users)
        shown_users = Budget(n_users).take(users)
        shown_claims = Budget(n_claims).take(claims)
        budget.spent += len(shown_users) + len(shown_claims)
        budget.elided += len(users) - len(shown_users) + len(claims) - len(shown_claims)
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
                **_collision(entry),
                **annotations_of(store, key),
                **_symbol_body(store, key, entry, sites),
                # The true total, kept alongside the budgeted list, so the
                # renderer states "used by 47 site(s)" even when it shows 12.
                "used_by_count": len(users),
                # `in`: the method/function whose body holds the use -- the caller node a diagram names.
                "used_by": [_use_row(store, u) for u in shown_users],
                "claims": shown_claims,
                "claims_count": len(claims),
                # The way to every use of this one match, at the full budget.
                "see_all": "cdp query symbol %s --exact" % key if len(users) + len(states) >
                len(shown_users) + len(shown_states) else None,
            }
        )
        if tally:   # an enum's values, declaration line then name, for the ones nothing writes
            members = sorted((d["anchor"]["line"], d["fqn"].rpartition(".")[2]) for s in sites
                             for d in file_rows(store, s["anchor"]["file"], "defines")
                             if d["fqn"].rpartition(".")[0] == key and d["kind"] in ("field", "constant"))
            out[-1].update(state_section(states, shown_states, tally, [m for _, m in members],
                                         lambda u: _use_row(store, u)))
    return _finish({"query": "symbol", "name": name, "match": mode, "found": out}, store, budget)


def _use_row(store: Store, u: Dict) -> Dict:
    """One `used_by` row: module, the use's own line, and (where one encloses it) the member it is in."""
    row = {"module": u["module"], "at": cite(u["anchor"])}
    owner = _enclosing_member(store, u["file"], u["anchor"]["line"])
    if owner:
        row["in"] = owner
    return row


def _enclosing_member(store: Store, rel: str, line: int) -> Optional[str]:
    """The fqn of the innermost method/function definition in `rel` whose extent holds `line`, or
    None (a use at class or field level). From the file's `defines` extents, built once per file."""
    def build() -> List:
        return sorted(((d["anchor"]["line"], d.get("end_line") or d["anchor"]["line"], d["fqn"])
                       for d in file_rows(store, rel, "defines") if d["kind"] in ("method", "function")),
                      key=lambda e: (e[0], -e[1]))

    best = None
    for lo, hi, fqn in _memo(store, "_member_extents:" + rel, build):
        if lo > line:
            break
        if line <= hi:
            best = fqn   # sorted by start, so a later hit starts inside the earlier one: innermost wins
    return best


def _memo(store: Store, key: str, build):
    """Per-query cache on the store; a duck-typed store with no cache just rebuilds."""
    cache = getattr(store, "_cache", None)
    if cache is None:
        return build()
    if key not in cache:
        cache[key] = build()
    return cache[key]


def _call_index(store: Store, rel: str) -> Dict:
    """`(file, from_sig or from_symbol) -> [call row, ...]` (in source order) from one file's `uses`
    rows of kind `call`: an overload's calls are keyed by its own sig (cdp/sigs.py); built once per
    file per query. The rows themselves, not a tuple per row: allocating 100k+ tuples on a loaded
    store costs ~0.3 s in GC."""
    def build() -> Dict:
        seen: Dict = {}
        for u in sorted((u for u in file_rows(store, rel, "uses") if u.get("kind") == "call" and u.get("from_symbol")),
                        key=lambda u: (u["file"], u["anchor"]["line"])):
            seen.setdefault((u["file"], u.get("from_sig") or u["from_symbol"]), []).append(u)
        return seen

    return _memo(store, "_call_index:" + rel, build)


def _defines_per_name(store: Store, rel: str) -> Dict:
    """`(file, fqn) -> how many method definitions` in one file -- more than one is an overload."""
    def build() -> Dict:
        n: Dict = {}
        for d in file_rows(store, rel, "defines"):
            if d["kind"] in ("method", "function"):
                n[(d["file"], d["fqn"])] = n.get((d["file"], d["fqn"]), 0) + 1
        return n

    return _memo(store, "_defines_per_name:" + rel, build)


def _calls_of(store: Store, rel: str, fqn: str, d: Dict) -> List[str]:
    """The members one definition's body calls, deduped. An overload reads its own `from_sig` rows. A
    store scanned before overloads had sigs pools every overload's calls under the name, so there the
    calls are cut to the ones inside this definition's lines. Calls under the name but outside every
    overload (a field initialiser, which runs in every constructor) belong to each overload, as in the graph."""
    index = _call_index(store, rel)
    rows = index.get((rel, d.get("sig") or fqn), [])
    if d.get("sig") and (rel, fqn) in index:
        rows = sorted(rows + index[(rel, fqn)], key=lambda r: r["anchor"]["line"])
    if not d.get("sig") and _defines_per_name(store, rel).get((rel, fqn), 0) > 1:
        lo = d["anchor"]["line"]
        hi = d.get("end_line") or lo
        rows = [r for r in rows if lo <= r["anchor"]["line"] <= hi]
    out: List[str] = []
    for r in rows:
        fqn = _resolved_target(store, r) if r.get("chain") or r.get("strict") else r["fqn"]
        if fqn and fqn not in out:
            out.append(fqn)
    return out


def _collision(entry: Dict) -> Dict:
    """`collision` and `overloads` for one symbol (the rule is `sigs.collision`, shared with the scan)."""
    clash, overloads = sigs.collision(entry["sites"])
    return {"collision": clash, "overloads": overloads} if overloads else {"collision": clash}


def _resolved_target(store: Store, row: Dict) -> Optional[str]:
    """The callee of a chained or strict call row as resolve settled it, or None where resolve dropped
    it. The row's own `fqn` is only the extractor's guess: a chain's *base* type (`logger.info` in a
    `StrictLogging` class: `Svc#info`), or for a bare call the enclosing class (`when(..)` from a
    Mockito static import: `SvcTest#when`) -- either credits the call to a class that does not declare
    it. Matched by file, line, caller and method name (two same-named calls on one line share one)."""
    def build() -> List:
        # one file's call rows, not one tuple key per row: 50k+ allocations on a loaded store cost ~0.3 s in GC
        return [u for u in xref_uses_of(store, row["file"]) if u.get("kind") == "call"]

    line, caller, tail = row["anchor"]["line"], row.get("from_symbol"), "#" + row["fqn"].rpartition("#")[2]
    for u in _memo(store, "_resolved_calls:" + row["file"], build):
        if u["anchor"]["line"] == line and u.get("from_symbol") == caller and u["fqn"].endswith(tail):
            return u["fqn"]
    return None


def _body_facts(store: Store, rel: str, fqn: str, d: Dict) -> Dict:
    """What a method body does, from facts already indexed: the members it calls, the exceptions it
    declares, and how many string literals its body holds (counted from the `code` artifact).
    Empty keys are left out."""
    if d.get("kind") not in ("method", "function"):
        return {}
    out: Dict = {}
    calls = _calls_of(store, rel, fqn, d)
    if calls:
        out["calls"] = [_short_name(c) for c in calls]
    if d.get("throws"):
        out["throws"] = list(d["throws"])
    text = code_text(store, rel)
    end = d.get("end_line")
    if text and end:
        n = codeindex.count_literals(rel, text, d["anchor"]["line"], end)
        if n:
            out["literals"] = n
    return out


def _define_annotations(rel: str, d: Dict) -> Dict:
    """`annotations` and annotated `params` of one define row, as the query shows them."""
    out: Dict = {}
    if d.get("annotations"):
        out["annotations"] = ann_view(rel, d["annotations"])
    params = [{"name": p["name"], "type": p.get("type"), "annotations": ann_view(rel, p["annotations"])}
              for p in d.get("params", []) if p.get("annotations")]
    if params:
        out["params"] = params
    return out


def _symbol_body(store: Store, key: str, entry: Dict, sites: List[Dict]) -> Dict:
    """`body`: one row per definition site of a method (overloads differ): calls, throws, literals."""
    if entry["kind"] not in ("method", "function"):
        return {}
    body = []
    for s in sites:
        rows = _memo(store, "_method_rows:" + s["file"],
                     lambda: {(d["fqn"], d["file"], d["anchor"]["line"]): d
                              for d in file_rows(store, s["file"], "defines") if d["kind"] in ("method", "function")})
        d = rows.get((key, s["file"], s["anchor"]["line"]))
        facts = _body_facts(store, s["file"], key, d) if d else {}
        if facts or s.get("sig"):
            body.append({"at": cite(s["anchor"]), **({"sig": s["sig"]} if s.get("sig") else {}), **facts})
    return {"body": body} if body else {}


def _short_name(fqn: str) -> str:
    """`pkg.Outer.Inner#method` -> `Inner#method`; `pkg.Type` -> `Type`."""
    owner, sep, member = fqn.partition("#")
    return owner.rsplit(".", 1)[-1].rsplit("/", 1)[-1] + sep + member


def q_file(store: Store, path: str, budget: Optional[Budget] = None,
           exclude_role: Optional[Sequence[str]] = None, exact: bool = False, regex: bool = False) -> Dict:
    """One file's outline. A term matches a path by case-insensitive substring;
    `exact` keeps only the path itself or a path ending in `/<term>`."""
    budget = budget or Budget()
    mode = "regex" if regex else "exact" if exact else "substring"
    if regex:
        hit = make_matcher(path, "regex")
    else:
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
        info = file_rows(store, rel, "meta") or {}
        defines = sorted((d for d in file_rows(store, rel, "defines") if d["file"] == rel),
                         key=lambda d: d["anchor"]["line"])
        edges = [e for e in file_edges(store, rel) if e["file"] == rel]
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
                "signals": visible_signals(info.get("signals", [])),
                "defines_count": len(defines),
                "defines": [
                    {"fqn": d["fqn"], "kind": d["kind"], "at": cite(d["anchor"]),
                     "name": _short_name(d["fqn"]), "visibility": d.get("visibility"),
                     "line": d["anchor"]["line"], "end_line": d.get("end_line"),
                     **({"sig": d["sig"]} if d.get("sig") else {}),
                     **_define_annotations(rel, d), **_body_facts(store, rel, d["fqn"], d)}
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


def q_module(store: Store, name: str, budget: Optional[Budget] = None, match: str = "substring") -> Dict:
    budget = budget or Budget()
    hit = make_matcher(name, match)
    modules = [m for m in store.inventory["modules"] if m["name"] == name or hit(m["name"])]
    if not modules:
        return _finish({"query": "module", "name": name, "match": match, "found": []}, store, budget)
    graph = store.graph
    out = []
    for module in budget.take_items(modules, "module"):
        key = module["name"]
        claims = [c for c in store.state["claims"] if _claim_module(c, store) == key
                  and "library:" not in c.get("subject", "")]  # same default as `claims`: import edges are noise
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
                "version_platforms": [
                    e["to"] for e in graph.get("declared", ()) if e["from"] == key and e.get("uses") == "version platform"
                ],
                "scopes": [s["node"] for s in store.partition["scopes"] if s["module"] == key],
                # The tally is over *every* claim, not the budgeted list: a
                # count that shrinks with the budget would understate the module.
                "claims_count": len(claims),
                "claims_by_kind": _tally(c["kind"] for c in claims),
                "claims": budget.take(claims),
            }
        )
    return _finish({"query": "module", "name": name, "match": match, "found": out, "found_count": len(modules)},
                   store, budget)


def _route_hit(r: Dict, pattern: str, exact: bool, regex=None) -> Optional[str]:
    """How `pattern` matched a route: `path`, `verb`, `verb+path` (`POST /v1/x`) or
    `handler` (class, method or `Class#method`, never a package prefix); else None. With `regex`
    (a compiled-pattern matcher) the pattern is searched in each of those, in that order."""
    if regex:
        owner, _, method = r["handler"].partition("#")
        for how, text in (("path", r["route"]), ("verb", r["verb"]), ("verb+path", "%s %s" % (r["verb"], r["route"])),
                          ("handler", "%s#%s" % (owner.rsplit(".", 1)[-1], method)), ("handler", r["handler"])):
            if regex(text):
                return how
        return None
    low = pattern.lower().strip()
    same = (lambda a: str(a).lower() == low) if exact else (lambda a: low in str(a).lower())
    if same(r["route"]):
        return "path"
    if same(r["verb"]):
        return "verb"
    verb, _, path = low.partition(" ")
    path = path.strip()
    if path and verb.upper() == r["verb"].upper() and (
            path == r["route"].lower() or (not exact and path in r["route"].lower())):
        return "verb+path"
    owner, _, method = r["handler"].partition("#")
    simple = owner.rsplit(".", 1)[-1]
    if exact:
        if low in (simple.lower(), method.lower(), (simple + "#" + method).lower(), r["handler"].lower()):
            return "handler"
    elif "." not in low and low in (simple + "#" + method).lower():
        return "handler"
    return None


def _inputs_of(store: Store, route: Dict) -> Dict:
    inputs = route_inputs(store, route["handler"], route["evidence"])
    return {"inputs": inputs} if inputs else {}


def q_routes(store: Store, pattern: Optional[str] = None,
             budget: Optional[Budget] = None,
             exclude_role: Optional[Sequence[str]] = None, exact: bool = False, regex: bool = False) -> Dict:
    """The HTTP surface. A pattern matches the route path, the verb, `VERB /path`
    or the handler's class/method; by case-insensitive substring, or with `exact`
    the whole name. Each row says which of those matched."""
    budget = budget or Budget()
    mode = "regex" if regex else "exact" if exact else "substring"
    routes = xref_field(store, "routes") + xref_field(store, "unresolved_routes")
    via: Dict[int, str] = {}
    rx = make_matcher(pattern, "regex") if (pattern and regex) else None
    if pattern:
        keep = []
        for r in routes:
            how = _route_hit(r, pattern, exact, rx)
            if how:
                via[id(r)] = how
                keep.append(r)
        routes = keep
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
            "matched_on": "route path or verb, or handler class/method" if pattern else None,
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
                    **({"matched_via": via[id(r)]} if pattern else {}),
                    **annotations_of(store, r["handler"]),
                    **_inputs_of(store, r),
                }
                for r in budget.take(routes)
            ],
        },
        store,
        budget,
    )


#: Sites listed per writer/reader group; the group's `count` is always the true total.
SITES_PER_GROUP = 3


def _dedupe_cites(edges: Sequence[Dict]) -> List[str]:
    """Distinct `file:line` of `edges`, in first-seen order (a persist and a read
    edge on one `DbSet` line are one site, not two)."""
    seen: Dict[str, None] = {}
    for e in edges:
        seen.setdefault(cite(e["anchor"]), None)
    return list(seen)


def _site_groups(store: Store, edges: Sequence[Dict]) -> List[Dict]:
    """Edges grouped by who they come from, with distinct sites and counts.

    A `migration:V1__x.sql` source is a script, not a symbol, and a table can have
    dozens: they collapse into one `SQL migration scripts` group (count = sites,
    `files` = scripts) instead of a list of identical labels."""
    groups: Dict[str, Dict] = {}
    for e in sorted(edges, key=lambda e: (e["source"], e["anchor"]["file"], e["anchor"]["line"])):
        src = e["source"]
        script = src.startswith("migration:")
        key = "SQL migration scripts" if script else src
        g = groups.setdefault(key, {"by": key if script else src.rsplit(".", 1)[-1], "fqn": None if script else src,
                                    "kind": "script" if script else "code", "sites": {}, "files": set()})
        g["sites"].setdefault(cite(e["anchor"]), None)
        g["files"].add(e["anchor"]["file"])
    return sorted(({"by": g["by"], "fqn": g["fqn"], "kind": g["kind"], "count": len(g["sites"]),
                    "files": len(g["files"]), "sites": list(g["sites"]),
                    **(annotations_of(store, g["fqn"]) if g["fqn"] else {})} for g in groups.values()),
                  key=lambda g: (g["kind"] == "script", g["by"]))


def _budget_groups(groups: List[Dict], budget: Budget) -> List[Dict]:
    out = []
    for g in groups:
        out.append(dict(g, sites=budget.take(g["sites"][:SITES_PER_GROUP])))
    return out


#: What every edge `q_table` reads names (`extract_where`).
_TABLE_NEEDLES = ("table:", "entity:")


def _entity_index(store: Store) -> Dict[tuple, str]:
    """`(file, line)` -> entity type name, from the `entity:X` persist edges the C#
    extractor writes on the same line as the `table:` edges of a `DbSet<X>`."""
    out: Dict[tuple, str] = {}
    for e in edges_where(store, _TABLE_NEEDLES):
        if e["channel"] == "persist" and e["target"].startswith("entity:"):
            out[(e["anchor"]["file"], e["anchor"]["line"])] = e["target"][len("entity:"):]
    return out


def _entity_users(store: Store, edges: Sequence[Dict], entity_at: Dict[tuple, str],
                  roles: Dict[str, str], budget: Budget) -> List[Dict]:
    """Code that touches the table through its entity class: the sites that use the
    `DbSet<X>` entity type outside the DbContext file and the migrations. Reads and
    writes are not told apart (an entity use does not say which)."""
    found: Dict[str, Dict[str, None]] = {}
    done: set = set()
    symbols, used_by = symbols_of(store), used_by_of(store)
    hits = []
    for e in edges:
        ent = entity_at.get((e["anchor"]["file"], e["anchor"]["line"]))
        if not ent or (ent, e["module"]) in done:
            continue
        done.add((ent, e["module"]))
        hits.append((e, ent.rsplit(".", 1)[-1]))
    if not hits:
        return []
    named = _memo(store, "_by_simple_name", lambda: _by_simple_name(symbols))
    prefetch_symbols(store, [k for _, simple in hits for k in named.get(simple, ())], owners=False)
    keyed = [(e, simple, [k for k in named.get(simple, ()) if symbols[k]["kind"] in ("class", "record", "struct")
                          and e["module"] in symbols[k]["modules"]]) for e, simple in hits]
    if isinstance(used_by, LazyMap):
        used_by.prefetch(k for _, _, keys in keyed for k in keys)
    for e, simple, keys in keyed:
        for key in keys:
            for u in used_by.get(key, []):
                f = u["file"]
                if f == e["anchor"]["file"] or "/Migrations/" in f:
                    continue
                if roles.get(f) == "test" or "/Tests/" in f or ".Tests/" in f:
                    continue
                found.setdefault(simple, {}).setdefault(cite(u["anchor"]), None)
    found = {k: v for k, v in found.items() if v}
    found = {k: {"entity": k, "count": len(v), "sites": budget.take(list(v)[:SITES_PER_GROUP])}
             for k, v in found.items()}
    return [found[k] for k in sorted(found)]


def _by_simple_name(symbols) -> Dict[str, List[str]]:
    """`simple name -> symbol keys ending in it`, in key order."""
    out: Dict[str, List[str]] = {}
    for k in symbols:
        out.setdefault(k.rsplit(".", 1)[-1], []).append(k)
    return out


#: Spring Data method-name prefixes that write (`save`, `saveAll`, `deleteById`, `removeByX`, ...) and
#: that read (`findByX`, `getById`, `countBy..`, `existsBy..`, `readBy..`, `queryBy..`, `streamBy..`).
_REPO_WRITE_PREFIXES = ("save", "delete", "remove")
_REPO_READ_PREFIXES = ("find", "get", "read", "query", "count", "exists", "stream")
#: A custom data-access method's own query (EntityManager): what marks a method body as one.
_QUERY_CALL = re.compile(r"\bcreate(?:Native)?Query\(")
_WRITE_CALL = re.compile(r"\.(?:executeUpdate|persist|merge|remove)\(")


#: A JPA relationship field: `@OneToMany(..) [@JoinColumn(..)] private List<Child> metadata;`.
_RELATION = re.compile(r"@(OneToMany|ManyToOne|OneToOne|ManyToMany)\b(\((?:[^()]|\([^()]*\))*\))?"
                       r"(?:\s*@[\w.]+(?:\((?:[^()]|\([^()]*\))*\))?)*"
                       r"\s*(?:(?:private|protected|public|final|transient)\s+)*([\w.<>,? ]+?)\s+(\w+)\s*[;=]")
#: JPA's own defaults: the to-one sides load with their owner, the collections only when touched.
_EAGER_BY_DEFAULT = ("ManyToOne", "OneToOne")


def _relations(store: Store, entity_files: Dict[str, str]) -> List[Dict]:
    """Every relationship field declared on an entity: owner, field, target entity (simple name), how it
    loads (`EAGER`/`LAZY`) and whether the owner's saves/deletes cascade to it. Read from the entity's
    source (fields are not indexed symbols); getter-annotated (property access) mappings are not seen."""
    if isinstance(store, Store):
        texts = store.code_texts(sorted(set(entity_files.values())))
    else:
        texts = (getattr(store, "code", None) or {}).get("files") or {}
    out = []
    for owner, path in sorted(entity_files.items()):
        text = texts.get(path) or ""
        for m in _RELATION.finditer(text):
            kind, args, decl, field = m.group(1), m.group(2) or "", m.group(3), m.group(4)
            target = re.search(r"targetEntity\s*=\s*(\w+)\.class", args)
            target = target.group(1) if target else re.findall(r"[A-Z]\w*", decl.replace("java.util.", ""))[-1:]
            fetch = re.search(r"FetchType\.(EAGER|LAZY)", args)
            cascades = set(re.findall(r"CascadeType\.(\w+)", args))
            out.append({"owner": owner, "field": field, "kind": kind,
                        "target": target if isinstance(target, str) else (target[0] if target else ""),
                        "fetch": fetch.group(1) if fetch else ("EAGER" if kind in _EAGER_BY_DEFAULT else "LAZY"),
                        "cascades": bool(cascades & {"ALL", "PERSIST", "MERGE", "REMOVE"})
                        or bool(re.search(r"orphanRemoval\s*=\s*true", args)),
                        "at": "%s:%d" % (path, text.count("\n", 0, m.start()) + 1)})
    return out


def _related_access(store: Store, table: str, entities: Sequence[str], by_entity: Dict[str, Tuple[str, List[Dict]]],
                    relations: List[Dict], roles: Dict[str, str], budget: Budget) -> Tuple[List[Dict], List[Dict]]:
    """A table reached only through another entity's relationship field: read wherever the owner is read
    (EAGER) or the field's getter is called (LAZY), written wherever the owner is saved/deleted when the
    relationship cascades. One group per field, naming the mapping line, so the rule is checkable."""
    simple = {e.rsplit(".", 1)[-1] for e in entities}
    writes, reads = [], []
    for rel in relations:
        if rel["target"] not in simple or rel["owner"] not in by_entity:
            continue
        owner_table, owner_persist = by_entity[rel["owner"]]
        ow, orr = _repository_access(store, owner_table, owner_persist, roles, Budget(10 ** 6), related=False)
        how = "%s.%s (@%s, %s%s, %s)" % (rel["owner"], rel["field"], rel["kind"], rel["fetch"],
                                          ", cascade" if rel["cascades"] else "", rel["at"])
        read_sites = [s for g in orr for s in g["sites_all"]] if rel["fetch"] == "EAGER" else []
        getter = "%s#get%s" % (rel["owner"], rel["field"][:1].upper() + rel["field"][1:])
        read_sites += list(_calls_into(store, {getter: ""}, roles).get(getter, {}))
        write_sites = [s for g in ow for s in g["sites_all"]] if rel["cascades"] else []
        for sites, out in ((write_sites, writes), (list(dict.fromkeys(read_sites)), reads)):
            if sites:
                out.append({"through": how, "entity": None, "count": len(sites),
                            "sites": budget.take(sites[:SITES_PER_GROUP])})
    return writes, reads


def _access_index(store: Store, roles: Dict[str, str]) -> "_Access":
    """What every table's access lookup reads, built once per answer and only as far as asked."""
    return _memo(store, "_access_index", lambda: _Access(store, roles))


class _Access:
    """Non-test calls by owner (`O` of `O#m`), entity -> bound repositories, and the non-test methods whose
    body builds an EntityManager query. A decomposed store reads only the xref files that can hold the part
    asked for (`Store.call_owners`); otherwise one pass over all of xref. Same values, same order."""

    def __init__(self, store, roles: Dict[str, str]) -> None:
        self.store, self.roles, self.owners = store, roles, {}
        self.files = store.call_owners() if isinstance(store, Store) else None
        self._bindings = self._queries = self._words = None
        if self.files is None:
            self._bindings = self._add(store.xref["uses"], None)
            texts = (getattr(store, "code", None) or {}).get("files") or {}
            self._queries = _query_bodies(store.xref["symbols"].items(), texts)

    def _add(self, uses, owner) -> Dict[str, List[str]]:
        """Group the non-test calls of `uses` on `owner` (None: all, False: none) into `owners`; return the bindings."""
        bindings: Dict[str, List[str]] = {}
        for u in uses:
            if u.get("kind") == "binding" and u.get("from_symbol"):
                bindings.setdefault(u.get("fqn"), []).append(u["from_symbol"])
            elif u.get("kind") == "call" and self.roles.get(u.get("from_file") or u["anchor"]["file"]) != "test":
                fqn = str(u.get("fqn", ""))
                if owner is None or fqn.partition("#")[0] == owner:
                    self.owners.setdefault(fqn.partition("#")[0], {}).setdefault(fqn, {}).setdefault(
                        cite(u["anchor"]), None)
        return bindings

    def bindings(self) -> Dict[str, List[str]]:
        if self._bindings is None:
            self._bindings = self._add(self.store.xref_uses_in([p for p, (_, b) in self.files.items() if b]), False)
        return self._bindings

    def owner_calls(self, owner: str) -> Dict[str, Dict[str, None]]:
        """`fqn -> {call site: None}` of the non-test calls on `owner` or its members, in first-call order."""
        if self.files is not None and owner not in self.owners:
            key = json.dumps(owner)[1:-1].encode()
            self._add(self.store.xref_uses_in([p for p, (o, _) in self.files.items() if o is None or key in o]), owner)
            self.owners.setdefault(owner, {})
        return self.owners.get(owner, {})

    def queries(self) -> List[Tuple[str, str]]:
        if self._queries is None:
            texts = self.store.code_texts()
            defined = self.store.defines_in([p for p, t in texts.items() if "Query(" in t])
            fqns = sorted({str(r.get("fqn")) for rows in defined.values() for r in rows})
            prefetch_symbols(self.store, fqns, owners=False)
            self._queries = _query_bodies(((f, symbols_of(self.store).get(f) or {}) for f in fqns), texts)
        return self._queries

    def may_mention(self, names: Sequence[str]) -> bool:
        """False only when no query body can match `_repository_access`'s `mentions` for `names`: it matches
        a name only as a whole word, so ASCII words absent from every (ASCII) body's words cannot match."""
        if self._words is None:
            bodies = [b for _, b in self.queries()]
            self._words = all(map(str.isascii, bodies)) and set(_WORD.findall("\n".join(bodies).lower()))
        return (self._words is False or not all(map(_WORD.fullmatch, names))
                or any(n.lower() in self._words for n in names))


_WORD = re.compile(r"[A-Za-z0-9_]+")


def _query_bodies(symbols, texts: Dict[str, str]) -> List[Tuple[str, str]]:
    """`(fqn, body)` of each non-test method site of `symbols` (`(fqn, entry)` pairs) building a query."""
    queries: List[Tuple[str, str]] = []
    for fqn, sym in symbols:
        if sym.get("kind") != "method":
            continue
        for site in sym.get("sites", []):
            text = texts.get(site.get("file")) or ""
            if site.get("role") == "test" or not site.get("end_line") or "Query(" not in text:
                continue
            body = "\n".join(text.splitlines()[site["anchor"]["line"] - 1: site["end_line"]])
            if _QUERY_CALL.search(body):
                queries.append((fqn, body))
    return queries


def _calls_into(store: Store, methods: Dict[str, str], roles: Dict[str, str]) -> Dict[str, Dict[str, None]]:
    """`method fqn -> {call site: None}` for every non-test call on one of `methods`."""
    index = _access_index(store, roles)
    return {m: c for m in methods for c in [index.owner_calls(m.partition("#")[0]).get(m)] if c}


def _repository_access(store: Store, table: str, persist: Sequence[Dict], roles: Dict[str, str],
                       budget: Budget, related: bool = False) -> Tuple[List[Dict], List[Dict]]:
    """Where a JPA table is really written and read, as `(writes, reads)` groups of call sites.

    The entity's `@Table` line is the mapping, not an access. A Spring Data repository bound to the entity
    (`extends JpaRepository<Entity, ..>`, an xref `binding`) is used through its methods: `save`/`delete`..
    write, `find`/`get`/`count`.. read, by Spring's own naming. A custom method (an `..Ext`/`..Impl` class,
    any non-test method that builds an EntityManager query) is credited to the tables its query text
    names -- JPQL `from Entity`, Criteria `Entity.class`, native SQL `from <table>` -- never to a class's
    main entity by guess (one such class can read several tables). Its callers are the sites."""
    index = _access_index(store, roles)
    entities = {e["source"] for e in persist}
    simple = {e.rsplit(".", 1)[-1] for e in entities}
    repos = {r: e for e in entities for r in index.bindings().get(e, [])}
    methods: Dict[str, Tuple[str, str]] = {}  # fqn -> (via, "write"|"read")
    for repo in repos:
        for fqn in (f for f in index.owner_calls(repo) if "#" in f):
            method = fqn.partition("#")[2]
            if method.startswith(_REPO_WRITE_PREFIXES):
                methods[fqn] = (repo, "write")
            elif method.startswith(_REPO_READ_PREFIXES):
                methods[fqn] = (repo, "read")
    names = "|".join(re.escape(n) for n in sorted(simple))
    if names and index.may_mention([*simple, table]):
        mentions = re.compile(r"\bfrom\s+(?:%s|%s)\b|\b(?:%s)\.class\b" % (names, re.escape(table), names), re.I)
        for fqn, body in index.queries():
            if fqn not in methods and mentions.search(body):
                methods[fqn] = (fqn.split("#", 1)[0], "write" if _WRITE_CALL.search(body) else "read")
    groups: Dict[Tuple[str, str], Dict[str, None]] = {}
    for fqn, cited in _calls_into(store, methods, roles).items():
        via, how = methods[fqn]
        groups.setdefault((how, via), {}).update(cited)
    out = {"write": [], "read": []}
    for (how, via) in sorted(groups):
        cited = list(groups[(how, via)])
        out[how].append({"through": via, "entity": repos.get(via), "count": len(cited),
                         "sites": budget.take(cited[:SITES_PER_GROUP]), "sites_all": cited})
    return out["write"], out["read"]


def _public(groups: List[Dict]) -> List[Dict]:
    return [{k: v for k, v in g.items() if k != "sites_all"} for g in groups]


def q_table(store: Store, name: Optional[str] = None,
            budget: Optional[Budget] = None,
            exclude_role: Optional[Sequence[str]] = None, exact: bool = False, regex: bool = False) -> Dict:
    """Who owns, writes and reads each table.

    "What breaks if I change this table" reduces to the union of the three
    lists below, and every entry carries the line that put it there.

    `RESEARCH_GRAPHIFY.md §10` calls this and `q_config` the worst of the silent
    truncations, and it is right: "who writes this table" is exactly the
    question where a partial list reads as a complete one and a wrong
    blast-radius conclusion follows directly from it.
    """
    budget = budget or Budget()
    mode = "regex" if regex else "exact" if exact else "substring"
    same = make_matcher(name or "", "regex" if regex else "exact" if exact else "substring")
    roles = _role_index(store)
    buckets: Dict[str, Dict[str, List[Dict]]] = {}
    by_entity: Dict[str, Tuple[str, List[Dict]]] = {}  # every mapped entity -> (its table, its persist edges)
    for edge in edges_where(store, _TABLE_NEEDLES):
        if not edge["target"].startswith("table:"):
            continue
        table = edge["target"][len("table:") :]
        if edge["channel"] == "persist":
            by_entity.setdefault(edge["source"], (table, []))[1].append(edge)
        if name and not same(table):
            continue
        if exclude_role and roles.get(edge["anchor"].get("file")) in exclude_role:
            continue
        slot = buckets.setdefault(table, {"schema_own": [], "persist": [], "read": []})
        if edge["channel"] in slot:
            slot[edge["channel"]].append(edge)

    entity_at = _entity_index(store)
    relations: Optional[List[Dict]] = None
    out = []
    for table in budget.take_items(sorted(buckets), "table"):
        slot = buckets[table]
        evidence = _dedupe_cites(slot["persist"] + slot["read"])
        writers = _site_groups(store, slot["persist"])
        readers = _site_groups(store, slot["read"])
        access = _repository_access(store, table, slot["persist"], roles, budget)
        if relations is None:  # parsed once per query, only when some table is answered
            relations = _relations(store, {e: es[0]["anchor"]["file"] for e, (_, es) in by_entity.items()})
        related = _related_access(store, table, [e["source"] for e in slot["persist"]], by_entity, relations,
                                  roles, budget)
        access = (_public(access[0]) + related[0], _public(access[1]) + related[1])
        out.append(
            {
                "table": table,
                # one citation the budget never cuts: a listed table always says where it is
                "at": evidence[0] if evidence else (cite(slot["schema_own"][0]["anchor"]) if slot["schema_own"] else None),
                "schema_owned_by": sorted({e["module"] for e in slot["schema_own"]}),
                "migration_count": len(slot["schema_own"]),
                "migrations": [cite(e["anchor"]) for e in budget.take(slot["schema_own"])],
                "written_by": sorted({e["source"] for e in slot["persist"]}),
                "read_by": sorted({e["source"] for e in slot["read"]}),
                "writers": _budget_groups(writers, budget),
                "readers": _budget_groups(readers, budget),
                "entity_users": _entity_users(store, slot["persist"] + slot["read"], entity_at, roles, budget),
                "repository_writes": access[0],
                "repository_reads": access[1],
                "evidence_count": len(evidence),
                "evidence": budget.take(evidence),
            }
        )
    return _finish(
        {"query": "table", "name": name, "match": mode if name else "all", "count": len(buckets), "tables": out},
        store, budget,
    )


#: Citations each key is guaranteed before any key gets more (H1).
CITES_PER_KEY = 3


_PLACEHOLDER_RE = re.compile(r"\$\{([^}:]+)(?::([^}]*))?\}")


def _value_default(store: Store, read: Dict) -> Optional[str]:
    """The `${key:default}` default of the `@Value` that made this read, from the annotation's
    parsed `args` (the edge itself is unchanged). None when there is no default."""
    cache = getattr(store, "_cache", None)
    if not isinstance(cache, dict):   # a duck-typed store: built per call
        cache = {}
    by_file = cache.get("_value_anns")
    if by_file is None:
        by_file = cache["_value_anns"] = {}
        for row in extract_where(store, ("config:",))["defines"]:
            by_file.setdefault(row["file"], []).append(row)
    if read["file"] not in by_file:   # a wrapped read's file need not mention a config key
        by_file[read["file"]] = list(file_rows(store, read["file"], "defines"))
    key = ("_value_at", read["file"])
    if key not in cache:
        index: Dict = {}
        for row in by_file[read["file"]]:
            groups = [row.get("annotations") or []]
            groups += [p.get("annotations") or [] for p in row.get("params") or []]
            for anns in groups:
                for ann in anns:
                    if ann.get("name") == "Value" and isinstance(ann.get("args", {}).get("value"), str):
                        index.setdefault(ann.get("line"), []).append(ann["args"]["value"])
        cache[key] = index
    for text in cache[key].get(read["anchor"].get("line"), ()):
        for m in _PLACEHOLDER_RE.finditer(text):
            if m.group(2) is not None and m.group(1) == read["key"]:
                return m.group(2)
    return None


def q_config(store: Store, key: Optional[str] = None,
             budget: Optional[Budget] = None,
             exclude_role: Optional[Sequence[str]] = None, exact: bool = False, regex: bool = False) -> Dict:
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
    mode = "regex" if regex else "exact" if exact else "substring"
    same = make_matcher(key or "", "regex" if regex else "exact" if exact else "substring")
    roles = _role_index(store) if exclude_role else {}
    rows: Dict[str, Dict] = {}

    def slot_of(name: str) -> Dict:
        return rows.setdefault(name, {"key": name, "declared": [], "read": [], "values": []})

    for row in extract_where(store, ("config:",))["defines"]:
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
    reads = config_reads({"io_edges": edges_where(store, ("config:",))}, xref_get(store, "constants", {}),
                         xref_get(store, "config_wrapped", ()))
    prefetch_symbols(store, [r["by"] for r in reads])
    for read in reads:
        if key and not same(read["key"]):
            continue
        if exclude_role and roles.get(read["file"]) in exclude_role:
            continue
        site = {"by": read["by"], "at": cite(read["anchor"]), **annotations_of(store, read["by"])}
        default = _value_default(store, read)
        if default is not None:
            site["default"] = default
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
