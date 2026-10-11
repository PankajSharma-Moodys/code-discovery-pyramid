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
import warnings
from typing import List

from .base import (
    ExtractContext,
    Extractor,
    FileFacts,
    anchor_at,
    channel_for_import,
    count_loc,
    mk_edge,
    mk_use,
)
from . import python_flow, python_io
from .pyhttp import emit_http_clients
from .python_flow import abs_module


class PythonExtractor(Extractor):
    language = "python"
    extensions = (".py", ".pyi")

    def extract(self, ctx: ExtractContext) -> FileFacts:
        facts = FileFacts(path=ctx.path, language=self.language, loc=count_loc(ctx.lines))
        facts.package = _module_path(ctx.path)
        primary = facts.package or ctx.path
        facts.primary = primary
        pkg = primary if ctx.path.endswith("__init__.py") else primary.rsplit(".", 1)[0] if "." in primary else ""

        try:
            # A target file's own string literals (e.g. a regex written as
            # "\S" instead of r"\S") make CPython's parser emit a
            # `SyntaxWarning` -- real about that file, irrelevant to whether
            # extraction succeeds, and otherwise noise on every scan's stderr.
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", SyntaxWarning)
                tree = ast.parse("\n".join(ctx.lines))
        except SyntaxError as exc:
            facts.notes.append("parse_error:line=%s" % getattr(exc, "lineno", "?"))
            return facts

        _imports(ctx, facts, tree, primary, pkg)
        python_flow.analyse(ctx, facts, tree, primary, pkg)
        python_io.analyse(ctx, facts, tree, primary, pkg)
        emit_http_clients(ctx, facts, tree, primary)
        _entrypoint(ctx, facts, primary)
        facts.signals = sorted(set(facts.signals))
        return facts


def _module_path(path: str) -> str:
    stem = path[: -len(".py")] if path.endswith(".py") else path
    if stem.endswith("/__init__"):
        stem = stem[: -len("/__init__")]
    return stem.replace("/", ".")


def _imports(ctx: ExtractContext, facts: FileFacts, tree: ast.AST, primary: str, pkg: str) -> None:
    seen_channels = set()
    for node in ast.walk(tree):
        names: List[str] = []
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            # A relative import is resolved against this file's own package; one that
            # climbs above the repository root stays relative and honest.
            base = abs_module(node.level, node.module or "", pkg)
            if base is None:
                base = "." * node.level + (node.module or "")
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
