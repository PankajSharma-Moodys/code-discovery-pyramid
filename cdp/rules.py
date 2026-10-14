"""Built-in join rules (ANNOTATIONS_PLAN P5): which annotations make an `io_edge`.

CDP interprets an annotation only where an answer needs a join across files: routes, tables,
config keys, schedules. Everything else is shown verbatim. The interpretations live in
`cdp/rules/*.json` (one file per framework family) and are applied here, as a post-pass over an
extraction, never inside an extractor.

Rule shape (see the JSON files)::

    {"id": "spring.web.mapping",
     "match": {"fqn": ["org.springframework...GetMapping", ...], "on": "method"},
     "aliases": ["GetMapping", ...],            # used only when the annotation's fqn is unresolved
     "vars": {"verb": {"GetMapping": "GET"}},   # name -> {annotation simple name: text}
     "unless": {"owner": {"fqn": [...], "aliases": [...]}, "imports": ["retrofit2.http"]},
     "when": {"first_type": true},              # the declaration is the file's first type
     "fallback": true,                          # fire only if no other rule made this channel in the file
     "inherit": true, "declared": false,        # apply to implementations through `supertypes`
     "emit": {"channel": "http_in", "signal": "http_resource",
              "target": ["route:{vars.verb} {join(owner.Path.value, value|path)}"]}}

Matching is by fqn first. An annotation whose fqn is unresolved (a wildcard import, a same-package
type) matches by simple-name alias; one whose fqn is known and not listed never does, so two
packages' `@Path` cannot be confused.

Template placeholders `{...}`: `a|b|'lit'` is the first non-empty alternative (`'lit'` is a literal);
`value` is an argument of the matched annotation; `owner.Ann.key` / `decl.Ann.key` read an
argument of another annotation on the owner class / the declaring member; `ann.name`, `decl.fqn`,
`owner.fqn`, `file.primary`, `vars.<name>` are facts; `join(base, sub)` is a route join; a
`:keys` filter yields one target per `${key}` named in a string (`@Value("${a}-${b}")`).
`join(a, b, c...)` folds any number of route parts; `params.0.type` is the declaring method's first
parameter type; an `:each` filter yields one target per string (or `Foo.class`, resolved through the
file's imports) in a list argument. `when.owner` requires an owner-class annotation (the inverse of
`unless.owner`). Constants stay symbolic: a dotted reference renders `${Owner.NAME}`, an unqualified one
`${<declaring class>.NAME}`. A placeholder with no value drops that `target` alternative; the
next one is tried.

`emit.sql` is the hook for SQL in annotations (P7): a template rendering the SQL text, handed to
`SQL_HOOK(text) -> [(target, channel)]` (native SQL: `table:` edges, `persist` for writes, `read` for
reads), one edge each; `"dialect": "jpql"` hands it to `JPQL_HOOK` (`entity:` edges) instead, and an
entity with a known `@Table` name also yields that `table:` edge. `{value:all}` joins every string of
an array argument (MyBatis `@Select({"select ...", "from t"})`). `when`/`unless` may test an argument
of the matched annotation: `{"arg": {"nativeQuery": true}}`.

Rule edges are stored in `extraction["rule_edges"]` (recomputed on every scan and refresh), never in
`io_edges`, which `incremental_extract` carries forward per module. Read both through `all_edges`.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from .anchor import build_anchor
from .util import read_lines

RULES_DIR = Path(__file__).resolve().parent / "rules"
META_DEPTH = 3
INHERIT_DEPTH = 5
TYPE_KINDS = ("class", "interface", "enum", "record", "annotation")
ON_KINDS = {"class": TYPE_KINDS, "method": ("method",), "field": ("field",), "constant": ("constant",)}
_RULE_KEYS = {"id", "match", "aliases", "emit", "vars", "unless", "when", "fallback", "inherit", "declared"}
_EMIT_KEYS = {"channel", "target", "signal", "sql", "dialect"}


#: Languages whose declarations the rule engine reads (a family lists `languages`; the old single
#: `"language": "java"` string is still accepted).
JVM_LANGS = frozenset({"java", "scala"})

_TRIPLE = re.compile(r'"{3,}')
_MARGIN = re.compile(r"(?m)^[ \t]*\|(?!\|)")
_STRIP_MARGIN = re.compile(r"\.stripMargin(?:\([^)]*\))?")


def _sql_text(text: str) -> str:
    """Scala SQL literal -> plain SQL: triple-quote delimiters, an `s`/`f` interpolator prefix before
    them, a `.stripMargin` suffix and the `|` margin of each line are dropped. Java text is unchanged."""
    if '"""' in text:
        text = re.sub(r'\b[sf](?="{3})', "", text)
        text = _TRIPLE.sub(" ", text)
    if ".stripMargin" in text:
        text = _STRIP_MARGIN.sub(" ", text)
    if "|" in text:
        text = _MARGIN.sub("", text)
    return text


