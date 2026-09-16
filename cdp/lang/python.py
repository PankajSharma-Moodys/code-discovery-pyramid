"""Python extractor.

Uses `ast`, so declarations and imports are exact rather than regex-approximate.
Anchors are still built from the raw lines, because a claim has to cite text a
human can find, not an AST node.

Where the Java extractor reads a `package` statement, this one derives the
module path from the file path — which looks like the path-inference mistake
§6.3 forbids, but is not: in Python the import path *is* the file path, and
`__init__.py` presence is the only thing that decides package boundaries. The
rule "read the namespace from wherever the language actually declares it" is the
same rule; the languages just declare it in different places.
"""

from __future__ import annotations

import ast
import re
import warnings
from typing import Dict, List, Optional, Tuple

from .base import (
    ExtractContext,
    Extractor,
    FileFacts,
    anchor_at,
    channel_for_import,
    count_loc,
    mk_define,
    mk_edge,
    mk_use,
)

ROUTE_DECORATORS = frozenset(["route", "get", "post", "put", "delete", "patch", "head", "options"])
ENV_RE = re.compile(r"""(?:os\.environ(?:\.get)?\s*[\[(]\s*|getenv\s*\(\s*)['"]([A-Za-z_][\w]*)['"]""")
SQL_RE = re.compile(r"\b(INSERT\s+INTO|UPDATE|DELETE\s+FROM|SELECT\b[\s\S]{0,200}?\bFROM)\s+([`\"'\[]?[\w.]+)", re.I)


class PythonExtractor(Extractor):
    language = "python"
    extensions = (".py", ".pyi")

    def extract(self, ctx: ExtractContext) -> FileFacts:
        facts = FileFacts(path=ctx.path, language=self.language, loc=count_loc(ctx.lines))
        facts.package = _module_path(ctx.path)
        primary = facts.package or ctx.path
        facts.primary = primary

        try:
            # A target file's own string literals (e.g. a regex written as
            # "\S" instead of r"\S") make CPython's parser emit a
            # `SyntaxWarning` — real about that file, irrelevant to whether
            # extraction succeeds, and otherwise noise on every scan's stderr.
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", SyntaxWarning)
                tree = ast.parse("\n".join(ctx.lines))
        except SyntaxError as exc:
            facts.notes.append("parse_error:line=%s" % getattr(exc, "lineno", "?"))
            return facts

        _imports(ctx, facts, tree, primary)
        _definitions(ctx, facts, tree, primary)
        _side_effects(ctx, facts, primary)
        _entrypoint(ctx, facts, primary)
        facts.signals = sorted(set(facts.signals))
        return facts


def _module_path(path: str) -> str:
    stem = path[: -len(".py")] if path.endswith(".py") else path
    if stem.endswith("/__init__"):
        stem = stem[: -len("/__init__")]
    return stem.replace("/", ".")


def _imports(ctx: ExtractContext, facts: FileFacts, tree: ast.AST, primary: str) -> None:
    seen_channels = set()
    for node in ast.walk(tree):
        names: List[str] = []
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level:  # relative import: keep it relative and honest
                base = "." * node.level + base
            names = [base] if base else []
        else:
            continue
        anchor = anchor_at(ctx, node.lineno - 1)
        if anchor is None:
            continue
        for name in names:
            facts.imports.append({"fqn": name, "line": node.lineno, "static": False, "anchor": anchor})
            facts.uses.append(mk_use(name, anchor, via_import=True, resolved="external"))
            channel = channel_for_import(name)
            if channel and channel not in seen_channels:
                seen_channels.add(channel)
                facts.io_edges.append(mk_edge(primary, "library:" + name.split(".")[0], channel, anchor))


