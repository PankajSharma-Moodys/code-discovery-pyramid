"""Deterministic claims — the structural facts, stated as citable claims.

PLAN.md's central decision is that Python owns structure and the LLM owns
meaning. This module is the first half of that bargain paying out: everything
here is a claim with real anchors that no agent had to be spawned to produce.

Two consequences worth being explicit about.

**CDP is useful before a single token is spent.** `cdp scan` runs inventory,
extraction, resolution and this module, and the result already answers most of
the questions a new joiner asks on day three — what the routes are, which module
owns which table, what the deployables are, where the config comes from. Leaf
agents then add the layer Python genuinely cannot: what any of it is *for*.

**These claims are the floor, not the ceiling.** A derived claim states what the
source says. It does not say why, and it will not notice that a module is named
one thing and its artifact another unless a rule here looks for exactly that.
Every rule in this file is a rule someone wrote down; the gaps are real and are
what the leaf agents and `unknowns.md` exist to cover.
"""

from __future__ import annotations

import re
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from .inventory import ROOT_MODULE

SLUG_RE = re.compile(r"[^a-z0-9]+")


def slug(text: str, fallback: str = "x") -> str:
    out = SLUG_RE.sub("_", str(text).lower()).strip("_")
    return out or fallback


def claim_id(*parts: str) -> str:
    """Build an id matching the schema's `^[a-z0-9_]+(\\.[a-z0-9_]+)+$`."""
    pieces = [slug(p) for p in parts if str(p).strip()]
    if len(pieces) < 2:
        pieces = (pieces + ["fact", "fact"])[:2]
    return ".".join(pieces)


