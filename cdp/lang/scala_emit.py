"""Scala facts from the token parser: imports, define rows, annotations, DI signals.

Mirrors `java.py`'s `_read_imports`, `_declarations` and `_emit_annotation_facts`, with the same row
shapes (`defines[]` with `annotations[].args`, `params`, `supertypes`, `ret`/`ftype`, `end_line`), so
the rule engine, `resolve.py` and the dataflow read a Scala row exactly like a Java one.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Set, Tuple

from .base import (
    ExtractContext,
    FileFacts,
    annotation_rows,
    anchor_at,
    is_third_party,
    mk_define,
    mk_use,
)
from .java import _Resolver
from .java_decl import join_tokens
from .java_types import norm_type, resolve_name
from .scala_annotations import STRIP_SUFFIXES, strip_margin
from .scala_decl import ScMember, ScType, ScalaDeclParser, scala_type_text
from .scala_tokens import ScTokens, string_value

SCALA_BUILTINS = frozenset([
    "String", "Int", "Long", "Double", "Float", "Boolean", "Byte", "Short", "Char", "Unit", "Any",
    "AnyRef", "AnyVal", "Nothing", "Null", "Object", "Option", "Some", "None", "Seq", "List", "Map",
    "Set", "Array", "Vector", "Iterable", "Iterator", "Either", "Left", "Right", "Try", "Success",
    "Failure", "Future", "Tuple2", "Tuple3", "BigDecimal", "BigInt", "Throwable", "Exception",
    "Class", "Product", "Serializable", "Nil", "Predef", "StringBuilder", "Option",
])
BARE_DROP = frozenset(["Unit", "Int", "Long", "Double", "Float", "Boolean", "Byte", "Short", "Char", "String",
                       "Any", "AnyRef", "AnyVal", "Nothing", "Null", "Object"])
DI_ANNOTATIONS = frozenset(["Component", "Service", "Repository", "Configuration", "Bean", "Autowired",
                            "Inject", "Named", "Singleton", "Controller", "RestController"])
JOB_SUPERS = frozenset(["Job", "InterruptableJob", "AbstractJob"])
_QUALIFIED_ANN_RE = re.compile(r"@([\w$]+(?:\s*\.\s*[\w$]+)*)")


class ScResolver(_Resolver):
    """`java._Resolver` that knows Scala's default imports (`scala.*`, `java.lang.*`, `Predef`)."""

    def resolve(self, name: str) -> Tuple[str, str]:
        base = name.strip().split("<", 1)[0].replace("[]", "").strip()
        if base in SCALA_BUILTINS and base not in self.local_types and base not in self.simple_to_fqn:
            return base, "third_party"
        return super().resolve(name)


# ------------------------------------------------------------------ imports


def read_imports(ctx: ExtractContext, tk: ScTokens, facts: FileFacts) -> Tuple[List[Dict], Dict[str, str], List[str]]:
    """`import a.b.C`, `a.b._`, `a.b.{C, D => E, _}` (any layout), at any nesting. Rows keep the
    old shape: a wildcard's `fqn` is the package without `._`."""
    imports: List[Dict] = []
    simple_to_fqn: Dict[str, str] = {}
    wildcards: List[str] = []
    n = tk.n
    i = 0
    while i < n:
        if not (tk.kind[i] == "id" and tk.text[i] == "import"
                and (i == 0 or tk.line[i - 1] < tk.line[i] or tk.text[i - 1] in ("{", ";", "}"))):
            i += 1
            continue
        row_line = tk.line[i]
        j = i + 1
        while j < n:
            path: List[str] = []
            while tk.is_id(j):
                path.append(tk.text[j])
                j += 1
                if tk.at(j) == "." and (tk.is_id(j + 1) or tk.at(j + 1) in ("_", "*", "{")):
                    j += 1
                    if tk.at(j) in ("_", "*"):
                        break
                    continue
                break
            base = ".".join(path)
            picks: List[Tuple[str, Optional[str]]] = []      # (fqn, local name or None for wildcard)
            if tk.at(j) in ("_", "*") and tk.text[j - 1] == ".":
                picks.append((base, None))
                j += 1
            elif tk.at(j) == "{":
                c = tk.close(j)
                k = j + 1
                while k < c:
                    if tk.at(k) in ("_", "*"):
                        picks.append((base, None))
                        k += 1
                    elif tk.is_id(k):
                        name, local = tk.text[k], tk.text[k]
                        k += 1
                        if tk.at(k) == "=>":
                            k += 1
                            if tk.at(k) == "_":
                                local = ""
                            elif tk.is_id(k):
                                local = tk.text[k]
                            k += 1
                        if local:
                            picks.append((base + "." + name, local))
                    else:
                        k += 1
                j = c + 1
            elif path:
                picks.append((base, path[-1]))
            for fqn, local in picks:
                anchor = anchor_at(ctx, row_line)
                if anchor is None:
                    continue
                imports.append({"fqn": fqn, "line": row_line + 1, "static": False, "anchor": anchor})
                if local is None:
                    wildcards.append(fqn)
                else:
                    simple_to_fqn.setdefault(local, fqn)
                resolved = "third_party" if is_third_party(fqn) else "external"
                facts.uses.append(mk_use(fqn, anchor, via_import=True, resolved=resolved))
            if tk.at(j) == "," and tk.is_id(j + 1):
                j += 1
                continue
            break
        i = max(j, i + 1)
    facts.imports = imports
    return imports, simple_to_fqn, wildcards


