"""Build the deterministic query corpus for one pinned repo.

    python3 benchmarks/answers/gen_queries.py --repo workflow-service --code ~/.cdp-phase1/oldcode

Terms are sampled (seeded) from the OLD store's raw artifacts, plus the full
lists `table`/`config` print, so the corpus is fixed before any new code runs.
Writes `~/.cdp-phase1/queries/<repo>.json`: `cli` entries (argv after
`query`), `mcp` entries (cdp_query kwargs) and `commands` (other subcommands).
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(__file__))
from raw import PHASE, OldRaw, repos  # noqa: E402

SEED = 1729


def list_terms(code: str, state: str, repo: str, kind: str, field: str):
    """Every row name a wide list query prints (old code, tests kept, no caps)."""
    out = subprocess.run([sys.executable, "-m", "cdp.cli", "query", kind, "--repo", repo, "--state-dir", state,
                          "--json", "--view", "list", "--max-tokens", "0", "--budget", "1000000", "--include-tests"],
                         cwd=code, capture_output=True, text=True, check=True).stdout
    return [r["name"] for r in json.loads(out).get(field, [])]


def sample(rng, items, n):
    items = sorted(set(items))
    return items if len(items) <= n else rng.sample(items, n)


def build(name: str, code: str) -> dict:
    meta = repos()[name]
    state = os.path.join(PHASE, "old")
    raw = OldRaw(os.path.join(state, "index.db"), meta["identity"], meta["sha"])
    rng = random.Random("%s:%s" % (SEED, name))
    xref, ext, inv, df, st = (raw.art(n) for n in ("xref", "extract", "inventory", "dataflow", "state"))
    syms = xref["symbols"]
    role = {f["path"]: f["role"] for f in inv["files"]}
    cli, mcp = [], []

    def add(kind, term=None, *flags, tag=""):
        argv = [kind] + ([term] if term is not None else []) + list(flags)
        cli.append({"id": "%s-%03d" % (kind, sum(1 for c in cli if c["argv"][0] == kind)), "argv": argv,
                    "tag": tag})

    # -- stats / coverage
    add("stats"); add("coverage")
    # -- symbol: 40 terms + variants
    keys = sorted(syms)
    def is_test(k):
        return all(role.get(s["anchor"]["file"]) == "test" for s in syms[k]["sites"])

    types = [k for k in keys if "#" not in k and syms[k]["kind"] in ("class", "interface", "enum", "record")]
    meths = [k for k in keys if "#" in k]
    # Mostly non-test symbols (tests are dropped by default), a couple of test ones.
    plain = sample(rng, [k for k in types if not is_test(k)], 8) + sample(rng, [k for k in types if is_test(k)], 2)
    members = sample(rng, [k for k in meths if not is_test(k)], 8) + sample(rng, [k for k in meths if is_test(k)], 2)
    colls = sample(rng, [c["fqn"] for c in xref.get("collisions", [])], 5)
    overl = {}
    for d in ext["defines"]:
        if d.get("kind") == "method":
            overl.setdefault((d["file"], d["fqn"]), []).append(d)
    ovs = sample(rng, [k[1] for k, v in overl.items() if len(v) > 1 and role.get(k[0]) != "test"], 4) + \
        sample(rng, [k[1] for k, v in overl.items() if len(v) > 1 and role.get(k[0]) == "test"], 1)
    short = [k.rsplit(".", 1)[-1] for k in sample(rng, plain, 4)]
    owner_m = []
    for k in sample(rng, [k for k in members if "#" in k and "." in k.split("#")[0]], 3):
        owner, _, m = k.partition("#")
        owner_m.append("%s#%s" % (owner.rsplit(".", 1)[-1], m.split("(")[0]))
    misses = ["NoSuchSymbolXyz", (plain[0][:-1] + "Q") if plain else "Zzz"]
    sym_terms = plain + members + colls + ovs + short + owner_m + misses
    for i, t in enumerate(sym_terms):
        add("symbol", t, tag="term")
    for t in sym_terms[:6]:
        add("symbol", t, "--include-tests", "--max-tokens", "0", tag="full")
    for t in sym_terms[:4]:
        add("symbol", t, "--exact", tag="exact")
    for t in members[:3] + ovs[:2]:
        add("symbol", t, "--view", "detail", "--max-tokens", "0", "--include-tests", tag="detail")
    for t in plain[:3]:
        add("symbol", t, "--budget", "5", tag="budget")
        add("symbol", t, "--exclude-role", "test", "--exclude-role", "build", tag="exclude")
    if plain:
        add("symbol", re.escape(plain[0].rsplit(".", 1)[-1]) + "$", "--match", "regex", tag="regex")
        add("symbol", plain[1].rsplit(".", 1)[-1] if len(plain) > 1 else plain[0], "--view", "count", tag="count")
        add("symbol", plain[0].rsplit(".", 1)[-1][:4], "--view", "list", "--offset", "5", tag="offset")
    # -- file: 20 (source, test, config/build)
    files = sorted(role)
    src = sample(rng, [f for f in files if role[f] == "source"], 13)
    tst = sample(rng, [f for f in files if role[f] == "test"], 4)
    oth = sample(rng, [f for f in files if role[f] in ("config", "build", "schema")], 3)
    for f in src + tst + oth:
        add("file", f, tag="term")
    for f in src[:3] + tst[:2]:
        add("file", f, "--view", "detail", "--max-tokens", "0", "--include-tests", tag="detail")
    if src:
        add("file", os.path.dirname(src[0]) or src[0], tag="dir")
        add("file", os.path.basename(src[1] if len(src) > 1 else src[0]), tag="basename")
    # -- module
    mods = [m["name"] for m in inv["modules"]]
    for m in sample(rng, mods, 5):
        add("module", m, tag="term")
    add("module", mods[0], "--view", "detail", "--max-tokens", "0", tag="detail")
    # -- routes: all, paged, filtered
    add("routes", None, "--max-tokens", "0", "--budget", "1000000", "--include-tests", tag="all")
    n = len(xref.get("routes", []))
    for off in range(0, max(n, 1), 50):
        add("routes", None, "--offset", str(off), tag="page")
    add("routes", None, "--view", "count", tag="count")
    add("routes", None, "--view", "detail", "--budget", "15", "--max-tokens", "0", tag="detail")
    segs = sorted({s for r in xref.get("routes", []) for s in r.get("route", "").split("/") if len(s) > 3 and "{" not in s})
    for s in sample(rng, segs, 5):
        add("routes", s, tag="term")
    add("routes", None, "--filter", "GET", "--view", "list", tag="filter")
    # -- table
    tables = list_terms(code, state, meta["path"], "table", "tables")
    add("table", None, tag="all"); add("table", None, "--include-tests", "--max-tokens", "0", "--budget", "1000000", tag="all-full")
    add("table", None, "--view", "count", tag="count")
    tsample = sample(rng, tables, 10)
    for t in tsample:
        add("table", t, "--view", "detail", "--max-tokens", "0", "--include-tests", tag="term")
    for t in tsample[:4]:
        add("table", t, "--exact", tag="exact")
    # -- config
    keys_c = list_terms(code, state, meta["path"], "config", "keys")
    add("config", None, tag="all"); add("config", None, "--view", "count", tag="count")
    add("config", None, "--offset", "50", tag="page")
    csample = sample(rng, keys_c, 10)
    for k in csample:
        add("config", k, "--view", "detail", "--max-tokens", "0", "--include-tests", tag="term")
    for k in csample[:4]:
        add("config", k, "--exact", tag="exact")
    # -- paths
    add("paths", None, tag="all"); add("paths", None, "--view", "count", tag="count")
    pths = df.get("paths", [])
    for p in sample(rng, range(len(pths)), 10):
        path = pths[p]
        hops = path.get("hops") or []
        frm = (hops[0].get("from") if hops else path.get("trigger") or "").rsplit(".", 1)[-1]
        to = (hops[-1].get("to") if hops else "").rsplit(".", 1)[-1]
        if frm and to and p % 2 == 0:
            add("paths", None, "--from", frm, "--to", to, "--max-tokens", "0", tag="from-to")
        elif frm:
            add("paths", None, "--from", frm, "--max-tokens", "0", tag="from")
    # -- trace: routes, handlers, sources
    entries = ["%s %s" % (r["verb"], r["route"]) for r in xref.get("routes", []) if r.get("verb") and r.get("route")]
    handlers = [r["handler"].rsplit(".", 1)[-1] for r in xref.get("routes", []) if r.get("handler")]
    sources = [s["node"].rsplit(".", 1)[-1] for s in df.get("sources", []) if s.get("node")]
    trace = sample(rng, entries, 4) + sample(rng, handlers, 3) + sample(rng, sources, 3)
    if len(trace) < 10:
        trace += sample(rng, [k.rsplit(".", 1)[-1] for k in members], 10 - len(trace))
    for t in trace:
        add("trace", t, "--max-tokens", "0", tag="term")
    for t in trace[:3]:
        add("trace", t, "--max-hops", "3", tag="hops")
        add("trace", t, "--include-tests", "--view", "detail", "--max-tokens", "0", tag="detail")
    # -- search
    words = [k.rsplit(".", 1)[-1].split("#")[-1] for k in sample(rng, keys, 6)]
    consts = [str(v.get("value")) for v in xref.get("constants", {}).values() if isinstance(v, dict) and v.get("value")]
    words += [c for c in sample(rng, consts, 2) if 3 < len(c) < 40][:2]
    words += [os.path.basename(src[0]).split(".")[0] if src else "main", "zzqx_not_there"]
    for w in words:
        add("search", w, "--max-tokens", "0", tag="term")
    for w in words[:3]:
        add("search", w, "--include-tests", "--budget", "8", tag="budget")
    add("search", words[0], "--match", "exact", tag="exact")
    add("search", "def |class ", "--match", "regex", "--budget", "10", tag="regex")
    add("search", words[1], "--view", "count", tag="count")
    # -- claims / unknowns / conflicts
    add("claims", None, tag="all"); add("claims", None, "--view", "count", tag="count")
    ckinds = sorted({c.get("kind") for c in st.get("claims", []) if c.get("kind")})
    for k in ckinds[:4]:
        add("claims", None, "--kind", k, tag="kind")
    for m in sample(rng, mods, 2):
        add("claims", None, "--module", m, tag="module")
    subjects = sorted({c.get("subject", "") for c in st.get("claims", [])})
    for s in sample(rng, subjects, 2):
        add("claims", None, "--subject", s.rsplit(".", 1)[-1], "--include-library", tag="subject")
    add("claims", None, "--offset", "40", tag="page")
    add("unknowns", None, tag="all"); add("conflicts", None, tag="all")

    # MCP subset: one or two per kind through the harness's own tool functions.
    pick = {}
    for c in cli:
        pick.setdefault(c["argv"][0], []).append(c)
    for kind, rows in sorted(pick.items()):
        for c in rows[:2]:
            kw = _mcp_kwargs(c["argv"])
            if kw is not None:
                mcp.append({"id": "mcp-" + c["id"], "tool": "cdp_query", "kwargs": kw})
    mcp.append({"id": "mcp-status", "tool": "cdp_status", "kwargs": {}})
    for t in (None, "symbol", "trace", "search"):
        mcp.append({"id": "mcp-help-%s" % (t or "overview"), "tool": "cdp_help", "kwargs": {"topic": t}})

    commands = [
        {"id": "cmd-status", "argv": ["status"]},
        {"id": "cmd-verify", "argv": ["verify"]},
        {"id": "cmd-diff-self", "argv": ["diff", "--old-sha", meta["sha"]]},
        {"id": "cmd-export-json", "argv": ["export", "--format", "json", "--out", "{OUT}/export"], "outdir": "export"},
        {"id": "cmd-docs", "argv": ["docs", "--out", "{OUT}/docs"], "outdir": "docs"},
    ]
    return {"repo": name, "sha": meta["sha"], "seed": SEED, "cli": cli, "mcp": mcp, "commands": commands}


FLAG_KW = {"--budget": ("budget", int), "--offset": ("offset", int), "--max-tokens": ("max_tokens", int),
           "--max-hops": ("max_hops", int), "--view": ("view", str), "--match": ("match", str),
           "--from": ("frm", str), "--to": ("to", str), "--kind": ("claim_kind", str), "--module": ("module", str),
           "--subject": ("subject", str), "--filter": ("filter", str), "--format": ("format", str)}


def _mcp_kwargs(argv):
    kw = {"kind": argv[0]}
    rest = argv[1:]
    if rest and not rest[0].startswith("--"):
        kw["term"], rest = rest[0], rest[1:]
    i = 0
    while i < len(rest):
        f = rest[i]
        if f in FLAG_KW:
            k, typ = FLAG_KW[f]
            kw[k] = typ(rest[i + 1]); i += 2
        elif f == "--exclude-role":
            kw.setdefault("exclude_role", []).append(rest[i + 1]); i += 2
        elif f in ("--exact", "--include-tests", "--include-library"):
            kw[f[2:].replace("-", "_")] = True; i += 1
        else:
            return None
    return kw


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--code", default=os.path.join(PHASE, "oldcode"))
    a = ap.parse_args()
    corpus = build(a.repo, os.path.expanduser(a.code))
    os.makedirs(os.path.join(PHASE, "queries"), exist_ok=True)
    out = os.path.join(PHASE, "queries", a.repo + ".json")
    with open(out, "w") as fh:
        json.dump(corpus, fh, indent=1, sort_keys=True)
    kinds = {}
    for c in corpus["cli"]:
        kinds[c["argv"][0]] = kinds.get(c["argv"][0], 0) + 1
    print(out, "cli=%d mcp=%d commands=%d" % (len(corpus["cli"]), len(corpus["mcp"]), len(corpus["commands"])), kinds)


if __name__ == "__main__":
    main()
