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


_JSX_PREV_WORDS = {"return", "default", "yield", "await", "case", "else"}


def scan(lines: List[str]) -> Tuple[List[str], List[Tuple[str, ...]], bool]:
    """Scan with JSX awareness; fall back to a JSX-free scan if an element never closes
    (e.g. a TS `<T>x` cast read as JSX), so a misread can't swallow the rest of the file."""
    res = _scan(lines, True)
    if res[3]:
        res = _scan(lines, False)
    return res[0], res[1], res[2]


def _scan(lines: List[str], jsx_on: bool):
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
    jsx: List[list] = []  # [stack depth, 'tag'|'text', closing, last non-space char]
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
        if state in ("ja", "jb"):
            cur.append(ch)
            if ch == '"' and state == "ja" or ch == "'" and state == "jb":
                state = "n"
            i += 1
            continue
        mode = jsx[-1][1] if jsx and jsx[-1][0] == len(stack) else ""
        if mode == "text":
            nxt = text[i + 1] if i + 1 < n else ""
            if ch == "<" and nxt == "/":
                jsx.append([len(stack), "tag", True, ""])
                cur.append("</")
                i += 2
            elif ch == "<" and (nxt.isalpha() or nxt in "_$>"):
                jsx.append([len(stack), "tag", False, ""])
                cur.append(ch)
                i += 1
            elif ch == "{":
                stack.append("{")
                cur.append(ch)
                last_sig = "{"
                i += 1
            else:
                cur.append(ch)
                i += 1
            continue
        if mode == "tag":
            tag = jsx[-1]
            if ch in "\"'":
                state = "ja" if ch == '"' else "jb"
                cur.append(ch)
            elif ch == "{":
                stack.append("{")
                cur.append(ch)
                last_sig = "{"
            elif ch == ">":
                jsx.pop()
                cur.append(ch)
                last_sig = "a"
                if tag[2]:
                    if jsx and jsx[-1][1] == "text" and jsx[-1][0] == len(stack):
                        jsx.pop()
                elif tag[3] != "/" and not text.startswith("(", i + 1):  # `<T>(x)` is a generic
                    jsx.append([len(stack), "text", False, ""])
            elif text.startswith("//", i):
                state = "lc"
                i += 2
                continue
            elif text.startswith("/*", i):
                state = "bc"
                i += 2
                continue
            else:
                cur.append(ch)
                if not ch.isspace():
                    tag[3] = ch
            i += 1
            continue
        # normal state
        if jsx_on and ch == "<" and i + 1 < n and (text[i + 1].isalpha() or text[i + 1] in "_$>") and (
                last_sig in _REGEX_PREV or last_sig == "" or prev_word in _JSX_PREV_WORDS
                or (last_sig == ">" and text[:i].rstrip().endswith("=>"))):
            jsx.append([len(stack), "tag", False, ""])
            cur.append(ch)
            i += 1
            continue
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
    return out, stacks[: len(out)], not stack, bool(jsx)