# ------------------------------------------------------------- declarations


def _vis(jt: ScType) -> str:
    for m in jt.mods:
        if m.startswith("__vis_"):
            return m[6:]
    return "public"


def _resolve_annotations(jt: ScType, resolver: ScResolver) -> None:
    def one(ann) -> None:
        m = _QUALIFIED_ANN_RE.match(ann[1])
        name = m.group(1).replace(" ", "") if m else ann[0]
        if "." in name:
            ann.fqn = resolver.resolve(name)[0]
        else:
            ann.fqn = resolver.local_types.get(name) or resolver.simple_to_fqn.get(name)

    for ann in jt.anns:
        one(ann)
    for ann in jt.ctor_anns:
        one(ann)
    for m in jt.members:
        for ann in m.anns:
            one(ann)
        for group in m.param_anns:
            for ann in group:
                one(ann)


def _param_row(name: str, ptype: str, anns) -> Dict:
    row = {"name": name, "type": ptype}
    if anns:
        row["annotations"] = annotation_rows(anns)
    return row


_STRIP_SUFFIXES = STRIP_SUFFIXES


def _is_pure_concat(tk: ScTokens, a: int, b: int) -> bool:
    """`"a" + B + "c"` (also a `.stripMargin` tail): strings, names and `+` only."""
    if b <= a:
        return False
    for j in range(a, b):
        k, t = tk.kind[j], tk.text[j]
        if k == "str" and string_value(t) is not None:
            continue
        if k == "id" and t not in ("new", "this", "super") and tk.at(j + 1) != "(":
            continue
        if k == "op" and t in ("+", "."):
            continue
        return False
    return True


def constant_value(tk: ScTokens, m: ScMember, owner: ScType, values: Dict[str, Optional[str]]) -> str:
    """A constant's initialiser as text: string literals and constant names concatenated (another
    object's constant stays symbolic, `${Owner.NAME}`, for the resolve phase); a `.stripMargin`
    tail is applied; anything else keeps the first string literal, or the raw expression."""
    a, b = m.init
    margin = False
    while b - 2 > a and tk.kind[b - 1] == "id" and tk.text[b - 2] == "." and "." + tk.text[b - 1] in _STRIP_SUFFIXES:
        margin = margin or tk.text[b - 1] == "stripMargin"
        b -= 2
    parts: List[str] = []
    j = a
    ok = b > a
    while ok and j < b:
        k, t = tk.kind[j], tk.text[j]
        if k == "str" and string_value(t) is not None:
            parts.append(string_value(t))
            j += 1
        elif k == "id" and t not in ("new", "this", "super") and tk.at(j + 1) != "(":
            names = [t]
            while tk.at(j + 1) == "." and tk.is_id(j + 2) and tk.at(j + 3) != "(":
                names.append(tk.text[j + 2])
                j += 2
            known = values.get(names[0]) if len(names) == 1 else None
            parts.append(known if known is not None else "${%s}" % ".".join(
                [owner.name] + names if len(names) == 1 else names[-2:]))
            j += 1
        else:
            ok = False
            break
        if j < b:
            if tk.at(j) != "+":
                ok = False
                break
            j += 1
            if j >= b:
                ok = False
    if ok and parts:
        s = "".join(parts)
        return strip_margin(s) if margin else s
    raw = join_tokens(tk, a, b)
    for j in range(a, b):
        if tk.kind[j] == "str" and string_value(tk.text[j]) is not None:
            s = string_value(tk.text[j])
            return strip_margin(s) if margin else s
    return raw


