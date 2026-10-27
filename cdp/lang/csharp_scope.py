"""Settles the type names the C# extractor could not place, in C#'s own name-lookup order.

`Resolver` (one file, no symbol table) qualifies a simple name it cannot place into the file's own
namespace (`Ns.Foo`) and leaves a dotted name with an unknown head as written (`Sub.Foo`); both are
recorded as `guess:` file signals. That is right for a type of the same namespace and a phantom for a
type an enclosing type or namespace, a `using` or a `global using` brings in, or one outside the
repository. With the declared classes in view each guessed name settles by the rule of ECMA-334
(namespace and type names, simple names):

1. the members of each enclosing type, innermost first (nested types, then those inherited from its
   declared bases; the type itself only for a member, not for its own base list);
2. each enclosing namespace, innermost first, ending with the global namespace: a type (or
   namespace-qualified path) declared there;
3. only when none of those owns the name: the types of the `using` namespaces and `using static`
   types (a `using` imports types, never namespaces: a dotted name's head must be an imported type);
   exactly one owner settles it, several stay as guessed (C# rejects the program). An alias
   (`using A = N.T;`) names only itself and imports nothing.

Name and arity go together: `Foo` and `Foo<T>` are different types. With the `attribute` rule a name
also matches `<Name>Attribute`, and both matching is ambiguous. A name no declared type owns is not a
repository type: a guessed one reverts to the name as written (a framework or third-party type), a
relative one is kept. Left as guessed: a name an outer namespace and a `using` both own (the file does
not say if the `using` sits inside the namespace body, which would win), a name found only through a
file's other namespace blocks, and everything resolvable only through library namespaces.

`scope_of(file) -> (namespace, usings, guessed names)` (a using is a namespace/type name or an import
row with its anchor, from which an alias is told apart); `probe(fqns) -> the declared classes among
them` (a set lookup at scan time, an indexed query in the store). Optional: `arity(fqn)` the type
parameter counts a declared name has, `bases(fqn)` its declared bases (both unknown in the store).
"""

from __future__ import annotations

import re
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

NAME_RE = re.compile(r"[A-Za-z_$][\w$.]*")
USING_RE = re.compile(r"(global\s+)?using\s+(static\s+)?(?:@?(\w+)\s*=\s*)?([\w.@]+)")
EXACT_FIELDS = ("ret", "ftype", "params", "supertypes")     # type arguments kept as written
ERASED_FIELDS = ("sig", "from_sig", "argt", "recv")         # type arguments dropped: the arity is unknown
SIG_FIELDS = EXACT_FIELDS + ERASED_FIELDS
USE_TARGET_KINDS = frozenset(["call", "type", "extends", "implements"])   # a use whose `fqn` names a type (`T#member`)
CLASS_KINDS = frozenset(["class", "interface", "enum", "record", "annotation"])
AMBIGUOUS = object()
MAX_BASES = 24


def using_kinds(row) -> Tuple[bool, bool]:
    """`(is_import, is_global)` of an import row (or plain name): False for an alias, which imports nothing."""
    if isinstance(row, str):
        return True, False
    fq = row.get("fqn")
    text = (row.get("anchor") or {}).get("anchor") or ""
    found = [m for m in USING_RE.finditer(text) if m.group(4) == fq]
    if not found:
        return True, False
    return any(not m.group(3) for m in found), any(m.group(1) for m in found)


def import_names(rows: Iterable) -> List[str]:
    """The namespaces/types a file's `using` rows import (aliases dropped), in source order."""
    out = [r if isinstance(r, str) else r["fqn"] for r in rows if using_kinds(r)[0]]
    return list(dict.fromkeys(out))


def global_usings(rows: Iterable[Dict]) -> Dict[str, List[str]]:
    """`module -> names` of the `global using` directives: they apply to every file of the compilation
    (approximated by the module)."""
    out: Dict[str, List[str]] = {}
    for r in rows:
        imp, glob = using_kinds(r)
        if imp and glob:
            out.setdefault(r.get("module") or "", []).append(r["fqn"])
    return out