def derive_claims(
    repo, inventory: Dict, extraction: Dict, graph: Dict, xref: Dict,
    partition: Dict, dataflow: Optional[Dict] = None
) -> List[Dict]:
    node_of = _node_index(partition)
    claims: List[Dict] = []
    claims += _naming(inventory, extraction, node_of)
    claims += _routes(xref, node_of)
    claims += _entrypoints(extraction, node_of)
    claims += _deployables(extraction, node_of)
    claims += _data_models(extraction, xref, node_of)
    claims += _schema_ownership(extraction, node_of)
    claims += _side_effects(extraction, node_of)
    claims += _config(extraction, node_of)
    claims += _dependencies(graph, node_of)
    claims += _generated(repo, inventory, node_of)
    claims += _boundaries(dataflow or {}, node_of)

    seen = set()
    unique = []
    for claim in sorted(claims, key=lambda c: (c["kind"], c["subject"], c["id"])):
        key = (claim["id"], claim["subject"], claim["kind"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(claim)
    return unique


def _node_index(partition: Dict) -> Dict[str, str]:
    index: Dict[str, str] = {}
    for scope in partition["scopes"]:
        for path in scope["files"]:
            index[path] = scope["node"]
    return index


def _claim(
    node_of: Dict[str, str],
    kind: str,
    subject: str,
    statement: str,
    evidence: Sequence[Dict],
    *,
    channel: Optional[str] = None,
    visibility: Optional[str] = None,
    side_effect_type: Optional[str] = None,
    confidence: str = "high",
    id_parts: Sequence[str] = (),
) -> Optional[Dict]:
    evidence = [e for e in evidence if e]
    if not evidence or len(statement) < 12:
        return None
    claim = {
        "id": claim_id(*(id_parts or (kind, subject))),
        "kind": kind,
        "subject": subject,
        "statement": statement[:500],
        "evidence": list(evidence),
        "confidence": confidence,
        "source_node": node_of.get(str(evidence[0].get("file")), "root"),
    }
    if channel:
        claim["channel"] = channel
    if visibility:
        claim["visibility"] = visibility
    if side_effect_type:
        claim["side_effect_type"] = side_effect_type
    return claim


def _add(out: List[Dict], claim: Optional[Dict]) -> None:
    if claim is not None:
        out.append(claim)


def _short(fqn: str) -> str:
    """A readable name for a symbol, whatever shape its language gives it.

    `a.b.C#method` -> `C#method`, `a.b.C` -> `C`, `path/to/mod` -> `mod`.
    Blindly taking the last dotted segment turns the Python module
    `svc.store.repo` into `repo`, which reads as a class name and produces
    sentences that are subtly wrong about what kind of thing they describe.
    """
    name = fqn.rsplit("/", 1)[-1]
    if "#" in name:
        owner, _, member = name.partition("#")
        return owner.rsplit(".", 1)[-1] + "#" + member
    return name.rsplit(".", 1)[-1]


# ------------------------------------------------------------------ naming


def _naming(inventory: Dict, extraction: Dict, node_of: Dict[str, str]) -> List[Dict]:
    out: List[Dict] = []

    # rootProject.name vs directory names -- RESEARCH.md's own opening example.
    for row in extraction["defines"]:
        if row["fqn"] != "build:rootProject.name":
            continue
        value = str(row.get("value", ""))
        dirs = [m["name"] for m in inventory["modules"] if m["name"] != ROOT_MODULE]
        if value and not any(d.startswith(value) or value in d for d in dirs):
            _add(
                out,
                _claim(
                    node_of,
                    "naming",
                    "build:rootProject.name",
                    "The build's root project is named '%s', which appears in no directory name; "
                    "every module directory is '%s...'. Build logs, metrics and the OpenAPI title "
                    "use '%s'." % (value, _common_dir_prefix(dirs) or "?", value),
                    [row["anchor"]],
                    id_parts=("naming", "root_project", value),
                ),
            )

    # Declared package vs directory path.
    divergences: Dict[str, List[str]] = {}
    for module, notes in extraction["module_notes"].items():
        for note in notes:
            if note.startswith("package_path_divergence:"):
                _, kind, pair = note.split(":", 2)
                divergences.setdefault(kind, []).append(pair)

    for kind, pairs in sorted(divergences.items()):
        example = sorted(pairs)[0]
        from_path, declared = example.split("|", 1)
        anchor = _find_package_anchor(extraction, declared)
        label = (
            "differ only in case" if kind == "case" else "do not correspond"
        )
        _add(
            out,
            _claim(
                node_of,
                "naming",
                "package-path-divergence",
                "%d source files declare a package whose text and directory path %s "
                "(e.g. directory '%s' declares 'package %s'). Any path-to-package inference "
                "produces names that match nothing; on a case-insensitive filesystem this is invisible."
                % (len(pairs), label, from_path.replace(".", "/"), declared),
                [anchor] if anchor else [],
                confidence="high",
                id_parts=("naming", "package_path", kind),
            ),
        )
    return out


def _common_dir_prefix(dirs: Sequence[str]) -> str:
    if not dirs:
        return ""
    prefix = dirs[0]
    for d in dirs[1:]:
        while prefix and not d.startswith(prefix):
            prefix = prefix[:-1]
    return prefix


def _find_package_anchor(extraction: Dict, package: str) -> Optional[Dict]:
    for row in extraction["defines"]:
        if row["fqn"].startswith(package + ".") and row["kind"] in ("class", "interface", "enum"):
            return row["anchor"]
    return None


# ------------------------------------------------------------- entrypoints


def _routes(xref: Dict, node_of: Dict[str, str]) -> List[Dict]:
    out: List[Dict] = []
    for route in xref["routes"]:
        symbolic = " (declared via the constant %s)" % route["symbolic"] if route.get("symbolic") else ""
        _add(
            out,
            _claim(
                node_of,
                "entrypoint",
                "route:%s %s" % (route["verb"], route["route"]),
                "%s %s is served by %s in %s%s."
                % (route["verb"], route["route"], route["handler"].rsplit(".", 1)[-1],
                   route["module"], symbolic),
                route["evidence"],
                channel="http_in",
                id_parts=("entrypoint", "route", route["verb"], route["route"]),
            ),
        )
    # A route whose constant could not be resolved is a stated gap, not a
    # silently-published identifier (§6.3).
    for route in xref["unresolved_routes"]:
        _add(
            out,
            _claim(
                node_of,
                "entrypoint",
                "route:%s %s" % (route["verb"], route["route"]),
                "%s route declared symbolically as %s; the constant %s was not found anywhere "
                "in the repository, so the literal path is unknown."
                % (route["verb"], route["route"], ", ".join(route.get("unresolved_constants", []))),
                route["evidence"],
                channel="http_in",
                confidence="low",
                id_parts=("entrypoint", "route_unresolved", route["verb"], route["route"]),
            ),
        )
    return out


def _entrypoints(extraction: Dict, node_of: Dict[str, str]) -> List[Dict]:
    out: List[Dict] = []
    for edge in extraction["io_edges"]:
        if edge["channel"] == "process_boundary" and edge["target"].startswith("process:"):
            # A Dockerfile also marks its directory as a process. That fact is
            # already stated as a `deployable` claim with the entry command, so
            # emitting it again here would list every unit twice under two
            # headings. Only the source-declared entry point (a `main()`, whose
            # source is a symbol rather than a module directory) belongs here.
            if edge["source"] == edge["module"]:
                continue
            _add(
                out,
                _claim(
                    node_of,
                    "entrypoint",
                    edge["source"],
                    "%s declares a process entry point in %s; it is one of the repository's "
                    "separately-startable units." % (edge["source"].rsplit(".", 1)[-1], edge["module"]),
                    [edge["anchor"]],
                    channel="process_boundary",
                    id_parts=("entrypoint", "main", edge["source"]),
                ),
            )
        elif edge["channel"] == "schedule" and edge["target"] in ("scheduler",):
            _add(
                out,
                _claim(
                    node_of,
                    "entrypoint",
                    edge["source"],
                    "%s is timer-triggered rather than request-triggered; it runs as a scheduled "
                    "job in %s." % (edge["source"].rsplit(".", 1)[-1], edge["module"]),
                    [edge["anchor"]],
                    channel="schedule",
                    id_parts=("entrypoint", "schedule", edge["source"]),
                ),
            )
    return out


def _deployables(extraction: Dict, node_of: Dict[str, str]) -> List[Dict]:
    out: List[Dict] = []
    for row in extraction["defines"]:
        if row["kind"] == "config_key" and row["fqn"].startswith("process:") and row.get("value"):
            _add(
                out,
                _claim(
                    node_of,
                    "deployable",
                    row["fqn"],
                    "%s is packaged as its own container image; its entry command is %s."
                    % (row["module"], str(row["value"])[:200]),
                    [row["anchor"]],
                    channel="process_boundary",
                    id_parts=("deployable", row["fqn"]),
                ),
            )
    return out


# ------------------------------------------------------------- data models


def _data_models(extraction: Dict, xref: Dict, node_of: Dict[str, str]) -> List[Dict]:
    out: List[Dict] = []
    for edge in extraction["io_edges"]:
        if edge["channel"] != "persist":
            continue
        if edge["target"].startswith("table:"):
            table = edge["target"][len("table:") :]
            _add(
                out,
                _claim(
                    node_of,
                    "data_model",
                    edge["target"],
                    "Table '%s' is written from %s in %s."
                    % (table, _short(edge["source"]), edge["module"]),
                    [edge["anchor"]],
                    channel="persist",
                    id_parts=("data_model", "entity", table),
                ),
            )
        elif edge["target"].startswith("entity:"):
            entity = edge["target"][len("entity:") :]
            same = _short(entity) == _short(edge["source"])
            _add(
                out,
                _claim(
                    node_of,
                    "data_model",
                    edge["target"],
                    (
                        "%s is persisted, but no table name is stated in source; the binding is "
                        "left to the persistence framework's default." % _short(entity)
                        if same
                        else "%s reads and writes %s; no table name is stated in source, so the "
                        "binding is left to the persistence framework's default."
                        % (_short(edge["source"]), _short(entity))
                    ),
                    [edge["anchor"]],
                    channel="persist",
                    confidence="medium",
                    id_parts=("data_model", "repository", edge["source"], entity),
                ),
            )

    # Representation chains: each `map` edge is one hop of the transformation
    # topology §6.1 calls invisible to a dependency graph.
    for edge in extraction["io_edges"]:
        if edge["channel"] != "map":
            continue
        _add(
            out,
            _claim(
                node_of,
                "data_model",
                "%s -> %s" % (edge["source"], edge["target"]),
                "%s is converted to %s by a mapper in %s; the two are different representations "
                "of the same record."
                % (edge["source"].rsplit(".", 1)[-1], edge["target"].rsplit(".", 1)[-1], edge["module"]),
                [edge["anchor"]],
                channel="map",
                id_parts=("data_model", "map", edge["source"], edge["target"]),
            ),
        )
    return out


def _schema_ownership(extraction: Dict, node_of: Dict[str, str]) -> List[Dict]:
    by_table: Dict[str, List[Dict]] = {}
    for edge in extraction["io_edges"]:
        if edge["channel"] == "schema_own" and edge["target"].startswith("table:"):
            by_table.setdefault(edge["target"], []).append(edge)

    out: List[Dict] = []
    for target in sorted(by_table):
        edges = sorted(by_table[target], key=lambda e: e["file"])
        modules = sorted({e["module"] for e in edges})
        _add(
            out,
            _claim(
                node_of,
                "ownership",
                target,
                "The schema for '%s' is owned by %s, defined across %d migration(s)."
                % (target[len("table:") :], ", ".join(modules), len(edges)),
                [e["anchor"] for e in edges[:4]],
                channel="schema_own",
                id_parts=("ownership", "schema", target),
            ),
        )
    return out


# ------------------------------------------------------------ side effects


_SIDE_EFFECTS = {
    "ssh_exec": ("ssh_exec", "runs commands on remote hosts over SSH"),
    "http_out": ("http_out", "makes outbound HTTP calls"),
    "metric_emit": ("metric_emit", "emits metrics to an observability sink"),
    "read": ("db_read", "reads from the database"),
}


def _side_effects(extraction: Dict, node_of: Dict[str, str]) -> List[Dict]:
    out: List[Dict] = []
    grouped: Dict[Tuple[str, str], List[Dict]] = {}
    for edge in extraction["io_edges"]:
        if edge["channel"] in _SIDE_EFFECTS:
            grouped.setdefault((edge["module"], edge["channel"]), []).append(edge)

    for (module, channel), edges in sorted(grouped.items()):
        effect, phrase = _SIDE_EFFECTS[channel]
        edges = sorted(edges, key=lambda e: (e["file"], e["anchor"]["line"]))
        _add(
            out,
            _claim(
                node_of,
                "side_effect",
                "%s:%s" % (module, channel),
                "%s %s, across %d site(s)." % (module, phrase, len(edges)),
                [e["anchor"] for e in edges[:3]],
                channel=channel,
                side_effect_type=effect,
                id_parts=("side_effect", module, channel),
            ),
        )
    return out


def _config(extraction: Dict, node_of: Dict[str, str]) -> List[Dict]:
    out: List[Dict] = []
    grouped: Dict[str, List[Dict]] = {}
    for edge in extraction["io_edges"]:
        if edge["channel"] == "config_read" and edge["target"].startswith("config:"):
            if edge["source"].startswith("config-file:"):
                continue  # the file declaring the key, not a read of it
            grouped.setdefault(edge["target"], []).append(edge)

    for target in sorted(grouped):
        edges = sorted(grouped[target], key=lambda e: (e["file"], e["anchor"]["line"]))
        modules = sorted({e["module"] for e in edges})
        _add(
            out,
            _claim(
                node_of,
                "config",
                target,
                "Configuration key '%s' is read at %d site(s) in %s."
                % (target[len("config:") :], len(edges), ", ".join(modules)),
                [e["anchor"] for e in edges[:3]],
                channel="config_read",
                id_parts=("config", target),
            ),
        )
    return out


# ------------------------------------------------------------- dependencies


def _dependencies(graph: Dict, node_of: Dict[str, str]) -> List[Dict]:
    out: List[Dict] = []
    declared = {(e["from"], e["to"]) for e in graph["declared"]}
    for edge in graph["observed"]:
        pair = (edge["from"], edge["to"])
        note = "" if pair in declared else " This edge is NOT declared in the build manifest; it compiles by transitive resolution and will break on a dependency bump."
        _add(
            out,
            _claim(
                node_of,
                "dependency",
                "%s -> %s" % (edge["from"], edge["to"]),
                "%s imports %s at %d distinct sites.%s"
                % (edge["from"], edge["to"], edge["weight"], note),
                edge["examples"][:2],
                confidence="high" if pair in declared else "medium",
                id_parts=("dependency", "observed", edge["from"], edge["to"]),
            ),
        )
    return out


def _boundaries(dataflow: Dict, node_of: Dict[str, str]) -> List[Dict]:
    """The process-boundary data edges (RESEARCH.md section 6.1, criterion 4c).

    Grouped by process pair rather than emitted per table. Thirteen separate
    claims saying "api and manager both touch X" is one fact reported thirteen
    times, and burying it under its own repetitions is how a real finding gets
    skimmed past.
    """
    grouped: Dict[Tuple[str, ...], List[Dict]] = {}
    for row in dataflow.get("process_boundaries", []):
        grouped.setdefault(tuple(row["processes"]), []).append(row)

    out: List[Dict] = []
    for processes, rows in sorted(grouped.items()):
        shared = sorted({r["shared"] for r in rows})
        tables = [s for s in shared if s.startswith("table:")]
        evidence: List[Dict] = []
        for row in rows[:2]:
            evidence.extend(row["evidence"][:3])
        names = [p.rsplit(".", 1)[-1] for p in processes]
        _add(
            out,
            _claim(
                node_of,
                "side_effect",
                " <-> ".join(processes),
                "%s are separate deployable units that exchange data through shared storage "
                "(%d shared target(s)%s). No import connects them, so no dependency graph shows "
                "this edge; it is reachability over packaged code, not an observed runtime call."
                % (" and ".join(names), len(shared),
                   ", including " + ", ".join(t[len("table:"):] for t in tables[:4]) if tables else ""),
                evidence,
                channel="process_boundary",
                side_effect_type="db_write",
                confidence="medium",
                id_parts=("side_effect", "process_boundary") + tuple(names),
            ),
        )
    return out


def _generated(repo, inventory: Dict, node_of: Dict[str, str]) -> List[Dict]:
    """§6.7: a module whose tracked files are a rounding error against its disk
    files is described by its contract, not read.

    The anchor is the module's own build manifest — the thing that *states* the
    generation step — because that is the only file in the module a reader can
    actually check. Citing a generated file would be citing the symptom.
    """
    from .anchor import build_anchor
    from .util import read_lines

    out: List[Dict] = []
    for module in inventory["modules"]:
        if not module.get("generated_suspect") or not module["manifests"]:
            continue
        manifest = module["manifests"][0]
        lines = read_lines(repo / manifest)
        anchor = None
        for index in range(min(len(lines), 40)):
            anchor = build_anchor(manifest, lines, index)
            if anchor:
                break
        _add(
            out,
            _claim(
                node_of,
                "dependency",
                module["name"],
                "%s holds %d git-tracked file(s) against %d on disk. Its contents are generated "
                "at build time, so they are invisible to a git-based inventory and are described "
                "by the build contract rather than read."
                % (module["name"], module["files"], module.get("on_disk", 0)),
                [anchor] if anchor else [],
                channel="codegen",
                id_parts=("dependency", "generated", module["name"]),
            ),
        )
    return out
