"""`cdp lessons`."""

from __future__ import annotations

from .._common import Spec

from ... import trajectory as trajectory_mod
from ...util import CdpError


SPEC = Spec(
    group='learning',
    usage='lessons cut \\| unpromote \\| show',
    what='Cut and inspect numbered, pinned lesson-sets (`cdp run --lessons vN` pins one; default is always the latest cut, never the live corpus).',
    next='`cut` → next: `run --lessons vN`, or `holdout` to A/B first. `unpromote` → next: default `run` resolution now uses the new fallback (`--no-lessons` to opt out). `show` → tip: `lessons cut` / `lessons unpromote --version N`.',
)


def register(add) -> None:
    ls = add("lessons", "M9.3 (6.7): cut and inspect numbered, pinned lesson-sets")
    ls.add_argument("lessons_action", choices=["cut", "show", "unpromote"])
    ls.add_argument("--version", type=int, default=None,
                     help="show: which cut (default: latest); unpromote: required")
    ls.add_argument("--reason", default=None, help="unpromote: audit note, why this cut is being reverted")
    ls.set_defaults(func=cmd_lessons)


def cmd_lessons(args) -> int:
    """M9.3 (6.7): cut and inspect lesson-sets. A cut is a numbered,
    immutable snapshot of every promotion `cdp reflect` has accepted since the
    last cut -- `cdp run --lessons vN` pins one; the default (no flag) is
    always the *latest* cut, never the live, still-growing corpus (6.7:
    "default is latest cut, never live corpus -- a live corpus makes every
    run unreproducible")."""
    with trajectory_mod.TrajectoryStore() as trajectory:
        if args.lessons_action == "cut":
            version = trajectory.cut_lessons()
            if version is None:
                print("lessons   nothing pending to cut")
            else:
                n = len(trajectory.load_lessons(version))
                print("lessons   cut v%d (%d promotion(s))" % (version, n))
                print("next      cdp run --lessons v%d to pin it, or cdp holdout --lessons v%d "
                      "<held-out-repo> to A/B it first" % (version, version))
        elif args.lessons_action == "unpromote":
            if args.version is None:
                raise CdpError("`cdp lessons unpromote` needs --version")
            if not trajectory.unpromote_cut(args.version, reason=args.reason):
                raise CdpError("v%d is not currently promoted -- nothing to unpromote" % args.version)
            fallback = trajectory.latest_lesson_version()
            print("lessons   v%d unpromoted -- default `cdp run` resolution now falls back to %s"
                  % (args.version, ("v%d" % fallback) if fallback is not None else "no lesson-set"))
            print("next      cdp run --lessons vN uses the new fallback automatically; "
                  "pass --no-lessons to opt out entirely")
        else:  # show
            version = args.version if args.version is not None else trajectory.latest_lesson_version()
            if version is None:
                print("lessons   no cut exists yet")
                return 0
            lessons = trajectory.load_lessons(version)
            print("lessons   v%d (%d promotion(s))" % (version, len(lessons)))
            for row in lessons:
                print("  %-30s %-20s %s" % (row["node"], row["kind"], row["payload"]))
            print("tip       cdp lessons cut freezes new promotions since this cut; "
                  "cdp lessons unpromote --version N reverts one")
    return 0
