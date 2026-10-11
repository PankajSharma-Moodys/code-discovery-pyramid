"""C# extractor.

Declarations come from a token parser (`csharp_decl`) that reads every access level, generic and
tuple-returning methods, constructors (primary ones too), properties, fields, enum members and
types with long primary-constructor lists. Member bodies are walked by `csharp_flow`/`csharp_body`
for typed references and call sites, and by `csharp_config` for configuration reads.

ASP.NET routes are read per declaration, not by line proximity: a handler's own `[HttpGet]`/`[Route]`
templates are emitted with the *class* they belong to, and the resolve phase joins them with the
class-level `[Route]` collected from every part of a `partial` class (or from a base class), applying
the `[controller]` and `[action]` tokens (`cdp/routes_cs.py`). EF Core tables come from `DbSet<T>`
(table = `[Table]`/`ToTable` of T, else the property name), `[Table]`, `ToTable` and migration
`CreateTable(name:)`.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Set, Tuple

from .base import (
    ExtractContext,
    Extractor,
    FileFacts,
    anchor_at,
    channel_for_import,
    count_loc,
    is_third_party,
    mk_define,
    mk_edge,
    mk_use,
)
from .csharp_config import DYNAMIC, config_names, emit_config, key_of
from .csharp_http import emit_http_clients
from .csharp_decl import CMember, CType, DeclParser, parse_type
from .csharp_tokens import CsTokens, string_value
from .csharp_types import Resolver, norm_type

ROUTE_VERBS = {
    "HttpGet": "GET", "HttpPost": "POST", "HttpPut": "PUT", "HttpDelete": "DELETE",
    "HttpPatch": "PATCH", "HttpHead": "HEAD", "HttpOptions": "OPTIONS",
}
TYPE_KIND = {"struct": "class", "delegate": "class"}
BUILTIN_TYPES = frozenset(["string", "int", "long", "bool", "void", "object", "double", "float", "decimal", "byte",
                           "short", "char", "var", "dynamic", "uint", "ulong", "ushort", "sbyte"])


class CSharpExtractor(Extractor):
    language = "csharp"
    extensions = (".cs",)

    def extract(self, ctx: ExtractContext) -> FileFacts:
        facts = FileFacts(path=ctx.path, language=self.language, loc=count_loc(ctx.lines))
        tk = CsTokens(ctx.lines)
        parser = DeclParser(tk)
        types = parser.parse()
        ns = _namespace(parser)
        facts.package = ns or None

        imports, usings, aliases = _read_imports(ctx, parser, facts)
        resolver = Resolver(ns, usings, aliases)
        resolver.local_types = {t.name: t.fqn for t in types}
        primary = types[0].fqn if types else ((ns + "." if ns else "") + _stem(ctx.path))
        facts.primary = primary
        for t in types:
            if t.kind == "delegate":
                continue
        _declarations(ctx, facts, tk, types, resolver)
        _emit_import_edges(facts)
        _emit_routes(ctx, facts, types, tk)
        _emit_ef(ctx, facts, tk, types, primary)
        _emit_entrypoint(ctx, facts, tk, types, parser, primary)
        emit_http_clients(ctx, facts, primary)

        from .csharp_flow import emit_flow
        emit_flow(ctx, facts, tk, parser, types, resolver, [u for u in imports if u["static"]], ns)
        facts.signals = sorted(set(facts.signals))
        return facts


def _stem(path: str) -> str:
    return path.rsplit("/", 1)[-1].rsplit(".", 1)[0]


def _namespace(parser: DeclParser) -> str:
    if parser.top_ns:
        return parser.top_ns
    return parser.namespaces[0][0] if parser.namespaces else ""


def _read_imports(ctx, parser, facts):
    imports: List[Dict] = []
    usings: List[str] = []
    aliases: Dict[str, str] = {}
    for u in parser.usings:
        anchor = anchor_at(ctx, u.line)
        if anchor is None:
            continue
        imports.append({"fqn": u.name, "line": u.line + 1, "static": u.static, "anchor": anchor})
        if u.alias:
            aliases[u.alias] = u.name
        elif not u.static:
            usings.append(u.name)
        else:
            usings.append(u.name.rsplit(".", 1)[0] if False else u.name)
        resolved = "third_party" if is_third_party(u.name) else "external"
        facts.uses.append(mk_use(u.name, anchor, via_import=True, resolved=resolved))
    facts.imports = [{k: v for k, v in r.items()} for r in imports]
    return imports, usings, aliases


def _vis(v: str) -> str:
    return v


def _declarations(ctx, facts, tk, types: List[CType], resolver: Resolver) -> None:
    consts: Dict[str, Dict[str, Optional[str]]] = {}

    def typed(row: Dict, text: str, tvars) -> Dict:
        norm = norm_type(text, lambda n: _resolve(resolver, n), tvars)
        if norm and norm not in BUILTIN_TYPES and norm != "void":
            row["ret" if row["kind"] == "method" else "ftype"] = norm
        return row

    for jt in sorted(types, key=lambda t: (t.line, t.fqn)):
        anchor = anchor_at(ctx, jt.line)
        tv = jt.all_tparams()
        if anchor is not None:
            row = mk_define(jt.fqn, TYPE_KIND.get(jt.kind, jt.kind), jt.visibility, anchor)
            if jt.tparams:
                row["tparams"] = jt.tparams
            if jt.kind in TYPE_KIND:
                row["clr"] = jt.kind
            routes = [_template(text) for n, text in jt.anns if n == "Route"]
            if routes:
                row["route"] = routes
            if jt.extends:
                guess, state = resolver.resolve(jt.extends[0])
                row["route_parent"] = [guess] + [w + "." + guess.rsplit(".", 1)[-1] for w in resolver.wildcards]
            if jt.kind == "class" and "abstract" in jt.mods:
                row["abstract"] = True
            facts.defines.append(row)
        values = consts.setdefault(jt.fqn, {})
        if jt.pparams is not None:
            a2 = anchor_at(ctx, jt.line)
            if a2 is not None:
                facts.defines.append(mk_define(jt.fqn + "#<init>", "method", "public", a2,
                                               end_line=jt.line + 1))
            if jt.kind == "record":
                for ptype, pname in jt.pparams:
                    if a2 is not None:
                        row = mk_define(jt.fqn + "." + pname, "field", "public", a2)
                        facts.defines.append(typed(row, ptype, tv))
        for m in jt.members:
            if m.nodef or m.kind == "op":
                continue
            anchor = anchor_at(ctx, m.line)
            if anchor is None:
                continue
            vis = m.visibility
            if m.kind in ("method", "ctor"):
                name = "<init>" if m.kind == "ctor" else m.name
                row = mk_define(jt.fqn + "#" + name, "method", vis, anchor, end_line=m.end_line + 1)
                if m.kind == "method":
                    typed(row, m.ret, tv | set(m.tparams))
                    row["pmax"] = 99 if m.params and m.params[-1][0].endswith("[]") else len(m.params)
                    if m.ext:
                        row["ext"] = norm_type(m.ext, lambda n: _resolve(resolver, n), tv | set(m.tparams))
                    if m.tparams:
                        row["tparams"] = m.tparams
                facts.defines.append(row)
            elif m.kind == "enum_const":
                row = mk_define(jt.fqn + "." + m.name, "field", "public", anchor, end_line=m.end_line + 1)
                row["ftype"] = jt.fqn
                facts.defines.append(row)
            elif m.kind == "field":
                fqn = jt.fqn + "." + m.name
                const = "const" in m.mods or ("static" in m.mods and "readonly" in m.mods)
                if const and m.init and not m.prop:
                    value = _constant_value(tk, m, jt, values)
                    values[m.name] = value
                    row = mk_define(fqn, "constant", vis, anchor, value=value)
                else:
                    row = mk_define(fqn, "field", vis, anchor)
                facts.defines.append(typed(row, m.ftype, tv))
            _type_refs(facts, anchor, m, jt, resolver)
    return None


def _resolve(resolver: Resolver, name: str) -> str:
    head, dot, rest = name.partition(".")
    fqn, _ = resolver.resolve(head)
    return fqn + dot + rest if dot else fqn


def _type_refs(facts, anchor, m: CMember, jt: CType, resolver) -> None:
    from .java_flow import type_uses
    if m.kind == "field":
        type_uses(facts, m.ftype, anchor, jt.fqn, resolver)
    elif m.kind in ("method", "ctor"):
        for ptype, _ in m.params:
            type_uses(facts, ptype, anchor, m.symbol, resolver)


def _constant_value(tk: CsTokens, m: CMember, jt: CType, values: Dict[str, Optional[str]]) -> str:
    a, b = m.init
    key = key_of(tk, a, b, {k: v for k, v in values.items() if v is not None}, jt.name)
    if key != DYNAMIC:
        return key
    from .java_decl import join_tokens
    raw = join_tokens(tk, a, b)
    for j in range(a, b):
        if tk.kind[j] == "str":
            v = string_value(tk.text[j])
            if v is not None:
                return v
    return raw[:200]


def _emit_import_edges(facts: FileFacts) -> None:
    seen = set()
    for row in facts.imports:
        channel = channel_for_import(row["fqn"])
        if channel is None or channel in seen:
            continue
        seen.add(channel)
        parts = row["fqn"].split(".")
        root = ".".join(parts[:2]) if len(parts) >= 2 else row["fqn"]
        facts.io_edges.append(mk_edge(facts.primary, "library:" + root, channel, row["anchor"]))


# ------------------------------------------------------------------ routes


def _template(args: str, own: str = "") -> str:
    """The route template of an attribute: a literal, a concatenation, or `${Type.CONST}` parts
    for constants (settled by the resolve phase); "" when computed."""
    from .csharp_config import _split_args
    if "(" not in args:
        return ""
    tk = CsTokens([args])
    o = next((i for i in range(tk.n) if tk.text[i] == "("), -1)
    if o < 0:
        return ""
    for a, b in _split_args(tk, o):
        if tk.at(a + 1) == "=" and tk.text[a] != "template":
            continue
        if tk.at(a + 1) == ":" :
            a += 2
        elif tk.at(a + 1) == "=":
            a += 2
        key = key_of(tk, a, b, {}, own)
        return "" if key == DYNAMIC else key
    return ""


def _emit_routes(ctx, facts, types: List[CType], tk) -> None:
    for jt in types:
        if jt.kind not in ("class", "record") or "abstract" in jt.mods:
            continue
        if any(n == "ApiController" for n, _ in jt.anns):
            facts.signals.append("api_controller")
        class_has_route = any(n == "Route" for n, _ in jt.anns)
        emitted = False
        for m in jt.members:
            if m.kind != "method" or "static" in m.mods:
                continue
            if m.visibility != "public" or any(n == "NonAction" for n, _ in m.anns):
                continue
            verbs = [(ROUTE_VERBS[n], _template(text) if "(" in text else None)
                     for n, text in m.anns if n in ROUTE_VERBS]
            routes = [_template(text) if "(" in text else "" for n, text in m.anns if n == "Route"]
            if not verbs and not routes:
                continue
            sel: List[Tuple[str, str]] = []
            if not verbs:
                sel = [("ANY", r) for r in routes]
            elif routes and all(t is None or t == "" and False for _, t in verbs):
                sel = [(v, r) for v, _ in verbs for r in routes]
            else:
                sel = [(v, t or "") for v, t in verbs]
            anchor = anchor_at(ctx, m.line)
            if anchor is None:
                continue
            for verb, tpl in sel:
                emitted = True
                facts.signals.append("http_resource")
                edge = mk_edge(m.symbol, "route:%s %s" % (verb, tpl), "http_in", anchor)
                edge["route_class"] = jt.fqn
                edge["route_action"] = m.name
                facts.io_edges.append(edge)
        if class_has_route and not emitted and not any(
                n in ("ApiController",) for n, _ in jt.anns) and False:
            pass


# --------------------------------------------------------------------- EF Core


def _emit_ef(ctx, facts, tk: CsTokens, types: List[CType], primary: str) -> None:
    path = ctx.path
    migration = "/Migrations/" in path or path.endswith((".Designer.cs", "ModelSnapshot.cs"))
    for jt in types:
        if any(b.split("<", 1)[0].rsplit(".", 1)[-1] == "DbContext" or b.endswith("DbContext") for b in jt.bases):
            facts.signals.append("ef_dbcontext")
    explicit: Dict[str, Tuple[str, int]] = {}
    no_table: Set[str] = set()
    sets: List[Tuple[CType, CMember, str]] = []
    for jt in types:
        for n, text in jt.anns:
            if n == "Table":
                name = _template(text)
                if name and not name.startswith("${"):
                    explicit[jt.name] = (name, jt.line)
        for m in jt.members:
            if m.kind == "field" and m.prop and m.ftype.split("<", 1)[0].rsplit(".", 1)[-1] == "DbSet" \
                    and "<" in m.ftype:
                ent = m.ftype.split("<", 1)[1].rstrip(">").rsplit(".", 1)[-1]
                sets.append((jt, m, ent))
    # fluent API: `.Entity<T>(...)` ... `.ToTable("x")` / `.ToView(null)`
    owner_of = _owner_lines(types)
    entity: Optional[str] = None
    for i in range(tk.n):
        t = tk.text[i]
        if tk.kind[i] != "id":
            continue
        if t == "Entity" and tk.at(i + 1) == "<" and tk.is_id(i + 2):
            j = i + 2
            while tk.at(j + 1) == "." and tk.is_id(j + 2):
                j += 2
            entity = tk.text[j]
            if tk.at(j + 1) == ">" and tk.at(j + 2) == "(" and tk.at(tk.close(j + 2) + 1) == ".":
                pass
        elif t in ("ToTable", "ToView") and tk.at(i + 1) == "(" and tk.at(i - 1) == ".":
            c = tk.close(i + 1)
            if i + 2 < c and tk.kind[i + 2] == "str":
                name = string_value(tk.text[i + 2])
                if name and entity and not migration:
                    explicit[entity] = (name, tk.line[i])
            elif entity and not migration:
                no_table.add(entity)
        elif t == "CreateTable" and tk.at(i + 1) == "(":
            c = tk.close(i + 1)
            name = None
            for j in range(i + 2, c):
                if tk.text[j] == "name" and tk.at(j + 1) == ":" and tk.kind[j + 2] == "str":
                    name = string_value(tk.text[j + 2])
                    break
            if name is None and i + 2 < c and tk.kind[i + 2] == "str":
                name = string_value(tk.text[i + 2])
            if name:
                _table(ctx, facts, name, tk.line[i], owner_of(tk.line[i], primary), ("schema_own",), define=True)
    for ent, (name, line) in sorted(explicit.items(), key=lambda kv: kv[1][1]):
        if not migration:
            _table(ctx, facts, name, line, owner_of(line, primary), ("schema_own",), define=True)
    if migration:
        return
    for jt, m, ent in sets:
        facts.signals.append("ef_dbcontext")
        anchor = anchor_at(ctx, m.line)
        if anchor is None:
            continue
        facts.io_edges.append(mk_edge(jt.fqn, "entity:" + ent, "persist", anchor))
        if ent in no_table:
            continue
        name = explicit[ent][0] if ent in explicit else m.name
        _table(ctx, facts, name, m.line, jt.fqn, ("schema_own", "persist", "read"), define=ent not in explicit)


def _owner_lines(types: List[CType]):
    spans = sorted(((t.start_line, t.end_line, t.fqn) for t in types), key=lambda s: (s[0], -s[1]))

    def owner(line: int, default: str) -> str:
        best = default
        for a, b, fqn in spans:
            if a <= line <= b:
                best = fqn
        return best
    return owner


def _table(ctx, facts, name: str, line: int, owner: str, channels, define: bool) -> None:
    anchor = anchor_at(ctx, line)
    if anchor is None:
        return
    for ch in channels:
        if any(e["target"] == "table:" + name and e["channel"] == ch and e["source"] == owner for e in facts.io_edges):
            continue
        facts.io_edges.append(mk_edge(owner, "table:" + name, ch, anchor))
    if define and not any(d["fqn"] == "table:" + name for d in facts.defines):
        facts.defines.append(mk_define("table:" + name, "table", "public", anchor))


def _emit_entrypoint(ctx, facts, tk: CsTokens, types, parser, primary: str) -> None:
    for jt in types:
        for m in jt.members:
            if m.kind == "method" and m.name == "Main" and "static" in m.mods:
                anchor = anchor_at(ctx, m.line)
                if anchor is not None:
                    facts.signals.append("main")
                    facts.io_edges.append(mk_edge(primary, "process:" + primary, "process_boundary", anchor))
                return
    if parser.top_spans:
        anchor = anchor_at(ctx, tk.line[parser.top_spans[0][0]])
        if anchor is not None:
            facts.signals.append("main")
            facts.io_edges.append(mk_edge(primary, "process:" + primary, "process_boundary", anchor))
