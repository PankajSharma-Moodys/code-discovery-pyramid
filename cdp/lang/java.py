"""Java extractor.

PLAN.md Phase 2, and the place where "Python owns structure, the LLM owns
meaning" either pays off or silently loses recall.

Two rules from RESEARCH.md §6.3 are implemented literally because the validation
target punishes any shortcut around them:

1. **The package is read from source, never inferred from the path.** On the
   target the directory is `src/main/java/RMS/UnifiedStore/sqlpool/...` while the
   declared package is `rms.unifiedstore.sqlpool...`. The case differs and only
   survives because macOS is case-insensitive. Path inference here produces
   fully-qualified names that match nothing, and the failure is silent.

2. **Route constants are recorded symbolically, not resolved locally.** A leaf
   that resolves `@Path(ApiConstants.SQL_POOL_SERVER_PATH)` itself works only
   while the constant is inside its own scope. The extractor emits
   `${ApiConstants.SQL_POOL_SERVER_PATH}` and lets the deterministic resolve
   phase substitute the literal and attach the second anchor.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

from .java_decl import DeclParser, JMember, JType, join_tokens, skip_annotation
from .java_flow import emit_flow, use_row
from .java_tokens import Tokens
from .java_types import norm_type, resolve_name
from .base import (
    ExtractContext,
    Extractor,
    FileFacts,
    anchor_at,
    channel_for_import,
    count_loc,
    first_string_literal,
    is_third_party,
    annotation_rows,
    mk_define,
    mk_edge,
    mk_use,
    strip_block_comments,
)

PACKAGE_RE = re.compile(r"^\s*package\s+([A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*)\s*;")
IMPORT_RE = re.compile(r"^\s*import\s+(static\s+)?([A-Za-z_$][\w$]*(?:\.[\w$*]+)*)\s*;")
TYPE_RE = re.compile(
    r"^\s*(?:(public|protected|private)\s+)?"
    r"(?:(?:abstract|final|static|sealed|non-sealed|strictfp)\s+)*"
    r"(class|interface|enum|record|@interface)\s+([A-Za-z_$][\w$]*)"
)
CONST_RE = re.compile(
    r"^\s*(?:(public|protected|private)\s+)?static\s+final\s+"
    r"[\w$<>\[\],.\s]+?\s+([A-Za-z_$][\w$]*)\s*=\s*(.+?);\s*$"
)
METHOD_RE = re.compile(
    r"^\s*(public|protected|private)\s+"
    r"(?:(?:static|final|abstract|synchronized|native|default)\s+)*"
    r"(?:<[^>]*>\s+)?"
    r"([\w$<>\[\],.?\s]+?)\s+([a-zA-Z_$][\w$]*)\s*\("
)
MAIN_RE = re.compile(r"\bpublic\s+static\s+void\s+main\s*\(\s*(?:final\s+)?String")
EXTENDS_REPO_RE = re.compile(
    r"\b(?:extends|implements)\s+[\w.]*(JpaRepository|CrudRepository|PagingAndSortingRepository|MongoRepository|JpaSpecificationExecutor)\s*<\s*([\w$.]+)"
)
IFACE_METHOD_RE = re.compile(
    r"^\s*(?:public\s+|default\s+|abstract\s+)*"
    r"([A-Z][\w$<>,.\s\[\]]*?)\s+([a-zA-Z_$][\w$]*)\s*\(\s*([^)]*)\)\s*[;{]"
)
JOB_RE = re.compile(r"\b(?:implements|extends)\s+[\w.]*\b(Job|InterruptableJob|AbstractJob)\b")

HTTP_VERBS = ("GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS")
SPRING_MAPPINGS = {
    "GetMapping": "GET",
    "PostMapping": "POST",
    "PutMapping": "PUT",
    "DeleteMapping": "DELETE",
    "PatchMapping": "PATCH",
    "RequestMapping": "ANY",
}
DI_ANNOTATIONS = frozenset(
    ["Component", "Service", "Repository", "Configuration", "Bean", "Autowired",
     "Inject", "Named", "Singleton", "Controller", "RestController"]
)
JAVA_BUILTINS = frozenset(
    ["String", "Integer", "Long", "Double", "Float", "Boolean", "Byte", "Short",
     "Character", "Object", "List", "Map", "Set", "Optional", "void", "int",
     "long", "double", "float", "boolean", "byte", "short", "char"]
)


class _Annotation:
    __slots__ = ("name", "args", "index")

    def __init__(self, name: str, args: str, index: int) -> None:
        self.name = name
        self.args = args
        self.index = index


class JavaExtractor(Extractor):
    language = "java"
    extensions = (".java",)

    def extract(self, ctx: ExtractContext) -> FileFacts:
        lines = ctx.lines
        code = strip_block_comments(lines)
        facts = FileFacts(path=ctx.path, language=self.language, loc=count_loc(lines))

        facts.package = _read_package(code)
        pkg = facts.package or ""
        _note_package_path_divergence(ctx, facts, pkg)
        imports, simple_to_fqn, wildcards = _read_imports(ctx, code, facts)
        tk = Tokens(lines)
        parser = DeclParser(tk, pkg)
        parser.parse()
        types = parser.types
        resolver = _Resolver(pkg, simple_to_fqn, wildcards)
        resolver.local_types = {t.name: t.fqn for t in types}
        decls = _declarations(ctx, facts, tk, types, resolver, imports)
        annotations = _read_annotations(tk, types)

        primary = decls[0]["fqn"] if decls else (pkg + "." + _stem(ctx.path) if pkg else _stem(ctx.path))
        facts.primary = primary

        _emit_import_edges(ctx, facts, imports, primary)
        _emit_annotation_facts(ctx, facts, annotations, decls, primary, resolver, code)
        _emit_repository_edges(ctx, facts, code, annotations, decls, primary, resolver)
        _emit_mapper_edges(ctx, facts, code, annotations, decls, primary, resolver)
        _emit_entrypoints(ctx, facts, code, primary)
        statics: Dict[str, str] = {}
        static_wild: List[str] = []
        for r in imports:
            if r["static"]:
                if r["fqn"].endswith(".*"):
                    static_wild.append(r["fqn"][:-2])
                else:
                    owner, _, member = r["fqn"].rpartition(".")
                    statics.setdefault(member, owner)
        emit_flow(ctx, facts, code, tk, types, resolver, statics, static_wild)

        facts.signals = sorted(set(facts.signals))
        return facts


# ------------------------------------------------------------------ readers


def _stem(path: str) -> str:
    return path.rsplit("/", 1)[-1].rsplit(".", 1)[0]


def _read_package(code: List[str]) -> Optional[str]:
    for line in code[:80]:
        m = PACKAGE_RE.match(line)
        if m:
            return m.group(1)
    return None


SOURCE_ROOT_RE = re.compile(r"^(.*?/)?src/(?:main|test|it|integrationTest)/(?:java|kotlin)/(.+)$")


def _note_package_path_divergence(ctx: ExtractContext, facts: FileFacts, pkg: str) -> None:
    """Record where the declared package and the directory disagree.

    This is not a lint. It is the evidence for the naming facts §6.3 warns
    about: on the validation target the directory is `RMS/UnifiedStore/...`
    while the package is `rms.unifiedstore...`, and the mismatch survives only
    because macOS is case-insensitive. Recording the divergence turns "any
    path-to-package inference produces names that match nothing" from a rule
    the extractor silently obeys into a fact a reader can be told.
    """
    if not pkg:
        return
    m = SOURCE_ROOT_RE.match(ctx.path)
    if not m:
        return
    from_path = m.group(2).rsplit("/", 1)[0].replace("/", ".") if "/" in m.group(2) else ""
    if not from_path or from_path == pkg:
        return
    kind = "case" if from_path.lower() == pkg.lower() else "structure"
    facts.notes.append("package_path_divergence:%s:%s|%s" % (kind, from_path, pkg))


def _read_imports(
    ctx: ExtractContext, code: List[str], facts: FileFacts
) -> Tuple[List[Dict], Dict[str, str], List[str]]:
    """Returns (import rows, simple-name -> FQN, wildcard package prefixes)."""
    imports: List[Dict] = []
    simple_to_fqn: Dict[str, str] = {}
    wildcards: List[str] = []

    for idx, line in enumerate(code):
        m = IMPORT_RE.match(line)
        if not m:
            continue
        fqn = m.group(2)
        static = bool(m.group(1))
        anchor = anchor_at(ctx, idx)
        if anchor is None:
            continue
        row = {"fqn": fqn, "line": idx + 1, "static": static, "anchor": anchor}
        imports.append(row)
        if fqn.endswith(".*"):
            wildcards.append(fqn[:-2])
        else:
            simple_to_fqn.setdefault(fqn.rsplit(".", 1)[-1], fqn)
        resolved = "third_party" if is_third_party(fqn) else "external"
        facts.uses.append(mk_use(fqn, anchor, via_import=True, resolved=resolved))

    facts.imports = imports
    return imports, simple_to_fqn, wildcards


def _visibility(mods) -> str:
    for v in ("public", "protected", "private"):
        if v in mods:
            return v
    return "package"


def _declarations(ctx: ExtractContext, facts: FileFacts, tk: Tokens, types: List[JType],
                  resolver: "_Resolver", imports: List[Dict]) -> List[Dict]:
    """Define rows for every type, method, constructor and field at any access
    level, and the `decls` list the annotation readers attach to.

    `decls` entries carry `index` (0-based line of the name). A field's `owner_fqn`
    is its class: an annotation above a field belongs to the class, not to the
    next method down.
    """
    decls: List[Dict] = []
    retrofit = any(i["fqn"].startswith("retrofit2.http") for i in imports)
    consts: Dict[str, Dict[str, Optional[str]]] = {}

    def typed(row: Dict, text: str, tvars) -> Dict:
        norm = norm_type(text, lambda n: resolve_name(resolver, n), tvars)
        if norm and norm not in JAVA_BUILTINS and norm not in ("void", "int", "long", "double", "float",
                                                                 "boolean", "byte", "short", "char"):
            row["ret" if row["kind"] == "method" else "ftype"] = norm
        return row

    for jt in types:
        _resolve_annotations(jt, resolver)
    for jt in sorted(types, key=lambda t: (t.line, t.fqn)):
        anchor = anchor_at(ctx, jt.line)
        no_routes = retrofit or any(n == "FeignClient" for n, _ in jt.anns)
        if anchor is not None:
            row = mk_define(jt.fqn, jt.kind, _visibility(jt.mods), anchor, annotations=jt.anns)
            if jt.tparams:
                row["tparams"] = jt.tparams
            if jt.supertypes:
                row["supertypes"] = [norm_type(t, lambda n: resolve_name(resolver, n), jt.all_tparams()) or t
                                     for t in jt.supertypes]
            facts.defines.append(row)
            decls.append({"fqn": jt.fqn, "kind": jt.kind, "visibility": _visibility(jt.mods),
                          "anchor": anchor, "index": jt.line, "name": jt.name,
                          "anns": jt.anns, "no_routes": no_routes})
        tv = jt.all_tparams()
        values = consts.setdefault(jt.fqn, {})
        for m in jt.members:
            if m.kind == "init":
                continue
            anchor = anchor_at(ctx, m.line)
            if anchor is None:
                continue
            vis = m.visibility
            if m.kind in ("method", "ctor"):
                name = "<init>" if m.kind == "ctor" else m.name
                fqn = jt.fqn + "#" + name
                row = mk_define(fqn, "method", vis, anchor, end_line=m.end_line + 1, annotations=m.anns)
                if m.kind == "method":
                    typed(row, m.ret, tv | set(m.tparams))
                if m.params:
                    mtv = tv | set(m.tparams)
                    row["params"] = [
                        _param_row(pname, norm_type(ptype, lambda n: resolve_name(resolver, n), mtv) or ptype, pa)
                        for (ptype, pname), pa in zip(m.params, m.param_anns)]
                facts.defines.append(row)
                decls.append({"fqn": fqn, "kind": "method", "visibility": vis, "anchor": anchor,
                              "index": m.line, "name": name, "no_routes": no_routes,
                              "anns": m.anns, "type_fqn": jt.fqn})
            elif m.kind == "enum_const":
                row = mk_define(jt.fqn + "." + m.name, "field", "public", anchor, end_line=m.end_line + 1,
                                annotations=m.anns)
                row["ftype"] = jt.fqn
                facts.defines.append(row)
            elif m.kind == "field":
                fqn = jt.fqn + "." + m.name
                static_final = "static" in m.mods and "final" in m.mods
                if static_final and m.init:
                    value = _constant_value(tk, m, jt, values)
                    values[m.name] = value
                    row = mk_define(fqn, "constant", vis, anchor, value=value, annotations=m.anns)
                    decls.append({"fqn": fqn, "kind": "constant", "visibility": vis, "anchor": anchor,
                                  "index": m.line, "name": m.name, "no_routes": no_routes})
                else:
                    row = mk_define(fqn, "field", vis, anchor, annotations=m.anns)
                    decls.append({"fqn": fqn, "kind": "field", "visibility": vis, "anchor": anchor,
                                  "index": m.line, "name": m.name, "owner_fqn": jt.fqn,
                                  "no_routes": no_routes})
                typed(row, m.ftype, tv)
                facts.defines.append(row)
    decls.sort(key=lambda d: d["index"])
    return decls


_QUALIFIED_ANN_RE = re.compile(r"@([\w$]+(?:\s*\.\s*[\w$]+)*)")


def _resolve_annotations(jt: JType, resolver: "_Resolver") -> None:
    """Set `fqn` on every annotation of the type, its members and their parameters, where the
    file says what it is: a dotted name, a single-type import, or a type declared here. A name
    that only a wildcard import or the JDK could supply stays simple (rules match its alias)."""
    def one(ann) -> None:
        m = _QUALIFIED_ANN_RE.match(ann[1])
        name = m.group(1).replace(" ", "") if m else ann[0]
        if "." in name:
            ann.fqn = resolver.resolve(name)[0]
        else:
            ann.fqn = resolver.local_types.get(name) or resolver.simple_to_fqn.get(name)

    for ann in jt.anns:
        one(ann)
    for m in jt.members:
        for ann in m.anns:
            one(ann)
        for group in m.param_anns:
            for ann in group:
                one(ann)


def _param_row(name: str, ptype: str, anns) -> Dict:
    row = {"name": name, "type": ptype}
    if anns:
        row["annotations"] = annotation_rows(anns)
    return row


def _constant_value(tk: Tokens, m: JMember, jt: JType, values: Dict[str, Optional[str]]) -> str:
    """A `static final` initialiser as text. A concatenation of string literals
    and constant names becomes one string, with another class's constant kept
    symbolic (`${Owner.NAME}`) for the resolve phase; anything else keeps the old
    reading: the first string literal, or the raw expression."""
    a, b = m.init
    parts: List[str] = []
    j = a
    ok = b > a
    while ok and j < b:
        k, t = tk.kind[j], tk.text[j]
        if k == "str" and not t.startswith('"""'):
            parts.append(first_string_literal(t) or "")
            j += 1
        elif k == "id" and t not in ("new", "this", "super") and tk.at(j + 1) != "(":
            names = [t]
            while tk.at(j + 1) == "." and tk.is_id(j + 2) and tk.at(j + 3) != "(":
                names.append(tk.text[j + 2])
                j += 2
            known = values.get(names[0]) if len(names) == 1 else None
            parts.append(known if known is not None else "${%s}" % ".".join(
                [jt.name] + names if len(names) == 1 else names[-2:]))
            j += 1
        else:
            ok = False
            break
        if j < b:
            if tk.at(j) != "+":
                ok = False
                break
            j += 1
            if j >= b:
                ok = False
    if ok and parts:
        return "".join(parts)
    raw = join_tokens_raw(tk, a, b)
    literal = first_string_literal(raw)
    return literal if literal is not None else raw


