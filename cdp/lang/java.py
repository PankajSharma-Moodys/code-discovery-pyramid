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

from .base import (
    ExtractContext,
    Extractor,
    FileFacts,
    anchor_at,
    channel_for_import,
    count_loc,
    first_string_literal,
    is_third_party,
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
ANNOTATION_RE = re.compile(r"^\s*@([A-Za-z_$][\w$.]*)\s*(\(.*)?$")
EXTENDS_REPO_RE = re.compile(
    r"\b(?:extends|implements)\s+[\w.]*(JpaRepository|CrudRepository|PagingAndSortingRepository|MongoRepository|JpaSpecificationExecutor)\s*<\s*([\w$.]+)"
)
IFACE_METHOD_RE = re.compile(
    r"^\s*(?:public\s+|default\s+|abstract\s+)*"
    r"([A-Z][\w$<>,.\s\[\]]*?)\s+([a-zA-Z_$][\w$]*)\s*\(\s*([^)]*)\)\s*[;{]"
)
VALUE_KEY_RE = re.compile(r"\$\{([^}:]+)(?::[^}]*)?\}")
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
        decls = _read_declarations(ctx, code, pkg, facts)
        annotations = _read_annotations(code)

        primary = decls[0]["fqn"] if decls else (pkg + "." + _stem(ctx.path) if pkg else _stem(ctx.path))
        facts.primary = primary

        resolver = _Resolver(pkg, simple_to_fqn, wildcards)
        _emit_import_edges(ctx, facts, imports, primary)
        _emit_annotation_facts(ctx, facts, annotations, decls, primary, resolver, code)
        _emit_repository_edges(ctx, facts, code, decls, primary, resolver)
        _emit_mapper_edges(ctx, facts, code, annotations, decls, primary, resolver)
        _emit_entrypoints(ctx, facts, code, primary)

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


def _read_declarations(
    ctx: ExtractContext, code: List[str], pkg: str, facts: FileFacts
) -> List[Dict]:
    """Type, constant and public-method declarations, with brace-depth nesting.

    Braces inside string and character literals are masked out first; a single
    `"{"` in a message format string would otherwise shift every subsequent
    declaration into a phantom nested type.
    """
    masked = [_mask_literals(line) for line in code]
    decls: List[Dict] = []
    stack: List[Tuple[str, int]] = []  # (type fqn, brace depth at declaration)
    depth = 0

    for idx, line in enumerate(code):
        while stack and depth < stack[-1][1]:
            stack.pop()

        m = TYPE_RE.match(line)
        if m:
            visibility = m.group(1) or "package"
            kind = {"@interface": "annotation"}.get(m.group(2), m.group(2))
            name = m.group(3)
            outer = stack[-1][0] if stack else None
            fqn = (outer + "." + name) if outer else ((pkg + "." + name) if pkg else name)
            anchor = anchor_at(ctx, idx)
            if anchor is not None:
                row = {"fqn": fqn, "kind": kind, "visibility": visibility,
                       "anchor": anchor, "index": idx, "name": name}
                decls.append(row)
                facts.defines.append(mk_define(fqn, kind, visibility, anchor))
            stack.append((fqn, depth + 1))
        else:
            owner = stack[-1][0] if stack else None
            if owner:
                cm = CONST_RE.match(line)
                if cm:
                    visibility = cm.group(1) or "package"
                    name, raw = cm.group(2), cm.group(3).strip()
                    anchor = anchor_at(ctx, idx)
                    if anchor is not None:
                        literal = first_string_literal(raw)
                        value = literal if literal is not None else raw
                        facts.defines.append(
                            mk_define(owner + "." + name, "constant", visibility, anchor, value=value)
                        )
                        decls.append({"fqn": owner + "." + name, "kind": "constant",
                                      "visibility": visibility, "anchor": anchor,
                                      "index": idx, "name": name})
                elif METHOD_RE.match(line):
                    mm = METHOD_RE.match(line)
                    assert mm is not None
                    if mm.group(1) == "public" and mm.group(3) != mm.group(3).upper():
                        anchor = anchor_at(ctx, idx)
                        if anchor is not None:
                            fqn = owner + "#" + mm.group(3)
                            facts.defines.append(mk_define(fqn, "method", "public", anchor))
                            decls.append({"fqn": fqn, "kind": "method", "visibility": "public",
                                          "anchor": anchor, "index": idx, "name": mm.group(3)})

        depth += masked[idx].count("{") - masked[idx].count("}")

    decls.sort(key=lambda d: d["index"])
    return decls


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


def _read_annotations(code: List[str]) -> List[_Annotation]:
    """Annotation sites, joining arguments that wrap across lines."""
    found: List[_Annotation] = []
    for idx, line in enumerate(code):
        m = ANNOTATION_RE.match(line)
        if not m:
            continue
        name = m.group(1).rsplit(".", 1)[-1]
        args = m.group(2) or ""
        if args:
            depth = args.count("(") - args.count(")")
            j = idx + 1
            while depth > 0 and j < len(code) and j - idx < 30:
                args += " " + code[j].strip()
                depth += code[j].count("(") - code[j].count(")")
                j += 1
        found.append(_Annotation(name, args, idx))
    return found


class _Resolver:
    """Simple-name -> FQN within one file's own knowledge (§6.3)."""

    def __init__(self, pkg: str, simple_to_fqn: Dict[str, str], wildcards: List[str]) -> None:
        self.pkg = pkg
        self.simple_to_fqn = simple_to_fqn
        self.wildcards = wildcards

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
            return name, ("third_party" if is_third_party(name) else "external")
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
            return d["fqn"]
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
    table_names: Dict[int, str] = {}
    for ann in by_name.get("Table", []):
        name = _named_arg(ann.args, "name") or first_string_literal(ann.args)
        if name:
            table_names[ann.index] = name
            anchor = anchor_at(ctx, ann.index)
            if anchor:
                facts.defines.append(mk_define("table:" + name, "table", "public", anchor))

    for ann in by_name.get("Entity", []):
        owner = _owner_for(ann.index, decls, primary)
        # The @Table beside @Entity, if any: same declaration, within a few lines.
        target = None
        for t_index, t_name in table_names.items():
            if abs(t_index - ann.index) <= 4:
                target = "table:" + t_name
                break
        anchor = anchor_at(ctx, ann.index)
        if anchor is None:
            continue
        facts.signals.append("entity")
        # No @Table means JPA defaults the table name from the class name. That
        # is an inference, not a reading, so the edge points at the entity type
        # and the table binding is left for a human rather than guessed.
        facts.io_edges.append(mk_edge(owner, target or ("entity:" + owner), "persist", anchor))

    # --- HTTP inbound ------------------------------------------------------
    _emit_http_routes(ctx, facts, by_name, decls, primary, code)

    # --- configuration -----------------------------------------------------
    for ann in by_name.get("Value", []):
        for key in VALUE_KEY_RE.findall(ann.args):
            anchor = anchor_at(ctx, ann.index)
            if anchor:
                facts.io_edges.append(
                    mk_edge(_owner_for(ann.index, decls, primary), "config:" + key, "config_read", anchor)
                )
    for ann in by_name.get("ConfigurationProperties", []):
        prefix = _named_arg(ann.args, "prefix") or first_string_literal(ann.args) or ""
        anchor = anchor_at(ctx, ann.index)
        if anchor:
            facts.io_edges.append(
                mk_edge(_owner_for(ann.index, decls, primary),
                        "config:" + (prefix or "(class)"), "config_read", anchor)
            )

    # --- scheduling --------------------------------------------------------
    for name in ("Scheduled", "DisallowConcurrentExecution", "PersistJobDataAfterExecution", "Every"):
        for ann in by_name.get(name, []):
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


def _emit_http_routes(
    ctx: ExtractContext,
    facts: FileFacts,
    by_name: Dict[str, List[_Annotation]],
    decls: List[Dict],
    primary: str,
    code: List[str],
) -> None:
    """JAX-RS and Spring MVC routes, with constants left symbolic (§6.3).

    A class-level `@Path` whose argument is a constant reference becomes
    `${ApiConstants.SQL_POOL_SERVER_PATH}` in the target string. Nothing here
    tries to look the constant up: it may well live in another module, and a
    leaf that reached for it would be violating scope discipline.
    """
    class_index = decls[0]["index"] if decls else 0

    # Annotations are grouped by the declaration they sit above, not by line
    # proximity. Proximity is wrong whenever two handlers are close together:
    # a bare `@GET` followed six lines later by another method's `@Path("/{id}")`
    # will adopt that sub-path, and both routes collapse onto the same target
    # under deduplication. One route silently disappears and the other is wrong.
    blocks: Dict[int, List[_Annotation]] = {}
    boundaries = [d["index"] for d in decls]
    for ann in [a for group in by_name.values() for a in group]:
        owner = None
        for boundary in boundaries:
            if boundary >= ann.index:
                owner = boundary
                break
        if owner is None or owner - ann.index > 40:
            continue
        blocks.setdefault(owner, []).append(ann)

    base = ""
    base_anchor = None
    for ann in sorted(blocks.get(class_index, []), key=lambda a: a.index):
        if ann.name == "Path":
            base = _path_arg(ann.args)
            base_anchor = anchor_at(ctx, ann.index)
        elif ann.name in SPRING_MAPPINGS:
            spring_path = _path_arg(ann.args)
            if spring_path:
                base = spring_path
                base_anchor = anchor_at(ctx, ann.index)

    emitted = False
    for owner in sorted(blocks):
        if owner == class_index:
            continue
        group = sorted(blocks[owner], key=lambda a: a.index)
        sub = ""
        for ann in group:
            if ann.name == "Path":
                sub = _path_arg(ann.args)
        for ann in group:
            verb = None
            if ann.name in HTTP_VERBS:
                verb = ann.name
            elif ann.name in SPRING_MAPPINGS:
                verb = SPRING_MAPPINGS[ann.name]
                sub = _path_arg(ann.args) or sub
            if verb is None:
                continue
            anchor = anchor_at(ctx, ann.index)
            if anchor is None:
                continue
            emitted = True
            facts.signals.append("http_resource")
            facts.io_edges.append(
                mk_edge(
                    _owner_for(ann.index, decls, primary),
                    "route:%s %s" % (verb, _join_route(base, sub)),
                    "http_in",
                    anchor,
                )
            )

    # A resource class with a class-level @Path and no verb-annotated method is
    # still a mounted route; recording it is better than losing the mount point.
    if base and not emitted and base_anchor:
        facts.signals.append("http_resource")
        facts.io_edges.append(mk_edge(primary, "route:" + base, "http_in", base_anchor))


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
    for idx, line in enumerate(code):
        m = ANNOTATION_RE.match(line)
        if m and m.group(1).rsplit(".", 1)[-1] == "Repository":
            facts.signals.append("repository")
            break

    for idx, line in enumerate(code):
        m = EXTENDS_REPO_RE.search(line)
        if not m:
            continue
        entity, _ = resolver.resolve(m.group(2))
        anchor = anchor_at(ctx, idx)
        if anchor is None:
            continue
        facts.signals.append("repository")
        owner = _enclosing(idx, decls, primary)
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
