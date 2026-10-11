"""Side effects of one Python file: config reads, tables, routes, entities (B12, B13).

Everything here reads the `ast`, so a docstring, a comment or a variable called
`update` is never mistaken for code, and a key held in a module constant resolves:

* **config**: `os.environ[K]`, `os.environ.get/setdefault/pop(K)`, `os.getenv(K)`, the
  `environ`/`getenv` names imported from `os`, `K in os.environ`; `settings.X` of
  `django.conf`; the fields of a pydantic `BaseSettings` (with its `env_prefix`).
  The key is a literal, a constant of this file, or `${module.NAME}` for a constant
  of another (the resolve phase substitutes it); anything computed is `(dynamic)`.
* **tables**: SQLAlchemy `__tablename__` and `Table("x", ...)`, Django `Meta.db_table`, and
  SQL in string literals (never docstrings) that *begins* with a statement
  (`SELECT/INSERT/UPDATE/DELETE/REPLACE/CREATE TABLE/ALTER TABLE ...`), so prose like
  "update the body of the request" is not SQL.
* **routes**: Flask/Quart/Sanic/aiohttp/FastAPI decorators (verbs from `methods=`, the
  router's own `prefix=`/`url_prefix=`), `add_url_rule`/`add_api_route`, and Django
  `path()`/`re_path()` in a `urlpatterns` list.
"""

from __future__ import annotations

import ast
import re
from typing import Dict, List, Optional, Set, Tuple

from .base import ExtractContext, FileFacts, anchor_at, channel_for_import, mk_edge
from .python_flow import FUNC, abs_module, literal, stmts, target_names

HTTP_VERBS = ("get", "post", "put", "delete", "patch", "head", "options", "trace")
ROUTE_METHODS = frozenset(HTTP_VERBS) | {"route", "api_route", "websocket"}
ROUTER_FACTORIES = {"Flask": "prefix", "Quart": "prefix", "FastAPI": "prefix", "APIRouter": "prefix",
                    "Blueprint": "url_prefix", "Sanic": "", "Bottle": ""}
TASK_DECORATORS = frozenset(["task", "shared_task", "periodic_task", "scheduled_job"])
ENV_DEFAULT_CALLS = frozenset(["get", "setdefault", "pop"])
DYNAMIC = "(dynamic)"
ORM_ROOTS = frozenset(["sqlalchemy", "flask_sqlalchemy", "sqlmodel", "databases", "aiosqlite"])

SQL_START = re.compile(r"\A(?:\s|--[^\n]*\n|/\*[\s\S]*?\*/)*(?:WITH|SELECT|INSERT|UPDATE|DELETE|REPLACE|CREATE|DROP|"
                       r"ALTER|TRUNCATE|MERGE)\b", re.I)
NAME = r"""[`"\[]?([A-Za-z_][\w$]*(?:\.[A-Za-z_][\w$]*)*)[`"\]]?"""
NOT_TABLES = frozenset(["select", "set", "values", "lateral", "unnest", "only", "dual", "table", "where",
                        "if", "not", "exists", "temp", "temporary", "unlogged", "the", "a", "an"])
