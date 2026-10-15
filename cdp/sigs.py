"""Signature ids for overloaded methods: `Owner#name(T1,T2)`.

The name `Owner#name` stays the primary id everywhere (claims, links, `--as-of`, `symbol`).
Overloads share it, so a definition whose name has more than one definition in the same
owner *in one file* also carries `sig`, and the call rows emitted from its body carry
`from_sig`. A method that is not overloaded has no `sig`: its signature id is its name.

The rule -- one function, `param_type`, used by Java, Scala and C# alike:
  1. start from the parameter type as the extractor resolved it (`norm_type`'s text);
  2. erase generic arguments: every `<...>` group is dropped, nested ones included;
  3. drop the type-variable marker (`~T` -> `T`) and all whitespace;
  4. a varargs parameter (Java `T...`, Scala `T*`, C# `params T[]`) is written `T...`; a C# nullable
     value type keeps its `?` (`long?`), which the resolved text drops.
`sig = Owner#name(` + the types joined by `,` + `)`. Two overloads of one name that erase to the same
sig (`f(List<A>)`, `f(List<B>)`) keep their generic arguments instead -- step 2 is skipped for them.
Two that are still identical (a Scala class and its companion object, a C# explicit interface
implementation next to the public method) get a qualifier after the parentheses: `@object`, the
interface (`@IEnumerable`), else their 1-based position among the identical ones (`@2`).

A call to an overloaded name is resolved to one overload at xref time (`resolve`), where
every overload of the target is known: first by argument count against each overload's
arity range, then -- only among overloads of that count -- by the argument types the
extractor could see (literals, typed locals/parameters/fields). A type that is not known
matches anything; a candidate wins only when it is the one overload whose known argument
types all equal its parameter types. Anything else is not guessed: the call keeps every
remaining overload as `sig_candidates`.
"""

from __future__ import annotations

import re
from typing import Callable, Dict, List, Optional, Sequence, Tuple

# arity: (min, max); max None = unbounded (varargs)
Arity = Tuple[int, Optional[int]]


def erase(t: str) -> str:
    """Steps 2-3 of the rule: drop `<...>` groups, `~` markers and whitespace."""
    out: List[str] = []
    depth = 0
    for ch in t or "":
        if ch == "<":
            depth += 1
        elif ch == ">":
            depth = max(0, depth - 1)
        elif depth == 0 and not ch.isspace() and ch != "~":
            out.append(ch)
    return "".join(out)


def param_type(t: str, varargs: bool = False, generics: bool = False) -> str:
    """One parameter's type in a signature id (the whole rule); `generics` keeps `<...>` (step 2 skipped)."""
    s = ("".join(ch for ch in t or "" if not ch.isspace() and ch != "~") if generics else erase(t)) or "?"
    if varargs:
        s = (s[:-2] if s.endswith("[]") else s) + "..."
    return s


def sig_of(name: str, types: Sequence[str]) -> str:
    return "%s(%s)" % (name, ",".join(types))


def _counts(items) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for x in items:
        if x:
            out[x] = out.get(x, 0) + 1
    return out


def overload_sigs(entries: Sequence[Tuple[str, Sequence[Tuple[str, bool]], str]]) -> List[Optional[str]]:
    """`[(Owner#name, [(resolved param type, varargs), ...], qualifier hint), ...]` for every method and
    constructor definition of one file, in source order -> its sig, or None when the name is defined once."""
    count = _counts(name for name, _, _ in entries)
    out = [sig_of(name, [param_type(t, v) for t, v in ps]) if count[name] > 1 else None
           for name, ps, _ in entries]
    seen = _counts(out)
    out = [sig_of(name, [param_type(t, v, generics=True) for t, v in ps]) if sig and seen[sig] > 1 else sig
           for sig, (name, ps, _) in zip(out, entries)]
    seen = _counts(out)
    hinted = [sig + "@" + hint if sig and seen[sig] > 1 and hint else sig for sig, (_, _, hint) in zip(out, entries)]
    seen = _counts(hinted)
    nth: Dict[str, int] = {}
    final: List[Optional[str]] = []
    for sig in hinted:
        if sig and seen[sig] > 1:
            k = nth[sig] = nth.get(sig, 0) + 1
            if k > 1:
                sig += ("%d" if ")@" in sig else "@%d") % k
        final.append(sig)
    return final


