"""Scala declarations from tokens: packages, types, constructor parameters, members.

Mirrors `java_decl.DeclParser` and reuses its `JType`/`JMember` shapes. Scala differences handled:
statements end at a newline, not `;` (a statement ends at the first depth-0 token on a later line
whose indentation is not deeper than the statement's own); `private[x]` qualifiers; `def`/`val`/
`var` at any visibility; primary-constructor parameters are fields and the constructor takes the
annotations written before them (`class X @Inject() (..)`); `extends A with B`; `object` and
`trait`; `package a { .. }` blocks and chained `package` clauses.

Kinds: trait -> `interface`, object -> `class` with `is_object`, case class -> `class`
(`is_case`), enum -> `enum`. Bodies and initialisers stay token spans for the flow readers.
"""

from __future__ import annotations

from typing import List, Optional, Set, Tuple

from .base import Ann
from .java_decl import JMember, JType, join_tokens
from .scala_annotations import make_ann
from .scala_tokens import ScTokens, string_value

MODIFIERS = frozenset(["private", "protected", "override", "final", "abstract", "sealed", "implicit",
                       "lazy", "case", "inline", "open", "transparent", "opaque", "infix"])
TYPE_KW = ("class", "trait", "object", "enum")
# a token that continues the previous line's expression rather than starting a statement
CONTINUES = frozenset(["else", "match", "with", "extends", "catch", "finally", "yield", "forSome",
                       "if", "then", "do"])
IMPLICIT_PARAM = frozenset(["implicit", "using"])


class ScType(JType):
    __slots__ = ("is_object", "is_case", "ctor_anns", "ctor_mods", "scope")

    def __init__(self, kind: str, name: str, fqn: str, outer: Optional[JType]) -> None:
        super().__init__(kind, name, fqn, outer)
        self.is_object = False
        self.is_case = False
        self.ctor_anns: List[Ann] = []
        self.ctor_mods: Set[str] = set()
        self.scope = ""          # package the type is declared in


class ScMember(JMember):
    __slots__ = ("vis", "is_var", "is_lazy")

    def __init__(self, kind: str, name: str, owner: JType) -> None:
        super().__init__(kind, name, owner)
        self.vis = "public"
        self.is_var = False
        self.is_lazy = False

    @property
    def visibility(self) -> str:
        return self.vis


def visibility_of(mods: Set[str], qual: Optional[str]) -> str:
    if "private" in mods:
        return "private" if qual in (None, "this") else "package"
    if "protected" in mods:
        return "protected" if qual in (None, "this") else "package"
    return "public"


def scala_type_text(text: str) -> str:
    """Scala type text -> the Java-shaped text `java_types.norm_type` reads:
    `Map[String, Foo]` -> `Map<String,Foo>`, `Array[Foo]` -> `Foo[]`, `=> T` -> `T`, `T*` -> `T[]`."""
    t = text.strip()
    if t.startswith("=>"):
        t = t[2:].strip()
    star = t.endswith("*")
    if star:
        t = t[:-1]
    import re
    prev = None
    while prev != t:
        prev = t
        t = re.sub(r"\bArray\[([^\[\]]*)\]", lambda m: m.group(1) + "[]", t)
    t = t.replace("[]", "\0").replace("[", "<").replace("]", ">").replace(" ", "").replace("\0", "[]")
    return t + ("[]" if star else "")