def _native_sql_edges(text: str) -> List[Tuple[str, str]]:
    from .lang.data import sql_edges
    return sql_edges(_sql_text(text))


def _jpql_edges(text: str) -> List[Tuple[str, str]]:
    from .lang.data import jpql_edges
    return jpql_edges(text)


#: `emit.sql` hooks (ANNOTATIONS_PLAN P7): `hook(sql_text) -> [(target, channel), ...]`. `SQL_HOOK` reads
#: native SQL (`table:` edges); `JPQL_HOOK`, used by rules with `"dialect": "jpql"`, reads entity names
#: (`entity:` edges). Setting either to None switches that dialect off.
SQL_HOOK: Optional[Callable[[str], List[Tuple[str, str]]]] = _native_sql_edges
JPQL_HOOK: Optional[Callable[[str], List[Tuple[str, str]]]] = _jpql_edges


# ------------------------------------------------------------------ loading


class RuleError(ValueError):
    pass


def _as_list(v) -> List[str]:
    return [] if v is None else ([v] if isinstance(v, str) else list(v))


def _check(rule: Dict, family: Dict) -> Dict:
    rid = rule.get("id")
    if not rid or not isinstance(rid, str):
        raise RuleError("rule without an id in family %r" % family.get("family"))
    extra = set(rule) - _RULE_KEYS
    if extra:
        raise RuleError("rule %s: unknown keys %s" % (rid, sorted(extra)))
    match, emit = rule.get("match") or {}, rule.get("emit") or {}
    if not _as_list(match.get("fqn")) and not rule.get("aliases"):
        raise RuleError("rule %s matches nothing (no fqn, no aliases)" % rid)
    on = _as_list(match.get("on"))
    if not on or any(o not in ON_KINDS and o != "param" for o in on):
        raise RuleError("rule %s: match.on must be among class|method|field|constant|param" % rid)
    if set(emit) - _EMIT_KEYS or not emit.get("channel") or not (emit.get("target") or emit.get("sql")):
        raise RuleError("rule %s: emit needs channel and target (or sql), only %s allowed" % (rid, sorted(_EMIT_KEYS)))
    out = dict(rule)
    langs = _as_list(family.get("languages")) or _as_list(family.get("language", "java"))
    if not langs or not all(isinstance(x, str) and x for x in langs):
        raise RuleError("family %r: languages must be a non-empty list of names" % family.get("family"))
    out["languages"] = frozenset(langs)
    out["language"] = langs[0]
    out["family"] = family.get("family", "")
    out["_fqns"] = frozenset(_as_list(match.get("fqn")))
    out["_aliases"] = frozenset(rule.get("aliases") or ())
    out["_on"] = tuple(on)
    out["_targets"] = _as_list(emit.get("target"))
    return out


def load_rules(directory: Optional[Path] = None) -> List[Dict]:
    """Every rule of every `*.json` family file, validated, in file then rule order."""
    rules: List[Dict] = []
    seen = set()
    for path in sorted(Path(directory or RULES_DIR).glob("*.json")):
        family = json.loads(path.read_text(encoding="utf-8"))
        for rule in family.get("rules", []):
            rule = _check(rule, family)
            if rule["id"] in seen:
                raise RuleError("duplicate rule id %s" % rule["id"])
            seen.add(rule["id"])
            rules.append(rule)
    return rules


