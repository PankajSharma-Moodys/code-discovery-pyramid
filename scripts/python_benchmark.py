#!/usr/bin/env python3
"""Python extraction benchmark: CDP's index against the interpreter's own answers.

    python scripts/python_benchmark.py REPO [--trace FILE ...] [--truth FILE]
        [--misses N] [--min-defs 97 --min-calls 85 --min-precision 95 ...]

Ground truth comes from `scripts/python_truth.py` (ast + real imports: defs, call
and reference sites, env reads) and optionally `scripts/python_trace.py`
(`sys.monitoring`: calls that really happened, including `obj.method()`).
Compared with the deterministic CDP phases run on REPO:

  defs        every function/class/class attribute/constant fqn, against `defines`;
              also: module-level functions typed `method`, defs without `end_line`
  calls       static truth sites (file, line, target) against `used_by`
  precision   each indexed .py site: confirmed by truth, contradicted by static
              truth, phantom (no such name on those lines), or unverified
  traced      runtime call sites against `used_by`, by the syntactic form of the call
  config      env reads (os.environ[...] / .get / os.getenv / `environ` / via
              constants) against `config_read` edges

Sites whose line cannot be cited (cdp.anchor) are not index facts by design and
are left out of the denominator, counted separately. Exit 1 below a --min-*.
"""

from __future__ import annotations

import argparse
import ast
import json
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SPAN = 4  # cdp.anchor.MAX_SPAN
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(HERE))

from java_benchmark import as_git_repo, pct  # noqa: E402


def run_truth(repo: Path, pkgs, paths=()) -> list:
    cmd = [sys.executable, "-I", str(HERE / "python_truth.py"), str(repo)]
    for p in pkgs:
        cmd += ["--pkg", p]
    for p in paths:
        cmd += ["--path", str(p)]
    res = subprocess.run(cmd, capture_output=True, text=True, check=False)
    rows = [json.loads(line) for line in res.stdout.splitlines() if line.startswith("{")]
    if not rows:
        sys.exit("python truth produced nothing:\n" + res.stderr[-2000:])
    return rows


class Sites:
    """`used_by` indexed by (file, target) -> anchor start lines."""

    def __init__(self, xref: dict) -> None:
        self.by = defaultdict(list)
        self.all = []
        for fqn, sites in xref["used_by"].items():
            for s in sites:
                self.by[(s["file"], fqn)].append(s["anchor"]["line"])
                self.all.append((s["file"], s["anchor"]["line"], fqn))

    def hit(self, f: str, line: int, target: str, end=None) -> bool:
        end = line if end is None else end
        return any(line - SPAN < L <= end for L in self.by.get((f, target), ()))


def measure_defs(p, truth, show: int) -> dict:
    t_defs: dict = {}
    for r in truth:
        if r["t"] == "def":
            t_defs.setdefault(r["fqn"], r)            # a conditional redefinition is one symbol: the first
    idx = {}
    for d in p.extraction["defines"]:
        idx.setdefault(d["fqn"], d)
    hit = [k for k in t_defs if k in idx]
    out = {"defs": (len(hit), len(t_defs), pct(len(hit), len(t_defs)))}
    per = defaultdict(lambda: [0, 0])
    for k, r in t_defs.items():
        per[r["kind"]][1] += 1
        per[r["kind"]][0] += k in idx
    out["defs_by_kind"] = {k: "%d/%d (%.0f%%)" % (a, b, pct(a, b)) for k, (a, b) in sorted(per.items())}
    fn_ok = sum(1 for k, r in t_defs.items() if k in idx and r["kind"] == "function"
                and idx[k]["kind"] == "function")
    fn_all = sum(1 for r in t_defs.values() if r["kind"] == "function")
    out["module_fn_kind"] = (fn_ok, fn_all, pct(fn_ok, fn_all))
    ended = sum(1 for k in hit if t_defs[k]["kind"] in ("function", "method", "class") and idx[k].get("end_line"))
    ended_all = sum(1 for k in hit if t_defs[k]["kind"] in ("function", "method", "class"))
    out["end_line"] = (ended, ended_all, pct(ended, ended_all))
    exact = sum(1 for k in hit if t_defs[k]["kind"] in ("function", "method", "class")
                and idx[k].get("end_line") == t_defs[k]["end_line"])
    out["end_line_exact"] = (exact, ended_all, pct(exact, ended_all))
    out["defs_missed_sample"] = ["%s:%d %s [%s]" % (t_defs[k]["file"], t_defs[k]["line"], k, t_defs[k]["kind"])
                                 for k in sorted(set(t_defs) - set(idx))[:show]]
    return out


