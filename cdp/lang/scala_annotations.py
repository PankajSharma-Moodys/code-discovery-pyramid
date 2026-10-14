"""Scala annotation arguments in `annotation_args.py`'s row shape.

`@Every(jobName = "X", value = "60s", misfirePolicy = MisfirePolicy.NOW)` becomes
`{"jobName": "X", "value": "60s", "misfirePolicy": {"ref": "MisfirePolicy.NOW"}}`, exactly as for
Java. What differs is Scala's spelling of the same values:

  Array(a, b) / Seq(..) / List(..) / Array[T](..)  -> list
  classOf[T]                                       -> {"class": "T"}
  new Ann(k = v)                                   -> nested annotation row
  `type` = ..                                      -> key "type" (backticks dropped by the tokenizer)
  "a" + B + "b"                                    -> string / {"concat": [...]} (as Java)

A single unnamed argument is stored under `value`. Nothing here evaluates or resolves.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from .annotation_args import _lit, _number, _plus_ranges, _split
from .base import Ann, annotation_rows
from .java_decl import join_tokens
from .java_tokens import Tokens
from .scala_tokens import string_value

LIST_FUNCS = frozenset(["Array", "Seq", "List", "Vector", "Set", "IndexedSeq"])
STRIP_SUFFIXES = (".stripMargin", ".trim", ".stripLineEnd", ".stripLeading", ".stripTrailing")


def strip_margin(s: str) -> str:
    return "\n".join(re.sub(r"^\s*\|", "", ln) for ln in s.split("\n"))


def _margined(v: Any) -> Any:
    """`.stripMargin` applied to an annotation value: a string, or the string parts of a concat. Like
    `scala_emit`'s constants it covers the whole expression, so a margin on only the last operand of a
    `+` chain is approximate."""
    if isinstance(v, str):
        return strip_margin(v)
    if isinstance(v, dict) and isinstance(v.get("concat"), list):
        return {"concat": [strip_margin(p) if isinstance(p, str) else p for p in v["concat"]]}
    return v


def skip_annotation(tk: Tokens, j: int) -> int:
    """Index past the annotation starting at the `@` at `j` (`@a.B[T](x)(y)`)."""
    j += 1
    while tk.is_id(j):
        j += 1
        if tk.at(j) == "." and tk.is_id(j + 1):
            j += 1
            continue
        break
    if tk.at(j) == "[":
        j = tk.close(j) + 1
    if tk.at(j) == "(":
        j = tk.close(j) + 1
    return j


def annotation_name(tk: Tokens, i: int) -> Tuple[str, int]:
    """(simple name, index after the dotted name) of the annotation at the `@` at `i`."""
    name = tk.text[i + 1]
    j = i + 2
    while tk.at(j) == "." and tk.is_id(j + 1):
        name = tk.text[j + 1]
        j += 2
    return name, j


def make_ann(tk: Tokens, i: int) -> Tuple[Ann, int]:
    name, _ = annotation_name(tk, i)
    k = skip_annotation(tk, i)
    return Ann(name, join_tokens(tk, i, k), tk.line[i], tk.line[k - 1], annotation_args(tk, i, k)), k


def _dotted(tk: Tokens, a: int, b: int) -> Optional[str]:
    """`A.b.C` over [a, b) or None."""
    if a >= b or not tk.is_id(a):
        return None
    parts = [tk.text[a]]
    i = a + 1
    while i + 1 < b and tk.text[i] == "." and tk.is_id(i + 1):
        parts.append(tk.text[i + 1])
        i += 2
    return ".".join(parts) if i == b else None


def _operand(tk: Tokens, a: int, b: int) -> Optional[Any]:
    if a >= b:
        return None
    neg = False
    if tk.text[a] == "-" and tk.kind[a] == "op":
        neg, a = True, a + 1
        if a >= b:
            return None
    k, t = tk.kind[a], tk.text[a]
    if b - a == 1:
        if k == "str":
            s = string_value(t)
            return None if neg or s is None else s
        if k == "chr":
            return None if neg else t[1:-1]
        if k == "num":
            v = _number(t)
            return None if v is None else (-v if neg else v)
        if k == "id" and not neg:
            return t == "true" if t in ("true", "false") else {"ref": t}
        return None
    if neg:
        return None
    if k == "id" and t == "classOf" and tk.at(a + 1) == "[" and tk.close(a + 1) == b - 1:
        inner = _dotted(tk, a + 2, tk.close(a + 1))
        if inner is None:
            gen = tk.close(a + 1)
            # `classOf[Foo[Bar]]`: the raw class only
            inner = tk.text[a + 2] if a + 2 < gen and tk.is_id(a + 2) else None
        return {"class": inner} if inner else None
    d = _dotted(tk, a, b)
    return {"ref": d} if d else None


def _value(tk: Tokens, a: int, b: int) -> Any:
    """An annotation argument's value; a trailing `.stripMargin`/`.trim` is peeled off and applied last."""
    margin = False
    while b - 2 > a and tk.kind[b - 1] == "id" and tk.text[b - 2] == "." and "." + tk.text[b - 1] in STRIP_SUFFIXES:
        margin = margin or tk.text[b - 1] == "stripMargin"
        b -= 2
    v = _value_core(tk, a, b)
    return _margined(v) if margin else v


