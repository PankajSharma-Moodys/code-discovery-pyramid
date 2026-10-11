"""Compaction and the cold archive of `SqliteStore` (M7.3-M7.5): the superseded patches
`generations.superseded_indexes` names move from `claim_patch` to `claim_patches_archive`,
and `verify --full` / `export --format archive` read them back."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Set, Tuple

from ..util import CdpError, stable_hash

#: SCHEMA_V11 (`sqlite_backend.MIGRATIONS`): which snapshot an archived generation came from.
#: Run by `migrate_archive_snapshot_id` (idempotent: a half-applied attempt re-runs cleanly).
SCHEMA_V11 = "-- claim_patches_archive.snapshot_id + backfill: see sqlite_archive.migrate_archive_snapshot_id"


def migrate_archive_snapshot_id(conn) -> None:
    """Add `claim_patches_archive.snapshot_id` and fill it where it is unambiguous: the one
    snapshot whose partition names the row's scope. Rows that fit several snapshots (a refreshed
    snapshot copies its parent's scopes) or none stay NULL and keep the old scope-hash match."""
    if "snapshot_id" not in [r[1] for r in conn.execute("PRAGMA table_info(claim_patches_archive)")]:
        conn.execute("ALTER TABLE claim_patches_archive ADD COLUMN snapshot_id INTEGER")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_patches_archive_snapshot ON claim_patches_archive(snapshot_id)")
    scopes: Dict[int, Set[str]] = {}
    for sid, payload in conn.execute("SELECT snapshot_id, payload FROM snapshot_artifact WHERE name='partition'"):
        try:
            part = json.loads(payload)
        except ValueError:
            continue
        scopes[sid] = {str(v) for sc in part.get("scopes", []) for v in (sc.get("scope_hash"), sc.get("node")) if v}
    for rowid, scope_hash in conn.execute(
            "SELECT rowid, scope_hash FROM claim_patches_archive WHERE snapshot_id IS NULL").fetchall():
        owners = [sid for sid, names in scopes.items() if scope_hash in names]
        if len(owners) == 1:
            conn.execute("UPDATE claim_patches_archive SET snapshot_id=? WHERE rowid=?", (owners[0], rowid))
    conn.commit()


def superseded_for(patches: List[Dict], exclusions, keep_generations: int) -> List[int]:
    """Positions in `patches` that `compact` may archive: what the fold no longer reads *after*
    the rollback ledger has been applied. A patch a rollback excludes is never archived (an
    `--undo` needs it), and with it out of the way the generation below it is the live one, so it
    stays hot for as long as the rollback is in force."""
    from .. import generations

    live = [(i, p) for i, p in enumerate(patches) if not exclusions.matches(p)]
    return [live[j][0] for j in generations.superseded_indexes([p for _, p in live], keep_generations)]


def _view(patches: List[Dict], xref, partition, extraction, exclusions) -> str:
    """Everything a fold of `patches` yields that a reader sees, hashed (no repo: anchors are
    not re-verified, which compaction cannot change)."""
    from .. import state as state_mod

    out = state_mod.fold(patches, xref or {}, partition, repo=None, excluded_run_ids=exclusions, extraction=extraction)
    keys = ("claims", "unknowns", "conflicts", "coverage", "entailment", "contradictions")
    return stable_hash([out.get(k) for k in keys] + [out["provenance"]["fold_hash"]])


class EphemeralMixin:
    """Garbage control for dirty-tree snapshots. Needs `self._conn` from `SqliteStore`."""

    def _delete_snapshot_rows(self, snapshot_id: int) -> None:
        """Everything scoped to one snapshot, uncommitted (the caller owns the transaction)."""
        run_ids = [r[0] for r in self._conn.execute(
            "SELECT run_id FROM snapshot_run WHERE snapshot_id=?", (snapshot_id,)).fetchall()]
        for run_id in run_ids:
            self._conn.execute("DELETE FROM snapshot_task WHERE run_id=?", (run_id,))
            self._conn.execute("DELETE FROM snapshot_run WHERE run_id=?", (run_id,))
        for table in ("claim_patch", "snapshot_artifact", "snapshot_report", "snapshot_checkout",
                      "claim_patches_archive"):
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
        # Clean snapshots are recorded too: `gc` keeps the one each checkout last stood on.
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


    def checkout_heads(self) -> Dict[int, List[str]]:
        """`snapshot id -> checkouts whose most recent scan or refresh was of it`: what each
        worktree last stood on, clean or dirty."""
        out: Dict[int, List[str]] = {}
        for sid, checkout in self._conn.execute(
                "SELECT c.snapshot_id, c.checkout FROM snapshot_checkout c WHERE c.seq = "
                "(SELECT MAX(seq) FROM snapshot_checkout WHERE checkout = c.checkout) ORDER BY c.snapshot_id"):
            out.setdefault(sid, []).append(checkout)
        return out

    def model_patch_hashes(self) -> Dict[int, Set[str]]:
        """`snapshot id -> content hashes of its accepted model/human patches` (leaf and answer
        patches; never the scan's own derived one): the claims `gc` must not lose."""
        out: Dict[int, Set[str]] = {}
        for sid, h in self._conn.execute(
                "SELECT snapshot_id, content_hash FROM claim_patch WHERE is_derived=0 "
                "AND json_extract(payload, '$.status')='complete' "
                "AND COALESCE(json_extract(payload, '$.author_kind'), '') != 'python'"):
            out.setdefault(sid, set()).add(h)
        return out


