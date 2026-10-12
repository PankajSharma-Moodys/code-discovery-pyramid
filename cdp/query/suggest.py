"""Unknown terms: say so, and say what was probably meant (H8).

A lookup that matches nothing used to exit 0 with an empty list, which reads as
"there is no such thing". `annotate` adds `not_found: {term, did_you_mean}` so the
caller (CLI exit code 1, MCP result field) can retry with a real name.
"""

from __future__ import annotations

import difflib
import re
from typing import Dict, List, Optional

from .store import Store
from ..rules import all_edges

_SPLIT = re.compile(r"[.#:/_\-\s]+|(?<=[a-z0-9])(?=[A-Z])")


def _candidates(store: Store, kind: str) -> List[str]:
    if kind in ("symbol", "trace", "search"):
        names = {k.rsplit(".", 1)[-1] for k in store.xref["symbols"]} | set(store.xref["symbols"])
        if kind == "trace":
            names |= {r["route"] for r in store.xref["routes"] + store.xref["unresolved_routes"]}
        return sorted(names)
    if kind == "file":
        return sorted(f["path"] for f in store.inventory["files"])
    if kind == "module":
        return sorted(m["name"] for m in store.inventory["modules"])
    if kind == "routes":
        return sorted({r["route"] for r in store.xref["routes"] + store.xref["unresolved_routes"]})
    if kind == "table":
        return sorted({e["target"][6:] for e in all_edges(store.extraction) if e["target"].startswith("table:")})
    if kind == "config":
        return sorted({r["fqn"][7:] for r in store.extraction["defines"]
                       if r["kind"] == "config_key" and r["fqn"].startswith("config:")})
    return []


def did_you_mean(store: Store, kind: str, term: str, limit: int = 5) -> List[str]:
    pool = _candidates(store, kind)
    lower = {c.lower(): c for c in pool}
    hits = [lower[m] for m in difflib.get_close_matches(term.lower(), list(lower), n=limit, cutoff=0.6)]
    # Shared word pieces (`OrderServ` ~ `OrderService`, `order` ~ `OrderResource`) also count.
    pieces = {p.lower() for p in _SPLIT.split(term) if len(p) > 2}
    if pieces:
        for c in pool:
            if len(hits) >= limit:
                break
            if c not in hits and pieces & {p.lower() for p in _SPLIT.split(c) if p}:
                hits.append(c)
    return hits[:limit]


def _empty(kind: str, term: Optional[str], result: Dict) -> bool:
    if not term:
        return False
    if kind in ("symbol", "file", "module"):
        return not result.get("found")
    if kind == "trace":
        return result.get("found") is False
    if kind == "routes":
        return result.get("count") == 0
    if kind in ("table", "config"):
        return result.get("count") == 0
    if kind == "search":
        return not any((result.get("counts") or {}).values())
    return False


def annotate(store: Store, kind: str, term: Optional[str], result: Dict) -> Dict:
    if _empty(kind, term, result):
        result["not_found"] = {"term": term, "did_you_mean": did_you_mean(store, kind, term or "")}
    return result


def describe(result: Dict) -> Optional[str]:
    nf = result.get("not_found")
    if not nf:
        return None
    near = nf["did_you_mean"]
    return "not found: %r%s" % (nf["term"], "; did you mean: " + ", ".join(near) if near
                                else "; no close names (try `query search`, and check `query coverage`)")
