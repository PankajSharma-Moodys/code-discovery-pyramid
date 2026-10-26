"""Settles the base-type names the C# extractor guessed into a file's own namespace.

`Resolver.resolve` (one file, no symbol table) qualifies a simple name it cannot place, and a dotted
name whose head it does not know, into the file's own namespace (`Ns.Base`, `Ns.System.Attribute`).
That is right for a type of the same namespace and a phantom for a type a `using` brings in, one of an
enclosing namespace, or one outside the repository. With the declared classes in view a guessed name
settles in C#'s order: the declared type of the enclosing types, then of the file's namespace, then of
each enclosing namespace (innermost first); else the one declared type a `using` namespace owns (a
dotted name is only looked up relative to an enclosing scope: a `using` does not import namespaces);
else, as `jtypes.SigScope` does for Java, the name as written (a framework or third-party type).
Several `using` namespaces owning one name stay as guessed. Only names the extractor guessed (a
`guess:` file signal) are settled; a name the source wrote qualified (`global::`, alias) is kept.

`scope_of(file) -> (namespace, using namespaces, guessed names)`; `probe(fqns) -> the declared classes
among them` (a set lookup at scan time, an indexed query in the store).
"""

from __future__ import annotations

import re
from typing import Dict, List, Sequence

NAME_RE = re.compile(r"[A-Za-z_$][\w$.]*")


class CsSigScope:
    def __init__(self, scope_of, probe) -> None:
        self.scope_of = scope_of
        self.probe = probe
        self.known: Dict[str, bool] = {}

    def _scopes(self, ns: str, owner: str) -> List[str]:
        """Enclosing types of `owner` (innermost first), then `ns` and its parents."""
        out: List[str] = []
        if owner.startswith(ns + "."):
            segs = owner[len(ns) + 1:].split(".")
            out = [ns + "." + ".".join(segs[:i]) for i in range(len(segs) - 1, 0, -1)]
        parts = ns.split(".")
        return out + [".".join(parts[:i]) for i in range(len(parts), 0, -1)]

    def settle(self, texts: Sequence[str], file: str, owner: str) -> Dict[str, str]:
        """`name -> settled name` for each guessed name in `texts` (`owner` = the declaring type)."""
        ns, usings, guessed = self.scope_of(file)
        if not ns or not guessed:
            return {}
        names = {n for t in texts for n in NAME_RE.findall(t) if n in guessed and n.startswith(ns + ".")}
        if not names:
            return {}
        scopes = self._scopes(ns, owner)
        cands: Dict[str, List[str]] = {}
        for n in names:
            w = n[len(ns) + 1:]
            cands[n] = [s + "." + w for s in scopes] + ([] if "." in w else [u + "." + w for u in dict.fromkeys(usings) if u not in scopes])
        need = {c for cs in cands.values() for c in cs if c not in self.known}
        if need:
            hit = set(self.probe(need))
            for c in need:
                self.known[c] = c in hit
        out = {}
        for n, cs in cands.items():
            w = n[len(ns) + 1:]
            k = len(scopes)
            near = [c for c in cs[:k] if self.known[c]]
            if near:
                out[n] = near[0]
                continue
            owners = [c for c in cs[k:] if self.known[c]]
            if len(owners) == 1:
                out[n] = owners[0]
            elif not owners:
                out[n] = w
        return {n: v for n, v in out.items() if v != n}

    def fix_row(self, row: Dict) -> Dict:
        """`row` with its `supertypes` settled; the same row when nothing changes."""
        sup = row.get("supertypes")
        if not sup:
            return row
        fix = self.settle(sup, row["file"], row["fqn"])
        if not fix:
            return row
        return dict(row, supertypes=[NAME_RE.sub(lambda m: fix.get(m.group(0), m.group(0)), s) for s in sup])
