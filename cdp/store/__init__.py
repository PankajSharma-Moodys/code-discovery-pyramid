"""The store boundary (Phase 2, M2.1 — `PHASE/phase_2_plan.md` 0.1).

R1: *provenance is a column, not a directory. Files are an export format, not a
storage format.* This module is where that boundary lives. It owns every read
and write the pipeline performs against CDP's own workspace state: the
top-level artifacts (`inventory`, `extract`, `graph`, `partition`, `schedule`,
`xref`, `dataflow`, `state`, `manifest`), the `reports/` namespace, and the
append-only patch log.

Nothing outside `store/` touches the filesystem for state, and nothing outside
`store/` will later import `sqlite3` (M2.2). `docs/` is deliberately excluded:
it is a rendered *export*, never read back by CDP, so it stays with `docs.py`.
The `patches/inbox/` directory is also outside the log proper — it is the
handoff surface where an agent session drops leaf patches before `collect`
validates them, a real filesystem contract with `SKILL.md`'s orchestration —
but every read of it still goes through this module.

`M2.1` ships one backend, `FileStore`, over today's JSON files with **no
behaviour change**: same paths, same bytes on disk. `M2.2` adds `SqliteStore`
behind the same `WorkspaceStore` interface; the backend conformance suite in
`tests/test_store_conformance.py` is what proves the swap preserves meaning.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Tuple

ARTIFACTS = (
    "inventory", "extract", "graph", "partition", "schedule",
    "xref", "dataflow", "state", "manifest",
)
REPORTS = ("verify", "conflicts", "prompts", "rejected", "unknown_gates")


class WorkspaceStore(ABC):
    """Every read and write the pipeline performs, backend-agnostic."""

    # ----------------------------------------------------------- snapshots
    # (M2.4, 0.6/0.7: a snapshot is `(repo_id, commit_sha)`. Backends that
    # cannot hold more than one live snapshot -- `FileStore`, an export format
    # -- accept the call and no-op.)

    def begin_snapshot(self, repo_id: str, commit_sha: str, ephemeral: bool = False) -> None:
        """Select, creating if needed, the snapshot subsequent calls apply to.

        A no-op on backends without snapshot lineage (`FileStore`). Backends
        that do (`SqliteStore`) key it by `(repo_id, commit_sha)`, so two scans
        of the same commit reuse one snapshot and a different commit gets a new
        one that coexists with the old rather than overwriting it.
        """

    def mark_durable(self) -> None:
        """Assert this snapshot's claims may be cited by durable lineage.

        Raises if the current snapshot is `ephemeral`: a dirty tree's identity
        includes a diff hash nothing else can reproduce, so a claim anchored
        there would cite a state that cannot be re-derived (0.6). A no-op on
        backends without snapshot lineage.
        """

    # ------------------------------------------------------------ artifacts

    @abstractmethod
    def read_artifact(self, name: str, default: Any = None) -> Any:
        """Read one of `ARTIFACTS`. Raise `CdpError` if missing and no default."""

    @abstractmethod
    def write_artifact(self, name: str, data: Any) -> None:
        ...

    @abstractmethod
    def has_artifact(self, name: str) -> bool:
        ...

    def exists(self) -> bool:
        """Whether a scan has ever written to this store."""
        return self.has_artifact("inventory")

    # -------------------------------------------------------------- reports

    @abstractmethod
    def write_report(self, name: str, data: Any) -> None:
        ...

    @abstractmethod
    def read_report(self, name: str, default: Any = None) -> Any:
        """Read one of `REPORTS`, written by `write_report`. Raise `CdpError`
        if missing and no default -- symmetric with `read_artifact`, needed by
        golden capture, which must read state back through this interface
        rather than walking a backend's filesystem layout."""

    # ------------------------------------------------------------ patch log

    @abstractmethod
    def load_patches(self) -> List[Dict]:
        """The append-only log, in canonical (filename) order.

        Nothing downstream may depend on that order: `state.fold` must produce
        the same result under any permutation (`state.check_order_independence`).
        """

    @abstractmethod
    def append_patch(self, patch: Dict, label: str) -> str:
        """Append one patch. Never rewrites an existing slot. Returns its id."""

    @abstractmethod
    def write_derived_patch(self, patch: Dict) -> None:
        """Write the deterministic claims into the log's reserved first slot.

        Idempotent: `scan` is re-runnable and must not discard leaf patches
        already collected, so this overwrites one fixed slot rather than
        clearing the log.
        """

    # ------------------------------------------------------------ inbox (I/O
    # boundary with the agent session; see module docstring)

    @abstractmethod
    def ensure_inbox(self) -> None:
        ...

    @abstractmethod
    def read_inbox(self) -> List[Tuple[str, Any]]:
        """`(filename, patch_dict)` for every file in the inbox, sorted by name.

        A file that is not valid JSON yields `(filename, ValueError)` instead of
        raising, so `collect` can report it as a rejected patch rather than
        aborting the whole batch.
        """

    @abstractmethod
    def clear_inbox(self, node: str) -> None:
        """Remove the inbox entry for `node` once its patch has been logged."""


def has_scanned(state_dir) -> bool:
    """Whether a scan has ever written to `state_dir`, checked without
    constructing a backend. `SqliteStore.__init__` creates its db file (and
    parent directory) as a side effect of merely opening it -- fine for a
    command that is about to scan or read real state, wrong here: this is
    called from a directory-walk probe (`hook.find_state`) on every watched
    tool call, for directories the vast majority of which were never scanned.
    """
    from pathlib import Path

    return (Path(state_dir) / "index.db").is_file()


from .file_backend import FileStore  # noqa: E402  (avoid a circular import at module load)
from .sqlite_backend import SqliteStore  # noqa: E402

__all__ = ["WorkspaceStore", "FileStore", "SqliteStore", "ARTIFACTS", "REPORTS", "has_scanned"]
