"""Python HTTP clients as `http_out` edges: `requests.get("/x")`, `httpx`, `aiohttp`/`session.post(f"{BASE}/x/{id}")`.

Only a call whose receiver is `requests`/`httpx`/`aiohttp` or looks like a client/session object, in a
file that imports one of those libraries, and whose URL is a string literal (or an f-string with one;
each interpolation becomes `{}`). A leading interpolated base (`{BASE}/x`) is dropped. Test files are skipped.
"""

from __future__ import annotations

import ast
import re
from typing import List, Optional

from .base import ExtractContext, FileFacts, anchor_at, mk_edge

_VERBS = {"get", "post", "put", "delete", "patch", "head", "options"}
_LIBS = ("requests", "httpx", "aiohttp", "urllib3")
_TEST_PATH = re.compile(r"(?:^|/)(?:tests?|testing)/|(?:^|/)test_[^/]*\.py$|_test\.py$")
_HOLE_BASE = re.compile(r"^\{[^{}]*\}(?=/)")


def _receiver_ok(node: ast.AST) -> bool:
    name = node.id if isinstance(node, ast.Name) else node.attr if isinstance(node, ast.Attribute) else ""
    low = name.lower()
    return low in _LIBS or low in ("http", "s") or "client" in low or "session" in low


def _url_text(node: ast.AST) -> Optional[str]:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return "".join(str(p.value) if isinstance(p, ast.Constant) else "{}" for p in node.values)
    return None


class _Visitor(ast.NodeVisitor):
    def __init__(self, ctx: ExtractContext, facts: FileFacts, primary: str) -> None:
        self.ctx, self.facts, self.owner = ctx, facts, primary

    def visit_ClassDef(self, node):
        saved, self.owner = self.owner, self.owner + "." + node.name
        self.generic_visit(node)
        self.owner = saved

    def _fn(self, node):
        saved, self.owner = self.owner, self.owner + "#" + node.name
        self.generic_visit(node)
        self.owner = saved

    visit_FunctionDef = visit_AsyncFunctionDef = _fn

    def visit_Call(self, node):
        func = node.func
        if isinstance(func, ast.Attribute) and node.args and _receiver_ok(func.value):
            verb, args = func.attr.lower(), node.args
            if verb == "request" and len(args) >= 2:
                m = args[0]
                verb = m.value.lower() if isinstance(m, ast.Constant) and isinstance(m.value, str) else ""
                args = args[1:]
            raw = _url_text(args[0]) if verb in _VERBS else None
            if raw:
                raw = _HOLE_BASE.sub("", raw)
            if raw and "/" in raw:
                anchor = anchor_at(self.ctx, node.lineno - 1)
                if anchor:
                    self.facts.signals.append("http_client")
                    self.facts.io_edges.append(
                        mk_edge(self.owner, "http:%s %s" % (verb.upper(), raw), "http_out", anchor))
        self.generic_visit(node)


def emit_http_clients(ctx: ExtractContext, facts: FileFacts, tree: ast.AST, primary: str) -> None:
    if _TEST_PATH.search(ctx.path):
        return
    if not re.search(r"^\s*(?:import|from)\s+(?:%s)\b" % "|".join(_LIBS), "\n".join(ctx.lines), re.M):
        return
    _Visitor(ctx, facts, primary).visit(tree)