def join_tokens_raw(tk: Tokens, a: int, b: int) -> str:
    from .java_decl import join_tokens
    return join_tokens(tk, a, b)


def _mask_literals(line: str) -> str:
    out = []
    quote = None
    i = 0
    while i < len(line):
        ch = line[i]
        if quote:
            if ch == "\\":
                i += 2
                continue
            if ch == quote:
                quote = None
            i += 1
            continue
        if ch in ('"', "'"):
            quote = ch
            i += 1
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def _read_annotations(tk: Tokens, types: List[JType]) -> List[_Annotation]:
    """Every declaration-level annotation site, from the token stream: any position (several
    to a line, after a modifier, on a parameter, nested in another annotation's arguments) and
    never inside a string or comment. Method bodies and field initialisers are skipped: an
    annotation there decorates a local variable or an anonymous class's member, not an API.
    `args` is the argument list as compact source text, `(...)`."""
    skip = bytearray(tk.n)
    for jt in types:
        for m in jt.members:
            for span in (m.body, m.init):
                if span:
                    skip[span[0]:span[1]] = b"\x01" * (span[1] - span[0])
    found: List[_Annotation] = []
    for i in range(tk.n):
        if skip[i]:
            continue
        if tk.text[i] != "@" or tk.kind[i] != "op" or not tk.is_id(i + 1) or tk.text[i + 1] == "interface":
            continue
        j = i + 1
        while tk.at(j + 1) == "." and tk.is_id(j + 2):
            j += 2
        k = skip_annotation(tk, i)
        args = join_tokens(tk, j + 1, k) if k > j + 1 else ""
        found.append(_Annotation(tk.text[j], args, tk.line[i]))
    return found


