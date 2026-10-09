"""The import rules that keep `cdp/commands/` thin.

* A command file imports engines and `commands/_common` -- never another
  command (the registry and the `link` group import their own members).
* An engine never imports `commands/`.
"""

import ast
import unittest
from pathlib import Path

CDP = Path(__file__).resolve().parent.parent / "cdp"
COMMANDS = CDP / "commands"
REGISTRY = {COMMANDS / "__init__.py", COMMANDS / "link" / "__init__.py"}


def _targets(path: Path):
    """(line, module parts relative to `cdp`, imported names) for every import."""
    pkg = path.relative_to(CDP).with_suffix("").parts[:-1]
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name.split(".")[0] == "cdp":
                    yield node.lineno, a.name.split(".")[1:], []
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = list(pkg[: len(pkg) - (node.level - 1)]) if node.level > 1 else list(pkg)
                mod = base + (node.module.split(".") if node.module else [])
            elif node.module and node.module.split(".")[0] == "cdp":
                mod = node.module.split(".")[1:]
            else:
                continue
            names = [a.name for a in node.names]
            yield node.lineno, mod, names


class LayeringTest(unittest.TestCase):
    def test_commands_import_only_engines_and_common(self) -> None:
        bad = []
        for path in sorted(COMMANDS.rglob("*.py")):
            if path in REGISTRY:
                continue
            for line, mod, names in _targets(path):
                if mod[:1] == ["commands"]:
                    ok = mod[1:2] == ["_common"] or (mod == ["commands"] and names == ["_common"])
                    if not ok:
                        bad.append("%s:%d imports %s" % (path.relative_to(CDP), line, ".".join(mod + names)))
        self.assertEqual(bad, [], "commands may import only engines and commands/_common")

    def test_engines_never_import_commands(self) -> None:
        bad = []
        for path in sorted(CDP.rglob("*.py")):
            if COMMANDS in path.parents or path.name in ("cli.py", "__main__.py"):
                continue
            for line, mod, names in _targets(path):
                if mod[:1] == ["commands"]:
                    bad.append("%s:%d imports %s" % (path.relative_to(CDP), line, ".".join(mod + names)))
        self.assertEqual(bad, [], "engines must not import cdp.commands")

    def test_no_module_over_1000_lines(self) -> None:
        big = {str(p.relative_to(CDP)): n for p in CDP.rglob("*.py")
               if (n := len(p.read_text().splitlines())) > 1100}
        self.assertEqual(big, {}, "split these modules")


if __name__ == "__main__":
    unittest.main()
