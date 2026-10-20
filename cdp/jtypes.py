"""Java type walking for the resolve phase.

The extractor sees one file, so a call like `order.getCustomer().getName()` or
`child.inheritedMethod()` reaches here half-resolved: a receiver type, a chain of
steps, a name. This settles them against the global symbol table:

* inherited methods resolve to the class that declares them (superclass chain,
  interfaces, then lexically enclosing classes);
* a chain (`m:getCustomer`, `f:address`, `e` element, ...) is walked through each
  declared return or field type, with the JDK collection model for `List<X>`,
  `Optional<X>`, `Map<K,V>` and `Stream<X>`;
* anything it cannot settle yields None: no edge, never a wrong one.
"""

from __future__ import annotations

import re
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from .lang.java_types import is_jdk, jdk_step, split_type

GUESS_PREFIX = "guess:"   # file signal set by lang/java.py: a name qualified by guess
CLASS_KINDS = frozenset(["class", "interface", "enum", "record", "annotation"])
NAME_RE = re.compile(r"[A-Za-z_$][\w$.]*")
OBJECT_METHODS = frozenset(["toString", "equals", "hashCode", "getClass", "notify", "notifyAll",
                            "wait", "clone", "finalize"])


class TypeIndex:
    def __init__(self, extraction: Dict, symbols: Dict[str, Dict]) -> None:
        self.symbols = symbols
        self.wild: Dict[str, List[str]] = {}
        self.pkg_of = {f: info.get("package") for f, info in extraction.get("files", {}).items()}
        self._wildcards(extraction)
        self.supers: Dict[str, List[str]] = {}
        self._decl: Dict[Tuple[str, str], Optional[str]] = {}
        for row in extraction["uses"]:
            if row.get("kind") not in ("extends", "implements") or not row.get("from_symbol"):
                continue
            target = self.class_for(row["fqn"], row.get("alts") or (), row["file"])
            if target and target != row["from_symbol"]:
                self.supers.setdefault(row["from_symbol"], []).append(target)

    def _wildcards(self, extraction: Dict) -> None:
        for row in extraction["imports"]:
            if row["fqn"].endswith(".*"):
                self.wild.setdefault(row["file"], []).append(row["fqn"][:-2])

    # ------------------------------------------------------------- names

    def is_class(self, fqn: str) -> bool:
        entry = self.symbols.get(fqn)
        return bool(entry) and entry["kind"] in CLASS_KINDS

    def class_for(self, name: str, alts: Iterable[str], file: str) -> Optional[str]:
        """The repository class a (possibly guessed) type name denotes."""
        name = split_type(name)[0]
        if self.is_class(name):
            return name
        for alt in alts:
            alt = alt.split("#", 1)[0]
            if self.is_class(alt):
                return alt
        # A name the extractor could not settle was guessed into the file's own package;
        # below that package is what a wildcard import would complete. A qualified name
        # is settled by its full path, never by its last segment.
        pkg = self.pkg_of.get(file)
        rel = name[len(pkg) + 1:] if pkg and name.startswith(pkg + ".") else name
        if "." in rel and rel == name:
            return None
        for prefix in self.wild.get(file, ()):
            cand = prefix + "." + rel
            if self.is_class(cand):
                return cand
        return None

    def canon(self, type_str: str, file: str) -> str:
        """Replace each name in a type string by the repository class it denotes."""
        def fix(m: "re.Match[str]") -> str:
            name = m.group(0)
            return self.class_for(name, (), file) or name
        return NAME_RE.sub(fix, type_str)

    # ------------------------------------------------------------ members

    def hierarchy(self, owner: str) -> List[str]:
        """`owner`, its supertypes breadth-first, then each lexically enclosing
        class with its own supertypes."""
        out: List[str] = []
        seen = set()
        level = [owner]
        while level:
            nxt: List[str] = []
            for t in level:
                if t in seen:
                    continue
                seen.add(t)
                out.append(t)
                nxt.extend(self.supers.get(t, ()))
            level = nxt
        outer = owner.rsplit(".", 1)[0] if "." in owner else ""
        while outer and self.is_class(outer):
            for t in self.hierarchy_one(outer):
                if t not in seen:
                    seen.add(t)
                    out.append(t)
            outer = outer.rsplit(".", 1)[0] if "." in outer else ""
        return out

    def hierarchy_one(self, owner: str) -> List[str]:
        out, seen, level = [], set(), [owner]
        while level:
            nxt: List[str] = []
            for t in level:
                if t not in seen:
                    seen.add(t)
                    out.append(t)
                    nxt.extend(self.supers.get(t, ()))
            level = nxt
        return out

    def declaring(self, owner: str, name: str) -> Optional[str]:
        """`Declaring#name` for a method `owner` has, declares or inherits."""
        key = (owner, name)
        if key not in self._decl:
            found = None
            for t in ([owner] if name == "<init>" else self.hierarchy(owner)):
                if (t + "#" + name) in self.symbols:
                    found = t + "#" + name
                    break
            self._decl[key] = found
        return self._decl[key]

    def field_type(self, owner: str, name: str) -> Optional[str]:
        for t in self.hierarchy(owner):
            entry = self.symbols.get(t + "." + name)
            if entry and entry["kind"] in ("field", "constant"):
                ft = entry.get("ftype")
                if ft:
                    return self.canon(ft, entry["sites"][0]["file"])
                return None
        return None

    # -------------------------------------------------------------- types

    def step(self, type_str: str, step: str) -> Optional[str]:
        base, args, _ = split_type(type_str)
        if not base or base.startswith("~"):
            return None
        cls = base if self.is_class(base) else None
        if cls is None:
            return jdk_step(type_str, step) if is_jdk(base) else None
        if step.startswith("f:"):
            return self.field_type(cls, step[2:])
        if not step.startswith("m:"):
            return None
        decl = self.declaring(cls, step[2:])
        entry = self.symbols.get(decl) if decl else None
        ret = entry.get("ret") if entry else None
        if not ret:
            return None
        ret = self.canon(ret, entry["sites"][0]["file"])
        if "~" in ret:
            owner = decl.split("#", 1)[0]
            tparams = (self.symbols.get(owner) or {}).get("tparams") or []
            if owner == cls and args and len(args) == len(tparams):
                for tp, arg in zip(tparams, args):
                    ret = re.sub(r"~" + re.escape(tp) + r"(?![\w$])", arg, ret)
            if ret.startswith("~"):
                return None
            ret = re.sub(r"~[\w$]+", "?", ret)  # an argument nobody can name stays unknown
        return ret

    def walk(self, base: str, steps: Sequence[str]) -> Optional[str]:
        cur: Optional[str] = base
        for st in steps:
            if cur is None:
                return None
            cur = self.step(cur, st)
        return cur

    # -------------------------------------------------------------- calls

    def call_target(self, row: Dict) -> Optional[str]:
        """The `Owner#method` a call row denotes, or None to drop it."""
        file = row["file"]
        owner_guess, _, name = row["fqn"].partition("#")
        strict = bool(row.get("strict"))
        cands: List[str] = []
        if row.get("chain"):
            t = self.walk(self.canon(row.get("recv") or owner_guess, file), row["chain"])
            if not t:
                return None
            cands = [split_type(t)[0]]
        else:
            cands = [owner_guess] + [a.split("#", 1)[0] for a in row.get("alts") or ()]
        fallback: Optional[str] = None
        for guess in cands:
            cls = self.class_for(guess, (), file)
            if cls is None:
                continue
            if name == "<init>":
                # No explicit constructor: javac's implicit default one, i.e. the class.
                return cls + "#<init>" if cls + "#<init>" in self.symbols else cls
            decl = self.declaring(cls, name)
            if decl:
                return decl
            if fallback is None and not strict and name not in OBJECT_METHODS:
                fallback = cls + "#" + name
        return fallback


