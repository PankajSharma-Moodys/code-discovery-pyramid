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
