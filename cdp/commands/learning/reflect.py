"""`cdp reflect`."""

from __future__ import annotations

import shlex

from .._common import Spec, locked, paths_from_args
from ... import query as query_mod, reflect as reflect_mod, runner as runner_mod, trajectory as trajectory_mod
from ...session import open_store


SPEC = Spec(
    group='learning',
    usage='reflect',
    what="One real model call per outlier scope from a run's trajectory corpus; keeps only well-formed promotions.",
    next='next (promotions accepted): `lessons cut`, then `holdout --lessons vN <held-out-repo>` before trusting it.',
)


def register(add) -> None:
    rf = add("reflect", "M9.3 (6.6): one real model call per outlier scope from a "
                         "run's own trajectory corpus, cashed out as a deterministic "
                         "promotion or discarded")
    rf.add_argument("--run-id", default=None, help="default: this store's own manifest run_id")
    rf.add_argument("--runner-cmd", required=True, metavar="CMD",
                     help="shell command for SubprocessRunner, given prompt and output "
                          "paths as its last two arguments")
    rf.add_argument("--limit", type=int, default=reflect_mod.DEFAULT_LIMIT,
                     help="max outlier scopes to reflect on (default %d)" % reflect_mod.DEFAULT_LIMIT)
    rf.add_argument("--timeout", type=float, default=300.0)
    rf.set_defaults(func=cmd_reflect)


@locked(shared=False)
def cmd_reflect(args) -> int:
    """M9.3 (6.6): select this run's own outlier scopes from the trajectory
    corpus (deterministic, M9.2's own columns), spend one real model call per
    outlier, and keep only what comes back as a well-formed, deterministic
    promotion (`reflect.validate_promotion`) -- everything else is discarded
    and named, never stored as a vague lesson (R10)."""
    paths = paths_from_args(args)
    backend = open_store(paths)
    store = query_mod.Store(backend)
    run_id = args.run_id or str(store.manifest.get("run_id", "cdp"))
    with trajectory_mod.TrajectoryStore() as trajectory:
        leaf_rows = trajectory.leaf_runs_for(run_id)
    outliers = reflect_mod.select_outliers(leaf_rows, limit=args.limit)
    if not outliers:
        print("reflect   0 outlier scope(s) in run %s -- nothing to reflect on" % run_id)
        backend.write_report("reflections", {"accepted": [], "discarded": []})
        backend.close()
        return 0
    runner = runner_mod.SubprocessRunner(shlex.split(args.runner_cmd), timeout_s=args.timeout)
    prompts_dir = paths.work / "reflections"
    prompts_dir.mkdir(parents=True, exist_ok=True)
    accepted, discarded = reflect_mod.reflect(outliers, runner, prompts_dir)
    for d in discarded:
        print("reflect   DISCARDED (%s): %s" % (d["node"], d["reason"]))
    for a in accepted:
        print("reflect   PROMOTED  (%s): %s" % (a["node"], a["promotion"]["promotion"]))
    print("reflect   %d accepted, %d discarded" % (len(accepted), len(discarded)))
    backend.write_report("reflections", {"accepted": accepted, "discarded": discarded})
    backend.close()
    if accepted:
        with trajectory_mod.TrajectoryStore() as trajectory:
            for a in accepted:
                trajectory.record_promotion(run_id=run_id, node=a["node"], promotion=a["promotion"])
        print("next      cdp lessons cut to freeze %d pending promotion(s), then "
              "cdp holdout --lessons vN <held-out-repo> to A/B before trusting it" % len(accepted))
    return 0
