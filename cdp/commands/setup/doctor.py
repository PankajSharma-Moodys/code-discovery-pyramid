"""`cdp doctor`."""

from __future__ import annotations

import shlex

from .._common import outcome_code, Spec, locked, paths_from_args, require_choice
from ... import doctor as doctor_mod, query as query_mod, runner as runner_mod
from ...schema import Validator, schema_path
from ...session import open_store
from ...util import SKILL_ROOT, path_within, positive_float, read_json, safe_name, write_json
from typing import Dict, List


SPEC = Spec(
    group='setup',
    usage='doctor --runner-cmd <cmd>',
    what='Cross-model conformance harness: schema validity, anchor survival, entailment, recall, false-unknown rate against a golden set. Writes `<state>/doctor/<model>.json`.',
    next='next (only one model report so far): `doctor --model <other>` to build the compatibility table.',
)


def register(add) -> None:
    dr = add("doctor", "model conformance harness (M6.1, 4.10) -- schema "
                        "validity, anchor survival, entailment, recall and "
                        "false-unknown rate against a hand-authored golden set")
    dr.add_argument("--runner-cmd", required=True, metavar="CMD",
                     help="shell command for SubprocessRunner, given prompt and patch "
                          "paths as its last two arguments")
    dr.add_argument("--model", required=True, metavar="LABEL",
                     help="label for this runner in the compatibility table "
                          "(e.g. a model name) -- not passed to the runner itself")
    dr.add_argument("--timeout", type=positive_float, default=300.0)
    dr.add_argument("--node", default=None, help="only this scope")
    dr.set_defaults(func=cmd_doctor)


@locked(shared=True)
def cmd_doctor(args) -> int:
    """M6.1 (4.10): dispatch one runner over every scope of an already-scanned
    repo, score each patch against the hand-authored golden set (currently
    only defined for the `tests/fixtures/minirepo` content, recognised by the symbols the
    repo defines, not its directory name -- on any other repo recall/false-unknown are
    n/a (`None`), rather than silently fabricating a golden set from CDP's own
    output).  Writes `<state>/doctor/<model>.json` and prints the
    compatibility table across every model report already on disk.
    """
    safe_name(args.model, "--model")
    paths = paths_from_args(args)
    backend = open_store(paths)
    store = query_mod.Store(backend)
    sched = store._load("schedule")
    run_id = str(store.manifest.get("run_id", "cdp"))
    validator = Validator.load(schema_path(SKILL_ROOT))
    if args.node:
        require_choice(args.node, [sc["node"] for sc in store.partition["scopes"]], "scope", "--node")
    runner = runner_mod.SubprocessRunner(shlex.split(args.runner_cmd), timeout_s=args.timeout)

    golden_by_module = doctor_mod.golden_for(store.xref, sorted({sc["module"] for sc in store.partition["scopes"]}))

    out_dir = paths.work / "doctor"
    out_dir.mkdir(parents=True, exist_ok=True)
    prompt_path = out_dir / "_scratch_prompt.md"
    patch_path = out_dir / "_scratch_patch.json"

    reports: List[Dict] = []
    for scope in store.partition["scopes"]:
        node = scope["node"]
        if args.node and node != args.node:
            continue
        golden = golden_by_module.get(scope["module"], [])
        report = doctor_mod.doctor_scope(
            scope, store.inventory, store.extraction, store.xref, sched,
            store.state.get("claims", []), run_id, runner, paths.repo,
            prompt_path, patch_path, validator, golden,
        )
        reports.append(report)
        print("  %-40s schema_valid=%-5s empty=%-5s recall=%s false_unknown=%s"
              % (node, report.get("schema_valid"), report.get("empty"),
                 doctor_mod.pct_text(report.get("recall")), doctor_mod.pct_text(report.get("false_unknown_rate"))))

    for p in (prompt_path, patch_path):
        if p.exists():
            p.unlink()

    agg = doctor_mod.aggregate(reports)
    agg["model"] = args.model
    agg["scope_reports"] = reports
    write_json(path_within(out_dir, "%s.json" % args.model, "--model"), agg)
    print("doctor    %s: schema_valid=%s yield_collapse=%s recall=%s false_unknown=%s (n=%d scope(s), %d golden fact(s))"
          % (args.model, doctor_mod.pct_text(agg["schema_validity_rate"]),
             doctor_mod.pct_text(agg["yield_collapse_rate"]), doctor_mod.pct_text(agg["recall"]),
             doctor_mod.pct_text(agg["false_unknown_rate"]), agg["scopes"], agg["golden_total"]))
    if not agg["golden_total"]:
        print("recall: n/a (no golden set for this repo)")

    models = {}
    for f in out_dir.glob("*.json"):
        data = read_json(f)
        if isinstance(data, dict) and "model" in data:
            models[data["model"]] = data
    if len(models) > 1:
        print("\n" + doctor_mod.compatibility_table(models))
    else:
        print("next      cdp doctor --model <other> to compare, once more than one "
              "model has a report here")

    backend.close()
    crashed = sum(1 for r in reports if not r.get("runner_ok"))
    unusable = sum(1 for r in reports if r.get("runner_ok") and not r.get("schema_valid"))
    if crashed or unusable:
        print("doctor    %d of %d scope(s) gave no usable patch (%d runner failure(s), %d invalid or missing)"
              % (crashed + unusable, len(reports), crashed, unusable))
    return outcome_code(len(reports) - crashed - unusable, crashed + unusable)
