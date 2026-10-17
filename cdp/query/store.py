"""The loaded state a query reads."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterator, List, Mapping, Optional, Union

from ..store import SqliteStore, WorkspaceStore
from ..util import CdpError


class Store:
    """Lazily-loaded view over a workspace store.

    Accepts a `WorkspaceStore` directly, or a `Path`/`str` for convenience --
    a bare directory is wrapped as `SqliteStore(dir/index.db)`, the CLI's own
    default (D3, `PHASE/FINDINGS.md`). There is no `FileStore` fallback: every
    production write path constructs `SqliteStore`, so a directory with no
    `index.db` has no state to read, full stop. Reading and writing state
    itself is `store/`'s job (R1); this class only caches rows and exposes
    the properties every renderer and query reads.
    """

    def __init__(self, backend: Union["WorkspaceStore", Path, str], use_latest: bool = True) -> None:
        if isinstance(backend, WorkspaceStore):
            self.backend = backend
        else:
            db = Path(backend) / "index.db"
            if not db.is_file():
                raise CdpError("no CDP state at %s — run `scan` first" % backend)
            self.backend = SqliteStore(db)
        # A view over the store reads the *current* state by default -- the
        # most recent snapshot, not whichever one `_snapshot_id()`'s lazy
        # `id=1` fallback happens to land on. See `use_latest_snapshot`'s
        # docstring for the bug this closes. `use_latest=False` opts out --
        # for a caller that already activated a specific snapshot itself
        # (e.g. `cdp diff`'s sha mode via `use_snapshot`), this call would
        # otherwise silently override that choice back to "latest".
        # Only when nothing was chosen: a store opened for one repo
        # (`cli._open_store`) already points at that repo's snapshot, and "the
        # latest in the file" would now be some other repo's.
        if use_latest and not self.backend.has_selection():
            self.backend.use_latest_snapshot()
        self._caches: Dict[Any, Dict[str, Any]] = {}

    @property
    def _cache(self) -> Dict[str, Any]:
        """Loaded artifacts and derived indexes, per selected snapshot: a cached value never
        answers for another snapshot after the backend's selection moves (`begin_snapshot`,
        `use_snapshot`). Assigning replaces the current snapshot's cache."""
        return self._caches.setdefault(getattr(self.backend, "_snapshot", None), {})

    @_cache.setter
    def _cache(self, value: Dict[str, Any]) -> None:
        self._caches[getattr(self.backend, "_snapshot", None)] = value

    def forget(self) -> None:
        """Drop every cached value (the MCP server, when its snapshot moved or was rewritten)."""
        self._caches = {}

    @property
    def choice(self):
        """How the chosen snapshot relates to the tree on disk (`snapshot.Choice`), if known."""
        return getattr(self.backend, "choice", None)

    def close(self) -> None:
        self.backend.close()

    def _load(self, name: str, default: Any = None) -> Any:
        if name not in self._cache:
            self._cache[name] = self.backend.read_artifact(name, default)
        return self._cache[name]

    inventory = property(lambda self: self._load("inventory"))
    extraction = property(lambda self: self._load("extract"))
    graph = property(lambda self: self._load("graph"))
    partition = property(lambda self: self._load("partition"))
    xref = property(lambda self: self._load("xref"))
    state = property(lambda self: self._load("state", {"claims": [], "unknowns": [], "conflicts": []}))
    dataflow = property(lambda self: self._load("dataflow", {"edges": [], "paths": [], "process_boundaries": []}))
    code = property(lambda self: self._load("code", {}))
    manifest = property(lambda self: self._load("manifest", {}))

    def node_of(self, path: str) -> Optional[str]:
        for scope in self.partition["scopes"]:
            if path in scope["files"]:
                return scope["node"]
        return None

    # ---------------------------------------------------------------- typed reads
    #
    # The hot query paths read through these instead of whole artifacts. On a store whose heavy
    # artifacts are per-file parts (`store/objects.py`) each reads only what it names; otherwise --
    # or once the whole artifact is loaded anyway -- it is a slice of the loaded dict. Either way
    # the value is the same, so an answer cannot depend on which path served it.

    def _parts(self, name: str) -> bool:
        if name in self._cache or not getattr(self.backend, "supports_object_store", lambda: False)():
            return False
        key = "_parts:" + name
        if key not in self._cache:
            self._cache[key] = self.backend.parts_skeleton(name) is not None
        return self._cache[key]

    def _memo(self, key: str, build) -> Any:
        if key not in self._cache:
            self._cache[key] = build()
        return self._cache[key]

    @property
    def symbols(self) -> Mapping:
        """`xref.symbols`."""
        if not self._parts("xref"):
            return self.xref["symbols"]
        b = self.backend
        return self._memo("_v:symbols", lambda: LazyMap(b.symbol_keys, b.symbol_entries,
                                                         lambda: b.artifact_field("xref", "symbols")))

    @property
    def used_by(self) -> Mapping:
        """`xref.used_by`."""
        if not self._parts("xref"):
            return self.xref["used_by"]
        b = self.backend
        return self._memo("_v:used_by", lambda: LazyMap(b.used_by_keys, b.used_by_entries,
                                                         lambda: self.xref["used_by"]))

    def xref_field(self, key: str) -> Any:
        """`xref[key]` for a field other than symbols/used_by/uses (routes, constants, ...)."""
        if not self._parts("xref"):
            return self.xref[key]
        return self._memo("_f:xref:" + key, lambda: self.backend.artifact_field("xref", key))

    def file_extract(self, path: str) -> Dict[str, Any]:
        """One file's extract rows: `{defines, uses, imports, io_edges, rule_edges: [...], meta}`
        (`meta` is `extraction["files"][path]`, absent when the file has none)."""
        if self._parts("extract"):
            part = self._memo("_f:extract:" + path, lambda: self.backend.file_part("extract", path) or {})
            return part
        return _by_file(self, "extract").get(path, {})

    def has_rule_edges(self) -> bool:
        """Whether `extract.rule_edges` is non-empty (it decides `rules.all_edges`' order)."""
        if not self._parts("extract"):
            return bool(self.extraction.get("rule_edges"))
        skel = self._memo("_skel:extract", lambda: self.backend.parts_skeleton("extract"))
        return bool(skel["runs"].get("rule_edges"))

    def defines_named(self, fqn: str) -> List[Dict]:
        """`[d for d in extract.defines if d["fqn"] == fqn]`, in that order."""
        if not self._parts("extract"):
            return [d for d in self.extraction["defines"] if d["fqn"] == fqn]
        return self.backend.defines_of([fqn]).get(fqn, [])

    def code_text(self, path: str) -> Optional[str]:
        """`code.files.get(path)`."""
        if not self._parts("code"):
            return (self.code or {}).get("files", {}).get(path)
        return self._memo("_f:code:" + path, lambda: self.backend.code_texts([path]).get(path))


