"""The extractor seam.

RESEARCH.md §9 names language coverage as a standing limitation: "the vocabulary
is intended to be language-independent; the detectors are not." This module is
where that separation is enforced. The channel vocabulary (§6.2), the claim
schema, and every downstream phase are language-neutral; everything that knows
what an `import` statement looks like lives behind `Extractor`.

Adding a language means adding one file to `cdp/lang/` and registering it. It
means touching nothing else.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from ..anchor import build_fact_anchor
from ..util import normalise_ws

# Import prefixes that are never internal to a repository. The resolve phase
# (§6.4) uses this to separate "third_party" from "unresolved": a use it cannot
# match against the global symbol table is only a finding if it looked like it
# should have matched.
THIRD_PARTY_PREFIXES: Tuple[str, ...] = (
    "java.", "javax.", "jakarta.", "jdk.", "sun.", "kotlin.", "scala.", "groovy.",
    "org.springframework.", "org.hibernate.", "org.apache.", "org.slf4j.",
    "org.junit.", "org.mockito.", "org.assertj.", "org.testng.", "org.quartz.",
    "org.json.", "org.yaml.", "org.w3c.", "org.xml.", "org.reactivestreams.",
    "com.google.", "com.fasterxml.", "com.codahale.", "com.jcraft.",
    "com.microsoft.", "com.amazonaws.", "com.azure.", "com.zaxxer", "com.sun.",
    "io.dropwizard.", "io.swagger.", "io.prometheus.", "io.netty.", "io.micrometer.",
    "io.reactivex.", "lombok.", "ch.qos.", "net.sf.", "reactor.", "graphql.",
    "software.amazon.", "feign.", "retrofit2.", "okhttp3.",
    # --- C# BCL and common libraries
    "System.", "Microsoft.", "Newtonsoft.", "AutoMapper.", "Serilog.",
    "FluentValidation.", "Xunit.", "Moq.", "NUnit.", "FluentAssertions.",
)

# Coarse per-language channel hints keyed on an import prefix. These are the
# §6.2 "signal" column, made machine-checkable. A hit produces an io_edge whose
# anchor is the import line itself, which is a genuinely citable fact: the file
# does import the thing.
IMPORT_CHANNEL_HINTS: Tuple[Tuple[str, str], ...] = (
    # --- JVM
    ("javax.ws.rs", "http_in"),
    ("jakarta.ws.rs", "http_in"),
    ("org.springframework.web.bind.annotation", "http_in"),
    ("io.dropwizard.jersey", "http_in"),
    ("javax.persistence", "persist"),
    ("jakarta.persistence", "persist"),
    ("org.springframework.data", "persist"),
    ("org.hibernate", "persist"),
    ("org.apache.http", "http_out"),
    ("okhttp3", "http_out"),
    ("retrofit2", "http_out"),
    ("java.net.http", "http_out"),
    ("org.springframework.web.client", "http_out"),
    ("com.jcraft.jsch", "ssh_exec"),
    ("org.quartz", "schedule"),
    ("io.dropwizard.jobs", "schedule"),
    ("org.springframework.scheduling", "schedule"),
    ("io.prometheus", "metric_emit"),
    ("com.codahale.metrics", "metric_emit"),
    ("io.micrometer", "metric_emit"),
    ("org.mapstruct", "map"),
    # --- Python
    ("flask", "http_in"),
    ("fastapi", "http_in"),
    ("django.urls", "http_in"),
    ("starlette", "http_in"),
    ("requests", "http_out"),
    ("httpx", "http_out"),
    ("aiohttp", "http_out"),
    ("urllib.request", "http_out"),
    ("sqlalchemy", "persist"),
    ("psycopg2", "persist"),
    ("pymysql", "persist"),
    ("pymongo", "persist"),
    ("django.db", "persist"),
    ("celery", "schedule"),
    ("apscheduler", "schedule"),
    ("paramiko", "ssh_exec"),
    ("prometheus_client", "metric_emit"),
    ("kafka", "event_publish"),
    ("pika", "event_publish"),
    # --- JS / TS
    ("express", "http_in"),
    ("fastify", "http_in"),
    ("koa", "http_in"),
    ("@nestjs/common", "http_in"),
    ("axios", "http_out"),
    ("node-fetch", "http_out"),
    ("got", "http_out"),
    ("typeorm", "persist"),
    ("sequelize", "persist"),
    ("mongoose", "persist"),
    ("@prisma/client", "persist"),
    ("pg", "persist"),
    ("node-cron", "schedule"),
    ("bull", "schedule"),
    ("kafkajs", "event_publish"),
    ("amqplib", "event_publish"),
    ("prom-client", "metric_emit"),
    # --- Go
    ("net/http", "http_out"),
    ("database/sql", "persist"),
    ("gorm.io/gorm", "persist"),
    ("github.com/gin-gonic/gin", "http_in"),
    ("github.com/gorilla/mux", "http_in"),
    ("golang.org/x/crypto/ssh", "ssh_exec"),
    ("github.com/prometheus/client_golang", "metric_emit"),
    # --- C# (verified against $TARGET_REPO's actual `using` directives,
    # PHASE/FINDINGS.md F2 -- not guessed)
    ("Microsoft.AspNetCore.Mvc", "http_in"),
    ("Microsoft.AspNetCore.Routing", "http_in"),
    ("Microsoft.EntityFrameworkCore", "persist"),
    ("System.Net.Http", "http_out"),
    ("Hangfire", "schedule"),
)


@dataclass
class FileFacts:
    """Everything one extractor learned about one file.

    Deliberately flat and JSON-shaped: these fields feed `defines[]`, `uses[]`
    and `io_edges[]` in the patch schema directly, so an extractor bug shows up
    as bad JSON rather than as a bad object graph.
    """

    path: str
    language: str
    loc: int = 0
    package: Optional[str] = None
    # The symbol this file is "about" — the type the data-flow graph uses as the
    # node for anything declared here. Without it a `call` edge would have to be
    # drawn from a file path, and paths are not symbols.
    primary: Optional[str] = None
    imports: List[Dict] = field(default_factory=list)
    defines: List[Dict] = field(default_factory=list)
    uses: List[Dict] = field(default_factory=list)
    io_edges: List[Dict] = field(default_factory=list)
    signals: List[str] = field(default_factory=list)
    # Declared build dependencies, for build manifests only (§5.2 declared arm).
    declared_deps: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)


@dataclass
class ExtractContext:
    path: str
    lines: List[str]
    module: str


class Extractor:
    """Base class. Subclasses set `language` and either `extensions` or `names`."""

    language: str = "unknown"
    extensions: Tuple[str, ...] = ()
    names: Tuple[str, ...] = ()
    role: str = "source"

    def extract(self, ctx: ExtractContext) -> FileFacts:  # pragma: no cover - abstract
        raise NotImplementedError


# ------------------------------------------------------------------ helpers


def anchor_at(ctx: ExtractContext, index: int) -> Optional[Dict]:
    """A deterministic fact cites its line exactly (`build_fact_anchor`): never None on a
    non-blank line, so a call on a line repeated many times is kept, not dropped."""
    return build_fact_anchor(ctx.path, ctx.lines, index)


class Ann(tuple):
    """One annotation (Java) or attribute (C#): `(name, text)` like the plain tuples it
    replaces, so `for name, text in anns` still reads it, plus the 0-based `line` and
    `end_line` it spans, so the index can cite the annotation and not just its owner."""

    def __new__(cls, name: str, text: str, line: int, end_line: int,
                arg_map: Optional[Dict] = None) -> "Ann":
        self = tuple.__new__(cls, (name, text))
        self.line, self.end_line = line, end_line
        self.arg_map: Dict = arg_map or {}   # parsed element values (annotation_args.py)
        self.parses_args = True             # False: the language never parses element values (Python)
        self.fqn: Optional[str] = None      # set by the language extractor when imports resolve it
        return self


#: Longest annotation text kept on a define row; a longer one (a multi-line `@Query`) is cut
#: with `...`, and its cited lines hold the rest.
ANNOTATION_TEXT_MAX = 400
EMPTY_PARENS = re.compile(r"^[^()]*\(\s*\)$")


def annotation_rows(anns: Sequence) -> List[Dict]:
    """The `annotations` a define row carries: name, source text, 1-based line span."""
    rows = []
    for ann in anns:
        name, text = ann[0], re.sub(r"\s*\n\s*", " ", ann[1]).strip()   # strings stay exact
        if len(text) > ANNOTATION_TEXT_MAX:
            text = text[:ANNOTATION_TEXT_MAX - 3] + "..."
        row = {"name": name}
        if isinstance(ann, Ann) and ann.fqn:
            row["fqn"] = ann.fqn
        row["text"] = text
        if isinstance(ann, Ann):
            row["line"], row["end_line"] = ann.line + 1, ann.end_line + 1
            if ann.arg_map:
                row["args"] = ann.arg_map
            elif ann.parses_args and EMPTY_PARENS.match(text):
                row["args"] = {}   # `@A()` is not `@A` (owner decision X24)
        rows.append(row)
    return rows


def mk_define(fqn: str, kind: str, visibility: str, anchor: Dict, value: Optional[str] = None,
              end_line: Optional[int] = None, annotations: Sequence = ()) -> Dict:
    row = {"fqn": fqn, "kind": kind, "visibility": visibility, "anchor": anchor}
    if value is not None:
        row["value"] = value
    if end_line is not None:
        row["end_line"] = end_line
    if annotations:
        row["annotations"] = annotation_rows(annotations)
    return row


def mk_use(fqn: str, anchor: Dict, via_import: bool = False, resolved: str = "external",
           access: Optional[str] = None, value: Optional[str] = None) -> Dict:
    """`access`/`value` (state evidence, `state_access`) are set only when given: every other row
    keeps exactly its four keys."""
    row = {"fqn": fqn, "resolved": resolved, "via_import": via_import, "anchor": anchor}
    if access is not None:
        row["access"], row["value"] = access, value
    return row


# ------------------------------------------------------------- state evidence
# A `Type.NAME` reference (an enum value, once resolve confirms the target) is classified from the
# tokens around it: `write` (assignment, named/initializer arg, setter-named call), `guard` (`==`/`!=`,
# `equals`, `case`/`is` pattern, membership in a literal set), else `read`. A call argument also
# carries `arg` = [callee, callee line, opener index, position, name] so resolve can name the
# parameter (constructor arg into a status field) and pair `(new, old)` transitions.
STATE_SETTER = re.compile(r"^(?:set|with|update|change|mark|move|transition)\w*?(?:status|state|phase)\w*$", re.I)
STATE_GUARD_CALLS = frozenset(("contains", "Contains", "containsAll", "equals", "Equals", "inSet", "inSetBind",
                               "isIn", "notIn", "in", "oneOf"))
STATE_GUARD_SUFFIX = re.compile(r"^[A-Z]\w*In$")          # `new WorkflowStatusIn(List(..))`
STATE_SETS = frozenset(("Set", "Seq", "List", "Vector", "Array", "of", "asList", "EnumSet", "HashSet",
                        "listOf", "setOf"))
STATE_MEMBER_TEST = frozenset(("contains", "Contains", "containsAll", "includes"))
STATE_THRU = frozenset(("toString", "ToString", "name", "ordinal", "id"))   # `S.A.toString == x` is still S.A
_DECL_KW = frozenset(("val", "var", "def", "let", "const", "final", "readonly", "lazy"))
_NOT_ASSIGN = frozenset(("=", "!", "<", ">", "+", "-", "*", "/", "%", "&", "|", "^", "?", ":"))


def _opener(tk, i: int) -> int:
    """Index of the unclosed bracket enclosing token `i`, or -1 (a bounded backward walk)."""
    j, steps = i - 1, 0
    while j >= 0 and steps < 400:
        if tk.kind[j] == "op":
            t = tk.text[j]
            if t in (")", "]", "}") and 0 <= tk.match[j] < j:
                j = tk.match[j]
            elif t in ("(", "[", "{"):
                return j
        j -= 1
        steps += 1
    return -1


def _qual_start(tk, i: int) -> int:
    while tk.at(i - 1) == "." and tk.is_id(i - 2):
        i -= 2
    return i


def _callee(tk, o: int) -> Tuple[Optional[str], int]:
    c = o - 1
    if tk.at(c) == "]" and 0 <= tk.match[c] < c:       # `f[T](..)`
        c = tk.match[c] - 1
    return (tk.text[c], c) if tk.is_id(c) else (None, -1)


def _is_guard_call(name: Optional[str]) -> bool:
    return bool(name) and (name in STATE_GUARD_CALLS or bool(STATE_GUARD_SUFFIX.match(name)))


def _arg_pos(tk, o: int, s: int) -> int:
    pos, j = 0, o + 1
    while j < s:
        if tk.kind[j] == "op" and tk.text[j] in ("(", "[", "{") and tk.match[j] > j:
            j = tk.match[j]
        elif tk.text[j] == ",":
            pos += 1
        j += 1
    return pos


def state_access(tk, s: int, e: int, lang: str) -> Tuple[str, Optional[List]]:
    """(`write`|`guard`|`read`, arg) for the reference whose qualifier starts at token `s` and whose
    value name is token `e`. Only token shapes are read; anything else is `read`."""
    s = _qual_start(tk, s)
    q = e + 1
    while tk.at(q) in (".", "?.") and tk.at(q + 1) in STATE_THRU:
        q += 2
        if tk.at(q) == "(" and tk.at(q + 1) == ")":
            q += 2
    p = s - 1
    if tk.at(p) == "(" and tk.at(p - 1) == "nameof" and tk.at(q) == ")":   # C# `x == nameof(S.A)`
        p, q = p - 2, q + 1
    pt, qt = tk.at(p), tk.at(q)
    if (pt == "=" and tk.at(p - 1) in ("=", "!")) or (qt in ("=", "!") and tk.at(q + 1) == "="):
        return "guard", None
    if qt in (".", "?.") and tk.at(q + 1) in ("equals", "Equals") or (lang == "cs" and qt == "=>" and pt in ("{", ",")):
        return "guard", None
    b = p
    while tk.at(b) == "|" or (lang == "cs" and tk.at(b) in ("or", "and", "not")):
        if tk.at(b) == "not" or not tk.is_id(b - 1):
            b -= 1
            continue
        b = _qual_start(tk, b - 1) - 1
    if tk.at(b) == "case" or (lang == "cs" and tk.at(b) == "is"):
        return "guard", None
    named = None
    if (pt == "=" and tk.at(p - 1) not in _NOT_ASSIGN) or (lang == "cs" and pt == ":"):
        n = p - 1
        if not tk.is_id(n):
            return "read", None
        before = tk.at(n - 1)
        o = _opener(tk, n)
        if before in ("(", ",") and o >= 0 and tk.text[o] == "(":
            named = tk.text[n]
        elif pt == ":":
            return "read", None
        elif before in _DECL_KW or before in (":", ">", "]", "?") or (tk.is_id(n - 1) and before != "this"):
            return "read", None                            # a declaration: `val s = ..`, `Status s = ..`
        else:
            return "write", None
    elif pt in ("(", ",", "{") and qt in (")", ",", "}"):
        o = p if pt in ("(", "{") else _opener(tk, s)
    else:
        return "read", None
    if o < 0:
        return "read", None
    close = tk.close(o)
    member_test = tk.at(close + 1) in (".", "?.") and tk.at(close + 2) in STATE_MEMBER_TEST
    if tk.text[o] == "{":                                  # C# `new[] { A, B }.Contains(x)`
        return ("guard" if member_test else "read"), None
    callee, ci = _callee(tk, o)
    if callee is None or callee == "nameof":
        return "read", None
    if _is_guard_call(callee):
        return "guard", None
    if STATE_SETTER.match(callee):
        return "write", None
    if callee in STATE_SETS and named is None:
        o2 = _opener(tk, _qual_start(tk, ci))
        if member_test or (o2 >= 0 and tk.text[o2] == "(" and _is_guard_call(_callee(tk, o2)[0])):
            return "guard", None
        return "read", None
    ctor = callee[:1].isupper() or callee == "copy" or tk.at(ci - 1) == "new"
    if named is not None and ctor:
        return "write", [callee, tk.line[ci] + 1, o, None, named]
    return "read", [callee, tk.line[ci] + 1, o, None if named else _arg_pos(tk, o, s), named]


def mark_state(rows: Sequence[Dict], tk, s: int, e: int, value: str, lang: str) -> None:
    """Annotate the `kind: type` row the qualifier at token `s` emitted with the value token `e` names."""
    if tk.at(e + 1) in ("(", "[") or tk.at(e + 1) == "." and tk.is_id(e + 2) and tk.at(e + 2) not in STATE_THRU \
            and tk.at(e + 2) not in ("equals", "Equals"):
        return
    for row in rows:
        if row.get("kind") == "type" and "access" not in row:
            access, arg = state_access(tk, s, e, lang)
            row["access"], row["value"] = access, value
            if arg:
                row["arg"] = arg
            return


def mk_edge(source: str, target: str, channel: str, anchor: Dict) -> Dict:
    return {"source": source, "target": target, "channel": channel, "anchor": anchor}


def channel_for_import(fqn: str) -> Optional[str]:
    """Longest-prefix match against IMPORT_CHANNEL_HINTS. Longest wins so that
    `org.springframework.data` beats a hypothetical `org.springframework` entry.
    """
    best: Optional[Tuple[int, str]] = None
    for prefix, channel in IMPORT_CHANNEL_HINTS:
        if fqn == prefix or fqn.startswith(prefix + ".") or fqn.startswith(prefix + "/"):
            if best is None or len(prefix) > best[0]:
                best = (len(prefix), channel)
    return best[1] if best else None


def is_third_party(fqn: str) -> bool:
    return any(fqn.startswith(p) for p in THIRD_PARTY_PREFIXES)


def strip_block_comments(lines: Sequence[str]) -> List[str]:
    """Blank out /* ... */ and // and # comment bodies, preserving line count.

    Line count preservation is not a nicety: every anchor in the run is a line
    number into the *original* file, so an extractor that reads a compacted copy
    would cite locations that do not exist.

    A `//` or `/*` inside a string literal is not a comment: `"http://host/x"`
    must survive intact, or every URL in the file is truncated at the scheme.
    """
    out: List[str] = []
    in_block = False
    for line in lines:
        result: List[str] = []
        i = 0
        quote = ""
        n = len(line)
        while i < n:
            if in_block:
                end = line.find("*/", i)
                if end == -1:
                    i = n
                else:
                    in_block = False
                    i = end + 2
                continue
            ch = line[i]
            if quote:
                result.append(ch)
                if ch == "\\" and i + 1 < n:
                    result.append(line[i + 1])
                    i += 1
                elif ch == quote:
                    quote = ""
                i += 1
                continue
            if ch in ('"', "'"):
                quote = ch
                result.append(ch)
                i += 1
                continue
            if line.startswith("/*", i):
                in_block = True
                i += 2
                continue
            if line.startswith("//", i):
                break
            result.append(ch)
            i += 1
        out.append("".join(result))
    return out


STRING_LITERAL = re.compile(r'"([^"\\]*(?:\\.[^"\\]*)*)"')


def first_string_literal(text: str) -> Optional[str]:
    m = STRING_LITERAL.search(text)
    return m.group(1) if m else None


def count_loc(lines: Sequence[str]) -> int:
    """Non-blank lines. Blank-line counts vary with formatter settings and would
    make the leaf budget in §3.3 a function of code style rather than content.
    """
    return sum(1 for line in lines if normalise_ws(line))


def mask_string_literals(line: str) -> str:
    """Blank out `"..."`/`'...'` contents so a brace inside a string literal
    (a message format, a route path) never shifts brace-depth nesting.

    Shared across extractors that track type/member nesting by counting
    braces per line (`java.py`'s original private `_mask_literals`,
    generalised here for `csharp.py` and `scala.py` to reuse without either
    depending on `java.py`).
    """
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
