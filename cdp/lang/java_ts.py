"""Java define rows from the shared tree-sitter layer (cdp.ts, rules/java.scm + emit_map.json).

Tool-provided: fqn, kind, visibility, anchor line, end_line, params name/type, ret, ftype, supertypes, annotation name/text/lines.
Own code fills what the rules do not say: type text -> fqn (hand resolver), type-variable scope, tparams/throws/sig fields,
constant `value`, annotation fqn/args and parameter annotations, all carried from the hand-parsed row with the same (fqn, line).
`apply` returns None when the layer is unavailable or the file is unusable (skipped, crashed, parse errors): the caller keeps the hand rows."""
import re
from typing import Dict, List, Optional

from .base import Ann, mk_define
from .java_types import NO_RETURN, norm_type, resolve_name

_STR = re.compile(r'("""[\s\S]*?"""|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\')|(\s+|//[^\n]*|/\*[\s\S]*?\*/)')
_JAVA_LANG_ANN = {"Override", "Deprecated", "SuppressWarnings", "FunctionalInterface", "SafeVarargs"}
_CARRY = ("tparams", "throws", "cfgp", "sig", "psig", "arity", "value")


def tight(t: str) -> str:
    """Annotation text as the hand tokenizer joins it: no comments, no whitespace except between two word characters."""
    out, last = [], 0
    for m in _STR.finditer(t):
        if m.group(2):
            a, b = t[:m.start()][-1:], t[m.end():][:1]
            out.append(t[last:m.start()])
            out.append(" " if (a.isalnum() or a in "_$") and (b.isalnum() or b in "_$") else "")
            last = m.end()
    out.append(t[last:])
    return "".join(out)


def bare(t: str) -> str:
    """Type text without type-use annotations (`List<@NonNull String>`, `int @Z []`): they are not part of the type."""
    while "@" in t:
        m = re.search(r"@\s*[\w$.]+", t)
        if not m:
            break
        j, depth = m.end(), 0
        k = j
        while k < len(t) and t[k] == " ":
            k += 1
        if k < len(t) and t[k] == "(":
            for j in range(k, len(t)):
                depth += (t[j] == "(") - (t[j] == ")")
                if depth == 0:
                    j += 1
                    break
        t = t[:m.start()] + " " + t[j:]
    return re.sub(r"\s+", " ", t).replace(" [", "[").replace("< ", "<").strip()


def _line(a: Dict) -> int:
    return a.get("line", a.get("start_line"))


def apply(ctx, types, resolver, pkg: str, old: List[Dict]) -> Optional[List[Dict]]:
    try:
        from cdp import ts
        if not ts.enabled("java"):
            return None
        res = ts.extract_ex("java", ctx.path, "\n".join(ctx.lines), pkg, keep_raw=True)
    except Exception:
        return None
    if res is None:
        return None
    rows, meta = res
    if meta.get("skipped") or meta.get("crash") or meta.get("error") or meta.get("has_error") or not rows:
        return None
    blank = set(meta.get("skipped_lines", ()))       # lines the layer blanked (over-long): its text there is empty
    hand = {(d["fqn"], _line(d["anchor"])): d for d in old}
    idx = {}                                    # (name-line, name) -> (type, member|None) for type-variable scope
    for jt in types:
        idx[(jt.line, jt.name)] = (jt, None)
        for m in jt.members:
            idx[(m.line, "<init>" if m.kind == "ctor" else m.name)] = (jt, m)
    norm = lambda t, tv: norm_type(bare(t), lambda n: resolve_name(resolver, n), tv) or bare(t)
    out = []
    for x in rows:
        h = hand.get((x["fqn"], _line(x["anchor"])))
        name = x["fqn"].rsplit("#", 1)[-1] if "#" in x["fqn"] else x["fqn"].rsplit(".", 1)[-1]
        jt, m = idx.get((_line(x["anchor"]) - 1, name), (None, None))
        tv = set(jt.all_tparams()) if jt else set()
        if m is not None:
            tv |= set(m.tparams)
        anns = []
        for a, raw in zip(x.get("annotations", []), x.get("raw_annotations", [])):
            ha = next((q for q in (h or {}).get("annotations", []) if q["name"] == a["name"] and q.get("line") == a["line"]), None)
            gap = ha and blank.intersection(range(a["line"], a["end_line"] + 1))
            ann = Ann(a["name"], ha["text"] if gap else tight(raw), a["line"] - 1, a["end_line"] - 1)
            if not (ha and ha.get("fqn")) and a["name"] in _JAVA_LANG_ANN:
                ann.fqn = "java.lang." + a["name"]       # java.lang is imported implicitly (JLS 7.3); a local or imported type of that name wins (set by the hand resolver)
            if ha:
                ann.fqn = ha.get("fqn") or ann.fqn
                ann.arg_map = ha.get("args") or {}
                if "args" in ha and not ha["args"]:
                    ann.parses_args = True
            anns.append(ann)
        end = x["end_line"] if x["kind"] not in ("field", "constant") or (h and "end_line" in h) else None   # S3: every type has a span
        row = mk_define(x["fqn"], x["kind"], x["visibility"], x["anchor"], end_line=end, annotations=anns)
        if x.get("supertypes"):
            row["supertypes"] = [norm(t, tv) for t in x["supertypes"]]
        if "ret" in x:
            row["ret"] = x["ret"] if x["ret"] == NO_RETURN else norm(x["ret"], tv)
        if "ftype" in x:
            row["ftype"] = x["ftype"] if x["ftype"] == x["fqn"].rsplit(".", 1)[0] else norm(x["ftype"], tv)   # enum constant: its owner
        if x.get("params"):
            hp = (h or {}).get("params") or []
            row["params"] = []
            for i, p in enumerate(x["params"]):
                pr = {"name": p["name"], "type": norm(p["type"], tv) if p.get("type") else ""}
                if i < len(hp) and hp[i].get("annotations") and hp[i]["name"] == p["name"]:
                    pr["annotations"] = hp[i]["annotations"]
                row["params"].append(pr)
        for key in _CARRY:
            if h and key in h:
                row[key] = h[key]
        if h and blank:                           # annotations on a blanked line: the layer never saw them
            have = {(q["name"], q["line"]) for q in row.get("annotations", [])}
            extra = [q for q in h.get("annotations", []) if (q["name"], q["line"]) not in have and blank.intersection(range(q["line"], q["end_line"] + 1))]
            if extra:
                row["annotations"] = sorted(row.get("annotations", []) + extra, key=lambda q: (q["line"], q["end_line"]))
        out.append(row)
    seen = {(r["fqn"], _line(r["anchor"])) for r in out}
    out += [d for k, d in hand.items() if k not in seen and _line(d["anchor"]) in blank]   # declarations on a blanked line
    return out