def _definitions(ctx: ExtractContext, facts: FileFacts, tree: ast.AST, primary: str) -> None:
    def visibility(name: str) -> str:
        if name.startswith("__") and not name.endswith("__"):
            return "private"
        return "internal" if name.startswith("_") else "public"

    def walk(node: ast.AST, prefix: str) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.ClassDef):
                fqn = prefix + "." + child.name
                anchor = anchor_at(ctx, child.lineno - 1)
                if anchor:
                    facts.defines.append(mk_define(fqn, "class", visibility(child.name), anchor))
                    _decorators(ctx, facts, child, fqn)
                    if any(_dotted(b).endswith(("Model", "Base", "Document")) for b in child.bases):
                        facts.signals.append("entity")
                        facts.io_edges.append(mk_edge(fqn, "entity:" + fqn, "persist", anchor))
                walk(child, fqn)
            elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                fqn = prefix + "#" + child.name
                anchor = anchor_at(ctx, child.lineno - 1)
                if anchor:
                    facts.defines.append(mk_define(fqn, "method", visibility(child.name), anchor))
                    _decorators(ctx, facts, child, fqn)
            elif isinstance(child, ast.Assign) and isinstance(node, ast.Module):
                for target in child.targets:
                    if isinstance(target, ast.Name) and target.id.isupper():
                        anchor = anchor_at(ctx, child.lineno - 1)
                        if anchor:
                            value = _literal(child.value)
                            facts.defines.append(
                                mk_define(prefix + "." + target.id, "constant",
                                          visibility(target.id), anchor, value=value)
                            )

    walk(tree, primary)


def _decorators(ctx: ExtractContext, facts: FileFacts, node: ast.AST, owner: str) -> None:
    for dec in getattr(node, "decorator_list", []):
        call = dec if isinstance(dec, ast.Call) else None
        target_node = call.func if call else dec
        dotted = _dotted(target_node)
        leaf = dotted.rsplit(".", 1)[-1]
        anchor = anchor_at(ctx, getattr(dec, "lineno", getattr(node, "lineno", 1)) - 1)
        if anchor is None:
            continue
        if leaf in ROUTE_DECORATORS and (dotted.count(".") >= 1 or leaf == "route"):
            path = _literal(call.args[0]) if call and call.args else ""
            verb = leaf.upper() if leaf != "route" else "ANY"
            facts.signals.append("http_resource")
            facts.io_edges.append(
                mk_edge(owner, "route:%s %s" % (verb, path or "/"), "http_in", anchor)
            )
        elif leaf in ("task", "shared_task", "periodic_task", "scheduled_job"):
            facts.signals.append("scheduled")
            facts.io_edges.append(mk_edge(owner, "scheduler", "schedule", anchor))


def _dotted(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return _dotted(node.value) + "." + node.attr
    if isinstance(node, ast.Call):
        return _dotted(node.func)
    return ""


def _literal(node: ast.AST) -> Optional[str]:
    if isinstance(node, ast.Constant) and isinstance(node.value, (str, int, float, bool)):
        return str(node.value)
    return None


def _side_effects(ctx: ExtractContext, facts: FileFacts, primary: str) -> None:
    seen: set = set()
    for idx, line in enumerate(ctx.lines):
        for key in ENV_RE.findall(line):
            if ("config", key) in seen:
                continue
            seen.add(("config", key))
            anchor = anchor_at(ctx, idx)
            if anchor:
                facts.io_edges.append(mk_edge(primary, "config:" + key, "config_read", anchor))
        m = SQL_RE.search(line)
        if m:
            table = m.group(2).strip("`\"'[]")
            channel = "read" if m.group(1).upper().startswith("SELECT") else "persist"
            if ("sql", table, channel) in seen:
                continue
            seen.add(("sql", table, channel))
            anchor = anchor_at(ctx, idx)
            if anchor:
                facts.io_edges.append(mk_edge(primary, "table:" + table, channel, anchor))


def _entrypoint(ctx: ExtractContext, facts: FileFacts, primary: str) -> None:
    for idx, line in enumerate(ctx.lines):
        if line.strip().startswith("if __name__") and "__main__" in line:
            anchor = anchor_at(ctx, idx)
            if anchor:
                facts.signals.append("main")
                facts.io_edges.append(
                    mk_edge(primary, "process:" + primary, "process_boundary", anchor)
                )
            return