class _Resolver:
    """Simple-name -> FQN within one file's own knowledge (§6.3)."""

    def __init__(self, pkg: str, simple_to_fqn: Dict[str, str], wildcards: List[str]) -> None:
        self.pkg = pkg
        self.simple_to_fqn = simple_to_fqn
        self.wildcards = wildcards
        self.local_types: Dict[str, str] = {}

    def resolve(self, name: str) -> Tuple[str, str]:
        """Returns (fqn, resolved-state).

        Resolution order follows the JLS, which matters more than it looks:
        a single-type import wins, then the compilation unit's **own package**,
        then a wildcard import. Omitting the same-package step is the bug that
        makes `WidgetRepository extends JpaRepository<WidgetEntity, Long>`
        produce `entity:WidgetEntity` instead of the fully-qualified name — and
        it only shows up when the entity happens to live beside the repository,
        which on a real codebase is most of the time.

        Names this file genuinely cannot resolve stay short and are completed by
        the global resolve phase, which has the symbol table this file lacks.
        """
        name = name.strip().split("<", 1)[0].strip()
        name = name.replace("[]", "").strip()
        if not name or name in JAVA_BUILTINS:
            return name, "third_party"
        if "." in name:
            # `Head.rest`: a type head (imported, nested here, or of this package) is
            # followed by its member types; a lowercase head is a package path and
            # the name is already fully qualified. Never matched by last segment.
            head, _, rest = name.partition(".")
            if head in JAVA_BUILTINS:
                return name, "third_party"
            fq = self.local_types.get(head) or self.simple_to_fqn.get(head)
            if fq:
                full = fq + "." + rest
                return full, ("third_party" if is_third_party(full) else "external")
            if head[:1].isupper() and self.pkg:
                return self.pkg + "." + name, "local"
            return name, ("third_party" if is_third_party(name) else "external")
        if name in self.local_types:
            return self.local_types[name], "external"
        hit = self.simple_to_fqn.get(name)
        if hit:
            return hit, ("third_party" if is_third_party(hit) else "external")
        if self.pkg:
            return self.pkg + "." + name, "local"
        return name, "unresolved"


