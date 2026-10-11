#!/usr/bin/env python3
"""C# extraction benchmark: CDP's index against Roslyn's own trees and semantic model.

    python scripts/csharp_benchmark.py REPO [--truth FILE] [--misses N]
        [--min-methods 95 --min-calls 85 --min-routes 90 --min-handlers 95 ...]

Builds `scripts/cstruth` (needs the .NET SDK; its Roslyn is referenced, no NuGet) in a temp
directory, runs it over REPO (pass --truth to reuse its output), runs the deterministic CDP
phases, and compares:

  methods     (owner, name) of every method and constructor (`<init>`, primary ones too) at any
              access level, against `defines` kind=method
  types       fqn of every named type, against `defines`
  fields      (owner, name) of every field, property, event and enum member, against defines
  call sites  (file, line, declaring-owner#name) for every invocation, `new`, `: base()/this()` and
              method group Roslyn binds into REPO, against `used_by` (property/field reads are
              `calls_member`, reported separately: `Owner.name`)
  routes      ASP.NET attribute routes Roslyn computes ([Route] of every partial part and of a base
              class, [controller]/[action] tokens, absolute templates): exact (verb, path), and
              (verb, path, handler)
  tables      EF Core tables: DbSet<T> by convention / [Table] / ToTable, CreateTable(name:)
  config      IConfiguration reads (indexer, GetValue, GetSection, GetConnectionString, Bind/Get)
              and Environment.GetEnvironmentVariable, with the key Roslyn folds ("" = computed,
              expected as `(dynamic)`); `appsettings*.json` leaf keys (`A:B`) against config defines

Exit status 1 when a --min-* threshold is missed. Misses are listed so a failure is a to-do list.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parent / "tests"))
from java_benchmark import as_git_repo, pct  # noqa: E402

SPAN = 4  # cdp.anchor.MAX_SPAN
CLASS_KINDS = ("class", "interface", "enum", "record", "struct", "annotation", "delegate")


def build_truth_tool() -> Path:
    src = HERE / "cstruth"
    digest = hashlib.sha1(b"".join(p.read_bytes() for p in sorted(src.glob("*.cs*")))).hexdigest()[:10]
    out = Path(tempfile.gettempdir()) / ("cstruth-" + digest)
    if (out / "out" / "CsTruth.dll").exists():
        return out / "out" / "CsTruth.dll"
    out.mkdir(parents=True, exist_ok=True)
    for p in src.glob("*.cs*"):
        shutil.copy(p, out / p.name)
    res = subprocess.run(["dotnet", "build", "-c", "Release", "-o", str(out / "out"), "-nologo", "-v", "q"],
                         cwd=out, capture_output=True, text=True)
    if res.returncode:
        sys.exit("building CsTruth failed:\n" + res.stdout[-3000:] + res.stderr[-2000:])
    return out / "out" / "CsTruth.dll"


def run_truth(repo: Path) -> list:
    dll = build_truth_tool()
    res = subprocess.run(["dotnet", str(dll), "--root", str(repo)], capture_output=True, text=True)
    rows = [json.loads(line) for line in res.stdout.splitlines() if line.startswith("{")]
    if not rows:
        sys.exit("Roslyn truth produced nothing:\n" + res.stderr[-2000:])
    sys.stderr.write(res.stderr.splitlines()[-1] + "\n")
    return rows


def norm_path(p: str) -> str:
    return p.strip("/")


def flatten_json(node, prefix=""):
    if isinstance(node, dict):
        for k, v in node.items():
            yield from flatten_json(v, prefix + ":" + k if prefix else k)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from flatten_json(v, "%s:%d" % (prefix, i))
    else:
        yield prefix


def measure(repo: Path, truth: list, show: int) -> dict:
    from helpers import Pipeline  # tests/helpers.py

    p = Pipeline(repo)
    out: dict = {}
    cs = lambda f: f.endswith(".cs")  # noqa: E731
    defines = [d for d in p.extraction["defines"] if cs(d["anchor"]["file"])]

    # ---- types
    t_types = {r["fqn"] for r in truth if r["t"] == "type"}
    i_types = {d["fqn"] for d in defines if d["kind"] in CLASS_KINDS}
    out["types"] = (len(t_types & i_types), len(t_types), pct(len(t_types & i_types), len(t_types)))
    out["types_missed_sample"] = sorted(t_types - i_types)[:show]

    # ---- methods
    t_rows = {(r["owner"], r["name"]): r for r in truth if r["t"] == "method"}
    t_methods = set(t_rows)
    i_methods = {tuple(d["fqn"].split("#", 1)) for d in defines if d["kind"] == "method" and "#" in d["fqn"]}
    hit = t_methods & i_methods
    out["methods"] = (len(hit), len(t_methods), pct(len(hit), len(t_methods)))
    out["methods_precision"] = (len(hit), len(i_methods), pct(len(hit), len(i_methods)))
    by_mod = Counter()
    tot_mod = Counter()
    for k, r in t_rows.items():
        label = "ctor" if r["ctor"] else r["mods"]
        tot_mod[label] += 1
        if k not in i_methods:
            by_mod[label] += 1
    out["methods_missed_by"] = {k: "%d/%d" % (by_mod[k], v) for k, v in sorted(tot_mod.items()) if by_mod[k]}
    out["methods_missed_sample"] = ["%s#%s" % k for k in sorted(t_methods - i_methods)[:show]]
    out["methods_extra_sample"] = ["%s#%s" % k for k in sorted(i_methods - t_methods)[:show]]

    # ---- fields
    t_fields = {(r["owner"], r["name"]) for r in truth if r["t"] == "field"}
    i_fields = {tuple(d["fqn"].rsplit(".", 1)) for d in defines
                if d["kind"] in ("constant", "field", "property", "event")}
    fhit = t_fields & i_fields
    out["fields"] = (len(fhit), len(t_fields), pct(len(fhit), len(t_fields)))
    out["fields_missed_sample"] = ["%s.%s" % k for k in sorted(t_fields - i_fields)[:show]]

    # ---- call sites
    from cdp.anchor import build_anchor
    lines_of: dict = {}

    def citable(f: str, line: int) -> bool:
        if f not in lines_of:
            lines_of[f] = (repo / f).read_text(errors="replace").splitlines()
        return build_anchor(f, lines_of[f], line - 1) is not None

    t_calls, t_members = {}, {}
    uncitable = 0
    for r in truth:
        if r["t"] != "call" or not r["target"]:
            continue
        if not citable(r["file"], r["line"]):
            uncitable += 1
            continue
        (t_members if r["how"] == "member" else t_calls)[(r["file"], r["line"], r["target"])] = r
    out["calls_uncitable_excluded"] = uncitable
    by_target = defaultdict(list)
    for fqn, sites in p.xref["used_by"].items():
        for s in sites:
            by_target[(s["file"], fqn)].append(s["anchor"]["line"])

    def hit_call(k) -> bool:
        return any(0 <= k[1] - line < SPAN for line in by_target.get((k[0], k[2]), ()))

    chit = [k for k in t_calls if hit_call(k)]
    out["calls"] = (len(chit), len(t_calls), pct(len(chit), len(t_calls)))
    mhit = [k for k in t_members if hit_call(k)]
    out["calls_member"] = (len(mhit), len(t_members), pct(len(mhit), len(t_members)))
    per_how = defaultdict(lambda: [0, 0])
    for k, r in t_calls.items():
        per_how[r["how"]][1] += 1
        per_how[r["how"]][0] += hit_call(k)
    out["calls_by_how"] = {h: "%d/%d (%.0f%%)" % (a, b, pct(a, b)) for h, (a, b) in sorted(per_how.items())}
    # precision: an indexed `Type#name` site Roslyn also saw at that line (any target); where Roslyn
    # resolved it the targets must agree. Unresolved by Roslyn (NuGet types) is not counted.
    seen_at: dict = defaultdict(dict)
    for r in truth:
        if r["t"] in ("call", "xcall") and r["how"] != "member":
            name = "<init>" if r["how"] in ("new", "ctor") else r["name"]
            for d in range(SPAN):
                seen_at[(r["file"], r["line"] - d, name)][r["target"]] = True
    ok = bad = 0
    bad_rows = []
    for fqn, sites in p.xref["used_by"].items():
        if "#" not in fqn:
            continue
        name = fqn.rsplit("#", 1)[-1]
        for s in sites:
            f, line = s["file"], s["anchor"]["line"]
            if not cs(f):
                continue
            targets = seen_at.get((f, line, name))
            if targets is None:
                bad += 1
                bad_rows.append("%s:%d %s (no such call)" % (f, line, fqn))
                continue
            resolved = [t for t in targets if t]
            if not resolved:
                continue            # Roslyn could not bind it (NuGet types in the way): not scored
            if fqn in resolved:
                ok += 1
            else:
                bad += 1
                bad_rows.append("%s:%d %s (roslyn: %s)" % (f, line, fqn, ",".join(sorted(resolved))))
    out["calls_precision"] = (ok, ok + bad, pct(ok, ok + bad))
    out["calls_missed_sample"] = ["%s:%d %s" % k for k in sorted(k for k in t_calls if not hit_call(k))[:show]]
    out["calls_extra_sample"] = bad_rows[:show]
    out["members_missed_sample"] = ["%s:%d %s" % k for k in sorted(k for k in t_members if not hit_call(k))[:show]]

    # ---- routes
    t_routes = {}
    for r in truth:
        if r["t"] == "route":
            t_routes[(r["verb"], norm_path(r["path"]), r["handler"])] = r
    i_routes = [r for r in p.xref["routes"] if cs(r["file"])]
    i_paths = {(r["verb"], norm_path(r["route"])) for r in i_routes}
    i_full = {(r["verb"], norm_path(r["route"]), r["handler"]) for r in i_routes}
    t_paths = {(v, pth) for v, pth, _ in t_routes}
    # a verb-less (`ANY`) route of ours is satisfied by any verb at the same path
    any_paths = {pth for v, pth in i_paths if v == "ANY"}
    phit = {k for k in t_paths if k in i_paths or k[1] in any_paths}
    out["routes"] = (len(phit), len(t_paths), pct(len(phit), len(t_paths)))
    fhit2 = {k for k in t_routes if k in i_full or (k[1], k[2]) in {(a[1], a[2]) for a in i_full if a[0] == "ANY"}}
    out["route_handlers"] = (len(fhit2), len(t_routes), pct(len(fhit2), len(t_routes)))
    out["routes_missed_sample"] = ["%s /%s -> %s" % k for k in sorted(set(t_routes) - fhit2)[:show]]
    out["routes_extra_sample"] = ["%s /%s -> %s" % k for k in sorted(i_full - set(t_routes))[:show]]
    out["routes_precision"] = (len(i_full & set(t_routes)), len(i_full),
                               pct(len(i_full & set(t_routes)), len(i_full)))

    # ---- tables
    t_tables = {r["name"] for r in truth if r["t"] == "table"}
    i_tables = {d["fqn"][len("table:"):] for d in p.extraction["defines"] if d["fqn"].startswith("table:")
                and cs(d["anchor"]["file"])}
    i_tables |= {e["target"][len("table:"):] for e in p.extraction["io_edges"]
                 if e["target"].startswith("table:") and cs(e["file"])}
    thit = t_tables & i_tables
    out["tables"] = (len(thit), len(t_tables), pct(len(thit), len(t_tables)))
    out["tables_missed_sample"] = sorted(t_tables - i_tables)[:show]
    out["tables_extra_sample"] = sorted(i_tables - t_tables)[:show]
    out.update(measure_config(repo, p, truth, show))
    return out


def measure_config(repo: Path, p, truth: list, show: int) -> dict:
    from cdp.resolve import config_reads

    reads = [r for r in config_reads(p.extraction, p.xref["constants"]) if r["file"].endswith(".cs")]
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
    res = {
        "config": (keyed, len(cfg), pct(keyed, len(cfg))),
        "config_sites": (found, len(cfg), pct(found, len(cfg))),
        "config_precision": (len(reads) - len(extra), len(reads), pct(len(reads) - len(extra), len(reads))),
        "config_missed_sample": missed[:show],
        "config_extra_sample": ["%s:%d %s" % (x["file"], x["anchor"]["line"], x["key"]) for x in extra[:show]],
    }
    # appsettings*.json declared keys
    want, have = set(), set()
    for f in repo.rglob("appsettings*.json"):
        rel = f.relative_to(repo).as_posix()
        if "/bin/" in rel or "/obj/" in rel:
            continue
        try:
            for k in flatten_json(json.loads(f.read_text(encoding="utf-8-sig"))):
                want.add((rel, k))
        except ValueError:
            continue
    for d in p.extraction["defines"]:
        if d["kind"] == "config_key" and d["fqn"].startswith("config:") and \
                d["anchor"]["file"].rsplit("/", 1)[-1].startswith("appsettings"):
            have.add((d["anchor"]["file"], d["fqn"][len("config:"):]))
    res["appsettings"] = (len(want & have), len(want), pct(len(want & have), len(want)))
    res["appsettings_missed_sample"] = ["%s %s" % k for k in sorted(want - have)[:show]]
    return res


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("repo", type=Path)
    ap.add_argument("--truth", type=Path, help="reuse a CsTruth jsonl")
    ap.add_argument("--misses", type=int, default=0, help="list N sample misses per metric")
    floors = ("methods", "calls", "fields", "types", "routes", "route_handlers", "tables", "config", "appsettings")
    for f in floors:
        ap.add_argument("--min-" + f.replace("_", "-"), type=float, default=0)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    if a.truth:
        truth = [json.loads(line) for line in a.truth.read_text().splitlines() if line.startswith("{")]
    else:
        truth = run_truth(a.repo.resolve())
    out = measure(as_git_repo(a.repo.resolve()), truth, a.misses)
    if a.json:
        print(json.dumps(out, indent=1, sort_keys=True))
    else:
        for k in ("types", "methods", "methods_precision", "fields", "calls", "calls_precision", "calls_member",
                  "routes", "route_handlers", "routes_precision", "tables", "config_sites", "config",
                  "config_precision", "appsettings"):
            n, d, pc = out[k]
            print("%-18s %6d/%-6d %6.1f%%" % (k, n, d, pc))
        print("methods missed by:", out["methods_missed_by"])
        print("calls by how:", out["calls_by_how"])
        print("uncitable call sites excluded:", out["calls_uncitable_excluded"])
        if a.misses:
            for k in sorted(k for k in out if k.endswith("_sample")):
                print("\n" + k)
                for line in out[k]:
                    print("  " + line)
    bad = [name for name in floors if out[name][2] < getattr(a, "min_" + name) ]
    for name in bad:
        print("BELOW TARGET: %s %.1f%%" % (name, out[name][2]), file=sys.stderr)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
