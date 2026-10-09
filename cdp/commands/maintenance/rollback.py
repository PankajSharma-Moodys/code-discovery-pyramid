"""`cdp rollback`."""

from __future__ import annotations

from .._common import Spec, locked, paths_from_args
from ... import query as query_mod, rollback as rollback_mod, state as state_mod, trajectory as trajectory_mod
from ...session import open_store
from ...store import registry as registry_mod
from ...util import CdpError
from ...verify import STRICT


SPEC = Spec(
    group='maintenance',
    usage='rollback --to-run R \\| --to-snapshot S',
    what="Excludes a run's patches from the fold without deleting them (append-only ledger).",
    next='next: `query stats` to confirm the exclusion took effect. tip: `--reason "..."` to record why.',
)


def register(add) -> None:
    rb = add("rollback", "exclude a run's patches from the fold, without deleting them")
    rb_target = rb.add_mutually_exclusive_group(required=True)
    rb_target.add_argument("--to-run", metavar="RUN_OR_COMMIT",
                            help="exclude just this run's patches")
    rb_target.add_argument("--to-snapshot", metavar="COMMIT",
                            help="exclude this run and every run appended after it")
    rb.add_argument("--reason", default=None, help="why (recorded in the rollback ledger)")
    rb.add_argument("--mode", choices=["strict", "lenient"], default=STRICT)
    rb.set_defaults(func=cmd_rollback)


@locked(shared=False)
def cmd_rollback(args) -> int:
    """M3.7: exclude a run's patches from the fold, without deleting them (R5).

    `--to-run` drops exactly one run, wherever it sits in the log. `--to-snapshot`
    drops that run and every run appended after it -- the log's own append
    order, since patches carry no timestamp by construction (D8). Either way
    the excluded run_ids are recorded in an append-only ledger
    (`cdp/rollback.py`) that every future fold (`scan`, `collect`, `fold`,
    `refresh`) reads, so the exclusion holds until a future rollback changes it.
    """
    paths = paths_from_args(args)
    backend = open_store(paths)
    store = query_mod.Store(backend)
    patches = backend.load_patches()

    if args.to_run:
        target = rollback_mod.resolve_run_id(args.to_run)
        kept, new_excluded = rollback_mod.patches_excluding_run(patches, target)
        if not new_excluded:
            raise CdpError("no patch in the log is stamped with run %s -- nothing to roll back" % target)
        kind = "to_run"
    else:
        target = rollback_mod.resolve_run_id(args.to_snapshot)
        kept, new_excluded, found = rollback_mod.patches_up_to_run(patches, target)
        if not found:
            raise CdpError("run %s never appended a patch -- nothing to roll back to" % target)
        if not new_excluded:
            print("rollback  --to-snapshot %s: already the most recent run, nothing to exclude" % target)
            backend.close()
            return 0
        kind = "to_snapshot"

    prior_excluded = rollback_mod.load_excluded_run_ids(backend)
    all_excluded = prior_excluded | new_excluded
    folded = state_mod.fold(
        patches, store.xref, store.partition, repo=paths.repo, mode=args.mode,
        excluded_run_ids=all_excluded,
        extraction=store.extraction,
    )
    backend.write_artifact("state", folded)
    reason = args.reason or ("rollback --%s %s" % (kind.replace("_", "-"), target))
    rollback_mod.record_rollback(backend, kind, target, new_excluded, reason)

    repo_id = registry_mod.repo_identity(paths.repo)
    with trajectory_mod.TrajectoryStore() as trajectory:
        for excluded_run_id in sorted(new_excluded):
            trajectory.record_run_event(run_id=excluded_run_id, repo_id=repo_id,
                                         event="rolled_back", reason=reason)

    print("rollback  %s %s: excluded %d run(s) (%s)"
          % (("--to-run" if kind == "to_run" else "--to-snapshot"), target,
             len(new_excluded), ", ".join(sorted(new_excluded))))
    print("folded    %d claim(s), %d unknown(s), coverage %.1f%%"
          % (len(folded["claims"]), len(folded["unknowns"]), 100 * folded["coverage"]["fraction"]))
    print("next      cdp query stats to confirm the exclusion took effect")
    if not args.reason:
        print("tip       --reason \"...\" records why, in the rollback ledger, for whoever reads it later")
    backend.close()
    return 0
