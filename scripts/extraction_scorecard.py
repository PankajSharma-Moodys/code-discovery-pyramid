#!/usr/bin/env python3
"""Extraction scorecard (task X0): implements sections 2-7 of EXTRACTION_METRICS.md.

    python3 scripts/extraction_scorecard.py            # scores every repo in REPOS under ~/git

Writes SCORECARD.md and scorecard.json in the repo root. Measures only: it never changes cdp/ or the
scanned repos. Facts come the way a real scan does (build_inventory, run_extract, rules.apply); H3 is
read from ~/.cdp/index.db opened read-only. Present rules are text checks over the blanked source
(strings/comments removed); they are approximate by design (spec section 3) and misses are listed.
"""
from __future__ import annotations

import argparse
import bisect
import collections
import json
import os
import random
import re
import sqlite3
import subprocess
import sys
import time
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("CDP_HOME", str(Path.home() / ".cdp-phase1" / "x0"))

LANGS = ["java", "csharp", "scala", "python", "typescript", "javascript"]
PROVISIONAL = {"python", "typescript", "javascript"}
REPOS = ["data-lake", "unified-store", "workflow-service", "dispatch", "CTFd"]
PASS_MARK = {"S": 95, "G": 95, "M": 95, "R": 95, "U": 95, "F": 90}
MEMBER_KINDS = {"method", "function", "field", "constant", "table"}
SEED = 20261026
MAX_MISSES = 5

# ---------------------------------------------------------------- blanking (strings/comments -> spaces)


def blank(text: str, lang: str) -> str:
    """Same-length text with comments and string/char literal contents replaced by spaces."""
    out = list(text)
    n = len(text)
    i = 0
    py = lang == "python"
    js = lang in ("javascript", "typescript")
    cs = lang == "csharp"
    scala = lang == "scala"
    java = lang == "java"

    def wipe(a, b):
        for k in range(a, min(b, n)):
            if out[k] != "\n":
                out[k] = " "

    while i < n:
        c = text[i]
        two = text[i:i + 2]
        if py and c == "#":
            j = text.find("\n", i)
            j = n if j < 0 else j
            wipe(i, j)
            i = j
            continue
        if not py and two == "//":
            j = text.find("\n", i)
            j = n if j < 0 else j
            wipe(i, j)
            i = j
            continue
        if not py and two == "/*":
            depth = 1
            j = i + 2
            while j < n and depth:
                if text[j:j + 2] == "/*" and scala:
                    depth += 1
                    j += 2
                elif text[j:j + 2] == "*/":
                    depth -= 1
                    j += 2
                else:
                    j += 1
            wipe(i, j)
            i = j
            continue
        # triple-quoted (java/scala text blocks, python docstrings, c# raw strings)
        if text[i:i + 3] in ('"""', "'''") and (py or java or scala or cs) and (c == '"' or py):
            q = text[i:i + 3]
            j = text.find(q, i + 3)
            j = n if j < 0 else j + 3
            wipe(i + 3, j - 3)
            i = j
            continue
        verbatim = False
        if cs and c in "@$" and text[i:i + 3] in ('$@"', '@$"'):
            verbatim, i = True, i + 2
            c = '"'
        elif cs and c == "@" and text[i + 1:i + 2] == '"':
            verbatim, i = True, i + 1
            c = '"'
        elif cs and c == "$" and text[i + 1:i + 2] == '"':
            i += 1
            c = '"'
        elif (scala or py) and c in "sfrbuSFRBU" and text[i + 1:i + 2] in ('"', "'") and (i == 0 or not (text[i - 1].isalnum() or text[i - 1] == "_")):
            i += 1
            c = text[i]
        if c == '"' or (c == "'" and (py or js)) or (c == "`" and js):
            q = c
            j = i + 1
            while j < n:
                if verbatim and text[j:j + 2] == '""':
                    j += 2
                    continue
                if text[j] == "\\" and not verbatim:
                    j += 2
                    continue
                if text[j] == q:
                    break
                if text[j] == "\n" and q != "`":
                    break
                j += 1
            wipe(i + 1, j)
            i = j + 1
            continue
        if c == "'" and (java or cs or scala):
            m = re.match(r"'(?:\\.[^']{0,6}|[^\\'])'", text[i:i + 10])
            if m:
                wipe(i + 1, i + m.end() - 1)
                i += m.end()
                continue
        i += 1
    return "".join(out)


# ---------------------------------------------------------------- source scanner

ID = r"[A-Za-z_$][\w$]*"
J_MODS = r"(?:(?:public|protected|private|static|final|abstract|synchronized|native|default|strictfp|transient|volatile|sealed|non-sealed)\s+)*"
CS_MODS = (r"(?:(?:public|protected|private|internal|static|readonly|const|abstract|virtual|override|async|sealed|partial|"
           r"extern|new|unsafe|volatile|required|file|ref)\s+)*")
SC_MODS = r"(?:(?:private|protected|override|final|implicit|lazy|abstract|sealed|inline|transparent|open|opaque|infix)(?:\[[^\]]*\])?\s+)*"
TS_MODS = r"(?:(?:public|private|protected|static|async|abstract|override|readonly|declare|get|set|accessor)\s+)*"
KEYWORD_TYPES = {"return", "new", "throw", "else", "case", "assert", "yield", "goto", "import", "package", "break",
                 "continue", "do", "throws", "extends", "implements", "await", "using", "var", "if", "for", "while", "switch", "try", "catch", "lock", "typeof"}

TYPE_RX = {
    "java": re.compile(r"^\s*(?:@\w[\w.]*(?:\([^)]*\))?\s+)*" + J_MODS + r"(?P<kw>@interface|class|interface|enum|record)\s+(?P<name>" + ID + r")(?(kw)(?=[\s<({]|$))"),
    "csharp": re.compile(r"^\s*(?:\[[^\]]*\]\s*)*" + CS_MODS + r"(?P<kw>class|interface|enum|record\s+struct|record\s+class|record|struct)\s+(?P<name>" + ID + r")"),
    "scala": re.compile(r"^\s*(?:@\w[\w.]*(?:\([^)]*\))?\s+)*" + SC_MODS + r"(?:case\s+)?(?P<kw>class|trait|object|enum)\s+(?P<name>" + ID + r"|`[^`]+`)"),
    "python": re.compile(r"^\s*(?P<kw>class)\s+(?P<name>" + ID + r")"),
    "ts": re.compile(r"^\s*(?:@[\w.]+(?:\([^)]*\))?\s+)*(?:export\s+)?(?:default\s+)?(?:declare\s+)?(?:abstract\s+)?(?:const\s+)?(?P<kw>class|interface|enum)\s+(?P<name>" + ID + r")"),
}
TYPE_RX["javascript"] = TYPE_RX["typescript"] = TYPE_RX["ts"]
RECORD_FIX = re.compile(r"record\s+\w+\s*[(<]")

JAVA_METHOD = re.compile(r"^" + J_MODS + r"(?:<[^;{}]*?>\s+)?(?P<type>[\w.$]+(?:\s*<.*>)?(?:\s*\[\s*\])*)\s+(?P<name>" + ID + r")\s*\(")
JAVA_FIELD = re.compile(r"^" + J_MODS + r"(?P<type>[\w.$]+(?:\s*<.*>)?(?:\s*\[\s*\])*)\s+(?P<name>" + ID + r")\s*(?:=(?!=)|;|,|\[)")
CS_METHOD = re.compile(r"^" + CS_MODS + r"(?P<type>[\w.]+(?:\s*<.*>)?\??(?:\s*\[[,\s]*\])*)\s+(?P<name>" + ID + r"(?:\.\w+)*)\s*(?:<[^>()]*>)?\s*\(")
CS_FIELD = re.compile(r"^" + CS_MODS + r"(?P<type>[\w.]+(?:\s*<.*>)?\??(?:\s*\[[,\s]*\])*)\s+(?P<name>" + ID + r")\s*(?:=(?!>)|;|,)")
CS_PROP = re.compile(r"^" + CS_MODS + r"(?P<type>[\w.]+(?:\s*<.*>)?\??(?:\s*\[[,\s]*\])*)\s+(?P<name>" + ID + r")\s*(?:\{|=>)")
SC_DEF = re.compile(r"^" + SC_MODS + r"def\s+(?P<name>`[^`]+`|\w+|[^\s\w(\[:=]+)")
SC_VAL = re.compile(r"^" + SC_MODS + r"(?:val|var)\s+(?P<name>" + ID + r")")
TS_METHOD = re.compile(r"^" + TS_MODS + r"(?:\*\s*)?(?P<name>[#\w$]+)[?!]?\s*(?:<[^>()]*>)?\s*\(")
TS_FIELD = re.compile(r"^" + TS_MODS + r"(?P<name>[#\w$]+)[?!]?\s*(?P<t>:\s*[^=;]+?)?\s*(?:=(?!>)|;|$)")
TS_FUNC = re.compile(r"^(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s*\*?\s*(?P<name>[\w$]+)\s*(?:<[^>()]*>)?\(")
TS_CONST = re.compile(r"^(?:export\s+)?(?:default\s+)?(?:const|let|var)\s+(?P<name>[\w$]+)\s*(?P<t>:[^=]+)?=\s*(?P<rhs>.*)")
TS_ARROW = re.compile(r"^(?:async\s+)?(?:\([^)]*\)|[\w$]+)\s*(?::[^=]*)?=>|^(?:async\s+)?function\b")
PY_DEF = re.compile(r"^(?:async\s+)?def\s+(?P<name>\w+)\s*\(")
PY_ASSIGN = re.compile(r"^(?P<name>[A-Za-z_]\w*)\s*(?P<t>:\s*[^=]+?)?\s*(?:=(?!=)|$)")
CS_USING = re.compile(r"^\s*(?:global\s+)?using\s+(?:static\s+)?(?!var\b)(?:\w+\s*=\s*)?[\w.<>,\s?\[\]]+;")

SKIP_NAMES = {"if", "for", "while", "switch", "catch", "return", "function", "super", "this", "synchronized", "else", "do",
              "try", "new", "with", "using", "lock", "typeof", "await", "yield", "throw", "when"}


def balanced(text: str, start: int, open_c="(", close_c=")"):
    """Index just past the group opened at text[start]; (end, closed)."""
    depth = 0
    for k in range(start, len(text)):
        if text[k] == open_c:
            depth += 1
        elif text[k] == close_c:
            depth -= 1
            if depth == 0:
                return k + 1, True
    return len(text), False


def split_top(s: str, sep=","):
    parts, depth, cur = [], 0, []
    for ch in s:
        if ch in "<([{":
            depth += 1
        elif ch in ">)]}":
            depth -= 1
        if ch == sep and depth == 0:
            parts.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    parts.append("".join(cur))
    return [p.strip() for p in parts if p.strip()]


def strip_groups(s: str, pairs=("<>", "()", "[]")) -> str:
    for o, c in pairs:
        depth, out = 0, []
        for ch in s:
            if ch == o:
                depth += 1
            elif ch == c:
                depth = max(0, depth - 1)
            elif depth == 0:
                out.append(ch)
        s = "".join(out)
    return s


