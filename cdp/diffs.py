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

from typing import Any, Dict, List, Optional, Set, Tuple
from pathlib import Path
from . import query as query_mod
from .store import FileStore, WorkspaceStore
from .util import CdpError


def _edge_pairs(edges: List[Dict]) -> Set[Tuple[str, str]]:
    return {(e["from"], e["to"]) for e in edges}


def _route_keys(xref: Dict) -> Set[Tuple[str, str]]:
    return {(r["verb"], r["route"]) for r in xref.get("routes", []) + xref.get("unresolved_routes", [])}


def _claim_location(claim: Dict) -> Tuple[Any, Any]:
    evidence = claim.get("evidence") or [{}]
    return evidence[0].get("file"), evidence[0].get("line")


def _file_changes(old_files: Dict[str, Dict], new_files: Dict[str, Dict],
                  old_xref: Dict, new_xref: Dict) -> Dict:
    """Files added, removed and changed between two snapshots.

    The index keeps no content hash, so `changed` is a file whose size or line
    count differs, or whose definitions' extents differ -- an edit that keeps
    the size and moves no definition is not seen (stated in the summary)."""
    def shape(xref: Dict) -> Dict[str, Set[Tuple]]:
        out: Dict[str, Set[Tuple]] = {}
        for fqn, e in xref.get("symbols", {}).items():
            for s in e.get("sites", []):
                end = s.get("end_line")
                out.setdefault(s["file"], set()).add(
                    (fqn, (end - s["anchor"]["line"]) if end else None, e.get("value")))
        return out

    old_shape, new_shape = shape(old_xref), shape(new_xref)
    both = set(old_files) & set(new_files)
    changed = sorted(
        p for p in both
        if (old_files[p].get("bytes"), old_files[p].get("loc")) != (new_files[p].get("bytes"), new_files[p].get("loc"))
        or old_shape.get(p, set()) != new_shape.get(p, set())
    )
    return {"added": sorted(set(new_files) - set(old_files)),
            "removed": sorted(set(old_files) - set(new_files)), "changed": changed}


def _symbol_changes(old_xref: Dict, new_xref: Dict) -> Dict:
    """Symbols added and removed, and ones whose extent length, value or visibility changed
    (a symbol that only moved down a file is not a change)."""
    old, new = old_xref.get("symbols", {}), new_xref.get("symbols", {})

    def sig(e: Dict) -> Tuple:
        return (e.get("visibility"), e.get("value"),
                tuple(sorted((s["file"], (s["end_line"] - s["anchor"]["line"]) if s.get("end_line") else None)
                             for s in e.get("sites", []))))

    return {"added": sorted(set(new) - set(old)), "removed": sorted(set(old) - set(new)),
            "changed": sorted(k for k in set(old) & set(new) if sig(old[k]) != sig(new[k]))}


def diff_snapshots(
    old_graph: Dict, old_xref: Dict, old_state: Dict,
    new_graph: Dict, new_xref: Dict, new_state: Dict,
    old_files: Optional[Dict[str, Dict]] = None, new_files: Optional[Dict[str, Dict]] = None,
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

    files = _file_changes(old_files, new_files, old_xref, new_xref) \
        if old_files is not None and new_files is not None else None
    symbols = _symbol_changes(old_xref, new_xref)
    return {
        "files": files,
        "symbols": symbols,
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


_SHOW = 10


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
    files, syms = diff.get("files"), diff["symbols"]
    if files is not None:
        lines.append("          %d file(s) changed, %d added, %d removed (size/extent based: an "
                     "edit that keeps both is not seen)"
                     % (len(files["changed"]), len(files["added"]), len(files["removed"])))
        for tag, key in (("~", "changed"), ("+", "added"), ("-", "removed")):
            lines += ["            %s %s" % (tag, f) for f in files[key][:_SHOW]]
            if len(files[key]) > _SHOW:
                lines.append("            ... %d more %s file(s) (--json lists all)" % (len(files[key]) - _SHOW, key))
    lines.append("          %d symbol(s) added, %d removed, %d changed (extent length, value or visibility)"
                 % (len(syms["added"]), len(syms["removed"]), len(syms["changed"])))
    for tag, key in (("+", "added"), ("-", "removed"), ("~", "changed")):
        lines += ["            %s %s" % (tag, f) for f in syms[key][:_SHOW]]
        if len(syms[key]) > _SHOW:
            lines.append("            ... %d more %s symbol(s) (--json lists all)" % (len(syms[key]) - _SHOW, key))
    for finding in diff["findings"]:
        lines.append("finding   %s" % finding)
    return lines


def open_diff_side(state_dir: Path) -> "query_mod.Store":
    """Directory-pair mode: detect which directory-shaped backend is
    actually present instead of assuming `SqliteStore` -- `FileStore`'s
    loose-JSON layout is just as diffable, it was simply never tried.
    Postgres has no per-snapshot directory at all, so it can't be reached
    this way; that's what `--repo`/`--old-sha`/`--new-sha` is for."""
    state_dir = state_dir.expanduser().resolve()
    if (state_dir / "index.db").is_file():
        return query_mod.Store(state_dir)
    if (state_dir / "graph.json").is_file():
        return query_mod.Store(FileStore(state_dir))
    raise CdpError(
        "no CDP state at %s -- run `scan` first. If this is postgres-backed "
        "state, `cdp diff <dir> <dir>` can't read it (postgres has no "
        "per-snapshot directory) -- use `cdp diff --repo ... --old-sha ... "
        "--new-sha ...` instead." % state_dir
    )


def current_snapshot_sha(backend: WorkspaceStore, repo_id: str, repo: Path) -> str:
    """The commit of the snapshot that answers for `repo` right now (the shared
    `snapshot.choose_snapshot` rule), never another repo's or branch's."""
    from .snapshot import choose_snapshot, stored_excludes

    snapshots = backend.list_snapshots()
    choice = choose_snapshot(repo, repo_id, snapshots, stored=stored_excludes(backend, repo_id, snapshots))
    if choice.row is None:
        raise CdpError("no scanned snapshot for %s (%s) -- run `cdp scan` first" % (repo_id, choice.reason))
    return choice.row["commit_sha"]
