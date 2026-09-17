"""Scala extractor (F2, `PHASE/FINDINGS.md` / `PHASE/TARGET.md` T1).

Deliberately lighter than `csharp.py`: the 73 `.scala` files sampled in
$TARGET_REPO are Flyway-style DB migrations and an SDK/service layer, with no
evidence anywhere in that sample of a Scala web framework (no akka-http/play
route shapes). Inventing framework-specific `io_edges` with nothing in the
real corpus to justify them would be exactly the "close a number gap, not a
real demand" mistake `RESEARCH_GRAPHIFY.md` §9 warns against -- so this
extractor stays structural: package, imports, and type declarations, plus
whatever `channel_for_import`'s shared hint table already recognises.

Self-contained: depends only on `cdp/lang/base.py`, never on `java.py` or
`csharp.py`.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

from .base import (
    ExtractContext,
    Extractor,
    FileFacts,
    anchor_at,
    channel_for_import,
    count_loc,
    is_third_party,
    mask_string_literals,
    mk_define,
    mk_edge,
    mk_use,
    strip_block_comments,
)

PACKAGE_RE = re.compile(r"^\s*package\s+([A-Za-z_][\w.]*)\s*\{?\s*$")
IMPORT_MULTI_RE = re.compile(r"^\s*import\s+([A-Za-z_][\w.]*)\.\{([^}]*)\}\s*$")
IMPORT_WILDCARD_RE = re.compile(r"^\s*import\s+([A-Za-z_][\w.]*)\._\s*$")
IMPORT_SINGLE_RE = re.compile(r"^\s*import\s+([A-Za-z_][\w.]*)\s*$")
TYPE_RE = re.compile(
    r"^\s*(?:(private|protected)(?:\[[\w.]+\])?\s+)?"
    r"(?:(?:abstract|final|sealed|case|implicit)\s+)*"
    r"(class|object|trait)\s+([A-Za-z_]\w*)"
)


class ScalaExtractor(Extractor):
    language = "scala"
    extensions = (".scala",)

    def extract(self, ctx: ExtractContext) -> FileFacts:
        lines = ctx.lines
        code = strip_block_comments(lines)
        facts = FileFacts(path=ctx.path, language=self.language, loc=count_loc(lines))

        facts.package = _read_package(code)
        pkg = facts.package or ""
        _read_imports(ctx, code, facts)
        decls = _read_declarations(ctx, code, pkg, facts)

        primary = decls[0]["fqn"] if decls else (pkg + "." + _stem(ctx.path) if pkg else _stem(ctx.path))
        facts.primary = primary

        _emit_import_edges(facts)

        facts.signals = sorted(set(facts.signals))
        return facts


def _stem(path: str) -> str:
    return path.rsplit("/", 1)[-1].rsplit(".", 1)[0]


def _read_package(code: List[str]) -> Optional[str]:
    for line in code[:40]:
        m = PACKAGE_RE.match(line)
        if m:
            return m.group(1)
    return None


def _read_imports(ctx: ExtractContext, code: List[str], facts: FileFacts) -> None:
    imports: List[Dict] = []
    for idx, line in enumerate(code):
        fqns: List[str] = []
        m = IMPORT_MULTI_RE.match(line)
        if m:
            base = m.group(1)
            for member in m.group(2).split(","):
                member = member.strip().split("=>")[0].strip()
                if member and member != "_":
                    fqns.append(base + "." + member)
        else:
            m = IMPORT_WILDCARD_RE.match(line)
            if m:
                fqns.append(m.group(1))
            else:
                m = IMPORT_SINGLE_RE.match(line)
                if m:
                    fqns.append(m.group(1))
        if not fqns:
            continue
        anchor = anchor_at(ctx, idx)
        if anchor is None:
            continue
        for fqn in fqns:
            imports.append({"fqn": fqn, "line": idx + 1, "anchor": anchor})
            resolved = "third_party" if is_third_party(fqn) else "external"
            facts.uses.append(mk_use(fqn, anchor, via_import=True, resolved=resolved))
    facts.imports = imports


def _read_declarations(ctx: ExtractContext, code: List[str], pkg: str, facts: FileFacts) -> List[Dict]:
    """Brace-depth nested, `pending`-until-opened the same way `csharp.py`
    does -- Scala mixes same-line (`class Foo extends Bar {`) and
    next-line-brace styles across the sampled corpus, so the declaration
    isn't pushed onto the nesting stack until its own opening brace is
    actually seen, rather than assuming either style."""
    masked = [mask_string_literals(line) for line in code]
    decls: List[Dict] = []
    stack: List[Tuple[str, int]] = []
    pending: Optional[str] = None
    pending_since = -1
    depth = 0
    # `case class CatalogDetails(...)` is frequently bodyless (no trailing
    # `{`), and its parameter list commonly wraps across several lines in
    # this corpus -- bounded the same way `csharp.py`'s record handling is.
    PENDING_MAX_LINES = 15

    for idx, line in enumerate(code):
        m = TYPE_RE.match(line)
        if m:
            pending = None  # previous pending never opened -- bodyless, drop it
            visibility = m.group(1) or "public"
            kind = m.group(2)
            name = m.group(3)
            outer = stack[-1][0] if stack else None
            fqn = (outer + "." + name) if outer else ((pkg + "." + name) if pkg else name)
            anchor = anchor_at(ctx, idx)
            if anchor is not None:
                decls.append({"fqn": fqn, "kind": kind, "visibility": visibility,
                              "anchor": anchor, "index": idx, "name": name})
                facts.defines.append(mk_define(fqn, kind, visibility, anchor))
            pending = fqn
            pending_since = idx
        elif pending is not None and idx - pending_since > PENDING_MAX_LINES:
            pending = None

        opens = masked[idx].count("{")
        closes = masked[idx].count("}")
        if pending is not None and opens > 0:
            stack.append((pending, depth))
            pending = None
        depth += opens - closes
        while stack and depth <= stack[-1][1]:
            stack.pop()

    decls.sort(key=lambda d: d["index"])
    return decls


def _emit_import_edges(facts: FileFacts) -> None:
    seen = set()
    for row in facts.imports:
        channel = channel_for_import(row["fqn"])
        if channel is None or channel in seen:
            continue
        seen.add(channel)
        parts = row["fqn"].split(".")
        root = ".".join(parts[:3]) if len(parts) >= 3 else row["fqn"]
        facts.io_edges.append(mk_edge(facts.primary, "library:" + root, channel, row["anchor"]))
