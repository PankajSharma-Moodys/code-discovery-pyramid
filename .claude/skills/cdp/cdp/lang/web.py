"""JavaScript / TypeScript extractor.

Regex-based, and honest about it: JS has no cheap stdlib parser, and a
hand-rolled one would be a larger correctness risk than the recall it buys.
The consequence is stated rather than hidden — this extractor finds top-level
declarations and framework signals, and will miss symbols declared inside
closures or produced by higher-order factories. Those become `unknowns[]`
entries at the leaf, which is the designed outcome for a gap in the detectors.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional

from .base import (
    ExtractContext,
    Extractor,
    FileFacts,
    anchor_at,
    channel_for_import,
    count_loc,
    mk_define,
    mk_edge,
    mk_use,
    strip_block_comments,
)

IMPORT_RE = re.compile(
    r"""^\s*(?:import\b[\s\S]*?from\s*|export\s+(?:\*|\{[^}]*\})\s*from\s*)['"]([^'"]+)['"]"""
)
BARE_IMPORT_RE = re.compile(r"""^\s*import\s*['"]([^'"]+)['"]""")
REQUIRE_RE = re.compile(r"""require\s*\(\s*['"]([^'"]+)['"]\s*\)""")
DECL_RE = re.compile(
    r"^\s*(export\s+(?:default\s+)?)?"
    r"(?:declare\s+)?(?:abstract\s+)?"
    r"(class|interface|enum|type|function|const|let|var)\s+"
    r"([A-Za-z_$][\w$]*)"
)
ROUTE_RE = re.compile(
    r"""\b(?:app|router|server|api|fastify)\s*\.\s*(get|post|put|delete|patch|all|use)\s*\(\s*['"`]([^'"`]+)['"`]"""
)
NEST_ROUTE_RE = re.compile(r"""^\s*@(Get|Post|Put|Delete|Patch|Controller)\s*\(\s*['"`]?([^'"`)]*)""")
ENV_RE = re.compile(r"process\.env\.([A-Za-z_][\w]*)|process\.env\[['\"]([A-Za-z_][\w]*)['\"]\]")
FETCH_RE = re.compile(r"""\b(?:fetch|axios(?:\.\w+)?|got|superagent)\s*\(\s*['"`]([^'"`]*)""")


class WebExtractor(Extractor):
    language = "javascript"
    extensions = (".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".mts", ".cts")

    def extract(self, ctx: ExtractContext) -> FileFacts:
        lines = ctx.lines
        code = strip_block_comments(lines)
        language = "typescript" if ctx.path.rsplit(".", 1)[-1].startswith(("ts", "mts", "cts")) else "javascript"
        facts = FileFacts(path=ctx.path, language=language, loc=count_loc(lines))
        facts.package = ctx.path.rsplit(".", 1)[0]
        primary = facts.package
        facts.primary = primary

        seen_channels = set()
        controller_base = ""
        for idx, line in enumerate(code):
            for regex in (IMPORT_RE, BARE_IMPORT_RE):
                m = regex.match(line)
                if m:
                    _add_import(ctx, facts, idx, m.group(1), primary, seen_channels)
                    break
            for spec in REQUIRE_RE.findall(line):
                _add_import(ctx, facts, idx, spec, primary, seen_channels)

            m = DECL_RE.match(line)
            if m:
                exported = bool(m.group(1))
                kind = {"function": "method", "const": "constant", "let": "field",
                        "var": "field", "type": "class"}.get(m.group(2), m.group(2))
                anchor = anchor_at(ctx, idx)
                if anchor:
                    facts.defines.append(
                        mk_define(primary + "." + m.group(3), kind,
                                  "public" if exported else "internal", anchor)
                    )

            m = NEST_ROUTE_RE.match(line)
            if m:
                anchor = anchor_at(ctx, idx)
                if anchor:
                    if m.group(1) == "Controller":
                        controller_base = "/" + m.group(2).strip("/")
                    else:
                        route = (controller_base.rstrip("/") + "/" + m.group(2).strip("/")).rstrip("/") or "/"
                        facts.signals.append("http_resource")
                        facts.io_edges.append(
                            mk_edge(primary, "route:%s %s" % (m.group(1).upper(), route), "http_in", anchor)
                        )

            for verb, route in ROUTE_RE.findall(line):
                if verb == "use":
                    continue
                anchor = anchor_at(ctx, idx)
                if anchor:
                    facts.signals.append("http_resource")
                    facts.io_edges.append(
                        mk_edge(primary, "route:%s %s" % (verb.upper(), route), "http_in", anchor)
                    )

            for a, b in ENV_RE.findall(line):
                key = a or b
                anchor = anchor_at(ctx, idx)
                if anchor:
                    facts.io_edges.append(mk_edge(primary, "config:" + key, "config_read", anchor))

            for url in FETCH_RE.findall(line):
                anchor = anchor_at(ctx, idx)
                if anchor:
                    facts.io_edges.append(
                        mk_edge(primary, "http:" + (url or "(dynamic)"), "http_out", anchor)
                    )

        facts.signals = sorted(set(facts.signals))
        facts.io_edges = _dedupe_edges(facts.io_edges)
        return facts


def _add_import(
    ctx: ExtractContext, facts: FileFacts, idx: int, spec: str, primary: str, seen: set
) -> None:
    anchor = anchor_at(ctx, idx)
    if anchor is None:
        return
    relative = spec.startswith(".")
    fqn = _normalise_relative(ctx.path, spec) if relative else spec
    facts.imports.append({"fqn": fqn, "line": idx + 1, "static": False, "anchor": anchor})
    facts.uses.append(
        mk_use(fqn, anchor, via_import=True, resolved="external" if relative else "third_party")
    )
    channel = channel_for_import(spec)
    if channel and channel not in seen:
        seen.add(channel)
        facts.io_edges.append(mk_edge(primary, "library:" + spec, channel, anchor))


def _normalise_relative(path: str, spec: str) -> str:
    """Turn `./foo` / `../bar/baz` into a repo-relative module id."""
    parts = path.split("/")[:-1]
    for chunk in spec.split("/"):
        if chunk in (".", ""):
            continue
        if chunk == "..":
            if parts:
                parts.pop()
        else:
            parts.append(chunk)
    return "/".join(parts)


def _dedupe_edges(edges: List[Dict]) -> List[Dict]:
    seen = set()
    out = []
    for e in edges:
        key = (e["source"], e["target"], e["channel"])
        if key in seen:
            continue
        seen.add(key)
        out.append(e)
    return out
