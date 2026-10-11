"""`cdp_link`: cross-repo links over MCP (a headless session without the CLI could not answer
"which services call X?"), with cited, compact results and the shared validation layer."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(SKILL_ROOT))
sys.path.insert(0, str(SKILL_ROOT / "tests"))

from helpers import have_git, make_repo  # noqa: E402

from cdp.util import ArgError, CdpError  # noqa: E402
from mcp_server import server as server_mod, tools  # noqa: E402
from mcp_server.schemas import TOOL_SCHEMAS, estimate_at_rest_tokens  # noqa: E402


class SchemaTest(unittest.TestCase):
    def test_registered_small_and_closed(self) -> None:
        self.assertIn("cdp_link", tools.TOOLS)
        schema = TOOL_SCHEMAS["cdp_link"]["inputSchema"]
        self.assertEqual(schema["properties"]["action"]["enum"], ["scan", "scan_save", "query"])
        self.assertEqual(schema["required"], ["action"])
        self.assertFalse(schema["additionalProperties"])
        self.assertLess(estimate_at_rest_tokens()["tokens_est"], 2000)

    def test_bad_arguments_are_rejected_by_the_schema_and_the_tool(self) -> None:
        for bad in ({"action": "zap"}, {"action": "query", "service": 3}, {"action": "scan", "x": 1}):
            with self.assertRaises(server_mod.InvalidParams, msg=str(bad)):
                server_mod._call("cdp_link", bad)
        for args in ({"action": "zap"}, {"action": "query", "service": 3}, {"action": "query", "service": " "}):
            with self.assertRaises(ArgError, msg=str(args)):
                tools.cdp_link(**args)

    def test_guide_lists_the_tool_and_drops_cli_only_for_it(self) -> None:
        text = (SKILL_ROOT / "SKILL.md").read_text()
        self.assertIn("cdp_link", text)
        self.assertNotIn("`link ...` (cross-repo)", text)


@unittest.skipUnless(have_git(), "needs git")
class AgainstTwoScannedRepos(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from cdp.cli import main
        import contextlib
        import io

        cls.tmp = tempfile.TemporaryDirectory()
        root = Path(cls.tmp.name)
        (root / "repos").mkdir()
        cls.callee = make_repo(root / "repos", "calleerepo")
        cls.caller = make_repo(root / "repos", "callerrepo")
        cls._old = os.environ.get("CDP_HOME")
        os.environ["CDP_HOME"] = str(root / "home")
        for repo in (cls.caller, cls.callee):
            with contextlib.redirect_stdout(io.StringIO()):
                assert main(["scan", "--repo", str(repo), "--quiet"]) == 0

    @classmethod
    def tearDownClass(cls) -> None:
        if cls._old is None:
            os.environ.pop("CDP_HOME", None)
        else:
            os.environ["CDP_HOME"] = cls._old
        cls.tmp.cleanup()

    def test_query_by_name_answers_without_a_prior_save_and_cites_both_ends(self) -> None:
        out = tools.cdp_link("query", "calleerepo")
        self.assertEqual(out["service"], "calleerepo")
        self.assertEqual(out["totals"], {"links": 1, "exact": 1, "heuristic": 0, "unmatched": 0})
        link = out["links"][0]
        self.assertEqual(link["call"], "POST /v1/charges")
        self.assertEqual(link["match"], "exact")
        self.assertRegex(link["caller"], r"^callerrepo:.+BillingClient\.java:\d+$")
        self.assertRegex(link["callee"], r"^calleerepo:.+ChargeResource\.java:\d+$")

    def test_scan_is_read_only_and_scan_save_persists_for_the_cli(self) -> None:
        db = Path(os.environ["CDP_HOME"]) / "index.db"
        tools.cdp_link("scan")
        from cdp.store.sqlite_backend import SqliteStore

        def saved() -> int:
            store = SqliteStore(db, readonly=True)
            try:
                return len(store.read_link_edges())
            finally:
                store.close()

        self.assertEqual(saved(), 0)
        out = tools.cdp_link("scan_save")
        self.assertEqual(out["totals"]["links"], 1)
        self.assertEqual(saved(), 1)

    def test_unknown_service_lists_the_known_names_and_service_needs_query(self) -> None:
        with self.assertRaises(CdpError) as ctx:
            tools.cdp_link("query", "nope")
        self.assertIn("callerrepo", str(ctx.exception))
        with self.assertRaises(CdpError):
            tools.cdp_link("query")
        with self.assertRaises(CdpError):
            tools.cdp_link("scan", "calleerepo")

    def test_over_rpc_the_result_is_json_text(self) -> None:
        reply = server_mod.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                                   "params": {"name": "cdp_link",
                                              "arguments": {"action": "query", "service": "callerrepo"}}})
        self.assertNotIn("isError", reply["result"])
        self.assertIn("BillingClient", reply["result"]["content"][0]["text"])


if __name__ == "__main__":
    unittest.main()
