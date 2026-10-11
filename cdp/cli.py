"""Command line interface: build the parser from the command registry, dispatch.

Every command lives in `cdp/commands/<group>/<name>.py` (its flags, its output)
and calls an engine module for the logic. See `cdp/commands/__init__.py` for the
registry.
"""

from __future__ import annotations

import json
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
    except KeyboardInterrupt:
        print("cdp: interrupted", file=sys.stderr)
        return 130
    except Exception as exc:  # noqa: BLE001 -- only the user-facing kinds below are caught
        if not _is_user_error(exc):
            raise
        # A user-facing environment problem (missing, unreadable or malformed input; a
        # file where a directory was wanted): one line naming it, never a traceback.
        print("cdp: %s" % _describe(exc), file=sys.stderr)
        return 2


def _is_user_error(exc: BaseException) -> bool:
    # sqlite3 is imported by exactly one module (the store backend), so its errors are
    # recognised by class module instead of an import here.
    return isinstance(exc, (OSError, json.JSONDecodeError, UnicodeError)) or type(exc).__module__ == "sqlite3"


def _describe(exc: BaseException) -> str:
    if isinstance(exc, json.JSONDecodeError):
        return "not valid JSON (line %d, column %d): %s" % (exc.lineno, exc.colno, exc.msg)
    if type(exc).__module__ == "sqlite3":
        return "not a usable CDP store: %s" % exc
    if isinstance(exc, OSError) and exc.filename is not None:
        return "%s: %s" % (exc.filename, exc.strerror or exc)
    return "%s: %s" % (type(exc).__name__, exc)


if __name__ == "__main__":  # `python3 -m cdp.cli ...`
    sys.exit(main())
