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

from . import sigs
from .rules import all_edges
from .graph import build_symbol_index, owners_of
from .cfgwrap import wrapped_reads
from .cstypes import CsTypeIndex
from .pytypes import PyIndex
from .lang.base import is_third_party
from .routes_cs import expand_routes

SYMBOLIC_RE = re.compile(r"\$\{([A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)+)\}")


def build_xref(inventory: Dict, extraction: Dict, graph: Dict) -> Dict:
    module_set = {m["name"] for m in inventory["modules"]}
    symbol_owner, namespace_owner = build_symbol_index(extraction)
    role_of = {f["path"]: f["role"] for f in inventory["files"]}

    symbols, collisions = _symbol_table(extraction, role_of)
    constants = _constant_table(extraction)
    _resolve_annotation_args(symbols, constants)
    paths = [f["path"] for f in inventory["files"]]
    cfg_calls: List[Tuple[str, Dict]] = []
    uses, counts = _resolve_by_language(extraction, module_set, symbol_owner, namespace_owner, symbols,
                                        paths, cfg_calls, role_of)
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
        "config_wrapped": wrapped_reads(symbols, cfg_calls),
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
        site = {
            "file": row["file"], "anchor": row["anchor"], "module": row["module"],
            "role": role_of.get(row["file"], "source"),
        }
        if row.get("end_line"):
            site["end_line"] = row["end_line"]
        for key in ("annotations", "params", "supertypes", "sig", "arity"):   # per declaration: overloads differ
            if row.get(key):
                site[key] = row[key]
        entry["sites"].append(site)
        if row.get("value") is not None:
            entry["value"] = row["value"]
        if row.get("cfgp"):     # parameters naming a config key: a wrapper (cfgwrap.py)
            entry["cfgp"] = sorted(set(entry.get("cfgp", ())) | set(row["cfgp"]))
        for key in ("ret", "ftype", "tparams"):
            # Overloads and duplicate declarations that disagree on a type
            # settle nothing: the walk must not pick one.
            if key not in entry:
                entry[key] = row.get(key)
            elif entry[key] != row.get(key):
                entry[key] = None

    collisions = []
    for fqn, entry in table.items():
        for key in ("ret", "ftype", "tparams"):
            if entry.get(key) is None:
                entry.pop(key, None)
        entry["modules"].sort()
        entry["sites"].sort(key=lambda s: (s["file"], s["anchor"]["line"]))
        clash, overloads = sigs.collision(entry["sites"])
        if overloads:
            entry["overloads"] = overloads
        if clash:
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


def _resolve_arg(value, constants: Dict[str, Dict], owner: str, module: str):
    """`value` with `resolved` added to every `{"ref"}` / `{"concat"}` the constant table can
    resolve (a constant of any file); anything else, and anything unresolvable, is returned as is."""
    if isinstance(value, list):
        return [_resolve_arg(v, constants, owner, module) for v in value]
    if not isinstance(value, dict):
        return value
    if "ref" in value:
        text = _resolve_ref(value["ref"], constants, owner, module)
        return {**value, "resolved": text} if text is not None else value
    if "concat" in value:
        out = []
        for part in value["concat"]:
            text = part if isinstance(part, str) else _resolve_ref(part.get("ref", ""), constants, owner, module)
            if text is None:
                return value
            out.append(text)
        return {**value, "resolved": "".join(out)}
    if "args" in value and "name" in value:             # a nested annotation row
        return {**value, "args": _resolve_args(value["args"], constants, owner, module)}
    return value


def _resolve_ref(ref: str, constants: Dict[str, Dict], owner: str, module: str):
    parts = ref.split(".")
    key = ".".join(parts[-2:]) if len(parts) > 1 else "%s.%s" % (owner, ref)
    if not owner and len(parts) == 1:
        return None
    text, _, missing = expand_placeholders("${%s}" % key, constants, module=module)
    return None if missing else text


def _resolve_args(args: Dict, constants: Dict[str, Dict], owner: str, module: str) -> Dict:
    return {k: _resolve_arg(v, constants, owner, module) for k, v in args.items()}


