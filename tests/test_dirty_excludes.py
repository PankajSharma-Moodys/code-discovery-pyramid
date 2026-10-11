"""A path the inventory excludes can never make the tree dirty.

Found live: `install --harness` then `git add -A` made every footer say "UNCOMMITTED
changes not in this index: .claude/... (+278)", the hook gate stand down, and `refresh`
refuse -- none of those paths are indexed. "Dirty" is `snapshot.is_dirty`, built on the
inventory's own exclusion list (built-ins, `.cdp.toml`, and the last scan's `--exclude`).
"""

from __future__ import annotations

import contextlib
import io
import json
import sqlite3
import subprocess
import tempfile
import unittest
from pathlib import Path

from helpers import have_git, make_repo

from cdp.cli import main
from cdp.util import CdpError
from test_hook import _OwnHome
from test_refresh import _commit_all


def _run(*argv: str):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = main(list(argv))
        except (CdpError, SystemExit) as exc:
            code, err = getattr(exc, "code", 2), io.StringIO(str(exc))
    return code, out.getvalue() + err.getvalue()


@unittest.skipUnless(have_git(), "dirty detection needs a real git repository")
class DirtyExcludesTest(_OwnHome, unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.make_home()
        self.repo = make_repo(Path(self.tmp.name))

    def write(self, rel: str, text: str = "x\n") -> None:
        path = self.repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def status(self) -> dict:
        code, out = _run("status", "--repo", str(self.repo), "--json")
        self.assertEqual(code, 0, out)
        return json.loads(out)

    def snapshots(self) -> list:
        with contextlib.closing(sqlite3.connect(str(self.home / "index.db"))) as db:
            return db.execute("select commit_sha, ephemeral from snapshot_meta order by id").fetchall()

    def scan(self, *extra: str) -> None:
        self.assertEqual(_run("scan", "--repo", str(self.repo), "--quiet", *extra)[0], 0)

    def test_only_excluded_changes_leave_the_tree_clean_everywhere(self) -> None:
        self.write(".claude/old.md")
        self.write(".idea/workspace.xml")
        _commit_all(self.repo, "tooling dirs")
        self.scan()
        self.write(".claude/old.md", "edited\n")      # tracked, modified
        self.write(".claude/skills/new.md")           # staged below
        self.write(".idea/other.xml")                 # staged below
        subprocess.run(["git", "-C", str(self.repo), "add", ".claude/skills", ".idea"], check=True)
        self.write(".vscode/untracked.json")          # untracked
        status = self.status()
        self.assertEqual(status["dirty_files"], [])
        code, out = _run("query", "stats", "--repo", str(self.repo))
        self.assertEqual(code, 0, out)
        self.assertNotIn("UNCOMMITTED", out)
        code, out = _run("refresh", "--repo", str(self.repo), "--quiet")
        self.assertEqual(code, 0, out)
        # a scan of that tree is the durable HEAD snapshot, not an ephemeral one
        self.scan()
        self.assertTrue(all(not eph for _, eph in self.snapshots()), self.snapshots())

    def test_a_tree_with_only_excluded_changes_scans_durably_from_the_start(self) -> None:
        self.write(".claude/settings.json", "{}\n")
        subprocess.run(["git", "-C", str(self.repo), "add", "-A"], check=True)
        self.scan()
        rows = self.snapshots()
        self.assertEqual([eph for _, eph in rows], [0], rows)
        self.assertNotIn("+dirty", rows[0][0])

    def test_an_indexed_file_modified_is_still_dirty(self) -> None:
        self.scan()
        self.write("NOTES.md")
        self.write(".claude/x.md")
        subprocess.run(["git", "-C", str(self.repo), "add", "-A"], check=True)
        self.assertEqual(self.status()["dirty_files"], ["NOTES.md"])
        code, out = _run("query", "stats", "--repo", str(self.repo))
        self.assertIn("UNCOMMITTED changes not in this index: NOTES.md", out)
        self.assertNotEqual(_run("refresh", "--repo", str(self.repo), "--quiet")[0], 0)
        self.scan()
        self.assertEqual([eph for _, eph in self.snapshots()], [0, 1])

    def test_scan_exclude_is_persisted_and_honoured(self) -> None:
        self.write("vendor/lib.py", "x = 1\n")
        _commit_all(self.repo, "vendor")
        self.scan("--exclude", "vendor")
        self.write("vendor/lib.py", "x = 2\n")
        self.assertEqual(self.status()["dirty_files"], [])
        self.assertEqual(_run("refresh", "--repo", str(self.repo), "--quiet")[0], 0)
        self.write("NOTES.md")
        subprocess.run(["git", "-C", str(self.repo), "add", "-A"], check=True)
        self.assertEqual(self.status()["dirty_files"], ["NOTES.md"])

    def test_team_exclude_from_cdp_toml_is_honoured(self) -> None:
        self.write(".cdp.toml", 'exclude = ["vendor"]\n')
        self.write("vendor/lib.py", "x = 1\n")
        _commit_all(self.repo, "vendor")
        self.scan()
        self.write("vendor/lib.py", "x = 2\n")
        self.assertEqual(self.status()["dirty_files"], [])


if __name__ == "__main__":
    unittest.main()
