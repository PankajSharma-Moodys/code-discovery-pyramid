"""`cdp holdout`."""

from __future__ import annotations

from .._common import Spec, locked, paths_from_args
from ... import holdout as holdout_mod, query as query_mod, reflect as reflect_mod, trajectory as trajectory_mod
from ...session import open_store
from ...store import registry as registry_mod
from .._common import require_lesson_cut
from ...util import CdpError, positive_int


SPEC = Spec(
    group='learning',
    usage='holdout --lessons N --repo <holdout-repo>',
    what="A/B a lesson-set cut against a repo outside its own learning corpus; promotes to latest only if it doesn't regress.",
    next="On promote: next — `run --lessons N` (or omit `--lessons`; it's now the latest cut).",
)


def register(add) -> None:
    ho = add("holdout", "M9.3 (6.8): A/B a lesson-set cut against a repo outside its own "
                         "learning corpus; promotes it to `latest` only if it passes")
    ho.add_argument("--lessons", type=positive_int, required=True, metavar="N", help="the cut to A/B")
    ho.set_defaults(func=cmd_holdout)


@locked(shared=False)
def cmd_holdout(args) -> int:
    """M9.3 (6.8): "A/B on a pinned snapshot, `--lessons none` vs `--lessons
    vN`. Learn on repos A-E, benchmark on F, or you are measuring
    memorisation." The A here is the deterministic tiering rule (M6.4) with
    and without the cut's `import_channel_hint` patterns applied -- no live
    model call, since T3 escalation is exactly the routing signal a lesson
    can move (`graph._looks_third_party`), and it is reproducible by
    construction. The split-is-real check (this milestone's own stress test)
    runs first and refuses outright if it fails."""
    paths = paths_from_args(args)
    backend = open_store(paths)
    store = query_mod.Store(backend)
    repo_id = registry_mod.repo_identity(paths.repo)

    with trajectory_mod.TrajectoryStore() as trajectory:
        try:
            require_lesson_cut(trajectory, args.lessons)
        except CdpError:
            store.close()
            raise
        learned = trajectory.learned_repos_for_cut(args.lessons)
        if repo_id in learned:
            store.close()
            raise CdpError(
                "holdout repo %r is in v%d's own learning corpus %s -- this would "
                "measure memorisation, not a real holdout (6.8)" % (repo_id, args.lessons, sorted(learned))
            )
        lessons = trajectory.load_lessons(args.lessons)
        if not lessons:
            store.close()
            raise CdpError("lesson-set v%d has no rows to A/B" % args.lessons)
        hints = reflect_mod.apply_lessons(lessons)
        unmeasured = holdout_mod.unmeasurable(lessons)
        if unmeasured:
            store.close()
            print("holdout   v%d NOT promoted: it contains %s, which no deterministic A/B can measure "
                  "(it measures import_channel_hint and budget_change on claims); pin it with "
                  "`run --lessons %d` instead" % (args.lessons, ", ".join(unmeasured), args.lessons))
            return 1

    none = holdout_mod.measure(store, {})
    with_lessons = holdout_mod.measure(store, hints)
    passed, regressed = holdout_mod.compare(none, with_lessons)
    metric = {"none": none, "lessons": with_lessons, "regressed": regressed}
    # Promotion bar: no quality metric (T3 rate, verified claims lost to the budget, claims citing an
    # elided subject, contradicted rate) may rise, and prompt cost may not grow more than COST_SLACK.
    print("holdout   v%d on %s: T3 %.3f -> %.3f, elided verified claims %d -> %d, elision regret %d -> %d, "
          "contradicted %.3f -> %.3f, tokens %d -> %d, claims/ktok %.2f -> %.2f -- %s"
          % (args.lessons, repo_id, none["t3_rate"], with_lessons["t3_rate"], none["elided_verified"],
             with_lessons["elided_verified"], none["elision_regret"], with_lessons["elision_regret"],
             none["contradicted_rate"], with_lessons["contradicted_rate"], none["tokens_est"],
             with_lessons["tokens_est"], none["claims_per_ktok"], with_lessons["claims_per_ktok"],
             "PROMOTE" if passed else "REJECT (%s)" % ", ".join(regressed)))
    backend.write_report("holdout", metric)
    store.close()
    if passed:
        with trajectory_mod.TrajectoryStore() as trajectory:
            trajectory.promote_cut(args.lessons, repo_id, metric)
        print("holdout   v%d promoted to latest" % args.lessons)
        print("next      cdp run --lessons %d (or omit --lessons; v%d is now the latest cut)"
              % (args.lessons, args.lessons))
    else:
        print("holdout   v%d NOT promoted -- regression on a repo outside its learning corpus" % args.lessons)
    return 0 if passed else 1
