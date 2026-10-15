"""Call sites from Scala member bodies (the Scala twin of `java_body.Scan`).

Same contract as Java: a receiver is typed from a *declared* type (parameter, `val x: T`, field,
`new T`, a companion `Type.m()`); an untyped `val x = foo()` carries a chain (`m:foo`, `f:bar`) for the
resolve phase to settle against the symbol table; a receiver nobody can type produces no row. The row
shape is `Scan.emit`'s (`kind: call`, `fqn: Type#m`, `from_symbol`, `chain`/`recv`, `strict`, `alts`),
inherited unchanged.

Scala differences handled here: `val`/`var` locals, `x =>` / `(a, b) =>` / `case P(x) =>` binders,
`new T(..)` and `T(..)` construction, curried and brace argument lists (`f(a)(b)`, `f { x => .. }`),
member access without parentheses (`user.getName`), and infix calls (`logger info msg`).
"""

from __future__ import annotations

from typing import Dict, List, Optional, Set, Tuple

from .base import ExtractContext, FileFacts, anchor_at
from .java_body import ALL_CAPS, FileInfo, Scan, TExpr
from .java_types import split_type
from .scala_decl import ScType, ScalaDeclParser, scala_type_text
from .scala_tokens import ScTokens

KEYWORDS = frozenset(["if", "else", "match", "case", "try", "catch", "finally", "throw", "return", "yield",
                      "do", "while", "for", "with", "extends", "forSome", "new", "this", "super", "null",
                      "true", "false", "val", "var", "def", "lazy", "import", "type", "class", "object",
                      "trait", "package", "implicit", "override", "private", "protected", "final", "sealed",
                      "abstract", "given", "using", "then", "end", "extension"])
SEQ_TYPES = frozenset(["Seq", "List", "Vector", "Set", "Array", "Iterable", "IndexedSeq", "Buffer", "ListBuffer",
                       "ArrayBuffer", "Stream", "LazyList", "Option", "Some", "Optional"])
ELEMENT_STEPS = frozenset(["head", "last", "headOption", "lastOption", "get", "getOrElse", "orNull", "orElse",
                           "min", "max", "apply", "find", "maxBy", "minBy", "reduce"])
SAME_STEPS = frozenset(["filter", "filterNot", "sorted", "sortBy", "sortWith", "distinct", "take", "drop",
                        "reverse", "tail", "init", "toList", "toSeq", "toVector", "toSet", "orElse"])
ACCESSOR = ("get", "is", "to", "has")


class ScFileInfo(FileInfo):
    def __init__(self, ctx: ExtractContext, facts: FileFacts, tk: ScTokens, resolver, types: List[ScType],
                 lines: List[str]) -> None:
        # `import a.B.fn` / `import a.B._`: a bare `fn(..)` may be a member of object `B`
        members = {n: f.rpartition(".")[0] for n, f in resolver.simple_to_fqn.items()
                   if n[:1].islower() and "." in f}
        super().__init__(ctx, facts, tk, resolver, types, members, list(resolver.wildcards),
                         lambda *a: False, None)
        self.http_types = frozenset()
        self.parser = ScalaDeclParser(tk, lines)

    def norm_scala(self, text: str, tvars) -> str:
        return self.norm(scala_type_text(text) if ("[" in text or "=>" in text or "*" in text) else text, tvars)


