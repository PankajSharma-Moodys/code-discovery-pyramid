"""Typed reads of the content-addressed object store (`ObjectStoreMixin` inherits them).

What `query.Store`'s views use instead of whole artifacts. They rely on the object-store plumbing
of `objects.ObjectStoreMixin` (`_view`, `_get_doc`, `_get_segs`, `_rows`, ...); split out of
`objects.py` only to keep that module under the size cap. `objects.py` imports this module, so the
shared primitives it defines are imported inside the methods that need them.
"""

from __future__ import annotations

import json
import re
import zlib
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

_SEG_COL = {"extract": "fseg", "xref": "xseg", "dataflow": "wseg"}
_USES_CUT = b', "uses": '
_OWNER = re.compile(rb'"fqn": "([^"#\\]*)([#"\\])')


class ObjectReadMixin:
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
        from .objects import PARTS

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
        from .objects import canon

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
        col = _SEG_COL[name]
        row = self.current_files().get(path)
        if not row or not row.get(col):
            return None
        return self._get_segs([row[col]])[row[col]]

    def segments(self, name: str, paths: Iterable[str]) -> Dict[str, Dict]:
        """`path -> file_part(name, path)` for each of `paths` that has a segment, in one read."""
        col = _SEG_COL[name]
        files = self.current_files()
        need = {files[p][col]: p for p in paths if files.get(p, {}).get(col)}
        return {need[sid]: seg for sid, seg in self._get_segs(need).items()}

    def _raw_segments(self, col: str, paths=None, cut: Optional[bytes] = None):
        """`(path, inflated canonical JSON of its `col` segment)`, unparsed; with `cut`, only the
        bytes before it (cached apart from whole segments, bounded like them)."""
        files = self.current_files()
        path_of = {r[col]: p for p, r in files.items() if r.get(col) and (paths is None or p in paths)}
        kind = "seg" if cut is None else "seg:" + cut.decode()
        have = {sid: self._bytes_cache[(kind, sid)] for sid in path_of if (kind, sid) in self._bytes_cache}
        for sid, z in self._in_chunks("SELECT id, z FROM seg WHERE id IN (%s)", [i for i in path_of if i not in have]):
            def load(z=z) -> bytes:
                raw = zlib.decompress(bytes(z))
                at = raw.find(cut) if cut is not None else -1
                return raw[:at] + b"}" if at >= 0 else raw
            have[sid] = self._cached_bytes(kind, sid, load)
        for sid in sorted(have, key=lambda i: files[path_of[i]]["ord"]):
            yield path_of[sid], have[sid]

    def extract_heads(self, needles: Sequence[str] = (), paths: Optional[Iterable[str]] = None) -> Dict[str, Dict]:
        """`path -> its extract segment`, read without parsing its `uses` (canonical JSON sorts that
        list after every other), for the files (of `paths`, when given) whose other rows hold the
        start of a JSON string beginning with one of `needles` -- any file, when there are none. A segment whose cut does
        not land on the top-level key is parsed whole (it then also carries `uses`)."""
        pats = [json.dumps(n)[:-1].encode() for n in needles]    # the string's opening, any ending
        per = {}
        for path, head in self._raw_segments("fseg", None if paths is None else set(paths), _USES_CUT):
            if pats and not any(p in head for p in pats):
                continue
            try:   # parses only when the cut is at the top-level key (any other leaves brackets open)
                per[path] = json.loads(head)
            except ValueError:
                per[path] = self.file_part("extract", path)
        return per

    def call_owners(self) -> Dict[str, Tuple[Optional[frozenset], bool]]:
        """`path -> (the owners O of every "fqn": "O#.." / "O" in its xref uses, None when one is
        escaped; whether it has a binding use)`, scanned from the raw segments, never parsed."""
        key = (id(self._view()), "owners")
        if key not in self._derived:
            out = {}
            for path, raw in self._raw_segments("xseg"):
                found = _OWNER.findall(raw)
                out[path] = (None if any(e == b"\\" for _, e in found) else frozenset(o for o, _ in found),
                             b'"kind": "binding"' in raw)
            self._derived[key] = out
        return self._derived[key]

    def code_texts(self, paths: Optional[Sequence[str]] = None) -> Dict[str, str]:
        """`code.files` (or the given paths of it), path-sorted."""
        from .objects import F_CODE, code_text

        files = self.current_files()
        want = [p for p in (files if paths is None else paths) if p in files and files[p]["flags"] & F_CODE]
        raw = self._blob_bytes(sorted({files[p]["blob"] for p in want}))
        return {p: code_text(raw[files[p]["blob"]]) for p in sorted(want)}
