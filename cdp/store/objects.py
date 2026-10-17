"""Content-addressed object store shared by `SqliteStore` and `PostgresStore` (PLAN_DB_ARCH.md).

A snapshot is a full per-file manifest (`snapshot_file`, one row per inventory file) plus named
documents (`snapshot_doc`), both pointing at shared, immutable, content-addressed objects:

    blob   raw file bytes, keyed by git's blob id (`sha1("blob <n>\\0" + bytes)`)
    seg    one file's rows of one heavy artifact (extract / xref uses / dataflow edges), or one
           file's raw extractor output (the per-file extraction cache, `fcache`); zlib JSON
    doc    any other JSON value (small artifacts, and the per-snapshot skeleton of a heavy one)

`f_def`/`x_use`/`flow` index the segments' rows by symbol so the hot queries read only the
files that matter. Every statement is written once here with `?` placeholders; `_q` rewrites it
for psycopg2 (`%s`, `ON CONFLICT DO NOTHING`, BYTEA).

**Byte-exact compatibility.** `read_artifact` of a decomposed artifact reassembles exactly the
dict `json.loads(json.dumps(data, sort_keys=True))` gave before: rows come back verbatim from the
segments, and each list's global order (which interleaves files: rows are sorted by fqn, not
grouped by file) is kept per snapshot as run lengths over the manifest's file order. `xref.symbols`
and `xref.used_by` are not stored: they are pure functions of the snapshot's extract and xref
uses (`resolve._symbol_table`, `resolve._transpose`), checked equal before that is relied on. A
value that does not decompose cleanly (a test's toy payload) is stored whole as one doc.

**Snapshot builds.** `begin_snapshot` starts an in-memory pending manifest; writes go to objects
at once (committed in batches; an orphan is harmless) and to the pending manifest. Writing
`manifest` -- always the last artifact scan/refresh write -- commits the manifest in one
transaction and only then marks the snapshot `complete` and makes it the latest. Writers hold the
store-wide `objects` lock shared from their first object write to that commit; `sweep_objects`
takes it exclusive, so it never deletes an object a pending manifest is about to reference.
"""

from __future__ import annotations

import contextlib
import gc
import hashlib
import json
import os
import struct
import sys
import zlib
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from ..util import CdpError, stable_hash

#: Heavy artifacts decomposed into per-file segments; everything else is one doc.
HEAVY = ("inventory", "extract", "xref", "dataflow", "code")
EXTRACT_LISTS = ("defines", "uses", "imports", "io_edges", "rule_edges")
PARTS = "__cdp_parts__"      # marks a decomposed artifact's skeleton doc
WHOLE = "__cdp_whole__"      # wraps a whole value that itself carries the PARTS key
INV_KEYS = ("binary", "bytes", "language", "loc", "module", "path", "role")
F_BINARY, F_CODE = 1, 2
SEG_EXTRACT, SEG_XREF, SEG_FLOW, SEG_FACTS = 1, 2, 3, 4
USED_BY_STATUS = {"local": 1, "matched": 2, "ambiguous": 3}
BATCH = 2000

SCHEMA_SQLITE = """
CREATE TABLE IF NOT EXISTS str  (id INTEGER PRIMARY KEY, h64 INTEGER NOT NULL UNIQUE, s TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS blob (id INTEGER PRIMARY KEY, sha BLOB NOT NULL UNIQUE, size INTEGER NOT NULL, z BLOB);
CREATE TABLE IF NOT EXISTS seg  (id INTEGER PRIMARY KEY, h BLOB NOT NULL UNIQUE, z BLOB NOT NULL);
CREATE TABLE IF NOT EXISTS doc  (id INTEGER PRIMARY KEY, h BLOB NOT NULL UNIQUE, z BLOB NOT NULL);
CREATE TABLE IF NOT EXISTS fcache (blob_id INTEGER NOT NULL, path_id INTEGER NOT NULL, module_id INTEGER NOT NULL,
  xver_id INTEGER NOT NULL, seg INTEGER NOT NULL, PRIMARY KEY (blob_id, path_id, module_id, xver_id)) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS f_def (seg INTEGER NOT NULL, ord INTEGER NOT NULL, fqn INTEGER NOT NULL,
  PRIMARY KEY (seg, ord)) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS x_use (seg INTEGER NOT NULL, ord INTEGER NOT NULL, to_sym INTEGER NOT NULL,
  status INTEGER NOT NULL, PRIMARY KEY (seg, ord)) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS flow (seg INTEGER NOT NULL, ord INTEGER NOT NULL, source INTEGER, target INTEGER,
  channel INTEGER, PRIMARY KEY (seg, ord)) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS snapshot_file (snapshot_id INTEGER NOT NULL, path_id INTEGER NOT NULL, ord INTEGER NOT NULL,
  blob_id INTEGER, module_id INTEGER, role_id INTEGER, lang_id INTEGER, bytes INTEGER, loc INTEGER, flags INTEGER,
  fseg INTEGER, xseg INTEGER, wseg INTEGER, PRIMARY KEY (snapshot_id, path_id)) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS snapshot_doc (snapshot_id INTEGER NOT NULL, name TEXT NOT NULL, doc_id INTEGER NOT NULL,
  PRIMARY KEY (snapshot_id, name)) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS sf_fseg ON snapshot_file (fseg, snapshot_id);
CREATE INDEX IF NOT EXISTS sf_xseg ON snapshot_file (xseg, snapshot_id);
CREATE INDEX IF NOT EXISTS sf_wseg ON snapshot_file (wseg, snapshot_id);
CREATE INDEX IF NOT EXISTS sf_blob ON snapshot_file (blob_id);
CREATE INDEX IF NOT EXISTS f_def_fqn ON f_def (fqn);
CREATE INDEX IF NOT EXISTS x_use_to ON x_use (to_sym, status);
CREATE INDEX IF NOT EXISTS flow_t ON flow (target);
CREATE INDEX IF NOT EXISTS flow_s ON flow (source);
CREATE INDEX IF NOT EXISTS fcache_seg ON fcache (seg);
CREATE INDEX IF NOT EXISTS sd_doc ON snapshot_doc (doc_id);
"""


def pg_schema() -> str:
    """The same DDL, by PLAN_DB_ARCH.md §4's mechanical substitutions (run against Postgres 17)."""
    sql = SCHEMA_SQLITE
    sql = sql.replace("(id INTEGER PRIMARY KEY,", "(id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,")
    sql = sql.replace(" WITHOUT ROWID", "").replace("BLOB", "BYTEA").replace("INTEGER", "BIGINT")
    sql += "ALTER TABLE blob ALTER z SET STORAGE EXTERNAL;\nALTER TABLE seg ALTER z SET STORAGE EXTERNAL;\n" \
           "ALTER TABLE doc ALTER z SET STORAGE EXTERNAL;\n"
    return sql


def git_blob_sha(raw: bytes) -> bytes:
    return hashlib.sha1(b"blob %d\0" % len(raw) + raw).digest()


