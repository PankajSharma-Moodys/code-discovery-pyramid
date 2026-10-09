"""Human-readable rendering of a query result."""

from __future__ import annotations

from typing import Dict, List

from ..util import truncate
from .common import _claim_lines, _more, cite


def render(result: Dict) -> str:
    """Text rendering of a result that has *already* been budgeted.

    Truncation happens in exactly one place — `Budget.take`, inside the query —
    so this function renders every row it is handed. An earlier version also cut
    here, with smaller and unrelated constants (`defines[:40]` in the JSON,
    `[:20]` on screen), which meant `--json` and the text output disagreed about
    what the answer was and neither said so.
    """
    kind = result.get("query")
    lines: List[str] = []

    if kind == "symbol":
        if not result["found"]:
            lines.append("No symbol matching %r. Try `search %s`."
                         % (result["name"], result["name"]))
        for entry in result["found"]:
            lines.append("%s  [%s %s]" % (entry["fqn"], entry["visibility"], entry["kind"]))
            if entry.get("value") is not None:
                lines.append("  value: %r" % entry["value"])
            lines.append("  defined in %s at %s" % (", ".join(entry["modules"]), ", ".join(entry["defined_at"])))
            if entry["collision"]:
                lines.append("  ! declared at more than one site; no winner is picked (§6.4)")
            lines.append("  used by %d site(s)" % entry["used_by_count"])
            for use in entry["used_by"]:
                lines.append("    %-24s %s" % (use["module"], use["at"]))
            if entry["used_by_count"] > len(entry["used_by"]):
                lines.append("    ... %d more (elided by the budget)"
                             % (entry["used_by_count"] - len(entry["used_by"])))
            for claim in entry["claims"]:
                lines.extend(_claim_lines(claim))
            lines.append("")

    elif kind == "file":
        if not result["found"]:
            lines.append("No file matching %r." % result["path"])
        for entry in result["found"]:
            lines.append("%s" % entry["path"])
            lines.append(
                "  module %s | node %s | %s | %s | %d loc"
                % (entry["module"], entry["node"], entry["language"], entry["role"], entry["loc"])
            )
            if entry.get("package"):
                lines.append("  package %s" % entry["package"])
            if entry["signals"]:
                lines.append("  signals: %s" % ", ".join(entry["signals"]))
            if entry["defines"]:
                lines.append("  defines:")
                for d in entry["defines"]:
                    if d.get("name"):
                        end = d.get("end_line")
                        span = "%s-%s" % (d["line"], end) if end and end != d["line"] else str(d["line"])
                        lines.append("    L%-9s %-9s %-9s %s" % (
                            span, d.get("visibility") or "", d["kind"], d["name"]))
                    else:
                        lines.append("    %-9s %-60s %s" % (d["kind"], truncate(d["fqn"], 60), d["at"]))
                lines.extend(_more("    ", entry["defines_count"], entry["defines"]))
            if entry["io_edges"]:
                lines.append("  edges:")
                for e in entry["io_edges"]:
                    lines.append("    %-16s %-50s %s" % (e["channel"], truncate(e["target"], 50), e["at"]))
                lines.extend(_more("    ", entry["io_edges_count"], entry["io_edges"]))
            for claim in entry["claims"]:
                lines.extend(_claim_lines(claim))
            lines.append("")

    elif kind == "module":
        if not result["found"]:
            lines.append("No module matching %r." % result["name"])
        for entry in result["found"]:
            lines.append("%s  (%d files, %d loc%s)" % (
                entry["name"], entry["files"], entry["loc"],
                ", %d on disk" % entry["on_disk"] if entry.get("on_disk") else ""))
            if entry["generated_suspect"]:
                lines.append("  ! generated at build time; described by contract, not read (§6.7)")
            lines.append("  languages: %s" % ", ".join("%s %d" % kv for kv in entry["by_language"].items()))
            lines.append("  depends on:   %s" % (", ".join(
                "%s(%d)" % (d["module"], d["weight"]) for d in entry["depends_on"]) or "-"))
            lines.append("  depended on:  %s" % (", ".join(
                "%s(%d)" % (d["module"], d["weight"]) for d in entry["depended_on_by"]) or "-"))
            if entry["declared_only"]:
                lines.append("  ! declared but never imported: %s" % ", ".join(entry["declared_only"]))
            if entry["observed_only"]:
                lines.append("  ! imported but not declared: %s" % ", ".join(entry["observed_only"]))
            lines.append("  scopes: %s" % ", ".join(entry["scopes"]))
            lines.append("  claims: %s" % ", ".join("%s %d" % kv for kv in entry["claims_by_kind"].items()))
            for claim in entry["claims"]:
                lines.extend(_claim_lines(claim))
            lines.extend(_more("  ", entry["claims_count"], entry["claims"]))
            lines.append("")

    elif kind == "routes":
        lines.append("%d route(s)" % result["count"])
        lines.extend(_more("  ", result["count"], result["routes"]))
        for r in result["routes"]:
            note = ""
            if r["unresolved_constants"]:
                note = "  ! constant unresolved: " + ", ".join(r["unresolved_constants"])
            elif r["declared_via"]:
                note = "  (declared as %s)" % r["declared_via"]
            lines.append("  %-7s %-40s %s" % (r["verb"], r["route"], r["handler"].rsplit(".", 1)[-1]))
            lines.append("          %s%s" % (" ".join(r["evidence"]), note))

    elif kind == "table":
        lines.append("%d table(s)" % result["count"])
        lines.extend(_more("  ", result["count"], result["tables"]))
        for t in result["tables"]:
            lines.append("  %s" % t["table"])
            lines.append("    schema owned by: %s" % (", ".join(t["schema_owned_by"]) or "(no migration found)"))
            if t["migrations"]:
                lines.append("    migrations: %s" % " ".join(t["migrations"]))
                lines.extend(_more("    ", t["migration_count"], t["migrations"]))
            if t["written_by"]:
                lines.append("    written by: %s" % ", ".join(s.rsplit(".", 1)[-1] for s in t["written_by"]))
            if t["read_by"]:
                lines.append("    read by:    %s" % ", ".join(s.rsplit(".", 1)[-1] for s in t["read_by"]))
            if t["evidence"]:
                lines.append("    %s" % " ".join(t["evidence"]))
                lines.extend(_more("    ", t["evidence_count"], t["evidence"]))

    elif kind == "config":
        lines.append("%d config key(s)" % result["count"])
        lines.extend(_more("  ", result["count"], result["keys"]))
        for c in result["keys"]:
            lines.append("  %s%s" % (c["key"], "  = %r" % c["values"][0] if c["values"] else ""))
            if c["declared"]:
                lines.append("    declared: %s" % " ".join(c["declared"]))
                lines.extend(_more("    ", c["declared_count"], c["declared"]))
            for r in c["read"]:
                lines.append("    read by %-50s %s" % (truncate(r["by"], 50), r["at"]))
            lines.extend(_more("    ", c["read_count"], c["read"]))

    elif kind == "paths":
        lines.append("%d traced path(s)" % result["count"])
        lines.extend(_more("  ", result["count"], result["paths"]))
        for p in result["paths"]:
            lines.append("  %s   [%s]" % (p["trigger"], p["confidence"]))
            for h in p["hops"]:
                lines.append("    --%s--> %-40s %s" % (h["channel"], h["to"], h["at"]))
            if p["representation_chain"]:
                lines.append("    representations: %s" % " -> ".join(
                    r.rsplit(".", 1)[-1] for r in p["representation_chain"]))

    elif kind == "trace":
        if not result["found"]:
            lines.append("No trace for %r." % result["entry"])
            lines.append("  %s" % result["why"])
        else:
            r = result["resolved_as"]
            lines.append("entry  %s   [%s]" % (r["label"], r["channel"]))
            lines.append("       %s  %s" % (r["node"], r.get("at") or "-"))
            lines.append("")
            lines.append("read %d of %d cited file(s):" % (len(result["files"]), result["file_count"]))
            for row in result["files"]:
                lines.append("  %s" % row["at"] or row["file"])
                lines.append("      %s  [%s]" % (row["why"], row["confidence"]))
            lines.extend(_more("  ", result["file_count"], result["files"]))
            lines.append("")
            lines.append("  %s" % result["trail"])
            if result["hops_exhausted"]:
                lines.append("")
                lines.append("  ! the walk stopped at --max-hops %d with the frontier still "
                             "open; the trail continues beyond this list."
                             % result["max_hops"])
            if result["unknowns"]:
                lines.append("")
                lines.append("unknowns on this path:")
                for u in result["unknowns"]:
                    lines.append("  %s" % u["question"])
            lines.append("")
            lines.append(result["caveat"])

    elif kind == "search":
        counts = result["counts"]
        if result["symbols"]:
            lines.append("symbols:")
            lines += ["  " + s for s in result["symbols"]]
            lines.extend(_more("  ", counts["symbols"], result["symbols"]))
        if result["files"]:
            lines.append("files:")
            lines += ["  " + f for f in result["files"]]
            lines.extend(_more("  ", counts["files"], result["files"]))
        if result["claims"]:
            lines.append("claims:")
            for claim in result["claims"]:
                lines.extend(_claim_lines(claim))
            lines.extend(_more("  ", counts["claims"], result["claims"]))
        if result["unknowns"]:
            lines.append("unknowns:")
            for u in result["unknowns"]:
                lines.append("  %s" % u["question"])
            lines.extend(_more("  ", counts["unknowns"], result["unknowns"]))
        if not lines:
            lines.append("Nothing matched %r." % result["text"])

    elif kind == "claims":
        lines.append("%d claim(s)" % result["count"])
        lines.extend(_more("  ", result["count"], result["claims"]))
        for claim in result["claims"]:
            lines.append("  %-12s %s" % (claim["kind"], truncate(claim["subject"], 70)))
            lines.extend(_claim_lines(claim, indent="    "))

    elif kind == "unknowns":
        lines.append("%d unknown(s) — the tribal-knowledge inventory" % result["count"])
        lines.extend(_more("  ", result["count"],
                           [r for rows in result["by_node"].values() for r in rows]))
        for node, rows in result["by_node"].items():
            lines.append("  %s" % node)
            for row in rows:
                lines.append("    %s" % row["question"])
                lines.append("      why: %s" % row["why_unresolved"])
                if row.get("needs"):
                    lines.append("      needs: %s%s" % (
                        row["needs"], " (migrated)" if row.get("needs_migrated") else ""))
                status = row.get("status", "open")
                if status != "open":
                    rb = row.get("resolved_by") or {}
                    detail = ("  resolved_by=%s (%s @ %s)" % (
                        rb.get("claim_id"), rb.get("author_kind"), rb.get("at_snapshot"))
                        if status == "resolved" else "")
                    lines.append("      status: %s%s" % (status, detail))
                if row.get("anchor"):
                    lines.append("      %s" % cite(row["anchor"]))

    elif kind == "conflicts":
        lines.append("%d conflict(s), %d near-miss(es)" % (result["count"], result["near_miss_count"]))
        lines.extend(_more("  ", result["count"], result["conflicts"]))
        lines.extend(_more("  ", result["near_miss_count"], result["near_misses"]))
        for c in result["conflicts"]:
            lines.append("  %s (%s) — %s" % (c["subject"], c["kind"], c["resolved_by"] or "CONTESTED"))
            for pos in c["positions"]:
                lines.append("    %s%s  by %s  (%d anchors)" % (
                    pos["values"], "  <-- kept" if pos["won"] else "",
                    ", ".join(pos["nodes"]), pos["evidence_count"]))
        for n in result["near_misses"]:
            lines.append("  ~ %s: %d wordings, same enums" % (n["subject"], len(n["statements"])))

    elif kind == "stats":
        c = result["census"]
        lines += [
            "repo        %s @ %s%s" % (
                result["repo"], result["head"][:12],
                "   (the build calls itself '%s')" % result["build_name"]
                if result.get("build_name") else ""),
            "census      %d tracked / %d on disk (%.1fx) [%s]"
            % (c["tracked"], c["on_disk"], c["ratio"], result["inventory_source"]),
            "modules     %d in %d scopes" % (result["modules"], result["scopes"]),
            "symbols     %d" % result["symbols"],
            "routes      %d" % result["routes"],
            "claims      %d  (%s)" % (result["claims"], ", ".join("%s %d" % kv for kv in result["claims_by_kind"].items())),
            "confidence  %s" % ", ".join("%s %d" % kv for kv in result["claims_by_confidence"].items()),
            "unknowns    %d" % result["unknowns"],
            "conflicts   %d" % result["conflicts"],
            "coverage    %.1f%% of tracked files in complete scopes"
            % (100 * result["coverage"].get("fraction", 0)),
            "graph       declared %d / observed %d inter-module edges"
            % (result["divergence"]["declared"], result["divergence"]["observed"]),
        ]
        for e in result["divergence"]["declared_not_observed"]:
            lines.append("  declared but never imported: %s -> %s" % (e["from"], e["to"]))
        for e in result["divergence"]["observed_not_declared"]:
            lines.append("  imported but not declared:   %s -> %s" % (e["from"], e["to"]))
        for row in result.get("declared_ambiguous", []):
            lines.append("  ambiguous declared dep:      %s -> '%s' (%s); no edge drawn"
                         % (row["from"], row["dep"], ", ".join(row["candidates"])))

    elif kind == "coverage":
        cov = result["coverage"]
        lines.append("coverage %d/%d tracked files (%.1f%%)"
                     % (cov.get("files_complete", 0), cov.get("files_total", 0),
                        100 * cov.get("fraction", 0)))
        if result["warning"]:
            lines.append(result["warning"])
        for node in cov.get("incomplete_nodes", []):
            lines.append("  incomplete: %s (%s)" % (node, result["nodes"].get(node, "not run")))

    else:
        lines.append(str(result))

    return "\n".join(lines).rstrip() + _footer(result)


def _footer(result: Dict) -> str:
    """`elided: N` and `as of commit X, state vY` — on every response.

    Both are mandatory (`CDP_CLI_SCOPE.md §C` item 1.3). The provenance line
    matters as much as the count: an answer with no commit attached cannot be
    checked against the tree it describes, and two answers from different
    snapshots are indistinguishable once pasted into a ticket.
    """
    parts: List[str] = [""]
    if result.get("budget_note"):
        parts.append(result["budget_note"])
    as_of = result.get("as_of") or {}
    parts.append(
        "elided: %d%s" % (
            result.get("elided", 0),
            "" if result.get("budget") is None else " (budget %d rows)" % result["budget"],
        )
    )
    parts.append(
        "as of %s@%s, state v%s"
        % (as_of.get("repo", "?"), str(as_of.get("commit", "unpinned"))[:12],
           as_of.get("state_version", 0))
    )
    return "\n" + "\n".join(parts)
