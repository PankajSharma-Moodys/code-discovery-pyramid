"""Definitions and call/reference sites for one Python file (B19, B20).

One pass over the `ast` with a scope stack. Every call (`f()`, `self.m()`,
`mod.f()`, `obj.method()`), reference (a function passed as an argument,
a constant, a decorator, a base class, an imported name) becomes a `uses[]` row
carrying an *expression*, not a guessed target: the start of a chain and the
steps to follow from it, written

    M:pkg.mod|.Class|()|.method     module `pkg.mod`, its `Class`, an instance, `.method`
    D:pkg.mod.Class|()              the class this file defines, an instance of it (`self`)
    P:pkg.mod.Class|.__init__       `super()` inside `Class`

The extractor sees one file, so anything that needs another file (is `Class` a
re-export? which class declares `method`? what does `f` return?) is left to
`cdp/pytypes.py`, which walks the expression against the symbol table and drops
what it cannot settle. A receiver whose type this file cannot establish yields no
row at all, never a guessed one.

Types come from: `self`/`cls`; annotations; `x = Class(...)`, `x = f()` (the
callee's annotated or inferred return type, resolved later); `with C() as x`;
`self.attr = ...` (recorded as a `field` define with its type) and module-level
`name = ...` (a `pybind` row, so `mod.name.method()` works from other files).
"""

from __future__ import annotations

import ast
import builtins
import sys
from typing import Dict, List, Optional, Set, Tuple

from .base import ExtractContext, FileFacts, anchor_at, mk_define, mk_use

Ex = Tuple[str, Tuple[str, ...]]

FUNC = (ast.FunctionDef, ast.AsyncFunctionDef)
BLOCKS = (ast.If, ast.Try, ast.With, ast.AsyncWith, ast.For, ast.AsyncFor, ast.While)
STDLIB = frozenset(getattr(sys, "stdlib_module_names", ())) | {"__future__", "typing_extensions"}
BUILTINS = frozenset(dir(builtins))
PROPERTY_DECORATORS = frozenset(["property", "cached_property", "abstractproperty"])
MAX_STEPS = 8
UNION_NAMES = frozenset(["Optional", "Union", "Annotated", "ClassVar", "Final", "Required", "NotRequired",
                         "ReadOnly"])
TYPE_NAMES = frozenset(["Type", "type"])
DICT_NAMES = frozenset(["Dict", "dict", "Mapping", "MutableMapping", "DefaultDict", "defaultdict", "OrderedDict"])
LIST_NAMES = DICT_NAMES | frozenset(["List", "list", "Sequence", "MutableSequence", "Iterable", "Iterator", "Set", "set",
                                     "FrozenSet", "frozenset", "Deque", "deque", "Collection", "AbstractSet"])


def ex_str(ex: Ex) -> str:
    return "|".join((ex[0],) + ex[1])


def stmts(body):
    """Statements of a block, looking through if/try/with/for/while (not into defs)."""
    for node in body:
        yield node
        if isinstance(node, BLOCKS) or type(node).__name__ == "TryStar":
            for attr in ("body", "orelse", "finalbody"):
                yield from stmts(getattr(node, attr, None) or [])
            for h in getattr(node, "handlers", None) or []:
                yield from stmts(h.body)


def target_names(target) -> List[str]:
    if isinstance(target, ast.Name):
        return [target.id]
    if isinstance(target, (ast.Tuple, ast.List)):
        return [n for e in target.elts for n in target_names(e)]
    if isinstance(target, ast.Starred):
        return target_names(target.value)
    return []


def visibility(name: str) -> str:
    if name.startswith("__") and not name.endswith("__"):
        return "private"
    return "internal" if name.startswith("_") else "public"


def literal(node) -> Optional[str]:
    """A constant's literal value; `"a" + "b"` and f-strings of constants fold."""
    if isinstance(node, ast.Constant) and isinstance(node.value, (str, int, float, bool)):
        return str(node.value)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        a, b = literal(node.left), literal(node.right)
        if a is not None and b is not None and isinstance(getattr(node.left, "value", ""), str):
            return a + b
    return None


