"""Phase 3c — topological wave scheduling (§5.3, §3.1).

Two axes, deliberately kept apart. The directory tree answers "what is a
coherent unit of ownership" and produced the partition. The dependency DAG
answers "what must be understood before what" and produces the order here.
Conflating them is a mistake RESEARCH.md calls out by name.

The payoff on the validation target is concrete: `sql-pool-common` is imported
by all eight other modules, 247 times for `common.model` alone. Scheduling it
first means one agent establishes what `DServer` is, and the other eight inherit
it as verified fact instead of reconstructing it eight times into eight subtly
different descriptions the merge operator would then have to reconcile.

The concurrency cap is a **wave size, not a ceiling** (§3.1). A level with 47
scopes runs as three waves. Nothing about repository size is bounded by it.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Set, Tuple

DEFAULT_MAX_CONCURRENT = 12


def build_schedule(
    partition: Dict,
    graph: Dict,
    max_concurrent: int = DEFAULT_MAX_CONCURRENT,
) -> Dict:
    level_of: Dict[str, int] = {}
    for i, layer in enumerate(graph["levels"]):
        for module in layer:
            level_of[module] = i

    # Modules a given module depends on, for the inherited-sigma filter (§3.3).
    deps: Dict[str, List[str]] = {}
    for edge in graph["observed"]:
        deps.setdefault(edge["from"], []).append(edge["to"])

    scopes = sorted(
        partition["scopes"],
        key=lambda s: (level_of.get(s["module"], 0), s["node"]),
    )

    waves: List[Dict] = []
    current_level: Optional[int] = None
    bucket: List[Dict] = []

    def flush() -> None:
        if not bucket:
            return
        for start in range(0, len(bucket), max_concurrent):
            chunk = bucket[start : start + max_concurrent]
            waves.append(
                {
                    "wave": len(waves),
                    "level": current_level,
                    "nodes": [s["node"] for s in chunk],
                    "file_count": sum(s["file_count"] for s in chunk),
                    "loc": sum(s["loc"] for s in chunk),
                }
            )
        bucket.clear()

    for scope in scopes:
        level = level_of.get(scope["module"], 0)
        if current_level is None:
            current_level = level
        if level != current_level:
            flush()
            current_level = level
        bucket.append(scope)
    flush()

    assignment = {}
    for wave in waves:
        for node in wave["nodes"]:
            assignment[node] = wave["wave"]

    return {
        "max_concurrent": max_concurrent,
        "waves": waves,
        "node_wave": dict(sorted(assignment.items())),
        "module_level": dict(sorted(level_of.items())),
        "module_deps": {k: sorted(set(v)) for k, v in sorted(deps.items())},
        "totals": {
            "waves": len(waves),
            "nodes": len(assignment),
            # Deterministic proxy for cost (PLAN.md C2): the exact source volume
            # the run authorises agents to read. Tokens are not measurable under
            # in-session execution, but this term is, and it is the one that
            # actually scales with repository size.
            "source_loc_scheduled": sum(w["loc"] for w in waves),
        },
    }


def summarise(schedule: Dict) -> List[str]:
    lines = [
        "schedule  %d waves, max %d concurrent, %d scheduled loc"
        % (
            schedule["totals"]["waves"],
            schedule["max_concurrent"],
            schedule["totals"]["source_loc_scheduled"],
        )
    ]
    for wave in schedule["waves"]:
        lines.append(
            "  wave %-2d (L%s) %2d nodes %5d loc  %s"
            % (
                wave["wave"],
                wave["level"],
                len(wave["nodes"]),
                wave["loc"],
                ", ".join(n.split("/", 1)[-1] for n in wave["nodes"][:4])
                + (" ..." if len(wave["nodes"]) > 4 else ""),
            )
        )
    return lines
