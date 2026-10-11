"""Python call/reference resolution for the resolve phase.

`cdp/lang/python_flow.py` writes each Python call or reference as an expression
(`M:pkg.mod|.Class|()|.method`: start somewhere, follow steps). This walks one
against the global symbol table:

* `M:` a module; `.name` on a module finds its function, class, constant, a
  submodule, or whatever the module binds the name to (`from .x import name`,
  `name = other.thing`), following re-exports through `__init__` files;
* `D:` a symbol this file defines; `P:` `super()` inside a class;
* `()` constructs a class, or yields a function's annotated / inferred return type;
* `.name` on a class or instance finds the method or field on the class or its
  repository bases, in the order Python looks (own class first).

Whatever cannot be settled yields None and the row is dropped: no edge beats a wrong
edge. Import names written against the import root (`pkg.mod` when the file lives
at `src/pkg/mod.py`) are matched to the repository's real module path.
"""

from __future__ import annotations

import os
from typing import Dict, Iterable, Iterator, List, Optional, Sequence, Set, Tuple

from .jtypes import TypeIndex

Val = Tuple[str, str]   # (mod|cls|inst|sym|var|super, fqn)
PY_SUFFIXES = (".py", ".pyi")
MAX_DEPTH = 12


class PyIndex(TypeIndex):
    def __init__(self, extraction: Dict, symbols: Dict[str, Dict], paths: Iterable[str] = ()) -> None:
        paths = list(paths)
        self.modules: Set[str] = set()
        for info in extraction["files"].values():
            if info.get("language") == "python" and info.get("package") is not None:
                self.modules.add(info["package"])
        # an empty `__init__.py` has no facts but is still a package others import from
        self.modules.update(_module_of(p) for p in paths if p.endswith(".py"))
        self.alias = _import_aliases(self.modules, extraction["files"], paths)
        self.exports: Dict[Tuple[str, str], Optional[str]] = {}
        bases: List[Dict] = []
        for row in extraction["uses"]:
            kind = row.get("kind")
            if kind == "pybind":
                key = (row["scope_package"], row["name"])
                if key not in self.exports:
                    self.exports[key] = row["py"]
                elif self.exports[key] != row["py"]:
                    self.exports[key] = None        # bound two ways: settles nothing
            elif kind == "pyextends":
                bases.append(row)
        self._ev: Dict[str, Optional[Val]] = {}
        self._py: Dict[str, bool] = {}
        super().__init__(extraction, symbols)
        for _ in range(2):                          # a base may be reached through another class
            self._ev.clear()
            found: Dict[str, List[str]] = {}
            for row in bases:
                v = self.eval(row["py"])
                if v and v[0] == "cls" and v[1] != row["from_symbol"]:
                    out = found.setdefault(row["from_symbol"], [])
                    if v[1] not in out:
                        out.append(v[1])
            self.supers.update(found)
        self._ev.clear()
        self._decl.clear()

    # ------------------------------------------------------------ modules
    def mod_canon(self, name: str) -> Optional[str]:
        if name in self.modules:
            return name
        return self.alias.get(name)

    def is_py(self, owner: str) -> bool:
        if owner not in self._py:
            entry = self.symbols.get(owner)
            self._py[owner] = bool(entry) and str(entry["sites"][0]["file"]).endswith(PY_SUFFIXES)
        return self._py[owner]

    def hierarchy(self, owner: str) -> List[str]:
        """Python has no lexically enclosing class scope: own class, then bases depth-first."""
        if not self.is_py(owner):
            return super().hierarchy(owner)
        out: List[str] = []

        def walk(t: str) -> None:
            if t in out:
                return
            out.append(t)
            for s in self.supers.get(t, ()):
                walk(s)
        walk(owner)
        return out

    def hierarchy_one(self, owner: str) -> List[str]:
        return self.hierarchy(owner) if self.is_py(owner) else super().hierarchy_one(owner)

    # --------------------------------------------------------- evaluation
    def value_of(self, fqn: str) -> Optional[Val]:
        entry = self.symbols.get(fqn)
        if not entry:
            return None
        kind = entry["kind"]
        if kind == "class":
            return ("cls", fqn)
        if kind in ("function", "method"):
            return ("sym", fqn)
        if kind in ("field", "constant"):
            return ("var", fqn)
        return None

    def eval(self, ex: str) -> Optional[Val]:
        if ex in self._ev:
            return self._ev[ex]
        self._ev[ex] = None                         # a cycle settles nothing
        parts = ex.split("|")
        tag, _, ref = parts[0].partition(":")
        v: Optional[Val] = None
        if tag == "M":
            m = self.mod_canon(ref)
            v = ("mod", m) if m else None
        elif tag == "D":
            v = self.value_of(ref)
        elif tag == "P":
            v = ("super", ref)
        elif tag == "TUP":
            v = ("tuple", ref)
        elif tag == "LST":
            v = ("list", ref)
        for st in parts[1:]:
            if v is None:
                break
            v = self.pstep(v, st)
        self._ev[ex] = v
        return v

    def typed(self, fqn: str, key: str) -> Optional[Val]:
        entry = self.symbols.get(fqn) or {}
        ex = entry.get(key)
        return self.eval(ex) if ex else None

    def pstep(self, v: Val, st: str) -> Optional[Val]:
        kind, ref = v
        if st[0] == "[":
            if kind == "list":
                return self.eval(ref.replace("~", "|"))
            if kind == "tuple" and st != "[]":
                items = ref.split("&&")
                i = int(st[1:-1])
                return self.eval(items[i].replace("~", "|")) if i < len(items) and items[i] else None
            return None
        if st == "()":
            if kind == "cls":
                return ("inst", ref)
            if kind == "sym":
                return self.typed(ref, "ret")
            if kind == "inst":
                decl = self.declaring(ref, "__call__")
                return self.typed(decl, "ret") if decl else None
            return None
        name = st[1:]
        if kind in ("var", "sym"):                  # a typed field / property: step through its type
            inner = self.typed(ref, "ftype")
            return self.pstep(inner, st) if inner else None
        if kind == "mod":
            return self.in_module(ref, name)
        if kind in ("cls", "inst"):
            return self.member(ref, name)
        if kind == "super":
            return self.member(ref, name, skip_self=True)
        return None

    def in_module(self, mod: str, name: str) -> Optional[Val]:
        fn = mod + "#" + name
        if fn in self.symbols:
            return ("sym", fn)
        dotted = mod + "." + name
        if dotted in self.symbols:
            return self.value_of(dotted)
        ex = self.exports.get((mod, name))
        bound = self.eval(ex) if ex else None
        if bound is not None:
            return bound            # `from .render import render` shadows the submodule of that name
        sub = self.mod_canon(dotted)
        return ("mod", sub) if sub else None

    def member(self, cls: str, name: str, skip_self: bool = False) -> Optional[Val]:
        for t in self.hierarchy(cls)[1 if skip_self else 0:]:
            fn = t + "#" + name
            if fn in self.symbols:
                return ("sym", fn)
            attr = t + "." + name
            if attr in self.symbols:
                return self.value_of(attr)
        return None

    # ------------------------------------------------------------ targets
    def targets(self, row: Dict) -> List[Tuple[str, str]]:
        """`(fqn, kind)` for each repository symbol a `py` row denotes."""
        v = self.eval(row["py"])
        if v is None:
            return []
        kind, ref = v
        out: List[Tuple[str, str]] = []
        if row["kind"] == "call":
            if kind == "var":                       # `self.factory(...)` where `factory = SomeClass`
                inner = self.typed(ref, "ftype")
                if inner is not None and inner[0] in ("cls", "sym"):
                    kind, ref = inner
            if kind == "sym":
                out.append((ref, "call"))
            elif kind == "cls":
                init = self.declaring(ref, "__init__")
                out.append((init or ref, "call"))
                if init:
                    out.append((ref, "ref"))
            elif kind == "inst":
                decl = self.declaring(ref, "__call__")
                if decl:
                    out.append((decl, "call"))
            return out
        if kind in ("sym", "cls", "var"):
            out.append((ref, "extends" if row["kind"] == "pyextends" else row["kind"]))
        return out

    def expand(self, rows: Sequence[Dict]) -> Iterator[Dict]:
        """`uses[]` with Python rows replaced by one resolved row per target."""
        for row in rows:
            if "py" not in row:
                yield row
            elif row["kind"] != "pybind":
                for fqn, kind in self.targets(row):
                    r = dict(row)
                    r["fqn"], r["kind"], r["pyres"] = fqn, kind, True
                    yield r


