"""`cdp answer`."""

from __future__ import annotations

import sys

from .._common import Spec, locked, paths_from_args
from ... import intake as intake_mod
from ...schema import Validator, schema_path
from ...util import SKILL_ROOT
from ...verify import STRICT


SPEC = Spec(
    group='leaf',
    usage='answer --scope S --subject X --claim "..." --anchor FILE:LINE',
    what='Records a human claim against an unknown — same validate/verify/entail/fold pipeline as a leaf patch, `author_kind=human`.',
    next="next: `query unknowns` to see what's still open.",
)


def register(add) -> None:
    schema_defs = Validator.load(schema_path(SKILL_ROOT)).schema["$defs"]
    an = add("answer", "record a human claim against an unknown -- validate, "
                        "verify anchor, entail, fold, no bypass (M4.4)")
    an.add_argument("scope", help="the node this claim belongs to, e.g. root/gateway")
    an.add_argument("--subject", required=True, help="what the claim is about, e.g. a fqn")
    an.add_argument("--kind", required=True, choices=sorted(schema_defs["claim_kind"]["enum"]),
                    help="one of CDP's closed claim kinds -- R11: humans outrank "
                         "models on interpretation, never on structure")
    an.add_argument("--claim", required=True, dest="statement", help="the statement text")
    an.add_argument("--anchor", required=True, metavar="FILE:LINE",
                    help="where this is true; the citable text is read from the file itself")
    an.add_argument("--channel", default=None, choices=sorted(schema_defs["channel"]["enum"]))
    an.add_argument("--confidence", default="high", choices=["high", "medium", "low"])
    an.add_argument("--author", default=None, help="default: git config user.name <user.email>")
    an.add_argument("--mode", choices=["strict", "lenient"], default=STRICT)
    an.set_defaults(func=cmd_answer)


@locked(shared=False)
def cmd_answer(args) -> int:
    r = intake_mod.answer(
        paths_from_args(args), scope=args.scope, subject=args.subject, statement=args.statement,
        anchor_ref=args.anchor, kind=args.kind, confidence=args.confidence, author=args.author,
        channel=args.channel, mode=args.mode,
    )
    claim, row = r["claim"], r["row"]
    if row is None:
        print("cdp: claim was NOT kept -- verification demoted it into unknowns[]", file=sys.stderr)
    else:
        print("answer    %s  verdict=%s  confidence=%s"
              % (claim["id"], row.get("verdict"), row.get("confidence")))
    for u in r["discharged"]:
        print("          discharged: %s" % u["question"])
    if r["kept"]:
        print("next      cdp query unknowns to see what's still open")
    return 0 if r["kept"] else 1