def assign(types, normalise: Callable[[str, set], str]) -> None:
    """Set `m.sig` on every overloaded method/constructor of one file's parsed types (Java, Scala, C#
    member objects); `normalise(type text, type vars)` is the extractor's own resolution. A C# type
    with a primary constructor (`pparams`) has an `<init>` definition of its own: it counts, and its
    sig lands on `jt.primary_sig`."""
    members = []
    entries = []
    for jt in types:
        tv = jt.all_tparams()
        if getattr(jt, "pparams", None) is not None:
            members.append((jt, None))
            entries.append((jt.fqn + "#<init>", [(normalise(t, tv), False) for t, _ in jt.pparams], ""))
        for m in jt.members:
            if m.kind not in ("method", "ctor") or getattr(m, "nodef", False):
                continue
            mtv = tv | set(m.tparams)
            last = len(m.params) - 1
            members.append((jt, m))
            pnull = getattr(m, "pnull", None) or ()
            hint = getattr(m, "explicit", "") or ("object" if getattr(jt, "is_object", False) else "")
            entries.append((m.symbol, [(normalise(t, mtv) + ("?" if i < len(pnull) and pnull[i] else ""),
                                        m.varargs and i == last)
                                       for i, (t, _) in enumerate(m.params)], hint.rsplit(".", 1)[-1]))
    for (jt, m), sig in zip(members, overload_sigs(entries)):
        if m is None:
            jt.primary_sig = sig
            continue
        m.sig = sig
        if m.varargs and m.arity is None:
            m.arity = (len(m.params) - 1, None)


def define_fields(row: Dict, m) -> None:
    """`sig` on an overloaded member's define row, and `arity` ([min, max], max null = unbounded)
    when that is not exactly its parameter count. Nothing on a member that is not overloaded."""
    if not getattr(m, "sig", None):
        return
    row["sig"] = m.sig
    n = len(m.params)
    if m.arity and tuple(m.arity) != (n, n):
        row["arity"] = list(m.arity)


def is_sig(node: str) -> bool:
    """`pkg.A#m(int)` (or `pkg.A#m(int)@object`) is a signature node; `pkg.A#m`, `config:(dynamic)` are not."""
    _, sep, member = node.partition("#")
    return bool(sep) and "(" in member and (member.endswith(")") or ")@" in member)


_DUP_SUFFIX = re.compile(r"\)@\d+$")


def collision(sites: Sequence[Dict]) -> Tuple[bool, Optional[int]]:
    """`(collision, overloads)` for one symbol's sites. Several sites that all carry distinct signatures
    are overloads (`overloads: N`), not a collision. A collision is one declaration at more than one site:
    two sites with the same signature (a positional `@2` is a duplicate in one file), or several sites of
    something without signatures (a class in main and test)."""
    if len(sites) < 2:
        return False, None
    if all(s.get("sig") for s in sites):
        keys = [_DUP_SUFFIX.sub(")", s["sig"]) for s in sites]
        return len(set(keys)) < len(keys), len(set(keys))
    return True, None


def name_of(node: str) -> str:
    """`pkg.A#m(int,String)` -> `pkg.A#m`; anything else unchanged."""
    if not is_sig(node):
        return node
    owner, _, member = node.partition("#")
    return owner + "#" + member.split("(", 1)[0]


def same_method(a: str, b: str) -> bool:
    """`A#m(int)` -> `A#m(String)`: one overload delegating to another. Path walks do not count it as a
    hop -- it is the same method; counting it cut real paths over the hop limit once overloads split."""
    return is_sig(a) and is_sig(b) and name_of(a) == name_of(b)


def short(node: str) -> str:
    """Display form: `pkg.A#m(java.lang.String)` -> `A#m(java.lang.String)`; others as before
    (`rsplit('.')`), so a signature's dotted parameter types are not cut."""
    if is_sig(node):
        owner, _, member = node.partition("#")
        return owner.rsplit(".", 1)[-1] + "#" + member
    return node.rsplit(".", 1)[-1]


def sig_types(sig: str) -> List[str]:
    """The parameter types of a sig (split at depth-0 commas)."""
    inner = sig[sig.index("(", sig.index("#")) + 1:sig.rindex(")")]
    if not inner:
        return []
    out, depth, cur = [], 0, []
    for ch in inner:
        if ch in "([<":
            depth += 1
        elif ch in ")]>":
            depth -= 1
        if ch == "," and depth == 0:
            out.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    out.append("".join(cur))
    return out


# ------------------------------------------------------------------ call sites

_ALIASES = {"integer": "int", "int32": "int", "int64": "long", "bool": "boolean", "character": "char",
            "single": "float", "int16": "short", "char": "char"}


def canon(t: str) -> str:
    """What two type spellings must agree on to match: erased, simple name, lower case, Java/C#/Scala
    primitive aliases folded (`Integer`/`Int`/`int`, `string`/`String`)."""
    s = erase(t).rstrip("?")       # a local's resolved type has no `?`: `long?` must not lose to `long`
    if s.endswith("..."):
        s = s[:-3] + "[]"
    base = s.rsplit(".", 1)[-1].lower()
    return _ALIASES.get(base, base)


