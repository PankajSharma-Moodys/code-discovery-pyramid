"""Python define rows from the shared tree-sitter layer (cdp.ts, rules/python.scm + emit_map.json).

Tool-provided: fqn, kind, visibility, anchor line, end_line, params name/annotation, supertypes (bases), decorator
name/text/lines. Own code fills what the rules do not say: decorator `args` and `fqn` (from the flow pass's
expressions), base-class fqns, and the resolver-encoded `ret`/`ftype`/`value`, which stay the flow pass's
(python_flow ann_ex/ex_of; X11d2 and X48 depend on that encoding). Declarations only the flow pass sees (`self.x = ...`,
defs nested in functions) are kept as it made them. `apply` returns None when the layer is unavailable or the file has
parse errors: the flow rows stay, without decorators, params and supertypes."""
import ast
import re
from typing import Dict, List, Optional

from .base import Ann, mk_define
from .python_flow import BUILTINS


def ex_fqn(ex, target=None, flow=None) -> Optional[str]:
    """Dotted name of a resolver expression `M:pkg|.Cls|()|.m` (instances drop the `()`); None when it is not a plain name chain.
    A module-level variable of this file (`router.get`) is replaced by its value's type (`fastapi.APIRouter.get`)."""
    if ex and flow and ex[0] == "M:" + flow.mod and ex[1] and ex[1][0][1:] in flow.mod_types:
        t = flow.mod_types[ex[1][0][1:]]
        ex = (t[0], t[1] + ex[1][1:]) if t else ex
    if ex is None:
        return "builtins." + target.id if isinstance(target, ast.Name) and target.id in BUILTINS else None
    if ex[0][:2] not in ("M:", "D:") or any(s != "()" and not s.startswith(".") for s in ex[1]):
        return None
    return ".".join([ex[0][2:]] + [s[1:] for s in ex[1] if s != "()"])


def _dotted(n) -> Optional[str]:
    parts = []
    while isinstance(n, ast.Attribute):
        parts.append(n.attr)
        n = n.value
    return ".".join([n.id] + parts[::-1]) if isinstance(n, ast.Name) else None


def _value(flow, n):
    """Argument value as annotation_args.py shapes it: literal, list, {"ref": dotted name}, else {"text": source}."""
    if isinstance(n, ast.Constant) and isinstance(n.value, (str, int, float, bool)):
        return n.value
    if isinstance(n, (ast.List, ast.Tuple, ast.Set)):
        return [_value(flow, e) for e in n.elts]
    ref = _dotted(n)
    if ref:
        return {"ref": ref}
    if isinstance(n, ast.BinOp) and isinstance(n.op, ast.Add):
        a, b = _value(flow, n.left), _value(flow, n.right)
        if isinstance(a, str) and isinstance(b, str):
            return a + b
    return {"text": flow.src(n)}


def decorator_args(flow, d) -> Dict:
    if not isinstance(d, ast.Call):
        return {}
    out = {}
    for i, a in enumerate(d.args):
        out["*" if isinstance(a, ast.Starred) else "value" if i == 0 else "arg%d" % i] = (
            {"text": flow.src(a)} if isinstance(a, ast.Starred) else _value(flow, a))
    for k in d.keywords:
        out[k.arg or "**"] = _value(flow, k.value)
    return out


_NAME = re.compile(r"([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*)\s*(?:\(|$)")


def _ann_name(raw: str) -> str:
    body = " ".join(raw[1:].split())
    m = _NAME.match(body)
    return m.group(1) if m else body


def apply(ctx, primary: str, flow, old: List[Dict]) -> Optional[List[Dict]]:
    try:
        from cdp import ts
        if not ts.enabled("python"):
            return None
        res = ts.extract_ex("python", ctx.path, "\n".join(ctx.lines), primary, keep_raw=True)
    except Exception:
        return None
    if res is None:
        return None
    rows, meta = res
    if meta.get("skipped") or meta.get("crash") or meta.get("error") or meta.get("has_error") or not rows:
        return None
    hand = {d["fqn"]: d for d in old}
    out, seen = [], set()
    for x in rows:
        raws = x.get("raw_annotations", [])
        if x["fqn"] in seen or any(a["name"] == "overload" for a in x.get("annotations", [])):
            continue                                  # a redefinition or `@overload` stub: the first real definition is the symbol
        seen.add(x["fqn"])
        h = hand.get(x["fqn"])
        dec = flow.decs.get(x["fqn"]) if flow else None
        dec = dec[1] if dec and len(dec[1]) == len(raws) else None
        anns = []
        for i, (a, raw) in enumerate(zip(x.get("annotations", []), raws)):
            ann = Ann(_ann_name(raw), raw, a["line"] - 1, a["end_line"] - 1)
            ann.parses_args = False   # Python keeps `@A()` without args (pinned by test_empty_paren_annotations)
            if dec:
                ann.fqn = ex_fqn(dec[i][1], dec[i][2], flow)
                ann.arg_map = decorator_args(flow, dec[i][0])
            anns.append(ann)
        row = mk_define(x["fqn"], x["kind"], x["visibility"], x["anchor"], end_line=x["end_line"], annotations=anns)
        if x.get("supertypes"):
            bases = flow.bases.get(x["fqn"], {}) if flow else {}
            row["supertypes"] = [ex_fqn(bases.get(" ".join(t.split())), None, flow) or t for t in x["supertypes"]]
        if x.get("params"):
            row["params"] = x["params"]
        for key in ("ret", "ftype", "value"):
            if h and key in h:
                row[key] = h[key]
        out.append(row)
    out += [d for f, d in hand.items() if f not in seen]
    return sorted(out, key=lambda d: d["anchor"]["line"])
