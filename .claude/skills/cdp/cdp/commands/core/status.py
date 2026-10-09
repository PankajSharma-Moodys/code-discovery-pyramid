"""`cdp status`."""

from __future__ import annotations

import json

from .._common import Spec, locked, paths_from_args
from ... import supervisor as supervisor_mod
from ...status import status
from typing import Dict


SPEC = Spec(
    group='core',
    usage='status',
    what="Waves, per-node statuses, coverage, freshness, and the current run's task table.",
    next='tip (stale/unreviewed scopes exist): `run --stale-only`. next (incomplete tasks): `run --resume --run-id <id>`.',
)


def register(add) -> None:
    st = add("status", "waves, node statuses and coverage")
    st.add_argument("--json", action="store_true")
    st.set_defaults(func=cmd_status)


@locked(shared=True)
def cmd_status(args) -> int:
    paths = paths_from_args(args)
    result = status(paths)
    if getattr(args, "json", False):
        print(json.dumps(result, sort_keys=True))
    else:
        print_status(result)
    return 0


def print_status(result: Dict) -> None:
    print("run       %s @ %s" % (result["run_id"], (result["head"] or "?")[:12]))
    cov = result["coverage"]
    print("coverage  %.1f%% (%d/%d tracked files)"
          % (100 * cov["fraction"], cov["files_complete"], cov["files_total"]))
    fresh = result["freshness"]
    if fresh is not None:
        print("freshness %d live, %d stale, %d anchored-but-unreviewed, %d unknown-churn"
              % (fresh["live"], fresh["stale"], fresh["unreviewed"], fresh["unknown_churn"]))
        if fresh["stale"] + fresh["unreviewed"] > 0:
            print("tip       cdp run --stale-only to re-dispatch just the stale/anchored-but-unreviewed scope(s)")
    for wave in result["waves"]:
        print("wave %-2d L%s  %d/%d complete  %d files, %d loc"
              % (wave["wave"], wave["level"], wave["done"], wave["total"],
                 wave["file_count"], wave["loc"]))
        for n in wave["nodes"]:
            print("    %-9s %s" % (n["status"], n["node"]))

    if result["tasks"]:
        print("\ntasks     run %s" % result["run_id"])
        incomplete = False
        for row in result["tasks"]:
            print("    %-14s %-40s attempts %d%s"
                  % (row["state"], row["node"], row["attempts"],
                     "  %s" % row["last_error"] if row["last_error"] else ""))
            if row["state"] not in (supervisor_mod.FOLDED,):
                incomplete = True
        if incomplete:
            print("next      cdp run --resume --run-id %s to continue the incomplete task(s) above"
                  % result["run_id"])