def _resolve_annotation_args(symbols: Dict[str, Dict], constants: Dict[str, Dict]) -> None:
    """Annotation `args` on xref sites gain `resolved` next to constant refs and concatenations
    (`{"ref": "ApiConstants.X", "resolved": "/v1/servers"}`). The extraction rows are not touched."""
    if not constants:
        return

    def rows(anns, owner, module):
        return [{**a, "args": _resolve_args(a["args"], constants, owner, module)} if a.get("args") else a
                for a in anns]

    for fqn, entry in symbols.items():
        head = fqn.partition("#")[0]
        owner = head.rpartition(".")[2]
        for site in entry["sites"]:
            module = site["module"]
            if site.get("annotations"):
                site["annotations"] = rows(site["annotations"], owner, module)
            if site.get("params"):
                site["params"] = [{**p, "annotations": rows(p["annotations"], owner, module)}
                                  if p.get("annotations") else p for p in site["params"]]


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


def _lang_of(path: str) -> str:
    ext = path.rsplit(".", 1)[-1].lower() if "." in path.rsplit("/", 1)[-1] else ""
    return "python" if ext in ("py", "pyi") else ext


def _resolve_by_language(extraction, module_set, symbol_owner, namespace_owner, symbols, paths,
                         cfg_calls, role_of):
    """`_resolve_uses`, with each language resolving only against its own declarations when a
    fully-qualified name is declared in more than one language (C# `Acme.Svc` and Java `Acme.Svc`
    are different types; the merged `symbols` table would let a call land on the other's members).
    Without such a collision this is exactly one `_resolve_uses` pass."""
    langs: Dict[str, Set[str]] = {}
    for row in extraction["defines"]:
        langs.setdefault(row["fqn"], set()).add(_lang_of(row["file"]))
    if not any(len(v) > 1 for v in langs.values()):
        return _resolve_uses(extraction, module_set, symbol_owner, namespace_owner, symbols, paths, cfg_calls)
    groups = sorted({l for v in langs.values() for l in v} | {_lang_of(r["file"]) for r in extraction["uses"]})
    out: List[Dict] = []
    counts: Dict[str, int] = {"local": 0, "matched": 0, "third_party": 0, "ambiguous": 0, "unresolved": 0}
    for lang in groups:
        part = dict(extraction)
        for key in ("defines", "uses", "imports"):
            part[key] = [r for r in extraction.get(key, []) if _lang_of(r["file"]) == lang]
        if not part["uses"]:
            continue
        lsyms, _ = _symbol_table(part, role_of)
        lown, lns = build_symbol_index(part)
        rows, c = _resolve_uses(part, module_set, lown, lns, lsyms, paths, cfg_calls)
        # an undeclared member that only another language declares is that language's, not a
        # fallback onto this one's class
        dropped = [r for r in rows if "#" in r["fqn"] and r["fqn"] not in lsyms and r["fqn"] in symbols]
        for r in dropped:
            c[r["resolved"]] = c.get(r["resolved"], 0) - 1
        rows = [r for r in rows if not ("#" in r["fqn"] and r["fqn"] not in lsyms and r["fqn"] in symbols)]
        out.extend(rows)
        for k, v in c.items():
            counts[k] = counts.get(k, 0) + v
    out.sort(key=lambda r: (r["fqn"], r["from_file"], r["anchor"]["line"]))
    return out, counts