# ------------------------------------------------------------------ emitters


def _emit_import_edges(ctx: ExtractContext, facts: FileFacts, imports: List[Dict], primary: str) -> None:
    """One io_edge per import that maps onto a §6.2 channel.

    Deduplicated by channel: 29 `javax.ws.rs.*` imports in one file are one fact
    about that file, not 29, and leaving them undeduplicated would let import
    style decide the coupling weights in §6.6.
    """
    seen = set()
    for row in imports:
        channel = channel_for_import(row["fqn"])
        if channel is None or channel in seen:
            continue
        seen.add(channel)
        facts.io_edges.append(
            mk_edge(primary, "library:" + _library_root(row["fqn"]), channel, row["anchor"])
        )


def _library_root(fqn: str) -> str:
    parts = fqn.split(".")
    return ".".join(parts[:3]) if len(parts) >= 3 else fqn


def _owner_for(index: int, decls: List[Dict], primary: str) -> str:
    """The declaration an annotation applies to: the next one below it."""
    for d in decls:
        if d["index"] >= index and d["index"] - index <= 40:
            return d.get("owner_fqn", d["fqn"])
    return primary


def _emit_annotation_facts(
    ctx: ExtractContext,
    facts: FileFacts,
    annotations: List[_Annotation],
    decls: List[Dict],
    primary: str,
    resolver: _Resolver,
    code: List[str],
) -> None:
    by_name: Dict[str, List[_Annotation]] = {}
    for ann in annotations:
        by_name.setdefault(ann.name, []).append(ann)
        if ann.name in DI_ANNOTATIONS:
            facts.signals.append("di:" + ann.name)

    # --- persistence -------------------------------------------------------
    for ann in by_name.get("Table", []):
        name = _named_arg(ann.args, "name") or first_string_literal(ann.args)
        if name:
            anchor = anchor_at(ctx, ann.index)
            if anchor:
                facts.defines.append(mk_define("table:" + name, "table", "public", anchor))

    # `@Entity` -> persist edge: rules/jpa.json (cdp/rules.py), after extraction.

    # --- HTTP inbound ------------------------------------------------------
    _emit_http_routes(ctx, facts, decls)

    # `@Value`, `@ConfigurationProperties` -> config_read edges: rules/spring_config.json.

    # --- scheduling --------------------------------------------------------
    scheduled = set()
    for name in ("Scheduled", "DisallowConcurrentExecution", "PersistJobDataAfterExecution", "Every"):
        for ann in by_name.get(name, []):
            owner = _owner_for(ann.index, decls, primary)
            if (name, owner, ann.index) in scheduled:
                continue     # repeated or `@Schedules`-wrapped on one line: one edge
            scheduled.add((name, owner, ann.index))
            anchor = anchor_at(ctx, ann.index)
            if anchor:
                facts.signals.append("scheduled")
                facts.io_edges.append(
                    mk_edge(_owner_for(ann.index, decls, primary), primary, "schedule", anchor)
                )
    for idx, line in enumerate(code):
        if JOB_RE.search(line):
            anchor = anchor_at(ctx, idx)
            if anchor:
                facts.signals.append("quartz_job")
                facts.io_edges.append(mk_edge(primary, "scheduler", "schedule", anchor))
            break


