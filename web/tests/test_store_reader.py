"""Scans a real fixture repo, then exercises `store_reader` against the
resulting `index.db` -- ground truth, not a hand-built db fixture."""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
MINIREPO = REPO_ROOT / "tests" / "fixtures" / "minirepo"


class StoreReaderTest(unittest.TestCase):
    def setUp(self) -> None:
        self.state_dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.state_dir, ignore_errors=True)
        subprocess.run(
            [sys.executable, "-m", "cdp", "scan", "--repo", str(MINIREPO),
             "--state-dir", str(self.state_dir)],
            cwd=REPO_ROOT, check=True, capture_output=True, text=True,
        )

    def test_latest_pinned_snapshot_reads_manifest_gated_artifacts(self) -> None:
        from web.api.store_reader import ReadOnlyConnection

        conn = ReadOnlyConnection(self.state_dir / "index.db")
        snapshot_id = conn.latest_pinned_snapshot()
        manifest = conn.read_artifact(snapshot_id, "manifest")
        self.assertIn("run_id", manifest)
        inventory = conn.read_artifact(snapshot_id, "inventory")
        self.assertIn("head", inventory)
        conn.close()

    def test_no_scan_raises_store_unavailable(self) -> None:
        from web.api.store_reader import ReadOnlyConnection, StoreUnavailable

        empty_dir = self.state_dir / "never_scanned"
        empty_dir.mkdir()
        conn = ReadOnlyConnection(empty_dir / "index.db")
        with self.assertRaises(StoreUnavailable):
            conn.latest_pinned_snapshot()

    def test_cacheable_artifact_is_served_from_cache_on_second_read(self) -> None:
        """`WEB_REDESIGN_RESEARCH.md` §5 item 3: cache parsed artifacts per
        `(db_path, snapshot_id)` in-process. Verified by closing the
        underlying sqlite connection between two reads of the same
        cacheable artifact -- if the second read weren't served from cache,
        it would raise (or reopen and still work, hiding the bug), so this
        also asserts identity: the exact same object comes back, meaning no
        second `json.loads` ran."""
        from web.api.store_reader import ReadOnlyConnection

        conn = ReadOnlyConnection(self.state_dir / "index.db")
        snapshot_id = conn.latest_pinned_snapshot()
        first = conn.read_artifact(snapshot_id, "inventory")
        conn.close()  # closing the sqlite connection would break an uncached re-read
        second = conn.read_artifact(snapshot_id, "inventory")
        self.assertIs(first, second)

    def test_state_artifact_is_never_cached(self) -> None:
        """`state` is folded in-place, wave by wave, by a live `cdp run`
        against the *same* snapshot_id (`cdp/cli.py`'s `_fold_and_write`) --
        confirmed by reading `cdp/cli.py`/`cdp/store/sqlite_backend.py`
        before writing this cache, not assumed. Caching it would serve a
        stale wave's claims to a request racing an in-flight run, so a
        second read must re-open the (still-live) connection rather than
        return the exact same object."""
        from web.api.store_reader import ReadOnlyConnection

        conn = ReadOnlyConnection(self.state_dir / "index.db")
        snapshot_id = conn.latest_pinned_snapshot()
        first = conn.read_artifact(snapshot_id, "state", default={"claims": []})
        second = conn.read_artifact(snapshot_id, "state", default={"claims": []})
        self.assertIsNot(first, second)
        conn.close()

    def test_connection_cannot_write(self) -> None:
        import sqlite3

        from web.api.store_reader import ReadOnlyConnection

        conn = ReadOnlyConnection(self.state_dir / "index.db")
        conn.latest_pinned_snapshot()
        with self.assertRaises(sqlite3.OperationalError):
            conn._conn().execute("INSERT INTO snapshot_meta (ephemeral, created_at) VALUES (1, 'x')")
        conn.close()


if __name__ == "__main__":
    unittest.main()