CTE = re.compile(r"(?:\bWITH(?:\s+RECURSIVE)?|,)\s*(\w+)\s+AS\s*(?:NOT\s+MATERIALIZED\s*|MATERIALIZED\s*)?\(", re.I)
NOT_A_TABLE_FROM = re.compile(r"(?:\b(?:EXTRACT|SUBSTRING|TRIM|OVERLAY)\s*\([^()]*|\bDISTINCT\s+)$", re.I)
SQL_VERBS = (
    ("persist", re.compile(r"\bINSERT\s+(?:OR\s+\w+\s+)?INTO\s+" + NAME, re.I)),
    ("persist", re.compile(r"\bREPLACE\s+INTO\s+" + NAME, re.I)),
    ("persist", re.compile(r"\bUPDATE\s+(?:OR\s+\w+\s+)?" + NAME + r"\s+SET\b", re.I)),
    ("persist", re.compile(r"\bDELETE\s+FROM\s+" + NAME, re.I)),
    ("persist", re.compile(r"\bTRUNCATE\s+(?:TABLE\s+)?" + NAME, re.I)),
    ("schema_own", re.compile(r"\bCREATE\s+(?:(?:GLOBAL\s+|LOCAL\s+)?(?:TEMP|TEMPORARY)\s+|UNLOGGED\s+)?TABLE\s+"
                              r"(?:IF\s+NOT\s+EXISTS\s+)?" + NAME, re.I)),
    ("schema_own", re.compile(r"\b(?:ALTER|DROP)\s+TABLE\s+(?:IF\s+EXISTS\s+)?(?:ONLY\s+)?" + NAME, re.I)),
    ("read", re.compile(r"\b(?:FROM|JOIN)\s+" + NAME + r"(?=[\s,;)]|$)", re.I)),
)