def abs_module(level: int, name: str, pkg: str) -> Optional[str]:
    if not level:
        return name
    parts = pkg.split(".") if pkg else []
    if level - 1 > len(parts):
        return None
    parts = parts[: len(parts) - (level - 1)]
    return ".".join(parts + ([name] if name else []))


class Scope:
    def __init__(self, kind: str, owner: str, cls: Optional[str] = None) -> None:
        self.kind = kind            # module | class | func
        self.owner = owner          # fqn that `from_symbol` names
        self.cls = cls              # class fqn, for methods and class bodies
        self.ents: Dict[str, Optional[Ex]] = {}   # names that ARE entities (nested defs, imports)
        self.vars: Dict[str, Optional[Ex]] = {}   # variables: name -> type (None: unknown)
        self.returns: List[Optional[Ex]] = []
        self.has_yield = False
        self.first: Optional[str] = None


class Flow:
    def __init__(self, ctx: ExtractContext, facts: FileFacts, tree: ast.Module, mod: str, pkg: str) -> None:
        self.ctx, self.facts, self.tree, self.mod, self.pkg = ctx, facts, tree, mod, pkg
        self.mod_names: Dict[str, Optional[Ex]] = {}
        self.mod_alts: Dict[str, List[Ex]] = {}     # a name bound two ways (`def f` / `from .x import f`)
        self.stack: List[Scope] = []
        self._anchors: Dict[int, Optional[Dict]] = {}
        self._seen: Set[Tuple] = set()
        self.defined: Dict[str, Dict] = {}          # fqn -> define row (deduplicated)
        self.ftypes: Dict[str, Optional[str]] = {}
        self.lines = ctx.lines

    # ------------------------------------------------------------ plumbing
    def anchor(self, line: int) -> Optional[Dict]:
        if line not in self._anchors:
            self._anchors[line] = anchor_at(self.ctx, line - 1)
        return self._anchors[line]

    def scope(self) -> Scope:
        return self.stack[-1]

    def row(self, kind: str, ex: Ex, line: int, how: str = "") -> None:
        if len(ex[1]) > MAX_STEPS:
            return
        key = (kind, line, ex_str(ex))
        if key in self._seen:
            return
        anchor = self.anchor(line)
        if anchor is None:
            return
        self._seen.add(key)
        row = mk_use(ex_str(ex), anchor, via_import=False, resolved="external")
        row["kind"] = kind
        row["py"] = ex_str(ex)
        row["from_symbol"] = self.scope().owner
        self.facts.uses.append(row)

    def define(self, fqn: str, kind: str, vis: str, node, value: Optional[str] = None,
               ret: Optional[Ex] = None, line: Optional[int] = None):
        """One define per fqn per file (a property's setter, a conditional redefinition
        are the same symbol). Returns the row, or None when the line is not citable."""
        prior = self.defined.get(fqn)
        if prior is not None:
            return prior
        anchor = self.anchor(line or node.lineno)
        if anchor is None:
            return None
        end = getattr(node, "end_lineno", None) or node.lineno
        row = mk_define(fqn, kind, vis, anchor, value=value, end_line=end)
        if ret is not None:
            row["ret"] = ex_str(ret)
        self.defined[fqn] = row
        self.facts.defines.append(row)
        return row

    def note_ftype(self, fqn: str, ex: Optional[Ex], value=None) -> None:
        """The type of a field or constant: every assignment must agree, or it is unknown."""
        if value is not None and _is_none(value):
            return
        s = ex_str(ex) if ex else None
        if fqn not in self.ftypes:
            self.ftypes[fqn] = s
        elif self.ftypes[fqn] != s:
            self.ftypes[fqn] = None

    # ------------------------------------------------------------- names
    def lookup(self, name: str) -> Tuple[Optional[Ex], bool]:
        """(expression, is_entity). An entity is something the name *is* (a def, a
        class, an import); a variable only has a type."""
        for i in range(len(self.stack) - 1, 0, -1):
            sc = self.stack[i]
            if sc.kind == "class" and i != len(self.stack) - 1:
                continue
            if name in sc.ents:
                return sc.ents[name], True
            if name in sc.vars:
                return sc.vars[name], False
        if name in self.mod_names:
            return self.mod_names[name], True
        return None, False

    def cls_scope(self) -> Optional[Scope]:
        for sc in reversed(self.stack):
            if sc.kind == "class":
                return sc
            if sc.kind == "func" and sc.cls:
                return sc
        return None

    def ex_of(self, node) -> Optional[Ex]:
        if isinstance(node, ast.Name):
            return self.lookup(node.id)[0]
        if isinstance(node, ast.Attribute):
            base = self.ex_of(node.value)
            return (base[0], base[1] + ("." + node.attr,)) if base else None
        if isinstance(node, ast.Call):
            f = node.func
            if isinstance(f, ast.Name) and f.id == "super":
                sc = self.cls_scope()
                return ("P:" + sc.cls, ()) if sc and sc.cls else None
            base = self.ex_of(f)
            return (base[0], base[1] + ("()",)) if base else None
        if isinstance(node, ast.Await):
            return self.ex_of(node.value)
        if isinstance(node, ast.Subscript):
            base = self.ex_of(node.value)
            if base is None:
                return None
            sl = node.slice
            idx = "[%d]" % sl.value if isinstance(sl, ast.Constant) and isinstance(sl.value, int) else "[]"
            return (base[0], base[1] + (idx,))
        if isinstance(node, ast.Tuple) and 0 < len(node.elts) <= 6:
            items = [self.ex_of(e) for e in node.elts]
            if all(i is None or not i[0].startswith(("TUP:", "LST:")) for i in items):
                return ("TUP:" + "&&".join(ex_str(i).replace("|", "~") if i else "" for i in items), ())
            return None
        if isinstance(node, ast.IfExp):
            a, b = self.ex_of(node.body), self.ex_of(node.orelse)
            if _is_none(node.orelse):
                return a
            return b if _is_none(node.body) else (a if a == b else None)
        if isinstance(node, ast.BoolOp):
            exs = [self.ex_of(v) for v in node.values if not _is_none(v)]
            return exs[0] if exs and all(e == exs[0] for e in exs) else None
        if isinstance(node, ast.NamedExpr):
            return self.ex_of(node.value)
        return None

    def ann_ex(self, node) -> Optional[Ex]:
        """The instance type an annotation denotes (None: not a repository-style name)."""
        if node is None:
            return None
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            try:
                return self.ann_ex(ast.parse(node.value.strip(), mode="eval").body)
            except SyntaxError:
                return None
        if isinstance(node, (ast.Name, ast.Attribute)):
            if isinstance(node, ast.Name) and node.id == "Self":
                sc = self.cls_scope()
                return ("D:" + sc.cls, ("()",)) if sc and sc.cls else None
            ex = self.ex_of(node)
            return (ex[0], ex[1] + ("()",)) if ex else None
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
            left, right = self.ann_ex(node.left), self.ann_ex(node.right)
            if _is_none(node.left):
                return right
            if _is_none(node.right):
                return left
            return left if left == right else None
        if isinstance(node, ast.Subscript):
            head = node.value
            name = head.id if isinstance(head, ast.Name) else head.attr if isinstance(head, ast.Attribute) else ""
            sl = node.slice
            elts = sl.elts if isinstance(sl, ast.Tuple) else [sl]
            if name in UNION_NAMES:
                if name == "Annotated":
                    elts = elts[:1]
                cand = [e for e in elts if not _is_none(e)]
                return self.ann_ex(cand[0]) if len(cand) == 1 else None
            if name in LIST_NAMES and elts:
                inner = self.ann_ex(elts[-1] if name in DICT_NAMES else elts[0])
                return ("LST:" + ex_str(inner).replace("|", "~"), ()) if inner else None
            if name in ("Tuple", "tuple") and elts:
                if len(elts) == 2 and isinstance(elts[1], ast.Constant) and elts[1].value is Ellipsis:
                    inner = self.ann_ex(elts[0])
                    return ("LST:" + ex_str(inner).replace("|", "~"), ()) if inner else None
                items = [self.ann_ex(e) for e in elts[:6]]
                if any(items):
                    return ("TUP:" + "&&".join(ex_str(i).replace("|", "~") if i else "" for i in items), ())
                return None
            if name in TYPE_NAMES and elts:
                inner = self.ann_ex(elts[0])
                return (inner[0], inner[1][:-1]) if inner and inner[1] and inner[1][-1] == "()" else None
        return None

    # --------------------------------------------------------- module scan
    def bind_module(self, name: str, ex: Optional[Ex]) -> None:
        if name not in self.mod_names:
            self.mod_names[name] = ex
        elif ex is not None and ex != self.mod_names[name]:
            alts = self.mod_alts.setdefault(name, [self.mod_names[name]] if self.mod_names[name] else [])
            if ex not in alts:
                alts.append(ex)

    def name_exs(self, name: str) -> List[Ex]:
        """Every expression a Name may denote (more than one for a conditional redefinition)."""
        ex, _ = self.lookup(name)
        if ex is None:
            return []
        if name in self.mod_alts and ex == self.mod_names.get(name) and not self.local_binding(name):
            return list(self.mod_alts[name])
        return [ex]

    def local_binding(self, name: str) -> bool:
        return any(name in sc.ents or name in sc.vars for sc in self.stack[1:])

    def module_scan(self) -> None:
        for node in stmts(self.tree.body):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                self.bind_module(node.name, ("M:" + self.mod, ("." + node.name,)))
            elif isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
                tg = node.targets if isinstance(node, ast.Assign) else [node.target]
                for t in tg:
                    for n in target_names(t):
                        self.bind_module(n, ("M:" + self.mod, ("." + n,)))
            elif isinstance(node, (ast.For, ast.AsyncFor)):
                for n in target_names(node.target):
                    self.bind_module(n, None)
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                for name, ex in self.import_bindings(node):
                    self.bind_module(name, ex)

    def import_bindings(self, node) -> List[Tuple[str, Optional[Ex]]]:
        out: List[Tuple[str, Optional[Ex]]] = []
        if isinstance(node, ast.Import):
            for a in node.names:
                root = a.name.split(".")[0]
                if root in STDLIB:
                    out.append((a.asname or root, None))
                elif a.asname:
                    out.append((a.asname, ("M:" + a.name, ())))
                else:
                    out.append((root, ("M:" + root, ())))
            return out
        base = abs_module(node.level, node.module or "", self.pkg)
        for a in node.names:
            if a.name == "*":
                continue
            name = a.asname or a.name
            if base is None or (not node.level and (node.module or "").split(".")[0] in STDLIB):
                out.append((name, None))
            else:
                out.append((name, ("M:" + base, ("." + a.name,))))
        return out

    # ---------------------------------------------------------------- run
    def run(self) -> None:
        self.module_scan()
        self.stack = [Scope("module", self.mod)]
        self.body(self.tree.body)
        for fqn, ft in self.ftypes.items():
            row = self.defined.get(fqn)
            if ft and row is not None:
                row["ftype"] = ft

    def body(self, nodes) -> None:
        for n in nodes:
            self.stmt(n)

    # ---------------------------------------------------------- statements
    def stmt(self, node) -> None:
        if isinstance(node, FUNC):
            self.function(node)
        elif isinstance(node, ast.ClassDef):
            self.klass(node)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            self.imp(node)
        elif isinstance(node, ast.Assign):
            self.expr(node.value)
            ex = self.ex_of(node.value)
            for t in node.targets:
                self.assign(t, ex, node, node.value)
        elif isinstance(node, ast.AnnAssign):
            self.annotation(node.annotation)
            if node.value is not None:
                self.expr(node.value)
            ex = self.ann_ex(node.annotation) or (self.ex_of(node.value) if node.value is not None else None)
            self.assign(node.target, ex, node, node.value, annotated=True)
        elif isinstance(node, ast.AugAssign):
            self.expr(node.target)
            self.expr(node.value)
        elif isinstance(node, (ast.For, ast.AsyncFor)):
            self.expr(node.iter)
            self.bind_loop(node.target, node.iter)
            self.body(node.body)
            self.body(node.orelse)
        elif isinstance(node, (ast.With, ast.AsyncWith)):
            for item in node.items:
                self.expr(item.context_expr)
                base = self.ex_of(item.context_expr)
                if base is not None:
                    pre = "__a" if isinstance(node, ast.AsyncWith) else "__"
                    for dunder in (pre + "enter__", pre + "exit__"):    # `with x:` calls both
                        self.row("call", (base[0], base[1] + ("." + dunder,)), item.context_expr.lineno)
                if item.optional_vars is not None:
                    ex = (base[0], base[1] + (".__enter__", "()")) if base else None
                    self.assign(item.optional_vars, ex, node, None)
            self.body(node.body)
        elif isinstance(node, ast.Return):
            if node.value is not None:
                self.expr(node.value)
                sc = self.scope()
                sc.returns.append(self.ex_of(node.value) if not _is_none(node.value) else _NONE_RET)
        elif isinstance(node, ast.Try) or type(node).__name__ == "TryStar":
            self.body(node.body)
            for h in node.handlers:
                if h.type is not None:
                    self.expr(h.type)
                if h.name:
                    self.scope().vars[h.name] = None
                self.body(h.body)
            self.body(node.orelse)
            self.body(node.finalbody)
        elif isinstance(node, ast.Global) or isinstance(node, ast.Nonlocal):
            pass
        elif isinstance(node, ast.If):
            self.expr(node.test)
            sc = self.scope()
            narrowed = self.narrow(node.test)
            saved = {n: sc.vars.get(n, _MISSING) for n in narrowed}
            sc.vars.update(narrowed)
            self.body(node.body)
            for n, old in saved.items():
                if old is _MISSING:
                    sc.vars.pop(n, None)
                else:
                    sc.vars[n] = old
            self.body(node.orelse)
        elif isinstance(node, ast.Assert):
            self.expr(node.test)
            self.expr(node.msg)
            self.scope().vars.update(self.narrow(node.test))
        else:
            for _, value in ast.iter_fields(node):
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

    def narrow(self, test) -> Dict[str, Optional[Ex]]:
        """`isinstance(x, Class)` (alone or `and`-ed): x is a Class inside the guarded block."""
        out: Dict[str, Optional[Ex]] = {}
        if isinstance(test, ast.BoolOp) and isinstance(test.op, ast.And):
            for v in test.values:
                out.update(self.narrow(v))
        elif isinstance(test, ast.Call) and isinstance(test.func, ast.Name) and test.func.id == "isinstance" \
                and len(test.args) == 2 and isinstance(test.args[0], ast.Name):
            cls = test.args[1]
            ex = self.ex_of(cls) if isinstance(cls, (ast.Name, ast.Attribute)) else None
            if ex is not None:
                out[test.args[0].id] = (ex[0], ex[1] + ("()",))
        return out

    def bind_loop(self, target, iterable) -> None:
        base = self.ex_of(iterable)
        if isinstance(target, ast.Name) and base is not None:
            self.scope().vars[target.id] = (base[0], base[1] + ("[]",))
        else:
            self.bind_unknown(target)

    def bind_unknown(self, target) -> None:
        for n in target_names(target):
            self.scope().vars[n] = None
        if not target_names(target):
            self.expr(target)

    def assign(self, target, ex: Optional[Ex], node, value, annotated: bool = False) -> None:
        sc = self.scope()
        if isinstance(target, ast.Name):
            name = target.id
            if sc.kind == "module":
                self.module_assign(name, ex, node, value, annotated)
            elif sc.kind == "class":
                self.class_attr(name, ex, node, value, annotated)
                sc.vars[name] = None
            else:
                if value is not None and _is_none(value):
                    sc.vars.setdefault(name, None)
                elif name in sc.vars and sc.vars[name] != ex:
                    sc.vars[name] = None
                else:
                    sc.vars[name] = ex
        elif isinstance(target, (ast.Tuple, ast.List)):
            rhs = getattr(node, "value", None)
            pairs = isinstance(rhs, (ast.Tuple, ast.List)) and len(rhs.elts) == len(target.elts) \
                and not any(isinstance(e, ast.Starred) for e in target.elts + rhs.elts)
            starred = any(isinstance(e, ast.Starred) for e in target.elts)
            for i, e in enumerate(target.elts):
                if pairs:
                    self.assign(e, self.ex_of(rhs.elts[i]), node, rhs.elts[i])
                elif ex is not None and not starred:
                    self.assign(e, (ex[0], ex[1] + ("[%d]" % i,)), node, None)
                else:
                    self.assign(e, None, node, None)
        elif isinstance(target, ast.Attribute):
            self.expr(target.value)
            self.instance_attr(target, ex, node, annotated)
        elif isinstance(target, ast.Starred):
            self.assign(target.value, None, node, None)
        else:
            self.expr(target)

    def module_assign(self, name: str, ex: Optional[Ex], node, value, annotated: bool) -> None:
        final = annotated and "Final" in ast.unparse(node.annotation)
        if name.isupper() or final:
            fqn = self.mod + "." + name
            self.define(fqn, "constant", visibility(name), node,
                        value=literal(value) if value is not None else None)
            self.note_ftype(fqn, ex, value)
        anchor = self.anchor(node.lineno)
        if ex is not None and anchor is not None:
            row = mk_use("%s.%s" % (self.mod, name), anchor, False, "external")
            row.update({"kind": "pybind", "py": ex_str(ex), "name": name, "from_symbol": self.mod})
            self.facts.uses.append(row)

    def class_attr(self, name: str, ex: Optional[Ex], node, value, annotated: bool) -> None:
        owner = self.scope().owner
        fqn = owner + "." + name
        self.define(fqn, "constant" if name.isupper() else "field", visibility(name), node,
                    value=literal(value) if value is not None and name.isupper() else None)
        self.note_ftype(fqn, ex, value)

    def self_binding(self, name: str) -> Optional[str]:
        """The class fqn when `name` is the first parameter of an enclosing method."""
        for sc in reversed(self.stack[1:]):
            if sc.kind == "class":
                return None
            if sc.first == name and sc.cls:
                return sc.cls
            if name in sc.vars or name in sc.ents:
                return None
        return None

    def instance_attr(self, target: ast.Attribute, ex: Optional[Ex], node, annotated: bool) -> None:
        if not isinstance(target.value, ast.Name):
            return
        cls = self.self_binding(target.value.id)
        if not cls or (cls + "#" + target.attr) in self.defined:
            return
        fqn = cls + "." + target.attr
        self.define(fqn, "field", visibility(target.attr), node, line=target.lineno)
        self.note_ftype(fqn, ex, getattr(node, "value", None))

    # ----------------------------------------------------------- imports
    def imp(self, node) -> None:
        sc = self.scope()
        for name, ex in self.import_bindings(node):
            if sc.kind == "func":
                sc.ents[name] = ex
            elif sc.kind == "class":
                sc.vars[name] = None
            if ex is None:
                continue
            if isinstance(node, ast.ImportFrom):
                self.row("import", ex, node.lineno)
            if sc.kind == "module":
                a = self.anchor(node.lineno)
                if a is not None:
                    row = mk_use("%s.%s" % (self.mod, name), a, False, "external")
                    row.update({"kind": "pybind", "py": ex_str(ex), "name": name, "from_symbol": self.mod})
                    self.facts.uses.append(row)

    # --------------------------------------------------------- functions
    def function(self, node) -> None:
        parent = self.scope()
        for d in node.decorator_list:
            self.decorator(d, node)
        if parent.kind == "class":
            fqn, kind = parent.owner + "#" + node.name, "method"
        elif parent.kind == "module":
            fqn, kind = parent.owner + "#" + node.name, "function"
        else:
            fqn, kind = parent.owner + "." + node.name, "function"
        decs = {_leaf(d) for d in node.decorator_list}
        is_prop = bool(decs & PROPERTY_DECORATORS)
        is_static = "staticmethod" in decs
        is_classm = "classmethod" in decs
        sc = Scope("func", fqn, cls=parent.owner if parent.kind == "class" else
                   (parent.cls if parent.kind == "func" else None))
        if parent.kind == "func":
            parent.ents[node.name] = ("D:" + fqn, ())
        # a method's own scope: `self`/`cls`, annotated parameters
        a = node.args
        params = a.posonlyargs + a.args
        for d in a.defaults + [x for x in a.kw_defaults if x is not None]:
            self.expr(d)
        for arg in params + a.kwonlyargs + [x for x in (a.vararg, a.kwarg) if x]:
            if arg.annotation is not None:
                self.annotation(arg.annotation)
        self.stack.append(sc)
        for arg in params + a.kwonlyargs + [x for x in (a.vararg, a.kwarg) if x]:
            sc.vars[arg.arg] = self.ann_ex(arg.annotation) if arg.annotation is not None else None
        if parent.kind == "class" and params and not is_static:
            sc.first = params[0].arg
            sc.vars[sc.first] = ("D:" + parent.owner, () if is_classm or node.name in ("__new__", "__init_subclass__",
                                                                                         "__class_getitem__") else ("()",))
        if node.returns is not None:
            self.annotation(node.returns)
        # nested defs are entities of this scope before their bodies are walked
        for n in stmts(node.body):
            if isinstance(n, FUNC):
                sc.ents[n.name] = ("D:%s.%s" % (fqn, n.name), ())
            elif isinstance(n, ast.ClassDef):
                sc.ents[n.name] = ("D:%s#%s" % (fqn, n.name), ())
        sc.has_yield = _has_yield(node)
        # `@overload` stubs describe the signature; the implementation is the symbol
        fresh = fqn not in self.defined and "overload" not in decs
        row = self.define(fqn, kind, visibility(node.name), node) if fresh else None
        self.body(node.body)
        self.stack.pop()
        if row is not None:
            ret = (self.ann_ex(node.returns) if node.returns is not None else None) or self.inferred_return(sc)
            if ret is not None:
                row["ftype" if is_prop else "ret"] = ex_str(ret)

    def inferred_return(self, sc: Scope) -> Optional[Ex]:
        if sc.has_yield:
            return None
        found = [r for r in sc.returns if r is not _NONE_RET]
        if not found or any(r is None for r in found):
            return None
        return found[0] if all(r == found[0] for r in found) else None

    def decorator(self, d, owner_node) -> None:
        target = d.func if isinstance(d, ast.Call) else d
        ex = self.ex_of(target)
        if ex is not None:
            self.row("call", ex, target.end_lineno or target.lineno)
        if isinstance(target, ast.Attribute):
            self.expr(target.value)
        if isinstance(d, ast.Call):
            for x in d.args:
                self.expr(x)
            for k in d.keywords:
                self.expr(k.value)

    def klass(self, node: ast.ClassDef) -> None:
        parent = self.scope()
        fqn = parent.owner + ("#" if parent.kind == "func" else ".") + node.name
        for d in node.decorator_list:
            self.decorator(d, node)
        self.define(fqn, "class", visibility(node.name), node)
        for b in node.bases:
            self.expr(b)
            while isinstance(b, ast.Subscript):          # `Base[T]`, `Generic[T]`: the class itself
                b = b.value
            ex = self.ex_of(b)
            if ex is not None:
                a = self.anchor(b.lineno)
                if a is not None:
                    row = mk_use(ex_str(ex), a, False, "external")
                    row.update({"kind": "pyextends", "py": ex_str(ex), "from_symbol": fqn})
                    self.facts.uses.append(row)
        for k in node.keywords:
            self.expr(k.value)
        if parent.kind == "func":
            parent.ents[node.name] = ("D:" + fqn, ())
        sc = Scope("class", fqn, cls=fqn)
        self.stack.append(sc)
        self.body(node.body)
        self.stack.pop()

    # -------------------------------------------------------- expressions
    def annotation(self, node) -> None:
        if node is None:
            return
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            try:
                inner = ast.parse(node.value.strip(), mode="eval").body
            except SyntaxError:
                return
            for n in ast.walk(inner):
                if hasattr(n, "lineno"):
                    n.lineno = node.lineno
                    n.end_lineno = node.lineno
            self.annotation(inner)
            return
        self.expr(node)

    def expr(self, node) -> None:
        if node is None:
            return
        if isinstance(node, ast.Call):
            self.call(node)
        elif isinstance(node, ast.Attribute):
            if isinstance(node.ctx, ast.Load):
                self.reference(node)
            self.expr(node.value)
        elif isinstance(node, ast.Name):
            if isinstance(node.ctx, ast.Load):
                self.reference(node)
        elif isinstance(node, ast.Lambda):
            sc = Scope("func", self.scope().owner, cls=self.scope().cls)
            a = node.args
            for d in a.defaults + [x for x in a.kw_defaults if x is not None]:
                self.expr(d)
            for arg in a.posonlyargs + a.args + a.kwonlyargs + [x for x in (a.vararg, a.kwarg) if x]:
                sc.vars[arg.arg] = None
            enclosing = self.scope()
            if enclosing.kind == "class" and a.args and a.args[0].arg == "self":
                # `x = property(lambda self: ...)` in a class body: `self` is the class
                sc.first = "self"
                sc.cls = enclosing.owner
                sc.vars["self"] = ("D:" + enclosing.owner, ("()",))
            self.stack.append(sc)
            self.expr(node.body)
            self.stack.pop()
        elif isinstance(node, (ast.ListComp, ast.SetComp, ast.GeneratorExp, ast.DictComp)):
            self.expr(node.generators[0].iter)
            sc = Scope("func", self.scope().owner, cls=self.scope().cls)
            self.stack.append(sc)
            for i, g in enumerate(node.generators):
                if i:
                    self.expr(g.iter)
                base = self.ex_of(g.iter) if isinstance(g.target, ast.Name) else None
                for n in target_names(g.target):
                    sc.vars[n] = (base[0], base[1] + ("[]",)) if base is not None else None
                for c in g.ifs:
                    self.expr(c)
            for part in ((node.key, node.value) if isinstance(node, ast.DictComp) else (node.elt,)):
                self.expr(part)
            self.stack.pop()
        elif isinstance(node, ast.NamedExpr):
            self.expr(node.value)
            ex = self.ex_of(node.value)
            if isinstance(node.target, ast.Name):
                self.scope().vars[node.target.id] = ex
        elif isinstance(node, (ast.Yield, ast.YieldFrom)):
            self.scope().has_yield = True
            self.expr(getattr(node, "value", None))
        elif isinstance(node, ast.Constant):
            return
        else:
            for child in ast.iter_child_nodes(node):
                if isinstance(child, ast.AST):
                    self.expr(child)

    def reference(self, node) -> None:
        """A Name or Attribute read that is not called. A Name is a reference only
        when it is an entity (a def, class or import), not a variable that merely has a type."""
        if isinstance(node, ast.Name):
            ex, entity = self.lookup(node.id)
            if ex is not None and entity:
                for alt in self.name_exs(node.id):
                    self.row("ref", alt, node.lineno)
            return
        ex = self.ex_of(node)
        if ex is None:
            return
        self.row("ref", ex, node.end_lineno or node.lineno)

    def call(self, node: ast.Call) -> None:
        f = node.func
        if isinstance(f, (ast.Name, ast.Attribute)):
            ex = self.ex_of(f)
            if ex is not None:
                for alt in (self.name_exs(f.id) if isinstance(f, ast.Name) else [ex]):
                    self.row("call", alt, f.end_lineno or node.lineno)
            if isinstance(f, ast.Attribute):
                self.expr(f.value)
        else:
            self.expr(f)
        for a in node.args:
            self.expr(a)
        for k in node.keywords:
            self.expr(k.value)


_NONE_RET: Ex = ("None", ())
_MISSING: Ex = ("missing", ())


def _is_none(node) -> bool:
    return isinstance(node, ast.Constant) and node.value is None


def _leaf(d) -> str:
    d = d.func if isinstance(d, ast.Call) else d
    return d.id if isinstance(d, ast.Name) else d.attr if isinstance(d, ast.Attribute) else ""


def _has_yield(fn) -> bool:
    stack = list(fn.body)
    while stack:
        n = stack.pop()
        if isinstance(n, (ast.Yield, ast.YieldFrom)):
            return True
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)):
            continue
        stack.extend(ast.iter_child_nodes(n))
    return False


def analyse(ctx: ExtractContext, facts: FileFacts, tree: ast.Module, mod: str, pkg: str) -> None:
    Flow(ctx, facts, tree, mod, pkg).run()
