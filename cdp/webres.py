"""Bind a JS/TS/Vue use row (`webmod`, `webexp`, `webname`) to the symbol it names.

The extractor sees one file, so it can only write the module as the file wrote it (`src/util/jp`
for `./jp`, `@/util/jp` for an alias). Here the repo's file list is in view: a module is a file
stem (extension and `/index` dropped), an alias resolves by the longest matching path suffix (the
candidate nearest the importing file wins a tie), and a re-export (`export {a} from`, `export *
from`) is followed to the file that declares the name. Language-agnostic data in, fqn out.
"""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Sequence, Tuple

WEB_EXTS = (".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".mts", ".cts", ".vue")
_CLASSY = ("class", "interface", "enum", "record", "annotation", "type")
_ALIASES = ("@/", "~/", "#/")


def is_web(path: str) -> bool:
    return path.endswith(WEB_EXTS)


def _stem(path: str) -> str:
    for ext in WEB_EXTS:
        if path.endswith(ext):
            return path[: -len(ext)]
    return path


class WebIndex:
    def __init__(self, paths: Iterable[str], symbols: Dict[str, Dict], reexports: Sequence[Dict]) -> None:
        self.symbols = symbols
        stems: Dict[str, str] = {}
        for p in sorted(paths):
            if is_web(p) and not p.endswith(".d.ts"):
                stems.setdefault(_stem(p), p)
        self.stems = stems
        self._suffix: Dict[str, List[str]] = {}
        self._canon: Dict[Tuple[str, str], Optional[str]] = {}
        self.exports: Dict[Tuple[str, str], Tuple[str, str]] = {}    # (module, name) -> (module, name) it re-exports
        self.stars: Dict[str, List[str]] = {}
        self._tops: Optional[Dict[str, Dict[str, List[str]]]] = None
        for row in reexports:
            here = _stem(row["file"])
            target = self.canon(row["webmod"], row["file"])
            if target is None:
                continue
            if row["webexp"] == "*" and row["reexport_as"] == "*":
                self.stars.setdefault(here, []).append(target)
            elif row["webexp"] != "*":
                self.exports[(here, row["reexport_as"])] = (target, row["webexp"])

    # ------------------------------------------------------------ modules
    def canon(self, mod: str, from_file: str) -> Optional[str]:
        key = (mod, from_file)
        if key not in self._canon:
            self._canon[key] = self._canon_of(mod, from_file)
        return self._canon[key]

    def _canon_of(self, mod: str, from_file: str) -> Optional[str]:
        for cand in (mod, _stem(mod)):
            if cand in self.stems:
                return cand
            if cand + "/index" in self.stems:
                return cand + "/index"
        if not mod.startswith(_ALIASES):
            return None
        tail = _stem(mod[2:])
        if not self._suffix:
            for s in self.stems:
                parts = s.split("/")
                for i in range(len(parts)):
                    self._suffix.setdefault("/".join(parts[i:]), []).append(s)
        found = self._suffix.get(tail) or self._suffix.get(tail + "/index") or []
        if len(found) > 1:
            here = from_file.split("/")

            def shared(s: str) -> int:
                n = 0
                for a, b in zip(here, s.split("/")):
                    if a != b:
                        break
                    n += 1
                return n
            best = max(shared(s) for s in found)
            found = [s for s in found if shared(s) == best]
        return found[0] if len(found) == 1 else None

    # ------------------------------------------------------------ names
    def _tops_of(self, mod: str) -> Dict[str, List[str]]:
        if self._tops is None:
            tops: Dict[str, Dict[str, List[str]]] = {}
            for fqn, entry in self.symbols.items():
                if "#" in fqn:
                    head, _, name = fqn.partition("#")
                    if head in self.stems and "." not in name and entry["kind"] in ("function", "method"):
                        tops.setdefault(head, {"class": [], "function": []})["function"].append(name)
                else:
                    head, _, name = fqn.rpartition(".")
                    if head in self.stems and entry["kind"] in _CLASSY:
                        tops.setdefault(head, {"class": [], "function": []})["class"].append(name)
            self._tops = tops
        return self._tops.get(mod, {"class": [], "function": []})

    def _find(self, mod: str, name: str, depth: int = 0) -> Optional[Tuple[str, str]]:
        """The (module, name) declaring `name` as seen from `mod`, through re-exports."""
        if mod + "#" + name in self.symbols or mod + "." + name in self.symbols:
            return mod, name
        if depth > 6:
            return None
        hop = self.exports.get((mod, name))
        if hop:
            return self._find(hop[0], hop[1], depth + 1)
        for star in self.stars.get(mod, ()):
            got = self._find(star, name, depth + 1)
            if got:
                return got
        return None

    def _default(self, mod: str, local: str) -> Optional[str]:
        """The name a default import binds: the local name when the module declares it, else the
        module's one class (or, with no class, its one function)."""
        if self._find(mod, local):
            return local
        tops = self._tops_of(mod)
        if len(tops["class"]) == 1:
            return tops["class"][0]
        if not tops["class"] and len(tops["function"]) == 1:
            return tops["function"][0]
        return None

    def target(self, row: Dict) -> Optional[str]:
        """The declared fqn this row names, or None."""
        mod = self.canon(row["webmod"], row["file"])
        if mod is None:
            return None
        exp, member, local = row["webexp"], row.get("webname"), row.get("weblocal") or ""
        if exp == "*":                                      # `ns.f(`
            return self._pick(self._find(mod, member) if member else None, None)
        name = self._default(mod, local) if exp == "default" else exp
        return self._pick(self._find(mod, name) if name else None, member)

    def _pick(self, got: Optional[Tuple[str, str]], member: Optional[str]) -> Optional[str]:
        if got is None:
            return None
        mod, name = got
        cls, fn = mod + "." + name, mod + "#" + name
        order = [cls + "#" + member, cls, fn] if member else [cls, fn]
        if member and cls not in self.symbols and fn in self.symbols:
            order = [fn]                                    # `obj.f(` on an exported object: the object is the symbol
        for cand in order:
            if cand in self.symbols:
                return cand
        return None
