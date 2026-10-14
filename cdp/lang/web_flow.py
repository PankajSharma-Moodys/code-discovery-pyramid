"""Body facts of a JS/TS file: outbound HTTP through in-file wrappers, React Router routes,
Pusher subscriptions, cross-module calls. Works on the comment-free text from `web_scan`.

Everything is syntactic and in-file: a URL expression is evaluated from string literals,
template literals, `+` and single-assignment locals; anything else becomes `${}` and a URL
with no literal text at all is dropped rather than guessed.
"""

from __future__ import annotations

import bisect
import re
from typing import Dict, List, Optional, Sequence, Tuple

from .web_decl import _CONT

_PH = re.compile(r"\$\{[^}]*\}")
_IDENT = re.compile(r"^[A-Za-z_$][\w$]*$")
_PATH = re.compile(r"^[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*$")
CLIENT_RE = re.compile(
    r"(?<![\w$.])(?:(axios|got|superagent|request)\s*\.\s*(get|post|put|delete|patch)|(fetch|axios|got|superagent))\s*\("
)


# ------------------------------------------------------------- text helpers

def skip_string(text: str, i: int) -> int:
    """Index just past the string/template literal opening at text[i]."""
    q, n = text[i], len(text)
    i += 1
    while i < n:
        c = text[i]
        if c == "\\":
            i += 2
            continue
        if q == "`" and c == "$" and text.startswith("{", i + 1):
            i = skip_balanced(text, i + 1)
            continue
        if c == q:
            return i + 1
        if c == "\n" and q != "`":
            return i
        i += 1
    return n


def skip_balanced(text: str, i: int) -> int:
    """text[i] opens ( [ {; return the index just past its match (strings skipped)."""
    depth, n = 0, len(text)
    while i < n:
        c = text[i]
        if c in "'\"`":
            i = skip_string(text, i)
            continue
        if c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return n


def split_top(text: str, sep: str) -> List[str]:
    parts, depth, start, i, n = [], 0, 0, 0, len(text)
    while i < n:
        c = text[i]
        if c in "'\"`":
            i = skip_string(text, i)
            continue
        if c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
        elif c == sep and depth == 0:
            parts.append(text[start:i])
            start = i + 1
        i += 1
    parts.append(text[start:])
    return parts


def first_args(text: str, open_paren: int) -> List[str]:
    end = skip_balanced(text, open_paren)
    return split_top(text[open_paren + 1:end - 1], ",")


# --------------------------------------------------------------- evaluation

def eval_expr(expr: str, env: Dict[str, str], depth: int = 0) -> str:
    """URL text of `expr`; unknown parts are `${name}` (a bare name) or `${}`."""
    expr = expr.strip()
    if depth > 6 or not expr:
        return "${}"
    while expr.startswith("(") and skip_balanced(expr, 0) == len(expr):
        expr = expr[1:-1].strip()
    terms = split_top(expr, "+")
    if len(terms) > 1:
        return "".join(eval_expr(t, env, depth + 1) for t in terms)
    if expr[0] in "'\"" and skip_string(expr, 0) == len(expr):
        return expr[1:-1]
    if expr[0] == "`" and skip_string(expr, 0) == len(expr):
        return _template(expr[1:-1], env, depth)
    if _IDENT.match(expr) and expr in env:
        value = eval_expr(env[expr], env, depth + 1)
        return "${%s}" % expr if value == "${}" else value     # an unevaluable local keeps its name
    if _PATH.match(expr):
        return "${%s}" % expr
    return "${}"


def _template(body: str, env: Dict[str, str], depth: int) -> str:
    out, i, n = [], 0, len(body)
    while i < n:
        if body.startswith("${", i):
            end = skip_balanced(body, i + 1)
            inner = body[i + 2:end - 1].strip()
            if _IDENT.match(inner) and inner in env:
                out.append(eval_expr(inner, env, depth + 1))
            elif _PATH.match(inner):
                out.append("${%s}" % inner)
            else:
                out.append("${}")
            i = end
        else:
            out.append(body[i])
            i += 1
    return "".join(out)


def tidy(url: str) -> str:
    """Runs of unknown parts (`&${}${}${}`) collapse to one."""
    return re.sub(r"(?:&?\$\{\}){2,}", "${}", url)


def has_literal(url: str) -> bool:
    return bool(_PH.sub("", url).strip("/ ?&"))


