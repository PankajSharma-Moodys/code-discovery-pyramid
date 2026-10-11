"""`cdp link collect`."""

from __future__ import annotations

import json

from .._common import Spec, locked, open_link_store, outcome_code, paths_from_args
from ... import link as link_mod
from ...link import read_link_report
from ...util import CdpError, read_json
from pathlib import Path


SPEC = Spec(
    group='link',
    usage='link collect --db --in DIR',
    what='Validates → verifies → entails → folds every patch from a prior `link prompts --out`.',
    next='next: `link query --service <name>`.',
)


def register(lk_sub) -> None:
    lkc = lk_sub.add_parser("collect", help="validate+verify+entail+fold every patch "
                                             "left in a `link prompts --out`'s inbox/ (M8.3)")
    lkc.add_argument("--db", default=None,
                      help="read from / write back into this SqliteStore's link.* "
                           "namespace instead of the one this invocation resolves to")
    lkc.add_argument("--in", dest="in_dir", required=True,
                      help="the directory a prior `link prompts --out` wrote")
    lkc.set_defaults(func=cmd_link_collect)


@locked(shared=False, scope="links")
def cmd_link_collect(args) -> int:
    """M8.3 (5.2): validate -> verify -> entail -> fold, for link-task
    patches only -- `link.validate_task_patch` is the validate+verify+entail
    step (closed verdict vocabulary, no fabricated citation), matching
    `cmd_collect`'s own shape for the single-repo case one function up, not
    the same function, since a link task's patch is a handful of fields
    against a cross-repo candidate set rather than a scope's full claim
    schema. Accepted resolutions attribute onto their link by `link_id`
    (never touching `match_kind`, M8.1's own closed vocabulary) and are
    persisted back the same way `link scan --db` writes -- R3 still holds,
    nothing here touches `snapshot.*`/`claim.*`.
    """
    in_dir = Path(args.in_dir).expanduser().resolve()
    tasks = {t["task_id"]: t for t in read_json(in_dir / "tasks.json")}

    paths = paths_from_args(args)
    store = open_link_store(args, paths, "collect", writable=True)
    try:
        report = read_link_report(store)
        run_id = "cdp-link"
        accepted = 0
        rejected = []
        folded = 0
        for patch_path in sorted((in_dir / "inbox").glob("*.json")):
            try:
                patch = json.loads(patch_path.read_text(encoding="utf-8"))
            except ValueError as exc:
                rejected.append((patch_path.name, ["not valid JSON: %s" % exc]))
                continue
            if not isinstance(patch, dict):
                rejected.append((patch_path.name, ["a patch is a JSON object, got %s" % type(patch).__name__]))
                continue
            task = tasks.get(patch.get("task_id"))
            if task is None:
                rejected.append((patch_path.name, ["/task_id: %r is not a known task" % patch.get("task_id")]))
                continue
            errors = link_mod.validate_task_patch(patch, task)
            if errors:
                rejected.append((patch_path.name, errors))
                continue
            accepted += 1
            folded += link_mod.fold_resolutions(report, task, patch, run_id, store=store)
    finally:
        store.close()

    print("link collect  accepted %d, rejected %d, %d resolution(s) folded"
          % (accepted, len(rejected), folded))
    for name, errors in rejected:
        print("  REJECTED %s: %s" % (name, "; ".join(errors[:4])))
    if folded:
        print("next      cdp link query --service <name>")
    return outcome_code(accepted, len(rejected))
