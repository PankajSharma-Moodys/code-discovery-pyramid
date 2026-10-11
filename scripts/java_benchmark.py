#!/usr/bin/env python3
"""Java extraction benchmark: CDP's index against javac's own trees.

    python scripts/java_benchmark.py REPO [--stubs DIR] [--classpath CP]
        [--truth FILE] [--misses N] [--min-methods 99 --min-calls 90 ...]

Runs `scripts/JavaTruth.java` (needs `javac`/`java`; pass --truth to reuse its
output), runs the deterministic CDP phases on REPO, and compares:

  methods     (owner, name) of every named class's methods, constructors
              (`<init>`) and interface methods, against `defines` kind=method
  fields      (owner, name) of every field, against constant/field defines
  call sites  (file, line, declaring-owner#name) for every call, `new` and
              `X::m` that javac resolves into REPO, against `used_by`
  config      every System.getenv/getProperty/Long.getLong/... read (and
              `getenv().getOrDefault`), with the key javac can fold ("" = computed,
              expected as `(dynamic)`), against the `config_read` edges of .java files
  tables      (--tables-truth) Flyway DDL tables, see `measure_tables`

Exit status 1 when a --min-* threshold is missed. Misses are listed so a
failure is a to-do list, not a number.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
SPAN = 4  # cdp.anchor.MAX_SPAN
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))


def run_truth(repo: Path, stubs, classpath: str) -> list:
    cmd = ["java", str(HERE / "JavaTruth.java"), "--root", str(repo)]
    if stubs:
        cmd += ["--stubs", str(stubs)]
    if classpath:
        cmd += ["--classpath", classpath]
    res = subprocess.run(cmd, capture_output=True, text=True, check=False)
    rows = [json.loads(line) for line in res.stdout.splitlines() if line.startswith("{")]
    if not rows:
        sys.exit("javac truth produced nothing:\n" + res.stderr[-2000:])
    return rows


def as_git_repo(path: Path) -> Path:
    """The inventory reads `git ls-files`, so a plain directory (a fixture inside
    this checkout) is copied to a temporary committed repo first."""
    import shutil
    import tempfile
    if (path / ".git").exists():
        return path
    tmp = Path(tempfile.mkdtemp(prefix="java-bench-")) / path.name
    shutil.copytree(path, tmp)
    env = {"GIT_AUTHOR_NAME": "b", "GIT_AUTHOR_EMAIL": "b@x", "GIT_COMMITTER_NAME": "b",
           "GIT_COMMITTER_EMAIL": "b@x", "PATH": "/usr/bin:/bin:/usr/local/bin"}
    for args in (["init", "-q", "-b", "main"], ["add", "-A"], ["commit", "-q", "-m", "fixture"]):
        subprocess.run(["git", "-C", str(tmp)] + args, check=True, capture_output=True, env=env)
    return tmp


def pct(a: int, b: int) -> float:
    return 100.0 * a / b if b else 100.0


def measure(repo: Path, truth: list, show: int) -> dict:
    # `truth` rows are relative to the repo root the truth tool was given
    from helpers import Pipeline  # tests/helpers.py

    p = Pipeline(repo)
    out: dict = {}

    # ---- methods
    t_methods = {(r["owner"], r["name"]) for r in truth if r["t"] == "method"}
    i_methods = {tuple(d["fqn"].split("#", 1)) for d in p.extraction["defines"]
                 if d["kind"] == "method" and "#" in d["fqn"]}
    hit = t_methods & i_methods
    out["methods"] = (len(hit), len(t_methods), pct(len(hit), len(t_methods)))
    out["methods_precision"] = (len(hit), len(i_methods), pct(len(hit), len(i_methods)))
    missed = sorted(t_methods - i_methods)
    by_mod = Counter()
    mods = {(r["owner"], r["name"]): r for r in truth if r["t"] == "method"}
    for k in missed:
        r = mods[k]
        by_mod["ctor" if r["ctor"] else "iface" if r["iface"] else
               ("pkg-private" if not any(m in r["mods"] for m in ("public", "protected", "private"))
                else "other")] += 1
    out["methods_missed_by"] = dict(by_mod)
    out["methods_missed_sample"] = ["%s#%s" % k for k in missed[:show]]
    out["methods_extra_sample"] = ["%s#%s" % k for k in sorted(i_methods - t_methods)[:show]]

    # ---- fields
    t_fields = {(r["owner"], r["name"]) for r in truth if r["t"] == "field"}
    i_fields = {tuple(d["fqn"].rsplit(".", 1)) for d in p.extraction["defines"]
                if d["kind"] in ("constant", "field")}
    fhit = t_fields & i_fields
    out["fields"] = (len(fhit), len(t_fields), pct(len(fhit), len(t_fields)))
    out["fields_missed_sample"] = ["%s.%s" % k for k in sorted(t_fields - i_fields)[:show]]

    # ---- call sites
    # A site whose line cannot be cited (the same text appears elsewhere in the
    # file, or the file has no specific enough line) is not an index fact by
    # design (anchor.py), so it is left out of the denominator and counted.
    from cdp.anchor import build_anchor
    lines_of: dict = {}

    def citable(f: str, line: int) -> bool:
        if f not in lines_of:
            lines_of[f] = (repo / f).read_text(errors="replace").splitlines()
        return build_anchor(f, lines_of[f], line - 1) is not None

    t_calls = {}
    uncitable = 0
    for r in truth:
        if r["t"] == "call" and r["target"]:
            if not citable(r["file"], r["line"]):
                uncitable += 1
                continue
            t_calls[(r["file"], r["line"], r["target"])] = r
    out["calls_uncitable_excluded"] = uncitable
    # An anchor is a span that may start up to MAX_SPAN-1 lines above the call
    # (`+ server.getId()` is too short to cite alone), so a call matches an
    # indexed site whose anchor starts at or just above its line.
    # `new X()` with no explicit constructor resolves to the class itself (javac's
    # implicit default constructor is not a declared symbol), so map javac's target.
    explicit = {r["owner"] for r in truth if r["t"] == "method" and r["name"] == "<init>"}

    def mapped(target: str) -> str:
        owner, _, name = target.partition("#")
        return owner if name == "<init>" and owner not in explicit else target

    t_calls = {(f, line, mapped(tg)): r for (f, line, tg), r in t_calls.items()}
    by_target = defaultdict(list)
    index = set()
    for fqn, sites in p.xref["used_by"].items():
        for s in sites:
            by_target[(s["file"], fqn)].append(s["anchor"]["line"])
            index.add((s["file"], s["anchor"]["line"], fqn))

    def hit(k) -> bool:
        return any(0 <= k[1] - line < SPAN for line in by_target.get((k[0], k[2]), ()))

    chit = [k for k in t_calls if hit(k)]
    out["calls"] = (len(chit), len(t_calls), pct(len(chit), len(t_calls)))
    loose_names = defaultdict(list)
    for (f, line, fqn) in index:
        loose_names[(f, fqn.rsplit("#", 1)[-1])].append(line)
    loose = [k for k in t_calls if any(0 <= k[1] - L < SPAN for L in loose_names.get((k[0], k[2].rsplit("#", 1)[-1]), ()))]
    out["calls_loose"] = (len(loose), len(t_calls), pct(len(loose), len(t_calls)))
    per_how = defaultdict(lambda: [0, 0])
    for k, r in t_calls.items():
        per_how[r["how"]][1] += 1
        per_how[r["how"]][0] += hit(k)
    # Every `new X(..)` javac saw must show in the class's own used_by (`symbol X`):
    # sites on `X#<init>` fold into the class, as q_symbol does.
    class_sites = defaultdict(list)
    for fqn, sites in p.xref["used_by"].items():
        for s in sites:
            class_sites[(s["file"], fqn.split("#", 1)[0])].append(s["anchor"]["line"])
    news = [k for k, r in t_calls.items() if r["how"] == "new"]
    nhit = [k for k in news if any(0 <= k[1] - L < SPAN for L in class_sites.get((k[0], k[2].split("#", 1)[0]), ()))]
    out["new_in_class_used_by"] = (len(nhit), len(news), pct(len(nhit), len(news)))
    out["new_in_class_used_by_missed"] = ["%s:%d %s" % k for k in sorted(set(news) - set(nhit))[:show]]
    out["calls_by_how"] = {h: "%d/%d (%.0f%%)" % (a, b, pct(a, b)) for h, (a, b) in sorted(per_how.items())}
    # Precision: an indexed call whose (file, line, name) javac also saw. Where
    # javac resolved it into the repo the targets must agree; where javac could
    # not resolve it (Lombok members, missing deps) the call is unverifiable and
    # not counted either way; where javac saw no such call it is a phantom.
    seen_at: dict = defaultdict(dict)
    for r in truth:
        if r["t"] == "call":
            name = "<init>" if r["how"] in ("new", "super", "this") else r["name"]
            for d in range(SPAN):
                seen_at[(r["file"], r["line"] - d, name)][mapped(r["target"]) if r["target"] else ""] = True
    ok = bad = 0
    bad_rows = []
    for (f, line, fqn) in sorted(index):
        if "#" not in fqn:
            continue
        name = fqn.rsplit("#", 1)[-1]
        if name not in ("<init>",) and not name:
            continue
        targets = seen_at.get((f, line, name))
        if targets is None:
            if not f.endswith(".java"):
                continue
            bad += 1
            bad_rows.append("%s:%d %s (no such call)" % (f, line, fqn))
            continue
        resolved = [t for t in targets if t]
        if not resolved:
            continue
        if fqn in resolved:
            ok += 1
        else:
            bad += 1
            bad_rows.append("%s:%d %s (javac: %s)" % (f, line, fqn, ",".join(sorted(resolved))))
    out["calls_precision"] = (ok, ok + bad, pct(ok, ok + bad))
    out.update(measure_config(p, truth, show))
    out["calls_missed_sample"] = ["%s:%d %s" % k for k in sorted(k for k in t_calls if not hit(k))[:show]]
    out["calls_extra_sample"] = bad_rows[:show]
    return out


def measure_config(p, truth: list, show: int) -> dict:
    """Java `config_read` edges against javac's `cfg` rows: the read must be found
    (same file, anchor at or just above the line) with the same key."""
    from cdp.resolve import config_reads

    every = [r for r in config_reads(p.extraction, p.xref["constants"], p.xref.get("config_wrapped", ()))
             if r["file"].endswith(".java")]
    # javac only knows System/Long/... reads; reads through a configuration provider or a
    # wrapper method are checked by `config_provider_reads` below, not scored against javac.
    reads = [r for r in every if not r.get("provider") and not r.get("wrapper")]
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
    truth_at = {(r["file"], r["line"]) for r in cfg}
    extra = [x for x in reads if not any(0 <= L - x["anchor"]["line"] < SPAN for (f, L) in truth_at if f == x["file"])]
    return {
        "config": (keyed, len(cfg), pct(keyed, len(cfg))),
        "config_sites": (found, len(cfg), pct(found, len(cfg))),
        "config_precision": (len(reads) - len(extra), len(reads), pct(len(reads) - len(extra), len(reads))),
        "config_provider_reads": len(every) - len(reads),
        "config_missed_sample": missed[:show],
        "config_extra_sample": ["%s:%d %s" % (x["file"], x["anchor"]["line"], x["key"]) for x in extra[:show]],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("repo", type=Path)
    ap.add_argument("--stubs", type=Path)
    ap.add_argument("--classpath", default="")
    ap.add_argument("--truth", type=Path, help="reuse a JavaTruth jsonl")
    ap.add_argument("--misses", type=int, default=0, help="list N sample misses per metric")
    ap.add_argument("--min-methods", type=float, default=0)
    ap.add_argument("--min-calls", type=float, default=0)
    ap.add_argument("--min-fields", type=float, default=0)
    ap.add_argument("--min-config", type=float, default=0)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    if a.truth:
        truth = [json.loads(line) for line in a.truth.read_text().splitlines() if line.startswith("{")]
    else:
        truth = run_truth(a.repo, a.stubs, a.classpath)
    out = measure(as_git_repo(a.repo), truth, a.misses)
    if a.json:
        print(json.dumps(out, indent=1, sort_keys=True))
    else:
        for k in ("methods", "methods_precision", "fields", "calls", "calls_loose", "calls_precision",
                  "new_in_class_used_by", "config_sites", "config", "config_precision"):
            n, d, p = out[k]
            print("%-18s %5d/%-5d %6.1f%%" % (k, n, d, p))
        print("methods missed by:", out["methods_missed_by"])
        print("calls by how:", out["calls_by_how"])
        print("uncitable call sites excluded:", out["calls_uncitable_excluded"])
        if a.misses:
            for k in ("methods_missed_sample", "methods_extra_sample", "fields_missed_sample",
                      "calls_missed_sample", "calls_extra_sample", "new_in_class_used_by_missed", "config_missed_sample",
                      "config_extra_sample"):
                print("\n" + k)
                for line in out[k]:
                    print("  " + line)
    bad = [name for name, floor in (("methods", a.min_methods), ("calls", a.min_calls),
                                    ("fields", a.min_fields), ("config", a.min_config)) if out[name][2] < floor]
    for name in bad:
        print("BELOW TARGET: %s %.1f%%" % (name, out[name][2]), file=sys.stderr)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