# ----------------------------------------------------------- scope helpers

class Source:
    """Whole-file text with an offset -> line index map."""

    def __init__(self, code: Sequence[str], stacks: Sequence[Tuple[str, ...]]) -> None:
        self.code, self.stacks = code, stacks
        self.text = "\n".join(code)
        self.starts: List[int] = []
        pos = 0
        for line in code:
            self.starts.append(pos)
            pos += len(line) + 1

    def line_of(self, offset: int) -> int:
        return bisect.bisect_right(self.starts, offset) - 1

    def span(self, first: int, last: int) -> Tuple[int, int]:
        end = self.starts[last] + len(self.code[last]) if last < len(self.code) else len(self.text)
        return self.starts[first], end


def params_of(src: Source, decl: Dict) -> List[str]:
    """Parameter names of a method/arrow declaration, in order."""
    a, b = src.span(decl["line"], decl["end"])
    text = src.text[a:b]
    m = re.search(r"\b%s\b" % re.escape(decl["name"]), text)
    if not m:
        return []
    k = text.find("(", m.end())
    brace = text.find("{", m.end())
    if k < 0 or (0 <= brace < k) or (decl["kind"] != "method"):
        return []
    names = []
    for p in split_top(text[k + 1:skip_balanced(text, k) - 1], ","):
        pm = re.match(r"\s*(?:\.\.\.)?\s*(?:(?:public|private|protected|readonly)\s+)*([A-Za-z_$][\w$]*)", p)
        names.append(pm.group(1) if pm else "")
    return names


def local_env(src: Source, first: int, last: int) -> Dict[str, str]:
    """Single-assignment `const|let|var x = <init>` locals of lines first..last."""
    env: Dict[str, str] = {}
    a, b = src.span(first, last)
    body = src.text[a:b]
    for m in re.finditer(r"(?<![\w$.])(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*(?::[^=\n]+)?=(?![=>])", body):
        name = m.group(1)
        assigns = len(re.findall(r"(?<![\w$.])%s\s*(?:[-+*/]?=)(?![=>])" % re.escape(name), body))
        if assigns != 1:
            continue
        line = src.line_of(a + m.end())
        base = len(src.stacks[src.line_of(a + m.start())])
        k = line
        while k + 1 <= last:
            nxt = src.code[k + 1].strip()
            if nxt and (len(src.stacks[k + 1]) > base or nxt.startswith(_CONT)):
                k += 1
            elif not nxt:
                k += 1
            else:
                break
        s0 = a + m.end()
        e0 = src.span(line, k)[1]
        env[name] = src.text[s0:e0].strip().rstrip(";")
    return env


# --------------------------------------------------------------- http calls