def declarations(ctx: ExtractContext, facts: FileFacts, tk: ScTokens, types: List[ScType],
                 resolver: ScResolver) -> List[Dict]:
    """Define rows for every type, constructor, method and field at any visibility, and the `decls`
    list later readers attach to (`index` = 0-based line of the name)."""
    decls: List[Dict] = []
    companions: Set[str] = set()
    consts: Dict[str, Dict[str, Optional[str]]] = {}
    classes = {(t.outer.fqn if t.outer else None, t.name) for t in types if not t.is_object}

    def typed(row: Dict, text: str, tvars) -> None:
        if not text:
            return
        norm = norm_type(text, lambda n: resolve_name(resolver, n), tvars)
        if norm and norm not in BARE_DROP:
            row["ret" if row["kind"] == "method" else "ftype"] = norm

    for jt in types:
        _resolve_annotations(jt, resolver)
    for jt in sorted(types, key=lambda t: (t.line, t.fqn)):
        companion = jt.is_object and (jt.outer.fqn if jt.outer else None, jt.name) in classes
        anchor = anchor_at(ctx, jt.line)
        if anchor is not None and not companion:
            row = mk_define(jt.fqn, jt.kind, _vis(jt), anchor, annotations=jt.anns)
            if jt.is_object:
                row["object"] = True
            if jt.is_case:
                row["case"] = True
            if jt.tparams:
                row["tparams"] = jt.tparams
            if jt.supertypes:
                row["supertypes"] = [norm_type(scala_type_text(t), lambda n: resolve_name(resolver, n),
                                               jt.all_tparams()) or t for t in jt.supertypes]
            facts.defines.append(row)
            decls.append({"fqn": jt.fqn, "kind": jt.kind, "visibility": _vis(jt),
                          "anchor": anchor, "index": jt.line, "name": jt.name})
        elif companion:
            companions.add(jt.fqn)
        tv = jt.all_tparams()
        values = consts.setdefault(jt.fqn, {})
        for m in jt.members:
            if m.kind == "init":
                continue
            anchor = anchor_at(ctx, m.line)
            if anchor is None:
                continue
            vis = m.visibility
            if m.kind in ("method", "ctor"):
                name = "<init>" if m.kind == "ctor" else m.name
                fqn = jt.fqn + "#" + name
                row = mk_define(fqn, "method", vis, anchor, end_line=m.end_line + 1, annotations=m.anns)
                mtv = tv | set(m.tparams)
                if m.kind == "method":
                    typed(row, m.ret, mtv)
                if m.params:
                    row["params"] = [
                        _param_row(pname, norm_type(ptype, lambda n: resolve_name(resolver, n), mtv) or ptype, pa)
                        for (ptype, pname), pa in zip(m.params, m.param_anns)]
                facts.defines.append(row)
                decls.append({"fqn": fqn, "kind": "method", "visibility": vis, "anchor": anchor,
                              "index": m.line, "name": name})
            elif m.kind == "field":
                fqn = jt.fqn + "." + m.name
                final = "final" in m.mods
                is_const = m.init is not None and not m.is_var and not m.is_lazy and (
                    final or (jt.is_object and _is_pure_concat(tk, *_strip_tail(tk, m.init))))
                if is_const:
                    value = constant_value(tk, m, jt, values)
                    values[m.name] = value
                    row = mk_define(fqn, "constant", vis, anchor, value=value, annotations=m.anns)
                    decls.append({"fqn": fqn, "kind": "constant", "visibility": vis, "anchor": anchor,
                                  "index": m.line, "name": m.name})
                else:
                    row = mk_define(fqn, "field", vis, anchor, annotations=m.anns)
                    decls.append({"fqn": fqn, "kind": "field", "visibility": vis, "anchor": anchor,
                                  "index": m.line, "name": m.name, "owner_fqn": jt.fqn})
                typed(row, m.ftype, tv)
                facts.defines.append(row)
    for r in facts.defines:
        if r["fqn"] in companions and r["kind"] in ("class", "interface"):
            r["companion"] = True
    decls.sort(key=lambda d: d["index"])
    return decls


def _strip_tail(tk: ScTokens, span: Tuple[int, int]) -> Tuple[int, int]:
    a, b = span
    while b - 2 > a and tk.kind[b - 1] == "id" and tk.text[b - 2] == "." and "." + tk.text[b - 1] in _STRIP_SUFFIXES:
        b -= 2
    return a, b


def di_signals(facts: FileFacts, types: List[ScType]) -> None:
    for jt in types:
        groups = [jt.anns, jt.ctor_anns]
        for m in jt.members:
            groups.append(m.anns)
            groups.extend(m.param_anns)
        for g in groups:
            for ann in g:
                if ann[0] in DI_ANNOTATIONS:
                    facts.signals.append("di:" + ann[0])
