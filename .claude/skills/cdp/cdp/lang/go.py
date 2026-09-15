"""Go extractor.

Go declares its namespace in source (`package foo`) exactly as Java does, so the
§6.3 read-from-source rule applies unchanged. Visibility is derived from the
identifier's first letter, which is the language's actual rule rather than a
convention.
"""

from __future__ import annotations

import re

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

PACKAGE_RE = re.compile(r"^\s*package\s+([A-Za-z_]\w*)")
IMPORT_LINE_RE = re.compile(r"""^\s*(?:import\s+)?(?:[\w.]+\s+)?"([^"]+)"\s*$""")
IMPORT_BLOCK_RE = re.compile(r"^\s*import\s*\(")
FUNC_RE = re.compile(r"^\s*func\s+(?:\([^)]*\)\s*)?([A-Za-z_]\w*)\s*\(")
TYPE_RE = re.compile(r"^\s*type\s+([A-Za-z_]\w*)\s+(struct|interface|\w+)")
CONST_RE = re.compile(r"""^\s*(?:const\s+)?([A-Z]\w*)\s*(?:=|\s+\w+\s*=)\s*"([^"]*)"\s*$""")
ROUTE_RE = re.compile(
    r"""\.(?:HandleFunc|Handle|GET|POST|PUT|DELETE|PATCH|Get|Post|Put|Delete|Patch)\s*\(\s*"([^"]+)\""""
)
ENV_RE = re.compile(r"""os\.(?:Getenv|LookupEnv)\s*\(\s*"([^"]+)\"""")
SQL_RE = re.compile(r"""\b(INSERT\s+INTO|UPDATE|DELETE\s+FROM|SELECT\b[\s\S]{0,200}?\bFROM)\s+([\w.]+)""", re.I)


class GoExtractor(Extractor):
    language = "go"
    extensions = (".go",)

    def extract(self, ctx: ExtractContext) -> FileFacts:
        code = strip_block_comments(ctx.lines)
        facts = FileFacts(path=ctx.path, language=self.language, loc=count_loc(ctx.lines))

        pkg_dir = ctx.path.rsplit("/", 1)[0] if "/" in ctx.path else ""
        for line in code[:40]:
            m = PACKAGE_RE.match(line)
            if m:
                facts.package = m.group(1)
                break
        primary = pkg_dir or (facts.package or ctx.path)
        facts.primary = primary

        in_block = False
        seen_channels = set()
        for idx, line in enumerate(code):
            if IMPORT_BLOCK_RE.match(line):
                in_block = True
                continue
            if in_block and line.strip() == ")":
                in_block = False
                continue
            m = IMPORT_LINE_RE.match(line)
            if m and (in_block or line.lstrip().startswith("import")):
                anchor = anchor_at(ctx, idx)
                if anchor:
                    spec = m.group(1)
                    facts.imports.append({"fqn": spec, "line": idx + 1, "static": False, "anchor": anchor})
                    facts.uses.append(mk_use(spec, anchor, via_import=True, resolved="external"))
                    channel = channel_for_import(spec)
                    if channel and channel not in seen_channels:
                        seen_channels.add(channel)
                        facts.io_edges.append(mk_edge(primary, "library:" + spec, channel, anchor))
                continue

            m = TYPE_RE.match(line)
            if m:
                anchor = anchor_at(ctx, idx)
                if anchor:
                    kind = "interface" if m.group(2) == "interface" else "class"
                    facts.defines.append(
                        mk_define(primary + "." + m.group(1), kind, _vis(m.group(1)), anchor)
                    )
                continue

            m = FUNC_RE.match(line)
            if m:
                anchor = anchor_at(ctx, idx)
                if anchor:
                    facts.defines.append(
                        mk_define(primary + "#" + m.group(1), "method", _vis(m.group(1)), anchor)
                    )
                if m.group(1) == "main":
                    anchor = anchor_at(ctx, idx)
                    if anchor:
                        facts.signals.append("main")
                        facts.io_edges.append(
                            mk_edge(primary, "process:" + primary, "process_boundary", anchor)
                        )
                continue

            m = CONST_RE.match(line)
            if m:
                anchor = anchor_at(ctx, idx)
                if anchor:
                    facts.defines.append(
                        mk_define(primary + "." + m.group(1), "constant", _vis(m.group(1)),
                                  anchor, value=m.group(2))
                    )

            for route in ROUTE_RE.findall(line):
                anchor = anchor_at(ctx, idx)
                if anchor:
                    facts.signals.append("http_resource")
                    facts.io_edges.append(mk_edge(primary, "route:ANY " + route, "http_in", anchor))
            for key in ENV_RE.findall(line):
                anchor = anchor_at(ctx, idx)
                if anchor:
                    facts.io_edges.append(mk_edge(primary, "config:" + key, "config_read", anchor))
            m = SQL_RE.search(line)
            if m:
                anchor = anchor_at(ctx, idx)
                if anchor:
                    channel = "read" if m.group(1).upper().startswith("SELECT") else "persist"
                    facts.io_edges.append(mk_edge(primary, "table:" + m.group(2), channel, anchor))

        facts.signals = sorted(set(facts.signals))
        return facts


def _vis(name: str) -> str:
    return "public" if name[:1].isupper() else "internal"