_TYPE_KINDS = ("class", "interface", "enum", "record", "annotation")


def _ann_args(ann) -> str:
    """The argument list of an `Ann`: its source text from the first `(`."""
    i = ann[1].find("(")
    return ann[1][i:] if i >= 0 else ""


def _emit_http_routes(ctx: ExtractContext, facts: FileFacts, decls: List[Dict]) -> None:
    """JAX-RS and Spring MVC routes, with constants left symbolic (§6.3).

    A class-level `@Path` whose argument is a constant reference becomes
    `${ApiConstants.SQL_POOL_SERVER_PATH}` in the target string. Nothing here
    tries to look the constant up: it may well live in another module, and a
    leaf that reached for it would be violating scope discipline.

    Each handler takes its prefix from its own enclosing type's annotations, never from
    another type in the file, and a Feign or Retrofit type emits no routes.
    """
    bases: Dict[str, Tuple[str, Optional[Dict]]] = {}
    for d in decls:
        if d["kind"] not in _TYPE_KINDS or d.get("no_routes"):
            continue
        base, base_anchor = "", None
        for ann in sorted(d.get("anns", []), key=lambda a: a.line):
            if ann[0] == "Path":
                base, base_anchor = _path_arg(_ann_args(ann)), anchor_at(ctx, ann.line)
            elif ann[0] in SPRING_MAPPINGS:
                spring_path = _path_arg(_ann_args(ann))
                if spring_path:
                    base, base_anchor = spring_path, anchor_at(ctx, ann.line)
        bases[d["fqn"]] = (base, base_anchor)

    emitted = False
    for d in decls:
        if d["kind"] != "method" or d.get("no_routes") or d.get("type_fqn") not in bases:
            continue
        base = bases[d["type_fqn"]][0]
        group = sorted(d.get("anns", []), key=lambda a: a.line)
        sub = ""
        for ann in group:
            if ann[0] == "Path":
                sub = _path_arg(_ann_args(ann))
        for ann in group:
            verb = None
            if ann[0] in HTTP_VERBS:
                verb = ann[0]
            elif ann[0] in SPRING_MAPPINGS:
                verb = SPRING_MAPPINGS[ann[0]]
                sub = _path_arg(_ann_args(ann)) or sub
            if verb is None:
                continue
            anchor = anchor_at(ctx, ann.line)
            if anchor is None:
                continue
            emitted = True
            facts.signals.append("http_resource")
            facts.io_edges.append(
                mk_edge(d["fqn"], "route:%s %s" % (verb, _join_route(base, sub)), "http_in", anchor))

    # A resource class with a class-level @Path and no verb-annotated method is
    # still a mounted route; recording it is better than losing the mount point.
    first = next((d for d in decls if d["kind"] in _TYPE_KINDS), None)
    if first is not None and first["fqn"] in bases and not emitted:
        base, base_anchor = bases[first["fqn"]]
        if base and base_anchor:
            facts.signals.append("http_resource")
            facts.io_edges.append(mk_edge(first["fqn"], "route:" + base, "http_in", base_anchor))


