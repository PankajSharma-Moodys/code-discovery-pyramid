#!/usr/bin/env python3
"""Ground truth for Python extraction, from the interpreter itself.

    python scripts/python_truth.py ROOT [--pkg DIR ...] > truth.jsonl

`ast` gives every def and every call node exactly. Where a call goes is decided
the way Python decides it: the module is imported, the name is looked up in its
real namespace (and `self.m` through the real MRO), and the object found is
traced back to its `def`. That is independent of CDP's own resolver, which never
imports anything. Calls Python cannot settle statically (`obj.m()` where `obj`
is a local, dynamic dispatch) are left out here; `--trace` runs a script under
`sys.monitoring` and records every call that actually happened, which covers them.

Rows (JSON lines, paths relative to ROOT):
  def    file line end_line fqn kind      kind = class|function|method|constant|attr
  call   file line target how             how  = bare|local|self|cls|super|mod|ctor|ref|deco|import|const|attr
  cfg    file line key                    every os.environ / os.getenv read ("" = key not constant)
  skip   file                             module that could not be imported (its sites are partial)

fqn scheme (the one CDP documents): `pkg.mod`, `pkg.mod.Class`, `pkg.mod#func`,
`pkg.mod.Class#method`, `pkg.mod.Class.ATTR`, `pkg.mod#outer.inner`.
"""

from __future__ import annotations

import ast
import contextlib
import importlib
import inspect
import io
import json
import os
import sys
import types
import warnings
from pathlib import Path
from typing import Dict, List, Optional, Tuple

SKIP_DIRS = {".git", "__pycache__", ".venv", "venv", "node_modules", "build", "dist", ".tox"}
FUNC = (ast.FunctionDef, ast.AsyncFunctionDef)
NESTED = (ast.If, ast.Try, ast.With, ast.AsyncWith, ast.For, ast.AsyncFor, ast.While, ast.TryStar
          if hasattr(ast, "TryStar") else ast.Try)


def module_name(rel: str) -> str:
    stem = rel[:-3]
    if stem.endswith("/__init__"):
        stem = stem[: -len("/__init__")]
    return stem.replace("/", ".")


def py_files(root: Path, pkgs: List[str]) -> List[str]:
    out = []
    for base in pkgs or ["."]:
        for dirpath, dirs, files in os.walk(root / base):
            dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
            for f in sorted(files):
                if f.endswith(".py"):
                    out.append(str((Path(dirpath) / f).relative_to(root)))
    return sorted(out)


def stmts(body):
    """Statements of a block, looking through if/try/with/for (not into defs)."""
    for node in body:
        yield node
        if isinstance(node, NESTED):
            for attr in ("body", "orelse", "finalbody"):
                yield from stmts(getattr(node, attr, []) or [])
            for h in getattr(node, "handlers", []) or []:
                yield from stmts(h.body)


def targets(node) -> List[str]:
    out = []

    def one(t):
        if isinstance(t, ast.Name):
            out.append(t.id)
        elif isinstance(t, (ast.Tuple, ast.List)):
            for e in t.elts:
                one(e)
        elif isinstance(t, ast.Starred):
            one(t.value)

    if isinstance(node, ast.Assign):
        for t in node.targets:
            one(t)
    elif isinstance(node, (ast.AnnAssign, ast.AugAssign)):
        one(node.target)
    return out


