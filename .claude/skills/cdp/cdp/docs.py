"""Phase 8b — output artifacts (§7).

Three deliverables aimed at three consumers: markdown for humans, JSON for
machines (already written by the earlier phases), and a generated `CLAUDE.md`
for the next agent that opens the repository.

`unknowns.md` is the one to read first. RESEARCH.md calls it "arguably the
highest-value artifact: a precise list of what to ask the incumbent team before
they leave", and it is the only output whose value goes *up* when the pipeline
does badly.

Every document leads with its coverage figure. A 94%-coverage run that says 94%
is useful; the same run presented as complete is worse than no run at all,
because a map that does not mark its own holes will be trusted across them.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence

from .inventory import ROOT_MODULE
from .util import human_int, truncate, write_text


def render_all(
    out_dir: Path,
    inventory: Dict,
    extraction: Dict,
    graph: Dict,
    partition: Dict,
    xref: Dict,
    dataflow: Dict,
    state: Dict,
    manifest: Dict,
) -> List[Path]:
    out_dir = Path(out_dir)
    written = [
        write_text(out_dir / "00-overview.md",
                   _overview(inventory, extraction, graph, xref, state, manifest)),
        write_text(out_dir / "dataflow.md", _dataflow(dataflow, xref, state)),
        write_text(out_dir / "unknowns.md", _unknowns(state, xref, inventory)),
        write_text(out_dir / "CLAUDE.md", _claude_md(inventory, graph, xref, state, extraction)),
    ]
    for module in inventory["modules"]:
        if module["name"] == ROOT_MODULE:
            continue
        written.append(
            write_text(
                out_dir / "modules" / (module["name"].replace("/", "__") + ".md"),
                _module_doc(module, inventory, extraction, graph, partition, xref, state),
            )
        )
    return written


# ---------------------------------------------------------------- helpers


def _coverage_banner(state: Dict) -> str:
    cov = state.get("coverage") or {}
    fraction = cov.get("fraction", 0.0)
    if not cov.get("files_total"):
        return (
            "> **Coverage: structural only.** These documents were generated from deterministic "
            "extraction. No leaf agent has run, so nothing here states *why* anything exists.\n"
        )
    if fraction >= 0.999:
        return "> **Coverage: 100%%** — all %d tracked files sit in scopes that completed.\n" % cov["files_total"]
    return (
        "> **Coverage: %.1f%%** — %d of %d tracked files are in scopes that completed. "
        "Everything absent from this document may be absent because it was never examined. "
        "Incomplete scopes: %s.\n"
        % (100 * fraction, cov["files_complete"], cov["files_total"],
           ", ".join("`%s`" % n for n in cov.get("incomplete_nodes", [])[:8]) or "none listed")
    )


def _cite(anchor: Dict) -> str:
    return "`%s:%s`" % (anchor.get("file"), anchor.get("line"))


def _claim_bullet(claim: Dict) -> str:
    cites = " ".join(_cite(a) for a in (claim.get("evidence") or [])[:4])
    mark = ""
    if claim.get("confidence") in ("low", "contested"):
        mark = " _(%s)_" % claim["confidence"]
    return "- %s%s — %s" % (claim.get("statement", ""), mark, cites)


def _by_kind(claims: Sequence[Dict], kind: str) -> List[Dict]:
    return [c for c in claims if c.get("kind") == kind]


def _module_of_claim(claim: Dict) -> Optional[str]:
    for node in claim.get("source_nodes") or []:
        if node.startswith("root/"):
            return node.split("/")[1]
    return None


# --------------------------------------------------------------- overview


def _overview(inventory: Dict, extraction: Dict, graph: Dict, xref: Dict,
              state: Dict, manifest: Dict) -> str:
    counts = inventory["counts"]
    claims = state.get("claims", [])
    lines: List[str] = [
        "# %s — architecture overview" % inventory["repo_name"],
        "",
        "Reconstructed by CDP at commit `%s`. Every claim below carries a `file:line` citation "
        "that a Python verifier confirmed against the file." % inventory["head"][:12],
        "",
        _coverage_banner(state),
        "## Census",
        "",
        "| | |",
        "|---|---|",
        "| Tracked files | %s |" % human_int(counts["tracked"]),
        "| Files on disk | %s (**%.1fx**) |" % (human_int(counts["on_disk"]), counts["ratio"]),
        "| Inventory source | `%s` |" % inventory["source"],
        "| Modules | %d |" % len([m for m in inventory["modules"] if m["name"] != ROOT_MODULE]),
        "| Symbols declared | %s |" % human_int(len(xref["symbols"])),
        "| HTTP routes | %d |" % len(xref["routes"]),
        "",
    ]
    if counts["ratio"] >= 2:
        lines += [
            "The %.1fx ratio is a first-class fact, not a diagnostic. A filesystem walk would "
            "spend most of its budget on files that no one wrote." % counts["ratio"],
            "",
        ]

    generated = [m for m in inventory["modules"] if m.get("generated_suspect")]
    if generated:
        lines.append("### Generated modules")
        lines.append("")
        for module in generated:
            lines.append(
                "- **`%s`** — %d tracked file(s) against %d on disk. Generated at build time; "
                "described by its build contract rather than read."
                % (module["name"], module["files"], module.get("on_disk", 0))
            )
        lines.append("")

    # --- naming -----------------------------------------------------------
    naming = _by_kind(claims, "naming")
    if naming:
        lines += ["## Naming", "",
                  "The facts that cost a newcomer an afternoon and appear in no artifact.", ""]
        lines += [_claim_bullet(c) for c in naming]
        lines.append("")

    # --- deployables ------------------------------------------------------
    deployables = _by_kind(claims, "deployable")
    entrypoints = [c for c in _by_kind(claims, "entrypoint") if c.get("channel") == "process_boundary"]
    if deployables or entrypoints:
        lines += ["## Deployable units", ""]
        lines += [_claim_bullet(c) for c in deployables + entrypoints]
        lines.append("")

    # --- dependency graph -------------------------------------------------
    lines += ["## Module dependency graph", "",
              "Built twice — from build manifests (**declared**) and from import statements "
              "(**observed**) — because the divergence between them is a finding, not an error "
              "to reconcile.", ""]
    lines.append("| Source | Inter-module edges |")
    lines.append("|---|---|")
    lines.append("| Declared (build manifests) | %d |" % graph["divergence"]["declared_edges"])
    lines.append("| Observed (imports) | %d |" % graph["divergence"]["observed_edges"])
    lines.append("")

    if graph["levels"]:
        lines += ["Observed dependency levels (each depends only on those above it):", "", "```"]
        for i, layer in enumerate(graph["levels"]):
            lines.append("L%d  %s" % (i, ", ".join(layer)))
        lines += ["```", ""]

    div = graph["divergence"]
    if div["observed_not_declared"]:
        lines += ["### Imported but not declared", "",
                  "These compile by transitive resolution and will break on a dependency bump.", ""]
        lines += ["- `%s` -> `%s`" % (e["from"], e["to"]) for e in div["observed_not_declared"]]
        lines.append("")
    if div["declared_not_observed"]:
        lines += ["### Declared but never imported", "",
                  "Candidate stale dependencies. Note that a dependency on a module whose sources "
                  "are generated at build time will appear here legitimately — the imports exist, "
                  "but not in git.", ""]
        lines += ["- `%s` -> `%s`" % (e["from"], e["to"]) for e in div["declared_not_observed"]]
        lines.append("")

    if not div["observed_not_declared"] and not div["declared_not_observed"]:
        lines += ["Declared and observed graphs agree exactly. That is a good sign about this "
                  "build's hygiene and an unusual one.", ""]

    # --- module table -----------------------------------------------------
    lines += ["## Modules", "", "| Module | Files | LOC | Depends on | Depended on by |", "|---|---|---|---|---|"]
    depends: Dict[str, List[str]] = {}
    depended: Dict[str, List[str]] = {}
    for edge in graph["observed"]:
        depends.setdefault(edge["from"], []).append(edge["to"])
        depended.setdefault(edge["to"], []).append(edge["from"])
    for module in sorted(inventory["modules"], key=lambda m: -m["files"]):
        if module["name"] == ROOT_MODULE:
            continue
        lines.append(
            "| [`%s`](modules/%s.md) | %d | %s | %s | %s |"
            % (module["name"], module["name"].replace("/", "__"), module["files"],
               human_int(module["loc"]),
               ", ".join(sorted(depends.get(module["name"], []))) or "—",
               ", ".join(sorted(depended.get(module["name"], []))) or "—")
        )
    lines.append("")

    # --- HTTP surface -----------------------------------------------------
    if xref["routes"]:
        lines += ["## HTTP surface", "",
                  "| Verb | Route | Handler | Declared as | Evidence |", "|---|---|---|---|---|"]
        for route in xref["routes"]:
            lines.append(
                "| `%s` | `%s` | `%s` | %s | %s |"
                % (route["verb"], route["route"], route["handler"].rsplit(".", 1)[-1],
                   "`%s`" % route["symbolic"] if route.get("symbolic") else "literal",
                   " ".join(_cite(a) for a in route["evidence"]))
            )
        lines.append("")
    if xref["unresolved_routes"]:
        lines += ["### Routes whose path constant was not found", ""]
        for route in xref["unresolved_routes"]:
            lines.append("- `%s %s` — constant %s not defined anywhere in the repository %s"
                         % (route["verb"], route["route"],
                            ", ".join("`%s`" % c for c in route.get("unresolved_constants", [])),
                            " ".join(_cite(a) for a in route["evidence"])))
        lines.append("")

    # --- duplicate FQNs ---------------------------------------------------
    cross = [c for c in xref["collisions"] if c["cross_module"] and not _synthetic(c["fqn"])]
    if cross:
        lines += ["## Duplicate fully-qualified names across modules", "",
                  "A repository that has these usually did not intend to. The resolver records "
                  "every definition site and picks no winner.", ""]
        for collision in cross[:25]:
            lines.append("- `%s` in %s — %s"
                         % (collision["fqn"], ", ".join(collision["modules"]),
                            " ".join(_cite(s["anchor"]) for s in collision["sites"][:4])))
        lines.append("")

    conflicts = state.get("conflicts", [])
    if conflicts:
        lines += ["## Merge conflicts", "",
                  "Where two scopes disagreed on a closed-vocabulary field about the same subject. "
                  "Resolution order is ownership, then evidence count, then escalation.", ""]
        for c in conflicts[:20]:
            lines.append("- **`%s`** (%s) — %s" % (c["subject"], c["kind"], c["resolved_by"] or "**contested**"))
        lines.append("")

    lines += ["## Where to go next", "",
              "- [`unknowns.md`](unknowns.md) — what this run could not establish. Read it before "
              "trusting anything above.",
              "- [`dataflow.md`](dataflow.md) — how a record actually travels, including edges no "
              "import expresses.",
              "- `cdp query` — the same state, queryable. `query symbol DServer`, "
              "`query table server`, `query routes`, `query paths --to table:server`.",
              ""]
    return "\n".join(lines)


def _synthetic(fqn: str) -> bool:
    return fqn.split(":", 1)[0] in ("config", "table", "entity", "process", "library", "route", "port", "build")


# ----------------------------------------------------------------- module


def _module_doc(module: Dict, inventory: Dict, extraction: Dict, graph: Dict,
                partition: Dict, xref: Dict, state: Dict) -> str:
    name = module["name"]
    claims = [c for c in state.get("claims", []) if _module_of_claim(c) == name]
    scopes = [s for s in partition["scopes"] if s["module"] == name]
    node_status = state.get("nodes", {})

    lines: List[str] = [
        "# `%s`" % name,
        "",
        "%d tracked files, %s lines. Part of `%s` at commit `%s`."
        % (module["files"], human_int(module["loc"]), inventory["repo_name"], inventory["head"][:12]),
        "",
    ]

    incomplete = [s["node"] for s in scopes if node_status.get(s["node"]) not in ("complete", None)]
    never_run = [s["node"] for s in scopes if s["node"] not in node_status]
    if incomplete or never_run:
        lines += [
            "> **This module is not fully covered.** Scopes not completed: %s. Facts about the "
            "files in those scopes are missing, not absent."
            % ", ".join("`%s`" % n for n in sorted(set(incomplete + never_run))),
            "",
        ]

    if module.get("generated_suspect"):
        lines += [
            "> **Generated module.** %d tracked file(s) against %d on disk. Its sources are "
            "produced at build time and are invisible to git, so nothing below describes them."
            % (module["files"], module.get("on_disk", 0)),
            "",
        ]

    lines += ["## Dependencies", ""]
    out_edges = [e for e in graph["observed"] if e["from"] == name]
    in_edges = [e for e in graph["observed"] if e["to"] == name]
    lines.append("**Imports:** " + (", ".join("`%s` (%d refs)" % (e["to"], e["weight"]) for e in out_edges) or "nothing in this repository"))
    lines.append("")
    lines.append("**Imported by:** " + (", ".join("`%s` (%d refs)" % (e["from"], e["weight"]) for e in in_edges) or "nothing in this repository"))
    lines.append("")

    sections = [
        ("Entry points", "entrypoint"),
        ("Public API surface", "public_api"),
        ("Data models", "data_model"),
        ("Configuration", "config"),
        ("Side effects", "side_effect"),
        ("Ownership", "ownership"),
        ("What the tests reveal", "test_behaviour"),
        ("Naming", "naming"),
        ("Dependencies (stated)", "dependency"),
    ]
    for title, kind in sections:
        rows = _by_kind(claims, kind)
        if not rows:
            continue
        lines += ["## %s" % title, ""]
        lines += [_claim_bullet(c) for c in rows[:60]]
        if len(rows) > 60:
            lines.append("- _... and %d more; use `cdp query claims --kind %s --module %s`_" % (len(rows) - 60, kind, name))
        lines.append("")

    defines = [d for d in extraction["defines"]
               if d["module"] == name and d["kind"] in ("class", "interface", "enum", "record")
               and d["visibility"] == "public"]
    if defines:
        lines += ["## Public types declared here", "", "| Type | Kind | Used by | Declared at |", "|---|---|---|---|"]
        for row in sorted(defines, key=lambda d: -len(xref["used_by"].get(d["fqn"], [])))[:40]:
            users = xref["used_by"].get(row["fqn"], [])
            lines.append("| `%s` | %s | %d | %s |"
                         % (row["fqn"].rsplit(".", 1)[-1], row["kind"], len(users), _cite(row["anchor"])))
        if len(defines) > 40:
            lines.append("")
            lines.append("_%d more; use `cdp query module %s`._" % (len(defines) - 40, name))
        lines.append("")

    unknowns = [u for u in state.get("unknowns", [])
                if any(s["node"] == str(u.get("source_node")) for s in scopes)]
    if unknowns:
        lines += ["## Open questions for this module", ""]
        for row in unknowns[:40]:
            lines.append("- %s" % row["question"])
            lines.append("  - _why unresolved:_ %s" % row["why_unresolved"])
        lines.append("")

    lines += ["## Scopes", "",
              "How the partitioner cut this module, and what each leaf was authorised to read.", "",
              "| Scope | Files | LOC | Status |", "|---|---|---|---|"]
    for scope in scopes:
        lines.append("| `%s` | %d | %s | %s |"
                     % (scope["node"], scope["file_count"], human_int(scope["loc"]),
                        node_status.get(scope["node"], "structural only")))
    lines.append("")
    return "\n".join(lines)


# --------------------------------------------------------------- dataflow


def _dataflow(dataflow: Dict, xref: Dict, state: Dict) -> str:
    lines: List[str] = [
        "# Data flow",
        "",
        "How data travels through this application — the question the module dependency graph "
        "cannot answer. The topology below was walked by deterministic Python over typed channel "
        "edges; every hop carries the anchor of the edge it came from, so a hop with no evidence "
        "has nowhere to hide.",
        "",
        _coverage_banner(state),
    ]

    boundaries = dataflow.get("process_boundaries", [])
    if boundaries:
        lines += [
            "## Edges that no import expresses",
            "",
            "Modules that exchange data through shared storage. These are real data edges with "
            "zero code-level coupling; a dependency graph cannot see them, and a reader told "
            "\"a depends on b depends on c\" will not expect them.",
            "",
        ]
        # Grouped by process pair: thirteen bullets saying "api and manager both
        # touch X" is one fact reported thirteen times, and a real finding
        # buried under its own repetitions gets skimmed past.
        by_pair: Dict[str, List[Dict]] = {}
        for row in boundaries:
            by_pair.setdefault(" and ".join(row["processes"]), []).append(row)
        for pair, rows in sorted(by_pair.items()):
            names = " and ".join("`%s`" % p.rsplit(".", 1)[-1] for p in rows[0]["processes"])
            lines.append("- **%s** (modules `%s`)" % (names, "`, `".join(rows[0]["modules"])))
            shared = sorted(r["shared"] for r in rows)
            tables = [s[len("table:") :] for s in shared if s.startswith("table:")]
            entities = [s[len("entity:") :].rsplit(".", 1)[-1] for s in shared if s.startswith("entity:")]
            if tables:
                lines.append("  - tables: %s" % ", ".join("`%s`" % t for t in tables))
            if entities:
                lines.append("  - entities: %s" % ", ".join("`%s`" % e for e in entities))
            lines.append("  - %s" % " ".join(_cite(a) for a in rows[0]["evidence"][:4]))
            lines.append("  - _%s_" % rows[0]["note"])
        lines.append("")

    chains = [p for p in dataflow.get("paths", []) if p["representation_chain"]]
    if chains:
        lines += ["## Representation chains", "",
                  "Where one record exists under several names. Each hop is a mapper; the chain is "
                  "what a reader has to know before `EServer`, `DServer` and `Server` stop looking "
                  "like three different things.", ""]
        seen = set()
        for path in chains[:40]:
            key = tuple(path["representation_chain"])
            if key in seen:
                continue
            seen.add(key)
            lines.append("- %s" % " -> ".join(
                "`%s`" % r.rsplit(".", 1)[-1] for r in path["representation_chain"]))
            lines.append("  - reached from `%s` (%s)"
                         % (path["source"].rsplit(".", 1)[-1], path["trigger_channel"]))
            for hop in path["hops"]:
                if hop["channel"] == "map":
                    lines.append("  - %s" % _cite(hop["anchor"]))
        lines.append("")

    paths = dataflow.get("paths", [])
    if paths:
        lines += ["## Traced paths", "",
                  "From every entry point to every reachable sink. `call` hops are derived from the "
                  "import table: an import proves a file *can* reach a symbol, not that it does, so "
                  "any path containing one is marked medium confidence.", ""]
        for path in paths[:60]:
            lines.append("### `%s`" % path["trigger"])
            lines.append("")
            lines.append("_%s, %s confidence, modules: %s_"
                         % (path["trigger_channel"], path["min_confidence"], ", ".join(path["modules"])))
            lines.append("")
            lines.append("```")
            lines.append(path["source"])
            for hop in path["hops"]:
                lines.append("  --%s--> %s" % (hop["channel"], hop["to"]))
            lines.append("```")
            lines.append("")
            for hop in path["hops"]:
                lines.append("- `%s` --%s--> `%s` %s"
                             % (hop["from"].rsplit(".", 1)[-1], hop["channel"],
                                hop["to"].rsplit(".", 1)[-1], _cite(hop["anchor"])))
            lines.append("")
        if len(paths) > 60:
            lines.append("_%d further paths; use `cdp query paths --from X --to Y`._" % (len(paths) - 60))
            lines.append("")

    lines += ["## What is not traced", "",
              "- **Runtime dependency injection.** The object graph the application assembles at "
              "startup is decided from types, not imports. What is reported here is the *declared* "
              "wiring; the runtime graph is a superset CDP cannot see.",
              "- **Dynamic dispatch.** A call through an interface produces an edge to the "
              "interface. Implementations are candidates, not hops.",
              "- **Reflection and string-keyed lookup.** Detected as a risk marker on the "
              "containing symbol, never traced through.",
              "- **What the data means.** CDP maps where data goes, not what it is. It will not "
              "tell you whether `capacity_percent` is a fraction or a percentage.",
              ""]
    return "\n".join(lines)


# --------------------------------------------------------------- unknowns


def _unknowns(state: Dict, xref: Dict, inventory: Dict) -> str:
    unknowns = state.get("unknowns", [])
    lines: List[str] = [
        "# Unknowns — the tribal-knowledge inventory",
        "",
        "Every question this run could not answer, with the anchor that raised it. This is the "
        "list to take to the incumbent team before they leave. A gap here is *output*, not "
        "failure: the alternative is a document that asserts a plausible answer, and a reader who "
        "cannot tell the difference.",
        "",
        _coverage_banner(state),
    ]

    if not unknowns:
        lines += ["_No unknowns recorded. If no leaf agent has run yet, that means nothing was "
                  "asked, not that nothing is unknown._", ""]

    grouped: Dict[str, List[Dict]] = {}
    for row in unknowns:
        grouped.setdefault(str(row.get("source_node") or "(unattributed)"), []).append(row)
    for node in sorted(grouped):
        lines += ["## `%s`" % node, ""]
        for row in grouped[node]:
            lines.append("- **%s**" % row["question"])
            lines.append("  - _why unresolved:_ %s" % row["why_unresolved"])
            if row.get("anchor"):
                lines.append("  - %s" % _cite(row["anchor"]))
            if row.get("demoted_from"):
                lines.append("  - _demoted claim:_ `%s`" % row["demoted_from"])
        lines.append("")

    unresolved = xref.get("unresolved_routes", [])
    if unresolved:
        lines += ["## Routes with unresolved path constants", ""]
        for route in unresolved:
            lines.append("- `%s %s` — %s" % (route["verb"], route["route"],
                                             ", ".join(route.get("unresolved_constants", []))))
        lines.append("")

    candidates = xref.get("unreferenced_candidates", {})
    if candidates.get("candidate_count"):
        lines += ["## Public types with no static reference", "",
                  candidates["note"], "",
                  "%d candidate(s). These are **not** dead code; any of dependency injection, "
                  "HTTP resource registration, job discovery or generated implementations makes a "
                  "naive dead-code claim wrong." % candidates["candidate_count"], ""]
        for row in candidates["candidates"][:40]:
            site = row["sites"][0]["anchor"] if row["sites"] else None
            lines.append("- `%s` %s" % (row["fqn"], _cite(site) if site else ""))
        lines.append("")
    return "\n".join(lines)


# -------------------------------------------------------------- CLAUDE.md


def _claude_md(inventory: Dict, graph: Dict, xref: Dict, state: Dict, extraction: Dict) -> str:
    """Orientation for the next agent that opens this repository.

    There is a pleasing recursion here: CDP's most durable output is a better
    starting context for the next agent — including the next CDP run.
    """
    claims = state.get("claims", [])
    lines: List[str] = [
        "# %s" % inventory["repo_name"],
        "",
        "Generated by CDP at commit `%s`. Every fact below carries a citation; if a citation is "
        "wrong, the fact is wrong and should be removed rather than repaired from memory."
        % inventory["head"][:12],
        "",
        "## Orientation",
        "",
        "- **%d files are tracked by git; %d exist on disk (%.1fx).** Use `git ls-files`, not a "
        "filesystem walk. Most of what is on disk is build output or generated code."
        % (inventory["counts"]["tracked"], inventory["counts"]["on_disk"], inventory["counts"]["ratio"]),
    ]
    for claim in _by_kind(claims, "naming")[:6]:
        lines.append("- %s %s" % (claim["statement"], " ".join(_cite(a) for a in claim.get("evidence", [])[:2])))
    lines.append("")

    generated = [m for m in inventory["modules"] if m.get("generated_suspect")]
    if generated:
        lines += ["## Do not read these", ""]
        for module in generated:
            lines.append("- `%s` — %d tracked / %d on disk. Generated at build time."
                         % (module["name"], module["files"], module.get("on_disk", 0)))
        lines.append("")

    lines += ["## Module map", "",
              "Dependency levels from observed imports; each level depends only on those above.", "", "```"]
    for i, layer in enumerate(graph["levels"]):
        lines.append("L%d  %s" % (i, ", ".join(layer)))
    lines += ["```", ""]

    depends: Dict[str, List[str]] = {}
    for edge in graph["observed"]:
        depends.setdefault(edge["from"], []).append("%s(%d)" % (edge["to"], edge["weight"]))
    for module in sorted(inventory["modules"], key=lambda m: -m["files"]):
        if module["name"] == ROOT_MODULE:
            continue
        lines.append("- **`%s`** (%d files) -> %s"
                     % (module["name"], module["files"],
                        ", ".join(sorted(depends.get(module["name"], []))) or "no internal deps"))
    lines.append("")

    processes = [c for c in _by_kind(claims, "entrypoint") if c.get("channel") == "process_boundary"]
    if processes:
        lines += ["## Processes", ""]
        for claim in processes:
            lines.append("- %s %s" % (claim["statement"], " ".join(_cite(a) for a in claim.get("evidence", [])[:1])))
        lines.append("")

    if xref["routes"]:
        lines += ["## HTTP routes", ""]
        for route in xref["routes"]:
            lines.append("- `%s %s` -> `%s` %s"
                         % (route["verb"], route["route"], route["handler"].rsplit(".", 1)[-1],
                            " ".join(_cite(a) for a in route["evidence"][:1])))
        if any(r.get("symbolic") for r in xref["routes"]):
            lines.append("")
            lines.append("Routes are declared through constants, so grepping for a literal path "
                         "will not find its handler. Grep for the constant name instead.")
        lines.append("")

    tables = sorted({e["target"][len("table:"):] for e in extraction["io_edges"]
                     if e["target"].startswith("table:")})
    if tables:
        lines += ["## Tables", "", ", ".join("`%s`" % t for t in tables[:60]), "",
                  "Use `cdp query table <name>` for who owns the schema, who writes, and who reads.", ""]

    hot = sorted(xref["used_by"].items(), key=lambda kv: -len(kv[1]))[:12]
    if hot:
        lines += ["## Most-referenced symbols", "",
                  "Changing these has the widest blast radius.", ""]
        for fqn, users in hot:
            lines.append("- `%s` — %d references" % (fqn, len(users)))
        lines.append("")

    lines += ["## Querying this instead of grepping", "",
              "```bash",
              "cdp query stats",
              "cdp query symbol DServer          # definitions + every use, with citations",
              "cdp query table server            # schema owner, writers, readers",
              "cdp query routes                  # HTTP surface, constants resolved",
              "cdp query module <name>           # purpose, deps, entrypoints, claims",
              "cdp query paths --to table:server # how data reaches a sink",
              "cdp query unknowns                # what is NOT known",
              "```",
              "",
              "## Coverage", "", _coverage_banner(state), ""]
    return "\n".join(lines)