_CACHE: Dict[str, List[Dict]] = {}


def builtin_rules() -> List[Dict]:
    if "builtin" not in _CACHE:
        _CACHE["builtin"] = load_rules()
    return _CACHE["builtin"]


# ------------------------------------------------------------------ matching


def ann_matches(ann: Dict, fqns: Iterable[str], aliases: Iterable[str]) -> bool:
    """fqn first; the simple-name alias only for an annotation whose fqn is unresolved."""
    fqn = ann.get("fqn")
    if fqn:
        return fqn in fqns
    return ann.get("name") in aliases


def _flatten(anns: Sequence[Dict]) -> Iterable[Dict]:
    """Each annotation row and every annotation nested in its arguments (`@Schedules({@Scheduled})`)."""
    for ann in anns or ():
        yield ann
        stack = list((ann.get("args") or {}).values())
        while stack:
            v = stack.pop(0)
            if isinstance(v, list):
                stack = v + stack
            elif isinstance(v, dict) and "name" in v and "text" in v:
                yield v
                stack = list((v.get("args") or {}).values()) + stack


class _Index:
    """Rules indexed for one pass, plus the repo facts a rule can need (types, `@interface` rows)."""

    def __init__(self, extraction: Dict, rules: Sequence[Dict]) -> None:
        self.rules = [r for r in rules if r["languages"] & JVM_LANGS]
        self.files = extraction.get("files") or {}
        self.types: Dict[str, Dict] = {}
        self.methods: Dict[str, List[Dict]] = {}
        self.ann_types: Dict[str, Dict] = {}
        self.ann_by_simple: Dict[str, List[Dict]] = {}
        self.imports: Dict[str, List[str]] = {}
        for d in extraction.get("defines") or ():
            if self.lang(d.get("file")) not in JVM_LANGS:
                continue
            if d["kind"] in TYPE_KINDS:
                self.types.setdefault(d["fqn"], d)
                if d["kind"] == "annotation":
                    self.ann_types.setdefault(d["fqn"], d)
                    self.ann_by_simple.setdefault(d["fqn"].rsplit(".", 1)[-1], []).append(d)
            elif d["kind"] == "method":
                self.methods.setdefault(d["fqn"], []).append(d)
        for imp in extraction.get("imports") or ():
            self.imports.setdefault(imp["file"], []).append(imp["fqn"])

    def lang(self, rel: Optional[str]) -> Optional[str]:
        return (self.files.get(rel) or {}).get("language")

    def meta_type(self, ann: Dict, rel: str) -> Optional[Dict]:
        """The repo `@interface` an annotation refers to: by fqn, else the file's own package, else a
        simple name that is unique in the repo."""
        fqn = ann.get("fqn")
        if fqn:
            return self.ann_types.get(fqn)
        name = ann.get("name") or ""
        pkg = (self.files.get(rel) or {}).get("package")
        if pkg and pkg + "." + name in self.ann_types:
            return self.ann_types[pkg + "." + name]
        hits = self.ann_by_simple.get(name, [])
        return hits[0] if len(hits) == 1 else None

    def resolver(self, rel: str) -> Callable[[str], str]:
        """`Foo` / `Outer.Inner` as a class name written in this file -> fqn when imports or the
        package say so, else the name as written."""
        imports = self.imports.get(rel, [])
        pkg = (self.files.get(rel) or {}).get("package") or ""

        def resolve(name: str) -> str:
            head, _, rest = name.partition(".")
            if head[:1].islower() and rest:
                return name                        # already qualified (`com.x.Foo`)
            for imp in imports:
                if imp.rsplit(".", 1)[-1] == head:
                    return imp + ("." + rest if rest else "")
            if pkg and pkg + "." + name in self.types:
                return pkg + "." + name
            return name

        return resolve

    def direct(self, ann: Dict, on: str, lang: Optional[str] = None):
        for rule in self.rules:
            if lang is not None and lang not in rule["languages"]:
                continue
            if on in rule["_on"] and ann_matches(ann, rule["_fqns"], rule["_aliases"]):
                yield rule

    def effective(self, ann: Dict, rel: str, on: str, depth: int = 0, seen=frozenset()):
        """`(rule, annotation-row-with-args)` pairs for one annotation: its own rules, or, when it
        has none, those of the annotations on its `@interface` (meta-annotations). The use site
        keeps its line; the arguments are the matching annotation's."""
        rules = list(self.direct(ann, on, self.lang(rel)))
        for rule in rules:
            yield rule, ann
        if rules or depth >= META_DEPTH:
            return
        meta = self.meta_type(ann, rel)
        if meta is None or meta["fqn"] in seen:
            return
        for m in _flatten(meta.get("annotations")):
            for rule, row in self.effective(m, meta.get("file") or rel, on, depth + 1, seen | {meta["fqn"]}):
                yield rule, dict(row, line=ann.get("line"), end_line=ann.get("end_line"))