# ------------------------------------------------------------ signature scope


class SigScope:
    """Settles the type names an extractor guessed into a file's own package.

    `_Resolver.resolve` (one file, no symbol table) names an unimported simple type
    `<package>.<Name>`; that is right for a same-package class and a phantom for a type a
    wildcard import brings in or one outside the repository. Here, with the declared classes
    in view, a name under the file's package settles in Java's order: the declared
    same-package class; else the one declared class a wildcard import owns; else (a JDK or
    third-party type) the bare name. A name several wildcards could own stays as it was.

    Only names the extractor guessed (a `guess:` file signal) are settled; a qualified name
    the source wrote is kept as written.

    `scope_of(file) -> (package, wildcard packages, guessed names)`; `probe(fqns) -> the declared classes
    among them` (a set lookup at scan time, an indexed query in the store).
    """

    def __init__(self, scope_of, probe) -> None:
        self.scope_of = scope_of
        self.probe = probe
        self.known: Dict[str, bool] = {}

    def _names(self, texts: Iterable[str], pkg: str, wilds: Sequence[str], guessed) -> Dict[str, List[str]]:
        found: Dict[str, List[str]] = {}
        for t in texts:
            for n in NAME_RE.findall(t):
                if n in guessed and n.startswith(pkg + "."):
                    found[n] = [n] + [w + "." + n[len(pkg) + 1:] for w in wilds]
        return found

    def settle(self, texts: Sequence[str], file: str) -> Dict[str, str]:
        """`name -> settled name` for each guessed name in `texts`."""
        pkg, wilds, guessed = self.scope_of(file)
        if not pkg or not guessed:
            return {}
        names = self._names(texts, pkg, wilds, guessed)
        need = {c for cands in names.values() for c in cands if c not in self.known}
        if need:
            hit = set(self.probe(need))
            for c in need:
                self.known[c] = c in hit
        out = {}
        for n, cands in names.items():
            if self.known[n]:
                continue
            owners = [c for c in cands[1:] if self.known[c]]
            if len(owners) == 1:
                out[n] = owners[0]
            elif not owners:
                out[n] = n[len(pkg) + 1:]
        return out

    def fix_row(self, row: Dict, fields: Sequence[str]) -> Dict:
        """`row` with each type-bearing field (`sig`, `ret`, `ftype`, `from_sig`, `argt` and the
        `type` of each of `params`) settled; the same row when nothing changes."""
        texts: List[str] = []
        for key in fields:
            v = row.get(key)
            if isinstance(v, str):
                texts.append(v)
            elif isinstance(v, list):
                texts.extend(x if isinstance(x, str) else (x.get("type") or "") if isinstance(x, dict) else ""
                             for x in v)
        if not texts:
            return row
        fix = self.settle(texts, row["file"])
        if not fix:
            return row

        def sub(s):
            return NAME_RE.sub(lambda m: fix.get(m.group(0), m.group(0)), s) if isinstance(s, str) else s

        new = dict(row)
        for key in fields:
            v = row.get(key)
            if isinstance(v, str):
                new[key] = sub(v)
            elif isinstance(v, list):
                new[key] = [dict(x, type=sub(x["type"])) if isinstance(x, dict) and "type" in x else sub(x) for x in v]
        return new


