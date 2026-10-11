"""Slim a Python source for a target install: no comments, no docstrings.

An install into another repository copies the runtime only (`install.TARGET_MEMBERS`), and
docstrings + comments are about a fifth of those bytes. Nothing at run time reads them, with
one exception: a module that prints its own `__doc__` (`hook.py --explain`) keeps its module
docstring. Statements are untouched, so behaviour is identical; line numbers are not, and
tracebacks from a target copy point into slimmed source (the repository's own vendored copy,
`install --self`, is never slimmed: it is held byte-identical to the source).
"""

from __future__ import annotations

import ast
import io
import tokenize
from typing import List, Tuple


def _docstrings(tree: ast.Module, keep_module: bool) -> List[Tuple[ast.Expr, bool]]:
    """`(docstring statement, it is the only statement of its body)` for every docstring to drop."""
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        if isinstance(node, ast.Module) and keep_module:
            continue
        first = node.body[0] if node.body else None
        if (isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)):
            found.append((first, len(node.body) == 1))
    return found


def slim_python(source: str) -> str:
    """`source` without docstrings (except a module docstring something reads as `__doc__`) and comments."""
    lines = source.splitlines(keepends=True)
    tree = ast.parse(source)
    drops = []
    for stmt, alone in _docstrings(tree, keep_module="__doc__" in source):
        if lines[stmt.lineno - 1][:stmt.col_offset].strip():  # shares its line with a `def x():`: leave it
            continue
        drops.append((stmt.lineno, stmt.end_lineno, stmt.col_offset, alone))
    for start, end, col, alone in sorted(drops, reverse=True):
        lines[start - 1:end] = [" " * col + "pass\n"] if alone else []
    text = "".join(lines)

    cuts = []  # (row, col) of every comment, in reading order
    for tok in tokenize.generate_tokens(io.StringIO(text).readline):
        if tok.type == tokenize.COMMENT and not (tok.start[0] == 1 and tok.string.startswith("#!")):
            cuts.append(tok.start)
    rows = text.splitlines(keepends=True)
    for row, col in reversed(cuts):
        before = rows[row - 1][:col]
        rows[row - 1:row] = [before.rstrip() + "\n"] if before.strip() else []
    out = "".join(rows)
    ast.parse(out)  # a slimmed file that no longer parses is a bug here, not in the target
    return out
