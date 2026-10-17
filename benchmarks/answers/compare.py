"""Old vs new: normalized answer diff, grounding pass rates and perf deltas.

    python3 benchmarks/answers/compare.py [--repo NAME ...] [--perf-only] [--show N]

Ignored when diffing: only timing and snapshot-id fields (`IGNORE_KEYS`, `TIME_RE`);
every other difference is listed. Perf: per-kind p50/p95 wall time and peak RSS from
capture.py's timings files, plus scan time / RSS (`old|new/scan_<repo>.time`) and DB size.
With only the old side captured it prints the baseline.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(__file__))
from raw import PHASE, repos  # noqa: E402

IGNORE_KEYS = {"generated_at", "snapshot_id", "wall_ms", "elapsed_s", "took_ms"}
TIME_RE = re.compile(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?(?:Z|[+-]\d\d:\d\d)?")
SIDE_RE = re.compile(r"/answers/[^/\s]+/")     # the capture's own output dir, named after its side


def unside(s):
    return SIDE_RE.sub("/answers/<side>/", TIME_RE.sub("<time>", s))


def scrub(obj):
    if isinstance(obj, dict):
        return {k: scrub(v) for k, v in obj.items() if k not in IGNORE_KEYS}
    if isinstance(obj, list):
        return [scrub(v) for v in obj]
    if isinstance(obj, str):
        return unside(obj)
    return obj


def jdiff(a, b, path="$", out=None, limit=20):
    out = [] if out is None else out
    if len(out) >= limit:
        return out
    if type(a) is not type(b):
        out.append("%s: %s -> %s" % (path, short(a), short(b)))
    elif isinstance(a, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a:
                out.append("%s.%s: added %s" % (path, k, short(b[k])))
            elif k not in b:
                out.append("%s.%s: removed %s" % (path, k, short(a[k])))
            else:
                jdiff(a[k], b[k], "%s.%s" % (path, k), out, limit)
        if list(a) != list(b) and set(a) == set(b):
            out.append("%s: key order differs" % path)
    elif isinstance(a, list):
        if len(a) != len(b):
            out.append("%s: len %d -> %d" % (path, len(a), len(b)))
        for i, (x, y) in enumerate(zip(a, b)):
            jdiff(x, y, "%s[%d]" % (path, i), out, limit)
    elif a != b:
        out.append("%s: %s -> %s" % (path, short(a), short(b)))
    return out


def short(v):
    s = json.dumps(v, sort_keys=True) if not isinstance(v, str) else repr(v)
    return s if len(s) < 120 else s[:117] + "..."


def tdiff(a, b, limit=10):
    a, b = unside(a).splitlines(), unside(b).splitlines()
    out = []
    for i in range(max(len(a), len(b))):
        x = a[i] if i < len(a) else "<eof>"
        y = b[i] if i < len(b) else "<eof>"
        if x != y:
            out.append("line %d: %r -> %r" % (i + 1, x[:140], y[:140]))
            if len(out) >= limit:
                break
    return out


def load_timings(side, repo):
    d = os.path.join(PHASE, "answers", side, repo)
    latest = {}
    if os.path.isdir(d):
        # A later partial capture (`--only mcp`) supersedes the same runs of an earlier one.
        files = [fn for fn in os.listdir(d) if fn.startswith("timings.") and fn.endswith(".jsonl")]
        for fn in sorted(files, key=lambda f: os.path.getmtime(os.path.join(d, f))):
            with open(os.path.join(d, fn)) as fh:
                for l in fh:
                    if l.strip():
                        t = json.loads(l)
                        latest[(t["id"], t["fmt"])] = t
    return list(latest.values())


def pct(xs, p):
    xs = sorted(xs)
    if not xs:
        return None
    return xs[min(len(xs) - 1, int(round(p / 100.0 * (len(xs) - 1))))]


def scan_time(side, repo):
    p = os.path.join(PHASE, side, "scan_%s.time" % repo)
    if not os.path.exists(p):
        return None, None
    txt = open(p).read()
    real = re.search(r"([\d.]+) real", txt)
    rss = re.search(r"(\d+)\s+maximum resident set size", txt)
    return (float(real.group(1)) if real else None), (int(rss.group(1)) if rss else None)


def db_size(side):
    p = os.path.join(PHASE, side, "index.db")
    tot = sum(os.path.getsize(p + s) for s in ("", "-wal") if os.path.exists(p + s))
    return tot or None


def perf(repo):
    print("\n## perf %s" % repo)
    for side in ("old", "new"):
        st, rss = scan_time(side, repo)
        if st is not None:
            print("scan %-3s  %.2fs  peak RSS %d MB" % (side, st, rss // 2**20))
    sides = {s: load_timings(s, repo) for s in ("old", "new")}
    kinds = sorted({(t["kind"], t["fmt"]) for rows in sides.values() for t in rows if t["fmt"] in ("json", "mcp")})
    print("%-22s %6s | %-27s | %-27s" % ("kind/fmt", "n", "old p50/p95 s  RSS p50 MB", "new p50/p95 s  RSS p50 MB"))
    for k, f in kinds:
        cells = []
        n = 0
        for side in ("old", "new"):
            rows = [t for t in sides[side] if t["kind"] == k and t["fmt"] == f]
            n = max(n, len(rows))
            if rows:
                w = [t["wall_s"] for t in rows]
                r = [t["rss"] for t in rows]
                cells.append("%6.3f/%6.3f  %8d" % (pct(w, 50), pct(w, 95), pct(r, 50) // 2**20))
            else:
                cells.append("-")
        print("%-22s %6d | %-27s | %-27s" % ("%s/%s" % (k, f), n, cells[0], cells[1]))


NEW = "new"


def diff_repo(repo, show):
    old, new = (os.path.join(PHASE, "answers", s, repo) for s in ("old", NEW))
    if not os.path.isdir(new):
        return None
    with open(os.path.join(PHASE, "queries", repo + ".json")) as fh:
        corpus = json.load(fh)
    diffs, same, missing = {}, 0, 0
    items = [("cli", "%s.%s" % (q["id"], f)) for q in corpus["cli"] for f in ("json", "txt")]
    items += [("mcp", c["id"] + ".json") for c in corpus["mcp"]]
    items += [("cmd", c["id"] + ".txt") for c in corpus["commands"]]
    for sub, fn in items:
        a, b = os.path.join(old, sub, fn), os.path.join(new, sub, fn)
        if not (os.path.exists(a) and os.path.exists(b)):
            missing += 1
            continue
        ta, tb = open(a).read(), open(b).read()
        if fn.endswith(".json"):
            try:
                d = jdiff(scrub(json.loads(ta)), scrub(json.loads(tb)))
            except ValueError:
                d = tdiff(ta, tb)
        else:
            d = tdiff(ta, tb)
        if d:
            diffs["%s/%s" % (sub, fn)] = d
        else:
            same += 1
    rcs = [{(t["id"], t["fmt"]): (t["rc"], t["rc"] and t.get("stderr")) for t in load_timings(s, repo)}
           for s in ("old", NEW)]
    for k in sorted(set(rcs[0]) & set(rcs[1])):
        if rcs[0][k] != rcs[1][k]:
            diffs["rc/%s.%s" % k] = ["exit code/stderr %r -> %r" % (rcs[0][k], rcs[1][k])]
    for c in corpus["commands"]:
        if not c.get("outdir"):
            continue
        ma, mb = (os.path.join(x, "cmd", c["id"] + ".meta.json") for x in (old, new))
        if os.path.exists(ma) and os.path.exists(mb):
            fa, fb = json.load(open(ma)).get("files", {}), json.load(open(mb)).get("files", {})
            bad = []
            for k in sorted(set(fa) | set(fb)):
                if fa.get(k) == fb.get(k):
                    continue
                pa, pb = (os.path.join(x, c["outdir"], k) for x in (old, new))
                # A file whose only difference is a timestamp or the capture's own path is equal.
                if fa.get(k) and fb.get(k) and os.path.exists(pa) and os.path.exists(pb) \
                        and unside(open(pa).read()) == unside(open(pb).read()):
                    continue
                bad.append(k)
            if bad:
                diffs["%s/files" % c["id"]] = ["file differs: %s" % k for k in bad]
            else:
                same += 1
    print("\n## diff %s: %d identical, %d differ, %d missing" % (repo, same, len(diffs), missing))
    for k, v in list(diffs.items())[:show]:
        print("  %s" % k)
        for line in v[:6]:
            print("      " + line)
    with open(os.path.join(new, "compare.json"), "w") as fh:
        json.dump({"identical": same, "missing": missing, "diffs": diffs}, fh, indent=1, sort_keys=True)
    return diffs


def grounding(repo):
    for side in ("old", "new"):
        p = os.path.join(PHASE, "answers", side, repo, "grounding.json")
        if os.path.exists(p):
            g = json.load(open(p))
            (sn, sp), (dn, dp) = g["source_total"], g["db_total"]
            print("grounding %-3s %s: source %d/%d (%.2f%%)  db %d/%d (%.2f%%)" % (
                side, repo, sp, sn, 100.0 * sp / max(sn, 1), dp, dn, 100.0 * dp / max(dn, 1)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", action="append")
    ap.add_argument("--perf-only", action="store_true")
    ap.add_argument("--show", type=int, default=40)
    ap.add_argument("--new", default="new", help="answers side to compare against old (e.g. a rerun)")
    a = ap.parse_args()
    global NEW
    NEW = a.new
    for side in ("old", "new"):
        s = db_size(side)
        if s:
            print("db %-3s %.1f MB (index.db + wal)" % (side, s / 1e6))
    for repo in a.repo or sorted(repos()):
        grounding(repo)
        if not a.perf_only:
            diff_repo(repo, a.show)
        perf(repo)


if __name__ == "__main__":
    main()
