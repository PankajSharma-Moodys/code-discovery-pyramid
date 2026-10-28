"""`wildcard:<module-or-package>` file signals: a name the file uses was left unsettled because of a
wildcard import that could have supplied it. Computed after resolve has the symbol table, written into
the extraction's per-file `signals` (a list of strings: no store schema), recomputed on every scan.

Python: a name no scope binds and no builtin is, whose `from X import *` sources include an outside
module, a non-literal `__all__`, or two suppliers (`PyIndex.star_blockers`). Java: a member row whose
type no wildcard import of the repository's own packages (JDK and libraries excluded) could be confirmed
against (`alts` unmatched). C#: a `guess:` type name no declared type owns (own and enclosing namespaces,
`using`/`global using` namespaces, nested types) whose file `using`s a namespace the repository does not
declare and `THIRD_PARTY_PREFIXES` does not list, unless the name is also unsettled in files with no such
namespace (then it is a framework/library type, e.g. `Assert`, `IDisposable`): see `_csharp_unsettled`."""

from __future__ import annotations

import builtins
from typing import Dict, List, Sequence, Set, Tuple

from .lang.base import is_third_party
from .pytypes import PyIndex

PREFIX = "wildcard:"
GUESS = "guess:"
_CLASS = frozenset(["class", "interface", "enum", "record", "annotation", "struct", "delegate"])
CAP = 5
_BUILTINS = frozenset(dir(builtins))


def _csharp_unsettled(extraction: Dict, symbols: Dict[str, Dict]) -> Dict[str, Set[str]]:
    from .lang.csharp_scope import global_usings, import_names
    classes = {k for k, v in symbols.items() if v.get("kind") in _CLASS}
    nested = {k.rsplit(".", 1)[-1] for k in classes if k.rsplit(".", 1)[0] in classes}
    repo_ns = {n for n in (i.get("package") for i in extraction["files"].values()) if n}
    repo_ns |= {n.rsplit(".", 1)[0] for n in list(repo_ns) if "." in n}      # parents of a declared namespace
    rows: Dict[str, List[Dict]] = {}
    for r in extraction["imports"]:
        if r["file"].endswith(".cs"):
            rows.setdefault(r["file"], []).append(r)
    glob = global_usings(r for rs in rows.values() for r in rs)
    module = {r["file"]: r["module"] for r in extraction["defines"] if r["file"].endswith(".cs")}
    per: Dict[str, Tuple[List[str], List[str]]] = {}
    for rel, info in extraction["files"].items():
        if not rel.endswith(".cs"):
            continue
        pkg = info.get("package") or ""
        parts = pkg.split(".") if pkg else []
        enc = [".".join(parts[:i]) for i in range(len(parts), 0, -1)] + [""]
        uses = import_names(rows.get(rel, ())) + glob.get(module.get(rel, ""), [])
        unknown = [u for u in dict.fromkeys(uses) if u not in repo_ns and u != "System" and not is_third_party(u + ".")]
        names = []
        for g in info.get("signals") or ():
            n = g[len(GUESS):] if g.startswith(GUESS) else ""
            r = n[len(pkg) + 1:] if pkg and n.startswith(pkg + ".") else ""
            if not r or r.split(".")[0] in nested or any(
                    (b + "." + r if b else r) + a in classes for b in enc + uses for a in ("", "Attribute")):
                continue
            names.append(r)
        per[rel] = (names, unknown)
    # a name unsettled where no unknown namespace could supply it is a framework/library type
    known = {n for names, unknown in per.values() if not unknown for n in names}
    return {rel: set(unknown) for rel, (names, unknown) in per.items() if unknown and any(n not in known for n in names)}


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
    if any(f.endswith(".cs") for f in extraction["files"]):
        for rel, nss in _csharp_unsettled(extraction, symbols).items():
            found.setdefault(rel, set()).update(nss)
    for rel, info in extraction["files"].items():
        sig = [s for s in info.get("signals") or () if not s.startswith(PREFIX)]
        sig += [PREFIX + w for w in sorted(found.get(rel, ()))[:CAP]]
        if sig != list(info.get("signals") or ()):
            info["signals"] = sorted(set(sig))
