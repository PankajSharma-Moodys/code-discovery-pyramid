"""Lexical scan of a JS/TS file: comments removed, bracket nesting per line.

Not a parser. It knows strings, template literals (with `${}` nesting), comments and
simple regex literals, which is enough to say "this line starts at the top level" or
"directly inside a top-level class body" without being fooled by braces in strings.
"""

from __future__ import annotations

import re
from typing import List, Tuple

_WORD = re.compile(r"[A-Za-z_$][\w$]*")
_REGEX_PREV = set("(,=:[!&|?{;+-*%~^")   # no '<': `</Route>` is a JSX close tag, not a regex


def scan(lines: List[str]) -> Tuple[List[str], List[Tuple[str, ...]], bool]:
    """Return (code_lines, stack_at_line_start, balanced).

    `code_lines[i]` is line i with comments blanked (string contents kept).
    `stack_at_line_start[i]` holds one entry per open bracket: 'c' class body, '{', '(', '[',
    't' (a `${` inside a template). `balanced` is False when the file ends with open brackets.
    """
    text = "\n".join(lines)
    n = len(text)
    out: List[str] = []
    stacks: List[Tuple[str, ...]] = [()]
    stack: List[str] = []
    pending_class = -1
    state = "n"          # n normal, s ' string, d " string, t template, lc line comment, bc block comment
    i = 0
    last_sig = ""        # last significant char in normal state (regex-vs-divide heuristic)
    cur: List[str] = []
    prev_word = ""
    while i < n:
        ch = text[i]
        if ch == "\n":
            out.append("".join(cur))
            cur = []
            stacks.append(tuple(stack))
            if state in ("s", "d", "lc"):
                state = "n"
            i += 1
            continue
        if state == "lc":
            i += 1
            continue
        if state == "bc":
            if text.startswith("*/", i):
                state = "n"
                i += 2
            else:
                i += 1
            continue
        if state in ("s", "d"):
            cur.append(ch)
            if ch == "\\" and i + 1 < n and text[i + 1] != "\n":
                cur.append(text[i + 1])
                i += 2
                continue
            if (ch == "'" and state == "s") or (ch == '"' and state == "d"):
                state = "n"
                last_sig = "a"
            i += 1
            continue
        if state == "t":
            cur.append(ch)
            if ch == "\\" and i + 1 < n and text[i + 1] != "\n":
                cur.append(text[i + 1])
                i += 2
                continue
            if ch == "`":
                state = "n"
                last_sig = "a"
            elif ch == "$" and text.startswith("{", i + 1):
                cur.append("{")
                stack.append("t")
                state = "n"
                last_sig = "{"
                i += 2
                continue
            i += 1
            continue
        # normal state
        if text.startswith("//", i):
            state = "lc"
            i += 2
            continue
        if text.startswith("/*", i):
            state = "bc"
            i += 2
            continue
        if ch in "'\"`":
            state = {"'": "s", '"': "d", "`": "t"}[ch]
            cur.append(ch)
            i += 1
            continue
        if ch == "/" and (last_sig in _REGEX_PREV or last_sig == ""):
            j, in_cls = i + 1, False
            while j < n and text[j] != "\n":
                c = text[j]
                if c == "\\":
                    j += 2
                    continue
                if c == "[":
                    in_cls = True
                elif c == "]":
                    in_cls = False
                elif c == "/" and not in_cls:
                    break
                j += 1
            if j < n and text[j] == "/":
                cur.append(text[i:j + 1])
                i = j + 1
                last_sig = "a"
                continue
        if ch.isalpha() or ch in "_$":
            m = _WORD.match(text, i)
            word = m.group(0)
            if word == "class" and prev_word != "." and (not cur or cur[-1] != "."):
                pending_class = len(stack)
            cur.append(word)
            i = m.end()
            last_sig = "a"
            prev_word = word
            continue
        if ch in "([":
            stack.append(ch)
        elif ch == "{":
            if pending_class == len(stack):
                stack.append("c")
                pending_class = -1
            else:
                stack.append("{")
        elif ch in ")]}":
            if stack:
                top = stack.pop()
                if top == "t" and ch == "}":
                    cur.append(ch)
                    state = "t"
                    i += 1
                    continue
        elif ch == ";" and pending_class == len(stack):
            pending_class = -1
        cur.append(ch)
        if not ch.isspace():
            last_sig = ch
            prev_word = "." if ch == "." else ""
        i += 1
    out.append("".join(cur))
    while len(stacks) < len(out):
        stacks.append(tuple(stack))
    return out, stacks[: len(out)], not stack
