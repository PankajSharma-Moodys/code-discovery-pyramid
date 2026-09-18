"""Package-level scaffold test, plus the at-rest token measurement (7.1's own
acceptance line) and the SDK-free half of `server.py` (`_call`'s dispatch).

Run by `make check-interfaces`, never by `make check` -- the real-protocol
half of `server.py` (`create_server`/`main`) needs the `mcp` SDK installed;
this file skips that part cleanly when it is absent.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(SKILL_ROOT))
sys.path.insert(0, str(SKILL_ROOT / "tests"))

import mcp_server  # noqa: E402
from mcp_server import server as server_mod  # noqa: E402
from mcp_server.schemas import TOOL_SCHEMAS, estimate_at_rest_tokens  # noqa: E402


class MCPServerScaffoldTest(unittest.TestCase):
    def test_package_imports(self) -> None:
        self.assertTrue(mcp_server.__doc__)

    def test_real_mcp_sdk_is_optional(self) -> None:
        try:
            import mcp  # noqa: F401
        except ImportError:
            self.skipTest("`mcp` SDK not installed -- pip install cdp[mcp]")


class AtRestTokenCostTest(unittest.TestCase):
    """7.1's acceptance line: "MCP server at 3 tools with a measured at-rest
    token cost" -- measured, not asserted. The plan's own reference point is
    a 13-tool server at ~49.2k tokens; this asserts the shape of that
    argument (three tools costs much less), not the literal number, since
    the estimator is a crude chars/4 heuristic, not a real tokenizer."""

    def test_three_tools_cost_far_less_than_the_49_2k_reference_point(self) -> None:
        measured = estimate_at_rest_tokens()
        self.assertEqual(measured["tool_count"], 3)
        self.assertEqual(set(measured["per_tool"]), {"cdp_query", "cdp_scan", "cdp_status"})
        self.assertLess(measured["tokens_est"], 2000)

    def test_growing_the_tool_count_is_the_stress_test_named_in_the_plan(self) -> None:
        schemas = dict(TOOL_SCHEMAS)
        for i in range(10):
            schemas["extra_tool_%d" % i] = TOOL_SCHEMAS["cdp_query"]
        # Reproduces the plan's own stress-test row ("MCP tool count grows to
        # 13") mechanically: a 13-tool surface costs roughly 13/3 of a
        # 3-tool one under the same estimator, the concrete form of "the
        # token-at-rest objection returns in full" the plan warns about.
        import json

        from cdp.prompts import CHARS_PER_TOKEN_EST

        grown = sum(
            len(json.dumps({"name": n, **s}, sort_keys=True)) // CHARS_PER_TOKEN_EST
            for n, s in schemas.items()
        )
        measured = estimate_at_rest_tokens()
        self.assertGreater(grown, measured["tokens_est"] * 3)


class CallDispatchTest(unittest.TestCase):
    """`server._call` without the `mcp` SDK -- the dispatch logic itself
    carries no SDK dependency and is tested here directly."""

    @classmethod
    def setUpClass(cls) -> None:
        from helpers import make_repo

        cls.tmp = tempfile.TemporaryDirectory()
        tmp_path = Path(cls.tmp.name)
        cls.repo = make_repo(tmp_path / "repo")
        cls.state_dir = tmp_path / "state"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def test_call_scan_then_query_by_name(self) -> None:
        scan_result = server_mod._call(
            "cdp_scan", {"repo": str(self.repo), "state_dir": str(self.state_dir)}
        )
        self.assertEqual(scan_result["query"], "stats")
        status = server_mod._call(
            "cdp_status", {"repo": str(self.repo), "state_dir": str(self.state_dir)}
        )
        self.assertIn("run_id", status)

    def test_call_rejects_an_unknown_tool_name(self) -> None:
        with self.assertRaises(ValueError):
            server_mod._call("not_a_real_tool", {})

    def test_create_server_fails_loudly_without_the_sdk(self) -> None:
        try:
            import mcp  # noqa: F401
        except ImportError:
            with self.assertRaises(ImportError):
                server_mod.create_server()
        else:
            self.skipTest("`mcp` SDK is installed -- this asserts the absent-SDK path")


if __name__ == "__main__":
    unittest.main()
