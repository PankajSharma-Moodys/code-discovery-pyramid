"""Phase 3 -- `cdp diff` (3.2, M3.5).

Typed structural deltas between two snapshots' already-computed views
(`graph`/`xref`/`state`), not a text diff. One build, three consumers per the
plan: `refresh`, a reviewer agent, a CI/CD agent. `FileStore` holds exactly one
snapshot at a time (`store/__init__.py`'s snapshot methods no-op on it), so the
two sides here are two independently-scanned state directories -- the same
shape the M3.1-M3.4 real-target exercises already used (two scratch state
dirs, or one worktree scanned twice).
"""

from __future__ import annotations

from typing import Any, Dict, List, Set, Tuple


def _edge_pairs(edges: List[Dict]) -> Set[Tuple[str, str]]:
    return {(e["from"], e["to"]) for e in edges}


def _route_keys(xref: Dict) -> Set[Tuple[str, str]]:
    return {(r["verb"], r["route"]) for r in xref.get("routes", []) + xref.get("unresolved_routes", [])}


def _claim_location(claim: Dict) -> Tuple[Any, Any]:
    evidence = claim.get("evidence") or [{}]
    return evidence[0].get("file"), evidence[0].get("line")


def diff_snapshots(
    old_graph: Dict, old_xref: Dict, old_state: Dict,
    new_graph: Dict, new_xref: Dict, new_state: Dict,
) -> Dict:
    modules_old, modules_new = set(old_graph["modules"]), set(new_graph["modules"])

    declared_old, declared_new = _edge_pairs(old_graph["declared"]), _edge_pairs(new_graph["declared"])
    observed_old, observed_new = _edge_pairs(old_graph["observed"]), _edge_pairs(new_graph["observed"])
    undeclared_old = _edge_pairs(old_graph["divergence"]["observed_not_declared"])
    undeclared_new = _edge_pairs(new_graph["divergence"]["observed_not_declared"])

    routes_old, routes_new = _route_keys(old_xref), _route_keys(new_xref)

    claims_old = {c["id"]: c for c in old_state.get("claims", [])}
    claims_new = {c["id"]: c for c in new_state.get("claims", [])}
    common_ids = set(claims_old) & set(claims_new)
    anchor_moved = [
        {"id": cid, "old": _claim_location(claims_old[cid]), "new": _claim_location(claims_new[cid])}
        for cid in sorted(common_ids)
        if _claim_location(claims_old[cid]) != _claim_location(claims_new[cid])
    ]

    cov_old = old_state.get("coverage", {}).get("fraction")
    cov_new = new_state.get("coverage", {}).get("fraction")
    regressed = cov_old is not None and cov_new is not None and cov_new < cov_old

    findings: List[str] = []
    for a, b in sorted(undeclared_new - undeclared_old):
        findings.append("%s now imports %s, and that edge is not declared in any manifest" % (a, b))
    for verb, route in sorted(routes_new - routes_old):
        findings.append("route added: %s %s" % (verb, route))
    for verb, route in sorted(routes_old - routes_new):
        findings.append("route removed: %s %s" % (verb, route))
    if regressed:
        findings.append("coverage regressed: %.1f%% -> %.1f%%" % (100 * cov_old, 100 * cov_new))

    return {
        "modules": {"added": sorted(modules_new - modules_old), "removed": sorted(modules_old - modules_new)},
        "declared_edges": {
            "added": sorted(declared_new - declared_old), "removed": sorted(declared_old - declared_new),
        },
        "observed_edges": {
            "added": sorted(observed_new - observed_old), "removed": sorted(observed_old - observed_new),
        },
        "undeclared_dependencies": {
            "appeared": sorted(undeclared_new - undeclared_old), "resolved": sorted(undeclared_old - undeclared_new),
        },
        "routes": {"added": sorted(routes_new - routes_old), "removed": sorted(routes_old - routes_new)},
        "claims": {
            "added": sorted(set(claims_new) - set(claims_old)),
            "removed": sorted(set(claims_old) - set(claims_new)),
            "anchor_moved": anchor_moved,
        },
        "coverage": {"old": cov_old, "new": cov_new, "regressed": regressed},
        "findings": findings,
    }


def summarise(diff: Dict) -> List[str]:
    lines = [
        "diff      %d module(s) added, %d removed"
        % (len(diff["modules"]["added"]), len(diff["modules"]["removed"])),
        "          %d declared edge(s) +/-%d/%d, %d observed edge(s) +/-%d/%d"
        % (len(diff["declared_edges"]["added"]) + len(diff["declared_edges"]["removed"]),
           len(diff["declared_edges"]["added"]), len(diff["declared_edges"]["removed"]),
           len(diff["observed_edges"]["added"]) + len(diff["observed_edges"]["removed"]),
           len(diff["observed_edges"]["added"]), len(diff["observed_edges"]["removed"])),
        "          %d route(s) added, %d removed"
        % (len(diff["routes"]["added"]), len(diff["routes"]["removed"])),
        "          %d claim(s) added, %d removed, %d anchor(s) moved"
        % (len(diff["claims"]["added"]), len(diff["claims"]["removed"]), len(diff["claims"]["anchor_moved"])),
    ]
    for finding in diff["findings"]:
        lines.append("finding   %s" % finding)
    return lines