DEFINE_TYPE_FIELDS = ("sig", "ret", "ftype", "params")
USE_TYPE_FIELDS = ("from_sig", "argt")


def sig_scope_from_extraction(extraction: Dict) -> Optional[SigScope]:
    """A `SigScope` over a whole extraction (None when it holds no Java)."""
    if not any(f.endswith(".java") for f in extraction.get("files", {})):
        return None
    wild: Dict[str, List[str]] = {}
    for row in extraction["imports"]:
        if row["fqn"].endswith(".*"):
            wild.setdefault(row["file"], []).append(row["fqn"][:-2])
    pkgs = {f: info.get("package") or "" for f, info in extraction["files"].items()}
    guess = {f: frozenset(g[len(GUESS_PREFIX):] for g in info.get("signals") or () if g.startswith(GUESS_PREFIX))
             for f, info in extraction["files"].items()}
    classes = {r["fqn"] for r in extraction["defines"] if r.get("kind") in CLASS_KINDS}
    return SigScope(lambda f: (pkgs.get(f, ""), wild.get(f, ()), guess.get(f, frozenset())), lambda cands: classes.intersection(cands))


def settle_extraction(extraction: Dict) -> Dict:
    """`extraction` with Java signature type names settled (rows copied, never mutated)."""
    scope = sig_scope_from_extraction(extraction)
    if scope is None:
        return extraction
    defines = [scope.fix_row(r, DEFINE_TYPE_FIELDS) if r["file"].endswith(".java") else r
               for r in extraction["defines"]]
    uses = [scope.fix_row(r, USE_TYPE_FIELDS) if r["file"].endswith(".java") and (r.get("from_sig") or r.get("argt")) else r
            for r in extraction["uses"]]
    return dict(extraction, defines=defines, uses=uses)
