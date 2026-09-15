"""Phase 7 — two-pass resolution and the xref index (§6.4).

**A leaf must never guess who calls it.** It cannot see its callers — that is
what bounded scope means — so resolution is a deterministic second pass over the
union of everything every scope declared.

Three jobs, all pure Python, all replayable:

1. Resolve every out-of-scope reference against the global symbol table:
   *matched* (a real edge), *third_party* (a dependency-surface fact), or
   *unresolved* (usually reflection, codegen, or a scope the run did not cover).
2. Substitute route constants. `@Path(ApiConstants.SQL_POOL_SERVER_PATH)` must
   reach the output as `/v1/servers` carrying **both** anchors. Without this the
   entire route inventory of the validation target would be a list of Java
   identifiers.
3. Invert `uses[]` into a used-by index. No model is asked "where is `DServer`
   used?" — a question models answer confidently and wrongly. The index is the
   transpose of verified data.

**Collisions: the resolver does not pick.** The union of all `defines[]` is not
injective — a class present in both `src/main` and `src/test`, a shaded
dependency, or two modules that genuinely declare the same name. Every
definition site is recorded, a use is resolved against the definition in its own
module when there is one, and otherwise the reference is emitted `ambiguous`
with all candidates attached.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Sequence, Set, Tuple

from .graph import build_symbol_index, owners_of
from .lang.base import is_third_party

SYMBOLIC_RE = re.compile(r"\$\{([A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)+)\}")


def build_xref(inventory: Dict, extraction: Dict, graph: Dict) -> Dict:
    module_set = {m["name"] for m in inventory["modules"]}
    symbol_owner, namespace_owner = build_symbol_index(extraction)
    role_of = {f["path"]: f["role"] for f in inventory["files"]}

    symbols, collisions = _symbol_table(extraction, role_of)
    constants = _constant_table(extraction)
    uses, counts = _resolve_uses(extraction, module_set, symbol_owner, namespace_owner, symbols)
    used_by = _transpose(uses)
    routes, route_gaps = _resolve_routes(extraction, constants)
    coupling = _coupling(graph)

    return {
        "head": extraction["head"],
        "symbols": symbols,
        "collisions": collisions,
        "constants": constants,
        "uses": uses,
        "used_by": used_by,
        "routes": routes,
        "unresolved_routes": route_gaps,
        "coupling": coupling,
        "resolution": counts,
        "unreferenced_candidates": _unreferenced(symbols, used_by, extraction),
    }


# ------------------------------------------------------------- symbol table


def _symbol_table(extraction: Dict, role_of: Dict[str, str]) -> Tuple[Dict[str, Dict], List[Dict]]:
    table: Dict[str, Dict] = {}
    for row in extraction["defines"]:
        entry = table.setdefault(
            row["fqn"],
            {"fqn": row["fqn"], "kind": row["kind"], "visibility": row["visibility"],
             "modules": [], "sites": []},
        )
        if row["module"] not in entry["modules"]:
            entry["modules"].append(row["module"])
        entry["sites"].append({
            "file": row["file"], "anchor": row["anchor"], "module": row["module"],
            "role": role_of.get(row["file"], "source"),
        })
        if row.get("value") is not None:
            entry["value"] = row["value"]

    collisions = []
    for fqn, entry in table.items():
        entry["modules"].sort()
        entry["sites"].sort(key=lambda s: (s["file"], s["anchor"]["line"]))
        if len(entry["sites"]) > 1:
            entry["collision"] = True
            collisions.append(
                {
                    "fqn": fqn,
                    "kind": entry["kind"],
                    "modules": entry["modules"],
                    "sites": entry["sites"],
                    # Same FQN in two modules is nearly always unintended and is
                    # reported in the overview. Same FQN in main and test within
                    # one module is a common, deliberate pattern.
                    "cross_module": len(entry["modules"]) > 1,
                }
            )
    return (
        dict(sorted(table.items())),
        sorted(collisions, key=lambda c: (not c["cross_module"], c["fqn"])),
    )


def _constant_table(extraction: Dict) -> Dict[str, Dict]:
    """`Owner.NAME` -> literal, for route-constant substitution.

    Keyed on the last two FQN segments rather than the full name because that is
    how the reference is written at the use site: source says
    `ApiConstants.SQL_POOL_SERVER_PATH`, never the fully-qualified form.
    """
    table: Dict[str, Dict] = {}
    for row in extraction["defines"]:
        if row["kind"] not in ("constant", "config_key"):
            continue
        if row.get("value") is None:
            continue
        parts = row["fqn"].split(".")
        if len(parts) < 2:
            continue
        short = ".".join(parts[-2:])
        entry = table.setdefault(short, {"short": short, "candidates": []})
        entry["candidates"].append(
            {
                "fqn": row["fqn"],
                "value": row["value"],
                "module": row["module"],
                "anchor": row["anchor"],
            }
        )
    for entry in table.values():
        entry["candidates"].sort(key=lambda c: (c["fqn"], c["anchor"]["file"], c["anchor"]["line"]))
        values = {c["value"] for c in entry["candidates"]}
        entry["unambiguous"] = len(values) == 1
        if entry["unambiguous"]:
            entry["value"] = entry["candidates"][0]["value"]
    return dict(sorted(table.items()))


# ------------------------------------------------------------------- uses


def _resolve_uses(
    extraction: Dict,
    module_set: Set[str],
    symbol_owner: Dict[str, List[str]],
    namespace_owner: Dict[str, List[str]],
    symbols: Dict[str, Dict],
) -> Tuple[List[Dict], Dict[str, int]]:
    counts = {"local": 0, "matched": 0, "third_party": 0, "ambiguous": 0, "unresolved": 0}
    out: List[Dict] = []

    for row in extraction["uses"]:
        fqn = row["fqn"]
        module = row["module"]
        entry = symbols.get(fqn)
        resolved = None
        target_modules: List[str] = []
        candidates: List[Dict] = []

        if entry:
            target_modules = entry["modules"]
            if len(entry["sites"]) > 1:
                own = [s for s in entry["sites"] if s["module"] == module]
                # A class present in both `src/main` and `src/test` is the most
                # common duplicate FQN there is, and it is deliberate rather
                # than a defect. Escalating it as ambiguous would bury the
                # duplicates that actually mean something — two modules
                # declaring the same name — under the ones that never do.
                production = [s for s in entry["sites"] if s["role"] != "test"]
                if own:
                    resolved = "local"
                    target_modules = [module]
                elif len(production) == 1:
                    resolved = "local" if production[0]["module"] == module else "matched"
                    target_modules = [production[0]["module"]]
                else:
                    resolved = "ambiguous"
                    candidates = [dict(s["anchor"]) for s in entry["sites"]]
            else:
                resolved = "local" if entry["modules"] == [module] else "matched"
        else:
            owners = owners_of(fqn, symbol_owner, namespace_owner)
            internal = [o for o in owners if o in module_set]
            if internal:
                resolved = "local" if internal == [module] else "matched"
                target_modules = internal
            elif is_third_party(fqn) or ("." not in fqn and "/" not in fqn):
                resolved = "third_party"
            else:
                resolved = "unresolved"

        counts[resolved] = counts.get(resolved, 0) + 1
        record = {
            "fqn": fqn,
            "from_module": module,
            "from_file": row["file"],
            "resolved": resolved,
            "anchor": row["anchor"],
        }
        if target_modules:
            record["to_modules"] = target_modules
        if candidates:
            record["candidates"] = candidates
        out.append(record)

    out.sort(key=lambda r: (r["fqn"], r["from_file"], r["anchor"]["line"]))
    return out, counts


def _transpose(uses: Sequence[Dict]) -> Dict[str, List[Dict]]:
    """The used-by index: pure inversion of verified data, no model involved."""
    index: Dict[str, List[Dict]] = {}
    for row in uses:
        if row["resolved"] not in ("local", "matched", "ambiguous"):
            continue
        index.setdefault(row["fqn"], []).append(
            {"module": row["from_module"], "file": row["from_file"], "anchor": row["anchor"]}
        )
    return {
        k: sorted(v, key=lambda r: (r["module"], r["file"], r["anchor"]["line"]))
        for k, v in sorted(index.items())
    }


# ------------------------------------------------------------------ routes


def _resolve_routes(extraction: Dict, constants: Dict[str, Dict]) -> Tuple[List[Dict], List[Dict]]:
    """Substitute `${Owner.CONST}` fragments and attach the definition anchor.

    A route claim arriving with only the annotation anchor is not published
    (§6.3). Here that rule has teeth in both directions: a substitution
    succeeds and the claim gains its second anchor, or it fails and the route is
    reported as an explicit gap — which now genuinely means "the constant was
    not found anywhere in the repository" rather than "the partitioner drew a
    line in an awkward place."
    """
    routes: List[Dict] = []
    gaps: List[Dict] = []

    for edge in extraction["io_edges"]:
        if edge["channel"] != "http_in" or not edge["target"].startswith("route:"):
            continue
        raw = edge["target"][len("route:") :]
        verb, _, path = raw.partition(" ")
        if not path:
            verb, path = "ANY", raw

        anchors = [edge["anchor"]]
        resolved_path = path
        missing: List[str] = []
        for ref in SYMBOLIC_RE.findall(path):
            entry = constants.get(ref)
            if entry and entry.get("unambiguous"):
                resolved_path = resolved_path.replace("${%s}" % ref, str(entry["value"]))
                anchors.append(entry["candidates"][0]["anchor"])
            else:
                missing.append(ref)

        record = {
            "verb": verb,
            "route": resolved_path,
            "symbolic": path if missing or path != resolved_path else None,
            "handler": edge["source"],
            "module": edge["module"],
            "file": edge["file"],
            "evidence": anchors,
        }
        if missing:
            record["unresolved_constants"] = sorted(set(missing))
            gaps.append(record)
        else:
            routes.append(record)

    routes.sort(key=lambda r: (r["route"], r["verb"], r["file"]))
    gaps.sort(key=lambda r: (r["route"], r["verb"], r["file"]))
    return routes, gaps


# ------------------------------------------------------------- derived views


def _coupling(graph: Dict) -> Dict[str, int]:
    return {"%s -> %s" % (e["from"], e["to"]): e["weight"] for e in graph["observed"]}


def _unreferenced(
    symbols: Dict[str, Dict], used_by: Dict[str, List[Dict]], extraction: Dict
) -> Dict:
    """§6.6: unreferenced symbols are **candidates**, never dead code.

    On the validation target a symbol can be live with zero static references
    through Spring DI (34 `@Component`, 9 `@Bean`), JAX-RS resource
    registration, Quartz job discovery, and MapStruct-generated implementations.
    Any of these makes a naive dead-code claim wrong, so the finding is phrased
    with its exclusion list attached rather than as a verdict.
    """
    framework_managed: Set[str] = set()
    for rel, info in extraction["files"].items():
        for signal in info.get("signals", []):
            if signal.startswith("di:") or signal in (
                "http_resource", "repository", "mapper", "entity", "quartz_job",
                "scheduled", "main", "deployable",
            ):
                framework_managed.add(rel)

    candidates = []
    for fqn, entry in symbols.items():
        if entry["kind"] not in ("class", "interface", "enum", "record"):
            continue
        if entry["visibility"] != "public":
            continue
        if fqn in used_by:
            continue
        files = {s["file"] for s in entry["sites"]}
        if files & framework_managed:
            continue
        candidates.append({"fqn": fqn, "kind": entry["kind"], "sites": entry["sites"][:1]})

    return {
        "note": (
            "No static reference found. Framework-managed entry points are excluded: "
            "dependency-injection annotations, HTTP resource registration, scheduled "
            "jobs, repositories, entities and generated mappers. These are candidates "
            "for review, not dead code (§6.6)."
        ),
        "excluded_files": len(framework_managed),
        "candidates": sorted(candidates, key=lambda c: c["fqn"])[:200],
        "candidate_count": len(candidates),
    }


def summarise(xref: Dict) -> List[str]:
    res = xref["resolution"]
    lines = [
        "resolve   %d local / %d matched / %d third-party / %d ambiguous / %d unresolved"
        % (res.get("local", 0), res.get("matched", 0), res.get("third_party", 0),
           res.get("ambiguous", 0), res.get("unresolved", 0)),
        "routes    %d resolved, %d with unresolved constants"
        % (len(xref["routes"]), len(xref["unresolved_routes"])),
        "symbols   %d defined, %d colliding (%d across modules)"
        % (
            len(xref["symbols"]),
            len(xref["collisions"]),
            sum(1 for c in xref["collisions"] if c["cross_module"]),
        ),
    ]
    return lines
