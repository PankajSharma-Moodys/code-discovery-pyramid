"""C# tokens: `java_tokens.Tokens` with C# lexical rules.

Verbatim (`@"..."`), interpolated (`$"..."`, `$@"..."`) and raw (triple-quoted) strings are one
`str` token each; preprocessor lines (`#region`, `#if`) and comments are dropped. `>` is always a
token of its own (generics close with runs of it); `=>`, `?.`, `??` and `::` are kept whole.
"""

from __future__ import annotations

import re
from typing import Optional

from .java_tokens import Tokens

TOKEN_RE = re.compile(
    r"(?P<pp>(?<![^\n])[ \t]*\#[^\n]*)"
    r"|(?P<ws>[ \t\r\f]+|\n)"
    r"|(?P<lc>//[^\n]*)"
    r"|(?P<bc>/\*.*?\*/)"
    r'|(?P<str>[$@]*"""(?:.|\n)*?"""|[$]?@[$]?"(?:[^"]|"")*"|\$"(?:\\.|[^"\\\n])*"|"(?:\\.|[^"\\\n])*")'
    r"|(?P<chr>'(?:\\.|[^'\\\n])*')"
    r"|(?P<id>@?[^\W\d]\w*)"
    r"|(?P<num>\d[\w.]*)"
    r"|(?P<op>=>|\?\.|\?\?=?|::|\.\.|.)",
    re.S,
)


class CsTokens(Tokens):
    __slots__ = ()
    REGEX = TOKEN_RE
    DROP = ("ws", "lc", "bc", "pp")

    def __init__(self, lines):
        super().__init__(lines)
        # `@class` is the identifier `class`
        for i, t in enumerate(self.text):
            if self.kind[i] == "id" and t.startswith("@"):
                self.text[i] = t[1:]
        # a `str` token spanning lines must advance the row counter: handled by Tokens for
        # DROP kinds only, so recount here from the raw text
        self._fix_lines(lines)

    def _fix_lines(self, lines) -> None:
        source = "\n".join(lines)
        row = 0
        idx = 0
        for m in self.REGEX.finditer(source):
            k = m.lastgroup
            t = m.group()
            if k in self.DROP:
                row += t.count("\n")
                continue
            self.line[idx] = row
            idx += 1
            row += t.count("\n")


def string_value(text: str) -> Optional[str]:
    """The literal a `str` token denotes, or None when it interpolates."""
    t = text
    if t.startswith('"""') or (t.lstrip("$@").startswith('"""')):
        body = t.lstrip("$@")
        if t.startswith("$") and "{" in body:
            return None
        return body[3:-3].strip("\n")
    interp = "$" in t[:3]
    verbatim = "@" in t[:3]
    body = t[t.index('"') + 1:-1]
    if interp and ("{" in body.replace("{{", "")):
        return None
    if interp:
        body = body.replace("{{", "{").replace("}}", "}")
    if verbatim:
        return body.replace('""', '"')
    return re.sub(r"\\(.)", lambda m: {"n": "\n", "t": "\t", "r": "\r", "0": "\0"}.get(m.group(1), m.group(1)), body)
