"""Java tokens with line numbers and bracket matching.

The line-regex extractor this replaces could not see a method whose modifiers
sat on another line, a call chained across lines, or a lambda. A token stream
reads those the way the compiler does, and it is what `java_decl` and
`java_body` walk. Comments are dropped; string, text-block and char literals are
single tokens, so a brace or a dot inside one never counts.

`>` is always a token of its own (never `>>`), because generics close with runs
of it. Callers that need a shift operator never do: nothing here evaluates
expressions.
"""

from __future__ import annotations

import re
from typing import List, Optional

TOKEN_RE = re.compile(
    r"(?P<ws>\s+)"
    r"|(?P<lc>//[^\n]*)"
    r"|(?P<bc>/\*.*?\*/)"
    r'|(?P<tb>"""(?:\\.|[^\\])*?""")'
    r'|(?P<str>"(?:\\.|[^"\\\n])*")'
    r"|(?P<chr>'(?:\\.|[^'\\\n])*')"
    r"|(?P<id>[A-Za-z_$][\w$]*)"
    r"|(?P<num>\d[\w.]*)"
    r"|(?P<op>->|::|\.\.\.|.)",
    re.S,
)

OPEN = {"(": ")", "[": "]", "{": "}"}


class Tokens:
    """Parallel arrays: `kind[i]` in id/num/str/chr/op, `text[i]`, `line[i]` (0-based)."""

    __slots__ = ("kind", "text", "line", "match", "n")
    REGEX = TOKEN_RE
    DROP = ("ws", "lc", "bc", "tb")

    def __init__(self, lines: List[str]) -> None:
        self.kind: List[str] = []
        self.text: List[str] = []
        self.line: List[int] = []
        source = "\n".join(lines)
        row = 0
        for m in self.REGEX.finditer(source):
            k = m.lastgroup
            t = m.group()
            if k in self.DROP:
                if "\n" in t:
                    if k == "tb":
                        self.kind.append("str")
                        self.text.append(t)
                        self.line.append(row)
                    row += t.count("\n")
                    continue
                if k == "tb":
                    self.kind.append("str")
                    self.text.append(t)
                    self.line.append(row)
                continue
            self.kind.append(k)
            self.text.append(t)
            self.line.append(row)
        self.n = len(self.text)
        self.match = self._pair()

    def _pair(self) -> List[int]:
        match = [-1] * self.n
        stack: List[int] = []
        for i, (k, t) in enumerate(zip(self.kind, self.text)):
            if k != "op":
                continue
            if t in OPEN:
                stack.append(i)
            elif t in (")", "]", "}"):
                # Pop to the nearest opener of the same family; a stray closer
                # (macro-ish or truncated source) never poisons later pairs.
                for j in range(len(stack) - 1, -1, -1):
                    if OPEN[self.text[stack[j]]] == t:
                        match[stack[j]] = i
                        match[i] = stack[j]
                        del stack[j:]
                        break
        return match

    def close(self, i: int) -> int:
        """Index of the bracket closing the one at `i`, or the last token."""
        j = self.match[i] if 0 <= i < self.n else -1
        return j if j > i else self.n - 1

    def is_id(self, i: int) -> bool:
        return 0 <= i < self.n and self.kind[i] == "id"

    def at(self, i: int) -> str:
        return self.text[i] if 0 <= i < self.n else ""

    def skip_angle(self, i: int) -> Optional[int]:
        """Index just past the `<...>` opening at `i`, or None if it is not a
        type-argument list (a comparison, say)."""
        depth = 0
        j = i
        while j < self.n:
            t = self.text[j]
            k = self.kind[j]
            if k == "op":
                if t == "<":
                    depth += 1
                elif t == ">":
                    depth -= 1
                    if depth == 0:
                        return j + 1
                elif t in (";", "{", "}", "=", "|", "!", "+", "-", "*", "/", "%", "(", ")"):
                    if t == "(" or t == ")":
                        return None
                    return None
                # `?`, `,`, `.`, `&`, `[`, `]`, `@` are all legal inside
            elif k in ("str", "chr", "num"):
                return None
            j += 1
            if j - i > 200:
                return None
        return None
