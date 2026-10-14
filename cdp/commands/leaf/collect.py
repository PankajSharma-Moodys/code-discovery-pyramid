"""`cdp collect`."""

from __future__ import annotations

from .._common import Spec, locked, paths_from_args
from ... import intake as intake_mod
from ...verify import STRICT


SPEC = Spec(
    group='leaf',
    usage='collect',
    what='Validates, verifies and appends leaf patches sitting in the inbox.',
    next='next: `fold --check`.',
)


def register(add) -> None:
    c = add("collect", "validate, verify and append leaf patches from the inbox")
    c.add_argument("--mode", choices=["strict", "lenient"], default=STRICT)
    c.set_defaults(func=cmd_collect)


@locked(shared=False)
def cmd_collect(args) -> int:
    r = intake_mod.collect(paths_from_args(args), mode=args.mode)
    accepted, rejected, stats = r["accepted"], r["rejected"], r["stats"]
    unknown_rejections = r["unknown_rejections"]
    if r["tiering_upgrades"]:
        print("tiering   %d scope(s) upgraded to T3 (leaf_escalated): %s"
              % (len(r["tiering_upgrades"]), ", ".join(sorted(r["tiering_upgrades"]))))

    print("accepted  %d patch(es), rejected %d" % (len(accepted), len(rejected)))
    if stats["claims_in"]:
        print("verify    %d/%d claims kept, demotion rate %.3f (%s)"
              % (stats["claims_kept"], stats["claims_in"], stats["demotion_rate"],
                 ", ".join("%s %d" % kv for kv in stats["reasons"].items()) or "no failures"))
        # PLAN.md C1: the number that decides whether the strict reading of
        # §5.4 is buying correctness or costing recall.
        print("          %d demoted claim(s) had at least one good anchor "
              "(would survive under --mode lenient)" % stats["would_survive_lenient"])
    for row in rejected:
        print("  REJECTED %s (%s)" % (row["file"], row.get("node", "?")))
        for err in row["errors"][:4]:
            print("    %s" % err)
    for row in r["rejected_claims"][:8]:
        print("  REJECTED claim %s (%s): %s" % (row["id"], row["node"], row["reasons"][0]))
    if r["rejected_claims"]:
        print("claims    %d claim(s) rejected, the rest of their patches kept" % len(r["rejected_claims"]))
    if unknown_rejections:
        print("gates     %d unknown(s) rejected" % len(unknown_rejections))
        for row in unknown_rejections[:8]:
            print("  REJECTED unknown (%s): %s" % (row["node"], row["reason"]))
    print("coverage  %.1f%%" % (100 * r["coverage"]["fraction"]))
    if stats["escalation_rate"] is not None:
        print("escalation %.3f (M6.3: fraction of claims that needed source beyond the digest)"
              % stats["escalation_rate"])
    if accepted:
        print("next      cdp fold --check")
    if rejected:
        print("rejected  %d patch(es) rejected: fix them and re-drop into the inbox (exit 1)" % len(rejected))
        return 1
    return 0
