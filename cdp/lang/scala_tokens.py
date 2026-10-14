"""Scala tokens: `java_tokens.Tokens` with Scala lexical rules.

Triple-quoted strings (`\"\"\"..\"\"\"`) and interpolated strings (`s"..."`, `f"..."`, `raw"..."`,
`s\"\"\"..\"\"\"`) are one `str` token each; backtick identifiers are one `id` token (backticks
removed); comments are dropped (block comments nest, to 8 levels; an unterminated one runs to EOF). `>` is always a token of its
own; `=>`, `<-`, `->`, `::`, `<:`, `>:` are kept whole. A `'x'` char literal is a `chr` token.
Brackets `( ) [ ] { }` pair as in Java, so `[T]` type arguments are skipped with `close`.
"""

from __future__ import annotations

import re
from typing import Optional

from .java_tokens import Tokens

# an interpolation hole may hold strings and one level of braces: `${xs.mkString(",")}`
_HOLE = r"""\$\{(?:[^{}"]|"(?:\\.|[^"\\])*"|\{[^{}]*\})*\}"""

# Scala block comments nest; `re` has no recursion, so unroll the nesting to a fixed depth.
_BC = r"/\*(?:[^*/]|\*(?!/)|/(?!\*))*\*/"
for _ in range(7):
    _BC = r"/\*(?:[^*/]|\*(?!/)|/(?!\*)|" + _BC + r")*\*/"
_BC += r"|/\*.*\Z"  # unterminated: comment to end of file

TOKEN_RE = re.compile(
    r"(?P<ws>\s+)"
    r"|(?P<lc>//[^\n]*)"
    r"|(?P<bc>" + _BC + r")"
    r'|(?P<str>(?<![\w$])(?:[A-Za-z_]\w*)?"""(?:.|\n)*?"""+'
    r'|(?<![\w$])[A-Za-z_]\w*"(?:' + _HOLE + r'|\\.|[^"\\\n])*"'
    r'|"(?:\\.|[^"\\\n])*")'
    r"|(?P<chr>'(?:\\.|\\u[0-9a-fA-F]{4}|[^'\\\n])')"
    r"|(?P<id>`[^`\n]+`|[A-Za-z_$][\w$]*)"
    r"|(?P<num>\d[\w.]*)"
    r"|(?P<op>=>|<-|->|::|<:|>:|.)",
    re.S,
)


class ScTokens(Tokens):
    __slots__ = ()
    REGEX = TOKEN_RE
    DROP = ("ws", "lc", "bc")

    def __init__(self, lines):
        super().__init__(lines)
        for i, t in enumerate(self.text):
            if self.kind[i] == "id" and t.startswith("`"):
                self.text[i] = t[1:-1]
        self._fix_lines(lines)

    def _fix_lines(self, lines) -> None:
        # a `str` token that spans lines must advance the row counter
        source = "\n".join(lines)
        row = 0
        idx = 0
        for m in self.REGEX.finditer(source):
            t = m.group()
            if m.lastgroup in self.DROP:
                row += t.count("\n")
                continue
            self.line[idx] = row
            idx += 1
            row += t.count("\n")


def string_value(text: str) -> Optional[str]:
    """The literal a `str` token denotes; None when it interpolates (`s"..$x"`)."""
    q = text.find('"')
    if q < 0:
        return None
    prefix, body = text[:q], text[q:]
    if body.startswith('"""'):
        inner = body[3:]
        inner = inner[: len(inner) - 3] if inner.endswith('"""') else inner
        raw = inner
        if prefix in ("s", "f") and re.search(r"\$[\w{$]", raw):
            return None
        return raw
    inner = body[1:-1]
    if prefix in ("s", "f") and re.search(r"\$[\w{]", inner.replace("$$", "")):
        return None
    if prefix == "raw":
        return inner
    return re.sub(r"\\(.)", lambda m: {"n": "\n", "t": "\t", "r": "\r", "b": "\b", "f": "\f", "0": "\0"}
                  .get(m.group(1), m.group(1)), inner)
