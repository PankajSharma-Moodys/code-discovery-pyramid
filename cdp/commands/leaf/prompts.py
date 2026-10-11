"""`cdp prompts`."""

from __future__ import annotations

from .._common import Spec, locked, paths_from_args, require_choice, require_lesson_cut
from ... import prompts as prompts_mod, rereview as rereview_mod, query as query_mod, reflect as reflect_mod, tiering as tiering_mod, trajectory as trajectory_mod
from ...prompts import build_prompt
from ...session import check_repo_matches_manifest, open_store
from ...util import non_negative_int, positive_int, write_text
from typing import Dict, List


SPEC = Spec(
    group='leaf',
    usage='prompts',
    what='Writes one leaf prompt per scope for the wave loop.',
    next='next: hand each prompt to a leaf, then `collect`. Flags: `--digest` (full-file prompts instead of citations), `--wave N`, `--node X`, `--lessons N`/`--no-lessons`.',
)


def register(add) -> None:
    pr = add("prompts", "write one leaf prompt per scope, for the wave loop")
    pr.add_argument("--wave", type=non_negative_int, default=None, help="only this wave")
    pr.add_argument("--node", default=None, help="only this node")
    pr.add_argument("--measure", action="store_true",
                     help="print a per-section token estimate (M5.6, 4.9) instead of "
                          "the usual per-scope summary -- chars/4, not a real tokenizer")
    pr.add_argument("--digest", action="store_true",
                     help="M6.3 (4.2): digest-first mode -- the leaf's input is full file "
                          "text inlined in the prompt, not a Read/Grep tool. Behind a flag "
                          "until doctor/benchmark evidence promotes it to default.")
    pr_lessons = pr.add_mutually_exclusive_group()
    pr_lessons.add_argument("--lessons", type=positive_int, default=None, metavar="N",
                             help="pin lesson-set cut vN (M9.3, 6.7/6.8); default: the "
                                  "latest *promoted* cut, or none if none is promoted yet")
    pr_lessons.add_argument("--no-lessons", action="store_true",
                             help="never use a lesson-set, even if one is promoted")
    pr.set_defaults(func=cmd_prompts)