# ------------------------------------------------------------------ templates


_PLACEHOLDER = re.compile(r"\{([^{}]+)\}")
_KEY = re.compile(r"\$\{([^}:]+)(?::[^}]*)?\}")


def _split_top(s: str, sep: str) -> List[str]:
    out, cur, quote, depth = [], [], False, 0
    for ch in s:
        if ch == "'":
            quote = not quote
        elif not quote and ch == "(":
            depth += 1
        elif not quote and ch == ")":
            depth -= 1
        if ch == sep and not quote and depth == 0:
            out.append("".join(cur).strip())
            cur = []
        else:
            cur.append(ch)
    out.append("".join(cur).strip())
    return out


def render_value(v, owner_name: str = "") -> str:
    """An annotation argument as route/config text, constants symbolic."""
    if isinstance(v, str):
        return v
    if isinstance(v, bool) or v is None:
        return "" if v is None else str(v).lower()
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, list):
        for item in v:
            text = render_value(item, owner_name)
            if text:
                return text
        return ""
    if isinstance(v, dict):
        if "ref" in v:
            ref = v["ref"]
            return "${%s}" % ref if "." in ref else ("${%s.%s}" % (owner_name, ref) if owner_name else "")
        if "concat" in v:
            return "".join(render_value(p, owner_name) for p in v["concat"])
    return ""


def _string_leaves(v) -> List[str]:
    """Literal strings of an argument, each on its own (a ref is not config text)."""
    if isinstance(v, str):
        return [v]
    if isinstance(v, list):
        return [s for item in v for s in _string_leaves(item)]
    if isinstance(v, dict) and "concat" in v:
        return [p for p in v["concat"] if isinstance(p, str)]
    return []


def _each_leaves(v, resolve: Callable[[str], str], owner_name: str = "") -> List[str]:
    """Every string, class literal (resolved) and constant of an argument, one per list item."""
    if isinstance(v, list):
        return [x for item in v for x in _each_leaves(item, resolve, owner_name)]
    if isinstance(v, dict) and "class" in v:
        return [resolve(v["class"])]
    text = render_value(v, owner_name)
    return [text] if text else []


def join_route(base: str, sub: str) -> str:
    if not sub:
        return base or "/"
    if not base:
        return sub
    return base.rstrip("/") + "/" + sub.lstrip("/")


