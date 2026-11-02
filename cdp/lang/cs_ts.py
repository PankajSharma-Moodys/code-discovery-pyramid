"""C# define rows from the shared tree-sitter layer (cdp.ts, rules/csharp.scm + emit_map.json), as java_ts does for Java.

Tool-provided: fqn, kind, visibility, anchor, end_line, params name/type, ret, ftype, supertypes, attribute name/text/lines.
Own code fills what the rules do not say: type text -> fqn (hand Resolver / norm_type), generic scope, `@` verbatim-name strip,
and every field only the hand model knows (tparams, clr, route, abstract, pmax, ext, sig, value, parameter modifier/default/
attributes, attribute fqn/args), carried from the hand row with the same (fqn, line). Hand rows the rules never produce
(primary-constructor `<init>` and record fields) are kept. `apply` returns None when the layer is unavailable or the file is
unusable (skipped, crashed, parse errors): the caller keeps the hand rows."""
import re
from typing import Dict, List, Optional

from .base import Ann, mk_define
from .csharp_decl import parse_type
from .csharp_tokens import CsTokens
from .java_ts import tight
from .java_types import NO_RETURN

_VERBATIM = re.compile(r"(^|[.#])@")
_SKIP = frozenset(("fqn", "kind", "visibility", "anchor", "end_line", "annotations", "ret", "ftype", "params", "supertypes"))


def _ann(name, text, line, end, h):
    a = Ann(name, text, line - 1, end - 1)
    if h:
        a.fqn, a.arg_map = h.get("fqn"), h.get("args") or {}
    return a


def apply(ctx, types, resolver, ns: str, old: List[Dict], norm_type, resolve) -> Optional[List[Dict]]:
    try:
        from cdp import ts
        if not ts.enabled("csharp"):
            return None
        res = ts.extract_ex("csharp", ctx.path, "\n".join(ctx.lines), "", keep_raw=True)
    except Exception:
        return None
    if res is None:
        return None
    rows, meta = res
    if meta.get("skipped") or meta.get("crash") or meta.get("error") or meta.get("has_error") or not rows:
        return None
    line = lambda a: a.get("line", a.get("start_line"))
    hand = {(d["fqn"], line(d["anchor"])): d for d in old}
    idx = {}                                    # (name-line, name) -> (type, member|None): generic scope
    for jt in types:
        idx[(jt.line, jt.name)] = (jt, None)
        for m in jt.members:
            idx[(m.line, "<init>" if m.kind == "ctor" else m.name)] = (jt, m)
    def norm(t, tv, glob=False):                # the hand type reader drops `?`, names tuples `ValueTuple<..>`; then the hand resolver
        r = parse_type(CsTokens([t]), 0)
        t = r[1] if r else t
        own = t.split("<", 1)[0]                # `global::A.B` is fully qualified (its own name, not its type arguments)
        return norm_type(t, lambda n: n if glob and n == own else resolve(resolver, n), tv) or t
    out, seen = [], set()
    for x in rows:
        fqn = _VERBATIM.sub(r"\1", x["fqn"])
        h = hand.get((fqn, line(x["anchor"])))
        seen.add((fqn, line(x["anchor"])))
        name = fqn.rsplit("#", 1)[-1] if "#" in fqn else fqn.rsplit(".", 1)[-1]
        jt, m = idx.get((line(x["anchor"]) - 1, name), (None, None))
        tv = set(jt.all_tparams()) if jt else set()
        if m is not None:
            tv |= set(m.tparams)
        hann = {(q["name"], q["line"]): q for q in (h or {}).get("annotations", [])}
        anns = []
        for a, raw in zip(x.get("annotations", []), x.get("raw_annotations", [])):
            name = a["name"][:-9] if a["name"].endswith("Attribute") and len(a["name"]) > 9 else a["name"]      # `[RouteAttribute]` is `Route`
            anns.append(_ann(name, tight(raw), a["line"], a["end_line"], hann.get((name, a["line"]))))
        have = {(q[0], q.line + 1) for q in anns}      # `#if` branches: the grammar reads one, the hand reader both
        anns += [_ann(k[0], q["text"], q["line"], q["end_line"], q) for k, q in hann.items() if k not in have]
        anns.sort(key=lambda q: q.line)
        end = x["end_line"] if x["kind"] not in ("field", "constant") or (h and "end_line" in h) else None   # S3: every type has a span
        row = mk_define(fqn, x["kind"], x["visibility"], x["anchor"], end_line=end, annotations=anns)
        if x.get("supertypes") and x["kind"] != "enum":
            row["supertypes"] = [norm(t[8:], tv, True) if t.startswith("global::") else norm(t, tv) for t in x["supertypes"]]
        if "ret" in x:
            row["ret"] = x["ret"] if x["ret"] == NO_RETURN else norm(x["ret"], tv)
        if "ftype" in x:
            row["ftype"] = x["ftype"] if x["ftype"] == fqn.rsplit(".", 1)[0] else norm(x["ftype"], tv)
        hp = (h or {}).get("params") or []
        tp = {p["name"]: p for p in x.get("params", [])}
        if tp or hp:                              # no `parameter` node for `params T[] x`: the hand param fills it
            row["params"] = []
            for p in [tp.get(q["name"], q) for q in hp] if hp else tp.values():
                pr = {"name": p["name"], "type": norm(p["type"], tv) if p["name"] in tp and p.get("type") else p.get("type", "")}
                pr.update({k: v for k, v in next((q for q in hp if q["name"] == p["name"]), {}).items() if k not in pr})
                row["params"].append(pr)
        for key, v in (h or {}).items():
            if key not in _SKIP and key not in row:
                row[key] = v
        out.append(row)
    out += [d for k, d in hand.items() if k not in seen]    # primary-constructor `<init>` and record fields
    return out