def _resolve_uses(
    extraction: Dict,
    module_set: Set[str],
    symbol_owner: Dict[str, List[str]],
    namespace_owner: Dict[str, List[str]],
    symbols: Dict[str, Dict],
    paths: Sequence[str] = (),
    cfg_calls: Optional[List[Tuple[str, Dict]]] = None,
) -> Tuple[List[Dict], Dict[str, int]]:
    counts = {"local": 0, "matched": 0, "third_party": 0, "ambiguous": 0, "unresolved": 0}
    out: List[Dict] = []
    types = PyIndex(extraction, symbols, paths)
    cstypes = CsTypeIndex(extraction, symbols) if any(f.endswith(".cs") for f in extraction["files"]) else None

    # Python call/reference rows are expressions; each becomes one row per target.
    for row in types.expand(extraction["uses"]):
        fqn = row["fqn"]
        module = row["module"]
        entry = symbols.get(fqn)
        if row.get("pyres"):
            pass  # `PyIndex.expand` already settled the target
        elif row.get("kind") == "call":
            # Inherited methods resolve to their declaring class; chained
            # receivers are walked through declared return and field types.
            fqn = (cstypes if cstypes and row["file"].endswith(".cs") else types).call_target(row)
            if fqn is None:
                continue
            entry = symbols.get(fqn) or symbols.get(fqn.split("#", 1)[0])
        elif row.get("kind"):
            # Member-level rows (typed references, calls, bindings) name a type
            # the extractor could only guess at -- same package or a wildcard
            # import. Only a candidate that is a real symbol counts, and it is
            # never settled through a namespace match: `pkg.Repo` resolving
            # because `pkg` is a known package is how a call lands on a class
            # that does not exist.
            fqn, entry = _member_target(fqn, row.get("alts") or (), symbols)
            if entry is None:
                continue
        elif entry is None and "#" in fqn:
            entry = symbols.get(fqn.split("#", 1)[0])
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

        kind = row.get("kind")
        if kind and resolved not in ("local", "matched", "ambiguous"):
            # Member-level facts (typed references, calls) that name nothing
            # in this repository are not "unresolved imports": most are
            # `String`-like types or third-party calls. Dropped, not counted.
            continue
        counts[resolved] = counts.get(resolved, 0) + 1
        record = {
            "fqn": fqn,
            "from_module": module,
            "from_file": row["file"],
            "resolved": resolved,
            "anchor": row["anchor"],
        }
        if kind:
            record["kind"] = kind
            record["from_symbol"] = row.get("from_symbol")
            if row.get("from_sig"):
                record["from_sig"] = row["from_sig"]
            if kind == "call" and entry and entry.get("kind") == "method" and len(entry["sites"]) > 1:
                _overload(record, entry["sites"], row)
        if target_modules:
            record["to_modules"] = target_modules
        if candidates:
            record["candidates"] = candidates
        out.append(record)
        if cfg_calls is not None and row.get("ka") and kind == "call":
            cfg_calls.append((fqn, row))

    out.sort(key=lambda r: (r["fqn"], r["from_file"], r["anchor"]["line"]))
    return out, counts


def _overload(record: Dict, sites: List[Dict], row: Dict) -> None:
    """A call to an overloaded name: `sig` + `sig_by` (`arity`/`type`) for the one overload it can be,
    else `sig_candidates` -- every overload still possible, never a guess (cdp/sigs.py)."""
    sig, how, candidates = sigs.resolve(sites, row.get("argc"), row.get("argt"))
    if sig:
        record["sig"], record["sig_by"] = sig, how
    elif candidates:
        record["sig_candidates"] = candidates


def _member_target(fqn: str, alts, symbols: Dict[str, Dict]):
    """First of `fqn` and its wildcard-import alternatives whose type exists.
    `Type#method` names resolve through the owning type: the method may be
    inherited (`save`) or an interface method the extractor never defines."""
    for cand in (fqn, *alts):
        owner = cand.split("#", 1)[0]
        entry = symbols.get(cand) or symbols.get(owner)
        if entry and entry["kind"] in ("class", "interface", "enum", "record", "annotation", "method"):
            return cand, entry
    return fqn, None


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


def expand_placeholders(text: str, constants: Dict[str, Dict], _seen: Tuple[str, ...] = (),
                        module: Optional[str] = None) -> Tuple[str, List[Dict], List[str]]:
    """Substitute every `${Owner.NAME}` in `text` with the constant's value, and
    recursively inside that value (`BASE = "${Api.ROOT}/v1"`). Returns the text,
    the anchors of the constants used, and the references that stayed unresolved
    (unknown, ambiguous, or a cycle)."""
    anchors: List[Dict] = []
    missing: List[str] = []

    def sub(m):
        ref = m.group(1)
        entry = constants.get(ref)
        if entry and not entry.get("unambiguous") and module:
            # the same `Owner.NAME` declared with different values in several modules: the use
            # site's own module decides, when it declares exactly one value
            own = [c for c in entry["candidates"] if c["module"] == module]
            if own and len({c["value"] for c in own}) == 1:
                entry = {"unambiguous": True, "value": own[0]["value"], "candidates": own}
        if not entry or not entry.get("unambiguous") or ref in _seen:
            missing.append(ref)
            return m.group(0)
        inner, inner_anchors, inner_missing = expand_placeholders(str(entry["value"]), constants, _seen + (ref,), module)
        anchors.append(entry["candidates"][0]["anchor"])
        anchors.extend(inner_anchors)
        missing.extend(inner_missing)
        return inner

    return SYMBOLIC_RE.sub(sub, text), anchors, missing


ENV_DEFAULT_RE = re.compile(r"^\$\{[A-Za-z_]\w*(?::-|-)([^}]*)\}$")
CONTEXT_PATH_KEY = "config:server.applicationContextPath"


