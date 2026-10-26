"""C# attribute arguments in `annotation_args.py`'s row shape (ECMA-334 "Attributes": positional
and named arguments).

`[Foo("a", 3, Name = X.Y, Types = new[] { typeof(T) })]` becomes
`{"value": "a", "value_2": 3, "Name": {"ref": "X.Y"}, "Types": [{"class": "T"}]}`. As for Java and
Scala, a named argument is stored under its name (`Name = v` and `Name: v` alike) and the first
positional argument under `value`; C# also allows several positional arguments, so the next ones
are `value_2`, `value_3`, ... (Java and Scala have no second unnamed argument).

  "s" / @"s" / $"s" / raw triple-quoted -> string (interpolation holes: {"text": src})
  'c'                               -> one-character string
  12, 0x1F, 1_000, 2.5f, 10UL       -> number;  true / false -> bool
  null, default(T), (int)x, a | b   -> {"text": src}
  typeof(T)                         -> {"class": "T"}
  nameof(A.B)                       -> "B" (the compile-time string)
  E.A, Consts.X                     -> {"ref": "E.A"}
  "a" + B + "b"                     -> string / {"concat": [...]} (as Java)
  new[] { .. } / new T[] { .. } / [a, b] -> list

Nothing here evaluates or resolves names. An attribute without parentheses has no `args`; the
caller adds `{}` for empty parentheses (`annotation_rows` drops an empty map).
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from .annotation_args import _lit, _plus_ranges, _split
from .java_decl import join_tokens
from .java_tokens import Tokens

_ESC = {"'": "'", '"': '"', "\\": "\\", "0": "\0", "a": "\a", "b": "\b", "f": "\f",
        "n": "\n", "r": "\r", "t": "\t", "v": "\v"}
_ESC_RE = re.compile(r"\\(u[0-9a-fA-F]{4}|U[0-9a-fA-F]{8}|x[0-9a-fA-F]{1,4}|.)", re.S)
_INT_RE = re.compile(r"(0[xX][0-9a-fA-F]+|0[bB][01]+|\d+)([uU]?[lL]?|[lL][uU])")
_FLT_RE = re.compile(r"(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?([fFdDmM]?)")


def _unescape(s: str) -> str:
    def sub(m):
        e = m.group(1)
        if e[0] in "uUx" and len(e) > 1:
            try:
                return chr(int(e[1:], 16))
            except (ValueError, OverflowError):
                return m.group(0)
        return _ESC.get(e, m.group(0))
    return _ESC_RE.sub(sub, s)


def _raw_string(t: str) -> str:
    n = len(t) - len(t.lstrip("$@"))
    body = t[n:]
    q = len(body) - len(body.lstrip('"'))
    body = body[q:-q]
    if "\n" not in body:
        return body
    lines = body.split("\n")
    if not lines[0].strip():
        lines = lines[1:]
    indent = ""
    if lines and not lines[-1].strip():
        indent = lines[-1]
        lines = lines[:-1]
    return "\n".join(l[len(indent):] if l.startswith(indent) else l for l in lines)


def _string(t: str) -> Optional[str]:
    """The literal a `str` token denotes; None when it interpolates."""
    head = t[:len(t) - len(t.lstrip("$@"))]
    interp = "$" in head
    if t[len(head):].startswith('"""'):
        if interp and re.search(r"(?<!\{)\{(?!\{)", t):
            return None
        return _raw_string(t)
    body = t[len(head) + 1:-1]
    if interp:
        if "{" in body.replace("{{", ""):
            return None
        body = body.replace("{{", "{").replace("}}", "}")
    if "@" in head:
        return body.replace('""', '"')
    return _unescape(body)


def _number(t: str) -> Optional[Any]:
    s = t.replace("_", "")
    m = _INT_RE.fullmatch(s)
    if m:
        return int(m.group(1), 0)
    m = _FLT_RE.fullmatch(s)
    if m and (m.group(2) or m.group(3) or "." in m.group(1)):
        try:
            return float(m.group(1) + (m.group(2) or ""))
        except ValueError:
            return None
    if re.fullmatch(r"\d+[mM]", s):
        return float(s[:-1])
    return None