def _join_route(base: str, sub: str) -> str:
    if not sub:
        return base or "/"
    if not base:
        return sub
    return base.rstrip("/") + "/" + sub.lstrip("/")


def _path_arg(args: str) -> str:
    """The route fragment from a `@Path(...)`, literal or symbolic.

    `@Path("/health")`                      -> `/health`
    `@Path(ApiConstants.SQL_POOL_SERVER_PATH)` -> `${ApiConstants.SQL_POOL_SERVER_PATH}`
    """
    if not args:
        return ""
    inner = args.strip()
    if inner.startswith("("):
        inner = inner[1:]
    if inner.endswith(")"):
        inner = inner[:-1]
    inner = inner.strip()
    literal = first_string_literal(inner)
    if literal is not None:
        return literal
    named = _named_arg(args, "value") or _named_arg(args, "path")
    if named:
        return named
    m = re.match(r"^([A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)+)$", inner)
    if m:
        return "${%s}" % m.group(1)
    return ""


def _named_arg(args: str, key: str) -> Optional[str]:
    m = re.search(key + r"\s*=\s*\"([^\"]*)\"", args)
    if m:
        return m.group(1)
    m = re.search(key + r"\s*=\s*([A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)+)", args)
    if m:
        return "${%s}" % m.group(1)
    return None


