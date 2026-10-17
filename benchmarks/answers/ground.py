"""Grounding oracle: are the captured answers true of the source and of the store's raw data?

    python3 benchmarks/answers/ground.py --side old --repo workflow-service [--raw old]

(a) source grounding: every cited `path:line[-end]` in a JSON or text answer names a file
    of the pinned clone with that line in range; every `{file, line, anchor}` and every
    compact `{path: [[line, text]]}` evidence entry has its text at that line.
(b) DB grounding: per kind, the answer's key facts are recomputed from the raw store data
    (`raw.py`, never `cdp` code): symbol definition sites and used_by sets/counts, file
    defines and io edges, route list, table and config edges, stats counts, claim/module
    names, dataflow path hops.
Writes `~/.cdp-phase1/answers/<side>/<repo>/grounding.json` and prints pass rates.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(__file__))
from raw import PHASE, open_raw, repos  # noqa: E402

CITE = re.compile(r"^(?P<path>[^\s:]+):(?P<line>\d+)(?:-(?P<end>\d+))?$")
TEXT_CITE = re.compile(r"(?<![\w/.-])(?P<path>[\w.@+-]*/[\w./@+-]*\.\w+|[\w@+-]+\.\w{1,6}):(?P<line>\d+)(?:-(?P<end>\d+))?")
WS = re.compile(r"\s+")
SPAN = 4


def norm(s: str) -> str:
    return WS.sub(" ", s).strip()


class Source:
    def __init__(self, root: str, sha: str):
        self.root = root
        head = subprocess.run(["git", "-C", root, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
        dirty = subprocess.run(["git", "-C", root, "status", "--porcelain"], capture_output=True, text=True).stdout
        if head != sha or dirty.strip():
            raise SystemExit("%s is not a clean checkout of %s" % (root, sha))
        self._lines = {}

    def lines(self, path):
        if path not in self._lines:
            p = os.path.join(self.root, path)
            if not os.path.isfile(p):
                self._lines[path] = None
            else:
                with open(p, "rb") as fh:
                    self._lines[path] = fh.read().decode("utf-8", "replace").splitlines()
        return self._lines[path]

    def check_line(self, path, line, end=None):
        ls = self.lines(path)
        if ls is None:
            return "missing file %s" % path
        if not 1 <= line <= max(len(ls), 1):
            return "line %d out of range (%d) %s" % (line, len(ls), path)
        if end is not None and not line <= end <= len(ls):
            return "end %d out of range %s:%d" % (end, path, line)
        return None

    def check_text(self, path, line, text, starts=True):
        """`text` (whitespace-normalised) begins on `line`, spanning up to SPAN lines."""
        bad = self.check_line(path, line)
        if bad:
            return bad
        ls = self.lines(path)
        t = norm(text)
        if t.endswith("...") or t.endswith("…"):
            t = t.rstrip(".…").rstrip()
        if t.startswith("...") or t.startswith("…"):    # elided prefix: the rest is mid-line
            t, starts = t.lstrip(".…").lstrip(), False
        if not t:
            return None
        first = norm(ls[line - 1])
        window = norm(" ".join(ls[line - 1:line - 1 + SPAN]))
        pos = window.find(t)
        if pos < 0 or (starts and pos > len(first)):
            return "text not at %s:%d: %r" % (path, line, text[:80])
        return None


def walk_citations(obj, src, out, parent_key=None):
    """Append (ok, detail) for each citation found anywhere in a JSON answer."""
    if isinstance(obj, dict):
        f, ln, anc = obj.get("file"), obj.get("line"), obj.get("anchor")
        if isinstance(f, str) and isinstance(ln, int) and isinstance(anc, str):
            out.append(("anchor", src.check_text(f, ln, anc)))
        for k, v in obj.items():
            # compact evidence: {path: [[line, text], ...]}
            if (isinstance(v, list) and v and ("/" in k or src.lines(k) is not None)
                    and all(isinstance(x, list) and len(x) == 2 and isinstance(x[0], int)
                            and isinstance(x[1], str) for x in v)):
                for line, text in v:
                    out.append(("evidence", src.check_text(k, line, text)))
                continue
            walk_citations(v, src, out, k)
        # search `code` rows: `name` is the source line itself
        if parent_key == "code" and isinstance(obj.get("at"), str) and isinstance(obj.get("name"), str):
            m = CITE.match(obj["at"])
            if m:
                out.append(("code-text", src.check_text(m["path"], int(m["line"]), obj["name"], starts=False)))
    elif isinstance(obj, list):
        for v in obj:
            walk_citations(v, src, out, parent_key)
    elif isinstance(obj, str):
        m = CITE.match(obj)
        if m and ("/" in m["path"] or src.lines(m["path"]) is not None):
            out.append(("cite", src.check_line(m["path"], int(m["line"]), int(m["end"]) if m["end"] else None)))


def text_citations(text, src, out):
    for m in TEXT_CITE.finditer(text):
        path = m["path"]
        if src.lines(path) is None and "/" not in path:
            continue        # `foo.bar:3` that is not a file is not a citation
        out.append(("text-cite", src.check_line(path, int(m["line"]), int(m["end"]) if m["end"] else None)))


# ---------------------------------------------------------------- DB oracle

def cite(a):
    return "%s:%d" % (a["file"], a["line"])


class Oracle:
    def __init__(self, raw):
        self.raw = raw
        inv = raw.art("inventory")
        self.role = {f["path"]: f["role"] for f in inv["files"]}
        self.files = {f["path"]: f for f in inv["files"]}
        self.xref = raw.art("xref")
        self.ext = raw.art("extract")
        self.state = raw.art("state")
        self.df = raw.art("dataflow")
        self.part = raw.art("partition")
        self.edges = list(self.ext.get("io_edges", [])) + list(self.ext.get("rule_edges", []))
        self.defs_by_file = defaultdict(list)
        for d in self.ext["defines"]:
            self.defs_by_file[d["file"]].append(d)
        self.edges_by_file = defaultdict(list)
        for e in self.edges:
            self.edges_by_file[e["file"]].append(e)
        self.tables = defaultdict(list)
        self.config = defaultdict(list)
        for e in self.edges:
            t = e.get("target", "")
            if t.startswith("table:"):
                self.tables[t[6:]].append(e)
            elif t.startswith("config:") and e["channel"] == "config_read":
                self.config[t[7:]].append(e)

    @staticmethod
    def excluded(argv):
        ex = {argv[i + 1] for i, a in enumerate(argv) if a == "--exclude-role"}
        if "--include-tests" not in argv and argv[0] != "file":
            ex.add("test")
        return ex

    def users(self, fqn, ex):
        ub = self.xref["used_by"]
        us = list(ub.get(fqn, []))
        if self.xref["symbols"].get(fqn, {}).get("kind") in ("class", "enum", "record"):
            us += ub.get(fqn + "#<init>", [])
        sites = {}
        for u in us:
            if self.role.get(u["file"]) in ex:
                continue
            sites.setdefault((u["file"], u["anchor"]["line"]), cite(u["anchor"]))
        return set(sites.values())

    def check(self, argv, ans):
        """[(check name, error or None)] for one JSON answer."""
        kind, res = argv[0], []
        full = "--max-tokens" in argv and argv[argv.index("--max-tokens") + 1] == "0" and not ans.get("elided")
        ex = self.excluded(argv)
        syms = self.xref["symbols"]
        if kind == "stats":
            inv = self.raw.art("inventory")
            for k, want in (("symbols", len(syms)), ("routes", len(self.xref.get("routes", []))),
                            ("modules", len(inv["modules"])), ("claims", len(self.state["claims"])),
                            ("scopes", len(self.part["scopes"])), ("resolution", self.xref["resolution"]),
                            ("roles", inv["by_role"]), ("languages", inv["by_language"]),
                            ("unknowns", len(self.state["unknowns"])), ("conflicts", len(self.state["conflicts"]))):
                res.append(("stats." + k, None if ans.get(k) == want else "%s: answer %r raw %r" % (k, ans.get(k), want)))
        elif kind == "coverage":
            got = ans.get("coverage", {}).get("files_total")
            res.append(("coverage.files_total", None if got == len(self.files) else "%r vs %d" % (got, len(self.files))))
        elif kind == "symbol":
            for f in ans.get("found", []):
                if "fqn" not in f:      # list view row: {name, at, note}
                    e = syms.get(f.get("name"))
                    res.append(("symbol.list_row", None if e and f.get("at") in {cite(s["anchor"]) for s in e["sites"]}
                                else "list row %r at %r not raw" % (f.get("name"), f.get("at"))))
                    continue
                fqn = f["fqn"]
                e = syms.get(fqn)
                if e is None:
                    res.append(("symbol.exists", "no raw symbol %s" % fqn)); continue
                res.append(("symbol.kind", None if f.get("kind") == e["kind"] else "%s kind %r vs %r" % (fqn, f.get("kind"), e["kind"])))
                sites = {cite(s["anchor"]) for s in e["sites"] if self.role.get(s["anchor"]["file"]) not in ex} or \
                    {cite(s["anchor"]) for s in e["sites"]}
                got = set(f.get("defined_at") or [])
                res.append(("symbol.defined_at", None if got and got <= {cite(s["anchor"]) for s in e["sites"]}
                            else "%s defined_at %s not in raw sites" % (fqn, sorted(got - sites)[:3])))
                if "used_by_count" in f:
                    want = self.users(fqn, ex)
                    shown = {u["at"] for u in f.get("used_by", [])}
                    res.append(("symbol.used_by_sites", None if shown <= want else "%s used_by not in raw: %s" % (fqn, sorted(shown - want)[:3])))
                    res.append(("symbol.used_by_count", None if f["used_by_count"] == len(want) else
                                "%s used_by_count %d raw %d" % (fqn, f["used_by_count"], len(want))))
        elif kind == "file":
            for f in ans.get("found", []):
                p = f["path"]
                inv = self.files.get(p)
                if inv is None:
                    res.append(("file.exists", "no raw file %s" % p)); continue
                for k in ("module", "role", "language", "loc"):
                    if k in f:
                        res.append(("file." + k, None if f[k] == inv[k] else "%s %s %r vs %r" % (p, k, f[k], inv[k])))
                rdefs = self.defs_by_file.get(p, [])
                if "defines_count" in f:
                    res.append(("file.defines_count", None if f["defines_count"] == len(rdefs) else
                                "%s defines_count %d raw %d" % (p, f["defines_count"], len(rdefs))))
                want = {(d["fqn"], d["anchor"]["line"]) for d in rdefs}
                got = {(d["fqn"], d.get("line") or int(d["at"].rsplit(":", 1)[1])) for d in f.get("defines", [])}
                res.append(("file.defines", None if got <= want else "%s defines not raw: %s" % (p, sorted(got - want)[:3])))
                redges = self.edges_by_file.get(p, [])
                if "io_edges_count" in f:
                    res.append(("file.io_edges_count", None if f["io_edges_count"] == len(redges) else
                                "%s io_edges_count %d raw %d" % (p, f["io_edges_count"], len(redges))))
                wante = {(e["channel"], e["target"], cite(e["anchor"])) for e in redges}
                gote = {(e["channel"], e["target"], e["at"]) for e in f.get("io_edges", []) if "at" in e and "target" in e}
                res.append(("file.io_edges", None if gote <= wante else "%s edges not raw: %s" % (p, sorted(gote - wante)[:2])))
        elif kind == "routes":
            raw = self.xref.get("routes", [])
            names = defaultdict(set)
            for r in raw:
                names["%s %s" % (r.get("verb"), r.get("route"))].update(cite(e) for e in r.get("evidence", []))
                names["%s %s" % (r.get("verb"), r.get("route"))].add("%s:%s" % (r.get("file"), ""))
            for r in ans.get("routes", []):
                n = r.get("name") or "%s %s" % (r.get("verb"), r.get("route"))
                if "evidence" in r and isinstance(r["evidence"], list):
                    bad = [e for e in r["evidence"] if isinstance(e, str) and e not in names.get(n, ())]
                    res.append(("routes.evidence", None if not bad else "%s evidence %s not raw" % (n, bad[:2])))
                if n not in names:
                    res.append(("routes.name", "route %r not in raw" % n)); continue
                at = r.get("at")
                res.append(("routes.at", None if not at or at in names[n] or at.rsplit(":", 1)[0] + ":" in names[n]
                            else "%s at %s not raw evidence" % (n, at)))
            if argv[1:2] and not argv[1].startswith("--"):
                pass
            elif full and "--offset" not in argv:
                want = [r for r in raw if self.role.get(r.get("file")) not in ex]
                res.append(("routes.count", None if ans.get("count") == len(want) else
                            "count %r raw %d" % (ans.get("count"), len(want))))
        elif kind == "table":
            for t in ans.get("tables", []):
                n = t.get("table") or t.get("name")
                if n not in self.tables:
                    res.append(("table.name", "table %r not in raw edges" % n)); continue
                if "migration_count" in t:
                    want = [e for e in self.tables[n] if e["channel"] == "schema_own" and self.role.get(e["file"]) not in ex]
                    res.append(("table.migration_count", None if t["migration_count"] == len(want) else
                                "%s migration_count %d raw %d" % (n, t["migration_count"], len(want))))
                srcs = {e.get("source") for e in self.tables[n]}
                for k in ("written_by", "read_by"):
                    for w in t.get(k, []):
                        res.append(("table." + k, None if w in srcs or w in syms else "%s %s %s not raw" % (n, k, w)))
        elif kind == "config":
            # Reads are config_read edges whose source is code (`config-file:` sources are
            # declarations), plus xref.config_wrapped; `${C}` keys resolve through constants.
            reads = defaultdict(list)
            for e in self.edges + list(self.xref.get("config_wrapped", [])):
                if e.get("channel") == "config_read" and e.get("target", "").startswith("config:") \
                        and not e.get("source", "").startswith("config-file:") and self.role.get(e["file"]) not in ex:
                    reads[e["target"][7:]].append(cite(e["anchor"]))
            decls = defaultdict(list)
            for d in self.ext["defines"]:
                if d["kind"] == "config_key" and d["fqn"].startswith("config:") and self.role.get(d["file"]) not in ex:
                    decls[d["fqn"][7:]].append(cite(d["anchor"]))
            for k in ans.get("keys", []):
                key = k.get("key") or k.get("name")
                if key is None:
                    continue
                if "read" not in k:           # list row {name, at, note}
                    at = k.get("at")
                    ok = key == "(dynamic)" or key in reads or key in decls or at in {c for v in reads.values() for c in v}
                    res.append(("config.list_row", None if ok else "config key %r not raw" % key)); continue
                if "declared_count" in k:
                    res.append(("config.declared_count", None if k["declared_count"] == len(decls.get(key, [])) else
                                "%s declared_count %d raw %d" % (key, k["declared_count"], len(decls.get(key, [])))))
                for site in k.get("declared", []):
                    res.append(("config.declared_site", None if site in decls.get(key, []) else "%s declared %s not raw" % (key, site)))
                via = 0
                for r in k.get("read", []):
                    sym = r.get("via_constant")
                    ok = r.get("at") in (reads.get(sym, []) if sym else reads.get(key, []))
                    via += bool(sym and ok)
                    res.append(("config.read_site", None if ok else "%s read %s not raw" % (key, r.get("at"))))
                if key != "(dynamic)" and len(k.get("read", [])) == k.get("read_count"):
                    want = len(reads.get(key, [])) + via
                    res.append(("config.read_count", None if k["read_count"] == want else
                                "%s read_count %d raw %d" % (key, k["read_count"], want)))
        elif kind == "paths":
            rawp = {tuple((h.get("channel"), cite(h["anchor"])) for h in p.get("hops", []) if h.get("anchor"))
                    for p in self.df.get("paths", [])}
            for p in ans.get("paths", []):
                hops = p.get("hops")
                if not isinstance(hops, list) or not hops or not isinstance(hops[0], dict):
                    continue
                key = tuple((h.get("channel"), h.get("at")) for h in hops if h.get("at"))
                res.append(("paths.hops", None if key in rawp else "path %s not a raw path" % (key[:2],)))
        elif kind == "module":
            mods = {m["name"] for m in self.raw.art("inventory")["modules"]}
            for m in ans.get("found", []):
                res.append(("module.name", None if m.get("name") in mods else "module %r not raw" % m.get("name")))
        elif kind == "claims":
            subj = {c.get("subject") for c in self.state["claims"]}
            ids = {c.get("id") for c in self.state["claims"]}
            for c in ans.get("claims", []):
                ok = c.get("name") in subj or c.get("subject") in subj or c.get("id") in ids
                res.append(("claims.row", None if ok else "claim %r not raw" % (c.get("name") or c.get("id"))))
        elif kind == "search":
            for s in ans.get("symbols", []):
                n = s.get("name") or s.get("fqn")
                res.append(("search.symbol", None if n in syms else "symbol %r not raw" % n))
            for s in ans.get("files", []):
                n = s.get("name") or s.get("path")
                res.append(("search.file", None if n in self.files else "file %r not raw" % n))
        elif kind == "trace":
            for f in ans.get("files", []):
                p = f.get("path") or (f.get("at") or "").rsplit(":", 1)[0] or f.get("name")
                if p:
                    res.append(("trace.file", None if p in self.files else "trace file %r not raw" % p))
        return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--side", required=True)
    ap.add_argument("--repo", required=True)
    ap.add_argument("--raw", default=None, help="raw reader (old|new); default = side")
    a = ap.parse_args()
    meta = repos()[a.repo]
    src = Source(meta["path"], meta["sha"])
    raw = open_raw(a.raw or a.side, os.path.join(PHASE, a.side), meta["identity"], meta["sha"])
    oracle = Oracle(raw)
    with open(os.path.join(PHASE, "queries", a.repo + ".json")) as fh:
        corpus = json.load(fh)
    base = os.path.join(PHASE, "answers", a.side, a.repo)
    src_stats, db_stats = defaultdict(lambda: [0, 0]), defaultdict(lambda: [0, 0])
    failures = []
    for q in corpus["cli"]:
        for fmt in ("json", "txt"):
            p = os.path.join(base, "cli", "%s.%s" % (q["id"], fmt))
            if not os.path.exists(p):
                continue
            with open(p) as fh:
                body = fh.read()
            cites = []
            if not body.strip():
                continue        # an error answer (non-zero exit, message on stderr): compare.py diffs it
            if fmt == "json":
                try:
                    ans = json.loads(body)
                except ValueError:
                    failures.append({"id": q["id"], "fmt": fmt, "check": "parse", "error": "not JSON"}); continue
                walk_citations(ans, src, cites)
                for name, err in oracle.check(q["argv"], ans):
                    s = db_stats[name]; s[0] += 1; s[1] += err is None
                    if err:
                        failures.append({"id": q["id"], "argv": q["argv"], "fmt": "db", "check": name, "error": err})
            else:
                text_citations(body, src, cites)
            for name, err in cites:
                s = src_stats[q["argv"][0] + ":" + fmt]; s[0] += 1; s[1] += err is None
                if err:
                    failures.append({"id": q["id"], "argv": q["argv"], "fmt": fmt, "check": name, "error": err})
    mcp_dir = os.path.join(base, "mcp")
    for call in corpus["mcp"]:
        p = os.path.join(mcp_dir, call["id"] + ".json")
        if os.path.exists(p) and call["tool"] == "cdp_query":
            with open(p) as fh:
                ans = json.load(fh)
            cites = []
            walk_citations(ans, src, cites)
            for name, err in cites:
                s = src_stats["mcp"]; s[0] += 1; s[1] += err is None
                if err:
                    failures.append({"id": call["id"], "fmt": "mcp", "check": name, "error": err})
    tot = lambda d: (sum(v[0] for v in d.values()), sum(v[1] for v in d.values()))
    report = {"source": {k: v for k, v in sorted(src_stats.items())}, "db": {k: v for k, v in sorted(db_stats.items())},
              "source_total": tot(src_stats), "db_total": tot(db_stats), "failures": failures}
    with open(os.path.join(base, "grounding.json"), "w") as fh:
        json.dump(report, fh, indent=1, sort_keys=True)
    (sn, sp), (dn, dp) = report["source_total"], report["db_total"]
    print("%s %s: source %d/%d (%.2f%%)  db %d/%d (%.2f%%)  failures %d" % (
        a.side, a.repo, sp, sn, 100.0 * sp / max(sn, 1), dp, dn, 100.0 * dp / max(dn, 1), len(failures)))
    byc = defaultdict(int)
    for f in failures:
        byc[f["check"]] += 1
    for k, v in sorted(byc.items(), key=lambda kv: -kv[1]):
        print("  %-26s %d" % (k, v))


if __name__ == "__main__":
    main()