def _operand(tk: Tokens, a: int, b: int) -> Optional[Any]:
    """One operand of a `+` chain; None when it is not a literal, constant, `nameof` or `typeof`."""
    if a >= b:
        return None
    neg = False
    if tk.kind[a] == "op" and tk.text[a] == "-":
        neg, a = True, a + 1
        if a >= b:
            return None
    k, t = tk.kind[a], tk.text[a]
    if b - a == 1:
        if k == "str":
            return None if neg else _string(t)
        if k == "chr":
            return None if neg else _unescape(t[1:-1])
        if k == "num":
            v = _number(t)
            return None if v is None else (-v if neg else v)
        if k == "id" and not neg:
            if t in ("true", "false"):
                return t == "true"
            if t == "null":
                return None
            return {"ref": t}
        return None
    if neg or k != "id":
        return None
    if t in ("typeof", "nameof") and tk.at(a + 1) == "(" and tk.close(a + 1) == b - 1 and b - a > 3:
        inner = join_tokens(tk, a + 2, b - 1)
        if t == "typeof":
            return {"class": inner}
        ids = [tk.text[i] for i in range(a + 2, b - 1) if tk.kind[i] == "id"]
        depth_ok = "<" not in inner
        if depth_ok and ids and all(tk.kind[i] == "id" or tk.text[i] == "." for i in range(a + 2, b - 1)):
            return ids[-1]
        return None
    parts = [t]
    i = a + 1
    while i + 1 < b and tk.text[i] == "." and tk.kind[i + 1] == "id":
        parts.append(tk.text[i + 1])
        i += 2
    if i != b:
        return None
    return {"ref": ".".join(parts)}


def _value(tk: Tokens, a: int, b: int) -> Any:
    if a >= b:
        return {"text": ""}
    while tk.kind[a] == "op" and tk.text[a] == "(" and tk.close(a) == b - 1 and b - a > 2:
        a, b = a + 1, b - 1                                  # (A + B)
    if tk.kind[a] == "op" and tk.text[a] == "[" and tk.close(a) == b - 1:
        return [_value(tk, s, e) for s, e in _split(tk, a + 1, b - 1)]   # collection expression
    if tk.text[a] == "new" and tk.kind[a] == "id":           # new[] { .. } / new T[] { .. } / new T[n] { .. }
        j = a + 1
        while j < b and tk.text[j] != "{":
            if tk.kind[j] == "op" and tk.text[j] in "([":
                j = tk.close(j)
            j += 1
        if j < b and tk.text[j] == "{" and tk.close(j) == b - 1 and "[" in tk.text[a + 1:j]:
            return [_value(tk, s, e) for s, e in _split(tk, j + 1, b - 1)]
    ranges = _plus_ranges(tk, a, b)
    ops = [_operand(tk, s, e) for s, e in ranges]
    if any(o is None for o in ops):
        return {"text": join_tokens(tk, a, b)}
    if len(ops) == 1:
        return ops[0]
    for o in ops:
        if isinstance(o, dict) and "class" in o:
            return {"text": join_tokens(tk, a, b)}
    if not any(isinstance(o, dict) for o in ops):
        if any(isinstance(o, str) for o in ops):             # all literals: the compiler folds it
            return "".join(_lit(o) for o in ops)
        return {"text": join_tokens(tk, a, b)}               # numeric sum: not a name to keep
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


def name_end(tk: Tokens, a: int, end: int) -> int:
    """Index after the attribute name at `a`: `A.B`, `global::A.B`, `A<int>`; `a` when none."""
    j = a
    while j < end and tk.is_id(j):
        j += 1
        if tk.at(j) == "<":
            depth = 0
            while j < end:
                t = tk.text[j]
                if tk.kind[j] == "op" and t in "([{":
                    j = tk.close(j)
                elif t == "<":
                    depth += 1
                elif t == ">":
                    depth -= 1
                    if depth == 0:
                        j += 1
                        break
                j += 1
        if tk.at(j) in (".", "::") and tk.is_id(j + 1):
            j += 1
            continue
        break
    return j


def attribute_args(tk: Tokens, a: int, end: int) -> Optional[Dict[str, Any]]:
    """`args` of the attribute spanning tokens `[a, end)`; None without parentheses, `{}` for `()`."""
    j = name_end(tk, a, end)
    if j >= end or tk.at(j) != "(" or tk.close(j) >= end:
        return None
    args: Dict[str, Any] = {}
    pos = 0
    for s, e in _split(tk, j + 1, tk.close(j)):
        if tk.is_id(s) and e > s + 2 and (
                (tk.at(s + 1) == "=" and tk.at(s + 2) != "=") or tk.at(s + 1) == ":"):
            args[tk.text[s]] = _value(tk, s + 2, e)
        else:
            args["value" if pos == 0 else "value_%d" % (pos + 1)] = _value(tk, s, e)
            pos += 1
    return args


def qualified_name(tk: Tokens, a: int, end: int) -> str:
    """The attribute name as written (`A.B`, generic arguments dropped, `global::` kept)."""
    j = name_end(tk, a, end)
    out = ""
    i = a
    while i < j:
        t = tk.text[i]
        if t == "<" and tk.kind[i] == "op":
            depth = 0
            while i < j:
                if tk.text[i] == "<":
                    depth += 1
                elif tk.text[i] == ">":
                    depth -= 1
                    if depth == 0:
                        break
                i += 1
        else:
            out += t
        i += 1
    return out
