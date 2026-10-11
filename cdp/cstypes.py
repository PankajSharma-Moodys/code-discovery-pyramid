"""C# type walking for the resolve phase: `jtypes.TypeIndex` with C# name and member rules.

* `using` namespaces and the enclosing namespaces of a file complete a name the extractor could
  only guess into the file's own namespace;
* a chain walks declared member types, the BCL model (`Task<T>`, `List<T>`, LINQ, `IOptions<T>`)
  and nested types (`Outer.Inner`), and binds a generic method's explicit type arguments;
* an extension method is the target when the receiver's class declares no such member and an
  `ext` parameter type of the repository matches the receiver (`ext` is recorded on the define).
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

from .jtypes import TypeIndex
from .lang.csharp_types import ENUMERABLE, MAPS, bcl_step, is_bcl
from .lang.java_types import split_type

OBJECT_METHODS = frozenset(["ToString", "Equals", "GetHashCode", "GetType", "MemberwiseClone", "Finalize"])
SEQUENCES = ENUMERABLE | MAPS


def _simple(t: str) -> str:
    return split_type(t)[0].rsplit(".", 1)[-1]


class CsTypeIndex(TypeIndex):
    def _wildcards(self, extraction: Dict) -> None:
        for f, info in extraction.get("files", {}).items():
            pkg = info.get("package")
            if f.endswith(".cs") and pkg:
                parts = pkg.split(".")
                self.wild[f] = [".".join(parts[:i]) for i in range(len(parts), 0, -1)]
        for row in extraction["imports"]:
            if row["file"].endswith(".cs") and row["fqn"] not in self.wild.get(row["file"], ()):
                self.wild.setdefault(row["file"], []).append(row["fqn"])
        # extension methods (the `this` parameter type of every overload) and every return type
        # an overloaded method declares: overloads that differ only in type arguments still agree
        # on the class a chain continues from
        self.exts: Dict[str, List[Tuple[str, List[str]]]] = {}
        self.rets: Dict[str, set] = {}
        ext_of: Dict[str, List[str]] = {}
        for row in extraction["defines"]:
            if row["kind"] != "method" or not row["file"].endswith(".cs"):
                continue
            if row.get("ext"):
                ext_of.setdefault(row["fqn"], [])
                if row["ext"] not in ext_of[row["fqn"]]:
                    ext_of[row["fqn"]].append(row["ext"])
            self.rets.setdefault(row["fqn"], set()).add(row.get("ret") or "")
        for fqn, types in ext_of.items():
            self.exts.setdefault(fqn.rsplit("#", 1)[1], []).append((fqn, types))

    def class_for(self, name: str, alts, file: str) -> Optional[str]:
        got = super().class_for(name, alts, file)
        if got or "." not in name:
            return got
        base = split_type(name)[0]
        for prefix in self.wild.get(file, ()):      # `Controllers.v3.Foo`: relative to a namespace
            if self.is_class(prefix + "." + base):
                return prefix + "." + base
        return None

    # -------------------------------------------------------------- types

    def _nested(self, cls: str, name: str) -> Optional[str]:
        for t in self.hierarchy(cls):
            if self.is_class(t + "." + name):
                return t + "." + name
        return None

    def step(self, type_str: str, step: str) -> Optional[str]:
        base, args, arrays = split_type(type_str)
        if not base or base.startswith("~"):
            return None
        if not self.is_class(base):
            return bcl_step(type_str, step) if (arrays or is_bcl(base)) else None
        if step.startswith("f:"):
            return self.field_type(base, step[2:]) or self._nested(base, step[2:])
        if not step.startswith("m:"):
            return None
        name, _, targs = step[2:].partition("<")
        decl = self.declaring(base, name)
        entry = self.symbols.get(decl) if decl else None
        ret = entry.get("ret") if entry else None
        if entry and not ret:
            rets = self.rets.get(decl, set())
            bases = {split_type(r)[0] for r in rets}
            if len(rets) > 1 and len(bases) == 1 and "" not in bases and not next(iter(bases)).startswith("~"):
                ret = next(iter(bases))             # overloads agree on the class, not on its arguments
        if not ret:
            return None
        ret = self.canon(ret, entry["sites"][0]["file"])
        if "~" in ret:
            if targs:
                mine = split_type("X<" + targs)[1] if targs.endswith(">") else []
                for tp, arg in zip(entry.get("tparams") or [], mine):
                    ret = re.sub(r"~" + re.escape(tp) + r"(?![\w$])", arg, ret)
            owner = decl.split("#", 1)[0]
            tparams = (self.symbols.get(owner) or {}).get("tparams") or []
            if owner == base and args and len(args) == len(tparams):
                for tp, arg in zip(tparams, args):
                    ret = re.sub(r"~" + re.escape(tp) + r"(?![\w$])", arg, ret)
            if ret.startswith("~"):
                return None
            ret = re.sub(r"~[\w$]+", "?", ret)
        return ret

    def settle(self, name: str, file: str) -> str:
        """`Ns.Type.Prop.Inner` -> the type the dotted path denotes (a class, then member steps)."""
        base = split_type(name)[0]
        if self.class_for(base, (), file):
            return self.canon(name, file)
        parts = base.split(".")
        for cut in range(len(parts) - 1, 0, -1):
            cls = self.class_for(".".join(parts[:cut]), (), file)
            if cls:
                t = self.walk(cls, ["f:" + p for p in parts[cut:]])
                return t or name
        return name

    # -------------------------------------------------------------- calls

    def _ext_target(self, name: str, recv: str, cls: Optional[str], file: str) -> Optional[str]:
        found = set()
        rs = _simple(recv)
        chain = set(self.hierarchy(cls)) if cls else set()
        for fqn, types in self.exts.get(name, ()):
            for et in types:
                eb = split_type(et)[0]
                es = eb.rsplit(".", 1)[-1]
                if eb.startswith("~") or es in ("Object", "object"):
                    ok = True
                elif cls:
                    ok = (self.class_for(eb, (), file) or self.class_for(eb, (), self._file_of(fqn))) in chain
                else:
                    ok = es == rs or (es in ("IEnumerable", "IQueryable") and rs in SEQUENCES)
                if ok:
                    found.add(fqn)
        return found.pop() if len(found) == 1 else None

    def _file_of(self, fqn: str) -> str:
        return self.symbols[fqn]["sites"][0]["file"]

    def call_target(self, row: Dict) -> Optional[str]:
        file = row["file"]
        owner_guess, _, name = row["fqn"].partition("#")
        recvs: List[str] = []
        if row.get("chain"):
            t = self.walk(self.settle(row.get("recv") or owner_guess, file), row["chain"])
            if not t:
                return None
            recvs = [t]
        elif row.get("ext"):
            recvs = [owner_guess]
        else:
            recvs = [owner_guess] + [a.split("#", 1)[0] for a in row.get("alts") or ()]
        for guess in recvs:
            t = self.settle(guess, file)
            cls = self.class_for(t, (), file)
            if cls is None:
                if name != "<init>" and not self.is_class(split_type(t)[0]):
                    hit = self._ext_target(name, t, None, file)
                    if hit:
                        return hit
                continue
            if name == "<init>":
                return cls + "#<init>" if cls + "#<init>" in self.symbols else cls
            decl = self.declaring(cls, name)
            if decl:
                return decl
            if name not in OBJECT_METHODS:
                hit = self._ext_target(name, t, cls, file)
                if hit:
                    return hit
        return None
