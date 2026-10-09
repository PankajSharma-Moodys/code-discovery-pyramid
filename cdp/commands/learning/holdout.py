"""`cdp holdout`."""

from __future__ import annotations

from .._common import Spec, locked, paths_from_args
from ... import query as query_mod, reflect as reflect_mod, tiering as tiering_mod, trajectory as trajectory_mod
from ...session import open_store
from ...store import registry as registry_mod
from ...util import CdpError


SPEC = Spec(
    group='learning',
    usage='holdout --lessons vN <repo>',
    what="A/B a lesson-set cut against a repo outside its own learning corpus; promotes to latest only if it doesn't regress.",
    next="On promote: next — `run --lessons vN` (or omit `--lessons`; it's now the latest cut).",
)


def register(add) -> None:
    ho = add("holdout", "M9.3 (6.8): A/B a lesson-set cut against a repo outside its own "
                         "learning corpus; promotes it to `latest` only if it passes")
    ho.add_argument("--lessons", type=int, required=True, metavar="N", help="the cut to A/B")
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

    symbol_owner, namespace_owner = tiering_mod.build_symbol_index_for_tiering(store.extraction)
    module_set = {m["name"] for m in store.inventory["modules"]}
    scopes = store.partition["scopes"]

    def t3_rate(extra_third_party) -> float:
        if not scopes:
            return 0.0
        t3 = sum(
            1 for s in scopes
            if tiering_mod.compute_tier(
                s, store.extraction, module_set, symbol_owner, namespace_owner, extra_third_party
            )["tier"] == tiering_mod.T3
        )
        return t3 / len(scopes)

    before = t3_rate(frozenset())
    after = t3_rate(hints["third_party_patterns"])
    metric = {"t3_rate_none": before, "t3_rate_lessons": after, "scopes": len(scopes)}

    # Promotion bar (6.8's own open decision, settled here): a lesson-set
    # must not *increase* T3 escalation on a repo it never learned from --
    # an increase means its import_channel_hint patterns overfit the
    # learning corpus rather than naming a real third-party root.
    passed = after <= before
    print("holdout   v%d on %s: T3 rate %.3f (none) -> %.3f (lessons) -- %s"
          % (args.lessons, repo_id, before, after, "PROMOTE" if passed else "REJECT"))
    backend.write_report("holdout", metric)
    store.close()
    if passed:
        with trajectory_mod.TrajectoryStore() as trajectory:
            trajectory.promote_cut(args.lessons, repo_id, metric)
        print("holdout   v%d promoted to latest" % args.lessons)
        print("next      cdp run --lessons v%d (or omit --lessons; v%d is now the latest cut)"
              % (args.lessons, args.lessons))
    else:
        print("holdout   v%d NOT promoted -- regression on a repo outside its learning corpus" % args.lessons)
    return 0 if passed else 1