class Scan:
    """What the text says is declared in one file."""

    def __init__(self, lang, ext, lines):
        self.lang, self.ext, self.lines = lang, ext, lines
        self.code = blank("\n".join(lines), lang).split("\n")
        if len(self.code) < len(lines):
            self.code += [""] * (len(lines) - len(self.code))
        self.types, self.members, self.imports, self.props = [], [], [], []
        self.package = None
        self.packages = []
        if lang == "python":
            self._scan_python()
        else:
            self._scan_braces()

    # ---- helpers
    def header(self, i, upto=6, stop="{"):
        """Code text from line i (0-based) until `stop` or `upto` lines."""
        buf = []
        for k in range(i, min(len(self.code), i + upto)):
            seg = self.code[k]
            if stop in seg:
                buf.append(seg.split(stop, 1)[0])
                break
            buf.append(seg)
        return " ".join(buf)

    def decl_text(self, i, upto=12):
        """Joined blanked text from line i, long enough to hold the whole parameter list."""
        return " ".join(self.code[i:i + upto])

    def params_of(self, i, name):
        """Python: (count without self/cls, params, text after the list) for `def name(`."""
        txt = self.decl_text(i)
        mm = re.search(r"\bdef\s+" + re.escape(name) + r"\s*\(", txt)
        if not mm:
            return 0, [], txt
        end, ok = balanced(txt, mm.end() - 1)
        params = [x for x in split_top(txt[mm.end():end - 1]) if x not in ("*", "/")]
        if params and re.match(r"(self|cls)\b", params[0]):
            params = params[1:]
        return len(params), params, txt[end:]

    # ---- brace languages
    def _type_hit(self, code, d0, stack):
        rx = TYPE_RX[self.lang]
        m = rx.match(code)
        if not m:
            return None
        kw = re.sub(r"\s+", " ", m.group("kw"))
        if self.lang == "java" and kw == "record" and not RECORD_FIX.search(code):
            return None
        if self.lang in ("javascript", "typescript") and not (d0 == 0 or (stack and d0 == stack[-1])):
            return None
        return kw, m.group("name")

    def _scan_braces(self):
        lang = self.lang
        depth = pdepth = 0
        stack = []
        pending = None  # (decl_depth, line_idx)
        pend_ann = None
        braces = []
        ns_pending = False
        sc = lang == "scala"
        open_attr = None  # (joined text, first line idx, lines joined): C# attribute list spanning lines, until its `]` closes
        prev_code = ""  # last non-blank code line before this one (C#: tells attribute `[` from collection expression `[`)
        for i, code in enumerate(self.code):
            d0, p0 = depth, pdepth
            at_level = p0 == 0 and (not stack and d0 == 0 or (stack and d0 == stack[-1]) or (lang in ("csharp", "scala", "java") and d0 == 0))
            member_level = p0 == 0 and bool(stack) and d0 == stack[-1]
            top_level = p0 == 0 and not stack and d0 == 0
            s = code.strip()
            if p0 == 0:
                self._imports(i, s)
            # pending type cancellation (scala: type without a body)
            if pending is not None and i > pending[1] and p0 == 0 and d0 == pending[0] and s and \
                    re.match(r"(?:@\w+\s*)*(?:(?:private|protected|override|final|implicit|lazy|abstract|sealed|case)\s+)*(?:def|val|var|class|object|trait|import|package|type|enum)\b", s):
                pending = None
            # annotations / attributes preceding a declaration
            rest = s
            if (at_level or member_level) and s:
                first = i
                if open_attr is not None:
                    s = open_attr[0] + " " + s
                    first = open_attr[1]
                    nj = open_attr[2] + 1
                    open_attr = None
                else:
                    nj = 1
                n_ann, rest, unclosed = self._leading_annotations(s, prev_code if first == i else "")
                if unclosed and lang == "csharp" and nj < 40:
                    open_attr = (s, first, nj)
                    n_ann, rest = 0, ""
                    s = ""
                    code = ""
                if n_ann:
                    pend_ann = (pend_ann[0] + n_ann if pend_ann else n_ann, pend_ann[1] if pend_ann else first)
            decl_item = None
            if (at_level or member_level) and rest:
                decl_item = self._decl(i, rest, d0, p0, stack, member_level, top_level)
            if decl_item is not None:
                if pend_ann:
                    decl_item["ann"] = pend_ann[0]
                    decl_item["ann_line"] = pend_ann[1] + 1
                pend_ann = None
                if decl_item["cat"] == "type" and "{" not in rest.split(";")[0] and lang != "python":
                    pass
                if decl_item["cat"] == "type":
                    pending = (d0, i)
            elif lang == "csharp" and rest and p0 == 0 and self.props and self.props[-1]["line"] == i + 1:
                # a property consumes its pending attributes (property is a `field` define for M1; not in S2/G3 members)
                pr = self.props[-1]
                if pend_ann:
                    pr["ann"] = pend_ann[0]
                    pr["ann_line"] = pend_ann[1] + 1
                pend_ann = None
            elif lang == "csharp" and rest and p0 == 0 and s.startswith("["):
                pend_ann = None  # same-line attributes on an unrecognised declaration must not leak onto the next member
            elif s and p0 == 0 and not (s.startswith("@") or (lang == "csharp" and s.startswith("["))) and not rest == "":
                pend_ann = None
            # brace accounting (namespace/package block braces are transparent)
            if lang == "csharp" and re.match(r"namespace\s+[\w.]+\s*(?:\{|$)", s) and ";" not in s:
                ns_pending = True
            elif lang == "scala" and re.match(r"package\s+[\w.]+\s*\{", s):
                ns_pending = True
            for ch in code:
                if ch == "{":
                    if ns_pending:
                        ns_pending = False
                        braces.append("ns")
                    else:
                        braces.append("o")
                        depth += 1
                        if pending is not None:
                            stack.append(depth)
                            pending = None
                elif ch == "}":
                    kind = braces.pop() if braces else "o"
                    if kind != "ns":
                        if stack and depth == stack[-1]:
                            stack.pop()
                        depth -= 1
                elif ch == "(":
                    pdepth += 1
                elif ch == ")":
                    pdepth = max(0, pdepth - 1)
                elif ch == ";" and pending is not None and pdepth == 0 and lang != "scala":
                    pending = None
            depth = max(depth, 0)
            if s:
                prev_code = s
        self._regions()

    def _leading_annotations(self, s, prev=""):
        """(count, rest_of_line, unclosed) for annotations/attributes at the start of the line.
        C#: a leading `[` is a collection expression, not an attribute, when the previous code
        line ends in an operator that expects an expression (`=`, `=>`, `(`, `,`, `[`, `?`) or is `return`/`yield return`."""
        n = 0
        lang = self.lang
        if lang == "csharp" and re.search(r"(?:=|=>|\(|,|\[|\?)$|(?:^|\s)return$", prev.rstrip()):
            return 0, s, False
        while True:
            s = s.lstrip()
            if lang == "csharp":
                if not s.startswith("["):
                    break
                end, ok = balanced(s, 0, "[", "]")
                if not ok:
                    n += 1
                    return n, "", True
                inner = s[1:end - 1]
                if re.match(r"\s*(assembly|module)\s*:", inner):
                    s = s[end:]
                    continue
                inner = re.sub(r"^\s*\w+\s*:\s*", "", inner)
                n += max(1, len(split_top(inner)))
                s = s[end:]
            else:
                if not s.startswith("@") or s.startswith("@interface"):
                    break
                m = re.match(r"@\s*[\w.$]+", s)
                if not m:
                    break
                n += 1
                s = s[m.end():]
                if s.lstrip().startswith("("):
                    s = s.lstrip()
                    end, ok = balanced(s, 0)
                    if not ok:
                        return n, "", True
                    s = s[end:]
        return n, s.strip(), False

    def _imports(self, i, s):
        lang = self.lang
        ok = False
        if lang == "java":
            ok = re.match(r"import\s+(?:static\s+)?[\w.*$]+\s*;", s) is not None
            m = re.match(r"package\s+([\w.]+)\s*;", s)
            if m and self.package is None:
                self.package = m.group(1)
            if m:
                self.packages.append(m.group(1))
        elif lang == "scala":
            ok = re.match(r"import\s+\S", s) is not None
            m = re.match(r"package\s+(?!object\b)([\w.]+)", s)
            if m:
                self.package = (self.package + "." if self.package else "") + m.group(1)
                self.packages = [self.package]
        elif lang == "csharp":
            ok = CS_USING.match(s + "") is not None and not s.startswith("using (")
            m = re.match(r"namespace\s+([\w.]+)", s)
            if m and self.package is None:
                self.package = m.group(1)
            if m:
                self.packages.append(m.group(1))
        elif lang in ("javascript", "typescript"):
            ok = re.match(r"import\s*(?:type\s+)?(?:[\w{*$]|['\"])", s) is not None and not s.startswith("import(") and not s.startswith("import.")
            if re.match(r"import\s*\(", s):
                ok = False
        if ok:
            self.imports.append(i + 1)

    def _decl(self, i, rest, d0, p0, stack, member_level, top_level):
        lang = self.lang
        th = self._type_hit(rest, d0, stack)
        if th is not None and (member_level or top_level or d0 == 0 or lang != "java" or True):
            kw, name = th
            item = {"cat": "type", "line": i + 1, "name": name, "kw": kw, "ann": 0}
            self.types.append(item)
            return item
        item = None
        if lang == "java":
            if member_level:
                item = self._java_member(i, rest)
        elif lang == "csharp":
            if member_level:
                item = self._cs_member(i, rest)
        elif lang == "scala":
            if member_level:
                item = self._scala_member(i, rest)
        else:
            if member_level:
                item = self._ts_member(i, rest)
            elif top_level:
                item = self._ts_top(i, rest)
        if item is not None:
            item["ann"] = 0
            item["line"] = i + 1
            self.members.append(item)
        return item

    def _type_names(self):
        return {t["name"] for t in self.types}

    def _java_member(self, i, rest):
        m = JAVA_METHOD.match(rest)
        if m and m.group("type") not in KEYWORD_TYPES:
            n, params, after = self._params_after(i, rest, m)
            return {"cat": "method", "name": m.group("name"), "np": n, "params": params, "ret": m.group("type"), "ctor": False}
        m = re.match(r"^" + J_MODS + r"(?P<name>" + ID + r")\s*\(", rest)
        if m and m.group("name") in self._type_names():
            n, params, after = self._params_after(i, rest, m)
            return {"cat": "method", "name": m.group("name"), "np": n, "params": params, "ret": None, "ctor": True}
        m = JAVA_FIELD.match(rest)
        if m and m.group("type") not in KEYWORD_TYPES and m.group("type") not in ("static", "final") and not rest.startswith("}"):
            return {"cat": "field", "name": m.group("name"), "ftype": m.group("type")}
        return None

    def _params_after(self, i, rest, m):
        """(count, [param text], text after the parameter list) of a declaration whose name is m.group('name')."""
        txt = self.decl_text(i)
        name = m.group("name")
        mm = re.search(r"(?<![\w$.])" + re.escape(name) + r"\s*(?:<[^>()]*>)?\s*\(", txt)
        if not mm:
            return 0, [], txt
        start = mm.end() - 1
        end, ok = balanced(txt, start)
        groups = [txt[start + 1:end - 1]]
        pos = end
        if self.lang == "scala":
            while re.match(r"\s*\(", txt[pos:]):
                pos += len(txt[pos:]) - len(txt[pos:].lstrip())
                e2, ok2 = balanced(txt, pos)
                groups.append(txt[pos + 1:e2 - 1])
                pos = e2
        params = []
        for g in groups:
            params += split_top(g)
        return len(params), params, txt[pos:]

    def _cs_member(self, i, rest):
        m = CS_METHOD.match(rest)
        if m and m.group("type") not in KEYWORD_TYPES and m.group("type") not in ("operator",):
            n, params, after = self._params_after(i, rest, m)
            return {"cat": "method", "name": m.group("name"), "np": n, "params": params, "ret": m.group("type"), "ctor": False}
        m = re.match(r"^" + CS_MODS + r"(?P<name>" + ID + r")\s*\(", rest)
        if m and m.group("name") in self._type_names():
            n, params, after = self._params_after(i, rest, m)
            return {"cat": "method", "name": m.group("name"), "np": n, "params": params, "ret": None, "ctor": True}
        m = CS_FIELD.match(rest)
        if m and m.group("type") not in KEYWORD_TYPES:
            return {"cat": "field", "name": m.group("name"), "ftype": m.group("type")}
        m = CS_PROP.match(rest)
        if m and m.group("type") not in KEYWORD_TYPES:
            self.props.append({"line": i + 1, "name": m.group("name"), "cat": "field", "ann": 0})
        return None

    def _scala_member(self, i, rest):
        m = SC_DEF.match(rest)
        if m:
            txt = self.decl_text(i)
            k = txt.find(m.group("name"))
            after = txt[k + len(m.group("name")):] if k >= 0 else ""
            after_s = after.lstrip()
            if after_s.startswith("["):
                end, ok = balanced(after_s, 0, "[", "]")
                after_s = after_s[end:].lstrip()
            groups, params = 0, []
            while after_s.startswith("("):
                end, ok = balanced(after_s, 0)
                params += split_top(after_s[1:end - 1])
                after_s = after_s[end:].lstrip()
            rm = re.match(r":\s*(?P<r>[^=]+?)\s*(?:=|\{|$)", after_s)
            return {"cat": "method", "name": m.group("name"), "np": len(params), "params": params,
                    "ret": rm.group("r") if rm else None, "ctor": False}
        m = SC_VAL.match(rest)
        if m:
            tm = re.match(r"\s*:\s*(?P<t>[^=]+?)\s*(?:=|$)", rest[m.end():])
            return {"cat": "field", "name": m.group("name"), "ftype": tm.group("t") if tm else None}
        return None

    def _ts_member(self, i, rest):
        m = TS_METHOD.match(rest)
        if m and m.group("name") not in SKIP_NAMES:
            txt = self.decl_text(i)
            k = txt.find(rest[:20]) if rest else 0
            start = txt.find("(", max(k, 0) + m.end(0) - 1)
            end, ok = balanced(txt, start)
            params = split_top(txt[start + 1:end - 1])
            after = txt[end:]
            rm = re.match(r"\s*:\s*(?P<r>[^{=;]+)", after)
            return {"cat": "method", "name": m.group("name"), "np": len(params), "params": params,
                    "ret": rm.group("r").strip() if rm else None, "ctor": m.group("name") == "constructor"}
        m = TS_FIELD.match(rest)
        if m and m.group("name") not in SKIP_NAMES and ("=" in rest or ";" in rest or ":" in rest) and not rest.startswith(("}", "{", "]", ")")):
            t = m.group("t")
            return {"cat": "field", "name": m.group("name"), "ftype": t.lstrip(": ").strip() if t else None}
        return None

    def _ts_top(self, i, rest):
        m = TS_FUNC.match(rest)
        if m:
            txt = self.decl_text(i)
            k = txt.find("(", txt.find(m.group("name")))
            end, ok = balanced(txt, k)
            params = split_top(txt[k + 1:end - 1])
            rm = re.match(r"\s*:\s*(?P<r>[^{=;]+)", txt[end:])
            return {"cat": "method", "name": m.group("name"), "np": len(params), "params": params,
                    "ret": rm.group("r").strip() if rm else None, "ctor": False, "func": True}
        m = TS_CONST.match(rest)
        if m:
            rhs = m.group("rhs")
            if TS_ARROW.match(rhs):
                txt = self.decl_text(i)
                k = txt.find("=", txt.find(m.group("name")))
                seg = txt[k + 1:].lstrip()
                seg = re.sub(r"^async\s+", "", seg)
                params, ret = [], None
                if seg.startswith("("):
                    end, ok = balanced(seg, 0)
                    params = split_top(seg[1:end - 1])
                    rm = re.match(r"\s*:\s*(?P<r>[^=]+?)\s*=>", seg[end:])
                    ret = rm.group("r").strip() if rm else None
                elif re.match(r"[\w$]+\s*=>", seg):
                    params = [seg.split("=>")[0].strip()]
                elif seg.startswith("function"):
                    p = seg.find("(")
                    if p >= 0:
                        end, ok = balanced(seg, p)
                        params = split_top(seg[p + 1:end - 1])
                return {"cat": "method", "name": m.group("name"), "np": len(params), "params": params,
                        "ret": ret, "ctor": False, "func": True}
            t = m.group("t")
            return {"cat": "field", "name": m.group("name"), "ftype": t.lstrip(": ").strip() if t else None, "const": True}
        return None

    # ---- python
    def _scan_python(self):
        stack = []  # (indent, kind)
        pdepth = 0
        pend_ann = None
        for i, code in enumerate(self.code):
            p0 = pdepth
            for ch in code:
                if ch in "([{":
                    pdepth += 1
                elif ch in ")]}":
                    pdepth = max(0, pdepth - 1)
            if p0 > 0 or not code.strip():
                continue
            indent = len(code) - len(code.lstrip())
            s = code.strip()
            while stack and indent <= stack[-1][0]:
                stack.pop()
            inner = stack[-1][1] if stack else None
            if re.match(r"(?:import\s+\w|from\s+[\w.]+\s+import\s)", s):
                self.imports.append(i + 1)
            if s.startswith("@"):
                pend_ann = (pend_ann[0] + 1 if pend_ann else 1, pend_ann[1] if pend_ann else i)
                continue
            item = None
            m = TYPE_RX["python"].match(s)
            if m:
                item = {"cat": "type", "line": i + 1, "name": m.group("name"), "kw": "class", "ann": 0}
                self.types.append(item)
                stack.append((indent, "class"))
            else:
                m = PY_DEF.match(s)
                if m:
                    if inner in (None, "class"):
                        n, params, after = self.params_of(i, m.group("name"))
                        rm = re.match(r"\s*->\s*(?P<r>[^:]+):", after)
                        item = {"cat": "method", "name": m.group("name"), "np": n, "params": params,
                                "ret": rm.group("r").strip() if rm else None, "ctor": False, "line": i + 1,
                                "func": inner is None, "ann": 0}
                        self.members.append(item)
                    stack.append((indent, "def"))
                elif inner in (None, "class"):
                    m = PY_ASSIGN.match(s)
                    if m and not s.startswith(("return", "if ", "for ", "while ", "with ", "else", "elif", "try", "except", "finally", "assert", "raise", "del ", "pass", "print")):
                        name = m.group("name")
                        has_t = bool(m.group("t"))
                        if (inner == "class" and ("=" in s or has_t)) or (inner is None and (name.isupper() or has_t) and ("=" in s or has_t)):
                            item = {"cat": "field", "name": name, "ftype": m.group("t").lstrip(": ").strip() if has_t else None,
                                    "line": i + 1, "ann": 0}
                            self.members.append(item)
            if pend_ann and item is not None:
                item["ann"] = pend_ann[0]
                item["ann_line"] = pend_ann[1] + 1
            if item is not None or (not s.startswith("@")):
                pend_ann = None
        self._regions()

    def _regions(self):
        """Enclosing-member region for each member: from its line to the line before the next sibling declaration."""
        items = sorted(self.types + self.members, key=lambda x: x["line"])
        for k, it in enumerate(items):
            it["end"] = items[k + 1]["line"] - 1 if k + 1 < len(items) else len(self.lines)

    def enclosing_member(self, line, cat="method"):
        best = None
        for it in self.members:
            if it["cat"] == cat and it["line"] <= line <= it.get("end", it["line"]):
                best = it
        return best


# ---------------------------------------------------------------- corpus loading


def git_status(repo: Path) -> str:
    r = subprocess.run(["git", "-C", str(repo), "status", "--porcelain=v1", "--untracked-files=all"], capture_output=True, text=True)
    head = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    return "HEAD %s\n%s" % (head, r.stdout.strip())


def load_repo(name: str):
    from cdp import extract as X, inventory as I, rules as R
    from cdp.util import read_lines
    repo = Path.home() / "git" / name
    t0 = time.time()
    inv = I.build_inventory(repo)
    t1 = time.time()
    ex = X.run_extract(repo, inv)
    t2 = time.time()
    ex = R.apply(ex, repo=repo)
    t3 = time.time()
    parsed_loc = sum(f["loc"] for f in inv["files"] if not f["binary"] and f["bytes"] <= 2_000_000 and f["path"] in ex["files"])
    return {"repo": repo, "inv": inv, "ex": ex, "read_lines": read_lines,
            "t": {"inventory": t1 - t0, "extract": t2 - t1, "rules": t3 - t2}, "loc": parsed_loc}


# ---------------------------------------------------------------- scoring state


class Cell:
    __slots__ = ("e", "p", "misses", "extra", "na", "note")

    def __init__(self):
        self.e = self.p = 0
        self.misses = []
        self.extra = collections.Counter()
        self.na = False
        self.note = ""

    def add(self, ok, where=None, n=1):
        self.p += n
        if ok:
            self.e += n
        elif where is not None:
            self.misses.append(where)

    def pct(self):
        return 100.0 * self.e / self.p if self.p else None


_JS_EXT = r"\.(?:js|mjs|cjs)$"
_ASSET_DIRS = {"static", "assets", "dist", "build", "vendor"}
_HASH_HEX = re.compile(r"[.\-]([0-9a-f]{8,})$")
_HASH_B64 = re.compile(r"[.\-]([0-9A-Za-z_][0-9A-Za-z_\-]{7})$")