def _emit_repository_edges(
    ctx: ExtractContext,
    facts: FileFacts,
    code: List[str],
    annotations: List[_Annotation],
    decls: List[Dict],
    primary: str,
    resolver: _Resolver,
) -> None:
    """Spring Data repositories.

    Two signals, deliberately kept apart. `@Repository` marks a type as a
    repository — on the validation target 9 types carry it. `extends
    JpaRepository<EServer, Long>` additionally names the entity, and only 6 do,
    because the `*RepositoryExt` custom-fragment interfaces declare methods
    without restating the type parameter.

    So the *signal* fires 9 times and the typed `persist` *edge* fires 6 times.
    Collapsing them would either lose three repositories or invent three entity
    bindings, and the second failure is the one nobody would notice.
    """
    if any(a.name == "Repository" for a in annotations):
        facts.signals.append("repository")

    for idx, line in enumerate(code):
        m = EXTENDS_REPO_RE.search(line)
        if not m:
            continue
        entity, state = resolver.resolve(m.group(2))
        anchor = anchor_at(ctx, idx)
        if anchor is None:
            continue
        facts.signals.append("repository")
        owner = _enclosing(idx, decls, primary)
        # The type argument is what ties a repository to its entity; the
        # dataflow walk follows it so a `repo.save()` call reaches the table.
        use_row(facts, entity, anchor, "binding", owner, state, resolver)
        facts.io_edges.append(mk_edge(owner, "entity:" + entity, "persist", anchor))
        facts.io_edges.append(mk_edge(owner, "entity:" + entity, "read", anchor))