class Defs:
    """AST-derived defs for one file, in the CDP fqn scheme."""

    def __init__(self, rel: str, tree: ast.Module) -> None:
        self.rel, self.mod = rel, module_name(rel)
        self.rows: List[dict] = []
        self.by_first: Dict[int, str] = {}      # first line (decorators included) -> fqn
        self.nodes: Dict[str, ast.AST] = {}
        self._block(tree.body, self.mod, "module")

    def _add(self, node, fqn: str, kind: str, line: Optional[int] = None) -> None:
        self.rows.append({"t": "def", "file": self.rel, "line": line or node.lineno,
                          "end_line": getattr(node, "end_lineno", None) or node.lineno,
                          "fqn": fqn, "kind": kind})

    def _block(self, body, owner: str, where: str) -> None:
        for node in stmts(body):
            if isinstance(node, ast.ClassDef):
                fqn = owner + ("#" if where == "func" else ".") + node.name
                self._add(node, fqn, "class")
                self.nodes[fqn] = node
                self.by_first[min([d.lineno for d in node.decorator_list] + [node.lineno])] = fqn
                self._block(node.body, fqn, "class")
            elif isinstance(node, FUNC) and any(
                    (d.id if isinstance(d, ast.Name) else d.attr if isinstance(d, ast.Attribute) else "") == "overload"
                    for d in node.decorator_list):
                self._block(node.body, owner, where)    # a signature stub, not the implementation
            elif isinstance(node, FUNC):
                if where == "module":
                    fqn, kind = owner + "#" + node.name, "function"
                elif where == "class":
                    fqn, kind = owner + "#" + node.name, "method"
                else:
                    fqn, kind = owner + "." + node.name, "function"
                self._add(node, fqn, kind)
                self.nodes[fqn] = node
                self.by_first[min([d.lineno for d in node.decorator_list] + [node.lineno])] = fqn
                self._block(node.body, fqn, "func")
            elif isinstance(node, (ast.Assign, ast.AnnAssign)) and where in ("module", "class"):
                for name in targets(node):
                    if where == "class":
                        self._add(node, owner + "." + name, "attr")
                    elif name.isupper() or (isinstance(node, ast.AnnAssign) and "Final" in ast.unparse(node.annotation)):
                        self._add(node, owner + "." + name, "constant")


class Truth:
    def __init__(self, root: Path, pkgs: List[str], extra_path: List[str] = ()) -> None:
        self.extra_path = list(extra_path)
        self.root = root
        self.files = py_files(root, pkgs)
        self.trees: Dict[str, ast.Module] = {}
        self.defs: Dict[str, Defs] = {}
        for rel in self.files:
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    self.trees[rel] = ast.parse((root / rel).read_text(errors="replace"))
            except SyntaxError:
                continue
            self.defs[rel] = Defs(rel, self.trees[rel])
        self.mods: Dict[str, Optional[types.ModuleType]] = {}
        self.rows: List[dict] = []
        self.abs = {str((root / r).resolve()): r for r in self.files}

    # ------------------------------------------------------------ import
    def load(self) -> None:
        sys.path.insert(0, str(self.root))
        for extra in self.extra_path:                  # source roots (`src/`) and stand-ins for third-party packages
            sys.path.insert(0, str((self.root / extra) if not Path(extra).is_absolute() else Path(extra)))
        for rel in self.files:
            name = module_name(rel)
            sink = io.StringIO()
            try:
                with contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink), warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    self.mods[rel] = importlib.import_module(name)
            except BaseException as exc:  # noqa: BLE001 - a module that cannot import is a fact, not a crash
                self.mods[rel] = None
                self.rows.append({"t": "skip", "file": rel, "why": type(exc).__name__})

    # ----------------------------------------------------------- targets
    def repo_file(self, path: str) -> Optional[str]:
        return self.abs.get(str(Path(path).resolve())) if path else None

    def fn_fqn(self, obj) -> Optional[str]:
        for _ in range(8):
            if isinstance(obj, (staticmethod, classmethod)):
                obj = obj.__func__
            elif isinstance(obj, property):
                obj = obj.fget
            elif isinstance(obj, types.MethodType):
                obj = obj.__func__
            elif hasattr(obj, "__wrapped__"):
                obj = obj.__wrapped__
            else:
                break
        code = getattr(obj, "__code__", None)
        if code is None:
            return None
        rel = self.repo_file(code.co_filename)
        d = self.defs.get(rel) if rel else None
        return d.by_first.get(code.co_firstlineno) if d else None

    def cls_fqn(self, cls) -> Optional[str]:
        if not isinstance(cls, type) or "<locals>" in cls.__qualname__:
            return None
        mod = sys.modules.get(cls.__module__)
        rel = self.repo_file(getattr(mod, "__file__", "") or "")
        if rel is None:
            return None
        fqn = cls.__module__ + "." + cls.__qualname__
        d = self.defs.get(rel)
        return fqn if d and fqn in d.nodes else None

    def target_of(self, obj) -> Optional[Tuple[str, str]]:
        """(fqn, how-kind) of a repo function, class or method object."""
        if isinstance(obj, type):
            c = self.cls_fqn(obj)
            return (c, "class") if c else None
        f = self.fn_fqn(obj)
        return (f, "fn") if f else None

    def ctor_target(self, cls) -> Optional[str]:
        c = self.cls_fqn(cls)
        if not c:
            return None
        for k in cls.__mro__:
            raw = k.__dict__.get("__init__")
            if raw is not None:
                f = self.fn_fqn(raw)
                if f:
                    return f
                if k is not object:
                    break
        return c

    # ------------------------------------------------------------- walk
    def run(self) -> None:
        for rel, d in self.defs.items():
            self.rows.extend(d.rows)
        for rel, tree in self.trees.items():
            mod = self.mods.get(rel)
            _Walker(self, rel, tree, mod).visit_module()