def is_bundled_asset(path, all_paths=()):
    """Owner decision D4 (EXTRACTION_METRICS.md section 1, 'production file'): minified, bundled and hashed-asset JS
    files are not scored by the coverage rows. Generic file-name rules, no repo names:
      1. basename `*.min.{js,mjs,cjs}`;
      2. basename has a `bundle` word (`x.bundle.js`, `x-bundle.js`, `x-bundle-core.js`);
      3. `X.dev.js` whose sibling `X.min.js` exists (the unminified twin of a minified build output);
      4. stem ends in a build hash (`name.<8+ hex with a digit>`, or `name-<8 base64url chars>` with an uppercase letter and
         a digit or 2+ uppercase) AND a directory segment is one of static/assets/dist/build/vendor.
    A plain `vendor.js` / `bundle`-free name is kept (no evidence it is a build output)."""
    base = path.rsplit("/", 1)[-1]
    if not re.search(_JS_EXT, base):
        return False
    stem = re.sub(_JS_EXT, "", base)
    if re.search(r"\.min$", stem):
        return True
    if re.search(r"(?:^|[.\-_])bundle(?:$|[.\-_])", stem):
        return True
    if stem.endswith(".dev") and (path[: -len(base)] + stem[:-4] + ".min.js") in all_paths:
        return True
    if _ASSET_DIRS & set(path.split("/")[:-1]):
        m = _HASH_HEX.search(stem)
        if m and re.search(r"\d", m.group(1)):
            return True
        m = _HASH_B64.search(stem)
        if m:
            t = m.group(1)
            up = sum(c.isupper() for c in t)
            if up and (re.search(r"\d", t) or up >= 2):
                return True
    return False


class Ctx:
    """Everything scored for one repo."""

    def __init__(self, name, data):
        self.name = name
        self.inv, self.ex = data["inv"], data["ex"]
        self.repo = data["repo"]
        self.t, self.loc = data["t"], data["loc"]
        self.read_lines = data["read_lines"]
        self.files = {f["path"]: f for f in self.inv["files"]}
        self.prod_all = sorted(p for p, f in self.files.items() if f["role"] == "source" and f["language"] in LANGS and not f["binary"])
        self.excluded = [p for p in self.prod_all if is_bundled_asset(p, self.files)]    # D4: coverage rows skip these
        _ex = set(self.excluded)
        self.prod = [p for p in self.prod_all if p not in _ex]
        self.defs_at = collections.defaultdict(list)
        self.defs_in = collections.defaultdict(list)
        for d in self.ex["defines"]:
            self.defs_at[(d["file"], d["anchor"]["line"])].append(d)
            self.defs_in[d["file"]].append(d)
        self.imports_at = collections.defaultdict(set)
        self.import_fqns = collections.defaultdict(list)
        self.type_fqns = {d["fqn"] for d in self.ex["defines"] if d["kind"] not in MEMBER_KINDS}
        for i in self.ex["imports"]:
            self.imports_at[i["file"]].add(i["line"])
            self.import_fqns[i["file"]].append(i["fqn"])
        self.edges = collections.defaultdict(list)
        for e in list(self.ex["io_edges"]) + list(self.ex.get("rule_edges") or []):
            self.edges[e["file"]].append(e)
        self.uses_in = collections.defaultdict(list)
        for u in self.ex["uses"]:
            self.uses_in[u["file"]].append(u)
        self.scans = {}

    def lang(self, path):
        return self.files[path]["language"]

    def scan(self, path):
        if path not in self.scans:
            lines = self.read_lines(self.repo / path)
            self.scans[path] = Scan(self.lang(path), path.rsplit(".", 1)[-1].lower(), lines)
        return self.scans[path]


def loc_of(rel, line, ctx):
    return "%s/%s:%d" % (ctx.name, rel, line)


class Score:
    def __init__(self):
        self.cells = collections.defaultdict(dict)   # fid -> lang -> Cell
        self.judg_present = []                       # text-check judgments (all)
        self.judg_emitted = []
        self.r2_keys = collections.Counter()

    def cell(self, fid, lang):
        c = self.cells[fid].get(lang)
        if c is None:
            c = self.cells[fid][lang] = Cell()
        return c

    def judge(self, fid, lang, where, ok, text):
        self.judg_present.append((fid, lang, where, text))
        if ok:
            self.judg_emitted.append((fid, lang, where, text))


def kind_ok(d, kinds):
    return d["kind"] in kinds


def valid_params(d, n, lang):
    ps = d.get("params")
    if not isinstance(ps, list) or not ps:
        return False
    if not all(isinstance(x, dict) and isinstance(x.get("name"), str) for x in ps):
        return False
    if len(ps) == n:
        return True
    return lang == "python" and len(ps) == n + 1 and ps[0]["name"] in ("self", "cls")


def line_text(ctx, rel, line, scan=None):
    s = scan or ctx.scan(rel)
    return s.lines[line - 1].strip()[:110] if 0 < line <= len(s.lines) else ""


def score_code_facts(ctx, sc: Score):
    FIELD_KINDS = {"field", "constant"}
    for rel in ctx.prod:
        lang = ctx.lang(rel)
        scan = ctx.scan(rel)
        ext = scan.ext
        is_py, is_js = lang == "python", lang in ("javascript", "typescript")

        def at(line, pred):
            return [d for d in ctx.defs_at.get((rel, line), ()) if pred(d)]

        # S1
        for t in scan.types:
            ds = at(t["line"], lambda d: d["kind"] not in MEMBER_KINDS)
            w = loc_of(rel, t["line"], ctx)
            sc.cell("S1", lang).add(bool(ds), w)
            sc.judge("S1", lang, w, bool(ds), line_text(ctx, rel, t["line"], scan))
        # S2
        for m in scan.members:
            ds = at(m["line"], lambda d: d["kind"] in ("method", "function", "field", "constant"))
            w = loc_of(rel, m["line"], ctx)
            sc.cell("S2", lang).add(bool(ds), w)
            sc.judge("S2", lang, w, bool(ds), line_text(ctx, rel, m["line"], scan))
        if lang == "csharp":
            sc.cell("S2", lang).extra["csharp_properties_present_not_scored"] += len(scan.props)
            sc.cell("S2", lang).extra["csharp_properties_with_define_at_line"] += sum(1 for pr in scan.props if at(pr["line"], lambda d: d["kind"] in ("field", "constant", "method")))
        # G1 / G2 / G3
        for m in scan.members:
            w = loc_of(rel, m["line"], ctx)
            if m["cat"] == "method":
                ds = at(m["line"], lambda d: d["kind"] in ("method", "function"))
                if m["np"] >= 1:
                    ok = any(valid_params(d, m["np"], lang) for d in ds)
                    sc.cell("G1", lang).add(ok, w)
                    sc.judge("G1", lang, w, ok, line_text(ctx, rel, m["line"], scan))
                    if ds and any(isinstance(d.get("pmax"), int) and not d.get("params") for d in ds):
                        sc.cell("G1", lang).extra["count_only_pmax"] += 1
                if m["ret"] and not m["ctor"] and lang != "javascript":
                    ok = any(isinstance(d.get("ret"), str) and d["ret"] for d in ds)
                    sc.cell("G2", lang).add(ok, w)
                    if m["ret"] == "void":
                        sc.cell("G2", lang).extra["void_present"] += 1
                        sc.cell("G2", lang).extra["void_emitted"] += int(ok)
                    sc.judge("G2", lang, w, ok, line_text(ctx, rel, m["line"], scan))
            elif m["cat"] == "field" and m.get("ftype") and lang != "javascript":
                ds = at(m["line"], lambda d: d["kind"] in FIELD_KINDS)
                ok = any(isinstance(d.get("ftype"), str) and d["ftype"] for d in ds)
                sc.cell("G3", lang).add(ok, w)
                sc.judge("G3", lang, w, ok, line_text(ctx, rel, m["line"], scan))
        # R1
        for t in scan.types:
            if has_base(scan, t, ext):
                w = loc_of(rel, t["line"], ctx)
                ds = at(t["line"], lambda d: d["kind"] not in MEMBER_KINDS)
                ok = any(isinstance(d.get("supertypes"), list) and d["supertypes"] and all(isinstance(x, str) for x in d["supertypes"]) for d in ds)
                sc.cell("R1", lang).add(ok, w)
                sc.judge("R1", lang, w, ok, line_text(ctx, rel, t["line"], scan))
                c2 = sc.cell("R2", lang)
                c2.p += 1
        # R3
        got = ctx.imports_at.get(rel, set())
        for ln in scan.imports:
            w = loc_of(rel, ln, ctx)
            ok = ln in got
            sc.cell("R3", lang).add(ok, w)
            sc.judge("R3", lang, w, ok, line_text(ctx, rel, ln, scan))
        # M1 (annotations above declarations)
        if lang != "javascript":
            for it in scan.types + scan.members + (scan.props if lang == "csharp" else []):
                n = it.get("ann", 0)
                if not n:
                    continue
                cat = it["cat"]
                kinds = ((lambda d: d["kind"] not in MEMBER_KINDS) if cat == "type" else
                         (lambda d: d["kind"] in ("method", "function")) if cat == "method" else (lambda d: d["kind"] in FIELD_KINDS))
                ds = at(it["line"], kinds)
                e = max([len(d.get("annotations") or ()) for d in ds] or [0])
                w = loc_of(rel, it.get("ann_line") or it["line"], ctx)
                c = sc.cell("M1", lang)
                c.p += n
                c.e += min(e, n)
                if min(e, n) < n:
                    c.misses.append(w)
                sc.judge("M1", lang, w, e >= n, line_text(ctx, rel, it.get("ann_line") or it["line"], scan))
        # S3 / S4 / G4 / M2 / M3 (facts-based)
        for d in ctx.defs_in.get(rel, ()):
            a = d["anchor"]["line"]
            w = loc_of(rel, a, ctx)
            for k in d:
                if (("super" in k and k != "supertypes") or k in ("extends", "implements", "base_kinds", "bases")) and d[k]:
                    sc.r2_keys[(lang, k)] += 1
            if d["kind"] not in ("method", "function", "field", "constant", "table") or d["kind"] in ("method", "function"):
                el = d.get("end_line")
                sc.cell("S3", lang).add(isinstance(el, int) and not isinstance(el, bool) and el >= a, w)
            sc.cell("G4", lang).add(d.get("visibility") in ("public", "protected", "internal", "package", "private"), w)
            sc.cell("S4", lang).add(s4_ok(d, scan, lang), w)
            for an in (d.get("annotations") or ()) if lang != "javascript" else ():
                aw = loc_of(rel, an.get("line") or a, ctx)
                if isinstance(an.get("text"), str) and "(" in an["text"]:
                    sc.cell("M2", lang).add(isinstance(an.get("args"), dict), aw)
                sc.cell("M3", lang).add(isinstance(an.get("fqn"), str) and bool(an["fqn"]), aw)


def has_base(scan, t, ext):
    lang, kw = scan.lang, t["kw"]
    i = t["line"] - 1
    if lang in ("java",):
        h = strip_groups(scan.header(i), pairs=("<>",))
        h = re.sub(r"\(.*?\)", " ", h)
        mm = re.search(r"\b(?:class|interface|enum|record|@interface)\s+" + re.escape(t["name"]) + r"(.*)", h)
        return bool(mm and re.search(r"\b(extends|implements)\b", mm.group(1)))
    if lang == "scala":
        h = scan.header(i, upto=4)
        h = h.split("=", 1)[0] if "{" not in h and "=" in h else h
        h = strip_groups(h, pairs=("[]", "()"))
        mm = re.search(r"\b" + re.escape(t["name"]) + r"(.*)", h)
        return bool(mm and re.search(r"\b(extends|with)\b", mm.group(1)))
    if lang == "csharp":
        if kw == "enum":
            return False
        h = strip_groups(scan.header(i, upto=4), pairs=("<>", "()"))
        mm = re.search(r"\b" + re.escape(t["name"]) + r"\s*(.*)", h)
        return bool(mm and mm.group(1).startswith(":"))
    if lang == "python":
        h = scan.decl_text(i, 6)
        mm = re.match(r"\s*class\s+\w+\s*(?:\[[^\]]*\])?\s*\(", h)
        if not mm:
            return False
        end, ok = balanced(h, mm.end() - 1)
        args = [a for a in split_top(h[mm.end():end - 1]) if "=" not in a.split("(")[0] or a.startswith("*")]
        args = [a for a in args if a != "object"]
        return bool(args)
    if lang in ("javascript", "typescript"):
        h = strip_groups(scan.header(i, upto=4), pairs=("<>",))
        mm = re.search(r"\b" + re.escape(t["name"]) + r"(.*)", h)
        if not mm:
            return False
        if ext in ("ts", "tsx"):
            return bool(re.search(r"\b(extends|implements)\b", mm.group(1)))
        return bool(re.search(r"\bextends\b", mm.group(1)))
    return False


def s4_ok(d, scan, lang):
    fqn = d["fqn"]
    kind = d["kind"]
    if lang in ("python", "javascript", "typescript"):
        pkgs = []   # no package keyword
    else:
        pkgs = scan.packages or ([scan.package] if scan.package else [])
    if pkgs and not any(fqn == p or fqn.startswith(p + ".") for p in pkgs):
        return False
    if kind == "method":
        return "#" in fqn
    if kind in ("field", "constant"):
        return "#" not in fqn and "." in fqn
    return True


# ---------------------------------------------------------------- uses (U1, U2)


def score_uses(ctx, sc: Score):
    for rel in ctx.prod:
        lang = ctx.lang(rel)
        loc = ctx.files[rel]["loc"]
        sc.cell("U1", lang).extra["loc"] += loc
        sc.cell("U2", lang).extra["loc"] += loc
        for u in ctx.uses_in.get(rel, ()):
            k = u.get("kind")
            if k == "type":
                sc.cell("U1", lang).p += 1
            elif k == "call":
                c = sc.cell("U2", lang)
                ok = bool(u.get("from_symbol"))
                c.add(ok, loc_of(rel, u["anchor"]["line"], ctx))
                c.extra["calls"] += 1


# ---------------------------------------------------------------- frameworks (F1-F7)

