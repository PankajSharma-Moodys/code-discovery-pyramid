"""Independent readers of a store's raw data, for the grounding oracle.

Nothing here imports `cdp`: the oracle must not share code with what it checks.
`OldRaw` reads the legacy `snapshot_artifact` JSON payloads; each reader exposes
the same small dict-of-artifacts view (`art(name)`) the oracle in `ground.py` uses.
"""

from __future__ import annotations

import json
import os
import sqlite3
import zlib
from typing import Dict, Optional

PHASE = os.path.expanduser(os.environ.get("CDP_PHASE1", "~/.cdp-phase1"))


def repos() -> Dict[str, Dict]:
    """`{name: {path, sha, identity}}` -- the pinned inputs, recorded once in repos.json."""
    with open(os.path.join(PHASE, "repos.json")) as fh:
        return json.load(fh)


class OldRaw:
    """Legacy schema: one JSON payload per (snapshot, artifact name)."""

    def __init__(self, db: str, identity: str, sha: str):
        self.conn = sqlite3.connect("file:%s?mode=ro" % db, uri=True)
        row = self.conn.execute("SELECT id FROM snapshot_meta WHERE repo_id=? AND commit_sha=?",
                                (identity, sha)).fetchone()
        if not row:
            raise SystemExit("no snapshot for %s@%s in %s" % (identity, sha, db))
        self.snapshot_id = row[0]
        self._cache: Dict[str, object] = {}

    def art(self, name: str) -> Optional[Dict]:
        if name not in self._cache:
            row = self.conn.execute("SELECT payload FROM snapshot_artifact WHERE snapshot_id=? AND name=?",
                                    (self.snapshot_id, name)).fetchone()
            self._cache[name] = json.loads(row[0]) if row else None
        return self._cache[name]


class NewRaw:
    """Object schema (PLAN_DB_ARCH.md), read with plain SQL: docs, the per-file manifest and its
    segments, and -- for the symbol facts -- the `f_def`/`x_use` indexes rather than any code path
    `cdp` answers queries with. `art(name)` returns the oracle's view of each artifact."""

    def __init__(self, db: str, identity: str, sha: str):
        self.conn = sqlite3.connect("file:%s?mode=ro" % db, uri=True)
        row = self.conn.execute("SELECT id FROM snapshot_meta WHERE repo_id=? AND commit_sha=? AND complete=1",
                                (identity, sha)).fetchone()
        if not row:
            raise SystemExit("no complete snapshot for %s@%s in %s" % (identity, sha, db))
        self.snapshot_id = row[0]
        self._cache: Dict[str, object] = {}
        self._docs = dict(self.conn.execute("SELECT name, doc_id FROM snapshot_doc WHERE snapshot_id=?",
                                            (self.snapshot_id,)).fetchall())
        rows = self.conn.execute(
            "SELECT s.s, f.ord, f.fseg, f.xseg, f.wseg, m.s, r.s, l.s, f.bytes, f.loc, f.flags "
            "FROM snapshot_file f JOIN str s ON s.id=f.path_id LEFT JOIN str m ON m.id=f.module_id "
            "LEFT JOIN str r ON r.id=f.role_id LEFT JOIN str l ON l.id=f.lang_id "
            "WHERE f.snapshot_id=? ORDER BY f.ord", (self.snapshot_id,)).fetchall()
        self.order = [r[0] for r in rows]
        self.files = {r[0]: r for r in rows}

    def _doc(self, name):
        doc_id = self._docs.get(name)
        if doc_id is None:
            return None
        z = self.conn.execute("SELECT z FROM doc WHERE id=?", (doc_id,)).fetchone()[0]
        d = json.loads(zlib.decompress(z))
        return d.get("__cdp_whole__", d) if isinstance(d, dict) and len(d) == 1 else d

    def _seg(self, seg_id):
        z = self.conn.execute("SELECT z FROM seg WHERE id=?", (seg_id,)).fetchone()[0]
        return json.loads(zlib.decompress(z))

    def _lists(self, skel, col, key):
        per = {p: self._seg(self.files[p][col]) for p in self.order if self.files[p][col]}
        out = {}
        for name, runs in skel["runs"].items():
            rows, cur = [], {}
            for pos, n in runs:
                p = self.order[pos]
                i = cur.get(p, 0)
                rows += per[p].get(name, [])[i:i + n]
                cur[p] = i + n
            out[name] = rows
        return out, per

    def art(self, name: str) -> Optional[Dict]:
        if name in self._cache:
            return self._cache[name]
        d = self._doc(name)
        if isinstance(d, dict) and "__cdp_parts__" in d:
            out = dict(d["rest"])
            if name == "inventory":
                out["files"] = [{"path": p, "module": r[5], "role": r[6], "language": r[7], "bytes": r[8],
                                 "loc": r[9], "binary": bool(r[10] & 1)} for p in self.order for r in [self.files[p]]]
            elif name == "extract":
                lists, per = self._lists(d, 2, "file")
                out.update(lists)
                out["files"] = {p: b["meta"] for p, b in per.items() if "meta" in b}
            elif name == "dataflow":
                out.update(self._lists(d, 4, "file")[0])
            elif name == "xref":
                out.update(self._lists(d, 3, "from_file")[0])
                out["symbols"] = self._symbols()
                out["used_by"] = self._used_by()
            d = out
        self._cache[name] = d
        return d

    def _symbols(self):
        """fqn -> {kind (first define in extract order), sites}, from f_def joined to this
        snapshot's manifest; the rows themselves come from the extract segments."""
        segs = {}
        hits = self.conn.execute(
            "SELECT s.s, d.seg, d.ord FROM f_def d JOIN snapshot_file f ON f.fseg=d.seg AND f.snapshot_id=? "
            "JOIN str s ON s.id=d.fqn", (self.snapshot_id,)).fetchall()
        out = {}
        for fqn, seg, o in hits:
            if seg not in segs:
                segs[seg] = self._seg(seg)
            row = segs[seg]["defines"][o]
            out.setdefault(fqn, []).append(row)
        ext_rank = {json.dumps(r, sort_keys=True): i for i, r in enumerate(self.art("extract")["defines"])}
        sym = {}
        for fqn, rows in out.items():
            rows.sort(key=lambda r: ext_rank.get(json.dumps(r, sort_keys=True), 0))
            sym[fqn] = {"fqn": fqn, "kind": rows[0]["kind"],
                        "sites": [{"file": r["file"], "anchor": r["anchor"], "module": r["module"]} for r in rows]}
        return sym

    def _used_by(self):
        """fqn -> users, from the `x_use` index (rows resolving local/matched/ambiguous)."""
        segs = {}
        out = {}
        for fqn, seg, o in self.conn.execute(
                "SELECT s.s, u.seg, u.ord FROM x_use u JOIN snapshot_file f ON f.xseg=u.seg AND f.snapshot_id=? "
                "JOIN str s ON s.id=u.to_sym", (self.snapshot_id,)).fetchall():
            if seg not in segs:
                segs[seg] = self._seg(seg)
            u = segs[seg]["uses"][o]
            out.setdefault(fqn, []).append({"module": u["from_module"], "file": u["from_file"], "anchor": u["anchor"]})
        return out


def open_raw(kind: str, state_dir: str, identity: str, sha: str):
    db = os.path.join(state_dir, "index.db")
    if kind == "old":
        return OldRaw(db, identity, sha)
    if kind == "new":
        return NewRaw(db, identity, sha)
    raise SystemExit("unknown raw reader %r" % kind)