def citable_fn(repo: Path):
    from cdp.anchor import build_anchor
    cache: dict = {}

    def citable(f: str, line: int) -> bool:
        if f not in cache:
            cache[f] = (repo / f).read_text(errors="replace").splitlines()
        return build_anchor(f, cache[f], line - 1) is not None
    return citable


def callee_forms(repo: Path):
    """(file, line range, name) -> syntactic form of the call at that place."""
    trees: dict = {}

    def form(f: str, line: int, end: int, name: str) -> str:
        if f not in trees:
            try:
                tree = ast.parse((repo / f).read_text(errors="replace"))
            except SyntaxError:
                tree = None
            calls = []
            for n in ast.walk(tree) if tree else ():
                if isinstance(n, ast.Call):
                    calls.append(n)
            trees[f] = calls
        short = name.rsplit("#", 1)[-1]
        owner_name = name.split("#")[0].rsplit(".", 1)[-1]
        best = "unknown"
        for n in trees[f]:
            if not (n.lineno <= end and (n.end_lineno or n.lineno) >= line):
                continue
            fn = n.func
            cal = fn.id if isinstance(fn, ast.Name) else fn.attr if isinstance(fn, ast.Attribute) else None
            if cal is None or (cal != short and not (short == "__init__" and cal == owner_name)
                               and cal != owner_name):
                continue
            if isinstance(fn, ast.Name):
                return "bare"
            v = fn.value
            if isinstance(v, ast.Call) and isinstance(v.func, ast.Name) and v.func.id == "super":
                return "super"
            if isinstance(v, ast.Name):
                best = "self/cls" if v.id in ("self", "cls") else "x.m (local/param/module)"
            elif isinstance(v, ast.Attribute):
                best = "self.a.m" if isinstance(v.value, ast.Name) and v.value.id == "self" else "a.b.m (chain)"
            else:
                best = "expr.m (call/subscript)"
        return best
    return form


