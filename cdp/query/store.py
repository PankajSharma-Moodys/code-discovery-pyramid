"""The loaded state a query reads."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional, Union

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
        self._cache: Dict[str, Any] = {}

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
    manifest = property(lambda self: self._load("manifest", {}))

    def node_of(self, path: str) -> Optional[str]:
        for scope in self.partition["scopes"]:
            if path in scope["files"]:
                return scope["node"]
        return None
