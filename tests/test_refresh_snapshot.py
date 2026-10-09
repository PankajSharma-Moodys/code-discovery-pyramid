"""A refreshed snapshot must be as complete as a scanned one.

`refresh` once wrote every artifact except `schedule`, so after any commit the
SessionStart hook (refresh, then status) left a store `status` could not read.
"""

from __future__ import annotations

import contextlib
import io
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from helpers import have_git, make_repo

from cdp.cli import main
from test_hook import _OwnHome
from test_refresh import _commit_all


@unittest.skipUnless(have_git(), "refresh needs a real git repository")
class RefreshSnapshotTest(_OwnHome, unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.make_home()
        self.repo = make_repo(Path(self.tmp.name))
        main(["scan", "--repo", str(self.repo), "--quiet"])

    def artifact_names(self) -> set:
        """Artifacts of the most recently written snapshot."""
        with contextlib.closing(sqlite3.connect(str(self.home / "index.db"))) as db:
            latest = db.execute("select id from snapshot_meta order by touch_seq desc limit 1").fetchone()[0]
            return {n for n, in db.execute(
                "select name from snapshot_artifact where snapshot_id=?", (latest,))}

    def test_refreshed_snapshot_has_every_artifact_a_scan_writes(self) -> None:
        scanned = self.artifact_names()
        self.assertIn("schedule", scanned)
        (self.repo / "NOTES.md").write_text("changed\n")
        _commit_all(self.repo, "move HEAD")
        main(["refresh", "--repo", str(self.repo), "--quiet"])
        self.assertEqual(self.artifact_names(), scanned)

    def test_status_reads_after_a_refresh(self) -> None:
        (self.repo / "NOTES.md").write_text("changed\n")
        _commit_all(self.repo, "move HEAD")
        main(["refresh", "--repo", str(self.repo), "--quiet"])
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = main(["status", "--repo", str(self.repo), "--json"])
        self.assertEqual(code, 0)
        self.assertIn("coverage", json.loads(out.getvalue()))


if __name__ == "__main__":
    unittest.main()
