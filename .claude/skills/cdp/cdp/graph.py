"""Phase 3a — the dual-source dependency graph (§5.2).

Build the graph twice, from build manifests and from import statements, and
treat the divergence as a deliverable rather than an error to reconcile.

On the validation target the declared arm has ~4 inter-module edges while the
observed arm is a complete 5-level DAG rooted at `sql-pool-common`, which every
other module imports. Manifest-only extraction — what almost any dependency tool
does — would report this repository as nine nearly-unrelated modules. That is
not a small error; it is the exact opposite of the truth.

Divergence is a finding in both directions. Imported-but-not-declared compiles
by transitive luck and breaks on a dependency bump. Declared-but-never-imported
is a stale dependency. Neither is visible if you pick one source.
"""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from .inventory import ROOT_MODULE

SYMBOL_KINDS = frozenset(["class", "interface", "enum", "record", "annotation"])


def build_graph(inventory: Dict, extraction: Dict) -> Dict:
    modules = [m["name"] for m in inventory["modules"]]
    module_set = set(modules)

    symbol_owner, namespace_owner = build_symbol_index(extraction)
    observed, unresolved, third_party = _observed_edges(
        extraction, module_set, symbol_owner, namespace_owner
    )
    declared, declared_ambiguous = _declared_edges(extraction, inventory, module_set)

    observed_pairs = {(e["from"], e["to"]) for e in observed}
    declared_pairs = {(e["from"], e["to"]) for e in declared}

    levels, cycles = _layer(modules, observed_pairs)

    return {
        "modules": modules,
        "declared": declared,
        "declared_ambiguous": declared_ambiguous,
        "observed": observed,
        "divergence": {
            "observed_not_declared": [
                {"from": a, "to": b} for a, b in sorted(observed_pairs - declared_pairs)
            ],
            "declared_not_observed": [
                {"from": a, "to": b} for a, b in sorted(declared_pairs - observed_pairs)
            ],
            "declared_edges": len(declared_pairs),
            "observed_edges": len(observed_pairs),
        },
        "levels": levels,
        "cycles": cycles,
        "external": {
            "third_party_packages": third_party,
            "unresolved_imports": unresolved,
        },
    }


# -------------------------------------------------------------- symbol index


def build_symbol_index(extraction: Dict) -> Tuple[Dict[str, List[str]], Dict[str, List[str]]]:
    """`fqn -> modules` and `namespace -> modules`, both from `defines[]` only.

    Two maps rather than one because an import may name a type (`...domain.DServer`)
    or a package (`...domain.*`), and collapsing them would make a wildcard
    import look unresolvable.
    """
    symbol: Dict[str, Set[str]] = {}
    namespace: Dict[str, Set[str]] = {}
    for row in extraction["defines"]:
        fqn = row["fqn"]
        module = row["module"]
        symbol.setdefault(fqn, set()).add(module)
        if row["kind"] in SYMBOL_KINDS and "." in fqn:
            namespace.setdefault(fqn.rsplit(".", 1)[0], set()).add(module)
        if "/" in fqn:
            namespace.setdefault(fqn.rsplit("/", 1)[0], set()).add(module)
    return (
        {k: sorted(v) for k, v in sorted(symbol.items())},
        {k: sorted(v) for k, v in sorted(namespace.items())},
    )


def owners_of(
    fqn: str, symbol_owner: Dict[str, List[str]], namespace_owner: Dict[str, List[str]]
) -> List[str]:
    """Which modules could satisfy a reference to `fqn`.

    Exact symbol first, then progressively shorter namespace prefixes. Returning
    a list rather than a winner is deliberate: §6.4 forbids the resolver from
    picking when an FQN is declared in more than one place.
    """
    if fqn in symbol_owner:
        return symbol_owner[fqn]
    candidate = fqn[:-2] if fqn.endswith(".*") else fqn
    for _ in range(12):
        if candidate in namespace_owner:
            return namespace_owner[candidate]
        if candidate in symbol_owner:
            return symbol_owner[candidate]
        cut = max(candidate.rfind("."), candidate.rfind("/"))
        if cut <= 0:
            break
        candidate = candidate[:cut]
    return []


