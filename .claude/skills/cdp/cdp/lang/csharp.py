"""C# extractor (F2, `PHASE/FINDINGS.md` / `PHASE/TARGET.md` T1).

$TARGET_REPO is 48% C# by LOC and none of it produced a claim before this --
every `.cs` file fell through to `GenericExtractor`. Regexes here are drawn
from real files sampled in that repository (file-scoped `namespace X.Y.Z;`,
ASP.NET Core `[Route]`/`[HttpGet]` attributes, EF Core `DbContext`/`DbSet<T>`),
not written from memory of C# syntax in the abstract.

Deliberately narrower than `java.py`: DI is done there via fluent
`services.AddScoped<I,T>()` calls rather than attributes, and AutoMapper/
MediatR aren't attribute-shaped either -- none of those fit this extractor's
detection style, so they're left as real gaps a leaf turns into `unknowns[]`,
not silently invented here.

Self-contained: depends only on `cdp/lang/base.py` (the shared seam every
extractor uses), never on `java.py` or `scala.py`.
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
    first_string_literal,
    is_third_party,
    mask_string_literals,
    mk_define,
    mk_edge,
    mk_use,
    strip_block_comments,
)

NAMESPACE_RE = re.compile(r"^\s*namespace\s+([A-Za-z_][\w.]*)\s*;")
USING_RE = re.compile(r"^\s*using\s+(static\s+)?([A-Za-z_][\w.]*)\s*;\s*$")
USING_ALIAS_RE = re.compile(r"^\s*using\s+([A-Za-z_]\w*)\s*=\s*([A-Za-z_][\w.]*)\s*;\s*$")
TYPE_RE = re.compile(
    r"^\s*(?:(public|internal|private|protected)(?:\s+(?:internal|protected))?\s+)?"
    r"(?:(?:abstract|sealed|static|partial|readonly|unsafe|new)\s+)*"
    r"(class|interface|enum|struct|record)\s+([A-Za-z_]\w*)"
)
METHOD_RE = re.compile(
    r"^\s*(public)\s+"
    r"(?:(?:static|virtual|override|abstract|async|sealed|new|partial|unsafe)\s+)*"
    r"(?:<[^>]*>\s+)?"
    r"([\w<>\[\],.?\s]+?)\s+([A-Za-z_]\w*)\s*\("
)
ATTR_RE = re.compile(r"^\s*\[([A-Za-z_][\w.]*)\s*(\(.*)?\]\s*$")
DBSET_RE = re.compile(r"\bDbSet\s*<\s*([\w.]+)\s*>")
DBCONTEXT_RE = re.compile(
    r"^\s*(?:public\s+)?(?:partial\s+)?class\s+([A-Za-z_]\w*)\s*:\s*[\w.,\s<>]*\bDbContext\b"
)
MAIN_RE = re.compile(r"\bstatic\s+(?:async\s+)?(?:void|Task|int)\s+Main\s*\(")

ROUTE_VERBS = {
    "HttpGet": "GET", "HttpPost": "POST", "HttpPut": "PUT",
    "HttpDelete": "DELETE", "HttpPatch": "PATCH", "HttpHead": "HEAD",
    "HttpOptions": "OPTIONS",
}


class _Attr:
    __slots__ = ("name", "args", "index")

    def __init__(self, name: str, args: str, index: int) -> None:
        self.name = name
        self.args = args
        self.index = index


class CSharpExtractor(Extractor):
    language = "csharp"
    extensions = (".cs",)

    def extract(self, ctx: ExtractContext) -> FileFacts:
        lines = ctx.lines
        code = strip_block_comments(lines)
        facts = FileFacts(path=ctx.path, language=self.language, loc=count_loc(lines))

        facts.package = _read_namespace(code)
        ns = facts.package or ""
        _read_imports(ctx, code, facts)
        decls = _read_declarations(ctx, code, ns, facts)
        attrs = _read_attributes(code)

        primary = decls[0]["fqn"] if decls else (ns + "." + _stem(ctx.path) if ns else _stem(ctx.path))
        facts.primary = primary

        _emit_import_edges(facts)
        _emit_attribute_facts(ctx, facts, attrs, decls, primary)
        _emit_ef_core_edges(ctx, facts, code, decls, primary)
        _emit_entrypoint(ctx, facts, code, primary)

        facts.signals = sorted(set(facts.signals))
        return facts


# ------------------------------------------------------------------ readers


def _stem(path: str) -> str:
    return path.rsplit("/", 1)[-1].rsplit(".", 1)[0]


def _read_namespace(code: List[str]) -> Optional[str]:
    for line in code[:80]:
        m = NAMESPACE_RE.match(line)
        if m:
            return m.group(1)
    return None


def _read_imports(ctx: ExtractContext, code: List[str], facts: FileFacts) -> None:
    imports: List[Dict] = []
    for idx, line in enumerate(code):
        fqn = None
        m = USING_RE.match(line)
        if m:
            fqn = m.group(2)
        else:
            m = USING_ALIAS_RE.match(line)
            if m:
                fqn = m.group(2)
        if fqn is None:
            continue
        anchor = anchor_at(ctx, idx)
        if anchor is None:
            continue
        row = {"fqn": fqn, "line": idx + 1, "anchor": anchor}
        imports.append(row)
        resolved = "third_party" if is_third_party(fqn) else "external"
        facts.uses.append(mk_use(fqn, anchor, via_import=True, resolved=resolved))
    facts.imports = imports


def _read_declarations(ctx: ExtractContext, code: List[str], ns: str, facts: FileFacts) -> List[Dict]:
    """Types and public methods, brace-depth nested.

    C#'s dominant style (confirmed against real `$TARGET_REPO` files, e.g.
    `Controllers/RoleNames.cs`) opens a type's body on the line *after* its
    header (Allman), not on the same line -- so a declaration is held
    `pending` until its own opening brace is actually seen, rather than being
    pushed onto the nesting stack immediately. Pushing immediately (the
    same-line assumption `java.py`'s K&R-tuned version makes) pops the type
    right back off before anything inside it is read, silently orphaning its
    members -- caught by a smoke test against a real snippet before this
    shipped, not assumed correct.
    """
    masked = [mask_string_literals(line) for line in code]
    decls: List[Dict] = []
    stack: List[Tuple[str, int]] = []  # (fqn, depth of its enclosing scope)
    pending: Optional[str] = None
    pending_since = -1
    depth = 0
    # A bodyless `public record Foo(int X, int Y);` never opens a brace, and
    # its parameter list can wrap across several lines -- bounded the same
    # way `java.py`'s multi-line annotation-argument join is (30 lines there;
    # a record's parameter list is shorter, so 15 here).
    PENDING_MAX_LINES = 15

    for idx, line in enumerate(code):
        m = TYPE_RE.match(line)
        if m:
            pending = None  # the previous pending never opened -- it was bodyless, drop it
            visibility = m.group(1) or "internal"
            kind = m.group(2)
            name = m.group(3)
            outer = stack[-1][0] if stack else None
            fqn = (outer + "." + name) if outer else ((ns + "." + name) if ns else name)
            anchor = anchor_at(ctx, idx)
            if anchor is not None:
                decls.append({"fqn": fqn, "kind": kind, "visibility": visibility,
                              "anchor": anchor, "index": idx, "name": name})
                facts.defines.append(mk_define(fqn, kind, visibility, anchor))
            pending = fqn
            pending_since = idx
        elif pending is None and stack:
            mm = METHOD_RE.match(line)
            if mm:
                owner = stack[-1][0]
                fqn = owner + "#" + mm.group(3)
                anchor = anchor_at(ctx, idx)
                if anchor is not None:
                    facts.defines.append(mk_define(fqn, "method", "public", anchor))
                    decls.append({"fqn": fqn, "kind": "method", "visibility": "public",
                                  "anchor": anchor, "index": idx, "name": mm.group(3)})
        elif pending is not None and idx - pending_since > PENDING_MAX_LINES:
            pending = None  # gave up waiting for a body; assume bodyless

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


def _read_attributes(code: List[str]) -> List[_Attr]:
    found: List[_Attr] = []
    for idx, line in enumerate(code):
        m = ATTR_RE.match(line)
        if not m:
            continue
        name = m.group(1).rsplit(".", 1)[-1]
        found.append(_Attr(name, m.group(2) or "", idx))
    return found


# ------------------------------------------------------------------ emitters


def _emit_import_edges(facts: FileFacts) -> None:
    """One io_edge per import that maps onto a channel (§6.2), deduplicated
    by channel -- the same rule `java.py` applies for the same reason: N
    imports from one library is one fact about the file, not N."""
    seen = set()
    for row in facts.imports:
        channel = channel_for_import(row["fqn"])
        if channel is None or channel in seen:
            continue
        seen.add(channel)
        parts = row["fqn"].split(".")
        root = ".".join(parts[:2]) if len(parts) >= 2 else row["fqn"]
        facts.io_edges.append(mk_edge(facts.primary, "library:" + root, channel, row["anchor"]))


def _owner_for(index: int, decls: List[Dict], primary: str) -> str:
    for d in decls:
        if d["index"] >= index and d["index"] - index <= 40:
            return d["fqn"]
    return primary


def _emit_attribute_facts(
    ctx: ExtractContext, facts: FileFacts, attrs: List[_Attr], decls: List[Dict], primary: str,
) -> None:
    by_name: Dict[str, List[_Attr]] = {}
    for a in attrs:
        by_name.setdefault(a.name, []).append(a)

    if by_name.get("ApiController"):
        facts.signals.append("api_controller")

    class_index = decls[0]["index"] if decls else 0
    base = ""
    for a in by_name.get("Route", []):
        if a.index <= class_index or not decls:
            literal = first_string_literal(a.args)
            if literal is not None:
                base = literal

    emitted = False
    for a in attrs:
        verb = ROUTE_VERBS.get(a.name)
        if verb is None:
            continue
        anchor = anchor_at(ctx, a.index)
        if anchor is None:
            continue
        sub = first_string_literal(a.args) or ""
        emitted = True
        facts.signals.append("http_resource")
        facts.io_edges.append(
            mk_edge(_owner_for(a.index, decls, primary),
                    "route:%s %s" % (verb, _join_route(base, sub)), "http_in", anchor)
        )

    if base and not emitted:
        anchor = anchor_at(ctx, by_name["Route"][0].index) if by_name.get("Route") else None
        if anchor is not None:
            facts.signals.append("http_resource")
            facts.io_edges.append(mk_edge(primary, "route:" + base, "http_in", anchor))


def _join_route(base: str, sub: str) -> str:
    if not sub:
        return base or "/"
    if not base:
        return sub
    return base.rstrip("/") + "/" + sub.lstrip("/")


def _emit_ef_core_edges(
    ctx: ExtractContext, facts: FileFacts, code: List[str], decls: List[Dict], primary: str,
) -> None:
    for idx, line in enumerate(code):
        m = DBCONTEXT_RE.match(line)
        if m:
            facts.signals.append("ef_dbcontext")
            break

    for idx, line in enumerate(code):
        m = DBSET_RE.search(line)
        if not m:
            continue
        anchor = anchor_at(ctx, idx)
        if anchor is None:
            continue
        owner = _owner_for(idx, decls, primary)
        entity = m.group(1).rsplit(".", 1)[-1]
        facts.io_edges.append(mk_edge(owner, "entity:" + entity, "persist", anchor))


def _emit_entrypoint(ctx: ExtractContext, facts: FileFacts, code: List[str], primary: str) -> None:
    for idx, line in enumerate(code):
        if MAIN_RE.search(line):
            anchor = anchor_at(ctx, idx)
            if anchor is None:
                continue
            facts.signals.append("main")
            facts.io_edges.append(mk_edge(primary, "process:" + primary, "process_boundary", anchor))
            break
