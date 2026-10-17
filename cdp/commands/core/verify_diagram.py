"""`cdp verify-diagram`."""

from __future__ import annotations

import json
import os
import sys

from .._common import Spec
from ... import diagram as diagram_mod


SPEC = Spec(
    group='core',
    usage='verify-diagram <file|-> [--json]',
    what='Checks every edge of a Mermaid flowchart/stateDiagram: its `file:line` must exist and the line +-3 must show the edge. No store read.',
    next='Exit 3: re-cite each non-correct edge at the call/assignment line (the `hint`), with a repo-unique path, then rerun. Exit 0: show the diagram.',
)


def register(add) -> None:
    vd = add("verify-diagram", "check each Mermaid edge's file:line citation against the repo")
    vd.add_argument("file", help="a .mmd file, a markdown answer with ```mermaid fences, or - for stdin")
    vd.add_argument("--json", action="store_true")
    vd.set_defaults(func=cmd_verify_diagram)


def cmd_verify_diagram(args) -> int:
    repo = os.path.abspath(getattr(args, "repo", ".") or ".")
    try:
        if args.file == "-":
            text = sys.stdin.read()
        else:
            with open(args.file, encoding="utf-8", errors="replace") as fh:
                text = fh.read()
        results = diagram_mod.grade(text, diagram_mod.Repo(repo))
    except (OSError, diagram_mod.DiagramError) as exc:
        if args.json:
            print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True))
        else:
            print("error     %s" % exc)
        return 1
    rc = diagram_mod.exit_code(results)
    totals = diagram_mod.summarize(results)
    if args.json:
        print(json.dumps({"ok": rc == 0, "repo": repo, "counts": totals, "diagrams": results},
                         sort_keys=True))
        return rc
    for n, r in enumerate(results, 1):
        _print_diagram(n, r)
    print("total     " + _counts(totals))
    if rc == 3:
        print("next      re-cite each non-correct edge at the line that performs it (see hint), "
              "with a repo-unique path; dash inferred edges (-.->); rerun cdp verify-diagram")
    elif rc == 1:
        print("next      fix the Mermaid syntax error above, then rerun cdp verify-diagram")
    else:
        print("tip       every cited edge checks out; dashed edges are still inferred, say so")
    return rc


def _counts(c) -> str:
    return ", ".join("%d %s" % (c[s], s) for s in diagram_mod.STATUSES if c[s]) or "0 edges"


def _print_diagram(n: int, r) -> None:
    print("diagram %d  %s  %d edges: %s" % (n, r["kind"], len(r["edges"]), _counts(r["counts"])))
    for err in r["errors"]:
        print("  error   %s" % err)
    for e in r["edges"]:
        arrow = "-.->" if e["dashed"] else "-->"
        edge = ("%s %s %s" % (e["from"], arrow, e["to"]))[:40]
        bad = [c for c in e["cites"] if c["status"] != "correct"]
        if bad:
            c = bad[0]
            note = "%s: %s" % (c["text"], c["detail"])
        elif e["cites"]:
            note = ", ".join("%s:%s" % (c["file"], c["text"].rpartition(":")[2]) for c in e["cites"][:2])
        else:
            note = "(no file:line on the edge label)" if e["status"] == "uncited" else "(dashed, uncited)"
        print("  %-4s %-14s %-40s %s" % (e["id"], e["status"], edge, note[:150]))
