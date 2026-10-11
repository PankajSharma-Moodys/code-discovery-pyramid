"""C# declarations from tokens: namespaces, usings, types, members at every access level.

The line-regex extractor this replaces indexed only `public` methods whose whole signature sat on
one line, so private/internal/protected members, generic `M<T>` and tuple-returning methods,
constructors, properties, and every member of a type with a long primary constructor were lost.
This reads declarations the way the grammar does. Method bodies, property accessors and field
initialisers are kept as token spans for `csharp_body`.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Set, Tuple

from .csharp_tokens import CsTokens
from .java_decl import JMember, JType, join_tokens

MODIFIERS = frozenset([
    "public", "private", "protected", "internal", "static", "abstract", "virtual", "override", "sealed",
    "async", "readonly", "const", "new", "partial", "extern", "unsafe", "volatile", "required", "file",
    "event", "fixed", "implicit", "explicit", "ref",
])
TYPE_KW = ("class", "struct", "interface", "enum")
NOT_TYPE = frozenset([
    "new", "return", "throw", "else", "case", "default", "if", "for", "foreach", "while", "do", "switch",
    "try", "catch", "finally", "break", "continue", "using", "lock", "yield", "await", "is", "as", "in",
    "out", "this", "base", "typeof", "sizeof", "checked", "unchecked", "goto", "operator", "class",
    "struct", "interface", "enum", "namespace", "where", "when", "fixed", "stackalloc", "get", "set",
    "init", "add", "remove",
])
NOT_TYPE = NOT_TYPE - frozenset(["get", "set", "init", "add", "remove", "when", "where"])
STOP_ANGLE = frozenset([";", "{", "}", "=", "|", "!", "+", "-", "*", "/", "%", ")", "&"])
OPS = frozenset(["+", "-", "*", "/", "%", "&", "|", "^", "!", "~", "<", ">", "=", "==", "!=", "true", "false"])


class CMember(JMember):
    __slots__ = ("prop", "bodies", "ctor_init", "ext", "explicit", "nodef")

    def __init__(self, kind: str, name: str, owner: "CType") -> None:
        super().__init__(kind, name, owner)
        self.prop = False
        self.bodies: List[Tuple[int, int]] = []
        self.ctor_init: Optional[Tuple[int, int, str]] = None   # args span, "base"/"this"
        self.ext = ""
        self.explicit = ""
        self.nodef = False

    @property
    def visibility(self) -> str:
        for v in ("public", "private", "protected", "internal"):
            if v in self.mods:
                return v
        if self.owner.kind == "interface":
            return "public"
        return "private"

    @property
    def symbol(self) -> str:
        if self.kind == "ctor":
            return self.owner.fqn + "#<init>"
        if self.kind in ("method", "op"):
            return self.owner.fqn + "#" + self.name
        return self.owner.fqn + "." + self.name


class CType(JType):
    __slots__ = ("ns", "pparams", "bases", "partial", "delegate_params", "primary_line")

    def __init__(self, kind: str, name: str, fqn: str, outer: Optional["CType"]) -> None:
        super().__init__(kind, name, fqn, outer)
        self.ns = ""
        self.pparams: Optional[List[Tuple[str, str]]] = None
        self.bases: List[str] = []
        self.partial = False
        self.primary_line = 0

    @property
    def visibility(self) -> str:
        for v in ("public", "private", "protected", "internal"):
            if v in self.mods:
                return v
        return "private" if self.outer is not None else "internal"


class Using:
    __slots__ = ("name", "static", "alias", "line", "glob")

    def __init__(self, name: str, static: bool, alias: str, line: int, glob: bool) -> None:
        self.name, self.static, self.alias, self.line, self.glob = name, static, alias, line, glob


def skip_angle(tk: CsTokens, i: int) -> Optional[int]:
    """Index just past the `<...>` at `i` when it is a type-argument/parameter list, else None."""
    depth = 0
    j = i
    while j < tk.n:
        t, k = tk.text[j], tk.kind[j]
        if k == "op":
            if t == "<":
                depth += 1
            elif t == ">":
                depth -= 1
                if depth == 0:
                    return j + 1
            elif t == "(":
                j = tk.close(j)
            elif t in STOP_ANGLE or t in ("=>", "&&", "||", "==", "?."):
                return None
        elif k in ("str", "chr", "num"):
            return None
        j += 1
        if j - i > 150:
            return None
    return None


def parse_type(tk: CsTokens, i: int) -> Optional[Tuple[int, str]]:
    """(end index, normalised text) of the type at `i`. Nullable `?` is dropped, tuples become
    `ValueTuple<..>`, multi-dimensional arrays `[]`."""
    j = i
    while tk.at(j) in ("ref", "readonly", "scoped", "in", "out", "params") and tk.kind[j] == "id":
        j += 1
    start = j
    parts: List[str] = []
    if tk.at(j) == "(":
        c = tk.close(j)
        elems: List[str] = []
        k = j + 1
        while k < c:
            r = parse_type(tk, k)
            if r is None:
                return None
            e, text = r
            elems.append(text)
            if tk.is_id(e) and tk.at(e + 1) in (",", ")"):
                e += 1
            if e < c and tk.at(e) != ",":
                return None
            k = e + 1
        if len(elems) < 2:
            return None
        parts.append("ValueTuple<%s>" % ",".join(elems))
        j = c + 1
    else:
        while True:
            if tk.at(j) == "global" and tk.at(j + 1) == "::":
                j += 2
            if not tk.is_id(j) or tk.text[j] in NOT_TYPE:
                return None
            name = tk.text[j]
            j += 1
            if tk.at(j) == "::":
                j += 1
                continue
            if tk.at(j) == "<":
                k = skip_angle(tk, j)
                if k is None:
                    return None
                args = _type_args(tk, j, k)
                name += "<%s>" % ",".join(args) if args is not None else ""
                j = k
            parts.append(name)
            if tk.at(j) == "." and tk.is_id(j + 1):
                j += 1
                parts.append(".")
                continue
            break
    text = "".join(parts)
    while True:
        if tk.at(j) == "?" and tk.at(j + 1) not in ("?",):
            j += 1
        elif tk.at(j) == "[" and tk.at(tk.close(j)) == "]" and all(
                tk.text[q] == "," for q in range(j + 1, tk.close(j))):
            j = tk.close(j) + 1
            text += "[]"
        elif tk.at(j) == "*" and tk.is_id(j + 1) and tk.at(j + 2) in ("=", ";", ",", ")"):
            j += 1
        else:
            break
    return j, text


def _type_args(tk: CsTokens, a: int, b: int) -> Optional[List[str]]:
    out: List[str] = []
    k = a + 1
    while k < b - 1:
        if tk.at(k) == ",":
            k += 1
            continue
        r = parse_type(tk, k)
        if r is None:
            # `Foo<>` / `Dictionary<,>` unbound
            k += 1
            continue
        k, text = r
        out.append(text)
    return out


def tparam_names(tk: CsTokens, i: int, end: int) -> List[str]:
    names: List[str] = []
    depth = 0
    expect = True
    for j in range(i, end):
        t = tk.text[j]
        if t == "<":
            depth += 1
            expect = depth == 1
        elif t == ">":
            depth -= 1
        elif t == "," and depth == 1:
            expect = True
        elif expect and depth == 1 and tk.kind[j] == "id" and t not in ("in", "out"):
            names.append(t)
            expect = False
    return names


class DeclParser:
    def __init__(self, tk: CsTokens) -> None:
        self.tk = tk
        self.types: List[CType] = []
        self.usings: List[Using] = []
        self.top_spans: List[Tuple[int, int]] = []
        self.top_ns = ""
        self.namespaces: List[Tuple[str, int]] = []

    # ----------------------------------------------------------- top level

    def parse(self) -> List[CType]:
        self._unit(0, self.tk.n, "")
        return self.types

    def _unit(self, i: int, end: int, ns: str) -> None:
        tk = self.tk
        while i < end:
            t = tk.text[i]
            if t == ";" and tk.kind[i] == "op":
                i += 1
                continue
            if tk.kind[i] == "id" and t == "extern" and tk.at(i + 1) == "alias":
                i = self._skip_stmt(i, end)
                continue
            if tk.kind[i] == "id" and (t == "using" or (t == "global" and tk.at(i + 1) == "using")):
                nxt = self._using(i, end)
                if nxt is not None:
                    i = nxt
                    continue
            if tk.kind[i] == "id" and t == "namespace":
                j = i + 1
                name = ""
                while tk.is_id(j) or tk.at(j) == ".":
                    name += tk.text[j]
                    j += 1
                full = (ns + "." + name) if ns else name
                self.namespaces.append((full, tk.line[i]))
                if tk.at(j) == ";":
                    ns = full
                    self.top_ns = full
                    i = j + 1
                    continue
                if tk.at(j) == "{":
                    c = tk.close(j)
                    self._unit(j + 1, c, full)
                    i = c + 1
                    continue
                i = j
                continue
            start = i
            mods, anns, j = self._modifiers(i)
            if j > i and tk.kind[j] == "id" and tk.text[j] in ("namespace", "using") and not mods:
                i = j   # `[assembly: X]` before a directive
                continue
            nxt = self._type_decl(j, None, mods, anns, ns, end)
            if nxt is not None:
                i = nxt
                continue
            # a top-level statement
            e = self._skip_stmt(start, end)
            self.top_spans.append((start, e))
            self.top_ns = self.top_ns or ns
            i = e

    def _skip_stmt(self, i: int, end: int) -> int:
        tk = self.tk
        j = i
        while j < end:
            t = tk.text[j]
            if tk.kind[j] == "op" and t in "([":
                j = tk.close(j) + 1
                continue
            if tk.kind[j] == "op" and t == "{":
                c = tk.close(j)
                nxt = tk.at(c + 1)
                if nxt in ("else", "catch", "finally", "while") and tk.kind[c + 1] == "id":
                    j = c + 1
                    continue
                if tk.at(c + 1) in (";", ")", ",", "."):
                    j = c + 1
                    continue
                return c + 1
            if t == ";" and tk.kind[j] == "op":
                return j + 1
            j += 1
        return end

    def _using(self, i: int, end: int) -> Optional[int]:
        tk = self.tk
        j = i
        glob = False
        if tk.at(j) == "global":
            glob = True
            j += 1
        j += 1  # using
        static = False
        alias = ""
        if tk.at(j) == "static":
            static = True
            j += 1
        if tk.is_id(j) and tk.at(j + 1) == "=":
            alias = tk.text[j]
            j += 2
        a = j
        while j < end and tk.text[j] != ";":
            if tk.at(j) in ("(", "{") or (tk.at(j) == "=" and not alias):
                return None   # a using statement / declaration, not a directive
            j += 1
        name = join_tokens(tk, a, j)
        if "<" in name:
            name = name.split("<", 1)[0]
        self.usings.append(Using(name, static, alias, tk.line[i], glob))
        return j + 1

    # ------------------------------------------------------------ modifiers

    def _attr_list(self, i: int, anns: List[Tuple[str, str]]) -> int:
        tk = self.tk
        c = tk.close(i)
        j = i + 1
        if tk.is_id(j) and tk.at(j + 1) == ":" and tk.at(j) in (
                "assembly", "module", "return", "field", "property", "method", "param", "type", "event"):
            j += 2
        a = j
        depth = 0
        while j <= c:
            t = tk.text[j] if j < c else ","
            if tk.kind[j] == "op" and t in "([{":
                j = tk.close(j)
            elif t == "," or j == c:
                if j > a:
                    name_i = a
                    name = ""
                    while tk.is_id(name_i):
                        name = tk.text[name_i]
                        if tk.at(name_i + 1) == ".":
                            name_i += 2
                            continue
                        break
                    if name.endswith("Attribute") and len(name) > 9:
                        name = name[:-9]
                    anns.append((name, join_tokens(tk, a, j)))
                a = j + 1
            j += 1
        return c + 1

    def _modifiers(self, i: int) -> Tuple[Set[str], List[Tuple[str, str]], int]:
        tk = self.tk
        mods: Set[str] = set()
        anns: List[Tuple[str, str]] = []
        while i < tk.n:
            t = tk.text[i]
            if t == "[" and tk.kind[i] == "op":
                i = self._attr_list(i, anns)
            elif tk.kind[i] == "id" and t in MODIFIERS and tk.at(i + 1) not in (".", "=", ";", ",", "{"):
                if t == "ref" and not (tk.at(i + 1) in ("struct", "partial", "readonly", "record")):
                    break   # `ref T Method()`: part of the return type
                if t == "readonly" and tk.at(i + 1) not in ("struct", "record", "partial", "ref"):
                    mods.add(t)
                    i += 1
                    continue
                if t == "new" and tk.at(i + 1) in ("(", "["):
                    break
                mods.add(t)
                i += 1
            else:
                break
        return mods, anns, i

    # ---------------------------------------------------------------- types

    def _type_decl(self, i: int, outer: Optional[CType], mods: Set[str], anns, ns: str,
                   end: int) -> Optional[int]:
        tk = self.tk
        t = tk.at(i)
        kind = None
        name_i = -1
        if i < tk.n and tk.kind[i] == "id":
            if t in TYPE_KW and tk.is_id(i + 1):
                kind, name_i = t, i + 1
            elif t == "record":
                j = i + 1
                if tk.at(j) in ("class", "struct"):
                    j += 1
                if tk.is_id(j) and tk.at(j + 1) in ("(", "<", "{", ":", ";"):
                    kind, name_i = "record", j
            elif t == "delegate":
                return self._delegate(i, outer, mods, anns, ns, end)
        if kind is None:
            return None
        name = tk.text[name_i]
        if outer is not None:
            fqn = outer.fqn + "." + name
        else:
            fqn = (ns + "." + name) if ns else name
        jt = CType(kind, name, fqn, outer)
        jt.ns = ns
        jt.mods, jt.anns = mods, anns
        jt.partial = "partial" in mods
        jt.line = tk.line[name_i]
        jt.start_line = tk.line[i]
        j = name_i + 1
        if tk.at(j) == "<":
            k = skip_angle(tk, j)
            if k:
                jt.tparams = tparam_names(tk, j, k)
                j = k
        if tk.at(j) == "(" and kind in ("class", "struct", "record"):
            c = tk.close(j)
            jt.pparams = self._params(j + 1, c)
            jt.primary_line = tk.line[j]
            j = c + 1
        if tk.at(j) == ":":
            j += 1
            while j < end and tk.at(j) not in ("{", ";") and tk.text[j] != "where":
                r = parse_type(tk, j)
                if r is None:
                    j += 1
                    continue
                j, text = r
                jt.bases.append(text)
                if tk.at(j) == "(":
                    j = tk.close(j) + 1
                if tk.at(j) == ",":
                    j += 1
        while j < end and tk.at(j) not in ("{", ";"):
            if tk.kind[j] == "op" and tk.text[j] in "([":
                j = tk.close(j)
            j += 1
        if jt.bases:
            if kind in ("class", "record") and not _looks_interface(jt.bases[0]):
                jt.extends.append(jt.bases[0])
                jt.implements.extend(jt.bases[1:])
            else:
                jt.implements.extend(jt.bases)
        jt.static = "static" in mods
        if outer is not None:
            outer.types.append(jt)
        self.types.append(jt)
        if tk.at(j) != "{":
            jt.end_line = tk.line[min(j, tk.n - 1)]
            jt.body = (j, j)
            return j + 1
        close = tk.close(j)
        jt.body = (j + 1, close)
        jt.end_line = tk.line[close]
        if kind == "enum":
            self._enum_members(jt, j + 1, close)
        else:
            self._members(jt, j + 1, close)
        return close + 1

    def _delegate(self, i, outer, mods, anns, ns, end) -> Optional[int]:
        tk = self.tk
        r = parse_type(tk, i + 1)
        if r is None or not tk.is_id(r[0]):
            return None
        j, ret = r
        name = tk.text[j]
        fqn = (outer.fqn + "." + name) if outer else ((ns + "." + name) if ns else name)
        jt = CType("delegate", name, fqn, outer)
        jt.ns, jt.mods, jt.anns = ns, mods, anns
        jt.line = jt.start_line = tk.line[j]
        j += 1
        if tk.at(j) == "<":
            k = skip_angle(tk, j)
            if k:
                jt.tparams = tparam_names(tk, j, k)
                j = k
        while j < end and tk.at(j) != ";":
            if tk.kind[j] == "op" and tk.text[j] in "([":
                j = tk.close(j)
            j += 1
        jt.end_line = tk.line[min(j, tk.n - 1)]
        jt.body = (j, j)
        if outer is not None:
            outer.types.append(jt)
        self.types.append(jt)
        return j + 1

    def _enum_members(self, jt: CType, i: int, end: int) -> None:
        tk = self.tk
        while i < end:
            anns: List = []
            while tk.at(i) == "[":
                i = self._attr_list(i, anns)
            if not tk.is_id(i):
                i += 1
                continue
            m = CMember("enum_const", tk.text[i], jt)
            m.mods = {"public", "static"}
            m.static = True
            m.ftype = jt.fqn
            m.line = m.start_line = tk.line[i]
            m.anns = anns
            i += 1
            if tk.at(i) == "=":
                a = i + 1
                while i < end and tk.at(i) != ",":
                    if tk.kind[i] == "op" and tk.text[i] in "([{":
                        i = tk.close(i)
                    i += 1
                m.init = (a, i)
            m.end_line = tk.line[min(i, tk.n - 1)]
            jt.members.append(m)
            if tk.at(i) == ",":
                i += 1

    # -------------------------------------------------------------- members

    def _members(self, jt: CType, i: int, end: int) -> None:
        tk = self.tk
        while i < end:
            if tk.text[i] == ";" and tk.kind[i] == "op":
                i += 1
                continue
            start = i
            mods, anns, i = self._modifiers(i)
            nxt = self._type_decl(i, jt, mods, anns, jt.ns, end)
            if nxt is not None:
                i = nxt
                continue
            if i >= end:
                break
            if tk.at(i) == "~" and tk.is_id(i + 1):
                i = self._skip_member(i, end)
                continue
            if tk.at(i) in ("implicit", "explicit") or (
                    tk.at(i) == "operator"):
                i = self._operator(jt, start, i, mods, anns, end)
                continue
            if tk.is_id(i) and tk.at(i + 1) == "(" and tk.text[i] == jt.name:
                i = self._method(jt, start, i, mods, anns, [], None, "ctor", end)
                continue
            r = parse_type(tk, i)
            if r is None:
                i = self._recover(i, end)
                continue
            j, rtype = r
            if tk.at(j) == "operator":
                i = self._operator(jt, start, j, mods, anns, end)
                continue
            explicit = ""
            if tk.at(j) == "this" and tk.at(j + 1) == "[":
                i = self._indexer(jt, start, j, rtype, mods, anns, end)
                continue
            if not tk.is_id(j):
                i = self._recover(i, end)
                continue
            name_i = j
            # explicit interface implementation: `void IFoo.Bar()` / `IFoo<T>.Bar`
            while True:
                k = name_i + 1
                if tk.at(k) == "<":
                    k2 = skip_angle(tk, k)
                    if k2 and tk.at(k2) == ".":
                        k = k2
                if tk.at(k) == "." and tk.is_id(k + 1):
                    explicit = explicit or tk.text[name_i]
                    name_i = k + 1
                    continue
                if tk.at(k) == "." and tk.at(k + 1) == "this" and tk.at(k + 2) == "[":
                    name_i = -1
                break
            if name_i < 0:
                i = self._recover(i, end)
                continue
            tparams: List[str] = []
            after = name_i + 1
            if tk.at(after) == "<":
                k = skip_angle(tk, after)
                if k and tk.at(k) == "(":
                    tparams = tparam_names(tk, after, k)
                    after = k
            if tk.at(after) == "(":
                i = self._method(jt, start, name_i, mods, anns, tparams, rtype, "method", end,
                                 open_i=after, explicit=explicit)
            elif tk.at(after) == "{" or tk.at(after) == "=>":
                i = self._property(jt, start, name_i, rtype, mods, anns, end)
            else:
                i = self._fields(jt, start, name_i, rtype, mods, anns, end)

    def _recover(self, i: int, end: int) -> int:
        tk = self.tk
        j = i
        while j < end and tk.text[j] != ";":
            if tk.kind[j] == "op" and tk.text[j] in "([{":
                c = tk.close(j)
                if tk.text[j] == "{" :
                    return c + 1
                j = c
            j += 1
        return max(j + 1, i + 1)

    def _skip_member(self, i: int, end: int) -> int:
        tk = self.tk
        j = i
        while j < end and tk.text[j] not in ("{", ";", "=>"):
            if tk.kind[j] == "op" and tk.text[j] in "([":
                j = tk.close(j)
            j += 1
        return self._after_body(j, end)[0]

    def _after_body(self, j: int, end: int) -> Tuple[int, Optional[Tuple[int, int]]]:
        """From a `{`, `=>` or `;` that ends a member header: (index after the member, body span)."""
        tk = self.tk
        if j >= end:
            return end, None
        if tk.text[j] == "{":
            c = tk.close(j)
            return c + 1, (j + 1, c)
        if tk.text[j] == "=>":
            a = j + 1
            k = a
            while k < end and tk.text[k] != ";":
                if tk.kind[k] == "op" and tk.text[k] in "([{":
                    k = tk.close(k)
                k += 1
            return k + 1, (a, k)
        return j + 1, None

    def _params(self, a: int, b: int) -> List[Tuple[str, str]]:
        tk = self.tk
        out: List[Tuple[str, str]] = []
        i = a
        while i < b:
            anns: List = []
            while tk.at(i) == "[":
                i = self._attr_list(i, anns)
            while tk.at(i) in ("this", "ref", "out", "in", "params", "scoped", "readonly") and i < b:
                i += 1
            r = parse_type(tk, i)
            if r is not None and r[0] < b + 1 and tk.is_id(r[0]) and r[0] < b:
                j, ptype = r
                out.append((ptype, tk.text[j]))
                i = j + 1
            else:
                # a record component without a name or a malformed list: skip the segment
                i = i if r is None else r[0]
            while i < b and tk.text[i] != ",":
                if tk.kind[i] == "op" and tk.text[i] in "([{":
                    i = tk.close(i)
                elif tk.text[i] == "<":
                    k = skip_angle(tk, i)
                    if k:
                        i = k - 1
                i += 1
            i += 1
        return out

    def _constraints(self, j: int, end: int) -> int:
        tk = self.tk
        while j < end and tk.at(j) not in ("{", ";", "=>"):
            if tk.kind[j] == "op" and tk.text[j] in "([":
                j = tk.close(j)
            j += 1
        return j

    def _method(self, jt: CType, start: int, name_i: int, mods, anns, tparams, rtype, kind: str, end: int,
                open_i: int = -1, explicit: str = "") -> int:
        tk = self.tk
        m = CMember(kind, tk.text[name_i], jt)
        m.mods, m.anns, m.tparams = set(mods), anns, tparams
        m.ret = rtype or ""
        m.line, m.start_line = tk.line[name_i], tk.line[start]
        m.static = "static" in mods
        m.explicit = explicit
        po = open_i if open_i >= 0 else name_i + 1
        pc = tk.close(po)
        plist = self._params(po + 1, pc)
        m.params = plist
        if any(tk.text[q] == "this" and tk.kind[q] == "id" for q in range(po + 1, min(pc, po + 3))) and plist:
            m.ext = plist[0][0]
        j = pc + 1
        if kind == "ctor" and tk.at(j) == ":" and tk.at(j + 1) in ("base", "this") and tk.at(j + 2) == "(":
            c = tk.close(j + 2)
            m.ctor_init = (j + 3, c, tk.text[j + 1])
            j = c + 1
        j = self._constraints(j, end)
        nxt, body = self._after_body(j, end)
        if body:
            m.body = body
        m.end_line = tk.line[min(max(nxt - 1, 0), tk.n - 1)]
        jt.members.append(m)
        return nxt

    def _operator(self, jt: CType, start: int, i: int, mods, anns, end: int) -> int:
        tk = self.tk
        j = i
        while j < end and tk.at(j) != "(":
            j += 1
        if j >= end:
            return end
        pc = tk.close(j)
        m = CMember("op", "operator", jt)
        m.mods, m.anns = set(mods), anns
        m.line = m.start_line = tk.line[i]
        m.params = self._params(j + 1, pc)
        nxt, body = self._after_body(self._constraints(pc + 1, end), end)
        m.body = body
        m.end_line = tk.line[min(max(nxt - 1, 0), tk.n - 1)]
        m.nodef = True
        jt.members.append(m)
        return nxt

    def _indexer(self, jt: CType, start: int, this_i: int, rtype: str, mods, anns, end: int) -> int:
        tk = self.tk
        m = CMember("field", "this[]", jt)
        m.mods, m.anns, m.ftype, m.prop = set(mods), anns, rtype, True
        m.line, m.start_line = tk.line[this_i], tk.line[start]
        m.nodef = True
        m.params = self._params(this_i + 2, tk.close(this_i + 1))
        j = tk.close(this_i + 1) + 1
        nxt = self._accessors(m, j, end)
        m.end_line = tk.line[min(max(nxt - 1, 0), tk.n - 1)]
        jt.members.append(m)
        return nxt

    def _accessors(self, m: CMember, j: int, end: int) -> int:
        """From the `{` or `=>` after a property header; fills `m.bodies`, `m.init`."""
        tk = self.tk
        if tk.at(j) == "=>":
            nxt, body = self._after_body(j, end)
            if body:
                m.bodies.append(body)
            return nxt
        if tk.at(j) != "{":
            return self._recover(j, end)
        c = tk.close(j)
        k = j + 1
        while k < c:
            while tk.at(k) == "[":
                k = tk.close(k) + 1
            while tk.at(k) in ("public", "private", "protected", "internal", "readonly", "static") and k < c:
                k += 1
            if tk.at(k) in ("get", "set", "init", "add", "remove"):
                k += 1
                if tk.at(k) == "{":
                    cc = tk.close(k)
                    m.bodies.append((k + 1, cc))
                    k = cc + 1
                elif tk.at(k) == "=>":
                    nxt, body = self._after_body(k, c)
                    if body:
                        m.bodies.append(body)
                    k = nxt
                else:
                    k += 1
            else:
                k += 1
        j = c + 1
        if tk.at(j) == "=":
            a = j + 1
            k = a
            while k < end and tk.at(k) != ";":
                if tk.kind[k] == "op" and tk.text[k] in "([{":
                    k = tk.close(k)
                k += 1
            m.init = (a, k)
            return k + 1
        return j

    def _property(self, jt: CType, start: int, name_i: int, rtype: str, mods, anns, end: int) -> int:
        tk = self.tk
        m = CMember("field", tk.text[name_i], jt)
        m.mods, m.anns, m.ftype, m.prop = set(mods), anns, rtype, True
        m.static = "static" in mods
        m.line, m.start_line = tk.line[name_i], tk.line[start]
        nxt = self._accessors(m, name_i + 1, end)
        m.end_line = tk.line[min(max(nxt - 1, 0), tk.n - 1)]
        jt.members.append(m)
        return nxt

    def _fields(self, jt: CType, start: int, name_i: int, ftype: str, mods, anns, end: int) -> int:
        tk = self.tk
        j = name_i
        while True:
            if not tk.is_id(j):
                return self._recover(j, end)
            m = CMember("field", tk.text[j], jt)
            m.mods, m.anns, m.ftype = set(mods), anns, ftype
            m.static = "static" in mods or "const" in mods
            m.line, m.start_line = tk.line[j], tk.line[start]
            j += 1
            if tk.at(j) == "{" and "event" in mods:
                nxt = self._accessors(m, j, end)
                jt.members.append(m)
                return nxt
            if tk.at(j) == "=":
                a = j + 1
                j = a
                while j < end:
                    t = tk.text[j]
                    if tk.kind[j] == "op" and t in "([{":
                        j = tk.close(j) + 1
                        continue
                    if t == "<":
                        k = skip_angle(tk, j)
                        if k:
                            j = k
                            continue
                    if t == ";" or (t == "," and tk.is_id(j + 1) and tk.at(j + 2) in ("=", ";", ",")):
                        break
                    j += 1
                m.init = (a, j)
            m.end_line = tk.line[min(j, tk.n - 1)]
            jt.members.append(m)
            if tk.at(j) == "," and tk.is_id(j + 1):
                j += 1
                continue
            return j + 1


def _looks_interface(name: str) -> bool:
    simple = name.split("<", 1)[0].rsplit(".", 1)[-1]
    return len(simple) > 1 and simple[0] == "I" and simple[1].isupper()
