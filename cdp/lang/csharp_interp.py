"""The expression holes of a C# interpolated string token (`$"a {Foo(x):N2} b"`)."""

from __future__ import annotations

from typing import List, Tuple


def holes(text: str) -> List[Tuple[str, int]]:
    """(expression text, newlines before it) for every `{expr}` of an interpolated string literal.
    `{{` is a literal brace; a `:format` or `,alignment` tail at the hole's top level is dropped."""
    s = text
    q = s.find('"')
    if q < 0 or "$" not in s[:q]:
        return []
    verbatim = "@" in s[:q]
    raw = s.startswith('"""', q)
    out: List[Tuple[str, int]] = []
    i = q + (3 if raw else 1)
    end = len(s) - (3 if raw else 1)
    while i < end:
        c = s[i]
        if c == "\\" and not verbatim and not raw:
            i += 2
            continue
        if c == "{":
            if s[i + 1:i + 2] == "{":
                i += 2
                continue
            j, depth = i + 1, 0
            while j < end:
                d = s[j]
                if d in "([{":
                    depth += 1
                elif d in ")]":
                    depth -= 1
                elif d == "}":
                    if depth == 0:
                        break
                    depth -= 1
                elif d == '"':
                    j += 1
                    while j < end and s[j] != '"':
                        j += 2 if s[j] == "\\" else 1
                elif d == "'" and s[j + 2:j + 3] == "'":
                    j += 2
                j += 1
            body = s[i + 1:j]
            cut, depth = len(body), 0
            for k, d in enumerate(body):
                if d in "([{":
                    depth += 1
                elif d in ")]}":
                    depth -= 1
                elif d in ":," and depth == 0 and body[k:k + 2] != "::":
                    cut = k
                    break
            expr = body[:cut]
            if expr.strip():
                out.append((expr, s.count("\n", 0, i + 1)))
            i = j + 1
            continue
        i += 1
    return out