class Site:
    """One annotation use: the matched row and the declaration facts a template reads."""

    def __init__(self, rule: Dict, ann: Dict, decl: Dict, owner: Dict, file_info: Dict, param_of=None,
                 resolve: Optional[Callable[[str], str]] = None) -> None:
        self.rule, self.ann, self.decl, self.owner = rule, ann, decl, owner
        self.file_info, self.param_of = file_info, param_of
        self.resolve = resolve or (lambda name: name)

    def _arg(self, anns: Sequence[Dict], name: str, key: str, owner_name: str) -> str:
        for a in anns or ():
            if a.get("name") == name or (a.get("fqn") or "").rsplit(".", 1)[-1] == name:
                text = render_value((a.get("args") or {}).get(key), owner_name)
                if text:
                    return text
        return ""

    def _term(self, term: str) -> Optional[str]:
        if len(term) >= 2 and term[0] == term[-1] == "'":
            return term[1:-1]
        head, _, rest = term.partition(".")
        cls_name = (self.owner or self.decl)["fqn"].rsplit(".", 1)[-1]
        if head == "ann" and rest == "name":
            return self.ann.get("name") or ""
        if head == "decl" and rest == "fqn":
            return self.decl["fqn"]
        if head == "owner" and rest == "fqn":
            return self.owner["fqn"] if self.owner else ""
        if head == "file" and rest == "primary":
            return self.file_info.get("primary") or ""
        if head == "params" and rest.count(".") == 1 and rest.split(".")[1] == "type":
            params = self.decl.get("params") or []
            i = rest.split(".")[0]
            return (params[int(i)].get("type") or "").split("<", 1)[0] if i.isdigit() and int(i) < len(params) else ""
        if head == "vars":
            return ((self.rule.get("vars") or {}).get(rest) or {}).get(self.ann.get("name")) or ""
        if head in ("owner", "decl") and rest.count(".") == 1:
            name, key = rest.split(".")
            target = self.owner if head == "owner" else self.decl
            return self._arg((target or {}).get("annotations"), name, key, cls_name)
        if "." not in term:
            return render_value((self.ann.get("args") or {}).get(term), cls_name)
        return ""

    def _alts(self, expr: str) -> Optional[str]:
        for term in _split_top(expr, "|"):
            text = self._term(term)
            if text:
                return text
        return None

    def expand(self, template: str) -> List[str]:
        """The targets a template yields: none when a placeholder has no value."""
        outs = [""]
        pos = 0
        for m in _PLACEHOLDER.finditer(template):
            lit = template[pos:m.start()]
            pos = m.end()
            expr, _, flt = m.group(1).partition(":") if not m.group(1).startswith("join(") else (m.group(1), "", "")
            if expr.startswith("join("):
                parts = [self._alts(e) or "" for e in _split_top(expr[len("join("):-1], ",")]
                acc = parts[0]
                for part in parts[1:]:
                    acc = join_route(acc, part)
                vals = [acc]
            elif flt == "each":
                vals = []
                for term in _split_top(expr, "|"):
                    vals = _each_leaves((self.ann.get("args") or {}).get(term), self.resolve,
                                        (self.owner or self.decl)["fqn"].rsplit(".", 1)[-1])
                    if vals:
                        break
            elif flt == "all":
                text = ""
                for term in _split_top(expr, "|"):
                    raw = (self.ann.get("args") or {}).get(term)
                    items = raw if isinstance(raw, list) else [raw]
                    text = " ".join(t for t in (render_value(it, (self.owner or self.decl)["fqn"].rsplit(".", 1)[-1])
                                                for it in items) if t)
                    if text:
                        break
                vals = [text] if text else []
            elif flt == "keys":
                vals = []
                for term in _split_top(expr, "|"):
                    raw = (self.ann.get("args") or {}).get(term)
                    vals = [k for s in _string_leaves(raw) for k in _KEY.findall(s)]
                    if vals:
                        break
            else:
                text = self._alts(expr)
                vals = [text] if text else []
            if not vals:
                return []
            outs = [o + lit + v for o in outs for v in vals]
        return [o + template[pos:] for o in outs]

    def targets(self) -> List[str]:
        for template in self.rule["_targets"]:
            got = self.expand(template)
            if got:
                return got
        return []


# ------------------------------------------------------------------ application


def _owner_of(d: Dict, idx: _Index) -> Optional[Dict]:
    if d["kind"] in TYPE_KINDS:
        return d
    fqn = d["fqn"]
    return idx.types.get(fqn.split("#", 1)[0] if d["kind"] == "method" else fqn.rsplit(".", 1)[0])


def _source(d: Dict, owner: Optional[Dict]) -> str:
    if d["kind"] == "field" and owner:
        return owner["fqn"]
    return d["fqn"]


