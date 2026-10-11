"""Python HTTP clients as `http_out` edges: `requests.get("/x")`, `httpx`, `aiohttp`/`session.post(f"{BASE}/x/{id}")`.

Only a call whose receiver is provably an HTTP client, in a file that imports one of those libraries:
the library module itself (`requests.get`), a name or `self.` attribute assigned from a client factory
(`requests.Session()`, `httpx.Client()`, `aiohttp.ClientSession()`, ...) or from another such name, or
one annotated with a client type (`session: requests.Session`). A variable merely *named* `session` or
`client` (Flask's `session`, a cache's `client_cache`) is not enough. The URL must be a string literal (or
an f-string with one; each interpolation becomes `{}`) that looks like a path or URL: no whitespace and a
`/`. A leading interpolated base (`{BASE}/x`) is dropped. Test files are skipped.
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


_CLIENT_TYPES = {"Session", "Client", "AsyncClient", "ClientSession", "PoolManager", "HTTPAdapter"}
_FACTORIES = _CLIENT_TYPES | {"session"}
_CLIENT_ATTR = re.compile(r"(?:client|session|^_?http)$", re.I)
_URLISH = re.compile(r"^(?:/|https?://|\{[^{}]*\}/|[^\s/{}][^\s]*/)[^\s]*$")


def _key(node: ast.AST) -> str:
    """`n:name` for a plain name, `a:attr` for `anything.attr` (so `self.session` is one key)."""
    if isinstance(node, ast.Name):
        return "n:" + node.id
    if isinstance(node, ast.Attribute):
        return "a:" + node.attr
    return ""


class _Clients:
    """The module aliases and the receivers of one file that are provably HTTP clients."""

    def __init__(self, tree: ast.AST) -> None:
        self.mods = set()       # local names of the libraries (`import requests as rq` -> rq)
        self.types = set()      # local names of client classes (`from httpx import Client as C`)
        self.keys = set()
        nodes = list(ast.walk(tree))
        for node in nodes:
            if isinstance(node, ast.Import):
                for a in node.names:
                    if a.name.split(".")[0] in _LIBS:
                        self.mods.add((a.asname or a.name).split(".")[0])
            elif isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[0] in _LIBS and not node.level:
                for a in node.names:
                    if a.name in _FACTORIES:
                        self.types.add(a.asname or a.name)
        for _ in range(3):      # `self.http = http` after `http = requests.Session()`
            before = len(self.keys)
            for node in nodes:
                self._visit(node)
            if len(self.keys) == before:
                break

    def _is_factory(self, value: ast.AST) -> bool:
        if isinstance(value, ast.Await):
            value = value.value
        if isinstance(value, ast.Call):
            f = value.func
            if isinstance(f, ast.Name):
                return f.id in self.types
            return (isinstance(f, ast.Attribute) and f.attr in _FACTORIES
                    and isinstance(f.value, ast.Name) and f.value.id in self.mods)
        return bool(_key(value)) and _key(value) in self.keys

    def _typed(self, ann: Optional[ast.AST]) -> bool:
        for n in ast.walk(ann) if ann is not None else ():
            if isinstance(n, ast.Name) and n.id in self.types:
                return True
            if (isinstance(n, ast.Attribute) and n.attr in _CLIENT_TYPES
                    and isinstance(n.value, ast.Name) and n.value.id in self.mods):
                return True
            if isinstance(n, ast.Constant) and isinstance(n.value, str):
                if any(re.search(r"\b%s\.%s\b" % (re.escape(m), t), n.value)
                       for m in self.mods for t in _CLIENT_TYPES) \
                        or any(re.search(r"\b%s\b" % re.escape(t), n.value) for t in self.types):
                    return True
        return False

    def _visit(self, node: ast.AST) -> None:
        if isinstance(node, ast.Assign) and self._is_factory(node.value):
            self.keys.update(k for k in map(_key, node.targets) if k)
        elif isinstance(node, ast.AnnAssign) and (self._typed(node.annotation)
                                                  or (node.value is not None and self._is_factory(node.value))):
            if _key(node.target):
                self.keys.add(_key(node.target))
        elif isinstance(node, (ast.With, ast.AsyncWith)):
            for item in node.items:
                if self._is_factory(item.context_expr) and item.optional_vars is not None \
                        and _key(item.optional_vars):
                    self.keys.add(_key(item.optional_vars))
        elif isinstance(node, ast.arg) and self._typed(node.annotation):
            self.keys.add("n:" + node.arg)

    def receiver_ok(self, node: ast.AST, url: str = "") -> bool:
        if isinstance(node, ast.Name) and node.id in self.mods:
            return True
        if bool(_key(node)) and _key(node) in self.keys:
            return True
        # `self.session` / `self.client` injected or inherited, never assigned in this file:
        # trusted only for an unmistakable URL (an absolute one or a rooted path)
        return (isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name)
                and node.value.id in ("self", "cls") and _CLIENT_ATTR.search(node.attr) is not None
                and url.startswith(("/", "http://", "https://")))


def _url_text(node: ast.AST) -> Optional[str]:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return "".join(str(p.value) if isinstance(p, ast.Constant) else "{}" for p in node.values)
    return None


class _Visitor(ast.NodeVisitor):
    def __init__(self, ctx: ExtractContext, facts: FileFacts, primary: str, clients: _Clients) -> None:
        self.ctx, self.facts, self.owner, self.clients = ctx, facts, primary, clients

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
        if isinstance(func, ast.Attribute) and node.args:
            self._call(node, func)
        self.generic_visit(node)

    def _call(self, node, func):
        verb, args = func.attr.lower(), node.args
        if verb == "request" and len(args) >= 2:
            m = args[0]
            verb = m.value.lower() if isinstance(m, ast.Constant) and isinstance(m.value, str) else ""
            args = args[1:]
        raw = _url_text(args[0]) if verb in _VERBS else None
        if raw:
            raw = _HOLE_BASE.sub("", raw)
        if raw and _URLISH.match(raw) and self.clients.receiver_ok(func.value, raw):
            anchor = anchor_at(self.ctx, node.lineno - 1)
            if anchor:
                self.facts.signals.append("http_client")
                self.facts.io_edges.append(
                    mk_edge(self.owner, "http:%s %s" % (verb.upper(), raw), "http_out", anchor))


def emit_http_clients(ctx: ExtractContext, facts: FileFacts, tree: ast.AST, primary: str) -> None:
    if _TEST_PATH.search(ctx.path):
        return
    if not re.search(r"^\s*(?:import|from)\s+(?:%s)\b" % "|".join(_LIBS), "\n".join(ctx.lines), re.M):
        return
    _Visitor(ctx, facts, primary, _Clients(tree)).visit(tree)