JVM, CS, PY, JS = ("java", "scala"), ("csharp",), ("python",), ("javascript", "typescript")
VERB = r"(?:get|post|put|delete|patch)"
FW = [
    # fid, framework, langs, regex, mode, channels, target prefix
    ("F1", "JAX-RS", JVM, r"@(?:GET|POST|PUT|DELETE|PATCH)\b", "ann", ("http_in",), "route:"),
    ("F1", "Spring MVC", JVM, r"@(?:Get|Post|Put|Delete|Patch)Mapping\b", "ann", ("http_in",), "route:"),
    ("F1", "Spring MVC", JVM, r"@RequestMapping\b", "ann_member", ("http_in",), "route:"),
    ("F1", "ASP.NET", CS, r"\[\s*Http(?:Get|Post|Put|Delete|Patch)\b", "ann", ("http_in",), "route:"),
    ("F1", "Django", PY, r"\b(?:re_)?path\s*\(", "urls", ("http_in",), "route:"),
    ("F1", "FastAPI", PY, r"@\w+\.(?:get|post|put|delete|patch)\s*\(", "ann", ("http_in",), "route:"),
    ("F1", "Flask", PY, r"@\w+\.(?:route|get|post|put|delete|patch)\s*\(\s*['\"]", "ann", ("http_in",), "route:"),
    ("F1", "Express", JS, r"\b(?:app|router)\.(?:get|post|put|delete|patch)\s*\(\s*['\"`]", "call", ("http_in",), "route:"),
    ("F2", "HttpClient (C#)", CS, r"\.(?:GetAsync|PostAsync|PutAsync|DeleteAsync|PatchAsync|SendAsync)\s*\(", "call", ("http_out",), "http:"),
    ("F2", "JAX-RS client", JVM, r"\.target\s*\(", "call", ("http_out",), "http:"),
    ("F2", "axios/fetch", JS, r"\baxios\s*(?:\.\s*(?:get|post|put|delete|patch|request)\s*)?\(|\bfetch\s*\(", "call", ("http_out",), "http:"),
    ("F3", "JPA", JVM, r"@(?:Entity|Table)\b", "ann", ("persist",), None),
    ("F3", "Spring Data", JVM, r"\bextends\s+(?:[\w.]+\.)?(?:JpaRepository|CrudRepository)\b", "decl", ("persist",), None),
    ("F3", "JDBI", JVM, r"@(?:SqlQuery|SqlUpdate)\b", "ann", ("persist",), None),
    ("F3", "EF Core", CS, r"(?:\bclass\s+\w+.*:\s*.*\bDbContext\b)|\bDbSet\s*<", "decl", ("persist",), None),
    ("F3", "Django models", PY, r"\bmodels\.Model\b", "decl", ("persist",), None),
    ("F3", "SQLAlchemy", PY, r"\bdeclarative_base\b|\bColumn\s*\(", "call", ("persist",), None),
    ("F4", "Dropwizard Jobs", JVM, r"@(?:Every|On|OnApplicationStart)\b", "ann", ("schedule",), None),
    ("F4", "Quartz", JVM, r"\b(?:implements|extends|with)\s+(?:[\w.]+\.)?Job\b", "decl", ("schedule",), None),
    ("F4", "Hangfire", CS, r"\b(?:RecurringJob|BackgroundJob)\.", "call", ("schedule",), None),
    ("F4", "BackgroundService/IHostedService", CS, r"\bclass\s+\w+.*:\s*.*\b(?:BackgroundService|IHostedService)\b", "decl", ("schedule",), None),
    ("F5", "Spring/javax DI", JVM, r"@(?:Component|Service|Repository|Autowired|Inject)\b", "ann", ("di",), None),
    ("F5", "MS DI", CS, r"\.Add(?:Scoped|Singleton|Transient)\s*<", "call", ("di",), None),
    ("F6", "C# IConfiguration", CS, r"\b(?:_?[cC]onfig(?:uration)?)\s*\[\s*\"|\.GetSection\s*\(|\.GetValue\s*<", "call", ("config_read",), None),
    ("F6", "Typesafe config", JVM, r"\b\w*[cC]onf(?:ig)?\w*\.get(?:String|Int|Boolean|Long|Double|Number|Config|StringList|IntList|Duration|Bytes|List|Object|Value|AnyRef)\w*\s*\(", "call", ("config_read",), None),
    ("F7", "Swagger/OpenAPI", JVM, r"@(?:Operation|ApiResponse|Tag|Schema)\b", "ann", ("swagger",), None),
]
FW_RX = [(f, fw, langs, re.compile(rx), mode, ch, tp) for f, fw, langs, rx, mode, ch, tp in FW]
FILE_FILTER = {   # marker only counts when the file also mentions the framework type (the spec names the type, not just the method)
    ("F2", "HttpClient (C#)"): re.compile(r"HttpClient"),
    ("F2", "JAX-RS client"): re.compile(r"WebTarget|ws\.rs\.client"),
    ("F6", "C# IConfiguration"): re.compile(r"IConfiguration|Extensions\.Configuration"),
}
PY_FLASK_IMP = re.compile(r"^\s*(?:from\s+flask\b|import\s+flask\b)", re.M)
PY_FASTAPI_IMP = re.compile(r"^\s*(?:from\s+fastapi\b|import\s+fastapi\b)", re.M)
FLASK_PATH = re.compile(r"@\w+\.\w+\s*\(\s*['\"]([^'\"]*)['\"]")


def py_route_owner(whole, code):
    """Attribute a Python route decorator line to 'Flask' or 'FastAPI' (never both).
    `.route(` is Flask only. Verb shortcuts (`.get(` etc.) are Flask when the file imports flask and not fastapi,
    FastAPI otherwise."""
    if re.search(r"@\w+\.route\s*\(", code):
        return "Flask" if PY_FLASK_IMP.search(whole) else None
    if PY_FLASK_IMP.search(whole) and not PY_FASTAPI_IMP.search(whole):
        return "Flask"
    return "FastAPI"


F_ROWS = ["F1", "F2", "F3", "F4", "F5", "F6", "F7"]


def next_decl(scan, line, within=60):
    best = None
    for it in scan.types + scan.members:
        if it["line"] >= line and it["line"] - line <= within and (best is None or it["line"] < best["line"]):
            best = it
    return best


def type_at(scan, line):
    best = None
    for t in scan.types:
        if t["line"] <= line <= t.get("end", t["line"]) or t["line"] <= line:
            if best is None or t["line"] >= best["line"]:
                best = t
    return best


def enclosing_define(ctx, rel, line):
    best = None
    for d in ctx.defs_in.get(rel, ()):
        if d["kind"] in ("method", "function") and isinstance(d.get("end_line"), int) and d["anchor"]["line"] <= line <= d["end_line"]:
            if best is None or d["anchor"]["line"] >= best["anchor"]["line"]:
                best = d
    return best


def class_route_prefix(scan, ctx_lines, tline):
    """String of a class-level @Path/@RequestMapping right above the type at tline, else ''."""
    for ln in range(tline - 1, max(0, tline - 10), -1):
        txt = ctx_lines[ln - 1] if ln - 1 < len(ctx_lines) else ""
        m = re.search(r"@(?:Path|RequestMapping)\s*\(\s*(?:(?:value|path)\s*=\s*)?\"([^\"]*)\"", txt)
        if m:
            return m.group(1).strip("/")
    txt = ctx_lines[tline - 1] if tline - 1 < len(ctx_lines) else ""
    m = re.search(r"@(?:Path|RequestMapping)\s*\(\s*(?:(?:value|path)\s*=\s*)?\"([^\"]*)\"", txt)
    return m.group(1).strip("/") if m else ""


def framework_sites(ctx, rel, scan):
    """Distinct (fid, framework, key) carrier sites with the marker lines that make them up."""
    lang = ctx.lang(rel)
    base = rel.rsplit("/", 1)[-1]
    sites = {}
    whole = "\n".join(scan.code)
    for ln, code in enumerate(scan.code, 1):
        if not code.strip():
            continue
        for fid, fw, langs, rx, mode, chans, tp in FW_RX:
            if lang not in langs or not rx.search(code):
                continue
            ff = FILE_FILTER.get((fid, fw))
            if ff is not None and not ff.search(whole):
                continue
            if fw in ("Flask", "FastAPI") and lang == "python":
                if py_route_owner(whole, code) != fw:
                    continue
            if mode == "urls" and base != "urls.py":
                continue
            if mode == "call" and fw == "Express" and False:
                continue
            decl = None
            if mode in ("ann", "ann_member"):
                decl = next_decl(scan, ln)
                if decl is None:
                    continue
                if mode == "ann_member" and decl["cat"] != "method":
                    continue   # class-level @RequestMapping is a prefix, not a route
                key = ("decl", decl["line"])
            elif mode == "decl":
                t = type_at(scan, ln)
                decl = t if t is not None and ln - t["line"] <= 6 else next_decl(scan, ln, 0)
                key = ("decl", decl["line"]) if decl else ("line", ln)
            else:
                key = ("line", ln)
            s = sites.setdefault((fid, fw, key), {"fid": fid, "fw": fw, "lines": set(), "decl": decl["line"] if decl else None,
                                                  "decl_cat": decl["cat"] if decl else None, "chans": chans, "tp": tp, "mode": mode})
            s["lines"].add(ln)
    # Dropwizard Configuration getters (F6, Java/Scala)
    if lang in JVM:
        for t in scan.types:
            h = scan.header(t["line"] - 1, upto=3)
            if re.search(r"\bextends\s+(?:[\w.]+\.)?\w*Configuration\b", h):
                for m in scan.members:
                    if m["cat"] == "method" and t["line"] < m["line"] <= t.get("end", m["line"]) and re.match(r"get[A-Z]", m["name"]) and m["np"] == 0:
                        sites[("F6", "Dropwizard Configuration", ("decl", m["line"]))] = {
                            "fid": "F6", "fw": "Dropwizard Configuration", "lines": {m["line"]}, "decl": m["line"],
                            "decl_cat": "method", "chans": ("config_read",), "tp": None, "mode": "getter"}
    return sites


def score_frameworks(ctx, sc: Score, fw_cells):
    for rel in ctx.prod:
        lang = ctx.lang(rel)
        scan = ctx.scan(rel)
        sites = framework_sites(ctx, rel, scan)
        if not sites:
            continue
        signals = ctx.ex["files"].get(rel, {}).get("signals") or []
        for key, s in sorted(sites.items(), key=lambda kv: (kv[0][0], kv[0][1], str(kv[0][2]))):
            fid, fw = s["fid"], s["fw"]
            anchors = set(s["lines"])
            carrier = None
            if s["decl"] is not None:
                anchors.add(s["decl"])
                kinds = {"type": None, "method": ("method", "function"), "field": ("field", "constant")}.get(s["decl_cat"])
                cands = [d for d in ctx.defs_at.get((rel, s["decl"]), ()) if (kinds is None and d["kind"] not in MEMBER_KINDS) or (kinds and d["kind"] in kinds)]
                carrier = cands[0] if cands else None
            elif s["mode"] == "call":
                carrier = enclosing_define(ctx, rel, min(s["lines"]))
            ok = False
            if fid == "F5":
                ok = any(x.startswith("di:") for x in signals)
            elif fid == "F7":
                names = {"Operation", "ApiResponse", "Tag", "Schema"}
                for d in ctx.defs_at.get((rel, s["decl"]), ()) if s["decl"] else ():
                    for an in d.get("annotations") or ():
                        if an.get("name") in names and (not an.get("fqn") or "swagger" in an["fqn"] or "oas" in an["fqn"]):
                            ok = True
            else:
                for e in ctx.edges.get(rel, ()):
                    if e["channel"] not in s["chans"] or e["anchor"]["line"] not in anchors:
                        continue
                    if s["tp"] and not e["target"].startswith(s["tp"]):
                        continue
                    if fw == "Flask":
                        fm = FLASK_PATH.search(line_text(ctx, rel, min(s["lines"]), scan))
                        if fm and not e["target"].endswith(fm.group(1)):
                            continue
                    if carrier is not None and not (e["source"] == carrier["fqn"] or e["source"].startswith(carrier["fqn"] + "#")
                                                    or e["source"].startswith(carrier["fqn"] + ".")):
                        continue
                    if fid == "F1" and lang in JVM:
                        t = type_at(scan, s["decl"] or min(s["lines"]))
                        pref = class_route_prefix(scan, scan.lines, t["line"]) if t else ""
                        if pref and pref not in e["target"]:
                            continue
                    ok = True
                    break
            w = loc_of(rel, min(s["lines"]), ctx)
            sc.cell(fid, lang).add(ok, w)
            fw_cells[(fid, fw)].add(ok, w)
            sc.judge(fid, lang, w, ok, "%s: %s" % (fw, line_text(ctx, rel, min(s["lines"]), scan)))


# ---------------------------------------------------------------- U3 / U4 candidate pools (manual samples)


def simple_type(t):
    t = re.sub(r"<.*>|\[.*\]", "", t or "")
    t = re.sub(r"[?\[\]*&\s]|\bfinal\b|\bref\b|\bout\b|\bin\b", "", t)
    return t.split(".")[-1]


def param_types(m, lang):
    """name -> declared type text from a method item's parameter strings."""
    out = {}
    for p in m.get("params") or ():
        p = re.sub(r"@\w[\w.]*(?:\([^)]*\))?\s*", "", p).strip()
        p = re.sub(r"=.*$", "", p).strip() if lang in ("csharp", "python") else p
        if lang in ("scala", "python", "typescript", "javascript"):
            mm = re.match(r"(?:implicit\s+|val\s+|var\s+)?(\w+)\s*\??\s*:\s*(.+)", p)
            if mm:
                out[mm.group(1)] = mm.group(2).strip()
        else:
            parts = p.rsplit(None, 1)
            if len(parts) == 2:
                out[parts[1]] = re.sub(r"^(?:final|ref|out|in|params|this)\s+", "", parts[0])
    return out


def u3_candidates(ctx):
    out = []
    for rel in ctx.prod:
        lang = ctx.lang(rel)
        if lang not in ("java", "csharp", "scala", "python", "typescript"):
            continue
        scan = ctx.scan(rel)
        fields = {}
        for m in scan.members:
            if m["cat"] == "field" and m.get("ftype"):
                fields.setdefault(m["name"], m["ftype"])
        seen = set()
        for u in ctx.uses_in.get(rel, ()):
            if u.get("kind") != "call":
                continue
            line = u["anchor"]["line"]
            fqn = u["fqn"]
            mname = fqn.split("#")[-1] if "#" in fqn else fqn.rsplit(".", 1)[-1]
            if not mname or line > len(scan.code):
                continue
            rx = re.compile(r"(?<![\w$.])(?:this\.|self\.)?(?P<r>[A-Za-z_$][\w$]*)\s*\.\s*" + re.escape(mname) + r"\s*\(")
            mm = rx.search(scan.code[line - 1])
            if not mm:
                continue
            recv = mm.group("r")
            key = (line, mname, recv)
            if key in seen:
                continue
            kind = rtype = None
            enc = scan.enclosing_member(line)
            if enc is not None:
                pt = param_types(enc, lang)
                if recv in pt:
                    kind, rtype = "param", pt[recv]
            if rtype is None and recv in fields:
                kind, rtype = "field", fields[recv]
            if rtype is None:
                continue
            seen.add(key)
            owner = fqn.split("#")[0] if "#" in fqn else ""
            mech = bool(owner) and simple_type(owner) == simple_type(rtype)
            imps = ctx.import_fqns.get(rel, ())
            # owner is a type declared in the repo, or is named by an import (explicit or wildcard), or is java.lang
            imp = bool(owner) and (owner in ctx.type_fqns or owner.startswith("java.lang.")
                                   or any(owner == i or owner.rsplit(".", 1)[0] == i or (i.endswith("*") and owner.rsplit(".", 1)[0] == i[:-2])
                                          or (lang in ("java", "scala") and i.split(".")[-1][:1].isupper() and owner.startswith(i + "."))
                                          for i in imps))
            out.append({"lang": lang, "repo": ctx.name, "file": rel, "line": line, "method": mname, "recv": recv,
                        "rtype": rtype, "rkind": kind, "use": fqn, "mech": mech, "imp": imp, "text": scan.lines[line - 1].strip()[:120]})
    return sorted(out, key=lambda x: (x["repo"], x["file"], x["line"], x["method"], x["recv"]))


HTTP_RX = {
    "java": r"\b(?:HttpGet|HttpPost|HttpPut|HttpDelete|HttpPatch)\s*\(|\.target\s*\(|\.uri\s*\(|URI\.create\s*\(|new\s+URL\s*\(",
    "scala": r"\.url\s*\(|\.target\s*\(|\.uri\s*\(|URI\.create\s*\(|\buri\"|Http\w*\(|basicRequest\.\w+\s*\(",
    "csharp": r"\.(?:GetAsync|PostAsync|PutAsync|DeleteAsync|PatchAsync|SendAsync|GetStringAsync|GetFromJsonAsync|PostAsJsonAsync|PutAsJsonAsync)\s*\(|new\s+HttpRequestMessage\s*\(|\bRestRequest\s*\(",
    "python": r"\brequests\.\w+\s*\(|\bhttpx\.\w+\s*\(|\burlopen\s*\(|\bsession\.(?:get|post|put|delete|patch)\s*\(",
    "javascript": r"\baxios\s*(?:\.\w+)?\s*\(|\bfetch\s*\(|\bhttp\.(?:get|post|put|delete)\s*\(",
}
HTTP_RX["typescript"] = HTTP_RX["javascript"]
SQL_RX = {
    "java": r"\.prepareStatement\s*\(|\.createStatement|\.executeQuery\s*\(|\.executeUpdate\s*\(|\.createQuery\s*\(|\.createNativeQuery\s*\(|\.update\s*\(|\.query\s*\(|\.queryForObject\s*\(|\.createUpdate\s*\(|\.prepareCall\s*\(",
    "scala": r"\.prepareStatement\s*\(|\.executeQuery\s*\(|\.executeUpdate\s*\(|\.createQuery\s*\(|\.createUpdate\s*\(|\.query\s*\(|\.update\s*\(|\bsql\s*\(",
    "csharp": r"new\s+SqlCommand\s*\(|\bCommandText\s*=|\.ExecuteSqlRaw\s*\(|\.FromSqlRaw\s*\(|\.ExecuteSqlInterpolated\s*\(|\.Query(?:<\w+>)?\s*\(|\.Execute(?:Scalar)?\s*\(|new\s+NpgsqlCommand\s*\(|new\s+MySqlCommand\s*\(",
    "python": r"\.execute(?:many)?\s*\(|\bpd\.read_sql\w*\s*\(|\.text\s*\(",
    "javascript": r"\.query\s*\(|\.execute\s*\(|\.raw\s*\(",
}
SQL_RX["typescript"] = SQL_RX["javascript"]
SQL_CHANNELS = ("persist", "read", "write", "schema_own")


