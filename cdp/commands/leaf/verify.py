"""`cdp verify`."""

from __future__ import annotations

from .._common import Spec, locked, paths_from_args
from ... import query as query_mod, state as state_mod
from ...session import check_repo_matches_manifest, open_store
from ...verify import STRICT


SPEC = Spec(
    group='leaf',
    usage='verify [--full]',
    what='Recomputes the fold from the log and diffs it against `state.json`; `--full` also proves the archive.',
    next='On `FAIL`: `rollback --to-run <run>`, then `fold`. On `ok` without `--full`: tip — `verify --full` (needs `compact` first).',
)


def register(add) -> None:
    vf = add("verify", "recompute the fold from the log and compare to state.json; "
                        "--full also proves the archive, not just the hot table")
    vf.add_argument("--full", action="store_true",
                     help="re-fold from the cold archive too (M7.4, 2.5) -- "
                          "what makes compaction provably lossless rather than asserted")
    vf.add_argument("--mode", choices=["strict", "lenient"], default=STRICT)
    vf.set_defaults(func=cmd_verify)


@locked(shared=True)
def cmd_verify(args) -> int:
    """M7.4 (2.5): same mechanism as `fold --check`, extended over the cold
    archive when `--full` is given -- the audit story that makes `compact`
    provably lossless rather than merely asserted."""
    paths = paths_from_args(args)
    backend = open_store(paths)
    store = query_mod.Store(backend)
    check_repo_matches_manifest(paths, store.manifest)
    problems = state_mod.check_fold(
        backend, store.xref, store.partition, repo=paths.repo, mode=args.mode, full=args.full
    )
    backend.close()
    if problems:
        for problem in problems:
            print("FAIL  %s" % problem)
        print("next      cdp rollback --to-run <the offending run> to exclude it, "
              "or cdp fold to recompute and re-check")
        return 1
    if args.full:
        print("ok    state.json = fold(merge, patches/ + archive/, xref.json)")
        print("ok    archive rows match their recorded content hash")
    else:
        print("ok    state.json = fold(merge, patches/, xref.json)")
        print("tip       cdp verify --full to also audit the cold archive "
              "(needs cdp compact to have run first)")
    return 0
