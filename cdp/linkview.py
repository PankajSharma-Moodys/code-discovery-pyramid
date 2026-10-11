"""Cross-repo links as the compact, cited answer an MCP client wants (`cdp_link`).

One call shape for `scan` / `scan_save` / `query`: match every scanned repo in the machine
store (`link.scan_links`, the code `cdp link scan` runs), optionally persist it, optionally
narrow it to one service, and render each link as `caller repo:file:line -> callee
repo:file:line` with the verb + path and `exact`/`heuristic`.

`query` always matches the current index, so it needs no earlier save and is never stale;
verdicts an AI link run saved (`link run`) are overlaid by link id.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from . import link as link_mod
from . import linkroute
from .linkid import link_id, reanchor
from .util import CdpError

ACTIONS = ("scan", "scan_save", "query")
DEFAULT_LIMIT = 100


def open_machine_store(home, writable: bool):
    """The machine store (`CDP_HOME`) as a link-capable backend: sqlite only, like the CLI."""
    from .session import resolve_backend
    from .store.sqlite_backend import SqliteStore

    kind, _pg = resolve_backend(home)
    db = home / "index.db"
    if kind != "sqlite":
        raise CdpError("%s backend cannot back cross-repo links -- needs the sqlite backend" % kind)
    if not writable and not db.is_file():
        raise CdpError("no scanned repos in %s -- run `cdp_scan` on each repo first" % home)
    return SqliteStore(db, readonly=not writable)


def _call(side: Dict, names) -> str:
    return "%s:%s:%d" % (link_mod.repo_label(side["repo"], names), side["anchor"]["file"], side["anchor"]["line"])


def _what(link: Dict) -> str:
    """`POST /v1/charges` for HTTP; the raw target (topic, table) otherwise."""
    channel = "http_in" if link["protocol"] == "http_out" else (
        "event_subscribe" if link["protocol"] == "event_publish" else "schema_own")
    target = link["callee"]["target"]
    path = linkroute.path_of(channel, target)
    verb = linkroute.verb_of(channel, target)
    return ("%s %s" % (verb, path)) if verb else path


def compact_link(link: Dict, names) -> Dict:
    out = {"call": _what(link), "caller": _call(link["caller"], names), "callee": _call(link["callee"], names),
           "match": link["match_kind"], "protocol": link["protocol"]}
    if link.get("self_link"):
        out["self"] = True
    if link.get("resolution"):
        out["verdict"] = link["resolution"]["verdict"]
    return out


def run(home, action: str, service: Optional[str] = None, limit: int = DEFAULT_LIMIT) -> Dict:
    """`cdp_link`'s body (the caller holds the right lock for `action`)."""
    if action not in ACTIONS:
        raise CdpError("unknown action %r -- one of %s" % (action, ", ".join(ACTIONS)))
    if action == "query" and not service:
        raise CdpError("action=query needs `service` (a repo's directory name, path or identity)")
    if action != "query" and service:
        raise CdpError("`service` only applies to action=query")
    persist = action == "scan_save"
    store = open_machine_store(home, writable=persist)
    try:
        snapshots = link_mod.snapshots_from_store(store)
        if not snapshots:
            raise CdpError("no scanned repos in %s -- run `cdp_scan` on each repo first" % home)
        names = link_mod.repo_names(store)
        report = link_mod.scan_links(snapshots)
        if persist:
            store.write_link_edges(report)
        saved = {link_id(e["data"]): e["data"]["resolution"] for e in store.read_link_edges()
                 if e["kind"] == "link" and e["data"].get("resolution")}
    finally:
        store.close()
    for link in report["links"]:
        res = saved.get(link_id(link))
        if res:
            link["resolution"] = reanchor(link, res)
    links, unmatched = report["links"], report["unmatched"]
    out: Dict = {"action": action, "repos": sorted(link_mod.repo_label(s["repo"], names) for s in snapshots)}
    if action == "query":
        edges = [{"kind": "link", "data": l} for l in links] + [{"kind": "unmatched", "data": u} for u in unmatched]
        known = [s["repo"] for s in snapshots]
        link_mod.require_known_service(edges, service, known, names)
        result = link_mod.query_service(edges, service, known, names)
        links, unmatched = result["links"], result["unmatched"]
        out["service"] = link_mod.repo_label(result["service"], names)
    out["totals"] = {"links": len(links), "exact": sum(1 for l in links if l["match_kind"] == "exact"),
                     "heuristic": sum(1 for l in links if l["match_kind"] == "heuristic"),
                     "unmatched": len(unmatched)}
    out["links"] = [compact_link(l, names) for l in links[:limit]]
    out["unmatched"] = [{"call": "%s %s" % (u["protocol"], u["outbound"]["target"]),
                         "caller": _call(u["outbound"], names)} for u in unmatched[:limit]]
    if len(links) > limit or len(unmatched) > limit:
        out["elided"] = {"links": max(0, len(links) - limit), "unmatched": max(0, len(unmatched) - limit),
                         "hint": "pass `service` (action=query) to narrow"}
    if persist:
        out["saved"] = "links persisted in the machine store; `cdp link query|prompts|run` can use them"
    return out
