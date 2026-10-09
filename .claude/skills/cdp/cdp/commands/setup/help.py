"""`cdp help`."""

from __future__ import annotations

from .._common import Spec

from ... import helpdoc
from ...schema import Validator
from ...util import CdpError, SKILL_ROOT
from pathlib import Path


SPEC = Spec(
    group='setup',
    usage='help [<command> \\| workflows] [--json]',
    what='When to use what, in what order, and what comes next — derived from the live parser, never hand-maintained.',
    next='—',
)


def register(add) -> None:
    h = add("help", "when to use what, in what order, and what comes next")
    h.add_argument("topic", nargs="?",
                   help="'workflows' for the named recipes, or a command name")
    h.add_argument("--json", action="store_true",
                   help="emit the machine-readable command surface "
                        "(schema/help-1.0.0.json)")
    h.set_defaults(func=cmd_help)


def cmd_help(args) -> int:
    """Guidance, derived from the live parser.

    `describe(args.parser)` rather than a table: the command list cannot drift
    from the CLI, because it *is* the CLI. A hand-maintained help text that
    disagrees with the tool is a confident wrong answer about the tool itself.
    """
    surface = helpdoc.describe(args.parser)
    if args.json:
        errors = Validator.load(schema_path_help()).validate(surface)
        if errors:
            raise CdpError(
                "`help --json` does not satisfy its own committed schema:\n  "
                + "\n  ".join(errors[:10])
            )
        print(__import__("json").dumps(surface, indent=2, sort_keys=True,
                                       ensure_ascii=False))
        return 0
    print(helpdoc.render(surface, args.topic))
    return 0


def schema_path_help() -> Path:
    from ...schema import help_schema_path

    return help_schema_path(SKILL_ROOT)
