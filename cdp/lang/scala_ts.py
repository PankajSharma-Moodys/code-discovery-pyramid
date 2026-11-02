"""Scala declaration facts from the tool layer (cdp.ts, rules/scala.scm). Replaces, on every matching hand row, the
visibility, extent and the type texts of ret/ftype/params/supertypes; what the grammar does not give stays ours: type
resolution to fqn (`norm_type`), type-variable scope, constants, annotation args/fqn, sigs, ctor rows."""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

from .. import ts
from .base import annotation_rows
from .scala_annotations import make_ann
from .scala_tokens import ScTokens
from .java_types import NO_RETURN, norm_type, resolve_name
from .scala_decl import scala_type_text

_SPANNED = ("class", "interface", "enum")
_VIS = re.compile(r"(private|protected)\s*(?:\[\s*(\w+)\s*\])?")


def _vis(text: str) -> str:
    """`private[this]` -> private; `protected[pkg]` -> package (SLS 5.2: a qualifier other than `this` widens to that scope)."""
    m = _VIS.match(text)
    if not m:
        return text
    return m.group(1) if m.group(2) in (None, "this") else "package"


_META = re.compile(r"^@\(\s*([\w.]+)[^()]*\)")      # `@(Schema @field)(..)`: annotation Schema, meta target field


def _ann_rows(anns, resolver):
    """Annotation rows for a tool row: name/span from the grammar text, element values and fqn from our parsers
    (the tool gives the span, not the values)."""
    out = []
    for a in anns:
        ann, _ = make_ann(ScTokens(_META.sub(r"@\1", a["text"]).splitlines() or [a["text"]]), 0)
        ann.line, ann.end_line = a["line"] - 1, a["end_line"] - 1
        ann.fqn = resolver.local_types.get(ann[0]) or resolver.simple_to_fqn.get(ann[0])
        out.append(ann)
    return annotation_rows(out)


def _scopes(types) -> Dict[Tuple[str, int], frozenset]:
    out = {}
    for jt in types:
        tv = frozenset(jt.all_tparams())
        out[(jt.fqn, jt.line)] = tv
        for m in jt.members:
            if m.kind == "init":
                continue
            name = "<init>" if m.kind == "ctor" else m.name
            out[(jt.fqn + ("#" if m.kind in ("method", "ctor") else ".") + name, m.line)] = tv | frozenset(m.tparams)
    return out


def apply(ctx, facts, types, resolver, pkg: str) -> Optional[dict]:
    """Overlay tool rows onto facts.defines in place. -> meta (None when the layer is off or the hand rows stay)."""
    if not ts.enabled("scala"):
        return None
    res = ts.extract_ex("scala", ctx.path, "\n".join(ctx.lines), pkg or "")
    if res is None:
        return None
    rows, meta = res
    if meta.get("skipped") or meta.get("has_error") or meta.get("crash") or meta.get("error"):
        return meta                                   # whole-file error / skipped: hand rows as they are
    tools: Dict[Tuple[str, int], List[dict]] = {}
    for r in rows:
        tools.setdefault((r["fqn"], r["anchor"]["line"]), []).append(r)
    scopes = _scopes(types)
    norm = lambda t, tv: norm_type(scala_type_text(t), lambda n: resolve_name(resolver, n), tv) or t
    for row in facts.defines:
        cands = tools.get((row["fqn"], row["anchor"]["line"]))
        if not cands:
            continue
        tr = next((c for c in cands if c["kind"] == row["kind"] or row["kind"] in ("constant", "field") and c["kind"] == "field"), None)
        if tr is None:
            continue
        tv = scopes.get((row["fqn"], row["anchor"]["line"] - 1), frozenset())
        row["visibility"] = _vis(tr["visibility"])
        if "end_line" in tr and ("end_line" in row or row["kind"] in _SPANNED):
            row["end_line"] = tr["end_line"]               # S3: a type define carries its extent too
        if "supertypes" in tr and "supertypes" in row:
            row["supertypes"] = [norm(t, tv) for t in tr["supertypes"]]
        if row["kind"] == "method" and row["fqn"].rsplit("#", 1)[-1] != "<init>" and "ret" in tr:
            row["ret"] = NO_RETURN if tr["ret"] in ("<none>", "Unit", "scala.Unit") else norm(tr["ret"], tv)
        elif row["kind"] in ("field", "constant") and "ftype" in tr and "ftype" in row:
            row["ftype"] = norm(tr["ftype"], tv)
        if "params" in tr and "params" not in row and row["kind"] == "method":
            row["params"] = [{"name": p["name"], **({"type": norm(p["type"], tv)} if p.get("type") else {})} for p in tr["params"]]
        elif "params" in tr and "params" in row and len(tr["params"]) == len(row["params"]):
            for hp, tp in zip(row["params"], tr["params"]):
                if tp.get("type"):
                    hp["type"] = norm(tp["type"], tv)
    have = {(r["fqn"], r["anchor"]["line"]) for r in facts.defines}
    otv = {jt.fqn: frozenset(jt.all_tparams()) for jt in types}
    owners = {r["fqn"] for r in facts.defines if r["kind"] in ("class", "interface", "enum")}
    for tr in rows:
        # class-parameter fields the hand parser lost (`@(Schema @field)(..)` annotation forms end its parameter scan)
        if tr["kind"] in _SPANNED and (tr["fqn"], tr["anchor"]["line"]) not in have and tr["fqn"] in owners:
            # X23: a companion `object X` is a type define of its own (the hand parser merged it into the class row)
            tr.update(object=True, companion=True, visibility=_vis(tr["visibility"]))
            tr["annotations"] = _ann_rows(tr["annotations"], resolver) if tr.get("annotations") else []
            if not tr["annotations"]:
                del tr["annotations"]
            if "supertypes" in tr:
                tr["supertypes"] = [norm(t, frozenset()) for t in tr["supertypes"]]
            facts.defines.append(tr)
        elif tr["kind"] == "field" and (tr["fqn"], tr["anchor"]["line"]) not in have and tr["fqn"].rsplit(".", 1)[0] in owners:
            tv = otv.get(tr["fqn"].rsplit(".", 1)[0], frozenset())
            tr["visibility"] = _vis(tr["visibility"])
            if "ftype" in tr:
                tr["ftype"] = norm(tr["ftype"], tv)
            if tr.get("annotations"):
                tr["annotations"] = _ann_rows(tr["annotations"], resolver)
            facts.defines.append(tr)
    return meta
