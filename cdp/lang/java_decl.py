"""Java declarations from tokens: types, methods, constructors, fields.

`java.py` used to find methods with a one-line regex that demanded
`public|protected|private` on the same line as the name. That silently skipped
package-private methods (every JUnit 5 test), interface methods and
constructors: 20% of a real codebase. This reads declarations the way the
grammar does, at any access level, and records each member's extent.

Only declarations are parsed here. Method bodies, field initialisers and
enum-constant arguments are kept as token spans for `java_body`.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Set, Tuple

from .base import Ann
from .java_tokens import Tokens

MODIFIERS = frozenset(["public", "protected", "private", "static", "final", "abstract",
                       "synchronized", "native", "transient", "volatile", "strictfp",
                       "default", "sealed"])
NOT_TYPE = frozenset(["new", "return", "throw", "else", "case", "default", "if", "for", "while",
                      "do", "switch", "try", "catch", "finally", "break", "continue", "import",
                      "package", "assert", "this", "super", "instanceof", "class", "interface",
                      "enum", "extends", "implements", "throws", "synchronized", "yield"])
TYPE_KEYWORDS = ("class", "interface", "enum")


class JMember:
    __slots__ = ("kind", "name", "mods", "anns", "ret", "params", "tparams", "line", "start_line",
                 "end_line", "body", "init", "owner", "static", "ftype", "varargs", "param_anns")

    def __init__(self, kind: str, name: str, owner: "JType") -> None:
        self.kind, self.name, self.owner = kind, name, owner
        self.mods: Set[str] = set()
        self.anns: List[Tuple[str, str]] = []
        self.ret = ""
        self.ftype = ""
        self.params: List[Tuple[str, str]] = []
        self.param_anns: List[List[Ann]] = []         # parallel to `params`
        self.tparams: List[str] = []
        self.line = self.start_line = self.end_line = 0
        self.body: Optional[Tuple[int, int]] = None   # token span of a method body
        self.init: Optional[Tuple[int, int]] = None   # token span of a field initialiser
        self.static = False
        self.varargs = False

    @property
    def symbol(self) -> str:
        if self.kind == "ctor":
            return self.owner.fqn + "#<init>"
        if self.kind in ("init", "field", "enum_const"):
            return self.owner.fqn + ("#<clinit>" if self.static else "#<init>")
        return self.owner.fqn + "#" + self.name

    @property
    def visibility(self) -> str:
        for v in ("public", "protected", "private"):
            if v in self.mods:
                return v
        if self.owner.kind in ("interface", "annotation"):
            return "public"
        return "package"


class JType:
    __slots__ = ("kind", "name", "fqn", "outer", "mods", "anns", "line", "start_line", "end_line",
                 "tparams", "extends", "implements", "members", "types", "body", "static")

    def __init__(self, kind: str, name: str, fqn: str, outer: Optional["JType"]) -> None:
        self.kind, self.name, self.fqn, self.outer = kind, name, fqn, outer
        self.mods: Set[str] = set()
        self.anns: List[Tuple[str, str]] = []
        self.line = self.start_line = self.end_line = 0
        self.tparams: List[str] = []
        self.extends: List[str] = []
        self.implements: List[str] = []
        self.members: List[JMember] = []
        self.types: List["JType"] = []
        self.body: Tuple[int, int] = (0, 0)
        self.static = False

    @property
    def supertypes(self) -> List[str]:
        return self.extends + self.implements

    def all_bounds(self) -> Dict[str, List[str]]:
        """Declared bounds of every type parameter in scope (inner declarations win)."""
        chain: List[JType] = []
        t: Optional[JType] = self
        while t is not None:
            chain.append(t)
            t = t.outer
        out: Dict[str, List[str]] = {}
        for t in reversed(chain):
            out.update(getattr(t.tparams, "bounds", {}))
        return out

    def all_tparams(self) -> Set[str]:
        out: Set[str] = set()
        t: Optional[JType] = self
        while t is not None:
            out.update(t.tparams)
            t = t.outer
        return out


def join_tokens(tk: Tokens, a: int, b: int) -> str:
    out: List[str] = []
    prev = ""
    for t in tk.text[a:b]:
        if prev and (prev[-1].isalnum() or prev[-1] in "_$") and (t[0].isalnum() or t[0] in "_$"):
            out.append(" ")
        out.append(t)
        prev = t
    return "".join(out)


def skip_annotation(tk: Tokens, j: int) -> int:
    """Index past the annotation starting at the `@` at `j`."""
    j += 1
    while tk.is_id(j):
        j += 1
        if tk.at(j) == "." and tk.is_id(j + 1):
            j += 1
            continue
        break
    if tk.at(j) == "(":
        j = tk.close(j) + 1
    return j


def parse_type(tk: Tokens, i: int) -> Optional[Tuple[int, str]]:
    """(end index, text) of the type starting at `i`, or None."""
    j = i
    while tk.at(j) == "@" and tk.at(j + 1) != "interface" and tk.is_id(j + 1):
        j = skip_annotation(tk, j)
    start = j
    if tk.at(j) in NOT_TYPE:
        return None
    while True:
        if not tk.is_id(j) or tk.text[j] in NOT_TYPE:
            return None
        j += 1
        if tk.at(j) == "<":
            k = tk.skip_angle(j)
            if k is None:
                return None
            j = k
        if tk.at(j) == "." and tk.is_id(j + 1):
            j += 1
            continue
        break
    while tk.at(j) == "[" and tk.at(j + 1) == "]":
        j += 2
    return j, join_type(tk, start, j)


def join_type(tk: Tokens, a: int, b: int) -> str:
    """Type text for tokens [a, b) without type-use annotations (`List<@NonNull String>`)."""
    kept: List[str] = []
    i = a
    while i < b:
        if tk.text[i] == "@" and tk.kind[i] == "op" and tk.is_id(i + 1):
            i = skip_annotation(tk, i)
            continue
        kept.append(tk.text[i])
        i += 1
    out: List[str] = []
    prev = ""
    for t in kept:
        if prev and (prev[-1].isalnum() or prev[-1] in "_$") and (t[0].isalnum() or t[0] in "_$"):
            out.append(" ")
        out.append(t)
        prev = t
    return "".join(out)


class TParams(list):
    """Type-parameter names in declaration order; `bounds` maps a name to its
    declared bound type texts (`T extends A & B` -> ["A", "B"])."""

    def __init__(self) -> None:
        super().__init__()
        self.bounds: Dict[str, List[str]] = {}


def _tparam_names(tk: Tokens, i: int, end: int) -> List[str]:
    names = TParams()
    depth = 0
    expect = True
    j = i
    while j < end:
        t = tk.text[j]
        if t == "<":
            depth += 1
            expect = depth == 1
        elif t == ">":
            depth -= 1
        elif t == "," and depth == 1:
            expect = True
        elif expect and depth == 1 and tk.kind[j] == "id":
            names.append(t)
            expect = False
            if tk.at(j + 1) == "extends":
                k, found = j + 2, []
                while k < end:
                    r = parse_type(tk, k)
                    if r is None:
                        break
                    k, text = r
                    found.append(text)
                    if tk.at(k) != "&":
                        break
                    k += 1
                if found:
                    names.bounds[t] = found
                j = k - 1
        j += 1
    return names


class DeclParser:
    def __init__(self, tk: Tokens, pkg: str) -> None:
        self.tk = tk
        self.pkg = pkg
        self.types: List[JType] = []   # every named type, outer before inner

    # ----------------------------------------------------------- top level

    def parse(self) -> List[JType]:
        tk = self.tk
        i = 0
        tops: List[JType] = []
        while i < tk.n:
            t = tk.text[i]
            if t in ("package", "import") and tk.kind[i] == "id":
                while i < tk.n and tk.text[i] != ";":
                    i += 1
                i += 1
                continue
            mods, anns, j = self._modifiers(i)
            nxt = self._type_decl(j, None, mods, anns)
            if nxt is not None:
                jt, i = nxt
                tops.append(jt)
                continue
            i = max(j, i + 1) if j == i else j + 1
        return tops

    def _annotation(self, i: int) -> Tuple[Ann, int]:
        """The annotation at the `@` at `i` (simple name, whitespace-light text, line span) and
        the index past it."""
        tk = self.tk
        name = tk.text[i + 1]
        j = i + 2
        while tk.at(j) == "." and tk.is_id(j + 1):
            name = tk.text[j + 1]
            j += 2
        k = skip_annotation(tk, i)
        return Ann(name, join_tokens(tk, i, k), tk.line[i], tk.line[k - 1]), k

    def _modifiers(self, i: int) -> Tuple[Set[str], List[Tuple[str, str]], int]:
        tk = self.tk
        mods: Set[str] = set()
        anns: List[Tuple[str, str]] = []
        while i < tk.n:
            t = tk.text[i]
            if t == "@" and tk.at(i + 1) != "interface" and tk.is_id(i + 1):
                ann, i = self._annotation(i)
                anns.append(ann)
            elif tk.kind[i] == "id" and t in MODIFIERS and not (t == "default" and tk.at(i + 1) in (":", "->")):
                mods.add(t)
                i += 1
            elif t == "non" and tk.at(i + 1) == "-" and tk.at(i + 2) == "sealed":
                i += 3
            else:
                break
        return mods, anns, i

    # ---------------------------------------------------------------- types

    def _type_decl(self, i: int, outer: Optional[JType], mods: Set[str],
                   anns: List[str]) -> Optional[Tuple[JType, int]]:
        tk = self.tk
        t = tk.at(i)
        if t in TYPE_KEYWORDS and tk.is_id(i + 1):
            kind, name_i = t, i + 1
        elif t == "@" and tk.at(i + 1) == "interface" and tk.is_id(i + 2):
            kind, name_i = "annotation", i + 2
        elif t == "record" and tk.is_id(i + 1) and tk.at(i + 2) in ("(", "<"):
            kind, name_i = "record", i + 1
        else:
            return None
        name = tk.text[name_i]
        fqn = (outer.fqn + "." + name) if outer else ((self.pkg + "." + name) if self.pkg else name)
        jt = JType(kind, name, fqn, outer)
        jt.mods, jt.anns = mods, anns
        jt.line = tk.line[name_i]
        jt.start_line = tk.line[i]
        jt.static = "static" in mods or outer is None or kind != "class" or (
            outer is not None and outer.kind in ("interface", "annotation"))
        j = name_i + 1
        if tk.at(j) == "<":
            k = tk.skip_angle(j)
            if k:
                jt.tparams = _tparam_names(tk, j, k)
                j = k
        components: Optional[Tuple[int, int]] = None
        if kind == "record" and tk.at(j) == "(":
            c = tk.close(j)
            components = (j + 1, c)
            j = c + 1
        section = ""
        while j < tk.n and tk.at(j) != "{":
            w = tk.text[j]
            if tk.kind[j] == "id" and w in ("extends", "implements", "permits"):
                section = w
                j += 1
                continue
            if section:
                r = parse_type(tk, j)
                if r is not None:
                    j, text = r
                    if section == "extends" and kind == "class":
                        jt.extends.append(text)
                    elif section in ("extends", "implements"):
                        jt.implements.append(text)
                    continue
            if tk.at(j) == ";":
                break
            j += 1
        if tk.at(j) != "{":
            return None
        close = tk.close(j)
        jt.body = (j + 1, close)
        jt.end_line = tk.line[close]
        if outer is not None:
            outer.types.append(jt)
        self.types.append(jt)
        if components is not None:
            self._record_components(jt, *components)
        self._members(jt, j + 1, close)
        return jt, close + 1

    def _record_components(self, jt: JType, a: int, b: int) -> None:
        for ptype, pname, line, _, panns in self._params(a, b):
            m = JMember("field", pname, jt)
            m.anns = panns
            m.mods = {"private", "final"}
            m.ftype, m.line, m.start_line, m.end_line = ptype, line, line, line
            jt.members.append(m)

    # -------------------------------------------------------------- members

    def _members(self, jt: JType, i: int, end: int) -> None:
        tk = self.tk
        if jt.kind == "enum":
            i = self._enum_constants(jt, i, end)
        while i < end:
            t = tk.text[i]
            if t == ";":
                i += 1
                continue
            if t == "{" or (t == "static" and tk.at(i + 1) == "{"):
                static = t == "static"
                o = i + 1 if static else i
                c = tk.close(o)
                m = JMember("init", "<clinit>" if static else "<init>", jt)
                m.static = static
                m.body = (o + 1, c)
                m.line = m.start_line = tk.line[i]
                m.end_line = tk.line[c]
                jt.members.append(m)
                i = c + 1
                continue
            start = i
            mods, anns, i = self._modifiers(i)
            nxt = self._type_decl(i, jt, mods, anns)
            if nxt is not None:
                i = nxt[1]
                continue
            tparams: List[str] = []
            if tk.at(i) == "<":
                k = tk.skip_angle(i)
                if k is None:
                    i = self._recover(i, end)
                    continue
                tparams = _tparam_names(tk, i, k)
                i = k
            if tk.is_id(i) and tk.at(i + 1) == "(" and tk.text[i] == jt.name:
                i = self._method(jt, start, i, mods, anns, tparams, None, ctor=True, end=end)
                continue
            if tk.is_id(i) and tk.at(i + 1) == "{" and tk.text[i] == jt.name and jt.kind == "record":
                c = tk.close(i + 1)
                m = JMember("ctor", jt.name, jt)
                m.mods, m.anns = mods, anns
                m.line, m.start_line, m.end_line = tk.line[i], tk.line[start], tk.line[c]
                m.body = (i + 2, c)
                jt.members.append(m)
                i = c + 1
                continue
            r = parse_type(tk, i)
            if r is None or not tk.is_id(r[0]):
                i = self._recover(i, end)
                continue
            j, rtype = r
            if tk.at(j + 1) == "(":
                i = self._method(jt, start, j, mods, anns, tparams, rtype, ctor=False, end=end)
            else:
                i = self._fields(jt, start, j, rtype, mods, anns, end)

    def _recover(self, i: int, end: int) -> int:
        tk = self.tk
        while i < end and tk.text[i] != ";":
            if tk.kind[i] == "op" and tk.text[i] in "([{":
                i = tk.close(i)
            i += 1
        return i + 1

    def _params(self, a: int, b: int) -> List[Tuple[str, str, int, bool, List[Ann]]]:
        """(type text, name, line, varargs, annotations) for the parameter list in tokens [a, b)."""
        tk = self.tk
        out: List[Tuple[str, str, int, bool, List[Ann]]] = []
        i = a
        while i < b:
            panns: List[Ann] = []
            while i < b and (tk.at(i) == "@" or tk.at(i) == "final"):
                if tk.at(i) == "@":
                    ann, i = self._annotation(i)
                    panns.append(ann)
                else:
                    i += 1
            r = parse_type(tk, i)
            if r is None:
                # skip to the next top-level comma
                while i < b and tk.text[i] != ",":
                    if tk.kind[i] == "op" and tk.text[i] in "([{":
                        i = tk.close(i)
                    i += 1
                i += 1
                continue
            j, ptype = r
            varargs = False
            if tk.at(j) == "...":
                varargs = True
                ptype += "[]"
                j += 1
            if tk.is_id(j):
                name = tk.text[j]
                line = tk.line[j]
                j += 1
                while tk.at(j) == "[" and tk.at(j + 1) == "]":
                    ptype += "[]"
                    j += 2
                if name != "this":
                    out.append((ptype, name, line, varargs, panns))
            while j < b and tk.text[j] != ",":
                if tk.kind[j] == "op" and tk.text[j] in "([{":
                    j = tk.close(j)
                j += 1
            i = j + 1
        return out

    def _method(self, jt: JType, start: int, name_i: int, mods: Set[str], anns: List[Tuple[str, str]],
                tparams: List[str], rtype: Optional[str], ctor: bool, end: int) -> int:
        tk = self.tk
        m = JMember("ctor" if ctor else "method", tk.text[name_i], jt)
        m.mods, m.anns, m.tparams = mods, anns, tparams
        m.ret = rtype or ""
        m.line, m.start_line = tk.line[name_i], tk.line[start]
        m.static = "static" in mods
        po = name_i + 1
        pc = tk.close(po)
        plist = self._params(po + 1, pc)
        m.params = [(t, n) for t, n, *_ in plist]
        m.param_anns = [pa for *_, pa in plist]
        m.varargs = any(v for _, _, _, v, _ in plist)
        j = pc + 1
        while j < end and tk.text[j] not in ("{", ";"):
            if tk.text[j] == "default" and tk.kind[j] == "id":
                while j < end and tk.text[j] != ";":
                    if tk.kind[j] == "op" and tk.text[j] in "([{":
                        j = tk.close(j)
                    j += 1
                break
            if tk.kind[j] == "op" and tk.text[j] in "([":
                j = tk.close(j)
            j += 1
        if j < end and tk.text[j] == "{":
            c = tk.close(j)
            m.body = (j + 1, c)
            m.end_line = tk.line[c]
            j = c + 1
        else:
            m.end_line = tk.line[min(j, tk.n - 1)]
            j += 1
        jt.members.append(m)
        return j

    def _fields(self, jt: JType, start: int, name_i: int, ftype: str, mods: Set[str],
                anns: List[str], end: int) -> int:
        tk = self.tk
        j = name_i
        while True:
            m = JMember("field", tk.text[j], jt)
            m.mods, m.anns, m.ftype = set(mods), anns, ftype
            if jt.kind in ("interface", "annotation"):
                m.mods |= {"static", "final", "public"}
            m.static = "static" in m.mods
            m.line, m.start_line = tk.line[j], tk.line[start]
            j += 1
            while tk.at(j) == "[" and tk.at(j + 1) == "]":
                m.ftype += "[]"
                j += 2
            if tk.at(j) == "=":
                a = j + 1
                j = a
                while j < end:
                    t = tk.text[j]
                    if tk.kind[j] == "op" and t in "([{":
                        j = tk.close(j) + 1
                        continue
                    if t == "<":
                        k = tk.skip_angle(j)
                        if k:
                            j = k
                            continue
                    if t == ";" or (t == "," and tk.is_id(j + 1) and tk.at(j + 2) in ("=", ";", ",", "[")):
                        break
                    j += 1
                m.init = (a, j)
            m.end_line = tk.line[min(j, tk.n - 1)]
            jt.members.append(m)
            if tk.at(j) == "," and tk.is_id(j + 1):
                j += 1
                continue
            return j + 1

    def _enum_constants(self, jt: JType, i: int, end: int) -> int:
        tk = self.tk
        while i < end:
            canns: List[Ann] = []
            while tk.at(i) == "@":
                ann, i = self._annotation(i)
                canns.append(ann)
            if not tk.is_id(i):
                break
            m = JMember("enum_const", tk.text[i], jt)
            m.anns = canns
            m.mods = {"public", "static", "final"}
            m.static = True
            m.ftype = jt.name
            m.line = m.start_line = tk.line[i]
            a = i
            i += 1
            spans = []
            if tk.at(i) == "(":
                c = tk.close(i)
                spans.append((i + 1, c))
                i = c + 1
            if tk.at(i) == "{":
                c = tk.close(i)
                spans.append((i + 1, c))
                i = c + 1
            m.end_line = tk.line[max(a, i - 1)]
            m.init = (spans[0][0], spans[-1][1]) if spans else (a, a)
            jt.members.append(m)
            if tk.at(i) == ",":
                i += 1
                continue
            if tk.at(i) == ";":
                i += 1
            break
        return i
