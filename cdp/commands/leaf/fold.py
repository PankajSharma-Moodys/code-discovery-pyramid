"""`cdp fold`."""

from __future__ import annotations

from .._common import Spec, locked, paths_from_args
from ... import query as query_mod, state as state_mod
from ...session import check_repo_matches_manifest, fold_and_write, open_store


SPEC = Spec(
    group='leaf',
    usage='fold [--check]',
    what='Recomputes `state.json` from `patches/` + `xref.json`. `--check` verifies the invariant instead of writing.',
    next='next (no `--check`): `query stats`. On `--check` failure: `rollback` the offending run, or `fold` again.',
)


def register(add) -> None:
    f = add("fold", "recompute state.json from patches/ + xref.json")
    f.add_argument("--check", action="store_true", help="verify the invariant instead of writing")
    f.set_defaults(func=cmd_fold)


@locked(shared=False)
def cmd_fold(args) -> int:
    paths = paths_from_args(args)
    backend = open_store(paths)
    store = query_mod.Store(backend)
    check_repo_matches_manifest(paths, store.manifest)
    if args.check:
        problems = state_mod.check_fold(backend, store.xref, store.partition, repo=paths.repo)
        problems += state_mod.check_order_independence(
            backend.load_patches(), store.xref, store.partition
        )
        backend.close()
        if problems:
            for problem in problems:
                print("FAIL  %s" % problem)
            return 1
        print("ok    state.json = fold(merge, patches/, xref.json)")
        print("ok    merge is order-independent under reordering of the log")
        return 0
    before = {c["id"] for c in store.state.get("claims", [])}
    folded = fold_and_write(backend, store.xref, store.partition, repo=paths.repo)
    dropped = sorted(before - {c["id"] for c in folded["claims"]})
    if dropped:
        demoted = {u.get("demoted_from") for u in folded["unknowns"] if u.get("demoted_from")}
        print("dropped   %d claim(s) that were live before this fold (%d demoted to unknowns, %d no longer "
              "in the log or rolled back): %s" % (len(dropped), len(demoted & set(dropped)),
                                                    len(dropped) - len(demoted & set(dropped)), ", ".join(dropped[:5])))
    print("folded %d patch(es) -> %d claims, %d unknowns, coverage %.1f%%"
          % (folded["provenance"]["patch_count"], len(folded["claims"]),
             len(folded["unknowns"]), 100 * folded["coverage"]["fraction"]))
    print("next      cdp query stats")
    backend.close()
    return 0
