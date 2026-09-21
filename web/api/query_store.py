"""A `WorkspaceStore` that is genuinely read-only, for reusing `cdp.query`.

`WEB_RESEARCH.md` §7.0/§7.2.1 is explicit: query semantics are never
reimplemented, every read endpoint delegates to `cdp.query.dispatch` (the
seam already shared by the CLI and `mcp_server`). But `cdp.query.Store`
only accepts a `WorkspaceStore` -- and the real one, `SqliteStore`, writes on
open (`store_reader.py`'s docstring: `_migrate()` and `_snapshot_id()` both
issue statements that fail against a `mode=ro` connection).

This module is the fix: a minimal `WorkspaceStore` subclass whose only real
methods are `read_artifact`/`has_artifact`, both delegating to the existing
pinned `ReadOnlyConnection` (`store_reader.py`). Verified before writing this
(see `PLAN.md`'s current-cycle notes): every function in `cdp/query.py`
reaches artifacts only through `store.<name>` properties, which route through
`read_artifact` -- never `load_patches`, `read_report`, or any `write_*`
method. Those therefore only need to exist to satisfy the abstract base;
callers on the read path never reach them.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from cdp.store import WorkspaceStore
from cdp.util import CdpError

from .store_reader import ReadOnlyConnection


class ReadOnlyWorkspaceStore(WorkspaceStore):
    """One manifest-pinned snapshot, read-only, for `cdp.query.Store` to wrap.

    Construct with `query_mod.Store(adapter, use_latest=False)` --
    `use_latest=False` is required: the connection is already pinned to the
    manifest-gated snapshot at construction time (`store_reader.py`'s whole
    point), and `use_latest_snapshot()` would re-resolve "latest" by
    `touch_seq` alone, reopening the exact torn-read window §7.0 closes.
    """

    def __init__(self, conn: ReadOnlyConnection, snapshot_id: int) -> None:
        self._conn = conn
        self._snapshot_id = snapshot_id

    def read_artifact(self, name: str, default: Any = None) -> Any:
        return self._conn.read_artifact(self._snapshot_id, name, default=default)

    def has_artifact(self, name: str) -> bool:
        try:
            self._conn.read_artifact(self._snapshot_id, name)
        except CdpError:
            return False
        return True

    def write_artifact(self, name: str, data: Any) -> None:
        raise self._no_write_path()

    def write_report(self, name: str, data: Any) -> None:
        raise self._no_write_path()

    def read_report(self, name: str, default: Any = None) -> Any:
        raise CdpError(
            "%s does not serve reports/ -- query.py never reads them"
            % type(self).__name__
        )

    def load_patches(self) -> List[Dict]:
        return []

    # -------------------------------------------------- patch log / inbox
    # None of these are on `query.py`'s read path (it never mutates the
    # patch log or the inbox); they exist only because `WorkspaceStore`
    # declares them abstract. All refuse, loudly, rather than silently
    # no-op -- a caller reaching one of these has a bug, not a read.

    def _no_write_path(self) -> CdpError:
        return CdpError("%s is read-only -- no write path" % type(self).__name__)

    def append_patch(self, patch: Dict, label: str) -> str:
        raise self._no_write_path()

    def write_derived_patch(self, patch: Dict) -> None:
        raise self._no_write_path()

    def ensure_inbox(self) -> None:
        raise self._no_write_path()

    def read_inbox(self) -> List[Tuple[str, Any]]:
        return []

    def clear_inbox(self, node: str) -> None:
        raise self._no_write_path()

    def task_rows(self, run_id: str) -> List[Dict]:
        return self._conn.task_rows(run_id)

    def snapshot_id(self) -> int:
        return self._snapshot_id