class ScScan(Scan):
    ARG_ANGLES = False      # `<` is only ever an operator in a Scala argument list
    def __init__(self, fi: ScFileInfo, jt: ScType, caller: str, tvars, bounds=None) -> None:
        super().__init__(fi, jt, caller, tvars, bounds=bounds)
        self.localdefs: Set[str] = set()
        self.nopush: Set[int] = set()                  # for-header brackets: bindings stay in the for scope
        self.for_ends: List[Tuple[int, int]] = []      # (token index the for expression ends, scope depth)
        self.due: List[Tuple[int, str, object]] = []   # (token index, kind, payload): bindings applied once their rhs is scanned

    # ------------------------------------------------------------- walking

    def run(self, a: int, b: int) -> None:
        tk = self.tk
        i = a
        while i < b:
            if self.for_ends and any(i >= e[0] for e in self.for_ends):   # a for / lambda / case body is over
                depth = min(e[1] for e in self.for_ends if i >= e[0])
                del self.scopes[depth:]
                self.for_ends = [e for e in self.for_ends if e[1] < depth]
            if self.due:
                self._apply_due(i)
            k, t = tk.kind[i], tk.text[i]
            if k == "op":
                if t == "{" and i not in self.nopush:
                    self.scopes.append({})
                elif t == "}" and i not in self.nopush:
                    if len(self.scopes) > 1:
                        self.scopes.pop()
                elif t == "(":
                    c = tk.close(i)
                    if tk.at(c + 1) == "=>" and c < b:
                        self._open_body(c + 2, i, lambda_=True)
                        self._lambda_params(i + 1, c)
                        i = c + 2
                        continue
                i += 1
                continue
            if k != "id" or i in self.consumed:
                i += 1
                continue
            nxt = tk.at(i + 1)
            if nxt == "=>" and t not in KEYWORDS:
                self._open_body(i + 2, i, lambda_=True)
                self.scopes[-1][t] = None
                i += 2
                continue
            if t == "for" and nxt in ("(", "{"):
                self._for(i)
                i += 1
                continue
            if t == "case" and tk.at(i + 1) not in ("class", "object"):
                i = self._case(i, b)
                continue
            if t in ("val", "var"):
                i = self._val(i, b)
                continue
            if t == "def" and tk.is_id(i + 1):
                i = self._local_def(i, b)
                continue
            if t == "new":
                self.chain(i, True)
                i += 1
                continue
            if t in KEYWORDS and t not in ("this", "super"):
                i += 1
                continue
            self.chain(i, True)
            i += 1

    def _for(self, i: int) -> None:
        """`for { p <- e; x = v } yield body`: open a scope for the header and the body. Each binder is
        declared only once its own segment (`p <- e` / `x = v`) is scanned, so a later `f <- ..` does not
        hide an outer `f` used by an earlier generator. The scope ends with the yield / do expression."""
        tk = self.tk
        o = i + 1
        c = tk.close(o)
        self.nopush.update((o, c))
        self.for_ends.append((self._for_end(c + 1), len(self.scopes)))
        self.scopes.append({})
        seg, depth, j = o + 1, 0, o + 1
        while j <= c:
            if j == c or (tk.kind[j] == "op" and tk.text[j] == ";") or \
                    (j > seg and tk.line[j] > tk.line[j - 1] and not self._continues(j)):
                self._segment(seg, j)
                seg = j + 1 if j < c and tk.text[j] == ";" else j
                if j < c and tk.text[j] != ";":
                    j += 1
                    continue
            if j < c and tk.kind[j] == "op" and tk.text[j] in "([{":
                j = tk.close(j)
            j += 1

    def _continues(self, j: int) -> bool:
        tk = self.tk
        return tk.text[j] in (".", ")", "]", "}") or tk.text[j - 1] in (".", ",", "(", "[", "<-", "=", "if")

    def _segment(self, a: int, e: int) -> None:
        tk = self.tk
        q = a
        while q < e:
            if tk.kind[q] == "op" and tk.text[q] in "([{":
                q = tk.close(q)
            elif tk.text[q] == "<-" and tk.kind[q] == "op":
                g = q + 1                              # the binder is live from the guard (`if ..`) on
                while g < e and not (tk.text[g] == "if" and tk.kind[g] == "id"):
                    g = tk.close(g) + 1 if tk.kind[g] == "op" and tk.text[g] in "([{" else g + 1
                self.due.append((g, "gen", range(a, q)))
                return
            elif tk.text[q] == "=" and tk.kind[q] == "op" and q > a and tk.at(q + 1) != "=" and tk.at(q - 1) != "=":
                if q == a + 1 and tk.is_id(a):
                    self.due.append((e, "val", (tk.text[a], q + 1)))
                else:
                    self.due.append((e, "gen", range(a, q)))
                return
            q += 1

    def _apply_due(self, i: int) -> None:
        keep = []
        for ev in self.due:
            if ev[0] > i:
                keep.append(ev)
            elif ev[1] == "gen":
                for q in ev[2]:
                    self._binder(q)
            else:
                self.scopes[-1][ev[2][0]] = self._dry(ev[2][1])
        self.due = keep

    def _for_end(self, s: int) -> int:
        """Token index just past the `yield` / `do` expression that follows a for header."""
        tk = self.tk
        if tk.at(s) in ("yield", "do"):
            s += 1
        j, first = s, tk.line[s] if s < tk.n else 0
        while j < tk.n:
            if tk.kind[j] == "op" and tk.text[j] in "([{":
                j = tk.close(j) + 1
                continue
            if tk.kind[j] == "op" and tk.text[j] in ");]}":
                return j
            if j > s and tk.line[j] > tk.line[j - 1] and not self._continues(j) and tk.text[j] not in ("else", "match"):
                return j
            j += 1
        return j

    def _lambda_params(self, a: int, c: int) -> None:
        tk = self.tk
        from .annotation_args import _split
        for s, e in _split(tk, a, c):
            if tk.is_id(s) and tk.at(s + 1) == ":" and s + 2 < e:
                r = self.fi.parser._parse_type(s + 2)
                typed = (self.fi.norm_scala(r[1], self.tvars), ()) if r else None
                self.scopes[-1][tk.text[s]] = typed
            elif tk.is_id(s):
                self.scopes[-1][tk.text[s]] = None

    def _case(self, i: int, b: int) -> int:
        """`case P(a, b: T) =>`: binders are declared (typed when written `x: T`), the guard and
        the arrow are skipped; the body is scanned by the main loop."""
        tk = self.tk
        j = i + 1
        while j < b and not (tk.text[j] == "=>" and tk.kind[j] == "op"):     # find the arrow first
            j = tk.close(j) + 1 if tk.kind[j] == "op" and tk.text[j] in "([{" else j + 1
        self._open_body(j + 1, i, lambda_=False)
        j = i + 1
        while j < b and not (tk.text[j] == "=>" and tk.kind[j] == "op"):
            if tk.kind[j] == "op" and tk.text[j] in "([{":
                for q in range(j + 1, tk.close(j)):
                    self._binder(q)
                j = tk.close(j) + 1
                continue
            self._binder(j)
            j += 1
        return j + 1

    def _open_body(self, body: int, at: int, lambda_: bool) -> None:
        """Binders of a lambda / `case` live in their own scope, popped where the body ends. A lambda
        written as the first thing in a `{` block already has that block's scope."""
        tk = self.tk
        if lambda_ and tk.at(at - 1) == "{" and (at - 1) not in self.nopush:
            return
        end, j = body, body
        while j < tk.n:
            if tk.kind[j] == "op" and tk.text[j] in "([{":
                j = tk.close(j) + 1
                continue
            if tk.kind[j] == "op" and tk.text[j] in ")]}":
                break
            if tk.kind[j] == "op" and tk.text[j] == ";" or (lambda_ and tk.kind[j] == "op" and tk.text[j] == ","):
                break
            if not lambda_ and tk.kind[j] == "id" and tk.text[j] == "case" and tk.at(j + 1) not in ("class", "object"):
                break
            j += 1
        end = j
        self.for_ends.append((end, len(self.scopes)))
        self.scopes.append({})

    def _binder(self, q: int) -> None:
        tk = self.tk
        if tk.kind[q] != "id" or not tk.text[q][:1].islower() or tk.text[q] in KEYWORDS:
            return
        if tk.at(q - 1) == "." or tk.at(q + 1) in ("(", "."):
            return
        if tk.at(q + 1) == ":":
            r = self.fi.parser._parse_type(q + 2)
            self.scopes[-1][tk.text[q]] = (self.fi.norm_scala(r[1], self.tvars), ()) if r else None
        else:
            self.scopes[-1][tk.text[q]] = None

    def _val(self, i: int, b: int) -> int:
        tk = self.tk
        j = i + 1
        if tk.at(j) == "(":                      # `val (a, b) = ..`
            for q in range(j + 1, tk.close(j)):
                if tk.is_id(q):
                    self.scopes[-1][tk.text[q]] = None
            return tk.close(j) + 1
        if not tk.is_id(j):
            return i + 1
        name = tk.text[j]
        j += 1
        if tk.at(j) == ":":
            r = self.fi.parser._parse_type(j + 1)
            if r:
                self.scopes[-1][name] = (self.fi.norm_scala(r[1], self.tvars), ())
                from .java_flow import type_uses
                anchor = anchor_at(self.fi.ctx, tk.line[i])
                if anchor is not None:
                    type_uses(self.fi.facts, scala_type_text(r[1]), anchor, self.caller, self.fi.resolver)
                return r[0]
            self.scopes[-1][name] = None
            return j
        if tk.at(j) == "=":
            nt = self.fi.parser.new_type(j + 1, tk.n)
            self.scopes[-1][name] = ((self.fi.norm_scala(nt, self.tvars), ()) if nt
                                     else self._dry(j + 1))
        else:
            self.scopes[-1][name] = None
        return j

    def _local_def(self, i: int, b: int) -> int:
        tk = self.tk
        name = tk.text[i + 1]
        self.localdefs.add(name)
        j = i + 2
        if tk.at(j) == "[":
            j = tk.close(j) + 1
        while tk.at(j) == "(":
            c = tk.close(j)
            for ptype, pname, *_ in self.fi.parser._params(j + 1, c):
                self.scopes[-1][pname] = (self.fi.norm_scala(ptype, self.tvars), ())
            j = c + 1
        return j

    # ------------------------------------------------------------- chains

    def _dry(self, i: int) -> Optional[TExpr]:
        end, te = self.chain(i, False)
        tk = self.tk
        if tk.at(end) == ".":                        # a leading-dot line continues the chain (`new B()\n  .build()`)
            return None
        if end >= tk.n or tk.line[end] > tk.line[end - 1] or tk.at(end) in (";", ")", "}", ",", "match"):
            return te
        return None

    def apply(self, te: Optional[TExpr], step: str) -> Optional[TExpr]:
        if te is None:
            return None
        base, steps = te
        cls = split_type(base)[0]
        if not steps and cls.rsplit(".", 1)[-1] in SEQ_TYPES and cls.rsplit(".", 1)[-1] not in self.fi.types:
            _, args, _ = split_type(base)
            if step.startswith("m:") and args:
                name = step[2:]
                if name in ELEMENT_STEPS:
                    return (args[0], ())
                if name in SAME_STEPS:
                    return te
            return None
        return super().apply(te, step)

    def chain(self, i: int, emit: bool) -> Tuple[int, Optional[TExpr]]:
        tk, fi = self.tk, self.fi
        k, t = tk.kind[i], tk.text[i]
        j = i + 1
        te: Optional[TExpr] = None
        prim_var: Optional[str] = None
        if k in ("str", "chr", "num"):
            return i + 1, None
        if t == "new":
            return self._new(i, emit)
        if t == "(":
            c = tk.close(i)
            end, inner = self.chain(i + 1, False) if i + 1 < c else (c, None)
            te = inner if end == c else None
            j = c + 1
        elif k == "id":
            if t == "this":
                te = (self.cls_type, ())
            elif t == "super":
                sup = self._super_type()
                te = (sup, ()) if sup else None
            elif t in KEYWORDS or t == "_":
                return i + 1, None
            elif tk.at(j) == "[" and t[:1].isupper() is False and tk.at(tk.close(j) + 1) == "(":
                # `foo[T](..)`: a generic bare call
                j = tk.close(j) + 1
                te = self._bare_call(t, i, j, emit)
                j = self._skip_args(j)
            elif tk.at(j) == "(" or (tk.at(j) == "{" and tk.line[j] == tk.line[i] and not t[:1].isupper()
                                      and self.lookup(t)[0] is False and t not in fi.resolver.simple_to_fqn):
                found, val = self.lookup(t)
                if found:                            # `f(x)` on a local function value
                    te = None
                    j = self._skip_args(j)
                elif t in self.localdefs:
                    j = self._skip_args(j)
                elif t[:1].isupper():                # `Foo(..)`: construction through the companion
                    te = self._type_ref(t)
                    self._type_use(t, i, emit)
                    if emit:
                        self.consumed.add(i)
                        self._argo = j
                        self.emit(te[0], "<init>", tk.line[i], "new", (), strict=False)
                        self._argo = None
                    j = self._skip_args(j)
                else:
                    te = self._bare_call(t, i, j, emit)
                    j = self._skip_args(j)
            else:
                found, val = self.lookup(t)
                if found:
                    te = val
                    prim_var = t
                elif t[:1].isupper() and not ALL_CAPS.match(t):
                    te = self._type_ref(t)
                    self._type_use(t, i, emit)
                elif ALL_CAPS.match(t) and t not in fi.resolver.simple_to_fqn:
                    te = self.apply((self.cls_type, ()), "f:" + t)
                elif t in fi.resolver.simple_to_fqn:
                    te = self._type_ref(t)
                    self._type_use(t, i, emit)
                elif t[:1].islower() and tk.at(j) == "." and self._package_path(i):
                    j, te = self._package_path(i)
                else:
                    te = self.apply((self.cls_type, ()), "f:" + t)
        else:
            return i + 1, None
        return self._hops(j, te, emit, prim_var)

    def _bare_call(self, name: str, i: int, open_i: int, emit: bool) -> Optional[TExpr]:
        tk, fi = self.tk, self.fi
        if emit:
            self._open = open_i if tk.at(open_i) == "(" else None
            alts = tuple(o + "#" + name for o in ([fi.static_imports[name]] if name in fi.static_imports else [])
                         ) + tuple(o + "#" + name for o in fi.static_wild)
            self.emit(self.cls_type, name, tk.line[i], "invoke", (), strict=True, alts=alts)
            self._open = None
            self.consumed.add(i)
        return self.apply((self.cls_type, ()), "m:" + name)

    def _skip_args(self, j: int) -> int:
        """Past every argument list: `(a)(b) { x => .. }`; a `{` counts only on the same line."""
        tk = self.tk
        while True:
            if tk.at(j) == "(":
                j = tk.close(j) + 1
            elif tk.at(j) == "{" and j > 0 and tk.line[j] == tk.line[j - 1]:
                j = tk.close(j) + 1
            else:
                return j

    def _hops(self, j: int, te: Optional[TExpr], emit: bool, prim_var: Optional[str]) -> Tuple[int, Optional[TExpr]]:
        tk = self.tk
        first = True
        while True:
            if tk.at(j) == "." and tk.is_id(j + 1):
                name_i = j + 1
                name = tk.text[name_i]
                k2 = name_i + 1
                if tk.at(k2) == "[":
                    k2 = tk.close(k2) + 1
                called = tk.at(k2) == "(" or (tk.at(k2) == "{" and tk.line[k2] == tk.line[name_i])
                if emit:
                    self.consumed.add(name_i)
                recv = te
                if called:
                    self._open = k2 if tk.at(k2) == "(" else None
                    if emit and recv is not None:
                        self.emit_te(recv, name, tk.line[name_i], "invoke", prim_var if first else None)
                    self._open = None
                    te = self.apply(recv, "m:" + name)
                    j = self._skip_args(k2)
                else:
                    te = self._access(recv, name, name_i, emit)
                    j = k2
                first = False
                continue
            if tk.at(j) == "." and tk.at(j + 1) in ("this", "class"):
                te = None
                j += 2
                continue
            if tk.at(j) == "(" and te is not None and not first:
                j = self._skip_args(j)             # `x.y(a)(b)`, apply on a value
                continue
            # infix call: `logger info msg`
            if te is not None and tk.is_id(j) and tk.text[j] not in KEYWORDS and tk.line[j] == tk.line[j - 1] \
                    and j + 1 < tk.n and tk.kind[j + 1] in ("str", "id", "num"):
                if emit:
                    self.consumed.add(j)
                    self.emit(te[0], tk.text[j], tk.line[j], "invoke", te[1], strict=True)
                return j + 1, None
            break
        return j, te

    def _access(self, recv: Optional[TExpr], name: str, name_i: int, emit: bool) -> Optional[TExpr]:
        """`a.b` without parentheses: a field of a repo type, or a parameterless method. Strict, so the
        row is dropped unless a method of that name exists; the step is `m:` for accessor-looking names
        (`getName`, `isOpen`), `f:` otherwise."""
        if recv is None:
            return None
        base, steps = recv
        if not steps and name[:1].isupper() and not ALL_CAPS.match(name) and self._is_type_ref(recv):
            return (base + "." + name, ())
        if ALL_CAPS.match(name):
            return self.apply(recv, "f:" + name)
        local = self.fi.fields.get(split_type(base)[0]) if not steps else None
        if local is not None and name in local:
            return (local[name], ())
        is_acc = name.startswith(ACCESSOR) and len(name) > 2 and name[2:3].isupper() or \
            name.startswith("get") and len(name) > 3 and name[3:4].isupper()
        if emit and is_acc:
            self.emit(base, name, self.tk.line[name_i], "invoke", steps, strict=True)
        return self.apply(recv, ("m:" if is_acc else "f:") + name)

    def _new(self, i: int, emit: bool) -> Tuple[int, Optional[TExpr]]:
        tk = self.tk
        r = self.fi.parser._parse_type(i + 1)
        if r is None:
            return i + 1, None
        e, ttext = r
        norm = self.fi.norm_scala(ttext, self.tvars)
        if emit:
            self.consumed.update(range(i + 1, e))
        te: TExpr = (norm, ())
        if tk.at(e) == "(":
            close = tk.close(e)
            after = close + 1
            if tk.at(after) == "{" and tk.line[after] == tk.line[close]:
                return after, None
            if emit:
                self._argo = e
                self.emit(split_type(norm)[0], "<init>", tk.line[i], "new", (), strict=False)
                self._argo = None
            self._type_use(ttext.split("[", 1)[0], i + 1, emit)
            return self._hops(after, te, emit, None)
        if tk.at(e) == "{":                         # `new T { .. }`: anonymous
            return e, None
        return e, None


