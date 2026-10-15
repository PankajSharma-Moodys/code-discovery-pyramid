"""Call sites from C# member bodies.

The C# twin of `java_body`: tokens, declared locals/parameters/fields, a receiver followed left to
right. `a.B().C` is a call to `B` on `a`'s declared type and a call to `C` on whatever `B` returns;
what the file cannot settle travels as a *chain* (`m:B` method result, `f:x` member, `e` element,
`a` index, `w` await) that `cdp/cstypes.py` walks against the symbol table. A call it cannot type
produces nothing rather than a wrong edge.

Rows are `uses[]` with `kind: "call"`: `fqn` `Type#method` (the receiver's static type or the
chain's base), `from_symbol`, `chain`/`recv`, `alts`, `strict` (drop unless the hierarchy declares
the method: C# has no generated members), `how` for `new`/`ctor`/`ref`, `ext` for a receiver the
repository does not declare (a BCL type: only an extension method of the repository can match).
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Set, Tuple

from .. import sigs
from .base import ExtractContext, FileFacts, anchor_at, is_third_party, mk_use
from .csharp_decl import NOT_TYPE, CMember, CType, parse_type, skip_angle
from .csharp_interp import holes
from .csharp_tokens import CsTokens
from .csharp_types import (BCL_MEMBERS, ELEMENT_COLLECTIONS, LAMBDA_ELEMENT, MOQ_LAMBDA, PRIMS, bcl_step, is_bcl,
                           norm_type, strip_path_args)
from .java_flow import type_uses
from .java_types import split_type

TExpr = Tuple[str, Tuple[str, ...]]
EXPR_KW = frozenset(["return", "throw", "else", "case", "yield", "do", "is", "as", "in", "await", "async", "static",
                     "ref", "out", "not", "and", "or", "when", "with", "switch"])
NO_VAR = NOT_TYPE | frozenset(["true", "false", "null", "nameof", "typeof", "default", "sizeof", "checked", "unchecked",
                               "stackalloc", "global", "delegate", "params", "unsafe", "fixed", "lock", "base", "this"])
DECL_PREV = frozenset([";", "{", "}", "(", ",", ")", "using", "await", "const", "static", "out", "ref", "readonly",
                       "unsafe", "else", ":"])
DECL_NEXT = frozenset(["=", ";", ",", ")", "[", "in", "=>", "when"])
MAX_STEPS = 10
GENERIC_FACTORY = frozenset(["GetService", "GetRequiredService", "GetRequiredKeyedService", "GetKeyedService",
                             "Resolve", "ResolveRequired", "Deserialize", "DeserializeObject", "CreateInstance",
                             "GetValue", "Get", "GetRequiredSection", "Unwrap", "As", "ReadFromJsonAsync", "Parse"])
OBJECT_METHODS = frozenset(["ToString", "Equals", "GetHashCode", "GetType", "MemberwiseClone", "Finalize"])
GROUP_HOSTS = LAMBDA_ELEMENT | frozenset(["ConvertAll", "Run", "StartNew", "Subscribe", "ForEach", "Register", "Retry"])


class FileInfo:
    def __init__(self, ctx: ExtractContext, facts: FileFacts, tk: CsTokens, resolver, types: List[CType],
                 statics: List[Dict]) -> None:
        self.ctx, self.facts, self.tk, self.resolver = ctx, facts, tk, resolver
        self.types = {t.fqn: t for t in types}
        self.static_types = [s["fqn"] for s in statics if not is_third_party(s["fqn"])]
        self.fields: Dict[str, Dict[str, str]] = {}

    def norm(self, text: str, tvars) -> str:
        return norm_type(strip_path_args(text), lambda n: n if n in PRIMS else self.resolver.resolve(n)[0], tvars)


class Scan:
    def __init__(self, fi: FileInfo, jt: CType, caller: str, tvars, tk: Optional[CsTokens] = None) -> None:
        self.fi, self.jt, self.caller, self.tvars = fi, jt, caller, tvars
        self.tk = tk or fi.tk
        self.scopes: List[Dict[str, Optional[TExpr]]] = [{}]
        self.consumed: Set[int] = set()
        self.hints: Dict[int, List[Optional[TExpr]]] = {}
        self.expect: Optional[str] = None            # type a target-typed `new()` / `return new()` takes
        self.new_types: Dict[int, TExpr] = {}        # target-typed `new` token -> (type, steps) its context gives
        self.cls_type = jt.fqn
        self.line_of = None                          # interpolation holes: the line of the string token
        self.init_braces: Set[int] = set()           # `{` of object initializers: `Name = new()` is not an assignment
        self.caller_sig: Optional[str] = None        # the enclosing overload's sig (cdp/sigs.py), if any
        self._argo: Optional[int] = None             # `(` of the call being emitted, for `argt`

    # ------------------------------------------------------------ entry

    def declare_params(self, params: List[Tuple[str, str]]) -> None:
        for ptype, name in params:
            self.scopes[-1][name] = (self.fi.norm(ptype, self.tvars), ())

    def line(self, i: int) -> int:
        return self.line_of if self.line_of is not None else self.tk.line[i]

    def run(self, a: int, b: int) -> None:
        tk = self.tk
        i = a
        while i < b:
            k, t = tk.kind[i], tk.text[i]
            if k == "str":
                self._interpolation(i)
                i += 1
                continue
            if k == "op":
                if t == "{":
                    self.scopes.append({"\0init": None} if i in self.init_braces else {})
                elif t == "}":
                    if len(self.scopes) > 1:
                        self.scopes.pop()
                elif t == "(" and i not in self.consumed:
                    i = self._paren(i)
                    continue
                elif t == "=" and tk.at(i + 1) == "new" and tk.at(i + 2) == "(":
                    self._assign_new(i)
                i += 1
                continue
            if k != "id" or i in self.consumed:
                i += 1
                continue
            if tk.at(i + 1) == "=>" and t not in EXPR_KW:
                self.scopes[-1][t] = (self.hints.get(i) or [None])[0]
                i += 2
                continue
            if t == "is" or t == "case":
                self._pattern(i + 1)
                i += 1
                continue
            if t == "return" and tk.at(i + 1) == "new" and tk.at(i + 2) == "(" and self.expect:
                self.new_types[i + 1] = (self.expect, ())
                i += 1
                continue
            if t == "out" or t == "ref":
                i += 1
                continue
            if t in ("new", "this", "base", "await"):
                self.chain(i, True)
                i += 1
                continue
            if t == "delegate" and tk.at(i + 1) == "(":
                self._lambda_params(i + 1, tk.close(i + 1))
                i += 1
                continue
            if t in NO_VAR or t in EXPR_KW:
                i += 1
                continue
            if self._declaration(i):
                i += 1
                continue
            self.chain(i, True)
            i += 1

    # ------------------------------------------------------- statements

    def _paren(self, i: int) -> int:
        tk = self.tk
        close = tk.close(i)
        if tk.at(close + 1) == "=>":
            self._lambda_params(i, close)
            return i + 1
        prev = tk.text[i - 1] if i > 0 else ""
        prev_kind = tk.kind[i - 1] if i > 0 else "op"
        if prev in (")", "]", ">") or (prev_kind == "id" and prev not in EXPR_KW and prev not in NO_VAR) \
                or prev in ("if", "while", "for", "foreach", "using", "lock", "switch", "catch", "fixed"):
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
                        s0 = seg[0] if tk.text[seg[0]] not in ("ref", "in", "out", "scoped") else seg[1]
                        r = parse_type(tk, s0)
                        if r and r[0] == seg[-1] and r[1] != "var":
                            typed = (self.fi.norm(r[1], self.tvars), ())
                    self.scopes[-1][name] = typed or (hint[n] if n < len(hint) else None)
                    n += 1
                seg = []
            elif tk.kind[j] == "id":
                seg.append(j)
            j += 1

    def _pattern(self, i: int) -> None:
        """`is T x`, `is not T x`, `case T x:`; the variable is declared with T."""
        tk = self.tk
        while tk.at(i) in ("not", "const"):
            i += 1
        r = parse_type(tk, i)
        if not r:
            return
        j, ttext = r
        if tk.at(j) == "{" and tk.close(j) + 1 < tk.n:
            j = tk.close(j) + 1
        if tk.is_id(j) and tk.text[j] not in ("when", "and", "or", "is", "as", "switch", "in") \
                and tk.at(j + 1) not in ("(", "."):
            self.scopes[-1][tk.text[j]] = (self.fi.norm(ttext, self.tvars), ())
            self._type_use(ttext, i, True)

    def _declaration(self, i: int) -> bool:
        tk = self.tk
        prev = tk.text[i - 1] if i > 0 else ";"
        if prev not in DECL_PREV:
            return False
        if tk.text[i] == "var" and tk.at(i + 1) == "(":
            c = tk.close(i + 1)
            for q in range(i + 2, c):
                if tk.kind[q] == "id" and tk.at(q + 1) in (",", ")"):
                    self.scopes[-1][tk.text[q]] = None
            return True
        r = parse_type(tk, i)
        if r is None:
            return False
        j, ttext = r
        if not tk.is_id(j) or tk.text[j] in NO_VAR or tk.text[j] in EXPR_KW and tk.text[j] != "in" \
                or tk.at(j + 1) not in DECL_NEXT:
            return False
        if tk.at(j + 1) == "=>" and prev not in ("{", ","):
            return False
        name = tk.text[j]
        self.consumed.add(j)
        if ttext == "var":
            val: Optional[TExpr] = None
            if tk.at(j + 1) == "=":
                val = self._dry(j + 2)
            elif tk.at(j + 1) == "in":
                src = self._dry(j + 2)
                val = self.apply(src, "e") if src else None
            self.scopes[-1][name] = val
            return True
        norm = self.fi.norm(ttext, self.tvars)
        self.scopes[-1][name] = (norm, ())
        if tk.at(j + 1) == "=" and tk.at(j + 3) == "(" and tk.at(j + 2) == "new":
            self.new_types[j + 2] = (norm, ())
        elif tk.at(j + 1) == "=" and tk.at(j + 2) == "[":
            self._init_news(j + 2, norm)
        self._type_use(ttext, i, True)
        return True

    def _assign_new(self, i: int) -> None:
        """`x = new(...)`, `this.x = new(...)`: the type is the declared type of `x`."""
        tk = self.tk
        if i < 1 or not tk.is_id(i - 1) or "\0init" in self.scopes[-1]:
            return
        found, val = self.lookup(tk.text[i - 1])
        if found and val and not val[1]:
            self.new_types[i + 1] = val

    def _interpolation(self, i: int) -> None:
        """Calls inside `$"...{expr}..."` holes: the hole is tokenised and scanned in this scope."""
        text = self.tk.text[i]
        if "$" not in text[:4] or "{" not in text:
            return
        for hole, nl in holes(text):
            sub = CsTokens([hole])
            if not sub.n:
                continue
            inner = Scan(self.fi, self.jt, self.caller, self.tvars, sub)
            inner.caller_sig = self.caller_sig
            inner.scopes = self.scopes
            inner.line_of = self.tk.line[i] + nl
            inner.run(0, sub.n)

    def _type_use(self, text: str, i: int, emit: bool) -> None:
        if emit and self.line_of is None:
            anchor = anchor_at(self.fi.ctx, self.tk.line[i])
            if anchor is not None:
                type_uses(self.fi.facts, text, anchor, self.caller, self.fi.resolver)

    # -------------------------------------------------- expression chains

    def _dry(self, i: int) -> Optional[TExpr]:
        end, te = self.chain(i, False)
        if self.tk.at(end) in (";", ",", ")") or end >= self.tk.n:
            return te
        return None

    def lookup(self, name: str) -> Tuple[bool, Optional[TExpr]]:
        for sc in reversed(self.scopes):
            if name in sc:
                return True, sc[name]
        t: Optional[CType] = self.jt
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
        if not steps:
            if step.startswith("f:"):
                f = self.fi.fields.get(split_type(base)[0])
                if f is not None and step[2:] in f:
                    return (f[step[2:]], ())
            if is_bcl(base) or "[]" in base or base in PRIMS:
                out = bcl_step(base, step)
                return (out, ()) if out else None
            if step == "f:Object" and split_type(base)[0].rsplit(".", 1)[-1] == "Mock" and split_type(base)[1]:
                return (split_type(base)[1][0], ())
        if len(steps) >= MAX_STEPS:
            return None
        return (base, steps + (step,))

    def _base_type(self) -> Optional[str]:
        if self.jt.extends:
            return self.fi.norm(self.jt.extends[0], self.tvars)
        return None

    def _group_host(self, i: int) -> bool:
        """Is the argument at `i` plausibly a method group? Only the arguments of a call that takes a
        delegate (`Select(Convert)`, `ConvertAll`, a generic `Handle<TException>(Method)`) are looked at:
        every other `(a.B, c)` is a property read and would be a row for nothing."""
        tk = self.tk
        j = i - 1
        while j > 0:
            if tk.text[j] in (")", "]", "}") and tk.kind[j] == "op":
                j = tk.match[j] if 0 <= tk.match[j] < j else j
            elif tk.text[j] == "(" and tk.kind[j] == "op":
                break
            elif tk.text[j] in (";", "{", "}"):
                return False
            j -= 1
        if j < 1:
            return False
        name = tk.text[j - 1]
        if name == "nameof":
            return False
        if name == ">":                                       # `Handle<TException>(Method)`
            return True
        return name in GROUP_HOSTS

    def _argc(self, o: int) -> Optional[int]:
        """Arguments in the call parentheses at `o` (top-level commas)."""
        tk = self.tk
        if o < 0 or tk.at(o) != "(":
            return None
        c = tk.close(o)
        if c == o + 1:
            return 0
        n, j = 1, o + 1
        while j < c:
            if tk.kind[j] == "op" and tk.text[j] in "([{":
                j = tk.close(j)
            elif tk.text[j] == "," and tk.kind[j] == "op":
                n += 1
            elif tk.text[j] == "<" and tk.kind[j] == "op":
                k = skip_angle(tk, j)
                if k and k <= c:
                    j = k - 1
            j += 1
        return n

    def _targs(self, i: int, k: int) -> List[str]:
        """The normalised type arguments of the `<...>` at tokens i..k."""
        tk = self.tk
        out: List[str] = []
        j = i + 1
        while j < k - 1:
            if tk.at(j) == ",":
                j += 1
                continue
            r = parse_type(tk, j)
            if r is None:
                return []
            j, text = r
            out.append(self.fi.norm(text, self.tvars))
        return out

    def chain(self, i: int, emit: bool) -> Tuple[int, Optional[TExpr]]:
        tk, fi = self.tk, self.fi
        k, t = tk.kind[i], tk.text[i]
        te: Optional[TExpr] = None
        j = i + 1
        prim_var: Optional[str] = None
        tref: Optional[str] = None      # raw dotted text while the head is a type / namespace path
        if k in ("str", "chr", "num"):
            return i + 1, None
        if t == "new":
            return self._new(i, emit)
        if t == "await":
            if emit:
                self.consumed.add(i + 1)
            end, te = self.chain(i + 1, emit)
            return end, self.apply(te, "w")
        if t == "this":
            te = (self.cls_type, ())
        elif t == "base":
            sup = self._base_type()
            te = (sup, ()) if sup else None
        elif t == "(":
            close = tk.close(i)
            te = self._paren_type(i, close)
            j = close + 1
            if te is None and self._cast_at(i, close):
                return j, None
        elif t in ("typeof", "nameof", "default", "sizeof") and tk.at(j) == "(":
            c = tk.close(j)
            if t == "default":
                r = parse_type(tk, j + 1)
                if r and r[0] == c:
                    return c + 1, (fi.norm(r[1], self.tvars), ())
            return c + 1, None
        elif k == "id":
            if t in NO_VAR:
                return i + 1, None
            targs: List[str] = []
            if tk.at(j) == "<":
                k2 = skip_angle(tk, j)
                if k2 and tk.at(k2) == "(":
                    targs = self._targs(j, k2)
                    j = k2
                elif k2 and tk.at(k2) == "." and tk.is_id(k2 + 1):
                    r = parse_type(tk, i)
                    if r and tk.at(r[0]) == ".":
                        te = (fi.norm(r[1], self.tvars), ())
                        tref = r[1]
                        j = r[0]
            if tk.at(j) == "(" and te is None:
                found, _ = self.lookup(t)
                if found:                                   # a delegate / local function value
                    te = None
                    j = tk.close(j) + 1
                else:
                    if emit:
                        alts = tuple(o + "#" + t for o in fi.static_types)
                        self._argo = j
                        self.emit(self.cls_type, t, tk.line[i], "invoke", (), alts=alts,
                                  strict=True, targs=targs, argc=self._argc(j))
                        self._argo = None
                        self._lambdas((self.cls_type, ()), t, j)
                        self.consumed.add(i)
                    step = "m:" + t + ("<%s>" % ",".join(targs) if targs else "")
                    te = self.apply((self.cls_type, ()), step)
                    j = tk.close(j) + 1
            elif te is None:
                found, val = self.lookup(t)
                if found:
                    te = val
                    prim_var = t
                elif t in fi.resolver.local_types or t in fi.resolver.aliases or t[:1].isupper():
                    te = (fi.resolver.resolve(t)[0], ())
                    tref = t
                    self._type_use(t, i, emit)
                else:
                    te = self.apply((self.cls_type, ()), "f:" + t)
                    prim_var = t
        else:
            return i + 1, None

        group: Optional[Tuple[Optional[TExpr], str, int]] = None   # a trailing member that may be a method group
        if emit and k == "id" and tk.at(i + 1) in (",", ")") and tk.at(i - 1) in ("(", ",") \
                and not self.lookup(t)[0] and t not in NO_VAR and self._group_host(i):
            group = ((self.cls_type, ()), t, i)
        # ---- postfix hops
        while True:
            c = tk.at(j)
            if c in (".", "?.") and tk.is_id(j + 1):
                name = tk.text[j + 1]
                e2 = j + 2
                targs = []
                if tk.at(e2) == "<":
                    k2 = skip_angle(tk, e2)
                    if k2 and tk.at(k2) == "(":
                        targs = self._targs(e2, k2)
                        e2 = k2
                if tk.at(e2) == "(":
                    if emit:
                        self.consumed.add(j + 1)
                    recv = te
                    te = self._hop(recv, name, j + 1, emit, targs, e2, tref is not None)
                    if emit:
                        self._lambdas(recv, name, e2)
                    tref = None
                    prim_var = None
                    j = tk.close(e2) + 1
                    continue
                if emit:
                    self.consumed.add(j + 1)
                group = (te, name, j + 1) if te is not None and tk.at(j + 2) in (",", ")") \
                    and tk.at(i - 1) in ("(", ",") and emit and self._group_host(i) else None
                if tref is not None:
                    tref += "." + name
                    te = (fi.resolver.resolve(tref)[0], ())
                else:
                    te = self.apply(te, "f:" + name)
                prim_var = None
                j += 2
                continue
            if c == "!" and tk.at(j + 1) in (".", "?.", "["):
                j += 1
                continue
            if c == "?" and tk.at(j + 1) == "[":
                j += 1
                continue
            if c == "[" and (te is not None or tref is None):
                te = self.apply(te, "a")
                tref = None
                prim_var = None
                j = tk.close(j) + 1
                continue
            break
        if emit and group is not None and group[0] is not None:
            # `xs.Select(Foo.Convert)`, `Run(Handler)`: a method group is a reference to the method
            self.emit(group[0][0], group[1], tk.line[group[2]], "ref", group[0][1], strict=True)
            self.consumed.add(group[2])
        return j, te

    def _paren_type(self, o: int, c: int) -> Optional[TExpr]:
        tk = self.tk
        if self._cast_at(o, c):
            return None
        if tk.at(o + 1) == "(" and self._cast_at(o + 1, tk.close(o + 1)) and tk.close(o + 1) + 1 < c:
            r = parse_type(tk, o + 2)
            inner_close = tk.close(o + 1)
            if r and inner_close + 1 < c:
                end, _ = self.chain(inner_close + 1, False) if tk.kind[inner_close + 1] in ("id", "op") else (c, None)
                if end == c:
                    return (self.fi.norm(r[1], self.tvars), ())
        if o + 1 >= c:
            return None
        end, te = self.chain(o + 1, False)
        if end == c:
            return te
        if tk.at(end) == "as":
            r = parse_type(tk, end + 1)
            if r and r[0] == c:
                return (self.fi.norm(r[1], self.tvars), ())
        return None

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
        return nk in ("id", "str", "num", "chr") and nxt not in ("is", "as", "in", "and", "or", "when") \
            or nxt in ("(", "!", "~")

    def _new(self, i: int, emit: bool) -> Tuple[int, Optional[TExpr]]:
        tk = self.tk
        j = i + 1
        steps: Tuple[str, ...] = ()
        if tk.at(j) == "(":                      # target-typed `new(...)`: the context names the type
            got = self.new_types.get(i)
            if got is None:
                return tk.close(j) + 1, None
            norm, steps = got
            e = j
        elif tk.at(j) == "[":                    # `new[] { ... }`
            return i + 1, None
        elif tk.at(j) == "{":                    # anonymous type
            return i + 1, None
        else:
            r = parse_type(tk, j)
            if r is None:
                return i + 1, None
            e, ttext = r
            ttext = strip_path_args(ttext)
            if ttext.endswith("[]"):             # `new T[] { new(...) }` is an array
                if tk.at(e) == "{":
                    self._init_news(e, self.fi.norm(ttext, self.tvars))
                return i + 1, None
            if tk.at(e) not in ("(", "{"):
                return i + 1, None
            norm = self.fi.norm(ttext, self.tvars)
            if emit:
                self.consumed.update(range(j, e))
            self._type_use(ttext, j, emit)
        te: Optional[TExpr] = (norm, ()) if not steps else None
        if emit:
            self._argo = e
            self.emit(split_type(norm)[0], "<init>", tk.line[i], "new", steps, strict=False)
            self._argo = None
        if tk.at(e) == "{":
            self.init_braces.add(e)
            self._init_news(e, norm)
            return tk.close(e) + 1, te
        close = tk.close(e)
        j = close + 1
        if tk.at(j) == "{":
            self.init_braces.add(j)
            self._init_news(j, norm)
            j = tk.close(j) + 1
        # `new Foo().Bar()`: the instance is the receiver of the chain
        return self._continue(j, te, emit)

    def _init_news(self, o: int, norm: str) -> None:
        """Target-typed `new(...)` inside an initializer: `{ Prop = new(...) }` has the type of
        `Prop`, an element of `{ new(...), ... }` (a list/array/`[..]`) the element type."""
        tk = self.tk
        c = tk.close(o)
        base, args, _ = split_type(norm)
        elem = args[0] if args and base.rsplit(".", 1)[-1] in ELEMENT_COLLECTIONS else (
            norm[:-2] if norm.endswith("[]") else None)
        j = o + 1
        while j < c:
            t = tk.text[j]
            if tk.kind[j] == "op" and t in "([{":
                j = tk.close(j) + 1
                continue
            if t == "new" and tk.at(j + 1) == "(":
                if tk.is_id(j - 2) and tk.at(j - 1) == "=" and tk.at(j - 3) in ("{", ",", "[") and o in self.init_braces:
                    self.new_types[j] = (norm, ("f:" + tk.text[j - 2],))
                elif elem and tk.at(j - 1) in ("{", ",", "["):
                    self.new_types[j] = (elem, ())
            j += 1

    def _continue(self, j: int, te: Optional[TExpr], emit: bool) -> Tuple[int, Optional[TExpr]]:
        tk = self.tk
        while tk.at(j) in (".", "?.") and tk.is_id(j + 1):
            name = tk.text[j + 1]
            e2 = j + 2
            targs: List[str] = []
            if tk.at(e2) == "<":
                k2 = skip_angle(tk, e2)
                if k2 and tk.at(k2) == "(":
                    targs, e2 = self._targs(e2, k2), k2
            if tk.at(e2) == "(":
                if emit:
                    self.consumed.add(j + 1)
                recv = te
                te = self._hop(recv, name, j + 1, emit, targs, e2, False)
                if emit:
                    self._lambdas(recv, name, e2)
                j = tk.close(e2) + 1
            else:
                if emit:
                    self.consumed.add(j + 1)
                te = self.apply(te, "f:" + name)
                j += 2
        return j, te

    # ------------------------------------------------------------- rows

    def _hop(self, recv: Optional[TExpr], name: str, name_i: int, emit: bool, targs: List[str], open_i: int,
             static: bool) -> Optional[TExpr]:
        if emit and recv is not None:
            self._argo = open_i
            self.emit(recv[0], name, self.tk.line[name_i], "invoke", recv[1], strict=True, targs=targs,
                      static=static, argc=self._argc(open_i))
            self._argo = None
        if targs and name in GENERIC_FACTORY and (recv is None or not recv[1]):
            if recv is None or is_bcl(recv[0]) or split_type(recv[0])[0] not in self.fi.types:
                if name not in ("Get", "Parse", "As") or recv is None or not is_bcl(recv[0]):
                    return (targs[0], ())
        if targs and name == "Cast" or name == "OfType":
            if targs:
                return ("System.Collections.Generic.IEnumerable<%s>" % targs[0], ())
        step = "m:" + name + ("<%s>" % ",".join(targs) if targs else "")
        return self.apply(recv, step)

    def emit(self, base: str, name: str, line: int, how: str, steps: Tuple[str, ...], strict: bool = False,
             alts: Tuple[str, ...] = (), targs: Optional[List[str]] = None, static: bool = False,
             argc: Optional[int] = None) -> None:
        fi = self.fi
        if not base:
            return
        cls = split_type(base)[0]
        if not cls or cls.startswith("~"):
            return
        ext = False
        if not steps:
            if cls in PRIMS or "[" in base or is_bcl(cls):
                # a BCL receiver: only an extension method of the repository can be the target
                if static or name in BCL_MEMBERS or name in OBJECT_METHODS or how != "invoke":
                    return
                ext = True
            elif is_third_party(cls):
                return
        elif is_third_party(cls) and not cls.startswith("System.Collections"):
            return
        anchor = anchor_at(fi.ctx, self.line_of if self.line_of is not None else line)
        if anchor is None:
            return
        _, state = fi.resolver.resolve(cls) if "." not in cls else (cls, "external")
        if cls in fi.types or (fi.resolver.pkg and cls.startswith(fi.resolver.pkg + ".")):
            state = "local" if cls not in fi.types else "external"
        row = mk_use("%s#%s" % (cls, name), anchor, via_import=False, resolved="external")
        row["kind"] = "call"
        row["from_symbol"] = self.caller
        row["speculative"] = state in ("local", "unresolved") and cls not in fi.types
        alt_list = list(alts)
        if alt_list:
            row["alts"] = alt_list
        if steps:
            row["chain"] = list(steps)
            row["recv"] = base
        if strict:
            row["strict"] = True
        if ext:
            row["ext"] = True
        if how != "invoke":
            row["how"] = how
        if targs:
            row["targs"] = targs
        if argc is not None:
            row["argc"] = argc
        self._overload_facts(row)
        fi.facts.uses.append(row)

    def _overload_facts(self, row: Dict) -> None:
        """`from_sig` (the overload this body is) and `argt` (argument types `resolve` picks an overload
        of the target by), plus `argc` where the row had none (`new X(..)`): cdp/sigs.py."""
        if self.caller_sig:
            row["from_sig"] = self.caller_sig
        if self._argo is None:
            return
        n, argt = sigs.call_args(self.tk, self._argo, self._arg_type, lambda j: skip_angle(self.tk, j))
        if "argc" not in row and n is not None:
            row["argc"] = n
        if argt:
            row["argt"] = argt

    def _arg_type(self, a: int, b: int) -> Optional[str]:
        return sigs.simple_arg(self.tk, a, b, self.lookup, self.cls_type)

    # ----------------------------------------------------------- lambdas

    def _lambdas(self, recv: Optional[TExpr], name: str, open_i: int) -> None:
        """Type the parameters of lambda arguments (`items.Where(x => ...)`, `mock.Setup(x => ...)`)."""
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
            if tk.at(s) == "async":
                s += 1
            if tk.is_id(s) and tk.at(s + 1) == "=>":
                n = 1
            elif tk.at(s) == "(" and tk.at(tk.close(s) + 1) == "=>":
                c = tk.close(s)
                n = 1 + sum(1 for q in range(s + 1, c) if tk.text[q] == ",") if c > s + 1 else 0
            else:
                continue
            base, args = split_type(recv[0])[0], split_type(recv[0])[1]
            if name in MOQ_LAMBDA and not recv[1] and base.rsplit(".", 1)[-1] == "Mock" and args:
                self.hints[s] = [(args[0], ())]
            elif n >= 1 and name in LAMBDA_ELEMENT:
                e = self.apply(recv, "e")
                self.hints[s] = [e] + [None] * (n - 1)
        return None


def emit_bodies(ctx, facts, tk, parser, types, resolver, statics, ns) -> None:
    fi = FileInfo(ctx, facts, tk, resolver, types, statics)
    for jt in types:
        tv = jt.all_tparams()
        fields = fi.fields.setdefault(jt.fqn, {})
        for ptype, pname in jt.pparams or ():
            fields[pname] = fi.norm(ptype, tv)
        for m in jt.members:
            if m.kind in ("field", "enum_const") and m.ftype:
                fields[m.name] = fi.norm(m.ftype, tv)
    for jt in types:
        tv = jt.all_tparams()
        for m in jt.members:
            if m.kind == "field" or m.kind == "enum_const":
                if m.kind == "field" and m.ftype:
                    scan = Scan(fi, jt, m.symbol, tv)
                    scan.expect = fi.norm(m.ftype, tv)
                    if m.init and m.init[1] > m.init[0]:
                        _seed(scan, tk, m.init[0])
                        scan.run(*m.init)
                    for a, b in m.bodies:
                        _seed(scan, tk, a)
                        scan.run(a, b)
                continue
            mtv = tv | set(m.tparams)
            scan = Scan(fi, jt, m.symbol, mtv)
            scan.caller_sig = m.sig
            scan.declare_params(m.params)
            scan.expect = fi.norm(m.ret, mtv) if m.kind == "method" and m.ret and m.ret not in ("void",) else None
            awaited = bcl_step(scan.expect, "w") if scan.expect else None
            if awaited:                       # `async Task<T> M() { return new(); }`
                scan.expect = awaited
            if m.ctor_init:
                a, b, which = m.ctor_init
                target = jt.fqn if which == "this" else (fi.norm(jt.extends[0], tv).split("<", 1)[0]
                                                         if jt.extends else "")
                if target:
                    scan._argo = a - 1
                    scan.emit(target, "<init>", tk.line[a - 2], "ctor", ())
                    scan._argo = None
                scan.run(a, b)
            if m.body:
                _seed(scan, tk, m.body[0])
                scan.run(*m.body)
    if parser.top_spans:
        owner = (ns + "." if ns else "") + "Program"
        top = CType("class", "Program", owner, None)
        scan = Scan(fi, top, owner + "#<Main>", frozenset())
        for a, b in parser.top_spans:
            scan.run(a, b)


def _seed(scan: Scan, tk: CsTokens, a: int) -> None:
    """`T x = new();`, `=> new()`: the first token is a target-typed `new`."""
    if tk.at(a) == "new" and tk.at(a + 1) == "(" and scan.expect:
        scan.new_types[a] = (scan.expect, ())
    elif tk.at(a) == "[" and scan.expect:
        scan._init_news(a, scan.expect)
