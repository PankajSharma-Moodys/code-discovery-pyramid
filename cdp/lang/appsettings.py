"""`appsettings*.json`: the keys a .NET service's `IConfiguration` reads, declared.

.NET flattens nested JSON into `Section:Key` (arrays into `Section:0`), which is the spelling
`cfg["A:B"]`/`GetValue("A:B")` uses, so every leaf becomes `config:A:B` -- a `config_key` define
(with its literal value) and a `config_read` edge from `config-file:<path>`, exactly as YAML and
properties files do. Comments and trailing commas (accepted by .NET) are tolerated.
"""

from __future__ import annotations

import json
import re
from typing import Dict, Iterator, List, Optional, Tuple

from .base import ExtractContext, Extractor, FileFacts, anchor_at, count_loc, mk_define, mk_edge

NAME_RE = re.compile(r"^appsettings(\.[\w.-]+)?\.json$", re.I)
KEY_LINE = re.compile(r'"((?:[^"\\]|\\.)*)"\s*:')


def _strip_comments(text: str) -> str:
    out: List[str] = []
    i, n, quote = 0, len(text), False
    while i < n:
        ch = text[i]
        if quote:
            out.append(ch)
            if ch == "\\" and i + 1 < n:
                out.append(text[i + 1])
                i += 1
            elif ch == '"':
                quote = False
        elif ch == '"':
            quote = True
            out.append(ch)
        elif text.startswith("//", i):
            while i < n and text[i] != "\n":
                i += 1
            continue
        elif text.startswith("/*", i):
            end = text.find("*/", i + 2)
            i = n if end < 0 else end + 2
            continue
        else:
            out.append(ch)
        i += 1
    return re.sub(r",(\s*[}\]])", r"\1", "".join(out))


def _leaves(node, prefix: str = "") -> Iterator[Tuple[str, Optional[str]]]:
    if isinstance(node, dict):
        for k, v in node.items():
            yield from _leaves(v, prefix + ":" + k if prefix else k)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _leaves(v, "%s:%d" % (prefix, i))
    elif prefix:
        yield prefix, None if node is None else (str(node).lower() if isinstance(node, bool) else str(node))


def _line_of(lines: List[str], path: List[str], start: int) -> int:
    """0-based line of the last key of `path`, searching forward from `start`."""
    want = path[-1]
    for i in range(start, len(lines)):
        if any(m.group(1) == want for m in KEY_LINE.finditer(lines[i])):
            return i
    return -1


class AppSettingsExtractor(Extractor):
    language = "config"
    role = "config"
    names = ()
    extensions = ()

    def matches(self, path: str) -> bool:
        return bool(NAME_RE.match(path.rsplit("/", 1)[-1]))

    def extract(self, ctx: ExtractContext) -> FileFacts:
        facts = FileFacts(path=ctx.path, language=self.language, loc=count_loc(ctx.lines))
        try:
            data = json.loads(_strip_comments("\n".join(ctx.lines)).lstrip("﻿"))
        except ValueError:
            return facts
        owner = "config-file:" + ctx.path
        cursor = 0
        seen = set()
        for key, value in _leaves(data):
            parts = key.split(":")
            while len(parts) > 1 and parts[-1].isdigit():
                parts = parts[:-1]      # a list item has no key of its own: cite the list's
            line = _line_of(ctx.lines, parts, cursor)
            if line < 0:
                line = _line_of(ctx.lines, parts, 0)
            if line < 0:
                continue
            cursor = line
            anchor = anchor_at(ctx, line)
            if anchor is None or key in seen:
                continue
            seen.add(key)
            facts.defines.append(mk_define("config:" + key, "config_key", "public", anchor,
                                           value=(value or "")[:200] or None))
            facts.io_edges.append(mk_edge(owner, "config:" + key, "config_read", anchor))
        return facts
