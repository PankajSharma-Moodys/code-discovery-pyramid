"""Whole-repo censuses: `stats` and `coverage`."""

from __future__ import annotations

from typing import Dict

from .common import _finish, _tally
from .store import Store


def q_stats(store: Store) -> Dict:
    """Never budgeted (`UNBUDGETED`). Takes no `budget` argument at all, so a
    future edit cannot quietly start honouring one."""
    inv = store.inventory
    state = store.state
    # The build's own name for itself, when it differs from the directory. On
    # the validation target `settings.gradle` says `rootProject.name = 'spm'`
    # while every directory is `sql-pool-*`, and that mismatch is the first
    # thing a newcomer trips over -- so it belongs in the first thing they run.
    build_name = None
    for row in store.extraction["defines"]:
        # Only the root `settings.gradle`: a fixture or sub-build's own
        # settings file names a different build.
        if row["fqn"] == "build:rootProject.name" and row["file"] == "settings.gradle":
            build_name = row.get("value")
            break
    return _finish({
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
        "declared_ambiguous": store.graph.get("declared_ambiguous", []),
    }, store, None)


def q_coverage(store: Store) -> Dict:
    """Never budgeted (`UNBUDGETED`). See `q_stats`."""
    state = store.state
    coverage = state.get("coverage", {})
    return _finish({
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
    }, store, None)