def local_names(node) -> Tuple[set, Dict[str, str]]:
    """Names bound in a function body (not nested scopes) -> (names, nested defs)."""
    names: set = set()
    nested: Dict[str, str] = {}

    class V(ast.NodeVisitor):
        def visit_FunctionDef(self, n):
            names.add(n.name)
            nested[n.name] = "def"

        visit_AsyncFunctionDef = visit_FunctionDef

        def visit_ClassDef(self, n):
            names.add(n.name)
            nested[n.name] = "class"

        def visit_Lambda(self, n):
            pass

        def visit_Name(self, n):
            if isinstance(n.ctx, (ast.Store, ast.Del)):
                names.add(n.id)

        def visit_ExceptHandler(self, n):
            if n.name:
                names.add(n.name)
            self.generic_visit(n)

        def visit_Import(self, n):
            for a in n.names:
                names.add((a.asname or a.name).split(".")[0])

        visit_ImportFrom = visit_Import

        def visit_Global(self, n):
            for g in n.names:
                names.discard(g)

        def visit_ListComp(self, n):
            pass

        visit_SetComp = visit_GeneratorExp = visit_DictComp = visit_ListComp

    v = V()
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
        a = node.args
        for arg in a.posonlyargs + a.args + a.kwonlyargs + [x for x in (a.vararg, a.kwarg) if x]:
            names.add(arg.arg)
        body = node.body if isinstance(node.body, list) else []
        for s in body:
            v.visit(s)
    else:
        for s in node.body:
            v.visit(s)
    declared = set()
    for sub in ast.walk(node):
        if isinstance(sub, ast.Global):
            declared.update(sub.names)
    return names - declared, nested


