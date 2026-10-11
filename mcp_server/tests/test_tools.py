"""End-to-end test of the three tools against a real scanned fixture repo.

No `mcp` SDK needed here -- `tools.py` never imports it. Run by
`make check-interfaces`, never `make check`.
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(SKILL_ROOT))
sys.path.insert(0, str(SKILL_ROOT / "tests"))

from helpers import make_repo  # noqa: E402

from mcp_server import tools  # noqa: E402


class ToolsAgainstARealScanTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        tmp_path = Path(cls.tmp.name)
        cls.repo = make_repo(tmp_path / "repo")
        # Tools have no state-dir argument: the store is the machine one (`CDP_HOME`).
        cls._old_home = os.environ.get("CDP_HOME")
        os.environ["CDP_HOME"] = str(tmp_path / "home")

    @classmethod
    def tearDownClass(cls) -> None:
        if cls._old_home is None:
            os.environ.pop("CDP_HOME", None)
        else:
            os.environ["CDP_HOME"] = cls._old_home
        cls.tmp.cleanup()

    def test_scan_then_query_then_status(self) -> None:
        scan_result = tools.cdp_scan(str(self.repo))
        self.assertEqual(scan_result.get("query"), "stats")
        self.assertGreater(scan_result["symbols"], 0)

        stats = tools.cdp_query(str(self.repo), "stats")
        self.assertEqual(stats, scan_result)

        coverage = tools.cdp_query(str(self.repo), "coverage")
        self.assertEqual(coverage["query"], "coverage")
        self.assertEqual(coverage["coverage"], scan_result["coverage"])

        status = tools.cdp_status(str(self.repo))
        self.assertIn("run_id", status)
        self.assertEqual(status["coverage"], scan_result["coverage"])

    def test_unknown_kind_is_rejected(self) -> None:
        tools.cdp_scan(str(self.repo))
        with self.assertRaises(ValueError):
            tools.cdp_query(str(self.repo), "not_a_real_kind")

    def test_query_before_any_scan_fails_loudly(self) -> None:
        empty_repo = Path(self.tmp.name) / "unscanned"
        empty_repo.mkdir()
        with self.assertRaises(Exception):
            tools.cdp_query(str(empty_repo), "stats")

    def test_refresh_brings_a_stale_index_to_head_and_refuses_a_dirty_tree(self) -> None:
        import subprocess

        repo = make_repo(Path(self.tmp.name) / "refreshrepo")
        tools.cdp_scan(str(repo))
        before = tools.cdp_status(str(repo))
        self.assertEqual(before["behind"], 0)
        (repo / "README.md").write_text("changed\n")
        git = lambda *a: subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@x",
                                         "-c", "commit.gpgsign=false", *a], check=True, capture_output=True)
        git("add", "-A")
        git("commit", "-qm", "edit")
        self.assertEqual(tools.cdp_status(str(repo))["behind"], 1)
        result = tools.cdp_refresh(str(repo))
        self.assertTrue(result["refreshed"])
        self.assertEqual(result["status"]["behind"], 0)
        self.assertEqual(result["status"]["head"], result["status"]["git_head"])
        self.assertTrue(any("refresh" in line for line in result["log"]))
        (repo / "README.md").write_text("dirty\n")
        with self.assertRaises(Exception) as caught:
            tools.cdp_refresh(str(repo))
        self.assertIn("clean working tree", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