class LazyMap(Mapping):
    """A read-only mapping whose values are fetched per key (`get_many([key])`), whose keys come
    from `keys_fn()`, and whose full iteration (`items`/`values`) loads `full_fn()` once."""

    def __init__(self, keys_fn, get_many, full_fn) -> None:
        self._keys_fn, self._get_many, self._full_fn = keys_fn, get_many, full_fn
        self._keys: Optional[List[str]] = None
        self._keyset: Optional[set] = None
        self._got: Dict[str, Any] = {}
        self._full: Optional[Dict[str, Any]] = None

    def _all_keys(self) -> List[str]:
        if self._keys is None:
            self._keys = list(self._full) if self._full is not None else self._keys_fn()
            self._keyset = set(self._keys)
        return self._keys

    def __getitem__(self, key: str) -> Any:
        if self._full is not None:
            return self._full[key]
        if key not in self._got:
            if self._keyset is not None and key not in self._keyset:
                raise KeyError(key)
            self._got[key] = self._get_many([key]).get(key, _MISSING)
        value = self._got[key]
        if value is _MISSING:
            raise KeyError(key)
        return value

    def __contains__(self, key: object) -> bool:
        self._all_keys()
        return key in self._keyset

    def __iter__(self) -> Iterator[str]:
        return iter(self._all_keys())

    def __len__(self) -> int:
        return len(self._all_keys())

    def _load_full(self) -> Dict[str, Any]:
        if self._full is None:
            self._full = self._full_fn()
        return self._full

    def items(self):
        return self._load_full().items()

    def values(self):
        return self._load_full().values()


_MISSING = object()


def symbols_of(store) -> Mapping:
    """`store.xref["symbols"]`, through the typed read when the store has one (duck-typed test stores do not)."""
    return store.symbols if isinstance(store, Store) else store.xref["symbols"]


def used_by_of(store) -> Mapping:
    return store.used_by if isinstance(store, Store) else store.xref["used_by"]


def xref_field(store, key: str) -> Any:
    return store.xref_field(key) if isinstance(store, Store) else store.xref[key]


def code_text(store, path: str) -> Optional[str]:
    if isinstance(store, Store):
        return store.code_text(path)
    return (getattr(store, "code", None) or {}).get("files", {}).get(path)


def _by_file(store, name: str) -> Dict[str, Dict]:
    """A duck-typed store's whole extraction (or xref uses), grouped by file once per query."""
    cache = getattr(store, "_cache", None)
    if cache is not None and ("_by_file:" + name) in cache:
        return cache["_by_file:" + name]
    out: Dict[str, Dict] = {}
    if name == "extract":
        ext = store.extraction
        for k in ("defines", "uses", "imports", "io_edges", "rule_edges"):
            for row in ext.get(k) or []:
                out.setdefault(row.get("file"), {}).setdefault(k, []).append(row)
        for p, meta in ext.get("files", {}).items():
            out.setdefault(p, {})["meta"] = meta
    else:
        for u in store.xref["uses"]:
            out.setdefault(u.get("from_file"), {}).setdefault("uses", []).append(u)
    if cache is not None:
        cache["_by_file:" + name] = out
    return out


def file_rows(store, path: str, key: str) -> Any:
    """One file's `extract[key]` rows (`meta`: its `extract.files` entry, or None), in snapshot order."""
    part = store.file_extract(path) if isinstance(store, Store) else _by_file(store, "extract").get(path, {})
    return part.get(key) if key == "meta" else part.get(key, [])


def file_edges(store, path: str) -> List[Dict]:
    """`[e for e in rules.all_edges(extraction) if e["file"] == path]` from that file's rows alone."""
    from ..rules import _edge_key

    io, extra = file_rows(store, path, "io_edges"), file_rows(store, path, "rule_edges")
    any_rules = store.has_rule_edges() if isinstance(store, Store) else bool(store.extraction.get("rule_edges"))
    return sorted([*io, *extra], key=_edge_key) if any_rules else io


def xref_uses_of(store, path: str) -> List[Dict]:
    """The `xref.uses` rows whose `from_file` is `path`, in snapshot order."""
    if isinstance(store, Store) and store._parts("xref"):
        return store._memo("_f:xuses:" + path, lambda: (store.backend.file_part("xref", path) or {}).get("uses", []))
    return _by_file(store, "xref").get(path, {}).get("uses", [])


def defines_named(store, fqn: str) -> List[Dict]:
    if isinstance(store, Store):
        return store.defines_named(fqn)
    return [d for d in store.extraction["defines"] if d["fqn"] == fqn]