def code_text(raw: bytes) -> Optional[str]:
    """`codeindex.build_code`'s text of a file, from its bytes (`util.read_lines`, joined)."""
    if b"\0" in raw[:8192]:
        return None
    return "\n".join(raw.decode("utf-8", errors="replace").splitlines())


def canon(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True).encode("utf-8")


class Encoded(tuple):
    """A segment body already encoded by the caller (an extraction worker): `(sha1 of canon(body),
    zlib of canon(body))`. `_put_segs` stores it as is, byte-identical to encoding `body` here."""

    def __new__(cls, h: bytes, z: bytes) -> "Encoded":
        return tuple.__new__(cls, (h, z))

    def __getnewargs__(self) -> Tuple[bytes, bytes]:     # pickled back from a worker process
        return (self[0], self[1])


def encode_seg(body: Any) -> Encoded:
    raw = canon(body)
    return Encoded(hashlib.sha1(raw).digest(), zlib.compress(raw, ZLEVEL))


ZLEVEL = 6


@contextlib.contextmanager
def _no_gc():
    """Pause the cyclic GC while decoding a whole artifact's segments: JSON values hold no cycles,
    and in a scan's multi-GB heap each collection the allocations trigger walks all of it."""
    was = gc.isenabled()
    gc.disable()
    try:
        yield
    finally:
        if was:
            gc.enable()
_THREAD_MIN_BYTES = 1 << 20


def _compress_many(raws: List[bytes]) -> List[bytes]:
    """`zlib.compress(raw, ZLEVEL)` of each, in order. zlib releases the GIL, so a large batch is
    compressed on threads; the output bytes are the same either way."""
    if len(raws) < 2 or sum(map(len, raws)) < _THREAD_MIN_BYTES:
        return [zlib.compress(r, ZLEVEL) for r in raws]
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=min(8, os.cpu_count() or 1)) as pool:
        return list(pool.map(lambda r: zlib.compress(r, ZLEVEL), raws, chunksize=32))


def _h64(s: str) -> int:
    return struct.unpack(">q", hashlib.sha1(s.encode("utf-8")).digest()[:8])[0]


_XVER: Optional[str] = None


def extractor_version() -> str:
    """Part of the extraction cache key: a hash of the per-file extractor's source (`cdp/lang`
    and the modules it imports) and the Python version (`ast` changes between releases)."""
    global _XVER
    if _XVER is None:
        root = Path(__file__).resolve().parent.parent
        h = hashlib.sha1(sys.version.encode())
        for p in sorted(root.glob("lang/*.py")) + [root / n for n in ("sigs.py", "anchor.py", "rules.py", "util.py")]:
            h.update(p.name.encode() + b"\0" + p.read_bytes())
        _XVER = "xver:" + h.hexdigest()
    return _XVER


class _Pending:
    """A manifest being built: `files` (path -> row of strings/ints) and `docs` (name -> doc id)."""

    def __init__(self, files: Dict[str, Dict], docs: Dict[str, int]) -> None:
        self.files, self.docs = files, docs
        self.staged: Dict[Optional[str], Any] = {}


