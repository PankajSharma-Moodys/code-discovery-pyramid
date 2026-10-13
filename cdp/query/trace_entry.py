"""What `trace` was asked about: a route (every verb on its path), a dataflow source, or a symbol.

A route path shared by several verbs resolves to *all* of them, one handler each; `VERB /path`
narrows to one. A class name resolves to the class and its public members, each of which `trace`
walks as an entry point of its own (see `trace.CLASS_TRACE_FILES`).
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional

from .common import _matches, cite, make_matcher
from .store import Store

CLASS_KINDS = ("class", "interface", "enum", "record", "struct")
VERB_PREFIX = re.compile(r"^(GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS)\s+(\S.*)$", re.I)
#: Classes that share a simple name (`Internal.TenantController`, `External.TenantController`)
#: are all walked, up to this many.
MAX_CLASSES = 4


def resolve_entry(store: Store, entry: str, adjacency: Dict[str, List[Dict]],
                  match: str = "substring") -> Optional[Dict]:
    """Route path (+ optional verb), exact source, exact class name, other source, symbol.

    `match=exact` keeps only whole-name tiers; `match=regex` searches the pattern in route paths, source
    nodes/triggers, class names and symbol names. A regex that matches several entries traces the first
    and lists the rest under `also_matched`, so a second endpoint is never silently dropped."""
    rx = make_matcher(entry, "regex") if match == "regex" else None
    if match == "substring":
        ladder = (lambda: _route(store, entry), lambda: _source(store, entry, exact=True),
                  lambda: _class(store, entry, adjacency), lambda: _source(store, entry, exact=False))
    else:
        ladder = (lambda: _route(store, entry, match, rx), lambda: _source(store, entry, True, rx),
                  lambda: _class(store, entry, adjacency, rx))
    for step in ladder:
        found = step()
        if found:
            return found
    return _symbol(store, entry, match, rx)


def _route(store: Store, entry: str, match: str = "substring", rx=None) -> Optional[Dict]:
    m = VERB_PREFIX.match(entry.strip()) if match != "regex" else None
    verb, path = (m.group(1).upper(), m.group(2).strip()) if m else (None, entry)
    routes = [r for r in store.xref["routes"] + store.xref["unresolved_routes"]
              if (verb is None or r["verb"].upper() == verb)]
    if rx:
        hits = sorted((r for r in routes if rx(r["route"]) or rx("%s %s" % (r["verb"], r["route"]))),
                      key=lambda r: (r["route"], r["verb"], r["handler"]))
    else:
        hits = [r for r in routes if r["route"] == path] \
            or [r for r in routes if r["route"].lower() == path.lower()] \
            or ([] if match == "exact" else [r for r in routes if _matches(r["route"], path)])
    if not hits:
        return None
    # Every verb that shares the first matching path; a path that merely contains the term
    # does not pull in the other paths it is a prefix of.
    group = [r for r in hits if r["route"] == hits[0]["route"]]
    group.sort(key=lambda r: (r["verb"], r["handler"]))
    files = store.extraction["files"]
    first = group[0]
    node = files.get(first["file"], {}).get("primary") or first["handler"].split("#", 1)[0]
    verbs = sorted({r["verb"] for r in group})
    others = sorted({"%s %s" % (r["verb"], r["route"]) for r in hits if r["route"] != first["route"]}) if rx else []
    return {
        **({"also_matched": others} if others else {}),
        "kind": "route",
        "node": node,
        "handler": first["handler"],
        "label": "%s %s" % (",".join(verbs), first["route"]),
        "channel": "http_in",
        "module": first["module"],
        "at": cite(first["evidence"][0]) if first["evidence"] else None,
        "handlers": [
            {"verb": r["verb"], "handler": r["handler"], "module": r["module"],
             "node": files.get(r["file"], {}).get("primary") or r["handler"].split("#", 1)[0],
             "at": cite(r["evidence"][0]) if r["evidence"] else None}
            for r in group
        ],
    }


def _source(store: Store, entry: str, exact: bool, rx=None) -> Optional[Dict]:
    for source in store.dataflow.get("sources", []):
        if (rx(source["node"]) or rx(source["trigger"])) if rx else \
                (source["node"] == entry or source["trigger"] == entry) if exact \
                else _matches(source["node"], entry):
            return {
                "kind": "source",
                "node": source["node"],
                "label": source["trigger"],
                "channel": source["channel"],
                "module": source["module"],
                "at": cite(source["anchor"]),
            }
    return None


def _class(store: Store, entry: str, adjacency: Dict[str, List[Dict]], rx=None) -> Optional[Dict]:
    """A class term: every class with that name, and the public members with outgoing edges."""
    symbols = store.xref["symbols"]
    keys = sorted((k for k, v in symbols.items() if v["kind"] in CLASS_KINDS
                   and (rx(k) if rx else (k == entry or k.rsplit(".", 1)[-1] == entry))),
                  key=lambda k: (len(k), k))
    if not keys:
        return None
    # A test double with the same name as the class under study is not the class.
    real = [k for k in keys if any(s.get("role") != "test" for s in symbols[k]["sites"])]
    keys = (real or keys)[:MAX_CLASSES]
    members = []
    for key in keys:
        for mk in sorted(k for k in symbols if k.startswith(key + "#")):
            info = symbols[mk]
            if info["kind"] == "method" and info["visibility"] == "public" and not mk.endswith("#<init>") \
                    and mk in adjacency:
                members.append(mk)
    sites = symbols[keys[0]]["sites"]
    return {
        "kind": "symbol",
        "scope": "class",
        "node": keys[0],
        "label": keys[0] if len(keys) == 1 else "%s (+%d same-named)" % (keys[0], len(keys) - 1),
        "channel": "defines",
        "module": sites[0]["module"] if sites else None,
        "at": cite(sites[0]["anchor"]) if sites else None,
        "classes": keys,
        "members": members,
    }


def _symbol(store: Store, entry: str, match: str = "substring", rx=None) -> Optional[Dict]:
    symbols = store.xref["symbols"]
    keys = [k for k in symbols if (rx(k) if rx else k == entry or k.rsplit(".", 1)[-1] == entry)]
    if not rx and match != "exact":
        keys = keys or [k for k in symbols if _matches(k, entry)]
    if not keys:
        return None
    ordered = sorted(keys, key=lambda k: (len(k), k))
    key = ordered[0]
    sites = symbols[key]["sites"]
    return {
        **({"also_matched": ordered[1:21]} if rx and len(ordered) > 1 else {}),
        "kind": "symbol",
        "node": key,
        "label": key,
        "channel": "defines",
        "module": sites[0]["module"] if sites else None,
        "at": cite(sites[0]["anchor"]) if sites else None,
    }
