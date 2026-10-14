"""JavaScript / TypeScript extractor.

Lexical, not a parser (`web_scan`): top-level declarations and members of top-level classes
(`web_decl`), then framework and body facts (`web_flow`): outbound HTTP through in-file
wrappers, React Router `ui_route`, Pusher subscriptions, cross-module calls. Symbols declared
inside closures or produced by factories are not seen.
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
)
from .web_decl import declarations
from .web_flow import Source, http_calls, module_calls, pusher_events, routes
from .web_scan import scan

IMPORT_RE = re.compile(
    r"""^\s*(?:import\b[\s\S]*?from\s*|export\s+(?:\*|\{[^}]*\})\s*from\s*)['"]([^'"]+)['"]"""
)
BARE_IMPORT_RE = re.compile(r"""^\s*import\s*['"]([^'"]+)['"]""")
REQUIRE_RE = re.compile(r"""require\s*\(\s*['"]([^'"]+)['"]\s*\)""")
ROUTE_RE = re.compile(
    r"""\b(?:app|router|server|api|fastify)\s*\.\s*(get|post|put|delete|patch|all|use)\s*\(\s*['"`]([^'"`]+)['"`]"""
)
NEST_ROUTE_RE = re.compile(r"""^\s*@(Get|Post|Put|Delete|Patch|Controller)\s*\(\s*['"`]?([^'"`)]*)""")
ENV_RE = re.compile(r"process\.env\.([A-Za-z_][\w]*)|process\.env\[['\"]([A-Za-z_][\w]*)['\"]\]")


def _is_test_path(path: str) -> bool:
    from . import _TEST_PATTERNS   # lang/__init__ imports this module, so import it lazily
    return any(p.search(path) for p in _TEST_PATTERNS)


class WebExtractor(Extractor):
    language = "javascript"
    extensions = (".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".mts", ".cts")

    def extract(self, ctx: ExtractContext) -> FileFacts:
        lines = ctx.lines
        code, stacks, _balanced = scan(lines)
        language = "typescript" if ctx.path.rsplit(".", 1)[-1].startswith(("ts", "mts", "cts")) else "javascript"
        facts = FileFacts(path=ctx.path, language=language, loc=count_loc(lines))
        facts.package = ctx.path.rsplit(".", 1)[0]
        primary = facts.package
        facts.primary = primary

        for d in declarations(code, stacks):
            anchor = anchor_at(ctx, d["line"])
            if anchor:
                fqn = primary + "." + (d["cls"] + "." if d["cls"] else "") + d["name"]
                facts.defines.append(mk_define(fqn, d["kind"], d["vis"], anchor, value=d["value"],
                                               end_line=d["end"] + 1))

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

        src = Source(code, stacks)
        decls = declarations(code, stacks)
        for call in http_calls(src, decls, primary):
            anchor = anchor_at(ctx, call["line"])
            if anchor:
                target = "http:%s%s" % (call["verb"] + " " if call["verb"] else "", call["url"])
                facts.io_edges.append(mk_edge(call["source"], target, "http_out", anchor))
        for call in module_calls(src, decls, primary, lambda spec: _normalise_relative(ctx.path, spec)):
            anchor = anchor_at(ctx, call["line"])
            if not anchor:
                continue
            if call["name"] is None:                       # named function import: module.fn
                fqn = "%s.%s" % (call["module"], call["exported"])
            else:
                fqn = "%s.%s#%s" % (call["module"], call["cls"], call["name"]) if call["cls"] \
                    else "%s.%s" % (call["module"], call["name"])
            row = mk_use(fqn, anchor, via_import=False, resolved="external")
            row.update({"kind": "call", "from_symbol": call["from"], "speculative": False, "how": "call"})
            facts.uses.append(row)
        for rt in ([] if _is_test_path(ctx.path) else routes(src)):   # a test's <Route> is not the app's route
            anchor = anchor_at(ctx, rt["line"])
            if anchor:
                facts.io_edges.append(mk_edge(primary, "ui_route:" + rt["path"], "ui_route", anchor))
        for ev in pusher_events(src, decls, primary):
            anchor = anchor_at(ctx, ev["line"])
            if anchor:
                facts.io_edges.append(mk_edge(ev["source"], "event:" + ev["event"], "event_subscribe", anchor))
                facts.signals.append("event_subscriber")

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
