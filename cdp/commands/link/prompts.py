"""`cdp link prompts`."""

from __future__ import annotations

import shlex

from .._common import Spec, locked, open_link_store, outcome_code, paths_from_args
from ... import link as link_mod, runner as runner_mod
from ...link import read_link_report
from ...util import CdpError, write_json, write_text
from pathlib import Path


SPEC = Spec(
    group='link',
    usage='link prompts --db --out DIR',
    what='Writes one prompt per ambiguous (heuristic) caller target.',
    next='next (no `--runner-cmd`): hand each prompt to a leaf, drop its patch in `<out>/inbox`, then `link collect --in <out>`.',
)


def register(lk_sub) -> None:
    lkp = lk_sub.add_parser("prompts", help="write one prompt per ambiguous (heuristic) "
                                             "link, from a prior `link scan --db` (M8.3, 5.2)")
    lkp.add_argument("--db", default=None,
                      help="read from / write back into this SqliteStore's link.* "
                           "namespace instead of the one this invocation resolves to")
    lkp.add_argument("--out", required=True, help="directory to write tasks/, tasks.json, "
                                                    "inbox/ into")
    lkp.add_argument("--runner-cmd", default=None,
                      help="if set, immediately run each task's prompt through this "
                           "command via runner.SubprocessRunner (same protocol `cdp run` "
                           "uses) and write its patch into --out/inbox/")
    lkp.set_defaults(func=cmd_link_prompts)


@locked(shared=False, scope="links")
def cmd_link_prompts(args) -> int:
    """M8.3 (5.2): the LLM tier fires only on ambiguous (`heuristic`) matches
    a prior `link scan --db` already persisted. Writes one prompt per
    distinct ambiguous caller target (`link.build_tasks` groups candidates so
    "three concatenations" become one question), plus `tasks.json` --
    `link collect`'s own validation reference for what each task actually
    showed the model, so a resolution's citation can be checked against it.

    Reuses `runner.py`'s protocol wholesale (5.2, "mirrors the core loop
    exactly"): with `--runner-cmd`, each task's prompt/patch pair is run
    through the exact same `SubprocessRunner` `cdp run` uses, no
    link-specific dispatch code.
    """
    paths = paths_from_args(args)
    store = open_link_store(args, paths, "prompts", writable=False)
    try:
        report = read_link_report(store)
    finally:
        store.close()

    tasks = link_mod.unresolved_tasks(report)  # a link that has a verdict is not asked again
    out_dir = Path(args.out).expanduser().resolve()
    (out_dir / "tasks").mkdir(parents=True, exist_ok=True)
    (out_dir / "inbox").mkdir(parents=True, exist_ok=True)
    write_json(out_dir / "tasks.json", tasks)

    runner = runner_mod.SubprocessRunner(shlex.split(args.runner_cmd)) if args.runner_cmd else None
    ran = failed = 0
    for task in tasks:
        prompt_path = out_dir / "tasks" / (task["task_id"] + ".md")
        write_text(prompt_path, link_mod.render_task_prompt(task))
        if runner is not None:
            patch_path = out_dir / "inbox" / (task["task_id"] + ".json")
            result = runner.run(prompt_path, patch_path)
            print("  %-20s %s%s" % (task["task_id"], "ok" if result.ok else "FAILED",
                                     "" if result.ok else ": %s" % result.error))
            ran += 1
            failed += 0 if result.ok else 1
    print("link prompts  %d ambiguous task(s) -> %s%s"
          % (len(tasks), out_dir, "  (ran %d via --runner-cmd)" % ran if runner else ""))
    if tasks and runner is None:
        print("next      hand each prompt in %s/tasks to a leaf, drop its patch in "
              "%s/inbox, then cdp link collect --in %s" % (out_dir, out_dir, out_dir))
    if failed:
        print("link prompts  %d of %d runner call(s) failed" % (failed, ran))
    return outcome_code(ran - failed, failed)