def _context_paths(extraction: Dict, constants: Dict[str, Dict]) -> Dict[str, Tuple[str, Dict]]:
    """module -> (Dropwizard `server.applicationContextPath`, its anchor), only where the
    module's own config states one unambiguously. A `${ENV:-/x}` value contributes its default."""
    found: Dict[str, Dict[str, Dict]] = {}
    for row in extraction["defines"]:
        if row["kind"] != "config_key" or row["fqn"] != CONTEXT_PATH_KEY or not row.get("value"):
            continue
        value = str(row["value"]).strip().strip("\"'")
        env = ENV_DEFAULT_RE.match(value)
        value = env.group(1) if env else value
        value, _, missing = expand_placeholders(value, constants)
        if missing or not value.startswith("/"):
            continue
        found.setdefault(row["module"], {}).setdefault(value, row["anchor"])
    return {m: next(iter(v.items())) for m, v in found.items() if len(v) == 1}


def _resolve_routes(extraction: Dict, constants: Dict[str, Dict]) -> Tuple[List[Dict], List[Dict]]:
    """Substitute `${Owner.CONST}` fragments and attach the definition anchor.

    A route claim arriving with only the annotation anchor is not published
    (§6.3). Here that rule has teeth in both directions: a substitution
    succeeds and the claim gains its second anchor, or it fails and the route is
    reported as an explicit gap — which now genuinely means "the constant was
    not found anywhere in the repository" rather than "the partitioner drew a
    line in an awkward place."

    A Dropwizard module's `server.applicationContextPath` is part of the URL every
    JAX-RS route in that module is served at, so it prefixes the route (`context_path`).
    """
    routes: List[Dict] = []
    gaps: List[Dict] = []
    contexts = _context_paths(extraction, constants)

    for edge in expand_routes(extraction):
        if edge["channel"] != "http_in" or not edge["target"].startswith("route:"):
            continue
        raw = edge["target"][len("route:") :]
        verb, _, path = raw.partition(" ")
        if not path:
            verb, path = "ANY", raw

        anchors = [edge["anchor"]]
        resolved_path, used, missing = expand_placeholders(path, constants, module=edge["module"])
        anchors.extend(used)
        record = {
            "verb": verb,
            "route": resolved_path,
            "symbolic": path if missing or path != resolved_path else None,
            "handler": edge["source"],
            "module": edge["module"],
            "file": edge["file"],
            "evidence": anchors,
        }
        ctx = contexts.get(edge["module"]) if edge["file"].endswith((".java", ".scala")) else None
        if ctx and not missing:
            prefix, anchor = ctx
            record["route"] = prefix.rstrip("/") + ("/" + resolved_path.lstrip("/") if resolved_path.strip("/") else "")
            record["context_path"] = prefix
            anchors.append(anchor)
        if missing:
            record["unresolved_constants"] = sorted(set(missing))
            gaps.append(record)
        else:
            routes.append(record)

    routes.sort(key=lambda r: (r["route"], r["verb"], r["file"]))
    gaps.sort(key=lambda r: (r["route"], r["verb"], r["file"]))
    return routes, gaps


# ------------------------------------------------------------------ config


def config_reads(extraction: Dict, constants: Dict[str, Dict], wrapped: Sequence[Dict] = ()) -> List[Dict]:
    """Every read of a config key or environment variable, one row per site:
    `{key, by, file, module, anchor, symbolic?, dynamic?}`.

    A key written as a constant of another file (`config:${Env.HOME_KEY}`) is
    resolved through the constant table, recursively; one that cannot be
    resolved is reported under `config:(dynamic)` with `symbolic` kept, so the
    read is counted and cited, never dropped. Declarations (`config-file:`
    sources) are not reads."""
    out: List[Dict] = []
    for edge in [*all_edges(extraction), *wrapped]:
        if edge["channel"] != "config_read" or not edge["target"].startswith("config:"):
            continue
        if edge["source"].startswith("config-file:"):
            continue
        key = edge["target"][len("config:") :]
        row = {"key": key, "by": edge["source"], "file": edge["file"], "module": edge["module"],
               "anchor": edge["anchor"]}
        for tag in ("provider", "wrapper"):
            if edge.get(tag):
                row[tag] = edge[tag]
        if "${" in key:
            value, used, missing = expand_placeholders(key, constants, module=edge["module"])
            row["symbolic"] = key
            if missing:
                row["key"] = "(dynamic)"
            else:
                row["key"] = value
                row["via"] = used[:1]
        out.append(row)
    return out


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
                "scheduled", "message_listener", "main", "deployable",
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
