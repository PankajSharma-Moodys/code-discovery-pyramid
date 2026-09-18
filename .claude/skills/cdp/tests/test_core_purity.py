"""Enforces "core imports no framework, ever" (`RESEARCH_GRAPHIFY.md` §7.11,
`pyproject.toml`'s `dependencies = []`).

Before the interface adapters (`mcp_server/`, `litellm_adapter/`,
`agent_adapter/`) existed, this was true only by discipline: nothing stopped
`cdp/` from importing `mcp`/`litellm`/`langgraph` directly the day someone
found it convenient mid-feature. This test makes it structural: walk every
`cdp/**/*.py`, parse it (never execute it — an import with a side effect must
not run just to be checked for), and fail naming every forbidden import's
`file:line`, not just the first.
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

from helpers import SKILL_ROOT  # noqa: F401  (sets sys.path)

CDP_ROOT = SKILL_ROOT / "cdp"

#: Top-level module names no `cdp/` file may import. Matched on the first
#: dotted segment, so `google.adk` is caught by `google` and `langchain_x` by
#: its own prefix check below.
FORBIDDEN_EXACT = {"mcp", "litellm", "langgraph", "fastmcp", "google"}
FORBIDDEN_PREFIXES = ("langchain",)


def _forbidden(module_name: str) -> bool:
    top = module_name.split(".", 1)[0]
    return top in FORBIDDEN_EXACT or any(top.startswith(p) for p in FORBIDDEN_PREFIXES)


def _violations(path: Path) -> list:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if _forbidden(alias.name):
                    found.append("%s:%d imports %s" % (path, node.lineno, alias.name))
        elif isinstance(node, ast.ImportFrom) and node.module:
            if _forbidden(node.module):
                found.append("%s:%d imports from %s" % (path, node.lineno, node.module))
    return found


class CorePurityTest(unittest.TestCase):
    def test_core_imports_no_agent_framework(self) -> None:
        violations = []
        for path in sorted(CDP_ROOT.rglob("*.py")):
            violations.extend(_violations(path))
        if violations:
            self.fail(
                "cdp/ must never import an agent framework -- adapters live "
                "outside core (mcp_server/, litellm_adapter/, agent_adapter/):\n  "
                + "\n  ".join(violations)
            )


if __name__ == "__main__":
    unittest.main()