def u4_candidates(ctx):
    """HTTP/SQL call lines whose argument joins a constant with something else (URL-like / SQL-like constants only)."""
    consts = collections.defaultdict(dict)   # file -> name -> value
    global_vals = collections.defaultdict(set)
    for d in ctx.ex["defines"]:
        if d["kind"] == "constant" and isinstance(d.get("value"), str) and d["value"]:
            nm = re.split(r"[.#]", d["fqn"])[-1]
            consts[d["file"]][nm] = d["value"]
            global_vals[nm].add((d["fqn"], d["value"]))
    url_like = re.compile(r"^(?:https?://|/)|/")
    sql_like = re.compile(r"\b(?:select|insert|update|delete|exec|execute|call|with|merge)\b", re.I)
    out = []
    for rel in ctx.prod:
        lang = ctx.lang(rel)
        scan = ctx.scan(rel)
        names = dict(consts.get(rel, {}))
        hrx, srx = re.compile(HTTP_RX[lang]), re.compile(SQL_RX[lang])
        for i, code in enumerate(scan.code, 1):
            which = None
            m = hrx.search(code)
            if m:
                which = "http"
            else:
                m = srx.search(code)
                if m:
                    which = "sql"
            if not m:
                continue
            blk = "\n".join(scan.code[i - 1:i + 5])
            orig = "\n".join(scan.lines[i - 1:i + 5])
            p = blk.find("(", m.start())
            if p < 0:
                continue
            end, ok = balanced(blk, p)
            arg = orig[p:end]
            like = url_like if which == "http" else sql_like
            hit = None
            for nm in sorted(set(re.findall(r"[A-Za-z_]\w*", arg))):
                if len(nm) < 3 or nm in ("true", "false", "null"):
                    continue
                val = names.get(nm)
                if val is None:
                    q = re.search(r"\b(\w+)\." + re.escape(nm) + r"\b", arg)
                    cands = [v for f, v in global_vals.get(nm, ()) if q and f.endswith(q.group(1) + "." + nm)]
                    allcap = nm.isupper() and len({v for f, v in global_vals.get(nm, ())}) == 1
                    val = cands[0] if cands else (next(iter(global_vals[nm]))[1] if allcap else None)
                nm_like = re.compile(r"url|uri|path|endpoint|route|host|base|api", re.I) if which == "http" else re.compile(r"sql|query|stmt|statement|command|cmd", re.I)
                if not val or not (like.search(val) or nm_like.search(nm)):
                    continue
                n = re.escape(nm)
                if re.search(r"\b" + n + r"\b\s*\+|\+\s*(?:\w+\.)?\b" + n + r"\b|\{\s*" + n + r"\b|format\s*\(\s*(?:\w+\.)?" + n + r"\b|\b" + n + r"\.(?:formatted|concat)\(|\$\{" + n + r"\b", arg):
                    hit = (nm, val)
                    break
            if not hit:
                continue
            chans = ("http_out",) if which == "http" else SQL_CHANNELS
            edges = [e for e in ctx.edges.get(rel, ()) if e["channel"] in chans and i <= e["anchor"]["line"] <= i + 4]
            mech = any(hit[1] in e["target"] for e in edges) if which == "http" else bool(edges)
            out.append({"lang": lang, "repo": ctx.name, "file": rel, "line": i, "which": which, "const": hit[0], "value": hit[1][:70],
                        "targets": sorted({e["target"][:80] for e in edges})[:3], "mech": mech, "text": scan.lines[i - 1].strip()[:120]})
    return out


# ---------------------------------------------------------------- health (H1-H4)

EXT_LANG = {"java": "java", "cs": "csharp", "scala": "scala", "py": "python", "ts": "typescript", "tsx": "typescript", "js": "javascript"}
TESTDIR_RX = [re.compile(p) for p in (
    r"^[^/]+\.(?:Unit|Integration|Functional|Component|Acceptance)?(?:Tests?|Specs?)$",   # .NET test project dir
    r"^.+-(?:tests?|it)$",                                                                 # build module foo-test(s) / foo-it
    r"^(?:tests|__tests__)$",
)]


def under_test_project(path):
    segs = path.split("/")
    for k, seg in enumerate(segs[:-1]):
        if any(rx.match(seg) for rx in TESTDIR_RX):
            return True
        if seg == "src" and k + 1 < len(segs) - 1 and segs[k + 1] in ("test", "it", "integrationTest"):
            return True
    return False


def score_h4(ctx, out):
    for p, f in ctx.files.items():
        ext = p.rsplit(".", 1)[-1] if "." in p.rsplit("/", 1)[-1] else ""
        exp = EXT_LANG.get(ext)
        if not exp:
            continue
        c = out["H4a"].setdefault(exp, Cell())
        c.add(f["language"] == exp, "%s/%s (label %s)" % (ctx.name, p, f["language"]))
        r = out["H4b"].setdefault(exp, Cell())
        in_test = under_test_project(p)
        if in_test:
            r.add(f["role"] == "test", "%s/%s (role %s, under a test project)" % (ctx.name, p, f["role"]))
        elif f["role"] == "test":
            r.extra["role_test_outside_test_project_info"] += 1
            if len(r.extra) and r.note.count("\n") < 10:
                r.note += "%s/%s\n" % (ctx.name, p)


def score_h1(ctx, out):
    """extractor_error notes. The extraction keeps notes per module (de-duplicated, no file), so when any exist the
    production files are re-extracted one by one (same `extract_file` the scan uses) to attribute them to files."""
    notes = [n for v in ctx.ex["module_notes"].values() for n in v if n.startswith("extractor_error")]
    out["notes"][ctx.name] = notes
    for rel in ctx.prod_all:
        out["H1files"][ctx.lang(rel)] += 1
    if notes:
        from cdp.lang import extract_file
        for rel in ctx.prod_all:
            facts = extract_file(rel, ctx.read_lines(ctx.repo / rel), ctx.files[rel]["module"])
            for n in facts.notes:
                if n.startswith("extractor_error"):
                    out["H1err"][ctx.lang(rel)] += 1
                    out["H1where"].append("%s/%s (%s)" % (ctx.name, rel, n[:80]))
    return notes


def read_h3(db_path, snapshots_wanted):
    """H3 from the stored scan, read-only. Returns ({repo: info}, {lang: Counter})."""
    uri = "file:%s?mode=ro" % db_path
    con = sqlite3.connect(uri, uri=True)
    info, per_lang = {}, collections.defaultdict(collections.Counter)
    for name in snapshots_wanted:
        row = con.execute("SELECT id, repo_id, commit_sha, created_at FROM snapshot_meta WHERE complete=1 AND repo_id LIKE ? ORDER BY id DESC LIMIT 1",
                          ("%/" + name,)).fetchone()
        if not row:
            info[name] = {"found": False}
            continue
        sid = row[0]
        info[name] = {"found": True, "snapshot_id": sid, "repo_id": row[1], "commit": row[2], "created_at": row[3]}
        q = ("SELECT p.s, l.s, r.s, f.xseg FROM snapshot_file f JOIN str p ON p.id=f.path_id JOIN str l ON l.id=f.lang_id "
             "JOIN str r ON r.id=f.role_id WHERE f.snapshot_id=? AND f.xseg IS NOT NULL")
        nfiles = 0
        for path, lang, role, xseg in con.execute(q, (sid,)).fetchall():
            if role != "source" or lang not in LANGS:
                continue
            z = con.execute("SELECT z FROM seg WHERE id=?", (xseg,)).fetchone()
            if not z:
                continue
            nfiles += 1
            for u in json.loads(zlib.decompress(bytes(z[0]))).get("uses") or ():
                if u.get("kind") in ("call", "type"):
                    per_lang[lang][u.get("resolved")] += 1
        info[name]["source_files_read"] = nfiles
    con.close()
    return info, per_lang


# ---------------------------------------------------------------- rendering


def fmt_pct(c, fid):
    if c.p == 0:
        return "0 present"
    pct = 100.0 * c.e / c.p
    mark = PASS_MARK.get(fid[0])
    bad = mark is not None and fid != "M3" and pct < mark
    return "%d%% (%d/%d)%s" % (int(pct), c.e, c.p, " ❌" if bad else "")


def is_bad(c, fid):
    mark = PASS_MARK.get(fid[0])
    return bool(c.p) and mark is not None and fid != "M3" and 100.0 * c.e / c.p < mark


NA = {
    "G2": {"javascript"}, "G3": {"javascript"}, "M1": {"javascript"}, "M2": {"javascript"}, "M3": {"javascript"},
    "R2": {"python", "javascript"}, "U3": {"javascript"},
}
for _fid in F_ROWS:
    NA.setdefault(_fid, set()).update(l for l in LANGS if not any(l in langs for f, _fw, langs, *_r in FW if f == _fid))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out-dir", default=str(ROOT))
    ap.add_argument("--db", default=str(Path.home() / ".cdp" / "index.db"))
    ap.add_argument("--repos", nargs="*", default=REPOS)
    ap.add_argument("--dump-samples", help="write the U3/U4 manual-sample listing to this path and exit after scoring")
    args = ap.parse_args()
    t_start = time.time()
    before = {r: git_status(Path.home() / "git" / r) for r in args.repos}

    sc = Score()
    fw_cells = collections.defaultdict(Cell)
    h4 = {"H4a": {}, "H4b": {}}
    h1 = {"notes": {}, "H1files": collections.Counter(), "H1err": collections.Counter(), "H1where": []}
    u3_all, u4_all, repo_info = [], [], {}
    for name in args.repos:
        data = load_repo(name)
        ctx = Ctx(name, data)
        score_code_facts(ctx, sc)
        score_uses(ctx, sc)
        score_frameworks(ctx, sc, fw_cells)
        score_h4(ctx, h4)
        notes = score_h1(ctx, h1)
        u3_all += u3_candidates(ctx)
        u4_all += u4_candidates(ctx)
        parsed_loc = sum(f["loc"] for f in ctx.ex["files"].values())
        repo_info[name] = {"head": ctx.inv["head"], "production_files": len(ctx.prod_all), "scored_files": len(ctx.prod), "excluded_d4": len(ctx.excluded), "files": len(ctx.files),
                           "by_language_production": dict(collections.Counter(ctx.lang(p) for p in ctx.prod_all)),
                           "timing_s": {k: round(v, 2) for k, v in ctx.t.items()}, "parsed_loc": parsed_loc,
                           "kloc_per_s_extract": round(parsed_loc / 1000 / ctx.t["extract"], 2),
                           "workers": os.cpu_count(), "extractor_error_notes": len(notes)}
        ctx.scans.clear()
    after = {r: git_status(Path.home() / "git" / r) for r in args.repos}

    # R2: is anything like extends/implements-kind emitted on any define?
    r2_keys = set()
    # (checked on the last loaded extraction per repo is not retained; recompute cheaply from the cells' defines below)
    h3_info, h3 = read_h3(args.db, args.repos)

    rng = random.Random(SEED)
    u3_sample = {}
    for lang in ("java", "csharp", "scala", "python", "typescript"):
        pool = [c for c in u3_all if c["lang"] == lang]
        u3_sample[lang] = {"pool": len(pool), "items": rng.sample(pool, min(50, len(pool)))}
    u4_sample = {}
    for lang in LANGS:
        pool = [c for c in u4_all if c["lang"] == lang]
        u4_sample[lang] = {"pool": len(pool), "items": rng.sample(pool, min(20, len(pool)))}
    if args.dump_samples:
        with open(args.dump_samples, "w") as fh:
            for lang, s in u3_sample.items():
                for c in s["items"]:
                    fh.write("U3|%s|%s|%d|%s|%s\t%s %s %s: %s -> %s | mech=%s | %s\n" % (c["repo"], c["file"], c["line"], c["method"], c["recv"], lang, c["rkind"], c["recv"], c["rtype"], c["use"], "%s/imp=%s" % (c["mech"], c["imp"]), c["text"]))
            for lang, s in u4_sample.items():
                for c in s["items"]:
                    fh.write("U4|%s|%s|%d|%s\t%s %s %s=%r | mech=%s targets=%s | %s\n" % (c["repo"], c["file"], c["line"], c["const"], lang, c["which"], c["const"], c["value"], c["mech"], c["targets"], c["text"]))
    report = build_report(args, sc, fw_cells, h4, h1, h3_info, h3, u3_sample, u4_sample, repo_info, before, after, time.time() - t_start)
    return report


def verdict_cell(samples, prefix, keyfn, lang):
    c = Cell()
    unjudged = 0
    for it in samples[lang]["items"]:
        v = MANUAL_VERDICTS.get(keyfn(prefix, it))
        if v is None:
            unjudged += 1
            continue
        v = v.split(":")[0]
        if v == "x":
            c.extra["not_a_valid_candidate"] += 1
            continue
        c.add(v == "y", "%s/%s:%d" % (it["repo"], it["file"], it["line"]))
    c.extra["unjudged"] = unjudged
    c.extra["pool"] = samples[lang]["pool"]
    return c


def u3_key(prefix, it):
    return "%s|%s|%s|%d|%s|%s" % (prefix, it["repo"], it["file"], it["line"], it["method"], it["recv"])


def u4_key(prefix, it):
    return "%s|%s|%s|%d|%s" % (prefix, it["repo"], it["file"], it["line"], it["const"])