def _emit_mapper_edges(
    ctx: ExtractContext,
    facts: FileFacts,
    code: List[str],
    annotations: List[_Annotation],
    decls: List[Dict],
    primary: str,
    resolver: _Resolver,
) -> None:
    """MapStruct `@Mapper` interfaces: one `map` edge per conversion method.

    §6.1 calls the mapper layer "the data-flow topology, invisible to a
    dependency graph". Each `DServer toDomain(EServer e)` is exactly one hop of
    the `EServer -> DServer -> Server` representation chain, so it is extracted
    per method rather than per class.
    """
    if not any(a.name == "Mapper" for a in annotations):
        return
    facts.signals.append("mapper")
    for idx, line in enumerate(code):
        m = IFACE_METHOD_RE.match(line)
        if not m:
            continue
        ret_raw, _name, params = m.group(1), m.group(2), m.group(3)
        ret, _ = resolver.resolve(ret_raw.split()[-1] if ret_raw.split() else ret_raw)
        if not ret or ret in JAVA_BUILTINS:
            continue
        anchor = anchor_at(ctx, idx)
        if anchor is None:
            continue
        for param in _param_types(params):
            src, _ = resolver.resolve(param)
            if not src or src in JAVA_BUILTINS or src == ret:
                continue
            facts.io_edges.append(mk_edge(src, ret, "map", anchor))


def _param_types(params: str) -> List[str]:
    out = []
    depth = 0
    current = []
    for ch in params:
        if ch == "<":
            depth += 1
        elif ch == ">":
            depth -= 1
        if ch == "," and depth == 0:
            out.append("".join(current))
            current = []
        else:
            current.append(ch)
    out.append("".join(current))
    types = []
    for chunk in out:
        parts = chunk.replace("final ", "").strip().split()
        parts = [p for p in parts if not p.startswith("@")]
        if len(parts) >= 2:
            types.append(parts[-2])
        elif len(parts) == 1 and parts[0]:
            types.append(parts[0])
    return types


def _emit_entrypoints(ctx: ExtractContext, facts: FileFacts, code: List[str], primary: str) -> None:
    for idx, line in enumerate(code):
        if MAIN_RE.search(line):
            anchor = anchor_at(ctx, idx)
            if anchor is None:
                continue
            facts.signals.append("main")
            facts.io_edges.append(mk_edge(primary, "process:" + primary, "process_boundary", anchor))
            break


def _enclosing(index: int, decls: List[Dict], primary: str) -> str:
    owner = primary
    for d in decls:
        if d["index"] <= index and d["kind"] in ("class", "interface", "enum", "record", "annotation"):
            owner = d["fqn"]
        elif d["index"] > index:
            break
    return owner
