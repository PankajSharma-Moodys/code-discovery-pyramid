"""`cdp refresh`."""

from __future__ import annotations

from .._common import Spec, locked, paths_from_args
from ... import refresh as refresh_mod
from ...verify import STRICT


SPEC = Spec(
    group='leaf',
    usage='refresh',
    what='Re-verifies every live claim against HEAD, zero model calls, incremental extraction.',
    next='next: `query stats`. Flags: `--quiet`. No-ops cleanly when HEAD is unchanged.',
)


def register(add) -> None:
    r = add("refresh", "re-verify every live claim against HEAD, zero model calls")
    r.add_argument("--mode", choices=["strict", "lenient"], default=STRICT)
    r.add_argument("--quiet", action="store_true")
    r.set_defaults(func=cmd_refresh)


@locked(shared=False)
def cmd_refresh(args) -> int:
    say = (lambda *a: None) if args.quiet else (lambda *a: print(*a))
    return refresh_mod.refresh_repo(
        paths_from_args(args), mode=args.mode, exclude=getattr(args, "exclude", None), say=say,
    )