def http_calls(src: Source, decls: List[Dict], primary: str) -> List[Dict]:
    """Outbound calls as {line, source, verb, url}; wrappers learned in-file are expanded."""
    callables = [d for d in decls if d["kind"] == "method"]

    def enclosing(line: int) -> Optional[Dict]:
        best = None
        for d in callables:
            if d["line"] <= line <= d["end"] and (best is None or d["end"] - d["line"] < best["end"] - best["line"]):
                best = d
        return best

    def fqn(d: Optional[Dict]) -> str:
        return primary if d is None else primary + "." + (d["cls"] + "." if d["cls"] else "") + d["name"]

    envs: Dict[int, Dict[str, str]] = {}

    def env_of(d: Optional[Dict]) -> Dict[str, str]:
        if d is None:
            return {}
        key = id(d)
        if key not in envs:
            envs[key] = local_env(src, d["line"], d["end"])
        return envs[key]

    direct: List[Dict] = []
    for m in CLIENT_RE.finditer(src.text):
        verb = (m.group(2) or "").upper() or None
        open_paren = m.end() - 1
        args = first_args(src.text, open_paren)
        if not args or not args[0].strip():
            continue
        line = src.line_of(m.start())
        d = enclosing(line)
        if m.group(3) == "fetch":
            opts = ",".join(args[1:])
            mm = re.search(r"method\s*:\s*['\"`](\w+)", opts)
            verb = mm.group(1).upper() if mm else "GET"
        first = args[0].strip()
        if m.group(3) in ("got", "superagent", "axios") and first[:1] not in ("'", '"', "`"):
            continue
        url = eval_expr(first, env_of(d))
        if has_literal(url) or _PH.search(url):
            direct.append({"line": line, "decl": d, "verb": verb, "url": url, "first": first})

    # wrappers: a callable whose client call's URL embeds one of its own parameters
    wrappers: Dict[str, Dict] = {}
    for row in direct:
        d = row["decl"]
        if d is None:
            continue
        params = params_of(src, d)
        for k, p in enumerate(params):
            if p and "${%s}" % p in row["url"] and d["name"] not in wrappers:
                wrappers[d["name"]] = {"param": k, "pname": p, "verb": row["verb"], "url": row["url"], "row": row}

    out: List[Dict] = []
    expanded = set()
    for name, w in wrappers.items():
        pat = re.compile(r"(?<![\w$.])(?:this\s*\.\s*)?%s\s*\(" % re.escape(name))
        for m in pat.finditer(src.text):
            line = src.line_of(m.start())
            prefix = src.text[max(0, m.start() - 9):m.start()]
            d = enclosing(line)
            if d is not None and d["name"] == name and d["line"] == line or prefix.endswith("function "):
                continue
            args = first_args(src.text, m.end() - 1)
            if len(args) <= w["param"]:
                continue
            value = eval_expr(args[w["param"]], env_of(d))
            if not has_literal(value):
                continue
            url = w["url"].replace("${%s}" % w["pname"], value)
            out.append({"line": line, "source": fqn(d), "verb": w["verb"], "url": tidy(url)})
            expanded.add(name)
    for row in direct:
        d = row["decl"]
        if d is not None and d["name"] in expanded and d["name"] in wrappers and wrappers[d["name"]]["row"] is row:
            continue            # the wrapper's own placeholder edge
        if not has_literal(row["url"]):
            continue
        out.append({"line": row["line"], "source": fqn(d), "verb": row["verb"], "url": tidy(row["url"])})
    return out


# ------------------------------------------------------------------- routes

_ROUTE_TAG = re.compile(r"<Route\b|</Route\s*>")


def _tag_end(text: str, i: int) -> int:
    """Index of the `>` closing the opening tag that starts at i."""
    depth, n = 0, len(text)
    while i < n:
        c = text[i]
        if c in "'\"`" and depth == 0:
            i = skip_string(text, i)
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
        elif c == ">" and depth == 0:
            return i
        i += 1
    return n


def _flat_attrs(tag: str) -> str:
    """Tag text with `{...}` groups collapsed (a lone string literal kept as `{"..."}`)."""
    out, i, n = [], 0, len(tag)
    while i < n:
        if tag[i] == "{":
            end = skip_balanced(tag, i)
            inner = tag[i + 1:end - 1].strip()
            if inner[:1] in "'\"`" and skip_string(inner, 0) == len(inner):
                out.append('{"%s"}' % inner[1:-1])
            else:
                out.append("{}")
            i = end
        else:
            out.append(tag[i])
            i += 1
    return "".join(out)


def routes(src: Source) -> List[Dict]:
    """React Router `<Route path>` elements as {line, path}, nesting joined."""
    from ..rules import join_route
    found: List[Dict] = []
    stack: List[str] = []
    pos = 0
    text = src.text
    while True:
        m = _ROUTE_TAG.search(text, pos)
        if not m:
            break
        if m.group(0).startswith("</"):
            if stack:
                stack.pop()
            pos = m.end()
            continue
        end = _tag_end(text, m.end())
        tag = _flat_attrs(text[m.end():end])
        self_closing = text[end - 1:end] == "/"
        pm = re.search(r"""\bpath\s*=\s*(?:"([^"]*)"|'([^']*)'|\{"([^"]*)"\})""", tag)
        sub = next((g for g in pm.groups() if g is not None), "") if pm else ""
        parent = stack[-1] if stack else ""
        if sub.startswith("/"):
            full = sub
        else:
            full = join_route(parent, sub) if parent or sub else ""
        is_index = bool(re.search(r"(?<![\w-])index(?![\w-])", tag)) and not pm
        if pm or is_index:
            found.append({"line": src.line_of(m.start()), "path": ("/" + full.lstrip("/")) if full else "/"})
        if not self_closing:
            stack.append(full)
        pos = end + 1
    return found


# ------------------------------------------------------------------- pusher