def arity_of(text: str, end: int) -> int:
    """The type argument count written right after a name ending at `end` (0 when none)."""
    if text[end:end + 1] != "<":
        return 0
    depth = commas = 0
    for ch in text[end:]:
        if ch == "<":
            depth += 1
        elif ch == ">":
            depth -= 1
            if not depth:
                return commas + 1
        elif ch == "," and depth == 1:
            commas += 1
    return 0


def rewrite(text: str, fix: Dict[Tuple[str, Optional[int]], str], exact: bool = True) -> str:
    return NAME_RE.sub(lambda m: fix.get((m.group(0), arity_of(text, m.end()) if exact else None), m.group(0)), text)


class CsSigScope:
    def __init__(self, scope_of, probe, arity=None, bases=None) -> None:
        self.scope_of = scope_of
        self.probe = probe
        self.arity = arity      # fqn -> frozenset of type parameter counts, or None
        self.bases = bases      # fqn -> declared base fqns, or None
        self.known: Dict[str, bool] = {}

    # ---------------------------------------------------------------- declared types

    def _fetch(self, fqns: Iterable[str]) -> None:
        need = {c for c in fqns if c not in self.known}
        if need:
            hit = set(self.probe(need))
            for c in need:
                self.known[c] = c in hit

    def _cls(self, fqn: str, arity: Optional[int]) -> bool:
        if not self.known.get(fqn):
            return False
        have = self.arity(fqn) if self.arity and arity is not None else None
        return have is None or arity in have

    def _chain(self, t: str) -> List[str]:
        """`t` then the declared bases it inherits members from (breadth first, cycle-safe)."""
        out = [t]
        i = 0
        while self.bases and i < len(out) and len(out) < MAX_BASES:
            out.extend(b for b in self.bases(out[i]) or () if b not in out)
            i += 1
        return out

    def _levels(self, ns: str, owner: str, inside: bool) -> Tuple[List[str], List[str]]:
        """(type prefixes with inherited ones, namespace prefixes ending with the global one)."""
        segs = owner[len(ns) + 1:].split(".")
        types: List[str] = []
        for i in range(len(segs) if inside else len(segs) - 1, 0, -1):
            types.extend(t for t in self._chain(ns + "." + ".".join(segs[:i])) if t not in types)
        parts = ns.split(".")
        return types, [".".join(parts[:i]) for i in range(len(parts), 0, -1)] + [""]

    def _paths(self, prefix: str, segs: Sequence[str], attr: bool) -> List[str]:
        base = prefix + "." if prefix else ""
        out = [base + ".".join(segs[:k]) for k in range(len(segs), 0, -1)]
        if attr:
            out.append(base + ".".join(segs[:-1] + [segs[-1] + "Attribute"]))
        return out

    def _hit(self, prefix: str, segs: Sequence[str], arity: Optional[int], attr: bool, imported: bool = False):
        """The declared name `prefix.segs` is (longest declared path; None, a name or AMBIGUOUS)."""
        base = prefix + "." if prefix else ""
        n = len(segs)
        if imported and n > 1 and not self._cls(base + segs[0], None):
            return None         # a `using` imports types, not namespaces
        for k in range(n, 0, -1):
            exact = k == n
            found = []
            for suffix in (("", "Attribute") if attr and exact else ("",)):
                path = base + ".".join(segs[:k - 1] + [segs[k - 1] + suffix])
                if self._cls(path, arity if exact else None):
                    found.append(path)
            if len(found) > 1:
                return AMBIGUOUS
            if found:
                return found[0] + "".join("." + s for s in segs[k:])
        return None

    # ---------------------------------------------------------------- settle

    def settle(self, texts: Sequence[str], file: str, owner: str, inside: bool = True,
               attribute: bool = False, exact: bool = True) -> Dict[Tuple[str, Optional[int]], str]:
        """`(name, arity) -> settled name` for each guessed name in `texts` (arity None when the texts
        are not `exact`: their type arguments are gone). `owner` is the type whose body holds them
        (`inside`), or the type whose base list it is (not `inside`)."""
        ns, usings, guessed = self.scope_of(file)
        if not ns or not guessed or not owner.startswith(ns + "."):
            return {}
        keys = {(m.group(0), arity_of(t, m.end()) if exact else None) for t in texts for m in NAME_RE.finditer(t) if m.group(0) in guessed}
        if not keys:
            return {}
        names = import_names(usings)
        types, spaces = self._levels(ns, owner, inside)
        used = [u for u in names if u not in spaces]
        plan = {}
        need = set()
        for key in keys:
            name, arity = key
            w = name[len(ns) + 1:] if name.startswith(ns + ".") else name
            segs = w.split(".")
            plan[key] = (w, segs)
            for p in types + spaces + used:
                need.update(self._paths(p, segs, attribute))
        self._fetch(need)
        out: Dict[Tuple[str, Optional[int]], str] = {}
        for key, (w, segs) in plan.items():
            name, arity = key
            fix = self._one(w, segs, arity, types, spaces, used, attribute)
            if fix is None:
                continue
            if fix == "":
                fix = w if name.startswith(ns + ".") else name
            if fix != name:
                out[key] = fix
        return out

    def _one(self, w, segs, arity, types, spaces, used, attr):
        """The settled name, "" when no declared type owns it, None to leave it alone."""
        near, outer = None, False
        for p in types:
            near = self._hit(p, segs, arity, attr)
            if near:
                break
        if not near:
            for i, p in enumerate(spaces):
                near = self._hit(p, segs, arity, attr)
                if near:
                    outer = i > 0
                    break
        if near is AMBIGUOUS:
            return None
        owners = {h for h in (self._hit(u, segs, arity, attr, True) for u in used) if h}
        if AMBIGUOUS in owners:
            return None
        if near:
            return None if owners and outer else near
        if len(owners) > 1:
            return None
        return next(iter(owners)) if owners else ""

    # ---------------------------------------------------------------- rows

    def _owner(self, row: Dict) -> Tuple[str, bool]:
        """(type owning the row's text, inside its body) -- a type row's text is its base list."""
        if "from_symbol" not in row and row.get("kind") in CLASS_KINDS:
            return row["fqn"], False
        use = "from_symbol" in row
        sym = (row.get("from_symbol") or "") if use else row["fqn"]
        if "#" in sym:
            return sym.split("#")[0], True
        if use:                         # a use from a type or from one of its fields
            self._fetch([sym])
            if self.known.get(sym):
                return sym, True
        return sym.rsplit(".", 1)[0], True

    def fix_row(self, row: Dict, fields: Sequence[str] = SIG_FIELDS) -> Dict:
        """`row` with each type-bearing field settled; the same row when nothing changes."""
        owner, inside = None, True
        new = row
        for group, exact in ((EXACT_FIELDS, True), (ERASED_FIELDS, False)):
            have = [k for k in group if row.get(k)]
            if not exact and "from_symbol" in row and row.get("kind") in USE_TARGET_KINDS and row.get("fqn"):
                have.append("fqn")
            if not have:
                continue
            texts: List[str] = []
            for k in have:
                v = row[k]
                texts.extend([v] if isinstance(v, str) else
                             [x if isinstance(x, str) else str(x.get("type") or "") for x in v if isinstance(x, (str, dict))])
            if owner is None:
                owner, inside = self._owner(row)
            fix = self.settle(texts, row["file"], owner, inside, exact=exact)
            if not fix:
                continue

            def sub(s):
                return rewrite(s, fix, exact) if isinstance(s, str) else s

            new = dict(new) if new is row else new
            for k in have:
                v = row[k]
                new[k] = sub(v) if isinstance(v, str) else [dict(x, type=sub(x["type"])) if isinstance(x, dict) and "type" in x
                                                              else sub(x) for x in v]
        return new