def scan_file(ctx: ExtractContext, facts: FileFacts, tk: ScTokens, types: List[ScType], resolver,
              lines: List[str], constants: Dict[str, str]) -> Dict[str, int]:
    """Append `kind: call` rows for every method, constructor and initialiser body."""
    fi = ScFileInfo(ctx, facts, tk, resolver, types, lines)
    fi.constants = constants
    fi.own = frozenset(jt.name for jt in types)
    for jt in types:
        tv = jt.all_tparams()
        for m in jt.members:
            if m.kind == "field":
                fi.fields.setdefault(jt.fqn, {})[m.name] = fi.norm_scala(m.ftype, tv) if m.ftype else ""
    before = len(facts.uses)
    for jt in types:
        tv = jt.all_tparams()
        for m in jt.members:
            for sp in (m.body, m.init):
                if not sp or sp[1] <= sp[0]:
                    continue
                mtv = tv | set(m.tparams)
                scan = ScScan(fi, jt, m.symbol, mtv, bounds=jt.all_bounds())
                if m.kind in ("method", "ctor"):
                    scan.declare_params(m.params)
                    scan.caller_sig = m.sig
                scan.run(*sp)
    calls = sum(1 for u in facts.uses[before:] if u.get("kind") == "call")
    return {"call_rows": calls}