def pusher_events(src: Source, decls: List[Dict], primary: str) -> List[Dict]:
    """`.bind('Evt', cb)` on a file that builds a Pusher client: one subscribe edge per bind."""
    if not re.search(r"new\s+Pusher\s*\(", src.text):
        return []
    out = []
    for m in re.finditer(r"\.\s*bind\s*\(", src.text):
        args = first_args(src.text, m.end() - 1)
        if len(args) < 2 or not args[0].strip():
            continue
        line = src.line_of(m.start())
        d = None
        for c in decls:
            if c["kind"] == "method" and c["line"] <= line <= c["end"] and \
                    (d is None or c["end"] - c["line"] < d["end"] - d["line"]):
                d = c
        env = local_env(src, d["line"], d["end"]) if d else {}
        for c in decls:                                  # top-level string constants
            if c["value"] is not None and c["cls"] is None:
                env.setdefault(c["name"], '"%s"' % c["value"])
        name = eval_expr(args[0], env)
        if name == "${}":
            continue
        source = primary if d is None else primary + "." + (d["cls"] + "." if d["cls"] else "") + d["name"]
        out.append({"line": line, "source": source, "event": name})
    return out


# ------------------------------------------------------------ module calls

_IMPORT_FROM = re.compile(r"""\bimport\s+([^'";]*?)\s+from\s+['"](\.[^'"]*)['"]""")


def module_calls(src: Source, decls: List[Dict], primary: str, normalise) -> List[Dict]:
    """`import X from './m'` then `X.f(` / `new X(..).f(` / `v.f(` (v = new X) -> {line, from, module, cls, name}."""
    bindings: Dict[str, Tuple[str, str]] = {}     # local name -> (module id, exported name or "default")
    for m in _IMPORT_FROM.finditer(src.text):
        clause, module = m.group(1).strip(), normalise(m.group(2))
        named = re.search(r"\{([^}]*)\}", clause)
        default = clause.split("{")[0].strip().rstrip(",").strip()
        if default and not default.startswith("*") and _IDENT.match(default):
            bindings[default] = (module, "default")
        if default.startswith("* as "):
            bindings[default[5:].strip()] = (module, "*")
        if named:
            for part in named.group(1).split(","):
                bits = re.split(r"\s+as\s+", part.strip())
                if bits and bits[0]:
                    bindings[bits[-1]] = (module, bits[0])
    if not bindings:
        return []
    inst: Dict[str, str] = {}                      # variable -> class binding
    for m in re.finditer(r"(?:(?:const|let|var)\s+|this\s*\.\s*)([A-Za-z_$][\w$]*)\s*=\s*new\s+([A-Za-z_$][\w$]*)\s*\(", src.text):
        if m.group(2) in bindings:
            inst[m.group(1)] = m.group(2)
    out: List[Dict] = []

    def owner(line: int) -> str:
        best = None
        for d in decls:
            if d["kind"] == "method" and d["line"] <= line <= d["end"] and \
                    (best is None or d["end"] - d["line"] < best["end"] - best["line"]):
                best = d
        return primary if best is None else primary + "." + (best["cls"] + "." if best["cls"] else "") + best["name"]

    def add(offset: int, local: str, name: str) -> None:
        module, exported = bindings[local]
        cls = local if exported in ("default", "*") and local[:1].isupper() else None
        line = src.line_of(offset)
        out.append({"line": line, "from": owner(line), "module": module, "cls": cls,
                    "exported": exported, "name": name})

    for local in bindings:
        for m in re.finditer(r"(?<![\w$.])%s\s*\.\s*([A-Za-z_$][\w$]*)\s*\(" % re.escape(local), src.text):
            add(m.start(), local, m.group(1))
        for m in re.finditer(r"new\s+%s\s*\([^()]*\)\s*\.\s*([A-Za-z_$][\w$]*)\s*\(" % re.escape(local), src.text):
            add(m.start(), local, m.group(1))
        if bindings[local][1] not in ("default", "*"):                       # named function import
            for m in re.finditer(r"(?<![\w$.])%s\s*\(" % re.escape(local), src.text):
                if src.text[max(0, m.start() - 4):m.start()].strip() != "new":
                    line = src.line_of(m.start())
                    out.append({"line": line, "from": owner(line), "module": bindings[local][0], "cls": None,
                                "exported": bindings[local][1], "name": None})
    for var, local in inst.items():
        for m in re.finditer(r"(?<![\w$])(?:this\s*\.\s*)?%s\s*\.\s*([A-Za-z_$][\w$]*)\s*\(" % re.escape(var), src.text):
            add(m.start(), local, m.group(1))
    return out
