"""Parser construction: the command registry assembled into one argparse tree.

Split from `cli.py` so consumers that only need the command surface
(`helpdoc`, `agent_adapter`) don't import the dispatcher.
"""

from __future__ import annotations

import argparse

from .commands import register_all
from .guide import apply_flag_help
from .util import CDP_VERSION


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
    apply_flag_help(p)
    return p