def _unmet(rule: Dict, owner: Optional[Dict]) -> bool:
    """`when.owner`: the rule needs one of these annotations on the owner class."""
    spec = (rule.get("when") or {}).get("owner")
    if not spec:
        return False
    return not (owner and any(ann_matches(a, _as_list(spec.get("fqn")), _as_list(spec.get("aliases")))
                              for a in owner.get("annotations") or ()))


def _arg_is(ann: Optional[Dict], spec: Dict) -> bool:
    """Every `arg: value` of `spec` holds on the annotation (`true` also matches the text "true")."""
    args = (ann or {}).get("args") or {}
    for key, want in spec.items():
        got = args.get(key)
        if got != want and not (isinstance(want, bool) and isinstance(got, str) and got.lower() == str(want).lower()):
            return False
    return True


def _blocked(rule: Dict, owner: Optional[Dict], rel: str, idx: _Index, ann: Optional[Dict] = None) -> bool:
    when = (rule.get("when") or {}).get("arg")
    if when and not _arg_is(ann, when):
        return True
    unless = rule.get("unless")
    if not unless:
        return False
    if unless.get("arg") and _arg_is(ann, unless["arg"]):
        return True
    spec = unless.get("owner") or {}
    if owner and any(ann_matches(a, _as_list(spec.get("fqn")), _as_list(spec.get("aliases")))
                     for a in owner.get("annotations") or ()):
        return True
    prefixes = tuple(unless.get("imports") or ())
    return bool(prefixes) and any(i.startswith(prefixes) for i in idx.imports.get(rel, ()))


class _Anchors:
    def __init__(self, repo: Optional[Path]) -> None:
        self.repo, self.lines = repo, {}

    def at(self, rel: str, line: int, text: str) -> Optional[Dict]:
        if self.repo is None:
            return {"file": rel, "line": line, "anchor": text}
        if rel not in self.lines:
            self.lines[rel] = read_lines(self.repo / rel)
        return build_anchor(rel, self.lines[rel], line - 1)


def _decl_sites(d: Dict) -> Iterable[Tuple[str, Dict, Optional[Dict]]]:
    for a in _flatten(d.get("annotations")):
        yield "decl", a, None
    for p in d.get("params") or ():
        for a in _flatten(p.get("annotations")):
            yield "param", a, p


def _on_for(d: Dict, role: str) -> str:
    if role == "param":
        return "param"
    return "class" if d["kind"] in TYPE_KINDS else d["kind"]


def _supertype_chain(t: Dict, idx: _Index) -> List[Dict]:
    out, seen, frontier = [], {t["fqn"]}, [t]
    for _ in range(INHERIT_DEPTH):
        nxt = []
        for cur in frontier:
            for s in cur.get("supertypes") or ():
                s = s.split("<", 1)[0]
                if s in idx.types and s not in seen:
                    seen.add(s)
                    nxt.append(idx.types[s])
        out += nxt
        frontier = nxt
        if not frontier:
            break
    return out