class ObjectStoreMixin:
    """Needs from the backend: `_x(sql, params)` (cursor), `_xmany(sql, rows)`, `_db_commit()`,
    `_db_rollback()`, `_pg` (bool), `_snapshot_id()`, `_objects_lock()` (a context manager
    factory taking `shared`), `_missing(name)`."""

    _pg = False

    # -------------------------------------------------------------- plumbing

    def _obj_init(self) -> None:
        self._str_ids: Dict[str, int] = {}
        self._id_strs: Dict[int, str] = {}
        self._building: Optional[int] = None
        self._pending: Optional[_Pending] = None
        self._staged_blobs: Dict[str, Tuple[int, bytes]] = {}   # path -> (blob id, sha), before the build
        self._lock_cm = None
        self._view_cache: Dict[int, _Pending] = {}     # committed manifests read this process
        self._bytes_cache: Dict[Tuple[str, int], bytes] = {}   # immutable objects, decompressed
        self._bytes_total = 0
        self._derived: Dict[Any, Any] = {}             # per-view lookup tables (_global_order)
        self._preloaded: Dict[Tuple[Any, str], Any] = {}   # preload_artifact: handed over once

    _BYTES_BUDGET = 256 << 20

    def _cached_bytes(self, kind: str, obj_id: int, load) -> bytes:
        """Objects never change once written, so their decompressed bytes are cached (bounded);
        every caller still gets freshly decoded values, never a shared object."""
        key = (kind, obj_id)
        got = self._bytes_cache.get(key)
        if got is None:
            got = load()
            if self._bytes_total + len(got) > self._BYTES_BUDGET:
                self._bytes_cache, self._bytes_total = {}, 0
            self._bytes_cache[key] = got
            self._bytes_total += len(got)
        return got

    def invalidate_views(self) -> None:
        """Forget cached manifests and object bytes (another process may have committed a
        manifest, or a sweep freed ids a later write reused): the MCP server calls this when
        `snapshot_fingerprint` changes."""
        self._view_cache, self._derived, self._preloaded = {}, {}, {}
        self._bytes_cache, self._bytes_total = {}, 0

    def snapshot_fingerprint(self) -> tuple:
        """Changes whenever what the selected snapshot answers could: another snapshot chosen, its
        manifest recommitted (`touch_seq`), any of its docs rewritten (`state` by a fold), or its
        patch log grown."""
        sid = self._snapshot
        if sid in (None, -1):
            return (sid,)
        meta = self._rows("SELECT touch_seq, complete FROM snapshot_meta WHERE id=?", (sid,))
        docs = self._rows("SELECT name, doc_id FROM snapshot_doc WHERE snapshot_id=? ORDER BY name", (sid,))
        patches = self._rows("SELECT COUNT(*), MAX(id) FROM claim_patch WHERE snapshot_id=?", (sid,))
        return (sid, tuple(map(tuple, meta)), tuple(map(tuple, docs)), tuple(map(tuple, patches)))

    def _q(self, sql: str) -> str:
        if not self._pg:
            return sql
        sql = sql.replace("?", "%s")
        if sql.startswith("INSERT OR IGNORE INTO"):
            sql = "INSERT INTO" + sql[len("INSERT OR IGNORE INTO"):] + " ON CONFLICT DO NOTHING"
        return sql

    def _bin(self, b: bytes):
        if self._pg:
            import psycopg2

            return psycopg2.Binary(b)
        return b

    def _rows(self, sql: str, params: Sequence = ()) -> List[tuple]:
        return list(self._x(self._q(sql), tuple(params)).fetchall())

    def _in_chunks(self, sql: str, ids: Sequence, extra: Sequence = ()) -> List[tuple]:
        """`sql` with one `(%s)` slot for an IN list, run over `ids` 500 at a time."""
        out: List[tuple] = []
        ids = list(ids)
        for i in range(0, len(ids), 500):
            chunk = ids[i:i + 500]
            out += self._rows(sql % ",".join("?" * len(chunk)), list(extra) + chunk)
        return out

    def _hold_objects_lock(self) -> None:
        """Writers hold the store-wide objects lock shared from their first object write to their
        manifest commit, so a concurrent `sweep_objects` cannot free what they are about to cite."""
        if self._lock_cm is None:
            cm = self._objects_lock(True)
            cm.__enter__()
            self._lock_cm = cm

    def _release_objects_lock(self) -> None:
        if self._lock_cm is not None:
            cm, self._lock_cm = self._lock_cm, None
            cm.__exit__(None, None, None)

    # ------------------------------------------------------------ interning

    def _intern(self, strings: Iterable[str]) -> Dict[str, int]:
        want = {s for s in strings if s is not None and s not in self._str_ids}
        if want:
            rows = [(_h64(s), s) for s in sorted(want)]
            self._xmany(self._q("INSERT OR IGNORE INTO str (h64, s) VALUES (?, ?)"), rows)
            by_h = {h: s for h, s in rows}
            for sid, h, s in self._in_chunks("SELECT id, h64, s FROM str WHERE h64 IN (%s)", list(by_h)):
                if by_h[h] != s:
                    raise CdpError("string hash collision in the store: %r vs %r" % (s, by_h[h]))
                self._str_ids[s] = sid
                self._id_strs[sid] = s
            self._db_commit()    # never hold the write lock past a lookup (other repos' scans write too)
        return self._str_ids

    def _strs(self, ids: Iterable[int]) -> Dict[int, str]:
        want = [i for i in set(ids) if i is not None and i not in self._id_strs]
        for sid, s in self._in_chunks("SELECT id, s FROM str WHERE id IN (%s)", want):
            self._id_strs[sid] = s
            self._str_ids[s] = sid
        return self._id_strs

    def _str_id(self, s: str) -> Optional[int]:
        """An existing string's id, without creating it (readers)."""
        if s in self._str_ids:
            return self._str_ids[s]
        rows = self._rows("SELECT id, s FROM str WHERE h64=?", (_h64(s),))
        if rows and rows[0][1] == s:
            self._str_ids[s] = rows[0][0]
            self._id_strs[rows[0][0]] = s
            return rows[0][0]
        return None

    # -------------------------------------------------------------- objects

    def _put_doc(self, obj: Any) -> int:
        self._hold_objects_lock()
        body = canon(obj)
        h = hashlib.sha1(body).digest()
        self._x(self._q("INSERT OR IGNORE INTO doc (h, z) VALUES (?, ?)"), (self._bin(h), self._bin(zlib.compress(body, ZLEVEL))))
        return self._rows("SELECT id FROM doc WHERE h=?", (self._bin(h),))[0][0]

    def _get_doc(self, doc_id: int) -> Any:
        def load() -> bytes:
            rows = self._rows("SELECT z FROM doc WHERE id=?", (doc_id,))
            if not rows:
                raise CdpError("dangling doc %s in the store" % doc_id)
            return zlib.decompress(bytes(rows[0][0]))
        return json.loads(self._cached_bytes("doc", doc_id, load))

    def put_blobs(self, items: Dict[str, Tuple[bytes, bytes]]) -> None:
        """`{path: (git blob sha, raw bytes)}`, staged for the next snapshot this store builds."""
        self._hold_objects_lock()
        shas = list({sha for sha, _ in items.values()})
        have = {bytes(sha): bid for bid, sha in self._in_chunks("SELECT id, sha FROM blob WHERE sha IN (%s)",
                                                                  [self._bin(s) for s in shas])}
        new = {}
        for path, (sha, raw) in items.items():
            if sha not in have and sha not in new:
                new[sha] = raw
        zs = _compress_many(list(new.values()))
        rows = [(self._bin(sha), len(raw), self._bin(z)) for (sha, raw), z in zip(new.items(), zs)]
        for i in range(0, len(rows), BATCH):
            self._xmany(self._q("INSERT OR IGNORE INTO blob (sha, size, z) VALUES (?, ?, ?)"), rows[i:i + BATCH])
            self._db_commit()
        if new:
            for bid, sha in self._in_chunks("SELECT id, sha FROM blob WHERE sha IN (%s)",
                                            [self._bin(s) for s in new]):
                have[bytes(sha)] = bid
        for path, (sha, _) in items.items():
            self._staged_blobs[path] = (have[sha], sha)

    def _blob_bytes(self, blob_ids: Sequence[int]) -> Dict[int, bytes]:
        return {bid: zlib.decompress(bytes(z)) for bid, z in
                self._in_chunks("SELECT id, z FROM blob WHERE id IN (%s) AND z IS NOT NULL", list(blob_ids))}

    def _put_segs(self, bodies: List[Tuple[Any, List[tuple]]], index: Optional[str]) -> List[int]:
        """Content-addressed segments; `index` (`f_def`/`x_use`/`flow`) rows go in only with a new
        segment, so a shared segment's rows exist exactly once. Returns ids in `bodies` order."""
        self._hold_objects_lock()
        enc = []     # (sha1, canonical bytes or None, zlib or None, index rows)
        for body, idx in bodies:
            if isinstance(body, Encoded):
                enc.append((body[0], None, body[1], idx))
            else:
                raw = canon(body)
                enc.append((hashlib.sha1(raw).digest(), raw, None, idx))
        ids: Dict[bytes, int] = {}
        for i in range(0, len(enc), BATCH):
            chunk = enc[i:i + BATCH]
            hs = list({h for h, _, _, _ in chunk})
            have = {bytes(h): sid for sid, h in self._in_chunks("SELECT id, h FROM seg WHERE h IN (%s)",
                                                                  [self._bin(h) for h in hs])}
            new = {}
            for h, raw, z, idx in chunk:
                if h not in have and h not in new:
                    new[h] = (raw, z, idx)
            if new:
                todo = [raw for raw, z, _ in new.values() if z is None]
                done = iter(_compress_many(todo))
                self._xmany(self._q("INSERT OR IGNORE INTO seg (h, z) VALUES (?, ?)"),
                            [(self._bin(h), self._bin(z if z is not None else next(done)))
                             for h, (raw, z, _) in new.items()])
                fresh = {bytes(h): sid for sid, h in self._in_chunks("SELECT id, h FROM seg WHERE h IN (%s)",
                                                                       [self._bin(h) for h in new])}
                if index:
                    rows = [(fresh[h],) + r for h, (_, _, idx) in new.items() for r in idx]
                    if rows:
                        cols = {"f_def": "(seg, ord, fqn) VALUES (?, ?, ?)",
                                "x_use": "(seg, ord, to_sym, status) VALUES (?, ?, ?, ?)",
                                "flow": "(seg, ord, source, target, channel) VALUES (?, ?, ?, ?, ?)"}[index]
                        # A concurrent writer of the same segment inserted the same rows: ignore.
                        self._xmany(self._q("INSERT OR IGNORE INTO %s %s" % (index, cols)), rows)
                have.update(fresh)
            self._db_commit()
            ids.update(have)
        return [ids[h] for h, _, _, _ in enc]

    def _get_segs(self, seg_ids: Iterable[int]) -> Dict[int, Any]:
        ids = sorted(set(seg_ids))
        missing = [i for i in ids if ("seg", i) not in self._bytes_cache]
        if len(missing) <= 64:        # a few files (a query): keep them; a whole artifact: stream
            for sid, z in self._in_chunks("SELECT id, z FROM seg WHERE id IN (%s)", missing):
                self._cached_bytes("seg", sid, lambda z=z: zlib.decompress(bytes(z)))
            return {i: json.loads(self._bytes_cache[("seg", i)]) if ("seg", i) in self._bytes_cache
                    else self._get_segs_uncached([i])[i] for i in ids}
        out = {i: json.loads(self._bytes_cache[("seg", i)]) for i in ids if ("seg", i) in self._bytes_cache}
        out.update(self._get_segs_uncached(missing))
        return out

    def _get_segs_uncached(self, ids: Sequence[int]) -> Dict[int, Any]:
        with _no_gc():
            return {sid: json.loads(zlib.decompress(bytes(z)))
                    for sid, z in self._in_chunks("SELECT id, z FROM seg WHERE id IN (%s)", list(ids))}

    # ----------------------------------------------- extraction cache (fcache)

    def supports_object_store(self) -> bool:
        return True

    def lookup_facts(self, keys: Dict[str, Tuple[bytes, str]]) -> Dict[str, Dict]:
        """`{path: (blob sha, module)}` -> `{path: raw FileFacts dict}` for every cache hit. Blobs
        must already be staged (`put_blobs`)."""
        xver = self._intern([extractor_version()])[extractor_version()]
        ids = self._intern(list(keys) + [m for _, m in keys.values()])
        want = {}
        for path, (sha, module) in keys.items():
            staged = self._staged_blobs.get(path)
            if staged and staged[1] == sha:
                want[(staged[0], ids[path], ids[module])] = path
        hits: Dict[str, int] = {}
        blob_ids = sorted({b for b, _, _ in want})
        for b, p, m, seg in self._in_chunks(
                "SELECT blob_id, path_id, module_id, seg FROM fcache WHERE xver_id=? AND blob_id IN (%s)",
                blob_ids, extra=(xver,)):
            path = want.get((b, p, m))
            if path is not None:
                hits[path] = seg
        bodies = self._get_segs(hits.values())
        return {path: bodies[seg] for path, seg in hits.items()}

    def put_facts(self, facts: Dict[str, Tuple[bytes, str, Any]]) -> None:
        """`{path: (blob sha, module, raw FileFacts dict)}` into the cache. The third item may
        instead be the segment already encoded, `encode_seg({"facts": dict})` (an extraction
        worker's), stored as is."""
        if not facts:
            return
        xver = self._intern([extractor_version()])[extractor_version()]
        ids = self._intern(list(facts) + [m for _, m, _ in facts.values()])
        paths = list(facts)
        seg_ids = self._put_segs([(d if isinstance(d, Encoded) else {"facts": d}, [])
                                  for p in paths for d in (facts[p][2],)], None)
        rows = []
        for path, seg in zip(paths, seg_ids):
            staged = self._staged_blobs.get(path)
            if staged and staged[1] == facts[path][0]:
                rows.append((staged[0], ids[path], ids[facts[path][1]], xver, seg))
        for i in range(0, len(rows), BATCH):
            self._xmany(self._q("INSERT OR IGNORE INTO fcache (blob_id, path_id, module_id, xver_id, seg) "
                                "VALUES (?, ?, ?, ?, ?)"), rows[i:i + BATCH])
            self._db_commit()

    # -------------------------------------------------------------- manifest views

    def _committed_view(self, snapshot_id: int) -> _Pending:
        docs = {name: doc for name, doc in
                self._rows("SELECT name, doc_id FROM snapshot_doc WHERE snapshot_id=?", (snapshot_id,))}
        return _Pending(None, docs)   # files loaded on demand (`_files_of`)

    def _view(self) -> _Pending:
        sid = self._snapshot_id()
        if self._building == sid and self._pending is not None:
            return self._pending
        view = self._view_cache.get(sid)
        if view is None:
            view = self._view_cache[sid] = self._committed_view(sid)
        return view

    def _files_of(self, view: _Pending) -> Dict[str, Dict]:
        """The manifest rows, `ord` order, with strings resolved."""
        if view.files is None:
            rows = self._rows(
                "SELECT path_id, ord, blob_id, module_id, role_id, lang_id, bytes, loc, flags, fseg, xseg, wseg "
                "FROM snapshot_file WHERE snapshot_id=? ORDER BY ord", (self._snapshot_id(),))
            names = self._strs([i for r in rows for i in (r[0], r[3], r[4], r[5])])
            view.files = {}
            for p, o, b, m, r, l, by, loc, fl, f, x, w in rows:
                view.files[names[p]] = {"ord": o, "blob": b, "module": names.get(m), "role": names.get(r),
                                        "language": names.get(l), "bytes": by, "loc": loc, "flags": fl or 0,
                                        "fseg": f, "xseg": x, "wseg": w}
        return view.files

    # ------------------------------------------------------------ builds

    def _begin_build(self, snapshot_id: int, reuse: bool) -> None:
        self._flush_build(complete=True)
        if reuse:
            prior = self._committed_view(snapshot_id)
            saved, self._snapshot = self._snapshot, snapshot_id
            try:
                files = {p: dict(r) for p, r in self._files_of(prior).items()}
            finally:
                self._snapshot = saved
            self._pending = _Pending(files, dict(prior.docs))
        else:
            self._pending = _Pending({}, {})
        self._building = snapshot_id

    def _staging(self) -> Dict:
        """Reports, and (key None) the derived patch, held for the manifest txn (PLAN_DB_ARCH.md §6)."""
        return self._pending.staged if self._pending and self._building == self._snapshot else {}

    def write_report(self, name: Optional[str], data: Any) -> None:
        data = json.loads(json.dumps(data, sort_keys=True))
        if self._pending and self._building == self._snapshot:
            self._pending.staged[name] = data
        else:
            self._put_row(self._snapshot_id(), name, data)
            self._db_commit()

    def write_derived_patch(self, patch: Dict) -> None:
        self.write_report(None, patch)

    def _put_row(self, sid: int, name: Optional[str], data: Any) -> None:
        """Report `name`, or (None) the derived patch: `seq` 0, replaced by every scan. Uncommitted."""
        from .sqlite_backend import _now

        j, x = self._Json(data) if self._pg else json.dumps(data, sort_keys=True), self._x
        if name is not None:
            return x(self._q("INSERT INTO snapshot_report (snapshot_id, name, payload) VALUES (?, ?, ?) "
                             "ON CONFLICT (snapshot_id, name) DO UPDATE SET payload=excluded.payload"), (sid, name, j))
        x(self._q("DELETE FROM claim_patch WHERE snapshot_id=? AND is_derived=?"), (sid, True))
        x(self._q("INSERT INTO claim_patch (snapshot_id, seq, label, content_hash, payload, is_derived, created_at) "
                  "VALUES (?, 0, 'derived', ?, ?, ?, ?)"), (sid, stable_hash(data), j, True, _now()))

    def load_patches(self) -> List[Dict]:
        rows = self._rows("SELECT seq, payload, is_derived FROM claim_patch WHERE snapshot_id=? ORDER BY seq",
                          (self._snapshot_id(),))
        if self._pg:
            self._db_commit()
        d = self._staging().get(None)
        return ([dict(d, patch_no=0)] if d else []) + [dict(p if self._pg else json.loads(p), patch_no=q)
                                                       for q, p, x in rows if not (d and x)]

    def _flush_build(self, complete: bool, discard: bool = False) -> None:
        """Commit a pending manifest that never got its `manifest` artifact (a test, or a command
        that stops early). An exception in flight discards it instead: the previous snapshot stays
        the readable one, and its objects are orphans for the next sweep."""
        if self._building is None:
            return
        if discard:
            self._building, self._pending = None, None
            self._release_objects_lock()
            return
        self._commit_build(complete=complete)

    def _commit_build(self, complete: bool = True) -> None:
        """The one transaction that makes a snapshot's manifest visible."""
        sid, view = self._building, self._pending
        files = view.files
        ids = self._intern([s for p, r in files.items() for s in (p, r.get("module"), r.get("role"), r.get("language"))])
        rows = [(sid, ids[p], r["ord"], r.get("blob"), ids.get(r.get("module")), ids.get(r.get("role")),
                 ids.get(r.get("language")), r.get("bytes"), r.get("loc"), r.get("flags") or 0,
                 r.get("fseg"), r.get("xseg"), r.get("wseg")) for p, r in files.items()]
        try:
            for table in ("snapshot_file", "snapshot_doc"):
                self._x(self._q("DELETE FROM %s WHERE snapshot_id=?" % table), (sid,))
            self._xmany(self._q(
                "INSERT INTO snapshot_file (snapshot_id, path_id, ord, blob_id, module_id, role_id, lang_id, bytes, "
                "loc, flags, fseg, xseg, wseg) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"), rows)
            self._xmany(self._q("INSERT INTO snapshot_doc (snapshot_id, name, doc_id) VALUES (?, ?, ?)"),
                        [(sid, n, d) for n, d in sorted(view.docs.items())])
            for name, data in view.staged.items():
                self._put_row(sid, name, data)
            if complete:
                self._finish_snapshot(sid)
            self._db_commit()
        except BaseException:
            self._db_rollback()
            raise
        self._building, self._pending = None, None
        self._staged_blobs = {}
        self._view_cache, self._derived = {}, {}
        self._release_objects_lock()

    # ------------------------------------------------------------ artifacts

    def preload_artifact(self, name: str) -> None:
        """Read `name` now and hand that value to the next `read_artifact(name)` of this snapshot
        (once: every read still gets a value no other caller holds). Lets a caller build a
        long-lived value before `gc.freeze()` when the code that reads it is not its own."""
        if self.has_artifact(name):
            self._preloaded[(self._snapshot, name)] = self.read_artifact(name)

    def read_artifact(self, name: str, default: Any = None) -> Any:
        got = self._preloaded.pop((self._snapshot, name), None) if self._preloaded else None
        if got is not None:
            return got
        if self._snapshot == -1:
            if default is None:
                raise CdpError(self._missing(name))
            return default
        view = self._view()
        doc = view.docs.get(name)
        if doc is None:
            if default is None:
                raise CdpError(self._missing(name))
            return default
        return self._assemble(name, view, self._get_doc(doc))

    def has_artifact(self, name: str) -> bool:
        if self._snapshot == -1:
            return False
        return name in self._view().docs

    def write_artifact(self, name: str, data: Any) -> None:
        sid = self._snapshot_id()
        self._derived, self._preloaded = {}, {}
        if self._building == sid:
            view = self._pending
            view.docs[name] = self._decompose(name, data, view)
            if name == "manifest":
                self._commit_build()
            return
        # A write outside a build applies to the committed manifest in one transaction.
        if name not in HEAVY:
            doc = self._whole(data)
            self._x(self._q("INSERT INTO snapshot_doc (snapshot_id, name, doc_id) VALUES (?, ?, ?) "
                            "ON CONFLICT (snapshot_id, name) DO UPDATE SET doc_id=excluded.doc_id"), (sid, name, doc))
            self._db_commit()
            self._view_cache.pop(sid, None)
            if not self._staged_blobs:
                self._release_objects_lock()
            return
        view = self._committed_view(sid)
        self._files_of(view)
        view.docs[name] = self._decompose(name, data, view)
        self._building, self._pending = sid, view
        self._commit_build(complete=False)

    def _whole(self, data: Any) -> int:
        if isinstance(data, dict) and PARTS in data:
            data = {WHOLE: data}
        return self._put_doc(data)

    def _decompose(self, name: str, data: Any, view: _Pending) -> int:
        with _no_gc():
            return self._decompose_parts(name, data, view)

    def _decompose_parts(self, name: str, data: Any, view: _Pending) -> int:
        if name not in HEAVY or not isinstance(data, dict):
            return self._whole(data)
        try:
            skel = getattr(self, "_split_" + name)(data, view)
        except _NotDecomposable:
            skel = None
        if skel is None:
            return self._whole(data)
        return self._put_doc(dict(skel, **{PARTS: name}))

    def _split_inventory(self, data: Dict, view: _Pending) -> Optional[Dict]:
        files = data.get("files")
        if not isinstance(files, list):
            return None
        seen = set()
        for f in files:
            if not isinstance(f, dict) or sorted(f) != list(INV_KEYS) or not isinstance(f["path"], str) \
                    or f["path"] in seen or not isinstance(f["binary"], bool) \
                    or not all(isinstance(f[k], int) and not isinstance(f[k], bool) for k in ("bytes", "loc")) \
                    or not all(isinstance(f[k], str) for k in ("language", "module", "role")):
                return None
            seen.add(f["path"])
        old = view.files or {}
        staged = self._staged_blobs
        new = {}
        for i, f in enumerate(files):
            prev = old.get(f["path"], {})
            blob = staged[f["path"]][0] if f["path"] in staged else prev.get("blob")
            new[f["path"]] = {"ord": i, "blob": blob, "module": f["module"], "role": f["role"],
                              "language": f["language"], "bytes": f["bytes"], "loc": f["loc"],
                              "flags": F_BINARY if f["binary"] else 0,
                              "fseg": None, "xseg": None, "wseg": None}
        others = [o for o in ("extract", "dataflow", "code", "xref") if o in view.docs]
        if view.files is not None and list(old) == list(new):
            # Same files in the same order (a rescan): the other artifacts' parts still line up.
            for p, r in new.items():
                for k in ("fseg", "xseg", "wseg"):
                    r[k] = old[p].get(k)
                r["flags"] |= (old[p].get("flags") or 0) & F_CODE
        elif others:
            # A different file set: re-split the other heavy artifacts against it (only a test
            # rewrites inventory alone; scan and refresh write every artifact after it).
            values = {o: self._assemble(o, view, self._get_doc(view.docs[o])) for o in others}
            view.files = new
            for o in others:
                view.docs[o] = self._decompose(o, values[o], view)
        view.files = new
        return {"rest": {k: v for k, v in data.items() if k != "files"}}

    def _per_file(self, rows: Any, key, pos: Dict[str, int]) -> Tuple[Dict[str, List], List[List[int]]]:
        if not isinstance(rows, list):
            raise _NotDecomposable()
        per: Dict[str, List] = {}
        runs: List[List[int]] = []
        for row in rows:
            f = key(row) if isinstance(row, dict) else None
            p = pos.get(f) if isinstance(f, str) else None
            if p is None:
                raise _NotDecomposable()
            per.setdefault(f, []).append(row)
            if runs and runs[-1][0] == p:
                runs[-1][1] += 1
            else:
                runs.append([p, 1])
        return per, runs

    def _positions(self, view: _Pending) -> Dict[str, int]:
        files = view.files if view.files is not None else self._files_of(view)
        return {p: r["ord"] for p, r in files.items()}

    def _split_extract(self, data: Dict, view: _Pending) -> Optional[Dict]:
        pos = self._positions(view)
        if not pos or not isinstance(data.get("files"), dict) or any(p not in pos for p in data["files"]):
            return None
        lists = [k for k in EXTRACT_LISTS if k in data]
        per: Dict[str, Dict[str, List]] = {}
        runs = {}
        for k in lists:
            rows, runs[k] = self._per_file(data[k], lambda r: r.get("file"), pos)
            for p, rs in rows.items():
                per.setdefault(p, {})[k] = rs
        for p, meta in data["files"].items():
            per.setdefault(p, {})["meta"] = meta
        paths = sorted(per, key=pos.get)
        fqns = self._intern(str(r.get("fqn")) for p in paths for r in per[p].get("defines", ()))
        bodies = [(per[p], [(i, fqns[str(r.get("fqn"))]) for i, r in enumerate(per[p].get("defines", ()))])
                  for p in paths]
        for p, sid in zip(paths, self._put_segs(bodies, "f_def")):
            view.files[p]["fseg"] = sid
        for p in set(view.files) - set(per):
            view.files[p]["fseg"] = None
        rest = {k: v for k, v in data.items() if k not in lists and k != "files"}
        return {"rest": rest, "lists": lists, "runs": runs}

    def _split_xref(self, data: Dict, view: _Pending) -> Optional[Dict]:
        pos = self._positions(view)
        if not pos or not isinstance(data.get("uses"), list):
            return None
        rows, runs = self._per_file(data["uses"], lambda r: r.get("from_file"), pos)
        from .. import resolve as resolve_mod

        derived = []
        try:
            if "used_by" in data and _same(data["used_by"], resolve_mod._transpose(data["uses"])):
                derived.append("used_by")
        except (KeyError, TypeError):
            pass
        paths = sorted(rows, key=pos.get)
        keys = self._intern(str(r.get("fqn")) for p in paths for r in rows[p])
        bodies = [({"uses": rows[p]},
                   [(i, keys[str(r.get("fqn"))], USED_BY_STATUS[r.get("resolved")])
                    for i, r in enumerate(rows[p]) if r.get("resolved") in USED_BY_STATUS])
                  for p in paths]
        for p, sid in zip(paths, self._put_segs(bodies, "x_use")):
            view.files[p]["xseg"] = sid
        for p in set(view.files) - set(rows):
            view.files[p]["xseg"] = None
        # `symbols` (one entry per fqn, not per file) is its own doc, so a field read of the
        # skeleton (`routes`, `constants`) does not parse it; `f_def` serves point lookups.
        skel = {"rest": {k: v for k, v in data.items() if k not in ("uses", "symbols") and k not in derived},
                "runs": {"uses": runs}, "derived": derived}
        if "symbols" in data:
            skel["symbols_doc"] = self._put_doc(data["symbols"])
        return skel

    def _split_dataflow(self, data: Dict, view: _Pending) -> Optional[Dict]:
        pos = self._positions(view)
        if not pos or not isinstance(data.get("edges"), list):
            return None
        rows, runs = self._per_file(
            data["edges"], lambda r: (r.get("anchor") or {}).get("file") if isinstance(r.get("anchor"), dict) else None, pos)
        paths = sorted(rows, key=pos.get)
        names = self._intern(str(r.get(k)) for p in paths for r in rows[p] for k in ("source", "target", "channel"))
        bodies = [({"edges": rows[p]},
                   [(i, names[str(r.get("source"))], names[str(r.get("target"))], names[str(r.get("channel"))])
                    for i, r in enumerate(rows[p])]) for p in paths]
        for p, sid in zip(paths, self._put_segs(bodies, "flow")):
            view.files[p]["wseg"] = sid
        for p in set(view.files) - set(rows):
            view.files[p]["wseg"] = None
        return {"rest": {k: v for k, v in data.items() if k != "edges"}, "runs": {"edges": runs}}

    def _split_code(self, data: Dict, view: _Pending) -> Optional[Dict]:
        files = data.get("files")
        if not isinstance(files, dict) or view.files is None and not self._files_of(view):
            return None
        rows = view.files
        if any(p not in rows or rows[p].get("blob") is None or not isinstance(t, str) for p, t in files.items()):
            return None
        raw = self._blob_bytes([rows[p]["blob"] for p in files])
        for p, text in files.items():
            if rows[p]["blob"] not in raw or code_text(raw[rows[p]["blob"]]) != text:
                return None
        for p, r in rows.items():
            r["flags"] = (r.get("flags") or 0) & ~F_CODE | (F_CODE if p in files else 0)
        return {"rest": {k: v for k, v in data.items() if k != "files"}}

    # ------------------------------------------------------------ reassembly

    def _assemble(self, name: str, view: _Pending, skel: Any) -> Any:
        with _no_gc():
            return self._assemble_parts(name, view, skel)

    def _assemble_parts(self, name: str, view: _Pending, skel: Any) -> Any:
        if not isinstance(skel, dict):
            return skel
        if WHOLE in skel and len(skel) == 1:
            return skel[WHOLE]
        if PARTS not in skel:
            return skel
        files = view.files if view.files is not None else self._files_of(view)
        order = sorted(files, key=lambda p: files[p]["ord"])
        out = dict(skel["rest"])
        kind = skel[PARTS]
        if kind == "inventory":
            out["files"] = [{"binary": bool(files[p]["flags"] & F_BINARY), "bytes": files[p]["bytes"],
                             "language": files[p]["language"], "loc": files[p]["loc"], "module": files[p]["module"],
                             "path": p, "role": files[p]["role"]} for p in order]
        elif kind == "extract":
            segs = self._get_segs(files[p]["fseg"] for p in order if files[p].get("fseg"))
            bodies = {p: segs[files[p]["fseg"]] for p in order if files[p].get("fseg")}
            for k in skel["lists"]:
                out[k] = _interleave(skel["runs"][k], order, {p: b.get(k, []) for p, b in bodies.items()})
            out["files"] = {p: bodies[p]["meta"] for p in sorted(bodies) if "meta" in bodies[p]}
        elif kind == "xref":
            segs = self._get_segs(files[p]["xseg"] for p in order if files[p].get("xseg"))
            out["uses"] = _interleave(skel["runs"]["uses"], order,
                                      {p: segs[files[p]["xseg"]]["uses"] for p in order if files[p].get("xseg")})
            from .. import resolve as resolve_mod

            if "used_by" in skel.get("derived", ()):
                out["used_by"] = {k: [_user(u) for u in v] for k, v in resolve_mod._transpose(out["uses"]).items()}
            if "symbols_doc" in skel:
                out["symbols"] = self._get_doc(skel["symbols_doc"])
        elif kind == "dataflow":
            segs = self._get_segs(files[p]["wseg"] for p in order if files[p].get("wseg"))
            out["edges"] = _interleave(skel["runs"]["edges"], order,
                                       {p: segs[files[p]["wseg"]]["edges"] for p in order if files[p].get("wseg")})
        elif kind == "code":
            code = [p for p in order if files[p]["flags"] & F_CODE]
            raw = self._blob_bytes([files[p]["blob"] for p in code])
            out["files"] = {p: code_text(raw[files[p]["blob"]]) for p in sorted(code)}
        # Key order as before (every value read back key-sorted, json sort_keys): rows and docs
        # come from canonical JSON already; only this level and `used_by` are built here.
        return dict(sorted(out.items()))

    # ------------------------------------------------------------ typed reads (hot queries)
    #
    # What `query.Store`'s views use instead of whole artifacts: each returns exactly what the
    # matching slice of `read_artifact` would (same rows, same order, key-sorted dicts).

    def current_files(self) -> Dict[str, Dict]:
        """The selected snapshot's manifest rows, by path (strings resolved)."""
        return self._files_of(self._view())

    def parts_skeleton(self, name: str) -> Optional[Dict]:
        """The skeleton of a decomposed artifact of the selected snapshot, else None (whole or absent)."""
        if self._snapshot == -1:
            return None
        view = self._view()
        key = (id(view), "skel", name)
        if key in self._derived:
            return self._derived[key]
        doc = view.docs.get(name)
        if doc is None:
            return None
        d = self._get_doc(doc)
        self._derived[key] = d if isinstance(d, dict) and PARTS in d else None
        return self._derived[key]

    def artifact_field(self, name: str, key: str, default: Any = None) -> Any:
        """One top-level field of an artifact without assembling the rest (`xref.routes`)."""
        skel = self.parts_skeleton(name)
        if skel is None:
            return self.read_artifact(name, {}).get(key, default)
        if key == "symbols" and "symbols_doc" in skel:
            return self._get_doc(skel["symbols_doc"])
        return self._get_doc(self._view().docs[name])["rest"].get(key, default)    # a fresh value

    def _snapshot_segs(self, col: str) -> Dict[int, str]:
        key = (id(self._view()), "segs", col)
        if key not in self._derived:
            self._derived[key] = {r[col]: p for p, r in self.current_files().items() if r.get(col)}
        return self._derived[key]

    def _global_order(self, skel: Dict, list_name: str):
        """`(path, local index) -> global index` of a decomposed list, from its run lengths."""
        key = (id(self._view()), "order", list_name)
        if key not in self._derived:
            self._derived[key] = self._build_global_order(skel, list_name)
        return self._derived[key]

    def _build_global_order(self, skel: Dict, list_name: str):
        files = self.current_files()
        order = sorted(files, key=lambda p: files[p]["ord"])
        spans: Dict[str, List[Tuple[int, int, int]]] = {}
        g, seen = 0, {}
        for pos, n in skel["runs"][list_name]:
            path = order[pos]
            local = seen.get(path, 0)
            spans.setdefault(path, []).append((local, g, n))
            seen[path] = local + n
            g += n

        def index(path: str, i: int) -> int:
            for local, start, n in spans.get(path, ()):
                if local <= i < local + n:
                    return start + i - local
            return -1
        return index

    def symbol_keys(self) -> List[str]:
        """Every fqn defined in the selected snapshot, sorted (the keys of `xref.symbols`)."""
        rows = self._rows("SELECT DISTINCT d.fqn FROM f_def d JOIN snapshot_file f ON f.fseg = d.seg "
                          "WHERE f.snapshot_id=?", (self._snapshot_id(),))
        names = self._strs(r[0] for r in rows)
        return sorted(names[r[0]] for r in rows)

    def defines_of(self, fqns: Sequence[str]) -> Dict[str, List[Dict]]:
        """`fqn -> its extract.defines rows`, in `extract.defines` order, through `f_def`."""
        skel = self.parts_skeleton("extract")
        seg_path = self._snapshot_segs("fseg")
        ids = {i: f for f in fqns for i in [self._str_id(f)] if i is not None}
        hits = [(seg, o, fqn) for seg, o, fqn in
                self._in_chunks("SELECT seg, ord, fqn FROM f_def WHERE fqn IN (%s)", list(ids)) if seg in seg_path]
        if not hits:
            return {}
        segs = self._get_segs(seg for seg, _, _ in hits)
        index = self._global_order(skel, "defines")
        out: Dict[str, List[Tuple[int, Dict]]] = {}
        for seg, o, fqn in hits:
            out.setdefault(ids[fqn], []).append((index(seg_path[seg], o), segs[seg]["defines"][o]))
        return {f: [r for _, r in sorted(rows, key=lambda t: t[0])] for f, rows in out.items()}

    def symbol_entries(self, fqns: Sequence[str]) -> Dict[str, Dict]:
        """`xref.symbols[fqn]` for each fqn defined here, computed from its define rows exactly as
        `build_xref` does (`resolve.symbol_entry`)."""
        from .. import resolve as resolve_mod

        rows = self.defines_of(fqns)
        if not rows:
            return {}
        key = (id(self._view()), "symbol-inputs")
        if key not in self._derived:     # read-only inputs, kept for the next lookup
            self._derived[key] = ({p: r["role"] for p, r in self.current_files().items()},
                                  self.artifact_field("xref", "constants", {}) or {})
        role_of, constants = self._derived[key]
        return {f: json.loads(canon(resolve_mod.symbol_entry(f, rs, role_of, constants))) for f, rs in rows.items()}

    def used_by_keys(self) -> List[str]:
        rows = self._rows("SELECT DISTINCT u.to_sym FROM x_use u JOIN snapshot_file f ON f.xseg = u.seg "
                          "WHERE f.snapshot_id=?", (self._snapshot_id(),))
        names = self._strs(r[0] for r in rows)
        return sorted(names[r[0]] for r in rows)

    def used_by_entries(self, fqns: Sequence[str]) -> Dict[str, List[Dict]]:
        """`xref.used_by[fqn]` through `x_use`: the uses resolving to it, sorted as `_transpose`
        sorts them (ties are within one file, where segment order is snapshot order)."""
        files = self.current_files()
        seg_path = self._snapshot_segs("xseg")
        ids = {i: f for f in fqns for i in [self._str_id(f)] if i is not None}
        hits = [(seg, o, fqn) for seg, o, fqn in
                self._in_chunks("SELECT seg, ord, to_sym FROM x_use WHERE to_sym IN (%s)", list(ids)) if seg in seg_path]
        segs = self._get_segs(seg for seg, _, _ in hits)
        out: Dict[str, List[Dict]] = {}
        for seg, o, fqn in sorted(hits, key=lambda h: (files[seg_path[h[0]]]["ord"], h[1])):
            u = segs[seg]["uses"][o]
            out.setdefault(ids[fqn], []).append(
                {"anchor": dict(u["anchor"]), "file": u["from_file"], "module": u["from_module"]})
        return {k: sorted(v, key=lambda r: (r["module"], r["file"], r["anchor"]["line"])) for k, v in out.items()}

    def file_part(self, name: str, path: str) -> Optional[Dict]:
        """One file's segment of a decomposed artifact (extract: its lists and `meta`; xref:
        `uses`; dataflow: `edges`), or None when the file has none."""
        col = {"extract": "fseg", "xref": "xseg", "dataflow": "wseg"}[name]
        row = self.current_files().get(path)
        if not row or not row.get(col):
            return None
        return self._get_segs([row[col]])[row[col]]

    def code_texts(self, paths: Optional[Sequence[str]] = None) -> Dict[str, str]:
        """`code.files` (or the given paths of it), path-sorted."""
        files = self.current_files()
        want = [p for p in (files if paths is None else paths) if p in files and files[p]["flags"] & F_CODE]
        raw = self._blob_bytes(sorted({files[p]["blob"] for p in want}))
        return {p: code_text(raw[files[p]["blob"]]) for p in sorted(want)}

    # ------------------------------------------------------------ gc

    def sweep_objects(self, dry_run: bool = False) -> Optional[Dict[str, int]]:
        """Mark-and-sweep of every object no snapshot manifest or doc reaches, under the objects
        lock held exclusive (non-blocking: None when a writer holds it -- `sweep deferred`)."""
        try:
            cm = self._objects_lock(False, timeout_s=0.0)
            cm.__enter__()
        except CdpError:
            return None
        try:
            live_seg = "SELECT fseg FROM snapshot_file WHERE fseg IS NOT NULL UNION " \
                       "SELECT xseg FROM snapshot_file WHERE xseg IS NOT NULL UNION " \
                       "SELECT wseg FROM snapshot_file WHERE wseg IS NOT NULL UNION SELECT seg FROM fcache"
            counts: Dict[str, int] = {}
            # The extraction cache is kept only for blobs a snapshot still holds.
            dead = [("fcache", "blob_id NOT IN (SELECT blob_id FROM snapshot_file WHERE blob_id IS NOT NULL)"),
                    ("seg", "id NOT IN (%s)" % live_seg),
                    ("f_def", "seg NOT IN (SELECT id FROM seg)"),
                    ("x_use", "seg NOT IN (SELECT id FROM seg)"),
                    ("flow", "seg NOT IN (SELECT id FROM seg)"),
                    ("blob", "id NOT IN (SELECT blob_id FROM snapshot_file WHERE blob_id IS NOT NULL)"),
                    ("doc", "id NOT IN (SELECT id FROM live_doc)")]
            # docs a skeleton cites (`symbols_doc`) are live with the skeleton that cites them
            self._x(self._q("CREATE TEMP TABLE IF NOT EXISTS live_doc (id BIGINT PRIMARY KEY)"), ())
            self._x(self._q("DELETE FROM live_doc"), ())
            self._x(self._q("INSERT INTO live_doc (id) SELECT DISTINCT doc_id FROM snapshot_doc"), ())
            cited = []
            for (doc_id,) in self._rows("SELECT DISTINCT doc_id FROM snapshot_doc WHERE name='xref'"):
                skel = self._get_doc(doc_id)
                if isinstance(skel, dict) and skel.get("symbols_doc"):
                    cited.append((skel["symbols_doc"],))
            self._xmany(self._q("INSERT OR IGNORE INTO live_doc (id) VALUES (?)"), cited)
            for table, where in dead:
                n = self._rows("SELECT COUNT(*) FROM %s WHERE %s" % (table, where))[0][0]
                counts[table] = n
                if n and not dry_run:
                    self._x(self._q("DELETE FROM %s WHERE %s" % (table, where)), ())
                    self._db_commit()
            return counts
        finally:
            cm.__exit__(None, None, None)

    def dangling_references(self) -> List[str]:
        """`verify --full`: manifest/doc references to objects that do not exist."""
        out = []
        for col in ("fseg", "xseg", "wseg"):
            n = self._rows("SELECT COUNT(*) FROM snapshot_file WHERE %s IS NOT NULL AND %s NOT IN (SELECT id FROM seg)"
                           % (col, col))[0][0]
            if n:
                out.append("%d snapshot_file.%s reference(s) to a missing segment" % (n, col))
        n = self._rows("SELECT COUNT(*) FROM snapshot_file WHERE blob_id IS NOT NULL "
                       "AND blob_id NOT IN (SELECT id FROM blob)")[0][0]
        if n:
            out.append("%d snapshot_file.blob_id reference(s) to a missing blob" % n)
        n = self._rows("SELECT COUNT(*) FROM snapshot_doc WHERE doc_id NOT IN (SELECT id FROM doc)")[0][0]
        if n:
            out.append("%d snapshot_doc reference(s) to a missing doc" % n)
        for (doc_id,) in self._rows("SELECT DISTINCT doc_id FROM snapshot_doc WHERE name='xref'"):
            skel = self._get_doc(doc_id) if self._rows("SELECT 1 FROM doc WHERE id=?", (doc_id,)) else None
            if isinstance(skel, dict) and skel.get("symbols_doc") and \
                    not self._rows("SELECT 1 FROM doc WHERE id=?", (skel["symbols_doc"],)):
                out.append("xref doc %s cites a missing symbols doc" % doc_id)
        return out


class _NotDecomposable(Exception):
    pass


def _user(u: Dict) -> Dict:
    """A `used_by` entry as it read back from JSON: sorted keys, its own anchor dict."""
    return {"anchor": dict(u["anchor"]), "file": u["file"], "module": u["module"]}


def _same(a: Any, b: Any) -> bool:
    return a == b or canon(a) == canon(b)


def _interleave(runs: List[List[int]], order: List[str], per: Dict[str, List]) -> List:
    out: List = []
    cursor: Dict[str, int] = {}
    for p, n in runs:
        path = order[p]
        i = cursor.get(path, 0)
        out.extend(per[path][i:i + n])
        cursor[path] = i + n
    return out