class ArchiveMixin:
    """Needs `self._conn` and `self.load_patches()` from `SqliteStore`."""

    # ------------------------------------------------------ compact (M7.3, 2.4)

    def supports_compaction(self) -> bool:
        return True

    def _snapshot_exclusions(self, snapshot_id: int):
        from .. import rollback

        row = self._conn.execute(
            "SELECT payload FROM snapshot_artifact WHERE snapshot_id=? AND name=?",
            (snapshot_id, rollback.LEDGER_ARTIFACT)).fetchone()
        ledger = json.loads(row[0]) if row else {"events": []}
        events = ledger.get("events", [])
        return rollback.Exclusions([
            (events[i].get("excluded_run_ids", []), *(events[i].get("patch_range") or (None, None)))
            for i in rollback._live_indexes(ledger)])

    def _artifact(self, snapshot_id: int, name: str) -> Any:
        row = self._conn.execute(
            "SELECT payload FROM snapshot_artifact WHERE snapshot_id=? AND name=?", (snapshot_id, name)).fetchone()
        return json.loads(row[0]) if row else None

    def _check_compaction_is_lossless(self, snapshot_id: int, derived: List[Dict], entries: List[Tuple[int, Dict]],
                                      moving: set, exclusions) -> None:
        """Fold the snapshot's log with and without the patches about to move; the live view
        (claims, unknowns, conflicts, coverage, entailment, fold hash) must be identical, or
        nothing moves."""
        xref, part, ext = (self._artifact(snapshot_id, n) for n in ("xref", "partition", "extract"))
        before = [p for _, p in entries] + derived
        after = [p for row_id, p in entries if row_id not in moving] + derived
        if _view(before, xref, part, ext, exclusions) != _view(after, xref, part, ext, exclusions):
            raise CdpError(
                "compact aborted, nothing moved: archiving %d patch(es) of snapshot %d would change its live "
                "claims. This is a bug in the compaction rule; the store is untouched." % (len(moving), snapshot_id))

    def compact(self, keep_generations: int = 1, threshold: float = 0.30,
                dry_run: bool = False) -> Dict[str, Any]:
        """Move superseded `complete` patches to `claim_patches_archive`.
        Nothing is deleted -- only relocated (R5) -- and nothing live moves: what is
        superseded is the fold's own rule (`generations.superseded_indexes`) applied to the log
        *after* the rollback ledger, so a generation a rollback brought back to life stays hot
        and a rolled-back one is never archived. Every snapshot that would lose rows is
        re-folded without them first, and the whole call aborts (nothing moves) unless its live
        view is identical. Whole-store, not scoped to the currently-selected snapshot:
        generations accumulate per `(snapshot_id, node)` across every re-run of a node on one commit.

        `threshold` gates whether this call acts: below it, nothing moves.
        `keep_generations` (at least 1) leaves that many generations of each scope hot.
        """
        if keep_generations < 1:
            raise CdpError("--keep-generations must be at least 1: the live generation is never archived")
        rows = self._conn.execute(
            "SELECT id, snapshot_id, seq, payload, is_derived FROM claim_patch ORDER BY snapshot_id, seq"
        ).fetchall()
        by_snapshot: Dict[int, List[Tuple[int, Dict]]] = {}
        derived_by_snapshot: Dict[int, List[Dict]] = {}
        for row_id, snapshot_id, seq, payload_text, is_derived in rows:
            payload = dict(json.loads(payload_text), patch_no=seq)
            if is_derived:
                derived_by_snapshot.setdefault(snapshot_id, []).append(payload)
            else:
                by_snapshot.setdefault(snapshot_id, []).append((row_id, payload))

        from .. import generations

        total_complete = 0
        to_archive: List[Tuple[int, int, Dict]] = []
        for snapshot_id, entries in by_snapshot.items():
            payloads = [p for _, p in entries]
            total_complete += sum(1 for p in payloads if generations.is_complete(p))
            exclusions = self._snapshot_exclusions(snapshot_id)
            moving = [entries[i][0] for i in superseded_for(payloads, exclusions, keep_generations)]
            if moving:
                self._check_compaction_is_lossless(
                    snapshot_id, derived_by_snapshot.get(snapshot_id, []), entries, set(moving), exclusions)
            for row_id in moving:
                to_archive.append((row_id, snapshot_id, next(p for r, p in entries if r == row_id)))

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
                part = self._artifact(snapshot_id, "partition") or {}
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
                "INSERT INTO claim_patches_archive (scope_hash, run_id, payload, content_hash, snapshot_id) "
                "VALUES (?, ?, ?, ?, ?)",
                (scope_hash, payload.get("run_id"), payload_text, stable_hash(payload), snapshot_id),
            )
            self._conn.execute("DELETE FROM claim_patch WHERE id=?", (row_id,))
        self._conn.commit()
        self._conn.execute("VACUUM")
        return {"moved": len(to_archive), "kept": total_complete - len(to_archive),
                 "eligible_ratio": eligible_ratio, "threshold_met": True}

    def restore_archived(self) -> int:
        """Move the selected snapshot's archived generations back into its log. A rollback calls
        this first: excluding a run can make an older generation live again, and a generation in
        the cold archive is invisible to the fold. Returns how many came back."""
        snapshot_id = self._snapshot_id()
        rows = self._conn.execute(
            "SELECT rowid, payload FROM claim_patches_archive WHERE snapshot_id=?", (snapshot_id,)).fetchall()
        for rowid, payload_text in rows:
            patch = json.loads(payload_text)
            seq = patch.pop("patch_no", None)
            if seq is None:
                seq = self._conn.execute(
                    "SELECT COALESCE(MAX(seq), 0) + 1 FROM claim_patch WHERE snapshot_id=? AND is_derived=0",
                    (snapshot_id,)).fetchone()[0]
            self._conn.execute(
                "INSERT OR IGNORE INTO claim_patch "
                "(snapshot_id, seq, label, content_hash, payload, is_derived, created_at) "
                "VALUES (?, ?, ?, ?, ?, 0, datetime('now'))",
                (snapshot_id, seq, str(patch.get("node", "?")).replace("/", "__"), stable_hash(patch),
                 json.dumps(patch, sort_keys=True)))
            self._conn.execute("DELETE FROM claim_patches_archive WHERE rowid=?", (rowid,))
        self._conn.commit()
        return len(rows)

    # ------------------------------------------------------- verify --full (M7.4, 2.5)

    def _archive_scope_hashes(self, partition: Optional[Dict]) -> Optional[set]:
        if not partition or not partition.get("scopes"):
            return None
        hashes = {s.get("scope_hash") for s in partition["scopes"] if s.get("scope_hash")}
        return hashes or None

    def _archive_rows(self, partition: Optional[Dict], columns: str) -> List[Tuple]:
        """Archive rows of the selected snapshot. A row archived before SCHEMA_V11 that could not
        be assigned to one snapshot (`snapshot_id` NULL) is matched by scope hash, as it always was."""
        hashes = self._archive_scope_hashes(partition)
        legacy = "snapshot_id IS NULL" + (" AND scope_hash IN (%s)" % ", ".join("?" * len(hashes)) if hashes else "")
        return self._conn.execute(
            "SELECT %s FROM claim_patches_archive WHERE snapshot_id=? OR (%s)" % (columns, legacy),
            (self._snapshot_id(),) + tuple(hashes or ())).fetchall()

    def load_patches_full(self, partition: Optional[Dict] = None) -> List[Dict]:
        """`load_patches()` plus every archived generation of *this snapshot* (M7.4). This is
        what makes `verify --full` a real re-fold from the raw log rather than the hot table
        alone. (Rows of other snapshots, even of the same scope, are not part of this log.)"""
        hot = self.load_patches()
        return hot + [json.loads(r[0]) for r in self._archive_rows(partition, "payload")]

    def verify_archive_integrity(self, partition: Optional[Dict] = None) -> List[str]:
        """Recompute each archived row's content hash and compare to the one
        recorded when it was archived. A row corrupted after the move fails
        here, named by scope and run, rather than surfacing only as an
        unexplained aggregate fold mismatch."""
        problems = []
        for rowid, scope_hash, run_id, payload_text, content_hash in self._archive_rows(
                partition, "rowid, scope_hash, run_id, payload, content_hash"):
            if content_hash is None:
                continue  # archived before SCHEMA_V6; nothing recorded to check against
            if stable_hash(json.loads(payload_text)) != content_hash:
                problems.append(
                    "archive row corrupted: scope_hash=%s run_id=%s (rowid %d) no longer "
                    "matches its recorded content hash" % (scope_hash, run_id, rowid)
                )
        return problems

    def dump_archive(self, partition: Optional[Dict] = None) -> List[Dict]:
        """M7.5: every archived row of the selected snapshot, raw -- `scope_hash`/`run_id` plus the
        payload and the content hash `verify --full` checks it against."""
        return [
            {"scope_hash": scope_hash, "run_id": run_id, "payload": json.loads(payload_text),
             "content_hash": content_hash}
            for scope_hash, run_id, payload_text, content_hash in self._archive_rows(
                partition, "scope_hash, run_id, payload, content_hash")
        ]
