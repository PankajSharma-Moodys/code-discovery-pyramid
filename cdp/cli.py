"""Command line interface: build the parser from the command registry, dispatch.

Every command lives in `cdp/commands/<group>/<name>.py` (its flags, its output)
and calls an engine module for the logic. See `cdp/commands/__init__.py` for the
registry.
"""

from __future__ import annotations

import sys
from typing import Optional, Sequence

from .parser import build_parser
from .util import CdpError


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
