"""Annotation element-value pairs from the Java token stream (ANNOTATIONS_PLAN §4).

`@Every(jobName="X", value="60s", misfirePolicy=Every.MisfirePolicy.NOW)` becomes
`{"jobName": "X", "value": "60s", "misfirePolicy": {"ref": "Every.MisfirePolicy.NOW"}}`.

Values: string, number, bool, `{"ref": X}` (constant or enum), `{"class": X}` (`Foo.class`),
list (`{a, b}`), a nested annotation row (same shape as any annotation row), `{"concat": [...]}`
(`BASE + "/x"`: strings and refs), and `{"text": src}` for anything else. A single unnamed
argument is stored under `value`. Nothing here evaluates or resolves: `resolve.py` adds
`resolved` to refs that name repo constants.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from .base import Ann, annotation_rows
from .java_tokens import Tokens

_ESC = {"n": "\n", "t": "\t", "r": "\r", "b": "\b", "f": "\f", "s": " ", "0": "\0",
        '"': '"', "'": "'", "\\": "\\"}
_ESC_RE = re.compile(r"\\(u+[0-9a-fA-F]{4}|\n|.)", re.S)


def _unescape(s: str) -> str:
    def sub(m):
        e = m.group(1)
        if e == "\n":
            return ""
        if e[0] == "u":
            return chr(int(e.lstrip("u"), 16))
        return _ESC.get(e, m.group(0))
    return _ESC_RE.sub(sub, s)


def text_block(raw: str) -> str:
    """The value of a `\"\"\"` text block: opening line dropped, incidental indentation
    stripped (the closing delimiter's line counts), trailing spaces trimmed, escapes read."""
    body = raw[3:-3]
    nl = body.find("\n")
    body = body[nl + 1:] if nl >= 0 else body
    lines = body.split("\n")
    sig = [l for l in lines[:-1] if l.strip()] + [lines[-1]]   # last line: closing delimiter's
    indent = min((len(l) - len(l.lstrip()) for l in sig), default=0)
    out = [l[indent:].rstrip() if l.strip() else "" for l in lines]
    return _unescape("\n".join(out))


def _string(raw: str) -> str:
    if raw.startswith('"""'):
        return text_block(raw)
    return _unescape(raw[1:-1])


def _number(t: str) -> Optional[Any]:
    s = t.replace("_", "")
    try:
        if re.fullmatch(r"(0[xX][0-9a-fA-F]+|0[bB][01]+|\d+)[lL]?", s):
            s = s.rstrip("lL")
            return int(s, 0) if not re.fullmatch(r"0\d+", s) else int(s, 8)
        if re.fullmatch(r"(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?[fFdD]?", s):
            return float(s.rstrip("fFdD"))
    except ValueError:
        pass
    return None


def _split(tk: Tokens, a: int, b: int) -> List[tuple]:
    """Top-level comma-separated element ranges `(start, end)` in `[a, b)`."""
    out, start, i = [], a, a
    while i < b:
        if tk.kind[i] == "op":
            t = tk.text[i]
            if t in "({[":
                i = tk.close(i)
            elif t == ",":
                if i > start:
                    out.append((start, i))
                start = i + 1
        i += 1
    if start < b:
        out.append((start, b))
    return out


def _join(tk: Tokens, a: int, b: int) -> str:
    from .java_decl import join_tokens
    return join_tokens(tk, a, b)


def _operand(tk: Tokens, a: int, b: int) -> Optional[Any]:
    """One operand of a `+` chain; None when it is not a literal, constant or class reference."""
    if a >= b:
        return None
    neg = False
    if tk.text[a] == "-" and tk.kind[a] == "op":
        neg, a = True, a + 1
        if a >= b:
            return None
    n = b - a
    k, t = tk.kind[a], tk.text[a]
    if n == 1:
        if k in ("str", "chr"):
            return None if neg else _string(t)
        if k == "num":
            v = _number(t)
            return None if v is None else (-v if neg else v)
        if k == "id" and not neg:
            if t in ("true", "false"):
                return t == "true"
            return {"ref": t}
        return None
    if neg or k != "id":
        return None
    parts = [t]
    i = a + 1
    while i + 1 < b and tk.text[i] == "." and tk.kind[i + 1] == "id":
        parts.append(tk.text[i + 1])
        i += 2
    if i != b:
        return None
    if parts[-1] == "class" and len(parts) > 1:
        return {"class": ".".join(parts[:-1])}
    return {"ref": ".".join(parts)}


def _plus_ranges(tk: Tokens, a: int, b: int) -> List[tuple]:
    out, start, i = [], a, a
    while i < b:
        if tk.kind[i] == "op":
            t = tk.text[i]
            if t in "({[":
                i = tk.close(i)
            elif t == "+":
                out.append((start, i))
                start = i + 1
        i += 1
    out.append((start, b))
    return out


def _value(tk: Tokens, a: int, b: int) -> Any:
    from .java_decl import skip_annotation
    if a >= b:
        return {"text": ""}
    while tk.text[a] == "(" and tk.kind[a] == "op" and tk.close(a) == b - 1 and b - a > 2:
        a, b = a + 1, b - 1                                  # (A + B)
    if tk.kind[a] == "op" and tk.text[a] == "@":
        end = skip_annotation(tk, a)
        if end == b:
            return _nested(tk, a, end)
    elif tk.kind[a] == "op" and tk.text[a] == "{" and tk.close(a) == b - 1:
        return [_value(tk, s, e) for s, e in _split(tk, a + 1, b - 1)]
    ranges = _plus_ranges(tk, a, b)
    ops = [_operand(tk, s, e) for s, e in ranges]
    if any(o is None for o in ops):
        return {"text": _join(tk, a, b)}
    if len(ops) == 1:
        return ops[0]
    for o in ops:
        if isinstance(o, dict) and "class" in o:
            return {"text": _join(tk, a, b)}
    if not any(isinstance(o, dict) for o in ops):
        if any(isinstance(o, str) for o in ops):             # all literals: the compiler folds it
            return "".join(_lit(o) for o in ops)
        return {"text": _join(tk, a, b)}                     # numeric sum: not a name to keep
    parts: List[Any] = []
    for o in ops:
        if isinstance(o, dict):
            parts.append(o)
        else:
            s = _lit(o)
            if parts and isinstance(parts[-1], str):
                parts[-1] += s
            else:
                parts.append(s)
    return {"concat": parts}


def _lit(o: Any) -> str:
    if isinstance(o, bool):
        return "true" if o else "false"
    return str(o)


def _nested(tk: Tokens, i: int, end: int) -> Dict:
    name = tk.text[i + 1] if i + 1 < tk.n else ""
    j = i + 2
    while tk.at(j) == "." and tk.is_id(j + 1):
        name = tk.text[j + 1]
        j += 2
    ann = Ann(name, _join(tk, i, end), tk.line[i], tk.line[end - 1], annotation_args(tk, i, end))
    return annotation_rows([ann])[0]


def annotation_args(tk: Tokens, i: int, end: int) -> Dict[str, Any]:
    """`args` of the annotation at the `@` at `i` (spanning tokens `[i, end)`); `{}` without any."""
    j = i + 2
    while tk.at(j) == "." and tk.is_id(j + 1):
        j += 2
    if tk.at(j) != "(" or tk.close(j) >= end:
        return {}
    close = tk.close(j)
    args: Dict[str, Any] = {}
    for a, b in _split(tk, j + 1, close):
        if tk.is_id(a) and tk.at(a + 1) == "=" and tk.at(a + 2) != "=" and a + 2 <= b:
            args[tk.text[a]] = _value(tk, a + 2, b)
        else:
            args["value"] = _value(tk, a, b)
    return args
