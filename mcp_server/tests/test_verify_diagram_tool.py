"""`cdp_verify_diagram` over the server's own dispatch."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(SKILL_ROOT))

from mcp_server import server as server_mod  # noqa: E402

DIAGRAM = """```mermaid
flowchart TD
  cmd_verify_diagram -->|"calls exit_code cdp/commands/core/verify_diagram.py:43"| exit_code
  cmd_verify_diagram -->|"calls frobnicate_widget cdp/commands/core/verify_diagram.py:1"| frobnicate_widget
  cmd_verify_diagram -.-> other
```"""


class VerifyDiagramToolTest(unittest.TestCase):
    def test_statuses_through_dispatch(self) -> None:
        r = server_mod._call("cdp_verify_diagram", {"repo": str(SKILL_ROOT), "diagram": DIAGRAM})
        st = [e["status"] for e in r["diagrams"][0]["edges"]]
        self.assertEqual(st[0], "correct")
        self.assertIn(st[1], ("unsupported", "wrong_citation"))
        self.assertEqual(st[2], "inferred")
        self.assertFalse(r["ok"])
        self.assertEqual(r["counts"]["correct"], 1)

    def test_bad_args(self) -> None:
        with self.assertRaises(server_mod.InvalidParams):
            server_mod._call("cdp_verify_diagram", {"repo": "."})


if __name__ == "__main__":
    unittest.main()
