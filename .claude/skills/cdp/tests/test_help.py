"""`cdp help` — `PHASE/phase_1_plan.md` M1.4.

The one assertion that carries the milestone is
`test_every_subparser_appears_in_json`. The stated requirement is that the
command list be *derived from the argparse tree, not a parallel hand-maintained
table*, and the only way to hold that line over time is a test that fails when a
new subcommand is added and the help does not know about it.
"""

from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stdout

from helpers import SKILL_ROOT  # noqa: F401  (sets sys.path)

from cdp import helpdoc
from cdp.cli import _parser, main
from cdp.schema import Validator, help_schema_path


def surface():
    return helpdoc.describe(_parser())


def run(*argv) -> str:
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = main(list(argv))
    assert code == 0, argv
    return buf.getvalue()


class DerivedFromTheParserTest(unittest.TestCase):
    def test_every_subparser_appears_in_json(self) -> None:
        import argparse

        expected = set()
        for action in _parser()._actions:
            if isinstance(action, argparse._SubParsersAction):
                expected |= set(action.choices)
        self.assertEqual({c["name"] for c in surface()["commands"]}, expected)

    def test_a_new_command_needs_no_edit_here(self) -> None:
        """The property, stated directly: describe() reads the parser it is
        handed, so a subcommand that exists is documented."""
        import argparse

        parser = argparse.ArgumentParser(prog="cdp")
        sub = parser.add_subparsers()
        sub.add_parser("invented", help="a command that exists nowhere else")
        names = [c["name"] for c in helpdoc.describe(parser)["commands"]]
        self.assertEqual(names, ["invented"])

    def test_flags_come_from_the_parser_too(self) -> None:
        query = [c for c in surface()["commands"] if c["name"] == "query"][0]
        flags = {f for option in query["options"] for f in option["flags"]}
        self.assertIn("--budget", flags)
        self.assertIn("--json", flags)

    def test_suppressed_defaults_are_not_serialised(self) -> None:
        """`argparse.SUPPRESS` is a sentinel, not data; emitting it would
        describe a default of "==SUPPRESS==" that no command has."""
        for command in surface()["commands"]:
            for option in command["options"]:
                self.assertNotEqual(option.get("default"), "==SUPPRESS==",
                                    "%s %s" % (command["name"], option["name"]))


class JsonSurfaceTest(unittest.TestCase):
    def test_validates_against_its_committed_schema(self) -> None:
        validator = Validator.load(help_schema_path(SKILL_ROOT))
        self.assertEqual(validator.validate(surface()), [])

    def test_cli_emits_valid_json(self) -> None:
        data = json.loads(run("help", "--json"))
        self.assertEqual(data["schema_version"], helpdoc.HELP_SCHEMA_VERSION)
        self.assertTrue(data["commands"])
        self.assertTrue(data["workflows"])

    def test_the_schema_check_can_fail(self) -> None:
        validator = Validator.load(help_schema_path(SKILL_ROOT))
        broken = surface()
        broken["commands"][0].pop("usage")
        self.assertTrue(validator.validate(broken))


class RenderedHelpTest(unittest.TestCase):
    def test_overview_renders(self) -> None:
        out = run("help")
        self.assertIn("THE ORDER THINGS HAPPEN IN", out)
        self.assertIn("query trace", out)
        # Guidance, not flags: the honest-reading section is the point.
        self.assertIn("elided: 0", out)

    def test_workflows_render_all_four_recipes(self) -> None:
        out = run("help", "workflows")
        for name in ("onboard", "refresh", "investigate", "review"):
            self.assertIn(name, out)
        self.assertIn("$ cdp scan", out)

    def test_command_topic_renders_its_real_flags(self) -> None:
        self.assertIn("--budget", run("help", "query"))

    def test_unknown_topic_says_what_is_available(self) -> None:
        out = run("help", "nonsense")
        self.assertIn("No help topic", out)
        self.assertIn("workflows", out)


if __name__ == "__main__":
    unittest.main()