class IO:
    def __init__(self, ctx: ExtractContext, facts: FileFacts, tree: ast.Module, mod: str, pkg: str) -> None:
        self.ctx, self.facts, self.tree, self.mod, self.pkg = ctx, facts, tree, mod, pkg
        self.os_names: Set[str] = set()          # names bound to the `os` module
        self.environ_names: Set[str] = set()     # names bound to os.environ
        self.getenv_names: Set[str] = set()
        self.settings_names: Set[str] = set()    # django.conf.settings
        self.repo_names: Dict[str, Tuple[str, str]] = {}   # name -> (module, original name) for from-imports
        self.mod_aliases: Dict[str, str] = {}    # name -> module for `import a.b as x`
        self.consts: Dict[str, str] = {}         # NAME / Class.NAME -> literal
        self.routers: Dict[str, str] = {}        # variable -> url prefix
        self.docstrings: Set[int] = set()
        self.cur_class = ""                      # simple name of the class being walked
        self.seen: Set[Tuple] = set()
        self.has_django_urls = False
        self.sqlalchemy = False                  # the file imports an ORM that has `Table(name, metadata, ...)`

    # ------------------------------------------------------------- scans
    def prescan(self) -> None:
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    if a.name.split(".")[0] in ORM_ROOTS:
                        self.sqlalchemy = True
                    if a.name == "os":
                        self.os_names.add(a.asname or "os")
                    elif a.asname:
                        self.mod_aliases[a.asname] = a.name
                    else:
                        self.mod_aliases[a.name.split(".")[0]] = a.name.split(".")[0]
            elif isinstance(node, ast.ImportFrom):
                base = abs_module(node.level, node.module or "", self.pkg) or ""
                for a in node.names:
                    name = a.asname or a.name
                    if base == "os" and a.name == "environ":
                        self.environ_names.add(name)
                    elif base == "os" and a.name == "getenv":
                        self.getenv_names.add(name)
                    elif base == "django.conf" and a.name == "settings":
                        self.settings_names.add(name)
                    elif base.startswith("django.urls"):
                        self.has_django_urls = True
                    if base.split(".")[0] in ORM_ROOTS:
                        self.sqlalchemy = True
                    if base:
                        self.repo_names[name] = (base, a.name)
            if isinstance(node, (ast.Module, ast.ClassDef) + FUNC) and node.body:
                first = node.body[0]
                if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
                    self.docstrings.add(id(first.value))
        for node in stmts(self.tree.body):
            if isinstance(node, ast.Assign):
                value = self.fold(node.value, {})
                for t in node.targets:
                    if isinstance(t, ast.Name):
                        if value is not None:
                            self.consts[t.id] = value
                        self.note_router(t.id, node.value)
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.value is not None:
                value = self.fold(node.value, {})
                if value is not None:
                    self.consts[node.target.id] = value
                self.note_router(node.target.id, node.value)
            elif isinstance(node, ast.ClassDef):
                for sub in stmts(node.body):
                    if isinstance(sub, ast.Assign):
                        value = self.fold(sub.value, {})
                        for t in sub.targets:
                            if isinstance(t, ast.Name) and value is not None:
                                self.consts[node.name + "." + t.id] = value

    def note_router(self, var: str, value) -> None:
        if isinstance(value, ast.Call):
            leaf = _leaf(value.func)
            if leaf in ROUTER_FACTORIES:
                prefix = ""
                kw = ROUTER_FACTORIES[leaf]
                for k in value.keywords:
                    if k.arg == kw and kw:
                        prefix = self.fold(k.value, {}) or ""
                self.routers[var] = prefix

    def fold(self, node, _seen) -> Optional[str]:
        """A string constant, `"a" + "b"`, or one made of this file's constants."""
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            a, b = self.fold(node.left, _seen), self.fold(node.right, _seen)
            return a + b if a is not None and b is not None else None
        if isinstance(node, ast.Name) and node.id in self.consts:
            return self.consts[node.id]
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            owner = self.cur_class if node.value.id in ("self", "cls") else node.value.id
            return self.consts.get(owner + "." + node.attr)
        return None

    def key_of(self, node) -> str:
        """The config key an expression names: a literal, or `${module.NAME}` for
        another file's constant (resolved later), else `(dynamic)`."""
        text = self.fold(node, {})
        if text is not None:
            return text
        parts = self.key_parts(node)
        return "".join(parts) if parts else DYNAMIC

    def key_parts(self, node) -> Optional[List[str]]:
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            a, b = self.key_parts(node.left), self.key_parts(node.right)
            return a + b if a is not None and b is not None else None
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return [node.value]
        if isinstance(node, ast.Name):
            if node.id in self.consts:
                return [self.consts[node.id]]
            if node.id in self.repo_names:
                mod, orig = self.repo_names[node.id]
                return ["${%s.%s}" % (mod.rsplit(".", 1)[-1], orig)]
            return None
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            if node.value.id in self.mod_aliases:
                return ["${%s.%s}" % (self.mod_aliases[node.value.id].rsplit(".", 1)[-1], node.attr)]
            if node.value.id in self.repo_names:
                return ["${%s.%s}" % (node.value.id, node.attr)]
            owner = self.cur_class if node.value.id in ("self", "cls") else node.value.id
            if (owner + "." + node.attr) in self.consts:
                return [self.consts[owner + "." + node.attr]]
        return None

    # --------------------------------------------------------------- run
    def edge(self, owner: str, target: str, channel: str, line: int) -> None:
        key = (owner, target, channel, line)
        if key in self.seen:
            return
        anchor = anchor_at(self.ctx, line - 1)
        if anchor is None:
            return
        self.seen.add(key)
        self.facts.io_edges.append(mk_edge(owner, target, channel, anchor))

    def run(self) -> None:
        self.prescan()
        for node in self.tree.body:
            self.visit(node, self.mod, "module")
        if self.has_django_urls:
            self.django_urls()

    def visit(self, node, owner: str, where: str) -> None:
        """Every node once, with the symbol it belongs to (`owner`)."""
        if isinstance(node, ast.ClassDef):
            fqn = owner + ("#" if where == "func" else ".") + node.name
            self.klass(node, fqn)
            for d in node.decorator_list:
                self.visit(d, owner, where)
            for b in node.bases:
                self.visit(b, owner, where)
            outer, self.cur_class = self.cur_class, node.name
            for s in node.body:
                self.visit(s, fqn, "class")
            self.cur_class = outer
        elif isinstance(node, FUNC):
            fqn = owner + ("." if where == "func" else "#") + node.name
            self.decorators(node, fqn)
            for d in node.decorator_list:
                self.visit(d, owner, where)
            for d in node.args.defaults + [x for x in node.args.kw_defaults if x is not None]:
                self.visit(d, owner, where)
            for s in node.body:
                self.visit(s, fqn, "func")
        elif isinstance(node, ast.JoinedStr):
            self.node(node, owner)
            for v in node.values:
                if not isinstance(v, ast.Constant):
                    self.visit(v, owner, where)
        else:
            if isinstance(node, ast.stmt):
                self.stmt(node, owner)
            self.node(node, owner)
            for child in ast.iter_child_nodes(node):
                self.visit(child, owner, where)

    def stmt(self, node, owner: str) -> None:
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == "__tablename__":
                    name = self.fold(node.value, {})
                    if name:
                        self.edge(owner, "table:" + name, "persist", node.lineno)

    def node(self, n, owner: str) -> None:
        if isinstance(n, ast.Subscript) and isinstance(n.ctx, ast.Load) and self.is_environ(n.value):
            self.edge(owner, "config:" + self.key_of(n.slice), "config_read", n.lineno)
        elif isinstance(n, ast.Call):
            self.call(n, owner)
        elif isinstance(n, ast.Compare) and any(isinstance(o, (ast.In, ast.NotIn)) for o in n.ops):
            if any(self.is_environ(c) for c in n.comparators):
                self.edge(owner, "config:" + self.key_of(n.left), "config_read", n.lineno)
        elif isinstance(n, ast.Attribute) and isinstance(n.ctx, ast.Load):
            if isinstance(n.value, ast.Name) and n.value.id in self.settings_names and n.attr.isupper():
                self.edge(owner, "config:" + n.attr, "config_read", n.end_lineno or n.lineno)
        elif isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in self.docstrings:
            self.sql(n.value, n.lineno, owner)
        elif isinstance(n, ast.JoinedStr):
            text = "".join(p.value if isinstance(p, ast.Constant) else "{}" for p in n.values)
            self.sql(text, n.lineno, owner)

    def is_environ(self, node) -> bool:
        if isinstance(node, ast.Name):
            return node.id in self.environ_names
        return (isinstance(node, ast.Attribute) and node.attr == "environ"
                and isinstance(node.value, ast.Name) and node.value.id in self.os_names)

    def call(self, n: ast.Call, owner: str) -> None:
        f = n.func
        line = (f.end_lineno if isinstance(f, ast.Attribute) else n.lineno) or n.lineno
        if n.args:
            if isinstance(f, ast.Name) and f.id in self.getenv_names:
                self.edge(owner, "config:" + self.key_of(n.args[0]), "config_read", line)
            elif isinstance(f, ast.Attribute) and f.attr == "getenv" and isinstance(f.value, ast.Name) \
                    and f.value.id in self.os_names:
                self.edge(owner, "config:" + self.key_of(n.args[0]), "config_read", line)
            elif isinstance(f, ast.Attribute) and f.attr in ENV_DEFAULT_CALLS and self.is_environ(f.value):
                self.edge(owner, "config:" + self.key_of(n.args[0]), "config_read", line)
            elif isinstance(f, ast.Name) and f.id == "getattr" and len(n.args) >= 2 \
                    and isinstance(n.args[0], ast.Name) and n.args[0].id in self.settings_names:
                key = self.fold(n.args[1], {})
                if key:
                    self.edge(owner, "config:" + key, "config_read", line)
        leaf = _leaf(f)
        if leaf == "Table" and self.sqlalchemy and (len(n.args) >= 2 or any(k.arg == "metadata" for k in n.keywords)) \
                and n.args:
            name = self.fold(n.args[0], {})
            if name:
                self.edge(owner, "table:" + name, "persist", n.lineno)
        if leaf in ("add_url_rule", "add_api_route", "add_route", "add_get", "add_post", "add_put",
                    "add_delete", "add_patch") and n.args:
            self.add_rule(n, leaf, owner)

    def sql(self, text: str, line: int, owner: str) -> None:
        start = SQL_START.match(text)
        if not start:
            return
        verb = start.group(0).split()[-1].upper().rstrip("(")
        ctes = {m.lower() for m in CTE.findall(text)}
        for channel, rx in SQL_VERBS:
            if channel == "read" and verb not in ("SELECT", "WITH", "INSERT", "CREATE", "REPLACE"):
                continue
            for m in rx.finditer(text):
                table = m.group(1)
                if table.lower() in NOT_TABLES or table.lower() in ctes or "{" in table or "}" in table:
                    continue
                if channel == "read" and NOT_A_TABLE_FROM.search(text[max(0, m.start() - 40): m.start()]):
                    continue
                at = line + text.count("\n", 0, m.start(1))
                self.edge(owner, "table:" + table, channel, at)

    # ----------------------------------------------------------- classes
    def klass(self, node: ast.ClassDef, fqn: str) -> None:
        bases = [_dotted(b) for b in node.bases]
        if any(b.endswith(("Model", "Base", "Document")) for b in bases):
            self.facts.signals.append("entity")
            self.edge(fqn, "entity:" + fqn, "persist", node.lineno)
        for sub in stmts(node.body):
            if isinstance(sub, ast.ClassDef) and sub.name == "Meta":
                for s in stmts(sub.body):
                    if isinstance(s, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "db_table" for t in s.targets):
                        name = self.fold(s.value, {})
                        if name:
                            self.edge(fqn, "table:" + name, "persist", s.lineno)
        if any(b.split(".")[-1] == "BaseSettings" for b in bases):
            self.settings_class(node, fqn)

    def settings_class(self, node: ast.ClassDef, fqn: str) -> None:
        prefix = ""
        for sub in stmts(node.body):
            call = None
            if isinstance(sub, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "model_config" for t in sub.targets):
                call = sub.value
            if isinstance(call, ast.Call):
                for k in call.keywords:
                    if k.arg == "env_prefix":
                        prefix = self.fold(k.value, {}) or ""
            if isinstance(sub, ast.ClassDef) and sub.name == "Config":
                for s in stmts(sub.body):
                    if isinstance(s, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "env_prefix" for t in s.targets):
                        prefix = self.fold(s.value, {}) or ""
        for sub in stmts(node.body):
            if isinstance(sub, ast.AnnAssign) and isinstance(sub.target, ast.Name) and not sub.target.id.startswith("_") \
                    and sub.target.id not in ("model_config",):
                env = None
                if isinstance(sub.value, ast.Call) and _leaf(sub.value.func) == "Field":
                    for k in sub.value.keywords:
                        if k.arg in ("env", "alias", "validation_alias"):
                            env = self.fold(k.value, {})
                key = env or (prefix + sub.target.id).upper()
                self.edge(fqn, "config:" + key, "config_read", sub.lineno)

    # ------------------------------------------------------------ routes
    def decorators(self, node, fqn: str) -> None:
        for dec in node.decorator_list:
            call = dec if isinstance(dec, ast.Call) else None
            target = call.func if call else dec
            leaf = _leaf(target)
            if leaf in ROUTE_METHODS and isinstance(target, ast.Attribute) and call is not None:
                self.route_decorator(call, target, leaf, fqn, dec)
            elif leaf in TASK_DECORATORS:
                self.facts.signals.append("scheduled")
                self.edge(fqn, "scheduler", "schedule", getattr(dec, "lineno", node.lineno))

    def route_decorator(self, call: ast.Call, target: ast.Attribute, leaf: str, fqn: str, dec) -> None:
        recv = target.value.id if isinstance(target.value, ast.Name) else _dotted(target.value)
        path_node = call.args[0] if call.args else next((k.value for k in call.keywords if k.arg in ("path", "rule")), None)
        if path_node is None and leaf != "route":
            return
        raw = self.route_path(path_node) if path_node is not None else "/"
        if raw is None:
            raw = DYNAMIC
        prefix = self.routers.get(recv, "")
        if prefix and raw != DYNAMIC:
            raw = prefix.rstrip("/") + ("/" + raw.lstrip("/") if raw.strip("/") else "")
        verbs = self.verbs(call, leaf)
        self.facts.signals.append("http_resource")
        for v in verbs:
            self.edge(fqn, "route:%s %s" % (v, raw or "/"), "http_in", dec.lineno)

    def route_path(self, node) -> Optional[str]:
        parts = self.key_parts(node)
        if parts is None and isinstance(node, ast.JoinedStr):
            return "".join(p.value if isinstance(p, ast.Constant) else "{}" for p in node.values)
        return "".join(parts) if parts is not None else None

    def verbs(self, call: ast.Call, leaf: str) -> List[str]:
        if leaf in HTTP_VERBS:
            return [leaf.upper()]
        if leaf == "websocket":
            return ["WS"]
        for k in call.keywords:
            if k.arg == "methods" and isinstance(k.value, (ast.List, ast.Tuple, ast.Set)):
                out = [e.value.upper() for e in k.value.elts if isinstance(e, ast.Constant) and isinstance(e.value, str)]
                if out:
                    return out
        return ["GET"]

    def add_rule(self, n: ast.Call, leaf: str, owner: str) -> None:
        path = self.route_path(n.args[0]) if n.args else None
        handler = None
        for k in n.keywords:
            if k.arg in ("view_func", "endpoint"):
                handler = k.value
        if handler is None and len(n.args) > 1:
            handler = n.args[1]
        if path is None or handler is None:
            return
        verb = leaf.split("_")[-1].upper() if leaf in ("add_get", "add_post", "add_put", "add_delete", "add_patch") else None
        verbs = [verb] if verb else self.verbs(n, "route")
        src = self.handler_symbol(handler, owner)
        self.facts.signals.append("http_resource")
        for v in verbs:
            self.edge(src, "route:%s %s" % (v, path), "http_in", n.lineno)

    def handler_symbol(self, node, owner: str) -> str:
        """A best-effort fqn for a handler expression (labels the route; not resolved)."""
        if isinstance(node, ast.Name):
            if node.id in self.repo_names:
                mod, orig = self.repo_names[node.id]
                return "%s#%s" % (mod, orig)
            return "%s#%s" % (self.mod, node.id)
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            mod = self.mod_aliases.get(node.value.id) or (
                "%s.%s" % self.repo_names[node.value.id] if node.value.id in self.repo_names else None)
            if mod:
                return "%s#%s" % (mod, node.attr)
        if isinstance(node, ast.Call):
            return self.handler_symbol(node.func, owner)
        return owner

    def django_urls(self) -> None:
        for node in stmts(self.tree.body):
            if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "urlpatterns" for t in node.targets):
                if isinstance(node.value, (ast.List, ast.Tuple)):
                    for elt in node.value.elts:
                        self.url_entry(elt, "")
            elif isinstance(node, ast.AugAssign) and isinstance(node.target, ast.Name) and node.target.id == "urlpatterns":
                if isinstance(node.value, (ast.List, ast.Tuple)):
                    for elt in node.value.elts:
                        self.url_entry(elt, "")

    def url_entry(self, call, prefix: str) -> None:
        if not isinstance(call, ast.Call) or _leaf(call.func) not in ("path", "re_path", "url") or len(call.args) < 2:
            return
        raw = self.route_path(call.args[0])
        if raw is None:
            return
        view = call.args[1]
        if isinstance(view, ast.Call) and _leaf(view.func) == "include":
            for sub in (view.args[0].elts if view.args and isinstance(view.args[0], (ast.List, ast.Tuple)) else []):
                self.url_entry(sub, prefix + raw)
            return
        path = "/" + (prefix + raw).lstrip("^").rstrip("$").lstrip("/")
        self.facts.signals.append("http_resource")
        self.edge(self.handler_symbol(view, self.mod), "route:ANY %s" % path, "http_in", call.lineno)


def _leaf(node) -> str:
    return node.id if isinstance(node, ast.Name) else node.attr if isinstance(node, ast.Attribute) else ""


def _dotted(node) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return _dotted(node.value) + "." + node.attr
    if isinstance(node, ast.Call):
        return _dotted(node.func)
    if isinstance(node, ast.Subscript):
        return _dotted(node.value)
    return ""


def analyse(ctx: ExtractContext, facts: FileFacts, tree: ast.Module, mod: str, pkg: str) -> None:
    IO(ctx, facts, tree, mod, pkg).run()
