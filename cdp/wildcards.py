"""`wildcard:<module-or-package>` file signals: a name the file uses was left unsettled because of a
wildcard import that could have supplied it. Computed after resolve has the symbol table, written into
the extraction's per-file `signals` (a list of strings: no store schema), recomputed on every scan.

Python: a name no scope binds and no builtin is, whose `from X import *` sources include an outside
module, a non-literal `__all__`, or two suppliers (`PyIndex.star_blockers`). Java: a member row whose
type no wildcard import of the repository's own packages (JDK and libraries excluded) could be confirmed
against (`alts` unmatched). C# is not covered."""

from __future__ import annotations

import builtins
from typing import Dict, List, Sequence, Set

from .lang.base import is_third_party
from .pytypes import PyIndex

PREFIX = "wildcard:"
CAP = 5
_BUILTINS = frozenset(dir(builtins))


def add_wildcard_signals(extraction: Dict, symbols: Dict[str, Dict], paths: Sequence[str] = ()) -> None:
    found: Dict[str, Set[str]] = {}
    uses = extraction["uses"]
    if any(r.get("kind") == "pystar" for r in uses):
        idx = PyIndex(extraction, symbols, paths)
        cache: Dict = {}
        for r in uses:
            py = r.get("py", "")
            if not py.startswith("S:") or "|." not in py:
                continue
            mod, _, rest = py[2:].partition("|")
            name = rest[1:].split(".", 1)[0]
            if name in _BUILTINS:
                continue
            if (mod, name) not in cache:
                cache[(mod, name)] = idx.star_blockers(mod, name)
            if cache[(mod, name)]:
                found.setdefault(r["file"], set()).update(cache[(mod, name)])
    stars: Dict[str, List[str]] = {}
    for r in uses:
        if r.get("alts") and r.get("file", "").endswith(".java") and r.get("kind"):
            cands = [r["fqn"], *r["alts"]]
            if any((symbols.get(c) or symbols.get(c.split("#", 1)[0])) for c in cands):
                continue
            rel = r["file"]
            if rel not in stars:
                stars[rel] = [i["fqn"][:-2] for i in extraction.get("imports") or ()
                              if i.get("file") == rel and i["fqn"].endswith(".*") and not is_third_party(i["fqn"])]
            for alt in r["alts"]:
                for w in stars[rel]:
                    if alt.startswith(w + "."):
                        found.setdefault(rel, set()).add(w)
    for rel, info in extraction["files"].items():
        sig = [s for s in info.get("signals") or () if not s.startswith(PREFIX)]
        sig += [PREFIX + w for w in sorted(found.get(rel, ()))[:CAP]]
        if sig != list(info.get("signals") or ()):
            info["signals"] = sorted(set(sig))