def measure_calls(p, repo: Path, truth, traces, show: int) -> dict:
    citable = citable_fn(repo)
    sites = Sites(p.xref)
    out: dict = {}
    t_calls, uncitable = {}, 0
    for r in truth:
        if r["t"] == "call":
            if not citable(r["file"], r["line"]):
                uncitable += 1
                continue
            t_calls[(r["file"], r["line"], r["target"], r["how"])] = r
    out["calls_uncitable_excluded"] = uncitable
    chit = [k for k in t_calls if sites.hit(k[0], k[1], k[2])]
    out["calls"] = (len(chit), len(t_calls), pct(len(chit), len(t_calls)))
    per = defaultdict(lambda: [0, 0])
    for k in t_calls:
        per[k[3]][1] += 1
        per[k[3]][0] += sites.hit(k[0], k[1], k[2])
    out["calls_by_how"] = {h: "%d/%d (%.0f%%)" % (a, b, pct(a, b)) for h, (a, b) in sorted(per.items())}
    # callable subset (everything but constants/attrs): the call-graph part
    fn_keys = [k for k in t_calls if k[3] not in ("const", "attr")]
    fh = [k for k in fn_keys if sites.hit(k[0], k[1], k[2])]
    out["calls_functions"] = (len(fh), len(fn_keys), pct(len(fh), len(fn_keys)))
    out["calls_missed_sample"] = ["%s:%d %s [%s]" % k for k in sorted(k for k in t_calls if not sites.hit(k[0], k[1], k[2]))[:show]]

    # ---- precision
    static_at = defaultdict(lambda: defaultdict(set))   # (file, line) -> name -> targets
    for (f, line, tgt, how) in t_calls:
        pass
    def site_name(fqn: str) -> str:
        owner, _, member = fqn.partition("#")
        name = member.split(".")[-1] if member else owner.rsplit(".", 1)[-1]
        return owner.rsplit(".", 1)[-1] if name == "__init__" else name

    for r in truth:
        if r["t"] == "call":
            name = site_name(r["target"])
            for d in range(SPAN):
                static_at[(r["file"], r["line"] - d)][name].add(r["target"])
    trace_at = defaultdict(set)
    for tr in traces:
        for L in range(tr["line"] - SPAN, (tr["end"] or tr["line"]) + 1):
            trace_at[(tr["file"], L)].add(tr["target"])
    text_cache: dict = {}

    def name_present(f: str, line: int, name: str) -> bool:
        if f not in text_cache:
            text_cache[f] = (repo / f).read_text(errors="replace").splitlines()
        lines = text_cache[f]
        window = " ".join(lines[max(0, line - 1): line - 1 + SPAN])
        return name in window

    conf = bad = unver = 0
    bad_rows, unver_rows = [], []
    for (f, line, fqn) in sorted(set(sites.all)):
        if not f.endswith(".py"):
            continue
        name = site_name(fqn)                          # `Class(...)` is written with the class name
        is_class = fqn.endswith("#__init__") or "#" not in fqn and name[:1].isupper() and not name.isupper()
        if name.startswith("__") and name.endswith("__"):
            unver += 1                                 # `obj(...)` / `with obj:` name nothing
            continue
        if fqn in static_at.get((f, line), {}).get(name, ()) or fqn in trace_at.get((f, line), ()):
            conf += 1
            continue
        others = static_at.get((f, line), {}).get(name)
        if is_class and others and any(t == fqn or t.startswith(fqn.split("#")[0] + "#__init__") or t == fqn.split("#")[0]
                                       for t in others):
            conf += 1                                  # a class and its constructor are one site
            continue
        if others:
            bad += 1
            bad_rows.append("%s:%d %s (truth: %s)" % (f, line, fqn, ",".join(sorted(others))))
        elif not name_present(f, line, name) and not is_class:
            bad += 1
            bad_rows.append("%s:%d %s (no such name)" % (f, line, fqn))
        else:
            unver += 1
            unver_rows.append("%s:%d %s" % (f, line, fqn))
    out["calls_precision"] = (conf, conf + bad, pct(conf, conf + bad))
    out["indexed_sites_unverified"] = unver
    out["calls_extra_sample"] = bad_rows[:show]
    out["calls_unverified_sample"] = unver_rows[:show]

    # ---- traced
    if traces:
        form = callee_forms(repo)
        from cdp.pytypes import PyIndex
        pyidx = PyIndex(p.extraction, p.xref["symbols"], [f["path"] for f in p.inventory["files"]])

        def bases_of(target: str):
            """The same method on each base class: `base.m()` that dispatched to an override
            (static dispatch names the base) or `Class(...)` for a class without `__init__`."""
            owner, _, member = target.partition("#")
            out = [owner] if member == "__init__" else []
            if member:
                out += [b + "#" + member for b in pyidx.hierarchy(owner)[1:]]
            return out
        per_form = defaultdict(lambda: [0, 0])
        missed = []
        total = ok = 0
        for tr in traces:
            if not citable(tr["file"], tr["line"]):
                continue
            end = tr["end"] or tr["line"]
            total += 1
            fm = form(tr["file"], tr["line"], end, tr["target"])
            per_form[fm][1] += 1
            if sites.hit(tr["file"], tr["line"], tr["target"], end) or any(
                    sites.hit(tr["file"], tr["line"], a, end) for a in bases_of(tr["target"])):
                ok += 1
                per_form[fm][0] += 1
            else:
                missed.append("%s:%d-%d %s [%s]" % (tr["file"], tr["line"], end, tr["target"], fm))
        out["traced"] = (ok, total, pct(ok, total))
        out["traced_by_form"] = {k: "%d/%d (%.0f%%)" % (a, b, pct(a, b)) for k, (a, b) in sorted(per_form.items())}
        out["traced_missed_sample"] = missed[:show]
    return out


