"""`cdp link`: the group and its subcommands."""

from __future__ import annotations

from . import scan as link_scan
from . import query as link_query
from . import prompts as link_prompts
from . import collect as link_collect
from . import run as link_run
from . import refresh as link_refresh
from ...util import CdpError


SPECS = (link_scan.SPEC, link_prompts.SPEC, link_collect.SPEC, link_run.SPEC, link_refresh.SPEC, link_query.SPEC)


def _no_subcommand(args) -> int:
    raise CdpError("link needs a subcommand: scan, query, refresh, prompts, collect or run (see `help link`)")


def register(add) -> None:
    lk = add("link", "who calls this service / what publishes to this topic, "
                      "across modules and across snapshots (Phase 8, M8.1-M8.2)")
    lk.set_defaults(func=_no_subcommand)
    lk_sub = lk.add_subparsers(dest="link_command")
    link_scan.register(lk_sub)
    link_query.register(lk_sub)
    link_prompts.register(lk_sub)
    link_collect.register(lk_sub)
    link_run.register(lk_sub)
    link_refresh.register(lk_sub)
