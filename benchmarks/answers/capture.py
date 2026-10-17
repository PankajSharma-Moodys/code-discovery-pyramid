"""Run a repo's query corpus against one code tree + state dir and save every answer.

    python3 benchmarks/answers/capture.py --repo workflow-service --side old \
        --code ~/.cdp-phase1/oldcode --state-dir ~/.cdp-phase1/old

Each CLI query runs twice (`--json` and the default text rendering) as its own
process, so wall time and peak RSS (`os.wait4`) are per query. The MCP subset runs
in one process through `mcp_server.tools` (`mcp_run.py`). Output goes to
`~/.cdp-phase1/answers/<side>/<repo>/` -- never inside this git repo.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
from raw import PHASE, repos  # noqa: E402


def run(argv, cwd, env=None):
    """(rc, stdout, stderr, wall_s, peak_rss_bytes) for one child process."""
    t0 = time.perf_counter()
    p = subprocess.Popen(argv, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    # communicate() reaps the child itself, so read the pipes on threads and reap with wait4.
    import threading
    bufs = {}

    def drain(name, stream):
        bufs[name] = stream.read()
    ts = [threading.Thread(target=drain, args=(n, s)) for n, s in (("out", p.stdout), ("err", p.stderr))]
    for t in ts:
        t.start()
    _, status, ru = os.wait4(p.pid, 0)
    for t in ts:
        t.join()
    p.returncode = os.waitstatus_to_exitcode(status)
    wall = time.perf_counter() - t0
    rss = ru.ru_maxrss if sys.platform == "darwin" else ru.ru_maxrss * 1024
    return p.returncode, bufs["out"].decode("utf-8", "replace"), bufs["err"].decode("utf-8", "replace"), wall, rss


def tree_hashes(root):
    out = {}
    for dp, _, fns in os.walk(root):
        for fn in fns:
            p = os.path.join(dp, fn)
            with open(p, "rb") as fh:
                out[os.path.relpath(p, root)] = hashlib.sha256(fh.read()).hexdigest()
    return dict(sorted(out.items()))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--side", required=True, help="old | new (answers subdirectory)")
    ap.add_argument("--code", required=True, help="checkout whose `cdp` package runs")
    ap.add_argument("--state-dir", required=True)
    ap.add_argument("--only", default="", help="comma list: cli,mcp,commands (default all)")
    a = ap.parse_args()
    code, state = os.path.expanduser(a.code), os.path.expanduser(a.state_dir)
    meta = repos()[a.repo]
    with open(os.path.join(PHASE, "queries", a.repo + ".json")) as fh:
        corpus = json.load(fh)
    out = os.path.join(PHASE, "answers", a.side, a.repo)
    os.makedirs(os.path.join(out, "cli"), exist_ok=True)
    only = set(filter(None, a.only.split(","))) or {"cli", "mcp", "commands"}
    timings = []
    base = [sys.executable, "-m", "cdp.cli"]
    if "cli" in only:
        for q in corpus["cli"]:
            for fmt, extra in (("json", ["--json"]), ("txt", [])):
                argv = base + ["query"] + q["argv"] + ["--repo", meta["path"], "--state-dir", state] + extra
                rc, so, se, wall, rss = run(argv, code)
                with open(os.path.join(out, "cli", "%s.%s" % (q["id"], fmt)), "w") as fh:
                    fh.write(so)
                timings.append({"id": q["id"], "kind": q["argv"][0], "fmt": fmt, "rc": rc, "wall_s": round(wall, 4),
                                "rss": rss, "stderr": se[-2000:]})
    if "commands" in only:
        os.makedirs(os.path.join(out, "cmd"), exist_ok=True)
        for c in corpus["commands"]:
            if c.get("outdir"):
                shutil.rmtree(os.path.join(out, c["outdir"]), ignore_errors=True)
            argv = base + [x.replace("{OUT}", out) for x in c["argv"]] + ["--repo", meta["path"], "--state-dir", state]
            rc, so, se, wall, rss = run(argv, code)
            rec = {"id": c["id"], "kind": "cmd", "fmt": "txt", "rc": rc, "wall_s": round(wall, 4), "rss": rss,
                   "stderr": se[-2000:]}
            if c.get("outdir") and os.path.isdir(os.path.join(out, c["outdir"])):
                rec["files"] = tree_hashes(os.path.join(out, c["outdir"]))
            with open(os.path.join(out, "cmd", c["id"] + ".txt"), "w") as fh:
                fh.write(so)
            with open(os.path.join(out, "cmd", c["id"] + ".meta.json"), "w") as fh:
                json.dump(rec, fh, indent=1, sort_keys=True)
            timings.append(rec)
    if "mcp" in only:
        env = dict(os.environ, CDP_HOME=state, PYTHONPATH=code)
        argv = [sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "mcp_run.py"),
                os.path.join(PHASE, "queries", a.repo + ".json"), meta["path"], os.path.join(out, "mcp")]
        rc, so, se, wall, rss = run(argv, code, env)
        if rc:
            print(se[-3000:], file=sys.stderr)
        for line in so.splitlines():
            if line.startswith("{"):
                timings.append(json.loads(line))
        timings.append({"id": "mcp-process", "kind": "mcp", "fmt": "proc", "rc": rc, "wall_s": round(wall, 4), "rss": rss})
    name = "timings.%s.jsonl" % "-".join(sorted(only))
    with open(os.path.join(out, name), "w") as fh:
        for t in timings:
            fh.write(json.dumps(t, sort_keys=True) + "\n")
    bad = [t["id"] + "." + t["fmt"] for t in timings if t.get("rc")]
    print("%s %s: %d runs, %d nonzero rc %s" % (a.side, a.repo, len(timings), len(bad), bad[:10]))


if __name__ == "__main__":
    main()