def measure_config(p, truth: list, show: int) -> dict:
    from cdp.resolve import config_reads

    reads = [r for r in config_reads(p.extraction, p.xref["constants"]) if r["file"].endswith(".py")]
    by_file = defaultdict(list)
    for r in reads:
        by_file[r["file"]].append(r)
    cfg = [r for r in truth if r["t"] == "cfg"]
    found = keyed = 0
    missed = []
    for r in cfg:
        want = r["key"] or "(dynamic)"
        near = [x for x in by_file.get(r["file"], ()) if 0 <= r["line"] - x["anchor"]["line"] < SPAN]
        if near:
            found += 1
            if any(x["key"] == want for x in near):
                keyed += 1
                continue
        missed.append("%s:%d %s (index: %s)" % (r["file"], r["line"], want, ",".join(x["key"] for x in near) or "none"))
    truth_at = [(r["file"], r["line"]) for r in cfg]
    extra = [x for x in reads if not any(f == x["file"] and 0 <= L - x["anchor"]["line"] < SPAN for f, L in truth_at)]
    return {
        "config": (keyed, len(cfg), pct(keyed, len(cfg))),
        "config_sites": (found, len(cfg), pct(found, len(cfg))),
        "config_precision": (len(reads) - len(extra), len(reads), pct(len(reads) - len(extra), len(reads))),
        "config_missed_sample": missed[:show],
        "config_extra_sample": ["%s:%d %s" % (x["file"], x["anchor"]["line"], x["key"]) for x in extra[:show]],
    }


def tables(p, show: int) -> dict:
    rows = sorted({(e["file"], e["anchor"]["line"], e["target"], e["channel"]) for e in p.extraction["io_edges"]
                   if e["file"].endswith(".py") and e["target"].startswith("table:")})
    return {"tables_listed": len(rows), "tables_sample": ["%s:%d %s %s" % r for r in rows[:show]]}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("repo", type=Path)
    ap.add_argument("--pkg", action="append", default=[])
    ap.add_argument("--path", action="append", default=[], help="extra sys.path entries for the truth run")
    ap.add_argument("--truth", type=Path)
    ap.add_argument("--trace", type=Path, action="append", default=[])
    ap.add_argument("--misses", type=int, default=0)
    ap.add_argument("--min-defs", type=float, default=0)
    ap.add_argument("--min-calls", type=float, default=0)
    ap.add_argument("--min-precision", type=float, default=0)
    ap.add_argument("--min-config", type=float, default=0)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    repo = as_git_repo(a.repo)
    if a.truth:
        truth = [json.loads(line) for line in a.truth.read_text().splitlines() if line.startswith("{")]
    else:
        truth = run_truth(a.repo, a.pkg, a.path)
    traces = [json.loads(line) for t in a.trace for line in t.read_text().splitlines() if line.startswith("{")]
    from helpers import Pipeline
    p = Pipeline(repo)
    out: dict = {}
    out.update(measure_defs(p, truth, a.misses))
    out.update(measure_calls(p, repo, truth, traces, a.misses))
    out.update(measure_config(p, truth, a.misses))
    out.update(tables(p, a.misses))
    out["modules_not_importable"] = sum(1 for r in truth if r["t"] == "skip")
    if a.json:
        print(json.dumps(out, indent=1, sort_keys=True))
    else:
        for k in ("defs", "module_fn_kind", "end_line", "end_line_exact", "calls", "calls_functions",
                  "calls_precision", "traced", "config_sites", "config", "config_precision"):
            if k in out:
                n, d, pc = out[k]
                print("%-18s %5d/%-5d %6.1f%%" % (k, n, d, pc))
        for k in ("defs_by_kind", "calls_by_how", "traced_by_form"):
            if k in out:
                print(k + ":", out[k])
        print("uncitable call sites excluded:", out["calls_uncitable_excluded"],
              "| indexed sites unverified:", out["indexed_sites_unverified"],
              "| modules not importable:", out["modules_not_importable"],
              "| table edges:", out["tables_listed"])
        if a.misses:
            for k in ("defs_missed_sample", "calls_missed_sample", "calls_extra_sample",
                      "calls_unverified_sample", "traced_missed_sample", "config_missed_sample",
                      "config_extra_sample", "tables_sample"):
                if k in out:
                    print("\n" + k)
                    for line in out[k]:
                        print("  " + line)
    bad = [n for n, floor, key in (("defs", a.min_defs, "defs"), ("calls", a.min_calls, "calls"),
                                   ("precision", a.min_precision, "calls_precision"),
                                   ("config", a.min_config, "config")) if out[key][2] < floor]
    for n in bad:
        print("BELOW TARGET: %s" % n, file=sys.stderr)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