@locked(shared=False)
def cmd_prompts(args) -> int:
    paths = paths_from_args(args)
    backend = open_store(paths, durable=True)
    store = query_mod.Store(backend)
    if args.digest:
        # M6.3: digest mode reads --repo's file content, unlike the default
        # prompt build -- the same silent-wrong-repo failure mode as F16.
        check_repo_matches_manifest(paths, store.manifest)
    sched = store._load("schedule")
    run_id = store.manifest.get("run_id", "cdp")
    prior = list(store.state.get("claims", []))

    if args.node is not None:
        require_choice(args.node, [sc["node"] for sc in store.partition["scopes"]], "scope", "--node")
    if args.wave is not None:
        require_choice(args.wave, set(sched["node_wave"].values()), "wave", "--wave")

    out_dir = paths.work / "prompts"
    out_dir.mkdir(parents=True, exist_ok=True)
    backend.ensure_inbox()

    # M6.4 (4.8): built once, not per scope -- `build_symbol_index` scans all
    # of `extraction`, so per-scope re-building would be quadratic in scope count.
    symbol_index = tiering_mod.build_symbol_index_for_tiering(store.extraction)

    # M9.3 (6.8): the same lesson resolution `cmd_run` uses, so `cdp prompts
    # --lessons vN` reproduces exactly what a real run would have applied --
    # this is `cdp holdout`'s own A/B lever, no live model call required.
    with trajectory_mod.TrajectoryStore() as trajectory:
        if args.no_lessons:
            lessons_version = None
        elif args.lessons is not None:
            require_lesson_cut(trajectory, args.lessons)
            lessons_version = args.lessons
        else:
            lessons_version = trajectory.latest_lesson_version(paths.repo_id)
        lesson_hints: Dict = {}
        if lessons_version is not None:
            lesson_hints = reflect_mod.apply_lessons(trajectory.load_lessons(lessons_version))
    prompt_kwargs: Dict = {}
    if lesson_hints.get("max_inherited") is not None:
        prompt_kwargs["max_inherited"] = lesson_hints["max_inherited"]

    written: List[Dict] = []
    # C2: a scope a leaf reviewed before, with stale claims or new files, gets a prompt for those only;
    # `collect` keeps its other claims (the marker below says which).
    plans = {n: p for n, p in rereview_mod.plans_for(
        store, paths.repo, [sc["node"] for sc in store.partition["scopes"]
                            if (not args.node or sc["node"] == args.node)]).items() if not p.empty}
    marker = {n: p.marker() for n, p in plans.items()}
    if args.node:  # one scope's prompt must not erase the markers of the others
        kept = backend.read_report("rereview", {}) or {}
        marker = dict({n: m for n, m in (kept.get("nodes") or {}).items() if n != args.node}
                      if kept.get("head") == store.inventory.get("head") else {}, **marker)
    for scope in store.partition["scopes"]:
        node = scope["node"]
        if args.node and node != args.node:
            continue
        if args.wave is not None and sched["node_wave"].get(node) != args.wave:
            continue
        text, stats = build_prompt(
            scope, store.inventory, store.extraction, store.xref, sched, prior, run_id,
            digest_mode=args.digest, repo_root=paths.repo, symbol_index=symbol_index,
            extra_third_party=lesson_hints.get("third_party_patterns", frozenset()),
            prompt_fixes=lesson_hints.get("prompt_fixes", ()),
            inbox_dir=backend._inbox_dir(),
            rereview=plans[node].as_prompt() if node in plans else None,
            **prompt_kwargs
        )
        path = out_dir / (node.replace("/", "__") + ".md")
        write_text(path, text)
        stats["prompt"] = str(path)
        stats["wave"] = sched["node_wave"].get(node)
        written.append(stats)

    backend.write_report("prompts", {"prompts": written})
    backend.write_report("rereview", {"head": store.inventory.get("head"), "nodes": marker})
    tiering_report = {row["node"]: row["tiering"] for row in written if "tiering" in row}
    backend.write_report("tiering", {"tiering": tiering_report})
    if tiering_report:
        t3 = {n: r for n, r in tiering_report.items() if r["tier"] == tiering_mod.T3}
        print("tiering   %d/%d scope(s) T3 (%s)" % (
            len(t3), len(tiering_report),
            ", ".join(sorted({r["reason"] for r in t3.values()})) or "none",
        ))
    if args.measure:
        print_token_report(written)
        backend.close()
        return 0
    fired = [w for w in written if w["budget_fired"]]
    tightened = [w for w in written if w.get("prompt_tightened")]
    exhausted = [w for w in written if w.get("prompt_budget_exhausted")]
    print("wrote %d prompt(s) to %s" % (len(written), out_dir))
    for row in written:
        flags = []
        if row["budget_fired"]:
            flags.append("BUDGET FIRED (%d elided)" % row["elided_claims"])
        if row.get("prompt_tightened"):
            flags.append("TIGHTENED (%s)" % ", ".join(row["prompt_tightened"]))
        if row.get("prompt_budget_exhausted"):
            flags.append("OVER max_prompt_tokens=%s EVEN AT FLOOR" % row.get("max_prompt_tokens"))
        print("  wave %-2s %-60s %2d files, sigma %d claim(s)%s"
              % (row["wave"], row["node"], row["files"], row["inherited_claims"],
                 "  " + "; ".join(flags) if flags else ""))
    if not fired:
        print("\ninherited-sigma budget never fired; the 200-claim default is not binding here.")
    if tightened:
        print("%d scope(s) exceeded max_prompt_tokens and were auto-tightened." % len(tightened))
    if exhausted:
        print("%d scope(s) still exceed max_prompt_tokens after every lever was floored -- "
              "raise --max-leaf-files/--max-leaf-loc down, or accept the overrun." % len(exhausted))
    if written:
        print("next      hand each prompt in %s to a leaf, then cdp collect" % out_dir)
        if not args.digest:
            print("tip       --digest builds full-file prompts instead of citations")
    backend.close()
    return 0


def print_token_report(written: List[Dict]) -> None:
    """M5.6 (4.9): sum every leaf's per-section chars and report the
    fixed/variable split `CDP_CLI_SCOPE.md` says to measure before deciding on
    batching. `header`+`task` do not grow with scope size -- they are the
    part of the cost that scales with *scope count*, which is the shape a
    wrong cost curve would have."""
    if not written:
        print("no scopes matched -- nothing to measure")
        return
    section_totals: Dict[str, int] = {}
    for row in written:
        for name, chars in row["section_chars"].items():
            section_totals[name] = section_totals.get(name, 0) + chars
    total_tokens = sum(row["tokens_est"] for row in written)
    fixed_tokens = sum(row["fixed_tokens_est"] for row in written)
    n = len(written)
    print("measured  %d leaf prompt(s), chars/%d token estimate (not a real tokenizer)"
          % (n, prompts_mod.CHARS_PER_TOKEN_EST))
    for name, chars in sorted(section_totals.items(), key=lambda kv: -kv[1]):
        print("  %-10s %8d chars  (%d/leaf avg)" % (name, chars, chars // n))
    print("total     %d tokens_est (%d/leaf avg)" % (total_tokens, total_tokens // n))
    print("fixed     %d tokens_est (%d/leaf avg) -- header+task, independent of scope content"
          % (fixed_tokens, fixed_tokens // n))
    print("variable  %d tokens_est (%d/leaf avg) -- files/structure/inherited/gaps"
          % (total_tokens - fixed_tokens, (total_tokens - fixed_tokens) // n))
