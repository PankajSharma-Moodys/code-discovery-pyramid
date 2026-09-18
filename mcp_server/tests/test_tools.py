"""End-to-end test of the three tools against a real scanned fixture repo.

No `mcp` SDK needed here -- `tools.py` never imports it. Run by
`make check-interfaces`, never `make check`.
"""

from __future__ import annotations

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
        cls.state_dir = tmp_path / "state"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def test_scan_then_query_then_status(self) -> None:
        scan_result = tools.cdp_scan(str(self.repo), state_dir=str(self.state_dir))
        self.assertEqual(scan_result.get("query"), "stats")
        self.assertGreater(scan_result["symbols"], 0)

        stats = tools.cdp_query(str(self.repo), "stats", state_dir=str(self.state_dir))
        self.assertEqual(stats, scan_result)

        coverage = tools.cdp_query(str(self.repo), "coverage", state_dir=str(self.state_dir))
        self.assertEqual(coverage["query"], "coverage")
        self.assertEqual(coverage["coverage"], scan_result["coverage"])

        status = tools.cdp_status(str(self.repo), state_dir=str(self.state_dir))
        self.assertIn("run_id", status)
        self.assertEqual(status["coverage"], scan_result["coverage"])

    def test_unknown_kind_is_rejected(self) -> None:
        tools.cdp_scan(str(self.repo), state_dir=str(self.state_dir))
        with self.assertRaises(ValueError):
            tools.cdp_query(str(self.repo), "not_a_real_kind", state_dir=str(self.state_dir))

    def test_query_before_any_scan_fails_loudly(self) -> None:
        empty_repo = Path(self.tmp.name) / "unscanned"
        empty_repo.mkdir()
        with self.assertRaises(Exception):
            tools.cdp_query(str(empty_repo), "stats", state_dir=str(empty_repo / "state"))


if __name__ == "__main__":
    unittest.main()