def literal_type(kind: str, text: str) -> Optional[str]:
    """The static type of one literal token, or None."""
    if kind == "str":
        return "String"
    if kind == "chr":
        return "char"
    if kind == "num":
        t = text.lower().replace("_", "")
        if t.startswith("0x") or t.startswith("0b"):
            return "long" if t.endswith("l") else "int"
        if t.endswith("l"):
            return "long"
        if t.endswith("f"):
            return "float"
        if t.endswith("d") or t.endswith("m") or "." in t or "e" in t:
            return "double"
        return "int"
    if kind == "id" and text in ("true", "false"):
        return "boolean"
    return None


def call_args(tk, o: Optional[int], typeof: Callable[[int, int], Optional[str]],
              skip_angle: Optional[Callable[[int], Optional[int]]] = None
              ) -> Tuple[Optional[int], Optional[List[str]]]:
    """`(argc, argt)` for the call parentheses at token `o`: the top-level argument count and, when at
    least one is known, each argument's type (`?` when not known). `(None, None)` with no `(`."""
    if o is None or o < 0 or tk.at(o) != "(":
        return None, None
    c = tk.close(o)
    if c == o + 1:
        return 0, None
    segs, s, j = [], o + 1, o + 1
    while j < c:
        if tk.kind[j] == "op" and tk.text[j] in "([{":
            j = tk.close(j)
        elif tk.kind[j] == "op" and tk.text[j] == "<" and skip_angle is not None:
            k = skip_angle(j)
            if k and k <= c:
                j = k - 1
        elif tk.kind[j] == "op" and tk.text[j] == ",":
            segs.append((s, j))
            s = j + 1
        j += 1
    segs.append((s, c))
    types = [typeof(a, b) if b > a else None for a, b in segs]
    argt = [(erase(t) or "?") if t else "?" for t in types] if any(types) else None
    return len(segs), argt


def simple_arg(tk, a: int, b: int, lookup, this_type: Optional[str]) -> Optional[str]:
    """A literal, `-literal`, `this`, or one identifier the scan has a type for (local, parameter,
    field). Everything else is unknown."""
    if b - a == 2 and tk.text[a] == "-" and tk.kind[a + 1] == "num":
        a += 1
    if b - a != 1:
        return None
    kind, text = tk.kind[a], tk.text[a]
    lit = literal_type(kind, text)
    if lit:
        return lit
    if kind != "id":
        return None
    if text == "this":
        return this_type
    found, val = lookup(text)
    if found and val and not val[1] and val[0] and not val[0].startswith("~"):
        return val[0]
    return None


# ------------------------------------------------------------------ resolution

def _admits(arity: Arity, argc: int) -> bool:
    lo, hi = arity
    return argc >= lo and (hi is None or argc <= hi)


def site_arity(site: Dict) -> Arity:
    a = site.get("arity")
    if a:
        return a[0], a[1]
    n = len(sig_types(site["sig"]))
    return n, n


def resolve(sites: Sequence[Dict], argc: Optional[int], argt: Optional[Sequence[str]]
            ) -> Tuple[Optional[str], Optional[str], List[str]]:
    """One call against the definition sites of its (overloaded) target ->
    `(sig, how, candidates)`: `how` is `arity` or `type`; with no single winner `sig` is None and
    `candidates` lists every overload still possible (all of them when nothing narrows)."""
    by_sig: Dict[str, Dict] = {}
    for s in sites:
        if s.get("sig"):
            by_sig.setdefault(s["sig"], s)
    if not by_sig:
        return None, None, []
    every = sorted(by_sig)
    if argc is None:
        return None, None, every
    fit = [g for g in every if _admits(site_arity(by_sig[g]), argc)]
    if len(fit) == 1:
        return fit[0], "arity", []
    if not fit:
        return None, None, every
    if argt and any(t != "?" for t in argt):
        exact = []
        for g in fit:
            ptypes = sig_types(g)
            ok = True
            for i, t in enumerate(argt):
                if t == "?":
                    continue
                p = ptypes[i] if i < len(ptypes) else (ptypes[-1] if ptypes and ptypes[-1].endswith("...") else None)
                if p is None:
                    ok = False
                    break
                if p.endswith("...") and i >= len(ptypes) - 1:
                    p = p[:-3]
                if canon(p) != canon(t):
                    ok = False
                    break
            if ok:
                exact.append(g)
        if len(exact) == 1:
            return exact[0], "type", []
    return None, None, fit
