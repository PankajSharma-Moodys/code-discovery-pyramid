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
from typing import Any, Dict, List, Optional, Tuple

from ..util import CdpError

ARTIFACTS = (
    "inventory", "extract", "graph", "partition", "schedule",
    "xref", "dataflow", "state", "manifest",
)
REPORTS = ("verify", "conflicts", "prompts", "rejected", "unknown_gates", "tiering")


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

    def load_patches_full(self, partition: Optional[Dict] = None) -> List[Dict]:
        """`load_patches()` plus anything `compact` moved to the archive
        (M7.4, 2.5). Base implementation: no archive exists on this backend,
        so it is exactly `load_patches()`."""
        return self.load_patches()

    def verify_archive_integrity(self, partition: Optional[Dict] = None) -> List[str]:
        """Per-row content-hash check over the archive (M7.4). Base
        implementation: no archive, so nothing to corrupt."""
        return []

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

    def close(self) -> None:
        """No-op default -- only a backend holding a live connection (Sqlite,
        Postgres) needs to override this."""

    def supports_run_tracking(self) -> bool:
        """Whether this backend can back `cdp run`/`cdp gc` at all. `False`
        by default (`FileStore`). Checked by the CLI up front so those
        commands fail with one clear message naming the missing capability,
        rather than a `list_snapshots()`-returns-`[]` read-side default
        cascading into a *different*, more confusing error deeper in (found
        live: `cdp gc` against `FileStore` reported "no snapshot for HEAD --
        run `cdp scan` first", which is wrong -- a scan did run; the backend
        just doesn't track snapshots as a retention concept)."""
        return False

    # ------------------------------------------- snapshots/runs/tasks/leases
    # (Phase 7: `cdp run`/`cdp gc` need these; only `SqliteStore` and
    # `PostgresStore` give them real, multi-writer-safe meaning. Read-side
    # methods default to an honest empty answer -- the same posture
    # `task_states`' own history already took ("schema-only... callers get
    # `{}` today, honestly, rather than a fabricated state"). Write-side
    # methods default to a clear refusal: a backend with no run/task storage
    # (`FileStore`) cannot silently pretend to support `cdp run`/`cdp gc`.)

    def supports_compaction(self) -> bool:
        """Whether this backend can back `cdp compact` (Phase 7, 2.4). `False`
        by default (`FileStore` has no cold table to move rows into)."""
        return False

    def compact(self, keep_generations: int = 1, threshold: float = 0.30,
                dry_run: bool = False) -> Dict[str, Any]:
        raise CdpError(
            "%s has no cold archive -- `cdp compact` needs the sqlite backend"
            % type(self).__name__
        )

    def dump_archive(self, partition: Optional[Dict] = None) -> List[Dict]:
        """M7.5: raw archived rows for `cdp export --format archive`. Same
        capability gate as `compact` -- a backend that cannot archive has
        nothing to dump."""
        raise CdpError(
            "%s has no cold archive -- `cdp export --format archive` needs "
            "the sqlite backend" % type(self).__name__
        )

    def list_snapshots(self) -> List[Dict]:
        return []

    def get_run(self, run_id: str) -> Optional[Dict]:
        return None

    def task_states(self, run_id: str) -> Dict[str, Dict]:
        return {}

    def task_rows(self, run_id: str) -> List[Dict]:
        return []

    def snapshot_id(self) -> int:
        return 1

    def use_latest_snapshot(self) -> None:
        """No-op default: a backend with no snapshot lineage has only ever
        one thing to be 'latest'."""

    def copy_patches_from(self, source_snapshot_id: int) -> None:
        """No-op default. Only ever invoked (`cmd_refresh`) when a freshly
        selected snapshot's patch log is empty -- impossible on a
        single-snapshot backend, where `begin_snapshot` is already a no-op,
        so the "new" snapshot is the same store whose log is never empty
        after any scan. Raising here would break `cdp refresh` against
        `FileStore`, which otherwise works fine without snapshot lineage."""

    def _no_run_tracking(self) -> CdpError:
        return CdpError(
            "%s has no run/task tracking -- `cdp run`/`cdp gc` need the "
            "sqlite or postgres backend" % type(self).__name__
        )

    def begin_run(self, run_id: str, partition_hash: Optional[str] = None) -> None:
        raise self._no_run_tracking()

    def finish_run(self, run_id: str, status: str) -> None:
        raise self._no_run_tracking()

    def upsert_task(self, run_id: str, scope_hash: str, **fields: Any) -> None:
        raise self._no_run_tracking()

    def acquire_lease(self, run_id: str, scope_hash: str, lease_seconds: float) -> bool:
        raise self._no_run_tracking()

    def heartbeat_lease(self, run_id: str, scope_hash: str, lease_seconds: float) -> None:
        raise self._no_run_tracking()

    def release_lease(self, run_id: str, scope_hash: str) -> None:
        raise self._no_run_tracking()

    def reclaim_expired(self, run_id: str) -> List[str]:
        raise self._no_run_tracking()

    def copy_folded_tasks(self, old_run_id: str, new_run_id: str, scope_hashes) -> None:
        raise self._no_run_tracking()

    def set_pinned(self, commit_sha: str, pinned: bool) -> None:
        raise self._no_run_tracking()

    def delete_snapshot(self, snapshot_id: int) -> None:
        raise self._no_run_tracking()


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
