"""`ReadOnlyWorkspaceStore` against a real scanned repo -- ground truth, not a
hand-built fixture, same posture as `test_nodeid.py`/`test_store_reader.py`.
Cross-checks `query.dispatch` through the adapter against `cdp query --json`
for the CLI-parity guarantee `WEB_RESEARCH.md` §7.2.1 requires."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
MINIREPO = REPO_ROOT / "tests" / "fixtures" / "minirepo"


class ReadOnlyWorkspaceStoreTest(unittest.TestCase):
    def setUp(self) -> None:
        self.state_dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.state_dir, ignore_errors=True)
        subprocess.run(
            [sys.executable, "-m", "cdp", "scan", "--repo", str(MINIREPO),
             "--state-dir", str(self.state_dir)],
            cwd=REPO_ROOT, check=True, capture_output=True, text=True,
        )

    def _adapter_store(self):
        from cdp import query as query_mod
        from web.api.query_store import ReadOnlyWorkspaceStore
        from web.api.store_reader import ReadOnlyConnection

        conn = ReadOnlyConnection(self.state_dir / "index.db")
        snapshot_id = conn.latest_pinned_snapshot()
        adapter = ReadOnlyWorkspaceStore(conn, snapshot_id)
        return query_mod.Store(adapter, use_latest=False)

    def test_dispatch_matches_cli_json_for_stats(self) -> None:
        from cdp import query as query_mod

        store = self._adapter_store()
        via_adapter = query_mod.dispatch(store, "stats")

        proc = subprocess.run(
            [sys.executable, "-m", "cdp", "query", "stats", "--repo", str(MINIREPO),
             "--state-dir", str(self.state_dir), "--json"],
            cwd=REPO_ROOT, check=True, capture_output=True, text=True,
        )
        via_cli = json.loads(proc.stdout)
        self.assertEqual(via_adapter, via_cli)

    def test_dispatch_matches_cli_json_for_unknowns(self) -> None:
        from cdp import query as query_mod

        store = self._adapter_store()
        via_adapter = query_mod.dispatch(store, "unknowns")

        proc = subprocess.run(
            [sys.executable, "-m", "cdp", "query", "unknowns", "--repo", str(MINIREPO),
             "--state-dir", str(self.state_dir), "--json"],
            cwd=REPO_ROOT, check=True, capture_output=True, text=True,
        )
        via_cli = json.loads(proc.stdout)
        self.assertEqual(via_adapter, via_cli)

    def test_write_paths_refuse(self) -> None:
        from cdp.util import CdpError
        from web.api.query_store import ReadOnlyWorkspaceStore
        from web.api.store_reader import ReadOnlyConnection

        conn = ReadOnlyConnection(self.state_dir / "index.db")
        adapter = ReadOnlyWorkspaceStore(conn, conn.latest_pinned_snapshot())
        with self.assertRaises(CdpError):
            adapter.write_artifact("state", {})
        with self.assertRaises(CdpError):
            adapter.append_patch({}, "leaf")


if __name__ == "__main__":
    unittest.main()