def build_report(args, sc, fw_cells, h4, h1, h3_info, h3, u3_sample, u4_sample, repo_info, before, after, runtime):
    out_dir = Path(args.out_dir)
    table, misses_out, raw = [], [], {}
    cells = {}

    def put(fid, lang, text, c=None, bad=False):
        cells[(fid, lang)] = (text, c, bad)

    for fid in ["S1", "S2", "S3", "S4", "G1", "G2", "G3", "G4", "M1", "M2", "M3", "R1", "R3"] + F_ROWS:
        for lang in LANGS:
            if lang in NA.get(fid, ()):
                put(fid, lang, "N/A")
                continue
            c = sc.cells[fid].get(lang) or Cell()
            put(fid, lang, fmt_pct(c, fid), c, is_bad(c, fid))
    # R2
    for lang in LANGS:
        if lang in NA["R2"]:
            put("R2", lang, "N/A")
        else:
            c = sc.cells["R2"].get(lang) or Cell()
            found = sorted(k for (l, k) in sc.r2_keys if l == lang)
            put("R2", lang, ("not emitted anywhere (0/%d)" % c.p if not found else "fields found %s (not scored)" % found) if c.p else "0 present", c)
    # U1 / U2
    for lang in LANGS:
        c = sc.cells["U1"].get(lang) or Cell()
        loc = c.extra["loc"]
        put("U1", lang, "%.1f type uses/kLOC (%d/%d)" % (1000.0 * c.p / loc, c.p, loc) if loc else "0 present", c)
        c = sc.cells["U2"].get(lang) or Cell()
        loc = c.extra["loc"]
        if loc and c.p:
            put("U2", lang, "%d%% (%d/%d) from_symbol; %.1f calls/kLOC%s" % (int(100.0 * c.e / c.p), c.e, c.p, 1000.0 * c.extra["calls"] / loc,
                                                                            " ❌" if is_bad(c, "U2") else ""), c, is_bad(c, "U2"))
        else:
            put("U2", lang, "0 present", c)
    # U3 / U4 (manual)
    for lang in LANGS:
        if lang in NA["U3"]:
            put("U3", lang, "N/A")
        else:
            c = verdict_cell(u3_sample, "U3", u3_key, lang)
            note = " [%d unjudged]" % c.extra["unjudged"] if c.extra["unjudged"] else ""
            put("U3", lang, (fmt_pct(c, "U3") if c.p else "0 present") + note + (" (pool %d)" % c.extra["pool"] if c.p else ""), c, is_bad(c, "U3"))
        c = verdict_cell(u4_sample, "U4", u4_key, lang)
        note = " [%d unjudged]" % c.extra["unjudged"] if c.extra["unjudged"] else ""
        put("U4", lang, (fmt_pct(c, "U4") if c.p else "0 present") + note + (" (pool %d)" % c.extra["pool"] if c.p else ""), c, is_bad(c, "U4"))
    # H1 / H2 / H3 / H4
    nerr = sum(len(v) for v in h1["notes"].values())
    for lang in LANGS:
        n = h1["H1files"].get(lang, 0)
        e = h1["H1err"].get(lang, 0)
        put("H1", lang, "%.1f per 1000 files (%d/%d)" % (1000.0 * e / n, e, n) if n else "0 present")
    ksum = sum(r["parsed_loc"] for r in repo_info.values()) / 1000.0
    tsum = sum(r["timing_s"]["extract"] for r in repo_info.values())
    for lang in LANGS:
        put("H2", lang, "%.1f kLOC/s pooled, all languages (%s)" % (ksum / tsum, ", ".join("%s %.1f" % (k, v["kloc_per_s_extract"]) for k, v in repo_info.items())))
    for lang in LANGS:
        cn = h3.get(lang)
        if not cn:
            put("H3", lang, "0 present")
            continue
        tot = sum(cn.values())
        r = cn.get("local", 0) + cn.get("matched", 0)
        other = tot - r - cn.get("third_party", 0) - cn.get("ambiguous", 0) - cn.get("unresolved", 0)
        put("H3", lang, "%d%% (%d/%d) resolved; third_party %.0f%%, ambiguous %.0f%%, unresolved %.0f%%, other %.0f%%" % (
            int(100.0 * r / tot), r, tot, 100.0 * cn.get("third_party", 0) / tot, 100.0 * cn.get("ambiguous", 0) / tot,
            100.0 * cn.get("unresolved", 0) / tot, 100.0 * other / tot))
    for fid in ("H4a", "H4b"):
        for lang in LANGS:
            c = h4[fid].get(lang) or Cell()
            put(fid, lang, ("%d%% (%d/%d)" % (int(100.0 * c.e / c.p), c.e, c.p) + ("" if c.e == c.p else " ❌")) if c.p else "0 present", c, bool(c.p and c.e != c.p))

    order = ["S1", "S2", "S3", "S4", "G1", "G2", "G3", "G4", "M1", "M2", "M3", "R1", "R2", "R3", "U1", "U2", "U3", "U4"] + F_ROWS + ["H1", "H2", "H3", "H4a", "H4b"]
    names = {"H4a": "H4 (language label)", "H4b": "H4 (role)"}
    hdr = "| Fact | " + " | ".join(l + (" (provisional)" if l in PROVISIONAL else "") for l in LANGS) + " |"
    table = [hdr, "|---|" + "---|" * len(LANGS)]
    for fid in order:
        table.append("| %s | %s |" % (names.get(fid, fid), " | ".join(cells[(fid, l)][0] for l in LANGS)))

    # misses for bad cells
    for fid in order:
        for lang in LANGS:
            text, c, bad = cells[(fid, lang)]
            if bad and c is not None:
                ex = c.misses[:MAX_MISSES]
                misses_out.append("- **%s / %s** %s: %s" % (names.get(fid, fid), lang, text.split(" ❌")[0], "; ".join("`%s`" % m for m in ex) or "(no location recorded)"))

    # per-framework table
    fwrows = ["| Fact | Framework | Emitted/Present | Result |", "|---|---|---|---|"]
    for (fid, fw), c in sorted(fw_cells.items()):
        fwrows.append("| %s | %s | %d/%d | %s |" % (fid, fw, c.e, c.p, (("%d%%" % int(100.0 * c.e / c.p)) + (" ❌" if 100.0 * c.e / c.p < 90 else "")) if c.p else "0 present"))
        if c.p and 100.0 * c.e / c.p < 90:
            misses_out.append("- **%s / %s (per framework)** %d%%: %s" % (fid, fw, int(100.0 * c.e / c.p), "; ".join("`%s`" % m for m in c.misses[:MAX_MISSES])))

    rng2 = random.Random(SEED + 1)
    jp = rng2.sample(sc.judg_present, min(10, len(sc.judg_present)))
    okset = {(f, l, w) for f, l, w, t in sc.judg_emitted}
    je = rng2.sample(sc.judg_emitted, min(10, len(sc.judg_emitted)))

    manual_u3 = []
    for lang, s in u3_sample.items():
        for it in s["items"]:
            v = MANUAL_VERDICTS.get(u3_key("U3", it), "unjudged")
            manual_u3.append("| %s | `%s/%s:%d` | %s %s: %s | `%s` | %s | %s |" % (lang, it["repo"], it["file"], it["line"], it["rkind"], it["recv"], it["rtype"], it["use"], "yes" if it["mech"] else "no", v))
    manual_u4 = []
    for lang, s in u4_sample.items():
        for it in s["items"]:
            v = MANUAL_VERDICTS.get(u4_key("U4", it), "unjudged")
            manual_u4.append("| %s | `%s/%s:%d` | %s %s=%r | %s | %s | %s |" % (lang, it["repo"], it["file"], it["line"], it["which"], it["const"], it["value"][:40], "; ".join(it["targets"])[:90] or "-", "yes" if it["mech"] else "no", v))

    same = all(before[r] == after[r] for r in before)
    h3_lines = []
    for name, i in h3_info.items():
        if not i.get("found"):
            h3_lines.append("- %s: **no complete snapshot in ~/.cdp/index.db; H3 for this repo not computed (no rescan done).**" % name)
        else:
            h3_lines.append("- %s: snapshot %d (repo_id `%s`, commit `%s`, created %s), %d production source files read. Current checkout HEAD: `%s`." % (
                name, i["snapshot_id"], i["repo_id"], i["commit"], i["created_at"], i["source_files_read"], repo_info[name]["head"]))

    md = []
    md.append("# SCORECARD\n")
    md.append("Generated by `python3 scripts/extraction_scorecard.py` (spec: EXTRACTION_METRICS.md). Seed %d. Runtime %.0f s. Corpus: %s. Production files only (role = source). "
              "Columns marked provisional per owner decision 1 (no file is labelled `typescript` by the inventory; `.ts/.tsx` count under `javascript`). "
              "Pass marks: 95%% S/G/M/R/U, 90%% F; ❌ = below mark.\n" % (SEED, runtime, ", ".join(repo_info)))
    md.append("\n".join(table) + "\n")
    md.append("## Example misses for each ❌ cell (up to %d)\n" % MAX_MISSES)
    md.append("\n".join(misses_out) or "(none)")
    md.append("\n## Framework rows split by framework (F cells above are per language)\n")
    md.append("\n".join(fwrows) + "\n")
    md.append("## Text-check judgments (seed %d)\n" % (SEED + 1))
    md.append("Ten random \"present\" judgments (a text check decided the construct is there; emitted = whether the facts matched):\n")
    for f, l, w, t in jp:
        md.append("- %s/%s `%s` emitted=%s: `%s`" % (f, l, w, "yes" if (f, l, w) in okset else "no", t))
    md.append("\nTen random \"emitted\" judgments (present and the facts matched):\n")
    for f, l, w, t in je:
        md.append("- %s/%s `%s`: `%s`" % (f, l, w, t))
    md.append("\n## U3 manual sample (seed %d; up to 50 per language; verdict y/n by hand, x = not a valid candidate)\n" % SEED)
    md.append("| lang | call | receiver (declared type) | use fqn | mechanical match | verdict |\n|---|---|---|---|---|---|")
    md.extend(manual_u3)
    md.append("\n## U4 manual sample (seed %d; up to 20 per language)\n" % SEED)
    md.append("| lang | call | constant | edge targets | mechanical | verdict |\n|---|---|---|---|---|---|")
    md.extend(manual_u4)
    md.append("\n## Per-repo health\n")
    md.append("| repo | production files | extract s | parsed kLOC | kLOC/s | extractor_error notes |\n|---|---|---|---|---|---|")
    for n, r in repo_info.items():
        md.append("| %s | %d | %.1f | %.1f | %.1f | %d |" % (n, r["production_files"], r["timing_s"]["extract"], r["parsed_loc"] / 1000.0, r["kloc_per_s_extract"], r["extractor_error_notes"]))
    md.append("\nextractor_error files (H1):\n")
    md.extend("- `%s`" % w for w in h1["H1where"][:10])
    md.append("\nH3 sources:\n")
    md.extend(h3_lines)
    md.append("\n## Repo state before/after\n")
    for r in before:
        md.append("- %s before == after: **%s**" % (r, "yes" if before[r] == after[r] else "NO"))
    md.append("\n```\n" + "\n".join("%s: %s" % (r, before[r].replace("\n", " | ")) for r in before) + "\n```\n")
    md.append("All %d repos unchanged: **%s**\n" % (len(before), "yes" if same else "NO"))
    md.append(HOW_PRODUCED.replace("\n\n", "\n\n- **Corpus (%d repos, ~/git/<name>):** %s.\n" % (len(repo_info), ", ".join(repo_info)), 1))
    md.append(READING)
    (out_dir / "SCORECARD.md").write_text("\n".join(md) + "\n")

    raw = {"seed": SEED, "runtime_s": round(runtime, 1), "repos": repo_info, "git_before": before, "git_after": after,
           "h3_snapshots": h3_info, "h3_counts": {l: dict(c) for l, c in h3.items()},
           "cells": {}, "frameworks": {"%s|%s" % k: {"emitted": c.e, "present": c.p, "misses": c.misses[:50]} for k, c in fw_cells.items()},
           "u3_samples": {l: {"pool": s["pool"], "items": [dict(it, verdict=MANUAL_VERDICTS.get(u3_key("U3", it))) for it in s["items"]]} for l, s in u3_sample.items()},
           "u4_samples": {l: {"pool": s["pool"], "items": [dict(it, verdict=MANUAL_VERDICTS.get(u4_key("U4", it))) for it in s["items"]]} for l, s in u4_sample.items()},
           "judgments_present": [list(x) + [(x[0], x[1], x[2]) in okset] for x in jp], "judgments_emitted": [list(x) for x in je],
           "h1_notes": h1["notes"], "h1_error_files": h1["H1where"], "r2_extra_keys_found": {"%s|%s" % k: v for k, v in sc.r2_keys.items()}}
    for (fid, lang), (text, c, bad) in cells.items():
        raw["cells"]["%s|%s" % (fid, lang)] = {"text": text, "bad": bad, "emitted": c.e if c else None, "present": c.p if c else None,
                                              "extra": dict(c.extra) if c else None, "misses": c.misses[:50] if c else None}
    (out_dir / "scorecard.json").write_text(json.dumps(raw, indent=1, sort_keys=True, default=str))
    return "\n".join(table)


HOW_PRODUCED = """## How each number was produced

- **Facts:** per repo `cdp.inventory.build_inventory`, `cdp.extract.run_extract(repo, inventory)` (default parallel workers, no cache), `cdp.rules.apply(extraction, repo=repo)`; framework edges = `io_edges` + `rule_edges`. Production file = inventory role `source`; language = inventory `language`.
- **Present (S1, S2, G1-G3, M1, R1, R3):** text checks over each file with comments and string contents blanked (`scripts/extraction_scorecard.py`, class `Scan`). Brace depth tracks the enclosing type body, so only members declared directly in a type body (or top-level functions/constants in Python/TS/JS) are counted; local variables and nested statements are not. Enum constants, C# properties (counted separately in scorecard.json as `csharp_properties_present_not_scored`) and Scala case-class parameters are not counted as members.
- **Emitted (S1, S2, G1-G3, M1, R1, R3):** a define (or import) in the file facts whose `anchor.line` / import `line` equals the declaration line (M1: `len(annotations)` capped at the number present).
- **S3, S4, G4, M2, M3, U1, U2:** computed from the facts only. S3/S4/G4 cover all defines in production files; S4 reads `package`/`namespace` from the source text (Python/JS/TS have no package keyword, so only the `#`/`.` separator rule is checked there).
- **R2:** denominator = R1-present types; nothing is emitted on any define for extends-vs-implements.
- **F1-F7:** per framework, the marker regexes in `FW` (script) over blanked source give distinct carrier sites (annotation + its declaration, a call line, or a type header). Emitted = an edge of the listed channel in the same file, anchored on a marker line or the declaration line, with `route:`/`http:` target prefix for F1/F2, whose `source` is the carrier define (or a member of it). F1 on JVM also requires the class-level `@Path`/`@RequestMapping` string to be inside the target. F5 = a `di:` signal on the file. F7 = the declaration's define lists the annotation with a swagger fqn. JVM markers are applied to Java and Scala.
- **U3 / U4:** candidate pools are built mechanically (U3: call use whose `recv.method(` receiver is a typed field or parameter of the enclosing method; U4: HTTP/SQL call line whose arguments combine a known constant with another operand). Samples are drawn with `random.Random(%d)`; each sampled call is listed above with file:line and the verdict recorded by hand (`MANUAL_VERDICTS` in the script). The "mechanical" column is only a pre-check.
- **H1:** `extractor_error` notes in the extraction `module_notes`. **H2:** parsed lines (sum of per-file `loc` in the extraction) / wall-clock seconds of `run_extract` (one run per repo, parallel workers, includes process start-up).
- **H3:** newest complete snapshot per repo in `~/.cdp/index.db`, opened with `mode=ro`; segments decoded directly; production source files; `call` and `type` uses; resolved = `local` + `matched`.
- **H4:** extension vs inventory `language` for every `.java .cs .scala .py .ts .tsx .js` file (all roles); role: files under a test project (a directory named `*.Tests`, `*.UnitTests`, `*.IntegrationTests`, `*-test(s)`, `*-it`, `tests`, `__tests__`, or `src/test|it|integrationTest`) must have role `test`. Files with role `test` outside those directories are only counted in scorecard.json.
""" % SEED


READING = """
## Reading decisions where the spec was silent

- G2 counts `void` as a declared return type (counts split in scorecard.json: `void_present`, `void_emitted`).
- C# properties are not counted as fields in S2/G3 (spec lists method, function, field, constant); their counts are in scorecard.json (`csharp_properties_present_not_scored`, `csharp_properties_with_define_at_line`). Enum constants and Scala constructor parameters are likewise not counted.
- S3/S4/G4 take "every define" literally: all define kinds in production files, including C# `table` defines.
- F rows: each cell is that language's share of the framework; the per-framework table gives the framework totals. JVM-library markers (Spring, JPA, Quartz, Dropwizard Jobs, Typesafe, Swagger) are applied to Java and Scala alike. A class-level `@RequestMapping` is not counted (it is a prefix, not a route). C# `.GetAsync`-style calls count only in files that mention `HttpClient`; JAX-RS `.target(` only in files mentioning `WebTarget`/`ws.rs.client`; C# `GetSection/GetValue/[]` only in files mentioning `IConfiguration`.
- H1 is attributed to files by re-running `extract_file` on production files because the scan keeps notes per module only; H2 is one pooled number per repo (time is not split by language), repeated in each column.
- H4 has two rows: language label vs extension, and role for files under test projects.
- `typescript` column: the inventory never labels a file `typescript` (decision 1), so it shows `0 present`; `.ts/.tsx` files are in the `javascript` column, where spec N/A cells (G2, G3, M1-M3, R2, U3) stay N/A.
- R2: `uses` rows of kind `extends`/`implements` exist, but no define carries a base-type kind, so R2 reads "not emitted anywhere".
- U4: the mechanical pool of calls joining a URL-like/SQL-like constant with another operand is small (see the pool size in each cell); every sampled call is listed.
"""