# --------------------------------------------------------------------- edges


def _observed_edges(
    extraction: Dict,
    module_set: Set[str],
    symbol_owner: Dict[str, List[str]],
    namespace_owner: Dict[str, List[str]],
) -> Tuple[List[Dict], List[Dict], Dict[str, int]]:
    weights: Dict[Tuple[str, str], int] = {}
    examples: Dict[Tuple[str, str], List[Dict]] = {}
    unresolved: Dict[str, Dict] = {}
    third_party: Dict[str, int] = {}

    for row in extraction["imports"]:
        src = row["module"]
        owners = owners_of(row["fqn"], symbol_owner, namespace_owner)
        internal = [o for o in owners if o in module_set and o != src]
        if not internal:
            if not owners:
                root = _package_root(row["fqn"])
                if _looks_third_party(row["fqn"]):
                    third_party[root] = third_party.get(root, 0) + 1
                else:
                    slot = unresolved.setdefault(
                        row["fqn"], {"fqn": row["fqn"], "count": 0, "anchor": row["anchor"]}
                    )
                    slot["count"] += 1
            continue
        for dst in internal:
            key = (src, dst)
            weights[key] = weights.get(key, 0) + 1
            if len(examples.setdefault(key, [])) < 3:
                examples[key].append(row["anchor"])

    edges = [
        {"from": a, "to": b, "weight": w, "examples": examples[(a, b)]}
        for (a, b), w in sorted(weights.items())
    ]
    return (
        edges,
        sorted(unresolved.values(), key=lambda r: (-r["count"], r["fqn"]))[:200],
        dict(sorted(third_party.items(), key=lambda kv: (-kv[1], kv[0]))[:60]),
    )


def _package_root(fqn: str) -> str:
    parts = fqn.replace("/", ".").split(".")
    return ".".join(parts[:3]) if len(parts) >= 3 else fqn


def _looks_third_party(fqn: str) -> bool:
    from .lang.base import is_third_party

    if is_third_party(fqn):
        return True
    # A bare, dotless import is a package name from a language whose stdlib we
    # did not enumerate; treat it as external rather than as a finding.
    return "." not in fqn and "/" not in fqn


def _declared_edges(
    extraction: Dict, inventory: Dict, module_set: Set[str]
) -> Tuple[List[Dict], List[Dict]]:
    """Manifest-declared edges, restricted to dependencies that name a module
    of this repository. A `com.fasterxml:jackson` coordinate is a real declared
    dependency but not an inter-module edge, and §5.2's comparison is about
    inter-module edges only.

    Returns `(edges, ambiguous)`.

    A manifest names a dependency by its short name (`project(':core')`,
    `<artifactId>core</artifactId>`), and a monorepo may hold more than one
    module whose directory basename is `core`. An earlier version built
    `{basename: module}` by iterating a `set`, so the winner was whichever the
    set yielded last — which varies with `PYTHONHASHSEED`, making two scans of
    one commit disagree about where a declared dependency points
    (`PHASE/FINDINGS.md` F1).

    Sorting the set would have made that deterministic while leaving CDP
    asserting one of two equally-supported edges. `owners_of` above states the
    opposite policy for the observed arm — *§6.4 forbids the resolver from
    picking when an FQN is declared in more than one place* — and the declared
    arm has no better claim to a winner. So an ambiguous basename yields **no
    edge** and is returned as an unresolved reference instead, which R6 requires
    to surface as an `unknown` rather than as a silent gap.
    """
    by_basename: Dict[str, List[str]] = {}
    for module in sorted(module_set):
        by_basename.setdefault(module.rsplit("/", 1)[-1], []).append(module)

    edges: List[Dict] = []
    ambiguous: List[Dict] = []
    for src, deps in sorted(extraction["declared_deps"].items()):
        for dep in sorted(set(deps)):
            if dep in module_set:
                candidates = [dep]
            else:
                candidates = by_basename.get(dep, [])
            candidates = [c for c in candidates if c != src]
            if len(candidates) == 1:
                edges.append({"from": src, "to": candidates[0]})
            elif len(candidates) > 1:
                ambiguous.append({"from": src, "dep": dep, "candidates": candidates})
    return (
        sorted(edges, key=lambda e: (e["from"], e["to"])),
        sorted(ambiguous, key=lambda a: (a["from"], a["dep"])),
    )


