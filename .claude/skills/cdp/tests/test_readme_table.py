"""The README command table is generated from each command's `SPEC`."""

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _gen():
    spec = importlib.util.spec_from_file_location("gen_readme", ROOT / "scripts" / "gen_readme.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class ReadmeTableTest(unittest.TestCase):
    def test_readme_matches_specs(self) -> None:
        gen = _gen()
        text = (ROOT / "README.md").read_text()
        self.assertEqual(gen.apply(text), text, "run `python3 scripts/gen_readme.py`")

    def test_every_command_has_a_row(self) -> None:
        from cdp.cli import build_parser
        from cdp.commands import specs

        usages = {s.usage.split()[0] for _t, group in specs() for s in group}
        parser_cmds = set(build_parser()._subparsers._group_actions[0].choices)
        self.assertEqual(usages, parser_cmds)


if __name__ == "__main__":
    unittest.main()