class _Walker:
    def __init__(self, truth: Truth, rel: str, tree: ast.Module, mod) -> None:
        self.t, self.rel, self.tree, self.mod = truth, rel, tree, mod
        self.mname = module_name(rel)
        self.defs = truth.defs[rel]
        self.scopes: List[dict] = []
        self.environ = os.environ

    # scope = {kind, names, nested, owner(fqn), cls(runtime class or None), first(param name), static}
    def visit_module(self) -> None:
        self.scopes = [{"kind": "module", "names": set(), "nested": {}, "owner": self.mname}]
        self.block(self.tree.body)

    def block(self, body) -> None:
        for s in body:
            self.stmt(s)

    # ---------------------------------------------------------- scoping
    def class_obj(self, fqn: str):
        if self.mod is None:
            return None
        rest = fqn[len(self.mname) + 1:]
        obj = self.mod
        for part in rest.split("."):
            obj = getattr(obj, part, None)
            if obj is None:
                return None
        return obj if isinstance(obj, type) else None

    def lookup(self, name: str):
        """-> ('local', None) | ('def', fqn, kind) | ('obj', object) | None"""
        for i in range(len(self.scopes) - 1, 0, -1):
            sc = self.scopes[i]
            if sc["kind"] == "class" and i != len(self.scopes) - 1:
                continue
            if name in sc["names"]:
                if name in sc["nested"]:
                    for cand in (sc["owner"] + "." + name, sc["owner"] + "#" + name):
                        node = self.defs.nodes.get(cand)
                        if node is not None:
                            return ("def", cand, "class" if isinstance(node, ast.ClassDef) else "def")
                return ("local", None)
        if self.mod is not None and name in vars(self.mod):
            return ("obj", vars(self.mod)[name])
        return None

    def self_binding(self, name: str):
        """('inst'|'cls', class) when `name` is the first parameter of an enclosing method."""
        for sc in reversed(self.scopes[1:]):
            if sc["kind"] == "class":
                return None
            if sc.get("first") == name and sc.get("cls") is not None:
                return ("cls" if sc.get("classmethod") else "inst", sc["cls"])
            if name in sc["names"]:
                return None
        return None

    # --------------------------------------------------------- statements
    def stmt(self, node) -> None:
        if isinstance(node, FUNC):
            for d in node.decorator_list:
                self.expr(d, deco=True)
            self.args_defaults(node.args)
            self.ann(node)
            names, nested = local_names(node)
            parent = self.scopes[-1]
            owner = self._fqn_of(node, parent)
            first = None
            static = any(isinstance(d, ast.Name) and d.id == "staticmethod" for d in node.decorator_list)
            clsm = any(isinstance(d, ast.Name) and d.id == "classmethod" for d in node.decorator_list)
            cls = parent.get("clsobj") if parent["kind"] == "class" else None
            allargs = node.args.posonlyargs + node.args.args
            if parent["kind"] == "class" and allargs and not static:
                first = allargs[0].arg
            self.scopes.append({"kind": "func", "names": names, "nested": nested, "owner": owner,
                                "cls": cls, "first": first, "classmethod": clsm, "clsfqn": parent.get("owner")})
            self.block(node.body)
            self.scopes.pop()
        elif isinstance(node, ast.ClassDef):
            for d in node.decorator_list:
                self.expr(d, deco=True)
            for b in node.bases:
                self.expr(b)
            for k in node.keywords:
                self.expr(k.value)
            names, nested = set(), {}
            for s in stmts(node.body):
                for n in targets(s):
                    names.add(n)
                if isinstance(s, FUNC):
                    names.add(s.name)
                    nested[s.name] = "def"
                elif isinstance(s, ast.ClassDef):
                    names.add(s.name)
                    nested[s.name] = "class"
            parent = self.scopes[-1]
            fqn = self._fqn_of(node, parent)
            clsobj = self.class_obj(fqn) if fqn and "#" not in fqn else None
            self.scopes.append({"kind": "class", "names": names, "nested": nested, "owner": fqn,
                                "clsobj": clsobj})
            if clsobj is not None and any(k.__name__ == "BaseSettings" for k in clsobj.__mro__):
                self.settings_fields(node, clsobj)
            self.block(node.body)
            self.scopes.pop()
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            self.imp(node)
        else:
            for field, value in ast.iter_fields(node):
                if isinstance(value, list):
                    for v in value:
                        if isinstance(v, ast.stmt):
                            self.stmt(v)
                        elif isinstance(v, ast.AST):
                            self.expr(v)
                elif isinstance(value, ast.stmt):
                    self.stmt(value)
                elif isinstance(value, ast.AST):
                    self.expr(value)

    def _fqn_of(self, node, parent) -> Optional[str]:
        first = min([d.lineno for d in node.decorator_list] + [node.lineno])
        return self.defs.by_first.get(first)

    def args_defaults(self, a) -> None:
        for d in a.defaults + [x for x in a.kw_defaults if x is not None]:
            self.expr(d)

    def ann(self, node) -> None:
        # annotations are string-evaluated lazily under `from __future__`; not references we claim
        pass

    def imp(self, node) -> None:
        if self.mod is None or not isinstance(node, ast.ImportFrom):
            return
        base = node.module or ""
        if node.level:
            pkg = self.mname if self.rel.endswith("__init__.py") else self.mname.rsplit(".", 1)[0] if "." in self.mname else ""
            parts = pkg.split(".") if pkg else []
            parts = parts[: len(parts) - (node.level - 1)] if node.level > 1 else parts
            base = ".".join(parts + ([base] if base else []))
        target_mod = sys.modules.get(base)
        for a in node.names:
            if target_mod is None or a.name == "*":
                continue
            obj = getattr(target_mod, a.name, None)
            tgt = self.t.target_of(obj) if obj is not None else None
            if tgt:
                self.emit(node.lineno, tgt[0], "import")
            else:
                c = self.const_target(base, a.name)
                if c:
                    self.emit(node.lineno, c, "import")

    # ------------------------------------------------------ expressions
    def emit(self, line: int, target: str, how: str) -> None:
        self.t.rows.append({"t": "call", "file": self.rel, "line": line, "target": target, "how": how})

    def const_target(self, modname: str, name: str, depth: int = 0) -> Optional[str]:
        """`modname.name` when that is a module-level constant defined (or re-imported) in the repo."""
        if depth > 6:
            return None
        for rel, d in self.t.defs.items():
            if d.mod != modname:
                continue
            fqn = modname + "." + name
            if any(r["fqn"] == fqn and r["kind"] == "constant" for r in d.rows):
                return fqn
            for node in ast.walk(self.t.trees[rel]):
                if isinstance(node, ast.ImportFrom) and any((a.asname or a.name) == name for a in node.names):
                    base = node.module or ""
                    if node.level:
                        pkg = modname if rel.endswith("__init__.py") else modname.rsplit(".", 1)[0] if "." in modname else ""
                        parts = pkg.split(".") if pkg else []
                        parts = parts[: len(parts) - (node.level - 1)] if node.level > 1 else parts
                        base = ".".join(parts + ([base] if base else []))
                    orig = next(a.name for a in node.names if (a.asname or a.name) == name)
                    return self.const_target(base, orig, depth + 1)
        return None

    def value(self, node):
        """Evaluate Name/Attribute/super() chains over real objects.
        -> ('obj', o) | ('inst', cls) | ('super', cls) | ('def', fqn, kind) | None"""
        if isinstance(node, ast.Name):
            sb = self.self_binding(node.id)
            if sb:
                return sb
            r = self.lookup(node.id)
            if r is None or r[0] == "local":
                return None
            return r
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "super" and not node.args:
            for sc in reversed(self.scopes[1:]):
                if sc["kind"] == "class":
                    break
                if sc.get("cls") is not None:
                    return ("super", sc["cls"])
            return None
        if isinstance(node, ast.Attribute):
            base = self.value(node.value)
            if base is None:
                return None
            kind = base[0]
            if kind == "obj":
                o = base[1]
                if isinstance(o, type):
                    kind, base = "cls", ("cls", o)
                elif isinstance(o, types.ModuleType):
                    got = getattr(o, node.attr, inspect.Parameter.empty)
                    return None if got is inspect.Parameter.empty else ("obj", got)
                else:
                    return None
            if kind in ("cls", "inst"):
                try:
                    raw = inspect.getattr_static(base[1], node.attr)
                except AttributeError:
                    return None
                return ("raw", raw, base[1])
            if kind == "super":
                cls = base[1]
                mro = cls.__mro__
                for k in mro[1:]:
                    if node.attr in k.__dict__:
                        return ("raw", k.__dict__[node.attr], cls)
                return None
        return None

    def resolve_target(self, v) -> Optional[Tuple[str, str]]:
        if v is None:
            return None
        if v[0] == "def":
            return (v[1], "def" if v[2] == "def" else "class")
        o = v[1]
        return self.t.target_of(o) if v[0] in ("obj", "raw") else None

    def how_of(self, node) -> str:
        if isinstance(node, ast.Name):
            return "bare"
        base = node.value
        if isinstance(base, ast.Call):
            return "super"
        root = base
        while isinstance(root, ast.Attribute):
            root = root.value
        if isinstance(root, ast.Name):
            sb = self.self_binding(root.id)
            if sb:
                return "cls" if sb[0] == "cls" else "self"
        return "mod"

    def expr(self, node, deco: bool = False) -> None:
        if isinstance(node, ast.Lambda):
            names, nested = local_names(node)
            self.args_defaults(node.args)
            self.scopes.append({"kind": "func", "names": names, "nested": nested, "owner": self.scopes[-1]["owner"],
                                "cls": None, "first": None})
            self.expr(node.body)
            self.scopes.pop()
            return
        if isinstance(node, (ast.ListComp, ast.SetComp, ast.GeneratorExp, ast.DictComp)):
            names = {n.id for g in node.generators for n in ast.walk(g.target) if isinstance(n, ast.Name)}
            first = node.generators[0].iter
            self.expr(first)
            self.scopes.append({"kind": "func", "names": names, "nested": {}, "owner": self.scopes[-1]["owner"],
                                "cls": None, "first": None})
            for i, g in enumerate(node.generators):
                if i:
                    self.expr(g.iter)
                for c in g.ifs:
                    self.expr(c)
            for part in ((node.key, node.value) if isinstance(node, ast.DictComp) else (node.elt,)):
                self.expr(part)
            self.scopes.pop()
            return
        self.config(node)
        if isinstance(node, ast.Call):
            self.call(node)
            return
        if isinstance(node, (ast.Name, ast.Attribute)) and isinstance(node.ctx, ast.Load):
            self.reference(node, "deco" if deco else "ref")
            if isinstance(node, ast.Attribute):
                self.expr(node.value)
            return
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.AST):
                self.expr(child)

    def line_of(self, node) -> int:
        return node.end_lineno if isinstance(node, ast.Attribute) else node.lineno

    def reference(self, node, how: str) -> None:
        v = self.value(node)
        tgt = self.resolve_target(v)
        if tgt:
            self.emit(self.line_of(node), tgt[0], how)
            return
        # constants / class attributes (not functions): look the name up in the defining AST
        if v is not None and v[0] in ("obj", "raw") and not isinstance(node, ast.Name):
            return
        c = self.const_ref(node)
        if c:
            self.emit(self.line_of(node), c, "const")

    def const_ref(self, node) -> Optional[str]:
        """`NAME`, `mod.NAME`, `Cls.NAME`, `self.NAME` that denote a repo constant / class attribute."""
        if isinstance(node, ast.Name):
            r = self.lookup(node.id)
            if r is None or r[0] != "obj" or self.mod is None:
                return None
            # defined here, or imported: follow `from x import NAME`
            return self.const_target(self.mname, node.id)
        if isinstance(node, ast.Attribute):
            base = self.value(node.value)
            if base is None:
                return None
            if base[0] == "obj" and isinstance(base[1], types.ModuleType):
                return self.const_target(base[1].__name__, node.attr)
            cls = None
            if base[0] in ("cls", "inst"):
                cls = base[1]
            elif base[0] == "obj" and isinstance(base[1], type):
                cls = base[1]
            if cls is not None:
                for k in cls.__mro__:
                    fqn = self.t.cls_fqn(k)
                    if fqn and k.__dict__.get(node.attr, None) is not None or (fqn and node.attr in getattr(k, "__annotations__", {})):
                        cand = fqn + "." + node.attr
                        d = self.t.defs.get(self.t.repo_file(getattr(sys.modules.get(k.__module__), "__file__", "")))
                        if d and any(r["fqn"] == cand for r in d.rows):
                            return cand
                        break
        return None

    def call(self, node: ast.Call) -> None:
        f = node.func
        if isinstance(f, (ast.Name, ast.Attribute)):
            v = self.value(f)
            tgt = None
            how = None
            if v is not None:
                if v[0] == "def":
                    fqn, kind = v[1], v[2]
                    if kind == "def":
                        tgt, how = fqn, "local"
                    else:
                        tgt, how = self.local_ctor(fqn), "ctor"
                else:
                    o = v[1]
                    if isinstance(o, type) and v[0] in ("obj", "raw"):
                        t = self.t.ctor_target(o)
                        if t:
                            tgt, how = t, "ctor"
                    else:
                        r = self.t.target_of(o) if v[0] in ("obj", "raw") else None
                        if r:
                            tgt, how = r[0], self.how_of(f)
            if tgt:
                self.emit(self.line_of(f), tgt, how)
            if isinstance(f, ast.Attribute):
                # the receiver is a reference in its own right
                self.expr(f.value)
            elif how == "ctor" or v is not None:
                pass
            if how == "ctor" and v is not None:
                cls_t = self.resolve_target(v)
                if cls_t:
                    self.emit(self.line_of(f), cls_t[0], "ref")
        else:
            self.expr(f)
        for a in node.args:
            self.expr(a)
        for k in node.keywords:
            self.expr(k.value)

    def local_ctor(self, fqn: str) -> str:
        return fqn

    # ------------------------------------------------------------ config
    def settings_fields(self, node: ast.ClassDef, cls) -> None:
        """Every annotated field of a pydantic BaseSettings is read from the environment."""
        prefix = getattr(getattr(cls, "Config", None), "env_prefix", "") or \
            (getattr(cls, "model_config", None) or {}).get("env_prefix", "")
        for s in node.body:
            if isinstance(s, ast.AnnAssign) and isinstance(s.target, ast.Name):
                self.t.rows.append({"t": "cfg", "file": self.rel, "line": s.lineno,
                                    "key": (prefix + s.target.id).upper()})

    def is_settings(self, node) -> bool:
        v = self.value(node)
        return bool(v) and v[0] == "obj" and type(v[1]).__module__.startswith("django.conf")

    def is_environ(self, node) -> bool:
        v = self.value(node)
        return bool(v) and v[0] == "obj" and v[1] is os.environ

    def key_of(self, node) -> str:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        v = self.value(node) if isinstance(node, (ast.Name, ast.Attribute)) else None
        if v and v[0] in ("obj", "raw") and isinstance(v[1], str):
            return v[1]
        return ""

    def config(self, node) -> None:
        rec = None
        if isinstance(node, ast.Subscript) and isinstance(node.ctx, ast.Load) and self.is_environ(node.value):
            rec = (node.lineno, self.key_of(node.slice))
        elif isinstance(node, ast.Call):
            f = node.func
            v = self.value(f) if isinstance(f, (ast.Name, ast.Attribute)) else None
            if v and v[0] == "obj" and v[1] is os.getenv and node.args:
                rec = (self.line_of(f), self.key_of(node.args[0]))
            elif isinstance(f, ast.Attribute) and f.attr in ("get", "setdefault", "pop") and self.is_environ(f.value) and node.args:
                rec = (self.line_of(f), self.key_of(node.args[0]))
        elif isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Load) and self.is_settings(node.value) \
                and node.attr.isupper():
            rec = (self.line_of(node), node.attr)
        elif isinstance(node, ast.Compare) and any(isinstance(o, (ast.In, ast.NotIn)) for o in node.ops):
            if any(self.is_environ(c) for c in node.comparators):
                rec = (node.lineno, self.key_of(node.left))
        if rec:
            self.t.rows.append({"t": "cfg", "file": self.rel, "line": rec[0], "key": rec[1]})


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("root", type=Path)
    ap.add_argument("--pkg", action="append", default=[], help="sub-directory to index (default: whole root)")
    ap.add_argument("--path", action="append", default=[],
                    help="extra sys.path entry (relative to ROOT unless absolute): a `src/` root, or stubs")
    a = ap.parse_args()
    truth = Truth(a.root.resolve(), a.pkg, a.path)
    truth.load()
    truth.run()
    for row in truth.rows:
        print(json.dumps(row, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
