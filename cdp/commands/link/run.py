"""`cdp link run`."""

from __future__ import annotations

from .._common import Spec, locked, paths_from_args
from ... import link as link_mod, supervisor as supervisor_mod, trajectory as trajectory_mod
from ...link import read_link_report
from ...session import build_runner, open_store
from ...store import SqliteStore
from ...util import CdpError
from pathlib import Path
from typing import Dict


SPEC = Spec(
    group='link',
    usage='link run --db',
    what='Dispatches every ambiguous task through the same lease/retry machine `run` uses for scopes.',
    next='next: `link query --service <name>`. Flags: `--runner-cmd`, `--max-attempts`.',
)


def register(lk_sub) -> None:
    lkr2 = lk_sub.add_parser("run", help="dispatch every ambiguous link task through the "
                                          "same lease/retry machinery `cdp run` uses for "
                                          "scopes, and record it to the trajectory store "
                                          "as dim_task_kind=link (post-Phase-9 item 5)")
    lkr2.add_argument("--db", default=None,
                       help="read from / write back into this SqliteStore's link.* "
                            "namespace instead of the one this invocation resolves to")
    lkr2.add_argument("--run-id", default=None, help="defaults to \"cdp-link\"")
    lkr2.add_argument("--out", default=None,
                       help="directory to write task prompts into (defaults to "
                            "<state>/link-tasks)")
    lkr2.add_argument("--runner-cmd", default=None, metavar="CMD",
                       help="run each task's prompt through this command via "
                            "runner.SubprocessRunner; without it, waits for a human/"
                            "external process to drop the patch file (FileRunner)")
    lkr2.add_argument("--timeout", type=float, default=300.0)
    lkr2.add_argument("--max-attempts", type=int, default=supervisor_mod.MAX_ATTEMPTS)
    lkr2.set_defaults(func=cmd_link_run)


@locked(shared=False, scope="links")
def cmd_link_run(args) -> int:
    """Post-Phase-9 item 5: `link prompts`/`link collect` are a manual,
    file-handoff pair (M8.3) with no leases, no `link_task` rows, and no
    trajectory row -- link work was invisible to `dim_task_kind=link`'s
    routing prior/elision regret even though both already support it by
    construction. This dispatches every ambiguous task through
    `link.dispatch_link_task` (the same lease/retry state machine `cdp run`
    uses for scopes, against `link_task` rather than `snapshot_task` -- R3's
    non-entanglement holds), folds validated resolutions immediately, and
    records one `fact_leaf_run` row per task with `task_kind="link"`.
    """
    paths = paths_from_args(args)
    store = SqliteStore(Path(args.db).expanduser().resolve()) if args.db else open_store(paths)
    try:
        if not store.supports_link_edges():
            raise CdpError(
                "%s cannot back `cdp link run` -- needs the sqlite backend "
                "(pass --db, or set `backend = \"sqlite\"` in CDP_HOME/config.toml)" % type(store).__name__
            )
        report = read_link_report(store)
        tasks = link_mod.build_tasks(report)
        run_id = args.run_id or "cdp-link"
        prompts_dir = Path(args.out).expanduser().resolve() if args.out else (paths.work / "link-tasks")
        prompts_dir.mkdir(parents=True, exist_ok=True)
        runner = build_runner(args.runner_cmd, args.timeout)
        model = args.runner_cmd.split()[0] if args.runner_cmd else "human"
        folded = 0
        counts: Dict[str, int] = {}
        with trajectory_mod.TrajectoryStore() as trajectory:
            for task in tasks:
                row = link_mod.dispatch_link_task(
                    task, run_id, runner, store, prompts_dir, max_attempts=args.max_attempts,
                )
                if row is None:
                    continue
                counts[row["state"]] = counts.get(row["state"], 0) + 1
                if row["state"] == supervisor_mod.VALIDATED:
                    folded += link_mod.fold_resolutions(report, task, row["patch"], run_id)
                repo_id = task["candidates"][0]["caller"]["repo"]
                trajectory.record_leaf_run(
                    run_id=run_id, node=task["task_id"], scope_hash=task["task_id"], repo_id=repo_id,
                    model=model, scope_shape_key=link_mod.link_task_shape_key(task),
                    template_version=None, tier=None, task_kind="link",
                    state=row["state"], attempts=row["attempts"],
                )
        store.write_link_edges(report)
    finally:
        store.close()
    print("link run  %d task(s)  %s  %d resolution(s) folded"
          % (len(tasks), ", ".join("%s %d" % kv for kv in sorted(counts.items())) or "nothing to dispatch", folded))
    if folded:
        print("next      cdp link query --service <name>")
    return 0
