"""`cdp run`."""

from __future__ import annotations

from .._common import Spec, locked, outcome_code, paths_from_args, require_lesson_cut
from ... import supervisor as supervisor_mod
from ...session import build_runner
from ... import trajectory as trajectory_mod
from ...util import CdpError, non_negative_int, positive_float, positive_int
from ...verify import STRICT


SPEC = Spec(
    group='leaf',
    usage='run --wave N \\| --wave-all \\| --stale-only \\| --scope X',
    what='Dispatch → collect → adjudicate → fold, wave by wave, supervised (leases, retries, resume).',
    next='next: `query stats`, or `fold --check`. tip (on partial failure): `run --resume`. Flags: `--runner-cmd`, `--parallel N` (scopes of a wave at once), `--max-attempts`, `--resume`, `--lessons N`/`--no-lessons`.',
)


def register(add) -> None:
    rn = add("run", "dispatch -> collect -> adjudicate -> fold, wave by wave")
    rn_target = rn.add_mutually_exclusive_group(required=True)
    rn_target.add_argument("--wave", type=non_negative_int, help="dispatch only this wave")
    rn_target.add_argument("--wave-all", action="store_true", help="every wave, in order")
    rn_target.add_argument("--stale-only", action="store_true",
                            help="only scopes owning a stale/anchored-but-unreviewed "
                                 "claim (the M3.1 freshness bucket), across every wave")
    rn_target.add_argument("--scope", help="one node, by name (e.g. root/gateway)")
    rn.add_argument("--runner-cmd", default=None, metavar="CMD",
                     help="shell command for SubprocessRunner, given prompt and patch "
                          "paths as its last two arguments (default: FileRunner -- "
                          "wait for a human/external process to drop the patch file)")
    rn.add_argument("--timeout", type=positive_float, default=900.0,
                     help="seconds before a task's runner call is treated as failed "
                          "(SubprocessRunner) or abandoned (FileRunner's poll deadline)")
    rn.add_argument("--parallel", type=positive_int, default=1, metavar="N",
                     help="dispatch up to N scopes of a wave at the same time (default 1). "
                          "A wave costs its slowest scope instead of the sum of all of them; "
                          "waves still go in order")
    rn.add_argument("--mode", choices=["strict", "lenient"], default=STRICT)
    rn.add_argument("--resume", action="store_true",
                     help="reclaim past-lease tasks and continue this run_id if the "
                          "partition is unchanged; otherwise open a new run inheriting "
                          "unchanged scopes (M5.5)")
    rn.add_argument("--max-attempts", type=positive_int, default=supervisor_mod.MAX_ATTEMPTS,
                     help="retries per scope before it is abandoned (default %d)"
                          % supervisor_mod.MAX_ATTEMPTS)
    rn_lessons = rn.add_mutually_exclusive_group()
    rn_lessons.add_argument("--lessons", type=positive_int, default=None, metavar="N",
                             help="pin lesson-set cut vN (M9.3, 6.7); default: the latest "
                                  "cut if one exists, otherwise none")
    rn_lessons.add_argument("--no-lessons", action="store_true",
                             help="never use a lesson-set, even if a cut exists")
    rn.set_defaults(func=cmd_run)


def cmd_run(args) -> int:
    """Only one `run` per repo at a time (its own lock), but the repo lock that `status`, `query`,
    `collect` and `refresh` use is held only while a wave's results are written (L12), so
    `status` works during a run."""
    from ... import lock as lock_mod
    from ...session import resolve_backend

    if args.runner_cmd is not None and not args.runner_cmd.strip():
        raise CdpError("--runner-cmd is empty: give the command, or omit it to wait for patch files")
    if args.lessons is not None:
        with trajectory_mod.TrajectoryStore() as trajectory:
            require_lesson_cut(trajectory, args.lessons)
    paths = paths_from_args(args)
    kind, pg = resolve_backend(paths.state)
    with lock_mod.repo_lock(paths, kind, pg, shared=False, scope="run:" + paths.repo_id):
        r = supervisor_mod.run_waves(
            paths, build_runner(args.runner_cmd, args.timeout),
            runner_cmd=args.runner_cmd, timeout=args.timeout, mode=args.mode,
            max_attempts=args.max_attempts, resume=args.resume, lessons=args.lessons,
            no_lessons=args.no_lessons, stale_only=args.stale_only, scope=args.scope,
            wave=args.wave, say=print, parallel=args.parallel,
        )
    tasks = r["tasks"]
    ok = tasks.get(supervisor_mod.VALIDATED, 0)
    failed = sum(n for state, n in tasks.items() if state != supervisor_mod.VALIDATED)
    if tasks:
        print("run       %d scope(s): %d accepted, %d abandoned or rejected%s"
              % (sum(tasks.values()), ok, failed,
                 " (%s)" % ", ".join("%s %d" % kv for kv in sorted(tasks.items())
                                      if kv[0] != supervisor_mod.VALIDATED) if failed else ""))
    unknowns = r["rejected_unknowns"]
    if unknowns:
        print("gates     %d unknown(s) rejected" % len(unknowns))
        for row in unknowns[:8]:
            print("  REJECTED unknown (%s): %s" % (row["node"], row["reason"]))
    if not r["nothing_stale"]:
        print("next      cdp query stats, or cdp fold --check")
        if r["any_incomplete"]:
            print("tip       cdp run --resume to retry the incomplete/failed scope(s)")
    if r["hint"]:
        print(r["hint"])
    return outcome_code(ok, failed)


def maybe_print_lessons_hint(trajectory: "trajectory_mod.TrajectoryStore") -> None:
    """Print `supervisor.lessons_hint`, when there is one."""
    msg = supervisor_mod.lessons_hint(trajectory)
    if msg:
        print(msg)