def apply(extraction: Dict, rules: Optional[Sequence[Dict]] = None, repo: Optional[Path] = None) -> Dict:
    """Emit every rule's edges into `extraction["rule_edges"]` and return the extraction.

    Pure function of the extraction (and the source lines for anchors): running it again, over
    `incremental_extract`'s output or a full scan's, gives the same result. Per-file `signals` and
    `io_edges` counts of Java files are recomputed, so rule output never accumulates."""
    rules = builtin_rules() if rules is None else list(rules)
    idx = _Index(extraction, rules)
    anchors = _Anchors(Path(repo) if repo is not None else None)
    edges: List[Dict] = []
    seen = set()
    fired: Dict[str, set] = {}
    deferred: List[Tuple] = []
    jpql_edges: List[Tuple] = []

    def emit(rule: Dict, site: Site, rel: str, module, line: int, end_text: str, source: str, owner_file: str) -> None:
        for target in site.targets() if rule["_targets"] else ():
            put(rule, rel, module, line, end_text, source, target, rule["emit"]["channel"], owner_file)
        sql = rule["emit"].get("sql")
        jpql = rule["emit"].get("dialect") == "jpql"
        hook = JPQL_HOOK if jpql else SQL_HOOK
        if sql and hook is not None:
            for text in site.expand(sql):
                for target, channel in hook(text):
                    if jpql:
                        jpql_edges.append((rule, rel, module, line, end_text, source, target, channel, owner_file))
                    else:
                        put(rule, rel, module, line, end_text, source, target, channel, owner_file)

    def put(rule, rel, module, line, text, source, target, channel, owner_file) -> None:
        key = (rule["id"], source, target, channel, rel, line)
        if key in seen:
            return
        anchor = anchors.at(rel, line, text)
        if anchor is None:
            return
        seen.add(key)
        edges.append({"source": source, "target": target, "channel": channel, "anchor": anchor,
                      "file": rel, "module": module, "rule": rule["id"]})
        if rule["emit"].get("signal"):
            fired.setdefault(owner_file, set()).add(rule["emit"]["signal"])
        fired.setdefault(owner_file + "\0channels", set()).add(channel)

    first_type: Dict[str, str] = {}
    for d in extraction.get("defines") or ():
        if d["kind"] in TYPE_KINDS and idx.lang(d.get("file")) in JVM_LANGS:
            cur = first_type.get(d["file"])
            if cur is None or (d["anchor"]["line"], d["fqn"]) < cur[0]:
                first_type[d["file"]] = ((d["anchor"]["line"], d["fqn"]), d["fqn"])

    for d in extraction.get("defines") or ():
        rel = d.get("file")
        if idx.lang(rel) not in JVM_LANGS:
            continue
        owner = _owner_of(d, idx)
        for role, ann, param in _decl_sites(d):
            on = _on_for(d, role)
            for rule, eff in idx.effective(ann, rel, on):
                if _blocked(rule, owner, rel, idx, eff) or _unmet(rule, owner):
                    continue
                if (rule.get("when") or {}).get("first_type") and (first_type.get(rel) or (0, None))[1] != d["fqn"]:
                    continue
                if rule.get("declared") is False:
                    continue
                site = Site(rule, eff, d, owner, idx.files.get(rel) or {}, resolve=idx.resolver(rel))
                job = (rule, site, rel, d.get("module"), eff.get("line") or ann.get("line"),
                       eff.get("text") or "", _source(d, owner), rel)
                if rule.get("fallback"):
                    deferred.append(job)
                else:
                    emit(*job)
        # implementations pick up inheritable annotations from their supertypes' methods
        if d["kind"] == "method" and owner and owner["kind"] in ("class", "enum", "record"):
            name = d["fqn"].split("#", 1)[1]
            for sup in _supertype_chain(owner, idx):
                for sm in idx.methods.get(sup["fqn"] + "#" + name, ()):
                    if len(sm.get("params") or ()) != len(d.get("params") or ()):
                        continue
                    srel = sm.get("file")
                    for role, ann, _ in _decl_sites(sm):
                        if role != "decl":
                            continue
                        for rule, eff in idx.effective(ann, srel, "method"):
                            if not rule.get("inherit") or _blocked(rule, sup, srel, idx, eff):
                                continue
                            if any(r is rule for a in _flatten(d.get("annotations"))
                                   for r, _e in idx.effective(a, rel, "method")):
                                continue        # the implementation declares its own
                            site = Site(rule, eff, sm, sup, idx.files.get(srel) or {})
                            emit(rule, site, srel, sm.get("module"), eff.get("line") or ann.get("line"),
                                 eff.get("text") or "", d["fqn"], rel)

    for job in deferred:
        rule, site, rel = job[0], job[1], job[2]
        if rule["emit"]["channel"] in fired.get(rel + "\0channels", ()):
            continue
        emit(*job)

    if jpql_edges:
        _jpql_to_tables(jpql_edges, edges, put)
    edges.sort(key=_edge_key)
    extraction["rule_edges"] = edges
    _refresh_counts(extraction, fired, rules)
    return extraction