def _module_of(path: str) -> str:
    stem = path[: -len(".py")]
    return (stem[: -len("/__init__")] if stem.endswith("/__init__") else stem).replace("/", ".")


def _import_aliases(modules: Set[str], files: Dict[str, Dict], paths: Iterable[str]) -> Dict[str, str]:
    """`import root` module names -> real (path-based) module names, where they differ:
    `src/pkg/mod.py` is imported as `pkg.mod`; `tests/helpers.py` (not in a package) as
    `helpers`. An alias two modules claim is dropped."""
    py = [p for p in paths if p.endswith(".py")]
    inits = {os.path.dirname(p) for p in py if os.path.basename(p) == "__init__.py"}
    claims: Dict[str, Set[str]] = {}
    for p in py:
        real = _module_of(p)
        d = os.path.dirname(p)
        top = None
        while d and d in inits:
            top = d
            d = os.path.dirname(d)
        base = os.path.basename(p)[:-3]
        if top is None:
            alias = base
        else:
            alias = _module_of(p[len(os.path.dirname(top)) + 1:] if os.path.dirname(top) else p)
        if alias != real and real in modules:
            claims.setdefault(alias, set()).add(real)
    return {a: next(iter(r)) for a, r in claims.items() if len(r) == 1 and a not in modules}
