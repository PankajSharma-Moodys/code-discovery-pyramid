"""Compaction and the cold archive of `SqliteStore` (M7.3-M7.5): the superseded patches
`generations.superseded_indexes` names move from `claim_patch` to `claim_patches_archive`,
and `verify --full` / `export --format archive` read them back."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

from ..util import CdpError, stable_hash


class EphemeralMixin:
    """Garbage control for dirty-tree snapshots. Needs `self._conn` from `SqliteStore`."""

    def _delete_snapshot_rows(self, snapshot_id: int) -> None:
        """Everything scoped to one snapshot, uncommitted (the caller owns the transaction)."""
        run_ids = [r[0] for r in self._conn.execute(
            "SELECT run_id FROM snapshot_run WHERE snapshot_id=?", (snapshot_id,)).fetchall()]
        for run_id in run_ids:
            self._conn.execute("DELETE FROM snapshot_task WHERE run_id=?", (run_id,))
            self._conn.execute("DELETE FROM snapshot_run WHERE run_id=?", (run_id,))
        for table in ("claim_patch", "snapshot_artifact", "snapshot_report", "snapshot_checkout"):
            self._conn.execute("DELETE FROM %s WHERE snapshot_id=?" % table, (snapshot_id,))
        self._conn.execute("DELETE FROM snapshot_meta WHERE id=?", (snapshot_id,))

    def prune_ephemeral(self, repo_id: str, snapshot_id: int, ephemeral: bool, checkout: str) -> List[int]:
        """Called by `begin_snapshot` in its transaction. Records that `checkout` now stands on
        `snapshot_id` if that is a dirty snapshot, and drops every other dirty snapshot of this
        repo that this checkout was the last to stand on, unless another checkout still does or
        it is pinned. So a checkout keeps at most its newest dirty snapshot, and none once it
        has a clean one. Returns the dropped ids. Rows no checkout ever claimed (written before
        this existed) are left to `gc`."""
        if not checkout:
            return []
        if ephemeral:
            self._conn.execute(
                "INSERT OR REPLACE INTO snapshot_checkout (snapshot_id, checkout, seq) VALUES (?, ?, "
                "(SELECT COALESCE(MAX(seq), 0) + 1 FROM snapshot_checkout))", (snapshot_id, checkout))
        old = [r[0] for r in self._conn.execute(
            "SELECT c.snapshot_id FROM snapshot_checkout c JOIN snapshot_meta m ON m.id = c.snapshot_id "
            "WHERE c.checkout=? AND c.snapshot_id != ? AND m.repo_id=? AND m.ephemeral=1",
            (checkout, snapshot_id, repo_id)).fetchall()]
        dropped: List[int] = []
        for sid in old:
            self._conn.execute("DELETE FROM snapshot_checkout WHERE snapshot_id=? AND checkout=?", (sid, checkout))
            held = self._conn.execute("SELECT 1 FROM snapshot_checkout WHERE snapshot_id=?", (sid,)).fetchone()
            pinned = self._conn.execute("SELECT pinned FROM snapshot_meta WHERE id=?", (sid,)).fetchone()
            if held is None and not (pinned and pinned[0]):
                self._delete_snapshot_rows(sid)
                dropped.append(sid)
        return dropped


class ArchiveMixin:
    """Needs `self._conn` and `self.load_patches()` from `SqliteStore`."""

    # ------------------------------------------------------ compact (M7.3, 2.4)

    def supports_compaction(self) -> bool:
        return True

    def compact(self, keep_generations: int = 1, threshold: float = 0.30,
                dry_run: bool = False) -> Dict[str, Any]:
        """Move superseded `complete` patches to `claim_patches_archive`.
        Nothing is deleted -- only relocated (R5) -- and nothing live moves: what is
        superseded is `generations.superseded_indexes`' answer, the fold's own rule, so
        the folded state is the same before and after. Whole-store, not scoped to the
        currently-selected snapshot: generations accumulate per `(snapshot_id, node)`
        across every re-run of a node on one commit.

        `threshold` gates whether this call acts: below it, nothing moves.
        `keep_generations` (at least 1) leaves that many generations of each scope hot.
        """
        from .. import generations

        if keep_generations < 1:
            raise CdpError("--keep-generations must be at least 1: the live generation is never archived")
        rows = self._conn.execute(
            "SELECT id, snapshot_id, seq, payload FROM claim_patch WHERE is_derived=0 ORDER BY snapshot_id, seq"
        ).fetchall()
        by_snapshot: Dict[int, List[Tuple[int, Dict]]] = {}
        for row_id, snapshot_id, seq, payload_text in rows:
            by_snapshot.setdefault(snapshot_id, []).append((row_id, dict(json.loads(payload_text), patch_no=seq)))

        total_complete = 0
        to_archive: List[Tuple[int, int, Dict]] = []
        for snapshot_id, entries in by_snapshot.items():
            payloads = [p for _, p in entries]
            total_complete += sum(1 for p in payloads if generations.is_complete(p))
            for i in generations.superseded_indexes(payloads, keep_generations):
                to_archive.append((entries[i][0], snapshot_id, payloads[i]))

        eligible_ratio = (len(to_archive) / total_complete) if total_complete else 0.0
        if eligible_ratio < threshold:
            return {"moved": 0, "kept": total_complete, "eligible_ratio": eligible_ratio,
                     "threshold_met": False}
        if dry_run:
            return {"moved": len(to_archive), "kept": total_complete - len(to_archive),
                     "eligible_ratio": eligible_ratio, "threshold_met": True}

        partition_cache: Dict[int, Dict[str, Optional[str]]] = {}
        for row_id, snapshot_id, payload in to_archive:
            node = str(payload.get("node", "?"))
            if snapshot_id not in partition_cache:
                part_row = self._conn.execute(
                    "SELECT payload FROM snapshot_artifact WHERE snapshot_id=? AND name='partition'",
                    (snapshot_id,),
                ).fetchone()
                part = json.loads(part_row[0]) if part_row else {}
                partition_cache[snapshot_id] = {
                    s["node"]: s.get("scope_hash") for s in part.get("scopes", [])
                }
            # A patch carries no `scope_hash` of its own (only `node`); the
            # cold index's key is the scope's content hash from that
            # snapshot's own partition, falling back to the node name itself
            # if the partition artifact is missing or stale (never fails the
            # move over a missing index value).
            scope_hash = partition_cache[snapshot_id].get(node) or node
            payload_text = json.dumps(payload, sort_keys=True)
            self._conn.execute(
                "INSERT INTO claim_patches_archive (scope_hash, run_id, payload, content_hash) "
                "VALUES (?, ?, ?, ?)",
                (scope_hash, payload.get("run_id"), payload_text, stable_hash(payload)),
            )
            self._conn.execute("DELETE FROM claim_patch WHERE id=?", (row_id,))
        self._conn.commit()
        self._conn.execute("VACUUM")
        return {"moved": len(to_archive), "kept": total_complete - len(to_archive),
                 "eligible_ratio": eligible_ratio, "threshold_met": True}

    # ------------------------------------------------------- verify --full (M7.4, 2.5)

    def _archive_scope_hashes(self, partition: Optional[Dict]) -> Optional[set]:
        if not partition or not partition.get("scopes"):
            return None
        hashes = {s.get("scope_hash") for s in partition["scopes"] if s.get("scope_hash")}
        return hashes or None

    def load_patches_full(self, partition: Optional[Dict] = None) -> List[Dict]:
        """`load_patches()` plus every archived generation for this snapshot's
        own scopes (M7.4). This is what makes `verify --full` a real re-fold
        from the raw log rather than the hot table alone."""
        hot = self.load_patches()
        scope_hashes = self._archive_scope_hashes(partition)
        if scope_hashes is None:
            rows = self._conn.execute("SELECT payload FROM claim_patches_archive").fetchall()
        else:
            placeholders = ", ".join("?" * len(scope_hashes))
            rows = self._conn.execute(
                "SELECT payload FROM claim_patches_archive WHERE scope_hash IN (%s)" % placeholders,
                tuple(scope_hashes),
            ).fetchall()
        return hot + [json.loads(r[0]) for r in rows]

    def verify_archive_integrity(self, partition: Optional[Dict] = None) -> List[str]:
        """Recompute each archived row's content hash and compare to the one
        recorded when it was archived. A row corrupted after the move fails
        here, named by scope and run, rather than surfacing only as an
        unexplained aggregate fold mismatch."""
        scope_hashes = self._archive_scope_hashes(partition)
        rows = self._conn.execute(
            "SELECT rowid, scope_hash, run_id, payload, content_hash FROM claim_patches_archive"
        ).fetchall()
        problems = []
        for rowid, scope_hash, run_id, payload_text, content_hash in rows:
            if scope_hashes is not None and scope_hash not in scope_hashes:
                continue
            if content_hash is None:
                continue  # archived before SCHEMA_V6; nothing recorded to check against
            if stable_hash(json.loads(payload_text)) != content_hash:
                problems.append(
                    "archive row corrupted: scope_hash=%s run_id=%s (rowid %d) no longer "
                    "matches its recorded content hash" % (scope_hash, run_id, rowid)
                )
        return problems

    def dump_archive(self, partition: Optional[Dict] = None) -> List[Dict]:
        """M7.5: every archived row, raw -- `scope_hash`/`run_id` plus the
        payload and the content hash `verify --full` checks it against."""
        scope_hashes = self._archive_scope_hashes(partition)
        rows = self._conn.execute(
            "SELECT scope_hash, run_id, payload, content_hash FROM claim_patches_archive"
        ).fetchall()
        out = []
        for scope_hash, run_id, payload_text, content_hash in rows:
            if scope_hashes is not None and scope_hash not in scope_hashes:
                continue
            out.append({
                "scope_hash": scope_hash,
                "run_id": run_id,
                "payload": json.loads(payload_text),
                "content_hash": content_hash,
            })
        return out