def _entity_tables(edges: Sequence[Dict]) -> Dict[str, List[Tuple[str, str]]]:
    """Entity simple name -> `[(module, table)]`: the `table:` edge `@Entity` + `@Table(name=...)` make,
    whose source is the entity class."""
    out: Dict[str, List[Tuple[str, str]]] = {}
    for e in edges:
        if e.get("rule") == "jpa.entity" and e["target"].startswith("table:"):
            out.setdefault(e["source"].rsplit(".", 1)[-1], []).append((e["module"], e["target"][len("table:"):]))
    return out


def _jpql_to_tables(pending: List[Tuple], edges: List[Dict], put) -> None:
    """JPQL names entities. The `entity:` edge is emitted; when the entity's table is named in source
    (`@Table(name=...)`, same module preferred, never guessed between two tables) the `table:` edge is
    emitted too. A write whose table is known gives the `table:` edge only: an `entity:` persist edge
    is read as "persisted, no table named" by the data-model claims."""
    tables = _entity_tables(edges)
    for rule, rel, module, line, text, source, target, channel, owner_file in pending:
        cands = tables.get(target[len("entity:"):].rsplit(".", 1)[-1], [])
        pick = {t for m, t in cands if m == module} or {t for _m, t in cands}
        table = next(iter(pick)) if len(pick) == 1 else None
        if table is None or channel != "persist":
            put(rule, rel, module, line, text, source, target, channel, owner_file)
        if table is not None:
            put(rule, rel, module, line, text, source, "table:" + table, channel, owner_file)


def _refresh_counts(extraction: Dict, fired: Dict[str, set], rules: Sequence[Dict]) -> None:
    vocab = {r["emit"]["signal"] for r in [*rules, *builtin_rules()]
             if r["languages"] & JVM_LANGS and r["emit"].get("signal")}
    per_file: Dict[str, int] = {}
    for e in extraction.get("io_edges") or ():
        per_file[e["file"]] = per_file.get(e["file"], 0) + 1
    for e in extraction["rule_edges"]:
        per_file[e["file"]] = per_file.get(e["file"], 0) + 1
    for rel, info in (extraction.get("files") or {}).items():
        if info.get("language") not in JVM_LANGS:
            continue
        sig = (set(info.get("signals") or ()) - vocab) | fired.get(rel, set())
        info["signals"] = sorted(sig)
        info["io_edges"] = per_file.get(rel, 0)
    totals = extraction.get("totals")
    if totals is not None:
        totals["io_edges"] = len(extraction.get("io_edges") or ()) + len(extraction["rule_edges"])


def _edge_key(row: Dict):
    anchor = row.get("anchor") or {}
    return (str(row.get("source") or ""), str(row.get("target") or ""), str(row.get("channel") or ""),
            str(row.get("file") or ""), str(anchor.get("file") or ""), int(anchor.get("line") or 0))


def all_edges(extraction: Dict) -> List[Dict]:
    """`io_edges` plus the rule edges, in `io_edges`' own order. The one read path: no consumer
    indexes `extraction["io_edges"]` directly."""
    base = extraction.get("io_edges") or []
    extra = extraction.get("rule_edges") or []
    if not extra:
        return base
    return sorted([*base, *extra], key=_edge_key)


def edges_untagged(extraction: Dict) -> List[Dict]:
    """`all_edges` without the `rule` tag: the edge set as a repo with no rule table would have
    stored it, so a fold hash does not change when a fact moves from an extractor into a rule."""
    return [{k: v for k, v in e.items() if k != "rule"} if "rule" in e else e for e in all_edges(extraction)]


def legacy_view(extraction: Dict) -> Dict:
    """The extraction as stored before rules existed: rule edges folded into `io_edges`, untagged.
    The golden gate compares this view, so moving a fact from an extractor into a rule is
    byte-identical there while a changed edge still shows."""
    if "rule_edges" not in extraction:
        return extraction
    out = {k: v for k, v in extraction.items() if k != "rule_edges"}
    out["io_edges"] = edges_untagged(extraction)
    return out