# BEGIN MANUAL VERDICTS
# Hand verdicts for the U3/U4 samples (key TAB verdict). Rule applied while reading each listed call: U3 y = the use fqn owner is a
# type declared in the repo or named by an import of that file; n = anything else (every n was checked by looking up the declared
# types of that simple name in the repo). U4 n = the call is the described pattern but no edge target carries the constant's value.
# A sample not in this table prints as "unjudged".
MANUAL_VERDICTS_RAW = """
U3|data-lake|risk-data-lake/risk-data-lake-dal/src/main/java/com/rms/riskdatalake/dal/repositories/impl/TenantRepositoryImpl.java|233|getByStatus|tenantDao	y
U3|data-lake|risk-data-lake/risk-data-lake-service/src/main/java/com/rms/riskdatalake/service/services/TenantService.java|367|generateSettingForTenantAdminUsers|settingService	y
U3|data-lake|risk-data-lake/risk-data-lake-migration/src/main/java/com/rms/riskdatalake/initializer/RunMigration.java|80|getOptionalValue|configProvider	y
U3|unified-store|sql-pool/sql-pool-provision/src/main/java/rms/unifiedstore/sqlpool/provision/cloudservices/ResourceResponseHelper.java|44|getStatus|resourceResponse	y
U3|unified-store|exposure-snapshot/snapshot-api/src/main/java/com/rms/unifiedstore/snapshot/api/resources/ExposureVariationsResource.java|260|enabled|featureFlagService	y
U3|workflow-service|workflow-service/workflow-service-qe-setup/src/main/java/com/rms/workflowqe/setup/provisioner/DataProvision.java|50|getConfigProvider|context	y
U3|data-lake|risk-data-lake/rdl-sql-validator/src/main/java/com/rms/riskdatalake/sqlvalidator/semantic/RdlSqlSemanticValidator.java|114|getText|ctx	y
U3|data-lake|db-replication/db-replication-core/replication-core-publisher/src/main/java/com/rms/replication/publisher/service/DataReaderService.java|22|getTableColumns|tableDao	y
U3|unified-store|exposure-snapshot/snapshot-api/src/main/java/com/rms/unifiedstore/snapshot/api/resources/EntityVariationResource.java|339|getAwsS3SecretKey|snapshotConfiguration	y
U3|unified-store|exposure-snapshot/entity-variation-task/src/main/java/com/rms/unifiedstore/entityvariation/helper/PortfolioProcessor.java|521|getVariationName|engineInput	y
U3|unified-store|client-java/uds-client/src/main/java/com/rms/unifiedstore/UnifiedStoreClientImpl.java|3701|getUserName|user	y
U3|unified-store|exposure-snapshot/entity-variation-task/src/main/java/com/rms/unifiedstore/entityvariation/dao/ExposureVariationJobsTableManager.java|41|getWorkflowId|exposureVariationJobs	y
U3|data-lake|risk-data-lake/risk-data-lake-service/src/main/java/com/rms/riskdatalake/service/services/GroupUserService.java|569|getTenantId|tenant	y
U3|unified-store|client-java/uds-client/src/main/java/com/rms/unifiedstore/AdminServiceImpl.java|50|getUserName|user	y
U3|unified-store|sql-pool/sql-pool-service/src/main/java/rms/unifiedstore/sqlpool/service/services/ServerService.java|265|setCapacity|server	n:own-namespace-fallback
U3|unified-store|exposure-snapshot/entity-variation-task/src/main/java/com/rms/unifiedstore/entityvariation/dao/ExposureVariationJobsTableManager.java|43|getSurrogateJobId|exposureVariationJobs	y
U3|unified-store|exposure-snapshot/snapshot-api/src/main/java/com/rms/unifiedstore/snapshot/api/helper/SnapshotDbHelper.java|39|insertExposureVariationJobs|dbCommunicator	y
U3|data-lake|odin/domain/odin-reporting/src/main/java/com/moodys/odin/domain/reporting/service/DashboardTemplateService.java|120|getFolderArn|dashboardRegistrationConnector	y
U3|data-lake|risk-data-lake/risk-data-lake-service/src/main/java/com/rms/riskdatalake/service/services/ReportingService.java|119|isFeatureEnabled|featureFlagHandler	y
U3|unified-store|exposure-snapshot/snapshot-api/src/main/java/com/rms/unifiedstore/snapshot/api/irp/variation/ExposureVariationsImpl.java|264|getUdsApi|snapshotConfiguration	y
U3|unified-store|sql-pool/sql-pool-service/src/main/java/rms/unifiedstore/sqlpool/service/services/ReservationService.java|789|getPoolId|reservation	n:own-namespace-fallback
U3|data-lake|risk-data-lake/risk-data-lake-service/src/main/java/com/rms/riskdatalake/service/services/ProvisionService.java|1293|saveTenant|tenantService	y
U3|unified-store|sql-pool/sql-pool-service/src/main/java/rms/unifiedstore/sqlpool/service/services/ReservationService.java|788|getPoolId|reservation	n:own-namespace-fallback
U3|data-lake|risk-data-lake/risk-data-lake-jobs/src/main/java/com/rms/riskdatalake/jobs/service/DownloadSqlResultService.java|192|saveResult|resultWriter	y
U3|unified-store|exposure-snapshot/snapshot-api/src/main/java/com/rms/unifiedstore/snapshot/api/irp/variation/v2/CreateExposureVariationV2JobImpl.java|307|getWorkflowServiceUrl|taskInput	y
U3|unified-store|exposure-snapshot/snapshot-api/src/main/java/com/rms/unifiedstore/snapshot/api/service/EntityVariationService.java|395|getAnalyticsEnginesApi|snapshotConfiguration	y
U3|unified-store|client-java/uds-client/src/main/java/com/rms/unifiedstore/SqlInstancesServiceImpl.java|137|getUserName|user	y
U3|data-lake|risk-data-lake/risk-data-lake-service/src/main/java/com/rms/riskdatalake/service/services/ReplicationService.java|1068|getTimestamp|dEventQueue	y
U3|workflow-service|lock-service/lock-service-dal/src/main/java/com/rms/lockservice/dal/repository/ResourceRepositoryExt.java|238|getName|resource	y
U3|unified-store|exposure-snapshot/snapshot-api/src/main/java/com/rms/unifiedstore/snapshot/api/model/bundle/ExposureBundle.java|294|getExposureNumber|exposureBundleEntity	y
U3|unified-store|exposure-snapshot/snapshot-common/src/main/java/com/rms/unifiedstore/snapshot/common/model/query/RelationalCondition.java|201|append|builder	n:own-namespace-fallback
U3|unified-store|client-java/uds-client/src/main/java/com/rms/unifiedstore/UnifiedStoreClientImpl.java|2380|getUserName|user	y
U3|unified-store|client-java/uds-client/src/main/java/com/rms/unifiedstore/DataBridgeServiceImpl.java|96|getUserName|user	y
U3|data-lake|odin/domain/odin-sql/src/main/java/com/moodys/odin/domain/sql/batch/SqlExportTask.java|94|tenantId|exportRequest	y
U3|unified-store|client-java/uds-client/src/main/java/com/rms/unifiedstore/UnifiedStoreClientImpl.java|4975|deleteEdm|edmService	y
U3|unified-store|exposure-snapshot/snapshot-api/src/main/java/com/rms/unifiedstore/snapshot/api/irp/variation/ExposureVariationsImpl.java|169|getExposureVariationV2|exposureVariationsImplV2	y
U3|data-lake|risk-data-lake/risk-data-lake-migration/src/main/java/com/rms/riskdatalake/initializer/reporting/ReportingService.java|576|getName|dataset	y
U3|unified-store|exposure-snapshot/snapshot-common/src/main/java/com/rms/unifiedstore/snapshot/common/model/query/ConditionWalker.java|94|isNot|inListCondition	y
U3|unified-store|client-java/uds-client/src/main/java/com/rms/unifiedstore/UnifiedStoreClientImpl.java|2049|deleteTransientDb|transientDbService	y
U3|unified-store|client-java/uds-client/src/main/java/com/rms/unifiedstore/SnapshotServiceImpl.java|191|getTenantId|user	y
U3|unified-store|sql-pool/sql-pool-manager/src/main/java/rms/unifiedstore/sqlpool/manager/jobs/CleanReservationJob.java|81|getInstance|serverHelperFactory	y
U3|unified-store|exposure-snapshot/ods-domain-data/src/main/java/com/rms/unifiedstore/cache/RedisCacheProvider.java|107|getKeys|redisClient	y
U3|unified-store|sql-pool/sql-pool-manager/src/main/java/rms/unifiedstore/sqlpool/manager/delegate/ServersMaintenanceBaseDelegate.java|131|getThresholdDiskUsage|poolConfig	n:own-namespace-fallback
U3|unified-store|client-java/uds-client/src/main/java/com/rms/unifiedstore/UnifiedStoreClientImpl.java|4900|deleteEdm|edmService	y
U3|data-lake|risk-data-lake/risk-data-lake-service/src/main/java/com/rms/riskdatalake/service/services/ProvisionService.java|270|setStatus|tenant	y
U3|data-lake|odin/domain/odin-scripts/src/main/java/com/moodys/odin/domain/scripts/service/DefaultScriptCommandService.java|149|validate|contentRules	y
U3|data-lake|risk-data-lake/risk-data-lake-migration/src/main/java/com/rms/riskdatalake/initializer/reporting/validation/SeededResourceValidator.java|60|validate|datasetValidator	y
U3|data-lake|risk-data-lake/risk-data-lake-service/src/main/java/com/rms/riskdatalake/service/services/ProvisionService.java|1022|saveTenant|tenantService	y
U3|data-lake|risk-data-lake/risk-data-lake-scheduler/src/main/java/com/rms/riskdatalake/scheduler/models/health/RDLHealthCheckResponse.java|14|getCommit|healthCheckResponse	y
U3|data-lake|risk-data-lake/risk-data-lake-service/src/main/java/com/rms/riskdatalake/service/services/SettingService.java|63|findByKey|settingRepository	y
U3|unified-store|service-api/RMS.UnifiedStore.Service.Api/Controllers/v1/ManagedSqlJobsController.cs|49|LogException|_logger	y
U3|unified-store|service-api/RMS.UnifiedStore.Service.Api/Integration/CatalogCardApiProxy.cs|60|LogException|_logger	y
U3|unified-store|managed-sql/RMS.UnifiedStore.Service.ManagedSql/DataLayer/EF/Migrations/20260313204003_AddMaintenanceTables.Designer.cs|759|Entity|modelBuilder	n:own-namespace-fallback
U3|unified-store|catalog-service/RMS.UnifiedStore.Service.Catalog/Startup.cs|193|AddSingleton|services	n:own-namespace-fallback
U3|unified-store|managed-sql/RMS.UnifiedStore.Service.ManagedSql/SqlInstances/SqlInstanceSystemDatabaseImporter.cs|100|ListSystemDatabasesAsync|_databaseRepository	n:own-namespace-fallback
U3|unified-store|service-api/RMS.UnifiedStore.Service.Api/Integration/CardApiProxy.cs|203|LogException|_logger	y
U3|unified-store|managed-sql/RMS.UnifiedStore.Service.ManagedSql/SqlInstances/ForceUpgradeHandler.cs|314|MarkAsNonRetryable|performContext	n:own-namespace-fallback
U3|unified-store|managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/HelmController.cs|158|UninstallReleaseAsync|_helmService	n:own-namespace-fallback
U3|unified-store|managed-sql/RMS.UnifiedStore.Service.ManagedSql/SqlInstances/SqlInstanceAdminHandler.cs|75|GetSqlInstanceAsync|_sqlInstanceRepository	n:own-namespace-fallback
U3|unified-store|managed-sql/RMS.UnifiedStore.Service.ManagedSql/Databases/LoginHelper.cs|187|DropAndCreateUserFromLoginAsync|_userManagement	n:own-namespace-fallback
U3|unified-store|service-api/RMS.UnifiedStore.Service.Api/Handlers/ImportExposureDatabaseHandler.cs|201|GetEdmByNameAsync|_edmRepository	n:own-namespace-fallback
U3|unified-store|service-api/RMS.UnifiedStore.Service.Api/DataLayer/EF/Migrations/20260917055236_AddMaintenanceWindows.Designer.cs|324|Entity|modelBuilder	n:own-namespace-fallback
U3|unified-store|catalog-service/RMS.UnifiedStore.Service.Catalog.Common/Integration/CatalogService.cs|762|PutCardInvokeWithRetryAsync|_cardProxy	y
U3|unified-store|service-api/RMS.UnifiedStore.Service.Api/Handlers/TenantHandler.cs|229|LogException|_logger	y
U3|unified-store|service-api/RMS.UnifiedStore.Service.Api/DataLayer/EF/Migrations/20220224162936_AlterExposureVariationsv1.Designer.cs|335|Entity|modelBuilder	n:own-namespace-fallback
U3|unified-store|managed-sql/RMS.UnifiedStore.Service.ManagedSql/DataLayer/EF/Migrations/20250910232230_AddQuotaTables.cs|82|CreateIndex|migrationBuilder	n:own-namespace-fallback
U3|unified-store|core/RMS.UnifiedStore.Core/Utils/HashHelper.cs|36|Dispose|md5	n:own-namespace-fallback
U3|unified-store|service-api/RMS.UnifiedStore.Service.Api/BackgroundJobs/SetSingleUserBackToMultiUserBackgroundJob.cs|101|GetDatabaseSysAdminConnectionAsync|_sqlInstanceCredentialsCache	y
U3|unified-store|service-api/RMS.UnifiedStore.Service.Api/Handlers/TransientDb/BaseTransientDbHandler.cs|204|ToString|connStrBuilder	n:own-namespace-fallback
U3|unified-store|managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/JobsController.cs|109|LogException|_logger	y
U3|unified-store|managed-sql/RMS.UnifiedStore.Service.ManagedSql/SqlInstances/ForceRestartHandler.cs|104|NewScope|_logger	y
U3|unified-store|managed-sql/RMS.UnifiedStore.Service.ManagedSql/DataLayer/EF/JobRepository.cs|137|LogException|_logger	y
U3|unified-store|catalog-service/RMS.UnifiedStore.Service.Catalog/Job/CardAggregateQueryJobHandler.cs|114|Interpret|_interpreter	n:own-namespace-fallback
U3|unified-store|managed-sql/RMS.UnifiedStore.Service.ManagedSql/Databases/DatabaseExportHandler.cs|91|AttachDatabaseAsync|_databaseAttachManager	y
U3|unified-store|service-api/RMS.UnifiedStore.Service.Api/LocalStartup.cs|193|IsDevelopment|_webHostEnvironment	n:own-namespace-fallback
U3|unified-store|managed-sql/RMS.UnifiedStore.Service.ManagedSql/Databases/DatabaseAttachManager.cs|233|GetDatabaseReloadedAsync|_databaseRepository	n:own-namespace-fallback
U3|unified-store|service-api/RMS.UnifiedStore.Service.Api/Handlers/DropArchivesHandler.cs|116|StartAsync|_jobScheduler	n:own-namespace-fallback
U3|unified-store|service-api/RMS.UnifiedStore.Service.Api/Handlers/KmsKeyHandler.cs|306|LogException|_logger	y
U3|unified-store|managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/AdminController.cs|641|ListJobsAsync|_adminHandler	n:own-namespace-fallback
U3|unified-store|managed-sql/RMS.UnifiedStore.Service.ManagedSql/Handlers/SnapshotDatabaseHandler.cs|756|UpdateJobDetailsAsync|_jobScheduler	n:own-namespace-fallback
U3|unified-store|service-api/RMS.UnifiedStore.Service.Api/RecurringJobs/ArchivesMetricsReportAndCleanupJob.cs|453|GetDatabaseHostingService|_databaseHostingServiceFactory	n:own-namespace-fallback
U3|unified-store|managed-sql/RMS.UnifiedStore.Service.ManagedSql/Clusters/ClusterAdminHandler.cs|52|UpdateClusterAsync|_clusterRepository	n:own-namespace-fallback
U3|unified-store|service-api/RMS.UnifiedStore.Service.Api/Handlers/CreateSnapshotHandler.cs|260|MarkAsNonRetryable|performContext	n:own-namespace-fallback
U3|unified-store|service-api/RMS.UnifiedStore.Service.Api/Integration/RdsDatabaseHostingService.cs|363|StartAsync|_jobScheduler	n:own-namespace-fallback
U3|unified-store|managed-sql/RMS.UnifiedStore.Service.ManagedSql/DataLayer/EF/Migrations/20260625190704_AddWorkflowCallbacksRetentionIndexes.Designer.cs|932|Entity|modelBuilder	n:own-namespace-fallback
U3|unified-store|managed-sql/RMS.UnifiedStore.Service.ManagedSql/Databases/DatabaseHandler.cs|1614|PutResult|jobResult	n:own-namespace-fallback
U3|unified-store|service-api/RMS.UnifiedStore.Service.Api/Integration/WorkflowService.cs|111|LogException|_logger	y
U3|unified-store|service-api/RMS.UnifiedStore.Service.Api/LocalStartup.cs|80|AddUnifiedStoreSwaggerDoc|services	n:own-namespace-fallback
U3|unified-store|service-api/RMS.UnifiedStore.Service.Api/Controllers/Internal/v1/CacheController.cs|61|LogException|_logger	y
U3|unified-store|service-api/RMS.UnifiedStore.Service.Api/Handlers/KmsKeyHandler.cs|357|UntilAsync|_statusPoller	n:own-namespace-fallback
U3|unified-store|managed-sql/RMS.UnifiedStore.Service.ManagedSql/Archives/ArchivesHandler.cs|811|RetryOperationAsync|_retryHandler	n:own-namespace-fallback
U3|unified-store|managed-sql/RMS.UnifiedStore.Service.ManagedSql/SqlInstances/SqlInstanceHandler.cs|1847|DeleteSnapshotAsync|_volumeManager	n:own-namespace-fallback
U3|unified-store|managed-sql/RMS.UnifiedStore.Service.ManagedSql/Archives/ArchivesHandler.cs|651|LogException|_logger	y
U3|unified-store|managed-sql/RMS.UnifiedStore.Service.ManagedSql/Databases/DatabaseImportHandler.cs|119|LogException|_logger	y
U3|unified-store|catalog-service/RMS.UnifiedStore.Service.Catalog.Common/Integration/CatalogService.cs|599|PutCardAsync|_cardApi	n:own-namespace-fallback
U3|unified-store|managed-sql/RMS.UnifiedStore.Service.ManagedSql/Databases/DatabaseMetaAdminHandler.cs|48|GetDatabaseAsync|_databaseRepository	n:own-namespace-fallback
U3|unified-store|service-api/RMS.UnifiedStore.Service.Api/DataLayer/EF/Migrations/20241029142855_AddArchiveSize.Designer.cs|483|Entity|modelBuilder	n:own-namespace-fallback
U3|unified-store|managed-sql/RMS.UnifiedStore.Service.ManagedSql/Engine/KubernetesWorkflowService.cs|121|GetNodesAsync|_kubernetesApi	n:own-namespace-fallback
U3|unified-store|managed-sql/RMS.UnifiedStore.Service.ManagedSql/Archives/ArchivesHandler.cs|791|GetSqlInstanceAsync|_sqlInstanceRepository	n:own-namespace-fallback
U3|unified-store|service-api/RMS.UnifiedStore.Service.Api/DataLayer/TransientDbRepository.cs|462|LogException|_logger	y
U3|workflow-service|workflow-service/core/scheduler-core/src/main/scala/com/rms/execution/scheduler/core/service/processor/RequestedLockProcessor.scala|357|doRollback|processorChain	y
U3|unified-store|exposure-snapshot/snapshot-legacy/snapshot-legacy-task/src/main/scala/com/rms/unifiedstore/task/AccountSnapshotTask.scala|227|getOrException|snapshotPayload	y
U3|unified-store|exposure-snapshot/download-exposure/src/main/scala/com/rms/unifiedstore/task/LiveVariationTask.scala|266|getOrException|variationPayload	y
U3|workflow-service|workflow-service/persistence/execution-dal/src/main/scala/com/rms/execution/dal/repository/execution/FetchWorkflowCompositeRepository.scala|58|copy|parameters	y
U3|unified-store|exposure-snapshot/snapshot-legacy/snapshot-legacy-task/src/main/scala/com/rms/unifiedstore/task/AccountSnapshotTask.scala|264|getOrDefault|snapshotPayload	y
U3|workflow-service|workflow-service/api/execution-api/src/main/scala/com/rms/execution/api/WorkflowApiApplication.scala|210|unwrap|platformDataSource	y
U3|workflow-service|workflow-service/persistence/execution-dal/src/main/scala/com/rms/execution/dal/dao/JobMetadataDao.scala|85|bind|statement	y
U3|workflow-service|workflow-service/core/execution-core/src/main/scala/com/rms/execution/ExecutionModule.scala|467|unwrap|platformDataSource	y
U3|workflow-service|workflow-service/persistence/execution-dal/src/main/scala/com/rms/execution/dal/dao/TenantDao.scala|54|bind|statement	y
U3|workflow-service|workflow-service/persistence/execution-dal/src/main/scala/com/rms/execution/dal/dao/JobMetricSampleDao.scala|61|bind|statement	y
U3|workflow-service|workflow-service/persistence/execution-dal/src/main/scala/com/rms/execution/dal/dao/WorkflowMetadataDao.scala|68|bind|statement	y
U3|unified-store|exposure-snapshot/snapshot-legacy/snapshot-legacy-task/src/main/scala/com/rms/unifiedstore/task/AccountSnapshotTask.scala|205|getOrException|snapshotPayload	y
U3|workflow-service|workflow-service/core/execution-core/src/main/scala/com/rms/execution/service/syncpodjob/kubernetes/KubernetesJobSynchronizer.scala|385|withExitCode|builder	y
U3|unified-store|exposure-snapshot/snapshot-legacy/snapshot-legacy-task/src/main/scala/com/rms/unifiedstore/task/PortfolioSnapshotTask.scala|634|getOrException|snapshotPayload	y
U3|workflow-service|workflow-service/persistence/execution-dal/src/main/scala/com/rms/execution/dal/dao/TenantDao.scala|50|bind|statement	y
U3|workflow-service|workflow-service/core/scheduler-core/src/main/scala/com/rms/execution/scheduler/core/util/TenantQueueIteratorExecutor.scala|145|getQueueId|iterator	y
U3|workflow-service|workflow-service/persistence/execution-dal/src/main/scala/com/rms/execution/dal/specification/workflow/WorkflowLockReleaseEquals.scala|11|bind|query	y
U3|workflow-service|workflow-service/persistence/execution-dal/src/main/scala/com/rms/execution/dal/dao/ArchiveQueryResultDao.scala|92|bind|statement	y
U3|workflow-service|workflow-service/persistence/execution-dal/src/main/scala/com/rms/execution/dal/dao/WorkflowMetadataDao.scala|66|bind|statement	y
U3|workflow-service|workflow-service/persistence/execution-dal/src/main/scala/com/rms/execution/dal/dao/JobResourcesRecommendationDao.scala|85|bind|statement	y
U3|workflow-service|workflow-service/core/execution-common/src/main/scala/com/rms/execution/utils/TryExec.scala|30|close|resource	n:own-namespace-fallback
U3|workflow-service|workflow-service/persistence/execution-dal/src/main/scala/com/rms/execution/dal/dao/JobMetadataDao.scala|96|bind|statement	y
U3|workflow-service|workflow-service/core/scheduler-core/src/main/scala/com/rms/execution/scheduler/core/util/TenantQueueIteratorExecutor.scala|276|containsKey|iteratorMap	n:own-namespace-fallback
U3|workflow-service|workflow-service/persistence/execution-dal/src/main/scala/com/rms/execution/dal/dao/JobMetricDao.scala|111|bind|statement	y
U3|workflow-service|workflow-service/persistence/execution-dal/src/main/scala/com/rms/execution/dal/dao/TenantDao.scala|57|bind|statement	y
U3|workflow-service|workflow-service/persistence/execution-dal/src/main/scala/com/rms/execution/dal/dao/JobResourcesRecommendationDao.scala|78|bind|statement	y
U3|workflow-service|workflow-service/persistence/execution-dal/src/main/scala/com/rms/execution/dal/dao/JobResourcesRecommendationDao.scala|74|bind|statement	y
U3|workflow-service|workflow-service/persistence/execution-dal/src/main/scala/com/rms/execution/dal/specification/archive/TenantIdAndHashEquals.scala|16|bind|query	y
U3|workflow-service|workflow-service/persistence/execution-dal/src/main/scala/com/rms/execution/dal/dao/TenantQueueDao.scala|60|bind|statement	y
U3|unified-store|exposure-snapshot/snapshot-legacy/snapshot-legacy-task/src/main/scala/com/rms/unifiedstore/task/PortfolioSnapshotTask.scala|625|getOrException|snapshotPayload	y
U3|workflow-service|workflow-service/core/execution-api-core/src/main/scala/com/rms/execution/api/core/validator/InputValidator.scala|164|getPercentComplete|progress	n:own-namespace-fallback
U3|workflow-service|workflow-service/persistence/execution-dal/src/main/scala/com/rms/execution/dal/dao/ArchiveQueryResultDao.scala|94|bind|statement	y
U3|workflow-service|workflow-service/persistence/execution-dal/src/main/scala/com/rms/execution/dal/dao/JobMetadataDao.scala|49|bind|statement	y
U3|unified-store|exposure-snapshot/snapshot-legacy/snapshot-legacy-task/src/main/scala/com/rms/unifiedstore/task/PortfolioSnapshotTask.scala|624|getOrException|snapshotPayload	y
U3|unified-store|exposure-snapshot/snapshot-legacy/snapshot-legacy-task/src/main/scala/com/rms/unifiedstore/task/AccountSnapshotTask.scala|207|getOrDefault|snapshotPayload	y
U3|workflow-service|workflow-service/persistence/execution-dal/src/main/scala/com/rms/execution/dal/dao/WorkflowDao.scala|149|bind|specification	y
U3|workflow-service|workflow-service/persistence/execution-dal/src/main/scala/com/rms/execution/dal/dao/JobMetricDao.scala|65|bind|statement	y
U3|workflow-service|workflow-service/persistence/execution-dal/src/main/scala/com/rms/execution/dal/dao/JobMetadataDao.scala|91|bind|statement	y
U3|workflow-service|workflow-service/core/execution-core/src/main/scala/com/rms/execution/api/util/NvmePermissionInitContainer.scala|61|setCommand|initContainer	y
U3|workflow-service|workflow-service/core/scheduler-core/src/main/scala/com/rms/execution/scheduler/core/util/TenantQueueIteratorExecutor.scala|304|get|iteratorMap	n:own-namespace-fallback
U3|workflow-service|workflow-service/persistence/execution-dal/src/main/scala/com/rms/execution/dal/util/JdbiExtension.scala|19|inTransaction|jdbi	y
U3|workflow-service|workflow-service/core/scheduler-core/src/main/scala/com/rms/execution/scheduler/core/service/processor/CheckConcurrencyProcessor.scala|89|doRollback|processorChain	y
U3|workflow-service|workflow-service/persistence/execution-dal/src/main/scala/com/rms/execution/dal/specification/archive/TenantIdAndHashEquals.scala|15|bind|query	y
U3|workflow-service|workflow-service/core/scheduler-core/src/main/scala/com/rms/execution/scheduler/core/util/TenantQueueIteratorExecutor.scala|253|getQueueId|iterator	y
U3|workflow-service|workflow-service/core/execution-api-core/src/main/scala/com/rms/execution/api/core/validator/InputValidator.scala|597|getJobType|jobInput	n:own-namespace-fallback
U3|workflow-service|workflow-service/persistence/execution-dal/src/main/scala/com/rms/execution/dal/dao/JobMetadataDao.scala|88|bind|statement	y
U3|workflow-service|workflow-service/persistence/execution-dal/src/main/scala/com/rms/execution/dal/dao/JobMetadataDao.scala|60|bind|statement	y
U3|workflow-service|workflow-service/persistence/execution-dal/src/main/scala/com/rms/execution/dal/dao/JobMetricSampleDao.scala|62|bind|statement	y
U3|workflow-service|workflow-service/persistence/execution-dal/src/main/scala/com/rms/execution/dal/specification/job/JobTenantIdEquals.scala|11|bind|query	y
U3|workflow-service|workflow-service/persistence/execution-dal/src/main/scala/com/rms/execution/dal/dao/JobProgressDao.scala|72|bind|statement	y
U4|data-lake|risk-data-lake/risk-data-lake-common/src/main/java/com/rms/riskdatalake/common/s3credentials/FoundationsS3Client.java|79|SCOPED_CREDENTIALS_PATH	n:no-edge-with-constant-value
U4|workflow-service|workflow-service/persistence/execution-dal/src/main/scala/com/rms/execution/dal/dao/KubernetesClusterInputDao.scala|24|InsertQuery	n:no-edge-with-constant-value
U3|dispatch|src/dispatch/plugins/dispatch_slack/case/interactive.py|1597|views_update|client	y
U3|dispatch|src/dispatch/entity_type/service.py|21|query|db_session	y
U3|dispatch|src/dispatch/plugins/dispatch_slack/incident/interactive.py|580|views_open|client	y
U3|dispatch|src/dispatch/participant_activity/service.py|44|add|db_session	y
U3|dispatch|src/dispatch/plugins/dispatch_pagerduty/service.py|72|rpost|client	y
U3|dispatch|src/dispatch/signal/service.py|208|dict|signal_filter_in	y
U3|dispatch|src/dispatch/signal/service.py|1026|execute|db_session	y
U3|dispatch|src/dispatch/monitor/service.py|67|dict|monitor_in	y
U3|dispatch|src/dispatch/database/manage.py|179|execute|connection	y
U3|dispatch|src/dispatch/signal/views.py|120|commit|db_session	y
U3|dispatch|src/dispatch/plugins/dispatch_slack/middleware.py|157|update|context	y
U3|dispatch|src/dispatch/incident_cost/service.py|205|add|db_session	y
U3|dispatch|src/dispatch/plugins/dispatch_slack/case/interactive.py|1487|views_open|client	y
U3|dispatch|src/dispatch/case/views.py|589|add_task|background_tasks	y
U3|dispatch|src/dispatch/feedback/incident/service.py|92|dict|feedback	y
U3|dispatch|src/dispatch/plugin/service.py|57|query|db_session	y
U3|dispatch|src/dispatch/project/service.py|11|query|db_session	y
U3|dispatch|src/dispatch/participant/service.py|82|query|db_session	y
U3|dispatch|src/dispatch/plugins/dispatch_slack/incident/interactive.py|1541|views_open|client	y
U3|dispatch|src/dispatch/plugins/dispatch_jira/plugin.py|107|search_users|client	y
U3|dispatch|src/dispatch/data/source/type/service.py|89|dict|source_type_in	y
U3|dispatch|src/dispatch/plugins/dispatch_slack/case/interactive.py|1436|chat_update|client	y
U3|dispatch|src/dispatch/incident/service.py|66|query|db_session	y
U3|dispatch|src/dispatch/signal/service.py|135|dict|signal_engagement_in	y
U3|dispatch|src/dispatch/plugins/dispatch_slack/case/interactive.py|1276|commit|db_session	y
U3|dispatch|src/dispatch/participant/service.py|290|commit|db_session	y
U3|dispatch|src/dispatch/entity_type/flows.py|35|commit|db_session	y
U3|dispatch|src/dispatch/signal/service.py|900|commit|db_session	y
U3|dispatch|src/dispatch/task/service.py|186|dict|task_in	y
U3|dispatch|src/dispatch/signal/service.py|343|query|db_session	y
U3|dispatch|src/dispatch/plugins/dispatch_slack/plugin.py|183|commit|db_session	y
U3|dispatch|src/dispatch/plugins/dispatch_slack/middleware.py|405|get|context	y
U3|dispatch|src/dispatch/plugins/dispatch_core/plugin.py|442|query|db_session	y
U3|dispatch|src/dispatch/feedback/service/service.py|18|query|db_session	y
U3|dispatch|src/dispatch/document/flows.py|98|add|db_session	y
U3|dispatch|src/dispatch/incident/views.py|206|add_task|background_tasks	y
U3|dispatch|src/dispatch/signal/service.py|449|commit|db_session	y
U3|dispatch|src/dispatch/signal/service.py|812|query|db_session	y
U3|dispatch|src/dispatch/tag/service.py|76|dict|tag_in	y
U3|dispatch|src/dispatch/ticket/service.py|27|add|db_session	y
U3|dispatch|src/dispatch/participant/service.py|266|bulk_save_objects|db_session	y
U3|dispatch|src/dispatch/data/source/environment/service.py|102|dict|source_environment	y
U3|dispatch|src/dispatch/storage/service.py|24|dict|storage_in	y
U3|dispatch|src/dispatch/data/source/service.py|166|dict|source	y
U3|dispatch|src/dispatch/participant/service.py|30|query|db_session	y
U3|dispatch|src/dispatch/plugins/dispatch_core/plugin.py|383|expire_all|db_session	y
U3|dispatch|src/dispatch/signal/service.py|144|add|db_session	y
U3|dispatch|src/dispatch/plugins/dispatch_slack/case/interactive.py|2628|users_info|client	y
U3|CTFd|CTFd/api/v1/challenges.py|1299|get|data	x:receiver-is-local-var-not-field-or-param
U3|dispatch|src/dispatch/plugins/dispatch_slack/incident/interactive.py|1054|commit|db_session	y
U4|dispatch|src/dispatch/plugins/dispatch_zoom/client.py|28|API_BASE_URI	n:no-edge-with-constant-value
U4|dispatch|src/dispatch/plugins/dispatch_zoom/client.py|44|API_BASE_URI	n:no-edge-with-constant-value
U4|dispatch|src/dispatch/plugins/dispatch_zoom/client.py|36|API_BASE_URI	n:no-edge-with-constant-value
"""
MANUAL_VERDICTS = dict(r.split("\t", 1) for r in MANUAL_VERDICTS_RAW.strip().split("\n") if "\t" in r)
# END MANUAL VERDICTS


if __name__ == "__main__":
    main()
