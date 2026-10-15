"""Call sites from Java member bodies.

Reads tokens, tracks declared locals, parameters and fields, and follows a
receiver chain left to right: `a.b().c()` is a call to `b` on `a`'s declared
type and a call to `c` on whatever `b` returns. The extractor sees one file, so
a type it cannot settle is carried as a *chain*: a base type plus steps
(`m:b` method result, `f:x` field, `e` element, `a` array index) that the
resolve phase walks against the symbol table. A call it cannot type at all
produces nothing, rather than a wrong edge.

Rows are `uses[]` with `kind: "call"`, as `java_flow` always produced:
    fqn         `Type#method`, the receiver's static type (or the chain's base)
    from_symbol the enclosing member
    chain       steps from `fqn`'s type to the receiver (absent for a plain receiver)
    alts        other owners the name may live in (wildcard imports, static imports)
    strict      drop the row unless some class in the hierarchy declares the method
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Set, Tuple

from .. import sigs
from .base import ExtractContext, FileFacts, anchor_at, is_third_party, mk_use
from .java_config import call_keys
from .java_decl import NOT_TYPE, JMember, JType, parse_type
from .java_tokens import Tokens
from .java_types import LAMBDA_ELEMENT, LAMBDA_MAP, is_jdk, jdk_step, split_type, wildcard_alts

PRIMS = frozenset(["int", "long", "double", "float", "boolean", "byte", "short", "char", "void"])
LITERALS = frozenset(["true", "false", "null"])
EXPR_KEYWORDS = frozenset(["return", "throw", "else", "case", "yield", "assert", "do", "instanceof"])
# every JLS keyword/literal that cannot name a variable (`in`, `record`, `var` can)
NO_VAR = NOT_TYPE | LITERALS | frozenset(["const", "goto"])
TExpr = Tuple[str, Tuple[str, ...]]
MAX_STEPS = 10
DECL_PREV = frozenset([";", "{", "}", "(", ",", ")", ":", "->", "final"])
DECL_NEXT = frozenset(["=", ";", ":", ",", ")", "["])
OBJECT_METHODS = frozenset(["toString", "equals", "hashCode", "getClass", "notify", "notifyAll", "wait",
                            "clone", "finalize"])
ALL_CAPS = re.compile(r"^[A-Z][A-Z0-9_]*$")


class FileInfo:
    """What the scanner needs to know about one file."""

    def __init__(self, ctx: ExtractContext, facts: FileFacts, tk: Tokens, resolver,
                 types: List[JType], static_imports: Dict[str, str], static_wild: List[str],
                 http_hook, event_hook=None) -> None:
        self.event_hook = event_hook
        self.ctx, self.facts, self.tk, self.resolver = ctx, facts, tk, resolver
        self.types = {t.fqn: t for t in types}
        self.static_imports, self.static_wild = static_imports, static_wild
        self.http_hook = http_hook
        self.fields: Dict[str, Dict[str, str]] = {}   # type fqn -> field name -> normalised type
        self.constants: Optional[Dict[str, str]] = None   # this file's constants (set by java_flow)
        self.own = frozenset()

    def resolve_name(self, name: str) -> str:
        if name in PRIMS:
            return name
        return self.resolver.resolve(name)[0]

    def norm(self, text: str, tvars) -> str:
        from .java_types import norm_type
        return norm_type(text, self.resolve_name, tvars)


class Scan:
    #: `<` in an argument list may open type arguments (`f(new HashMap<K, V>())`); not in Scala
    ARG_ANGLES = True

    def __init__(self, fi: FileInfo, jt: JType, caller: str, tvars, emit_types: bool = True,
                 bounds: Optional[Dict[str, List[str]]] = None) -> None:
        self.fi, self.tk, self.jt, self.caller, self.tvars = fi, fi.tk, jt, caller, tvars
        self.bounds = bounds or {}
        self.params: Dict[str, int] = {}
        self._open: Optional[int] = None   # token index of the `(` of the call being emitted
        self._argo: Optional[int] = None   # the same, for a constructor call (`new X(..)`, `this(..)`)
        self.caller_sig: Optional[str] = None   # the enclosing overload's sig (cdp/sigs.py), if any
        self.scopes: List[Dict[str, Optional[TExpr]]] = [{}]
        self.consumed: Set[int] = set()
        self.hints: Dict[int, List[Optional[TExpr]]] = {}
        self.emit_types = emit_types
        self.cls_type = jt.fqn
        self._sup = None

    # ------------------------------------------------------------ entry

    def declare_params(self, params: List[Tuple[str, str]]) -> None:
        for idx, (ptype, name) in enumerate(params):
            self.params[name] = idx
            self.scopes[-1][name] = (self.fi.norm(ptype, self.tvars), ())

    def run(self, a: int, b: int) -> None:
        tk = self.tk
        i = a
        while i < b:
            k, t = tk.kind[i], tk.text[i]
            if k == "op":
                if t == "{":
                    self.scopes.append({})
                elif t == "}":
                    if len(self.scopes) > 1:
                        self.scopes.pop()
                elif t == "(":
                    i = self._paren(i, b)
                    continue
                i += 1
                continue
            if k != "id" or i in self.consumed:
                i += 1
                continue
            if tk.at(i + 1) == "->":
                self.scopes[-1][t] = (self.hints.get(i) or [None])[0]
                i += 2
                continue
            if t == "instanceof" or (t == "case" and tk.at(i + 1) != "-"):
                self._pattern(i + 1)
                i += 1
                continue
            if t == "catch" and tk.at(i + 1) == "(":
                self._catch(i + 2)
                i += 1
                continue
            if t in ("new", "this", "super"):
                self.chain(i, True)
                i += 1
                continue
            if t in NO_VAR or t in EXPR_KEYWORDS:
                i += 1
                continue
            if self._declaration(i, b):
                i += 1
                continue
            self.chain(i, True)
            i += 1

    # ------------------------------------------------------- statements

    def _paren(self, i: int, b: int) -> int:
        """A `(` met in the main loop: lambda parameters, a cast or parenthesised
        expression (start of a chain), or call arguments (nothing to do)."""
        tk = self.tk
        close = tk.close(i)
        if tk.at(close + 1) == "->":
            self._lambda_params(i, close)
            return i + 1
        prev = tk.text[i - 1] if i > 0 else ""
        prev_kind = tk.kind[i - 1] if i > 0 else "op"
        if prev in (")", "]", ">") or (prev_kind == "id" and prev not in EXPR_KEYWORDS and prev not in NOT_TYPE
                                        and prev not in LITERALS):
            return i + 1
        self.chain(i, True)
        return i + 1

    def _lambda_params(self, o: int, c: int) -> None:
        tk = self.tk
        hint = self.hints.get(o) or []
        seg: List[int] = []
        n = 0
        j = o + 1
        while j <= c:
            if j == c or (tk.text[j] == "," and tk.kind[j] == "op"):
                if seg:
                    name = tk.text[seg[-1]]
                    typed = None
                    if len(seg) > 1:
                        r = parse_type(tk, seg[0] if tk.text[seg[0]] != "final" else seg[1])
                        if r and r[0] == seg[-1] and r[1] != "var":
                            typed = (self.fi.norm(r[1], self.tvars), ())
                    self.scopes[-1][name] = typed or (hint[n] if n < len(hint) else None)
                    n += 1
                seg = []
            elif tk.kind[j] == "id":
                seg.append(j)
            elif tk.text[j] in ("<", ">", ".", "[", "]", "?"):
                pass
            j += 1

    def _pattern(self, i: int) -> None:
        tk = self.tk
        while tk.text[i:i + 1] == ["final"]:
            i += 1
        r = parse_type(tk, i)
        if r and tk.is_id(r[0]) and tk.text[r[0]] not in ("when", "instanceof"):
            self.scopes[-1][tk.text[r[0]]] = (self.fi.norm(r[1], self.tvars), ())

    def _catch(self, i: int) -> None:
        tk = self.tk
        r = parse_type(tk, i)
        if not r:
            return
        j, first = r
        while tk.at(j) == "|":
            r2 = parse_type(tk, j + 1)
            if not r2:
                return
            j = r2[0]
        if tk.is_id(j):
            self.scopes[-1][tk.text[j]] = (self.fi.norm(first, self.tvars), ())

    def _declaration(self, i: int, b: int) -> bool:
        tk = self.tk
        prev = tk.text[i - 1] if i > 0 else ";"
        if prev not in DECL_PREV and not (tk.kind[i - 1] == "op" and prev == "@"):
            return False
        r = parse_type(tk, i)
        if r is None:
            return False
        j, ttext = r
        if not tk.is_id(j) or tk.text[j] in NO_VAR or tk.at(j + 1) not in DECL_NEXT:
            return False
        name = tk.text[j]
        if ttext == "var":
            val: Optional[TExpr] = None
            if tk.at(j + 1) == "=":
                val = self._dry(j + 2)
            elif tk.at(j + 1) == ":":
                src = self._dry(j + 2)
                val = self.apply(src, "e") if src else None
            self.scopes[-1][name] = val
            return True
        norm = self.fi.norm(ttext, self.tvars)
        self.scopes[-1][name] = (norm, ())
        if self.emit_types:
            from .java_flow import type_uses
            anchor = anchor_at(self.fi.ctx, tk.line[i])
            if anchor is not None:
                type_uses(self.fi.facts, ttext, anchor, self.caller, self.fi.resolver)
        return True

    # -------------------------------------------------- expression chains

    def _dry(self, i: int) -> Optional[TExpr]:
        """The type of the single chain expression starting at `i`, without
        emitting anything. None when it is not one chain ending the declarator."""
        end, te = self.chain(i, False)
        if self.tk.at(end) in (";", ",", ")", ":") or end >= self.tk.n:
            return te
        return None

    def lookup(self, name: str) -> Tuple[bool, Optional[TExpr]]:
        for sc in reversed(self.scopes):
            if name in sc:
                return True, sc[name]
        t: Optional[JType] = self.jt
        while t is not None:
            f = self.fi.fields.get(t.fqn)
            if f and name in f:
                return True, (f[name], ())
            t = t.outer
        return False, None

    def apply(self, te: Optional[TExpr], step: str) -> Optional[TExpr]:
        if te is None:
            return None
        base, steps = te
        if not base or base.startswith("~"):
            return None
        if not steps and step.startswith("f:"):
            cls = split_type(base)[0]
            f = self.fi.fields.get(cls)
            if f is not None and step[2:] in f:
                return (f[step[2:]], ())
        if not steps and is_jdk(base):
            out = jdk_step(base, step)
            return (out, ()) if out else None
        if len(steps) >= MAX_STEPS:
            return None
        return (base, steps + (step,))

    def _super_type(self) -> Optional[str]:
        if self.jt.extends:
            return self.fi.norm(self.jt.extends[0], self.jt.all_tparams())
        return None

    def chain(self, i: int, emit: bool) -> Tuple[int, Optional[TExpr]]:
        tk = self.tk
        fi = self.fi
        k, t = tk.kind[i], tk.text[i]
        te: Optional[TExpr] = None
        j = i + 1
        prim_var: Optional[str] = None
        line_i = i

        if k in ("str", "chr", "num"):
            return i + 1, None
        if t == "new":
            return self._new(i, emit)
        if t == "this":
            if tk.at(j) == "(":
                if emit:
                    self._argo = j
                    self.emit(self.cls_type, "<init>", tk.line[i], "ctor", (), strict=False)
                    self._argo = None
                return tk.close(j) + 1, None
            te = (self.cls_type, ())
        elif t == "super":
            if tk.at(j) == "(":
                sup = self._super_type()
                if emit and sup:
                    self._argo = j
                    self.emit(sup, "<init>", tk.line[i], "ctor", (), strict=False)
                    self._argo = None
                return tk.close(j) + 1, None
            sup = self._super_type()
            te = (sup, ()) if sup else None
        elif t == "(":
            close = tk.close(i)
            te = self._paren_type(i, close)
            j = close + 1
            if te is None and self._cast_at(i, close):
                return j, None
        elif k == "id":
            if t in NO_VAR and t not in ("this",):
                return i + 1, None
            if tk.at(j) == "(":
                # bare call: own, inherited, outer-class or statically imported
                if emit:
                    alts = tuple(o + "#" + t for o in ([fi.static_imports[t]] if t in fi.static_imports else [])
                                 ) + tuple(o + "#" + t for o in fi.static_wild)
                    self._open = j
                    self.emit(self.cls_type, t, tk.line[i], "invoke", (), strict=True, alts=alts)
                    self._open = None
                    self._lambdas((self.cls_type, ()), t, j)
                    self.consumed.add(i)
                c = tk.close(j)
                te = self._special(t, j, hop=False) or self.apply((self.cls_type, ()), "m:" + t)
                j = c + 1
            else:
                found, val = self.lookup(t)
                if found:
                    te = val
                    prim_var = t
                elif tk.at(j) == "::":
                    te = self._type_ref(t)
                    self._type_use(t, i, emit)
                elif t[:1].isupper() and (not ALL_CAPS.match(t) or (tk.at(j) == "." and tk.at(j + 1) == "this")):
                    te = self._type_ref(t)
                    self._type_use(t, i, emit)
                elif ALL_CAPS.match(t) and t not in fi.resolver.simple_to_fqn:
                    te = self.apply((self.cls_type, ()), "f:" + t)
                elif t[:1].islower() and tk.at(j) == "." and self._package_path(i):
                    j, te = self._package_path(i)
                elif t in fi.resolver.simple_to_fqn:
                    te = self._type_ref(t)
                    self._type_use(t, i, emit)
                else:
                    te = self.apply((self.cls_type, ()), "f:" + t)
                    prim_var = t
        else:
            return i + 1, None

        # ---- postfix hops
        first_hop = True
        while True:
            c = tk.at(j)
            if c == "." and tk.at(j + 1) == "<":
                k2 = tk.skip_angle(j + 1)
                if k2 and tk.is_id(k2) and tk.at(k2 + 1) == "(":
                    name = tk.text[k2]
                    if emit:
                        self.consumed.add(k2)
                    recv = te
                    te = self._hop(recv, name, k2, emit, prim_var if first_hop else None, "invoke")
                    if emit:
                        self._lambdas(recv, name, k2 + 1)
                    first_hop = False
                    j = tk.close(k2 + 1) + 1
                    continue
                break
            if c == "." and tk.at(j + 1) == "this":
                # `Outer.this` is the enclosing instance: the qualifier class itself
                if not (te is not None and not te[1] and self._is_type_ref(te)):
                    te = None
                j += 2
                continue
            if c == "." and tk.is_id(j + 1):
                name = tk.text[j + 1]
                if tk.at(j + 2) == "(":
                    if emit:
                        self.consumed.add(j + 1)
                    recv = te
                    te = self._hop(recv, name, j + 1, emit, prim_var if first_hop else None, "invoke")
                    if emit:
                        self._lambdas(recv, name, j + 2)
                    first_hop = False
                    j = tk.close(j + 2) + 1
                    continue
                if emit:
                    self.consumed.add(j + 1)
                if te is not None and not te[1] and name[:1].isupper() and not ALL_CAPS.match(name) \
                        and self._is_type_ref(te):
                    te = (te[0] + "." + name, ())
                else:
                    te = self.apply(te, "f:" + name)
                first_hop = False
                j += 2
                continue
            if c == "." and tk.at(j + 1) in ("class", "this", "new"):
                if tk.at(j + 1) == "new":
                    break
                te = None
                j += 2
                continue
            if c == "[":
                te = self.apply(te, "a")
                j = tk.close(j) + 1
                first_hop = False
                continue
            if c == "::" and (tk.is_id(j + 1) or tk.at(j + 1) == "new"):
                name = tk.text[j + 1]
                if emit and te is not None:
                    self.consumed.add(j + 1)
                    self.emit_te(te, "<init>" if name == "new" else name, tk.line[j + 1], "ref", None)
                return j + 2, None
            break
        return j, te

    def _is_type_ref(self, te: TExpr) -> bool:
        base = te[0]
        return base in self.fi.types or (base.split("<")[0].rsplit(".", 1)[-1][:1].isupper()
                                          and base.rsplit(".", 1)[-1] not in self.fi.fields)

    def _type_use(self, name: str, i: int, emit: bool) -> None:
        """`X.m()`, `X.CONST`, `X::m`, `X.class`: the qualifier is a use of class X itself."""
        if emit and self.emit_types:
            from .java_flow import type_uses
            anchor = anchor_at(self.fi.ctx, self.tk.line[i])
            if anchor is not None:
                type_uses(self.fi.facts, name, anchor, self.caller, self.fi.resolver)

    def _type_ref(self, name: str) -> TExpr:
        return (self.fi.resolve_name(name), ())

    def _package_path(self, i: int):
        """`org.slf4j.LoggerFactory.getLogger(...)`: lowercase segments then a type."""
        tk = self.tk
        j = i
        parts = [tk.text[j]]
        while tk.at(j + 1) == "." and tk.is_id(j + 2):
            j += 2
            parts.append(tk.text[j])
            if parts[-1][:1].isupper():
                for m in range(i, j + 1):
                    if tk.kind[m] == "id":
                        self.consumed.add(m)
                return j + 1, (".".join(parts), ())
            if not parts[-1][:1].islower():
                break
        return None

    def _paren_type(self, o: int, c: int) -> Optional[TExpr]:
        tk = self.tk
        if self._cast_at(o, c):
            r = parse_type(tk, o + 1)
            if r and tk.at(c + 1) != "":
                # `(Foo) x`: the cast covers the following expression; only
                # `((Foo) x).m()` types the parenthesised whole, handled below.
                return None
        if tk.at(o + 1) == "(" and self._cast_at(o + 1, tk.close(o + 1)) and tk.close(o + 1) + 1 < c:
            r = parse_type(tk, o + 2)
            inner_close = tk.close(o + 1)
            if r and inner_close + 1 < c:
                end, _ = self.chain(inner_close + 1, False) if tk.kind[inner_close + 1] == "id" else (c, None)
                if end == c:
                    return (self.fi.norm(r[1], self.tvars), ())
        end, te = self.chain(o + 1, False) if o + 1 < c else (c, None)
        return te if end == c else None

    def _cast_at(self, o: int, c: int) -> bool:
        tk = self.tk
        r = parse_type(tk, o + 1)
        if not r or r[0] != c:
            return False
        text = r[1]
        if not (text in PRIMS or text[:1].isupper() or "." in text):
            return False
        nxt = tk.text[c + 1] if c + 1 < tk.n else ""
        nk = tk.kind[c + 1] if c + 1 < tk.n else ""
        return nk in ("id", "str", "num", "chr") and nxt not in ("instanceof",) or nxt in ("(", "!", "~")

    def _new(self, i: int, emit: bool) -> Tuple[int, Optional[TExpr]]:
        tk = self.tk
        j = i + 1
        while tk.at(j) == "@":
            from .java_decl import skip_annotation
            j = skip_annotation(tk, j)
        r = parse_type(tk, j)
        if r is None:
            return i + 1, None
        e, ttext = r
        if tk.at(e) == "[":
            return i + 1, None
        if tk.at(e) != "(":
            return i + 1, None
        close = tk.close(e)
        if emit:
            self.consumed.update(range(j, e))
        norm = self.fi.norm(ttext, self.tvars)
        te: TExpr = (norm, ())
        anonymous = tk.at(close + 1) == "{"
        if emit and not anonymous:
            self._argo = e
            self.emit(split_type(norm)[0], "<init>", tk.line[i], "new", (), strict=False)
            self._argo = None
        if anonymous:
            return close + 1, None
        j = close + 1
        # `new Foo().bar()`: the instance is the receiver of the chain
        return self._continue(j, te, emit)

    def _continue(self, j: int, te: Optional[TExpr], emit: bool) -> Tuple[int, Optional[TExpr]]:
        tk = self.tk
        while tk.at(j) == "." and tk.is_id(j + 1):
            name = tk.text[j + 1]
            if tk.at(j + 2) == "(":
                if emit:
                    self.consumed.add(j + 1)
                recv = te
                te = self._hop(recv, name, j + 1, emit, None, "invoke")
                if emit:
                    self._lambdas(recv, name, j + 2)
                j = tk.close(j + 2) + 1
            else:
                if emit:
                    self.consumed.add(j + 1)
                te = self.apply(te, "f:" + name)
                j += 2
        return j, te

    # ------------------------------------------------------------- rows

    def _hop(self, recv: Optional[TExpr], name: str, name_i: int, emit: bool,
             prim_var: Optional[str], how: str) -> Optional[TExpr]:
        if emit and recv is not None:
            self._open = name_i + 1 if self.tk.at(name_i + 1) == "(" else None
            self.emit_te(recv, name, self.tk.line[name_i], how, prim_var)
            self._open = None
            if name == "post" and self.fi.event_hook is not None and not recv[1]:
                self.fi.event_hook(self, recv[0], name_i)
        special = self._special(name, name_i + 1, hop=True)
        return special or self.apply(recv, "m:" + name)

    def _special(self, name: str, open_i: int, hop: bool) -> Optional[TExpr]:
        """Mockito idioms whose result is the type of their argument:
        `verify(x)`, `spy(x)`, `mock(X.class)`, and `stubber.when(x)`."""
        if name not in ("verify", "spy", "mock") and not (hop and name == "when"):
            return None
        tk = self.tk
        if tk.at(open_i) != "(":
            return None
        j = open_i + 1
        if tk.is_id(j) and tk.at(j + 1) in (",", ")"):
            found, val = self.lookup(tk.text[j])
            return val if found else None
        c = tk.close(open_i)
        if c >= 3 and tk.at(c - 1) == "class" and tk.at(c - 2) == "." and tk.is_id(c - 3):
            r = parse_type(tk, j)
            if r and r[0] == c - 2:
                return (self.fi.norm(r[1], self.tvars), ())
        return None

    def emit_te(self, te: TExpr, name: str, line: int, how: str, prim_var: Optional[str]) -> None:
        base, steps = te
        self.emit(base, name, line, how, steps, prim_var=prim_var)

    def emit(self, base: str, name: str, line: int, how: str, steps: Tuple[str, ...], strict: bool = False,
             alts: Tuple[str, ...] = (), prim_var: Optional[str] = None,
             _seen: Tuple[str, ...] = (), argc: Optional[int] = None) -> None:
        fi = self.fi
        if not base:
            return
        cls = split_type(base)[0]
        if not cls:
            return
        if cls.startswith("~"):
            # A type variable: the call is on its bound(s). Each bound of an intersection
            # is tried; `strict` drops the ones that do not declare the method.
            if cls[1:] in self.bounds and len(_seen) < 4 and cls not in _seen:
                for text in self.bounds[cls[1:]]:
                    self.emit(fi.norm(text, self.tvars), name, line, how, steps, True, alts, prim_var,
                              _seen + (cls,))
            return
        if not steps and (cls in PRIMS or "[" in base):
            return
        simple = cls.rsplit(".", 1)[-1]
        if prim_var is not None and not steps and name != "<init>" and simple in fi.http_types:
            if fi.http_hook(line, self.caller, simple, prim_var, name):
                return
        if not steps:
            if is_jdk(cls) or (("." not in cls) and cls not in fi.types and
                               fi.resolver.resolve(cls)[1] == "third_party"):
                return
            if is_third_party(cls):
                return
        elif ("." not in cls and not is_jdk(cls) and fi.resolver.resolve(cls)[1] == "third_party"
              and cls not in fi.types):
            return
        elif is_third_party(cls) and not is_jdk(cls):
            return
        anchor = anchor_at(fi.ctx, line)
        if anchor is None:
            return
        _, state = fi.resolver.resolve(cls) if "." not in cls else (cls, "external")
        if cls in fi.types or cls.startswith(fi.resolver.pkg + ".") and fi.resolver.pkg:
            state = "local" if cls not in fi.types else "external"
        row = mk_use("%s#%s" % (cls, name), anchor, via_import=False, resolved="external")
        row["kind"] = "call"
        row["from_symbol"] = self.caller
        row["speculative"] = state in ("local", "unresolved") and cls not in fi.types
        alt_list = list(alts)
        if row["speculative"] and not steps:
            alt_list += wildcard_alts(fi.resolver, cls, "#" + name)
        if alt_list:
            row["alts"] = alt_list
        if steps:
            row["chain"] = list(steps)
            row["recv"] = base
        if strict:
            row["strict"] = True
        if how != "invoke":
            row["how"] = how
        if self._open is not None and fi.constants is not None:
            ka = call_keys(self.tk, self._open, fi.constants, fi.static_imports, fi.own, self.params)
            if ka:
                row["ka"] = ka
        self.overload_facts(row, argc)
        fi.facts.uses.append(row)

    def overload_facts(self, row: Dict, argc: Optional[int] = None) -> None:
        """`from_sig` (the overload this body is), `argc`/`argt` (what `resolve` picks an overload of
        the target by): cdp/sigs.py."""
        if self.caller_sig:
            row["from_sig"] = self.caller_sig
        o = self._open if self._open is not None else self._argo
        argt = None
        if o is not None:
            argc, argt = sigs.call_args(self.tk, o, self._arg_type, self.tk.skip_angle if self.ARG_ANGLES else None)
        if argc is not None:
            row["argc"] = argc
        if argt:
            row["argt"] = argt

    def _arg_type(self, a: int, b: int) -> Optional[str]:
        return sigs.simple_arg(self.tk, a, b, self.lookup, self.cls_type)

    # ----------------------------------------------------------- lambdas

    def _lambdas(self, recv: Optional[TExpr], name: str, open_i: int) -> None:
        tk = self.tk
        if recv is None or tk.at(open_i) != "(":
            return
        close = tk.close(open_i)
        starts = [open_i + 1]
        j = open_i + 1
        while j < close:
            if tk.kind[j] == "op" and tk.text[j] in "([{":
                j = tk.close(j)
            elif tk.text[j] == "," and tk.kind[j] == "op":
                starts.append(j + 1)
            j += 1
        for s in starts:
            if tk.is_id(s) and tk.at(s + 1) == "->":
                n = 1
            elif tk.at(s) == "(" and tk.at(tk.close(s) + 1) == "->":
                c = tk.close(s)
                n = 1 + sum(1 for q in range(s + 1, c) if tk.text[q] == ",") if c > s + 1 else 0
            else:
                continue
            if n == 1 and name in ("computeIfAbsent",):
                self.hints[s] = [self.apply(recv, "k")]
            elif n == 1 and name in LAMBDA_ELEMENT:
                self.hints[s] = [self.apply(recv, "e")]
            elif n == 2 and name in LAMBDA_MAP:
                self.hints[s] = [self.apply(recv, "k"), self.apply(recv, "v")]
            elif n == 2 and name in LAMBDA_ELEMENT:
                e = self.apply(recv, "e")
                self.hints[s] = [e, e]