# ------------------------------------------------------------------ layering


def _layer(modules: Sequence[str], edges: Set[Tuple[str, str]]) -> Tuple[List[List[str]], List[List[str]]]:
    """Longest-path layering: a module sits one level above its deepest dependency.

    Cycles are condensed rather than rejected. A dependency cycle between two
    modules is a real property of some repositories, and refusing to schedule is
    a worse answer than scheduling the cycle's members together and saying so.
    """
    deps: Dict[str, Set[str]] = {m: set() for m in modules}
    for src, dst in edges:
        if src in deps and dst in deps:
            deps[src].add(dst)

    cycles = _find_cycles(deps)
    in_cycle: Dict[str, int] = {}
    for i, group in enumerate(cycles):
        for m in group:
            in_cycle[m] = i

    level: Dict[str, int] = {}

    def depth(node: str, seen: Set[str]) -> int:
        if node in level:
            return level[node]
        if node in seen:
            return 0
        seen = seen | {node}
        best = 0
        for dep in deps.get(node, ()):
            if in_cycle.get(dep) is not None and in_cycle.get(dep) == in_cycle.get(node):
                continue  # same cycle: same level by construction
            best = max(best, depth(dep, seen) + 1)
        level[node] = best
        return best

    for m in sorted(modules):
        depth(m, set())

    for group in cycles:
        top = max(level[m] for m in group)
        for m in group:
            level[m] = top

    max_level = max(level.values()) if level else 0
    layers = [sorted(m for m in modules if level[m] == i) for i in range(max_level + 1)]
    return [l for l in layers if l], [sorted(c) for c in cycles if len(c) > 1]


def _find_cycles(deps: Dict[str, Set[str]]) -> List[List[str]]:
    """Tarjan strongly-connected components, iterative to survive deep graphs."""
    index: Dict[str, int] = {}
    low: Dict[str, int] = {}
    on_stack: Set[str] = set()
    stack: List[str] = []
    result: List[List[str]] = []
    counter = [0]

    for root in sorted(deps):
        if root in index:
            continue
        work: List[Tuple[str, Iterable[str]]] = [(root, iter(sorted(deps.get(root, ()))))]
        index[root] = low[root] = counter[0]
        counter[0] += 1
        stack.append(root)
        on_stack.add(root)
        while work:
            node, it = work[-1]
            advanced = False
            for child in it:
                if child not in deps:
                    continue
                if child not in index:
                    index[child] = low[child] = counter[0]
                    counter[0] += 1
                    stack.append(child)
                    on_stack.add(child)
                    work.append((child, iter(sorted(deps.get(child, ())))))
                    advanced = True
                    break
                if child in on_stack:
                    low[node] = min(low[node], index[child])
            if advanced:
                continue
            work.pop()
            if work:
                low[work[-1][0]] = min(low[work[-1][0]], low[node])
            if low[node] == index[node]:
                component = []
                while True:
                    m = stack.pop()
                    on_stack.discard(m)
                    component.append(m)
                    if m == node:
                        break
                if len(component) > 1:
                    result.append(sorted(component))
    return sorted(result)


def summarise(graph: Dict) -> List[str]:
    div = graph["divergence"]
    lines = [
        "graph     declared %d edges / observed %d edges"
        % (div["declared_edges"], div["observed_edges"]),
    ]
    for i, layer in enumerate(graph["levels"]):
        lines.append("  L%d  %s" % (i, ", ".join(layer)))
    if graph["cycles"]:
        lines.append("  cycles: " + "; ".join(" <-> ".join(c) for c in graph["cycles"]))
    for row in graph.get("declared_ambiguous", []):
        lines.append(
            "  ! %s declares '%s'; %d modules share that name, so no edge is drawn: %s"
            % (row["from"], row["dep"], len(row["candidates"]), ", ".join(row["candidates"]))
        )
    return lines
