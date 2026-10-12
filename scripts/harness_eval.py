#!/usr/bin/env python3
"""Measure whether a Claude Code session reaches for the CDP index first.

For each install mode a fresh copy of the target repo is installed (`run.py install ...`),
scanned into CDP_HOME, and each question is put to a real headless session:

    claude -p "<q>" --strict-mcp-config --mcp-config .mcp.json --allowedTools ... \
        --output-format stream-json --verbose        (cwd = the copy)

`tool_use` events are parsed per question. One real model session per (mode, question, repeat):
mind the count (`--dry-run` prints it).

    (a mode whose flags include --no-cli-allow runs sessions without `mcp__cdp__*` on --allowedTools,
    so an MCP call must be permitted by the installed settings, as in an interactive session.)

    python3 scripts/harness_eval.py --source /tmp/hx/base-src --work /tmp/hx/work \
        --cdp-home /tmp/hx/home --mode default:--harness --mode strict:"--harness --strict" \
        --n 2 --jobs 4 --out /tmp/hx/out.json

`--questions FILE.json` takes `{"id": "question text"}` (default: eight sql-pool questions).
`--parse FILE` parses one saved stream-json transcript and prints its row (no session).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent

EMULATE_TRUST = "--emulate-trust"  # mode flag: see `emulate_trust`
NO_MCP_ALLOW = "--no-cli-allow"  # mode flag: do not pass mcp__cdp__* on the command line (permission friction)
BUILTIN_ALLOWED = "Read,Grep,Glob,Bash(grep:*),Bash(find:*),Bash(ls:*)"
ALLOWED = "mcp__cdp__*," + BUILTIN_ALLOWED

DEFAULT_QUESTIONS: Dict[str, str] = {
    "callers": "Who calls ReservationService.makeReservations in this repo?",
    "impact": "What breaks if I change the ServerService class?",
    "tables": "Which database tables does the POST /unified-store/sql-pool/v1/reservations route touch?",
    "config": "Where is the SQL_POOL_SCHEMA config key read?",
    "endpoints": "What HTTP endpoints does this service expose?",
    "eventbus": "How does the EventBus flow work in sql-pool-service?",
    "jobs": "Which Quartz jobs exist in this repo and when does each run?",
    "constant": "Where is the string constant \"read-only\" used?",
}

#: Tools that explore the repo. Everything else (ToolSearch, TodoWrite, ...) is bookkeeping.
EXPLORE = ("Read", "Grep", "Glob", "Bash")
_BOOKKEEPING_BASH = re.compile(r"^\s*(echo|pwd|cd)\b")


def is_cdp(name: str) -> bool:
    return name.startswith("mcp__") and "cdp" in name


def is_query(name: str) -> bool:
    return name.startswith("mcp__") and name.endswith("cdp_query")


def parse_stream(lines) -> Dict:
    """One row from a stream-json transcript."""
    calls: List[Dict] = []
    result: Dict = {}
    denied = 0
    by_id: Dict[str, Dict] = {}
    for line in lines:
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        kind = ev.get("type")
        if kind == "assistant":
            for block in (ev.get("message") or {}).get("content") or []:
                if block.get("type") == "tool_use":
                    inp = block.get("input") or {}
                    call = {"tool": block["name"], "input": inp,
                            "kind": inp.get("kind") if is_query(block["name"]) else None}
                    calls.append(call)
                    by_id[block.get("id")] = call
        elif kind == "user":
            content = (ev.get("message") or {}).get("content")
            for block in content if isinstance(content, list) else []:
                if block.get("type") == "tool_result" and by_id.get(block.get("tool_use_id")):
                    text = json.dumps(block.get("content"))
                    if block.get("is_error") and ("hook" in text.lower() or "CDP" in text):
                        denied += 1
                        by_id[block["tool_use_id"]]["denied"] = True
        elif kind == "result":
            result = ev
    explore = [c for c in calls if (c["tool"] in EXPLORE and not _BOOKKEEPING_BASH.match(str(c["input"].get("command", ""))))
               or is_cdp(c["tool"])]
    first_explore = explore[0]["tool"] if explore else None
    before = 0
    for c in calls:
        if is_query(c["tool"]):
            break
        if c["tool"] in ("Grep", "Read", "Glob") or (c["tool"] == "Bash" and not _BOOKKEEPING_BASH.match(str(c["input"].get("command", "")))):
            before += 1
    return {
        "calls": len(calls),
        "first_tool": calls[0]["tool"].replace("mcp__cdp__", "cdp:") if calls else None,
        "first_explore": first_explore.replace("mcp__cdp__", "cdp:") if first_explore else None,
        "cdp_first": bool(first_explore and is_cdp(first_explore)),
        "used_cdp": any(is_query(c["tool"]) for c in calls),
        "before_first_cdp": before,
        "kinds": [c["kind"] for c in calls if c["kind"]],
        "denied": denied,
        "non_cdp_calls": sum(1 for c in calls if not is_cdp(c["tool"]) and c["tool"] in EXPLORE),
        "sequence": ["%s(%s)" % (c["tool"].replace("mcp__cdp__", "cdp:"),
                                 str(c["input"].get("kind") or c["input"].get("pattern") or c["input"].get("command")
                                     or c["input"].get("file_path") or "")[:50]) for c in calls],
        "answer": str(result.get("result") or "")[:1500],
        "cost_usd": result.get("total_cost_usd"),
        "is_error": bool(result.get("is_error")),
    }


def run_cli(args: List[str], env: Dict[str, str], cwd: Path = ROOT, check: bool = True) -> str:
    proc = subprocess.run([sys.executable, str(ROOT / "run.py")] + args, cwd=str(cwd), env=env,
                          capture_output=True, text=True)
    if check and proc.returncode != 0:
        raise SystemExit("run.py %s failed: %s" % (" ".join(args), (proc.stderr or proc.stdout)[-600:]))
    return proc.stdout


def emulate_trust(target: Path) -> None:
    """Headless `claude -p` ignores a project's shared `.claude/settings.json` `permissions.allow` until the
    folder's trust dialog was accepted (measured: the same rule works at once from `settings.local.json`, and
    from `settings.json` in a trusted folder). A harness copy is never trusted, so copy the installed rule to
    `settings.local.json` to get what an interactive, trusted session gets."""
    path = target / ".claude" / "settings.json"
    perms = json.loads(path.read_text()).get("permissions") if path.exists() else None
    if perms:
        (target / ".claude" / "settings.local.json").write_text(json.dumps({"permissions": perms}, indent=2))


def prepare(source: Path, work: Path, label: str, flags: str, env: Dict[str, str]) -> Path:
    """Fresh copy of `source`, installed with `flags`, scanned into CDP_HOME."""
    target = work / label / source.name
    if target.exists():
        shutil.rmtree(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, target, symlinks=True)
    run_cli(["install", str(target)] + [f for f in shlex.split(flags) if f != EMULATE_TRUST], env)
    # Commit the install so the index (pinned to HEAD) is fresh and hooks do not stand down
    # for a dirty tree, then scan.
    subprocess.run(["git", "add", "-A"], cwd=str(target), capture_output=True)
    subprocess.run(["git", "-c", "user.email=h@h", "-c", "user.name=h", "commit", "-qm", "install", "--allow-empty"],
                   cwd=str(target), capture_output=True)
    run_cli(["scan", "--repo", str(target)], env)
    if EMULATE_TRUST in flags.split():
        emulate_trust(target)
    return target


def session(target: Path, question: str, env: Dict[str, str], model: Optional[str], timeout: int,
            allowed: str = ALLOWED) -> List[str]:
    cmd = ["claude", "-p", question, "--strict-mcp-config", "--mcp-config", ".mcp.json",
           "--allowedTools", allowed, "--output-format", "stream-json", "--verbose"]
    if model:
        cmd += ["--model", model]
    try:
        proc = subprocess.run(cmd, cwd=str(target), env=env, capture_output=True, text=True, timeout=timeout)
        return proc.stdout.splitlines()
    except subprocess.TimeoutExpired as exc:
        return (exc.stdout or b"").decode().splitlines() if isinstance(exc.stdout, bytes) else (exc.stdout or "").splitlines()


def table(rows: List[Dict], modes: List[str], questions: List[str]) -> str:
    out = ["| mode | n | cdp-first | used cdp | mean calls | mean grep/read before 1st cdp_query | mean grep/read total | denials |",
           "|---|---|---|---|---|---|---|---|"]
    for mode in modes:
        rs = [r for r in rows if r["mode"] == mode]
        if not rs:
            continue
        n = len(rs)
        out.append("| %s | %d | %d/%d | %d/%d | %.1f | %.1f | %.1f | %d |" % (
            mode, n, sum(r["cdp_first"] for r in rs), n, sum(r["used_cdp"] for r in rs), n,
            sum(r["calls"] for r in rs) / n, sum(r["before_first_cdp"] for r in rs) / n,
            sum(r["non_cdp_calls"] for r in rs) / n, sum(r["denied"] for r in rs)))
    out += ["", "| question | " + " | ".join(modes) + " |", "|---|" + "---|" * len(modes)]
    for q in questions:
        cells = []
        for mode in modes:
            rs = [r for r in rows if r["mode"] == mode and r["question"] == q]
            cells.append("; ".join("%s/%d calls/%d pre%s" % (r["first_explore"] or "-", r["calls"], r["before_first_cdp"],
                                                              "/" + ",".join(r["kinds"][:3]) if r["kinds"] else "")
                                   for r in rs) or "-")
        out.append("| %s | %s |" % (q, " | ".join(cells)))
    return "\n".join(out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", type=Path, help="pristine git copy of the target repo")
    ap.add_argument("--work", type=Path, help="scratch directory for per-mode copies (outside any repo)")
    ap.add_argument("--cdp-home", type=Path, help="CDP_HOME to scan into (never ~/.cdp)")
    ap.add_argument("--mode", action="append", default=[], metavar="LABEL:FLAGS",
                    help="install mode, e.g. default:--harness or strict:'--harness --strict';")
    ap.add_argument("--questions", type=Path, help="JSON {id: question}; default: the eight sql-pool questions")
    ap.add_argument("--only", help="comma-separated question ids")
    ap.add_argument("--n", type=int, default=1, help="repeats per (mode, question)")
    ap.add_argument("--jobs", type=int, default=1, help="concurrent sessions")
    ap.add_argument("--model")
    ap.add_argument("--timeout", type=int, default=420)
    ap.add_argument("--out", type=Path, help="JSON results file")
    ap.add_argument("--reuse", action="store_true", help="skip prepare; reuse existing copies under --work")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--parse", type=Path, help="parse one saved stream-json file and print its row")
    args = ap.parse_args(argv)

    if args.parse:
        print(json.dumps(parse_stream(args.parse.read_text().splitlines()), indent=2))
        return 0
    if not (args.source and args.work and args.cdp_home and args.mode):
        ap.error("--source, --work, --cdp-home and at least one --mode are required")
    if args.cdp_home.resolve() == (Path.home() / ".cdp").resolve():
        ap.error("refusing to use ~/.cdp")
    questions = json.loads(args.questions.read_text()) if args.questions else dict(DEFAULT_QUESTIONS)
    if args.only:
        questions = {k: v for k, v in questions.items() if k in args.only.split(",")}
    modes = [m.partition(":")[0:3:2] for m in args.mode]
    noallow = {label for label, flags in modes if NO_MCP_ALLOW in flags.split()}
    modes = [(label, " ".join(f for f in flags.split() if f != NO_MCP_ALLOW)) for label, flags in modes]  # EMULATE_TRUST stays: prepare() reads it
    total = len(modes) * len(questions) * args.n
    print("%d real sessions" % total, file=sys.stderr)
    if args.dry_run:
        return 0

    env = dict(os.environ, CDP_HOME=str(args.cdp_home))
    env.pop("CDP_LEAF_SESSION", None)
    targets = {}
    for label, flags in modes:
        targets[label] = (args.work / label / args.source.name) if args.reuse else prepare(args.source, args.work, label, flags, env)

    jobs = [(label, qid, q, i) for label, _ in modes for qid, q in questions.items() for i in range(args.n)]

    def one(job):
        label, qid, q, i = job
        lines = session(targets[label], q, env, args.model, args.timeout,
                       BUILTIN_ALLOWED if label in noallow else ALLOWED)
        (args.work / label).mkdir(parents=True, exist_ok=True)
        (args.work / label / ("%s.%d.jsonl" % (qid, i))).write_text("\n".join(lines))
        row = parse_stream(lines)
        row.update(mode=label, qid=qid, question=q, rep=i)
        print("%-10s %-9s #%d first=%-14s calls=%2d pre=%d kinds=%s" % (
            label, qid, i, row["first_explore"], row["calls"], row["before_first_cdp"], ",".join(row["kinds"][:4])),
            file=sys.stderr, flush=True)
        return row

    with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
        rows = list(pool.map(one, jobs))
    if args.out:
        args.out.write_text(json.dumps(rows, indent=2))
    print(table(rows, [m for m, _ in modes], list(questions.values())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