class ScalaDeclParser:
    def __init__(self, tk: ScTokens, lines: List[str]) -> None:
        self.tk = tk
        self.lines = lines
        self.types: List[ScType] = []
        self.package = ""             # the file's first (full chained) package clause
        self._indent_cache: dict = {}

    # ------------------------------------------------------------ utilities

    def _indent(self, row: int) -> int:
        v = self._indent_cache.get(row)
        if v is None:
            s = self.lines[row] if row < len(self.lines) else ""
            v = len(s) - len(s.lstrip())
            self._indent_cache[row] = v
        return v

    def _stmt_end(self, start: int, i: int, end: int) -> int:
        """Index (exclusive) where the statement begun at token `start` ends, scanning from `i`."""
        tk = self.tk
        col = self._indent(tk.line[start])
        j = i
        while j < end:
            if tk.kind[j] == "op" and tk.text[j] in "([{":
                j = tk.close(j) + 1
                continue
            if tk.text[j] == ";" and tk.kind[j] == "op":
                return j + 1
            if j > start and tk.line[j] > tk.line[j - 1] and self._indent(tk.line[j]) <= col:
                t, k = tk.text[j], tk.kind[j]
                if (k in ("id", "str", "num", "chr") and t not in CONTINUES) or t in ("@", "{", "("):
                    prev = tk.text[j - 1]
                    if not (tk.kind[j - 1] == "op" and prev in (",", "=", "+", "-", "*", "/", "&&", "||", ".", ":",
                                                                  "=>", "<-", "|", "&", "%", "(", "[", "{")):
                        return j
            j += 1
        return min(j, end)

    def _skip_to_boundary(self, start: int, end: int) -> int:
        return max(self._stmt_end(start, start, end), start + 1)

    # ------------------------------------------------------------ top level

    def parse(self) -> List[ScType]:
        tops: List[ScType] = []
        self._block(0, self.tk.n, "", None, tops, top=True)
        return tops

    def _block(self, i: int, end: int, pkg: str, outer: Optional[ScType], out: List[ScType], top: bool) -> None:
        tk = self.tk
        while i < end:
            t = tk.text[i]
            if t == ";" and tk.kind[i] == "op":
                i += 1
                continue
            if tk.kind[i] == "id" and t == "package":
                if tk.at(i + 1) == "object" and tk.is_id(i + 2):
                    mods, anns = set(), []
                    nxt = self._type_decl(i + 1, outer, mods, anns, pkg, None, name_override="package",
                                          name_tok=i + 2, pkg_obj=True)
                    if nxt is not None:
                        jt, i = nxt
                        out.append(jt)
                        continue
                j = i + 1
                parts = []
                while tk.is_id(j):
                    parts.append(tk.text[j])
                    j += 1
                    if tk.at(j) == "." and tk.is_id(j + 1):
                        j += 1
                        continue
                    break
                name = ".".join(parts)
                new = (pkg + "." + name) if pkg else name
                if tk.at(j) == "{":
                    c = tk.close(j)
                    if top and not self.package:
                        self.package = new
                    self._block(j + 1, c, new, outer, out, top=False)
                    i = c + 1
                else:
                    if top and not outer:
                        self.package = new
                    pkg = new                      # a chained clause extends the one before it
                    i = j
                continue
            if tk.kind[i] == "id" and t == "import":
                i = self._skip_to_boundary(i, end)
                continue
            start = i
            mods, anns, qual, i = self._modifiers(i)
            if i >= end:
                break
            nxt = self._type_decl(i, outer, mods, anns, pkg, qual)
            if nxt is not None:
                jt, i = nxt
                out.append(jt)
                continue
            i = self._skip_to_boundary(start if i == start else i, end) if i < end else end

    # ------------------------------------------------------------ modifiers

    def _modifiers(self, i: int) -> Tuple[Set[str], List[Ann], Optional[str], int]:
        tk = self.tk
        mods: Set[str] = set()
        anns: List[Ann] = []
        qual: Optional[str] = None
        while i < tk.n:
            t = tk.text[i]
            if t == "@" and tk.kind[i] == "op" and tk.is_id(i + 1):
                ann, i = make_ann(tk, i)
                anns.append(ann)
            elif tk.kind[i] == "id" and t in MODIFIERS and not (
                    t == "case" and tk.at(i + 1) not in ("class", "object")):
                if t == "implicit" and tk.at(i + 1) not in ("def", "val", "var", "class", "object", "lazy",
                                                             "final", "private", "protected", "override"):
                    break
                mods.add(t)
                i += 1
                if t in ("private", "protected") and tk.at(i) == "[" and tk.line[i] == tk.line[i - 1]:
                    c = tk.close(i)
                    qual = tk.text[i + 1] if i + 1 < c else None
                    i = c + 1
            else:
                break
        return mods, anns, qual, i

    # ---------------------------------------------------------------- types

    def _type_decl(self, i: int, outer: Optional[ScType], mods: Set[str], anns: List[Ann], pkg: str,
                   qual: Optional[str], name_override: Optional[str] = None, name_tok: Optional[int] = None,
                   pkg_obj: bool = False) -> Optional[Tuple[ScType, int]]:
        tk = self.tk
        kw = tk.text[i] if tk.is_id(i) else ""
        if kw not in TYPE_KW:
            return None
        ni = name_tok if name_tok is not None else i + 1
        if not tk.is_id(ni):
            return None
        name = tk.text[ni]
        kind = {"class": "class", "object": "class", "trait": "interface", "enum": "enum"}[kw]
        if pkg_obj:
            fqn = (pkg + "." if pkg else "") + name + ".package"
        elif outer is not None:
            fqn = outer.fqn + "." + name
        else:
            fqn = (pkg + "." if pkg else "") + name
        jt = ScType(kind, name, fqn, outer)
        jt.scope = pkg
        jt.mods, jt.anns = set(mods), anns
        jt.is_object = kw == "object"
        jt.is_case = "case" in mods
        jt.static = True
        jt.line, jt.start_line = tk.line[ni], tk.line[i]
        jt.mods = set(mods) | {"__vis_" + visibility_of(mods, qual)}
        j = ni + 1
        if tk.at(j) == "[":
            c = tk.close(j)
            jt.tparams = [tk.text[q] for q in range(j + 1, c)
                          if tk.kind[q] == "id" and tk.text[q - 1] in ("[", ",") and tk.text[q] not in ("_",)]
            j = c + 1
        # primary constructor: `@Inject() private (..)(implicit ..)`
        clauses: List[Tuple[int, int]] = []
        if kw in ("class", "enum") or (kw == "trait"):
            while True:
                k = j
                while tk.at(k) == "@" and tk.is_id(k + 1):
                    ann, k = make_ann(tk, k)
                    jt.ctor_anns.append(ann)
                while tk.is_id(k) and tk.text[k] in ("private", "protected"):
                    jt.ctor_mods.add(tk.text[k])
                    k += 1
                    if tk.at(k) == "[":
                        k = tk.close(k) + 1
                if tk.at(k) == "(" and (k == j or tk.line[k] == tk.line[k - 1] or jt.ctor_anns
                                         or tk.line[k] - tk.line[k - 1] <= 1):
                    c = tk.close(k)
                    clauses.append((k + 1, c))
                    j = c + 1
                    continue
                if k != j and not clauses:
                    j = k
                break
        # `extends A(args) with B[T]`
        if tk.at(j) == "extends" or tk.at(j) == "<:":
            j += 1
            first = True
            while j < tk.n:
                r = self._parse_type(j)
                if r is None:
                    break
                j, text = r
                if tk.at(j) == "(":                 # parent constructor arguments
                    while tk.at(j) == "(":
                        j = tk.close(j) + 1
                if first:
                    jt.extends.append(text)
                    first = False
                else:
                    jt.implements.append(text)
                if tk.at(j) == "with" and tk.kind[j] == "id":
                    j += 1
                    continue
                break
        # optional body
        close = None
        if tk.at(j) == "{":
            close = tk.close(j)
            jt.body = (j + 1, close)
            jt.end_line = tk.line[close]
            nxt_i = close + 1
        else:
            last = max(j - 1, ni)
            jt.body = (j, j)
            jt.end_line = tk.line[min(last, tk.n - 1)]
            nxt_i = j
        if outer is not None:
            outer.types.append(jt)
        self.types.append(jt)
        for ci, (a, b) in enumerate(clauses):
            self._ctor_params(jt, a, b, first=(ci == 0), anchor_tok=ni)
        if jt.ctor_anns or clauses or kw == "class":
            self._add_ctor(jt, ni, clauses, tk.line[min(max(j - 1, ni), tk.n - 1)])
        if close is not None:
            self._members(jt, j + 1, close)
        return jt, nxt_i

    def _parse_type(self, i: int) -> Optional[Tuple[int, str]]:
        """(end index, Scala type text) of a simple/path type at `i`: `a.B[C, D]`, `A#B`, `(A, B)`."""
        tk = self.tk
        j = i
        while tk.at(j) == "@" and tk.is_id(j + 1):
            _, j = make_ann(tk, j)
        start = j
        if tk.at(j) == "(":
            j = tk.close(j) + 1
            if tk.at(j) == "=>":
                r = self._parse_type(j + 1)
                return (r[0], join_tokens(tk, start, r[0])) if r else None
            return j, join_tokens(tk, start, j)
        if not tk.is_id(j) or tk.text[j] in ("extends", "with", "new", "def", "val", "var"):
            return None
        while True:
            j += 1
            if tk.at(j) == "[":
                j = tk.close(j) + 1
            if tk.at(j) in (".", "#") and tk.is_id(j + 1):
                j += 1
                continue
            break
        return j, join_tokens(tk, start, j)

    # ------------------------------------------------------- ctor and params

    def _params(self, a: int, b: int) -> List[Tuple[str, str, int, Set[str], List[Ann], Tuple[int, int]]]:
        """(type text, name, line, modifiers (`val`/`var`/..), annotations, default-span) per parameter."""
        tk = self.tk
        out = []
        from .annotation_args import _split
        for s, e in _split(tk, a, b):
            i = s
            anns: List[Ann] = []
            mods: Set[str] = set()
            while i < e:
                if tk.at(i) == "@" and tk.is_id(i + 1):
                    ann, i = make_ann(tk, i)
                    anns.append(ann)
                elif tk.kind[i] == "id" and tk.text[i] in ("val", "var", "implicit", "using", "private", "protected",
                                                          "override", "final", "inline"):
                    mods.add(tk.text[i])
                    i += 1
                    if tk.at(i) == "[" and tk.text[i - 1] in ("private", "protected"):
                        i = tk.close(i) + 1
                else:
                    break
            if not tk.is_id(i) or tk.at(i + 1) != ":":
                continue
            name, line = tk.text[i], tk.line[i]
            ti = i + 2
            d = ti
            while d < e:                    # the type ends at a depth-0 `=` (default value)
                if tk.kind[d] == "op" and tk.text[d] in "([{":
                    d = tk.close(d) + 1
                    continue
                if tk.text[d] == "=" and tk.kind[d] == "op":
                    break
                d += 1
            text = scala_type_text(join_tokens(tk, ti, d))
            out.append((text, name, line, mods, anns, (d + 1, e) if d < e else (0, 0)))
        return out

    def _ctor_params(self, jt: ScType, a: int, b: int, first: bool, anchor_tok: int) -> None:
        for ptype, pname, line, mods, panns, _ in self._params(a, b):
            m = ScMember("field", pname, jt)
            m.anns = panns
            public = "val" in mods or "var" in mods or jt.is_case
            m.vis = visibility_of(mods, None) if public else "private"
            m.mods = {"final"} if not "var" in mods else set()
            m.is_var = "var" in mods
            m.ftype, m.line, m.start_line, m.end_line = ptype, line, line, line
            jt.members.append(m)

    def _add_ctor(self, jt: ScType, name_i: int, clauses: List[Tuple[int, int]], end_row: int) -> None:
        tk = self.tk
        m = ScMember("ctor", jt.name, jt)
        m.anns = list(jt.ctor_anns)
        m.vis = visibility_of(jt.ctor_mods, None)
        m.line = tk.line[name_i]
        m.start_line = tk.line[name_i]
        m.end_line = end_row
        params = []
        pa = []
        for a, b in clauses:
            for ptype, pname, _, _, panns, _ in self._params(a, b):
                params.append((ptype, pname))
                pa.append(panns)
        m.params, m.param_anns = params, pa
        # the constructor takes the annotations that sat before the parameter list, not the class's
        jt.members.append(m)

    # -------------------------------------------------------------- members

    def _self_type_end(self, i: int, end: int) -> int:
        """Index after a leading self-type clause (`self: Foo with Bar[A] =>`, `this: Foo =>`, `self =>`) at `i`,
        else `i`. Only a template body's first token; `case x =>` and `x => ..` are not self-types."""
        tk = self.tk
        if i >= end or tk.kind[i] != "id":
            return i
        j = i + 1
        if tk.at(j) == "=>":
            return j + 1 if tk.text[i] == "self" else i
        if tk.at(j) != ":" or tk.text[i] == "case":
            return i
        j += 1
        while j < end:
            r = self._parse_type(j)
            if r is None:
                return i
            j = r[0]
            if tk.at(j) == "with" and tk.kind[j] == "id":
                j += 1
                continue
            break
        return j + 1 if j < end and tk.at(j) == "=>" else i

    def _members(self, jt: ScType, i: int, end: int) -> None:
        tk = self.tk
        i = self._self_type_end(i, end)
        while i < end:
            t = tk.text[i]
            if t == ";" and tk.kind[i] == "op":
                i += 1
                continue
            start = i
            if tk.kind[i] == "id" and t == "import":
                i = self._skip_to_boundary(i, end)
                continue
            if t == "{" and tk.kind[i] == "op":
                c = tk.close(i)
                m = ScMember("init", "<init>", jt)
                m.body = (i + 1, c)
                m.line = m.start_line = tk.line[i]
                m.end_line = tk.line[c]
                jt.members.append(m)
                i = c + 1
                continue
            mods, anns, qual, i = self._modifiers(i)
            if i >= end:
                break
            nxt = self._type_decl(i, jt, mods, anns, jt.scope, qual)
            if nxt is not None:
                i = nxt[1]
                continue
            kw = tk.text[i] if tk.kind[i] == "id" else ""
            if kw == "def":
                i = self._def(jt, start, i, mods, anns, qual, end)
            elif kw in ("val", "var"):
                i = self._vals(jt, start, i, mods, anns, qual, end)
            else:
                i = self._skip_to_boundary(start, end) if i == start else self._stmt_end(start, i, end)
                if i <= start:
                    i = start + 1

    def _def(self, jt: ScType, start: int, i: int, mods: Set[str], anns: List[Ann], qual: Optional[str],
             end: int) -> int:
        tk = self.tk
        ni = i + 1
        if ni >= end or tk.kind[ni] not in ("id", "op"):
            return self._stmt_end(start, i + 1, end)
        name = tk.text[ni]
        m = ScMember("ctor" if name == "this" else "method", name, jt)
        m.mods, m.anns = mods, anns
        m.vis = visibility_of(mods, qual)
        m.line, m.start_line = tk.line[ni], tk.line[start]
        j = ni + 1
        if tk.at(j) == "[":
            c = tk.close(j)
            m.tparams = [tk.text[q] for q in range(j + 1, c)
                         if tk.kind[q] == "id" and tk.text[q - 1] in ("[", ",")]
            j = c + 1
        params: List[Tuple[str, str]] = []
        pann: List[List[Ann]] = []
        while tk.at(j) == "(":
            if tk.line[j] > tk.line[j - 1] and self._indent(tk.line[j]) <= self._indent(tk.line[start]):
                break
            c = tk.close(j)
            for ptype, pname, _, _, panns, _ in self._params(j + 1, c):
                params.append((ptype, pname))
                pann.append(panns)
            j = c + 1
        m.params, m.param_anns = params, pann
        stop = self._stmt_end(start, j, end)
        if tk.at(j) == ":" and j < stop:
            d = j + 1
            while d < stop:
                if tk.kind[d] == "op" and tk.text[d] in "([{":
                    d = tk.close(d) + 1
                    continue
                if tk.text[d] == "=" and tk.kind[d] == "op" and tk.at(d + 1) != "=":
                    break
                d += 1
            m.ret = scala_type_text(join_tokens(tk, j + 1, min(d, stop)))
            j = d
        if j < stop and tk.at(j) == "=":
            a = j + 1
            if a < stop and tk.at(a) == "{" and tk.close(a) == stop - 1 or (
                    a < stop and tk.at(a) == "{" and tk.close(a) + 1 >= stop):
                m.body = (a + 1, tk.close(a))
            else:
                m.body = (a, stop)
        elif j < stop and tk.at(j) == "{":           # procedure syntax `def f() { .. }`
            m.body = (j + 1, tk.close(j))
        m.end_line = tk.line[min(stop - 1, tk.n - 1)] if stop > start else tk.line[start]
        jt.members.append(m)
        return stop

    def _vals(self, jt: ScType, start: int, i: int, mods: Set[str], anns: List[Ann], qual: Optional[str],
              end: int) -> int:
        tk = self.tk
        is_var = tk.text[i] == "var"
        ni = i + 1
        stop = self._stmt_end(start, ni, end)
        if not tk.is_id(ni) or tk.at(ni) == "(":      # `val (a, b) = ..` pattern: not a named member
            return stop
        names = [ni]
        j = ni + 1
        while tk.at(j) == "," and tk.is_id(j + 1):
            names.append(j + 1)
            j += 2
        ftype = ""
        if tk.at(j) == ":":
            d = j + 1
            while d < stop:
                if tk.kind[d] == "op" and tk.text[d] in "([{":
                    d = tk.close(d) + 1
                    continue
                if tk.text[d] == "=" and tk.kind[d] == "op":
                    break
                d += 1
            ftype = scala_type_text(join_tokens(tk, j + 1, min(d, stop)))
            j = d
        init = None
        if j < stop and tk.at(j) == "=":
            init = (j + 1, stop)
        for n in names:
            m = ScMember("field", tk.text[n], jt)
            m.mods, m.anns, m.ftype, m.is_var = set(mods), anns, ftype, is_var
            m.is_lazy = "lazy" in mods
            m.vis = visibility_of(mods, qual)
            m.line, m.start_line = tk.line[n], tk.line[start]
            m.end_line = tk.line[min(stop - 1, tk.n - 1)]
            m.init = init
            m.static = jt.is_object if isinstance(jt, ScType) else False
            jt.members.append(m)
        return stop
