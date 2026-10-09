"""Command line interface: build the parser from the command registry, dispatch.

Every command lives in `cdp/commands/<group>/<name>.py` (its flags, its output)
and calls an engine module for the logic. See `cdp/commands/__init__.py` for the
registry.
"""

from __future__ import annotations

import argparse
import sys
from typing import Optional, Sequence

from .commands import register_all
from .util import CDP_VERSION, CdpError


def build_parser() -> argparse.ArgumentParser:
    # The location flags are accepted on both sides of the subcommand. Typing
    # `cdp scan --repo X` is the natural order and `cdp --repo X scan` is the
    # one argparse makes natural; refusing either is a papercut on every call.
    # SUPPRESS keeps the subparser copy from overwriting a value already given
    # to the top-level parser with its own default.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--repo", default=argparse.SUPPRESS,
                        help="repository to analyse (default: cwd)")
    common.add_argument("--state-dir", default=argparse.SUPPRESS,
                        help="alias for CDP_HOME: the one machine-level store "
                             "(default: ~/.cdp). Never inside --repo.")

    p = argparse.ArgumentParser(prog="cdp", parents=[common],
                                description="Code Discovery Pyramid v%s" % CDP_VERSION)
    sub = p.add_subparsers(dest="command")

    def add(name: str, help_text: str) -> argparse.ArgumentParser:
        return sub.add_parser(name, parents=[common], help=help_text)

    register_all(add)
    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 1
    args.parser = parser
    try:
        return args.func(args) or 0
    except CdpError as exc:
        print("cdp: %s" % exc, file=sys.stderr)
        return 2
    except BrokenPipeError:
        return 0


if __name__ == "__main__":  # `python3 -m cdp.cli ...`
    sys.exit(main())