def _value_core(tk: Tokens, a: int, b: int) -> Any:
    if a >= b:
        return {"text": ""}
    while tk.text[a] == "(" and tk.kind[a] == "op" and tk.close(a) == b - 1 and b - a > 2:
        a, b = a + 1, b - 1
    if tk.kind[a] == "op" and tk.text[a] == "@":
        end = skip_annotation(tk, a)
        if end == b:
            return _nested(tk, a, end)
    # `new Ann(..)` -> nested annotation row
    if tk.text[a] == "new" and tk.is_id(a + 1):
        j = a + 2
        name = tk.text[a + 1]
        while tk.at(j) == "." and tk.is_id(j + 1):
            name = tk.text[j + 1]
            j += 2
        if tk.at(j) == "[":
            j = tk.close(j) + 1
        if j == b or (tk.at(j) == "(" and tk.close(j) == b - 1):
            return _nested_new(tk, a, name, j, b)
    # `Array(..)` / `Seq[T](..)` -> list
    if tk.kind[a] == "id" and tk.text[a] in LIST_FUNCS:
        j = a + 1
        if tk.at(j) == "[":
            j = tk.close(j) + 1
        if tk.at(j) == "(" and tk.close(j) == b - 1:
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
        if any(isinstance(o, str) for o in ops):
            return "".join(_lit(o) for o in ops)
        return {"text": join_tokens(tk, a, b)}
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


def _args_in(tk: Tokens, open_i: int, close_i: int) -> Dict[str, Any]:
    args: Dict[str, Any] = {}
    for a, b in _split(tk, open_i + 1, close_i):
        if tk.is_id(a) and tk.at(a + 1) == "=" and tk.at(a + 2) != "=" and a + 2 <= b:
            args[tk.text[a]] = _value(tk, a + 2, b)
        else:
            args["value"] = _value(tk, a, b)
    return args


def _nested(tk: Tokens, i: int, end: int) -> Dict:
    name, _ = annotation_name(tk, i)
    ann = Ann(name, join_tokens(tk, i, end), tk.line[i], tk.line[end - 1], annotation_args(tk, i, end))
    return annotation_rows([ann])[0]


def _nested_new(tk: Tokens, a: int, name: str, j: int, b: int) -> Dict:
    args = _args_in(tk, j, b - 1) if tk.at(j) == "(" else {}
    ann = Ann(name, join_tokens(tk, a, b), tk.line[a], tk.line[b - 1], args)
    return annotation_rows([ann])[0]


def annotation_args(tk: Tokens, i: int, end: int) -> Dict[str, Any]:
    """`args` of the annotation at the `@` at `i` (spanning tokens `[i, end)`); `{}` without any."""
    _, j = annotation_name(tk, i)
    if tk.at(j) == "[":
        j = tk.close(j) + 1
    if tk.at(j) != "(" or tk.close(j) >= end:
        return {}
    return _args_in(tk, j, tk.close(j))
