"""The MCP surface is generated from the same guide as the CLI (E2/E3/E10).

* `cdp_query`'s schema covers all 14 kinds with enums and ranges, and exposes exactly
  the parameters the CLI `query` has (E3: `exclude_role` used to raise a TypeError).
* `cdp_help(topic)` returns the text `cdp help <topic>` prints.
* `cdp_query` and `cdp query --json` return the same answer for the same question.
"""

from __future__ import annotations

import contextlib
import inspect
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(SKILL_ROOT))
sys.path.insert(0, str(SKILL_ROOT / "tests"))

from helpers import make_repo  # noqa: E402

from cdp import query as query_mod  # noqa: E402
from cdp.cli import main  # noqa: E402
from cdp.guide_kinds import APPLIES, KINDS, PARAMS, ROLES, VIEWS  # noqa: E402
from mcp_server import server as server_mod, tools  # noqa: E402
from mcp_server.schemas import TOOL_SCHEMAS  # noqa: E402


class SchemaIsGenerated(unittest.TestCase):
    def test_query_schema_covers_every_kind_param_and_range(self) -> None:
        schema = TOOL_SCHEMAS["cdp_query"]
        props = schema["inputSchema"]["properties"]
        self.assertEqual(props["kind"]["enum"], list(KINDS))
        self.assertEqual(set(props["kind"]["enum"]), set(query_mod.QUERIES))
        self.assertEqual(set(props), set(PARAMS) | {"repo", "kind"})
        self.assertEqual(props["exclude_role"]["items"]["enum"], list(ROLES))
        self.assertEqual(props["budget"]["minimum"], 0)
        self.assertEqual(props["max_hops"]["minimum"], 0)
        self.assertFalse(schema["inputSchema"]["additionalProperties"])
        for kind in KINDS:
            self.assertIn("\n%s: " % kind, schema["description"])
        self.assertIn("paths (use frm/to)", props["term"]["description"])

    def test_tool_signature_matches_the_schema(self) -> None:
        params = set(inspect.signature(tools.cdp_query).parameters)
        self.assertEqual(params, set(TOOL_SCHEMAS["cdp_query"]["inputSchema"]["properties"]))

    def test_help_tool_is_registered_and_small(self) -> None:
        self.assertIn("cdp_help", tools.TOOLS)
        self.assertIn("cdp_help", TOOL_SCHEMAS)
        from mcp_server.schemas import estimate_at_rest_tokens

        self.assertLess(estimate_at_rest_tokens()["tokens_est"], 2000)


class AgainstARealScan(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        root = Path(cls.tmp.name)
        cls.repo = make_repo(root / "r", "orderrepo")
        cls._old = os.environ.get("CDP_HOME")
        os.environ["CDP_HOME"] = str(root / "home")
        with contextlib.redirect_stdout(io.StringIO()):
            assert main(["scan", "--repo", str(cls.repo), "--quiet"]) == 0

    @classmethod
    def tearDownClass(cls) -> None:
        if cls._old is None:
            os.environ.pop("CDP_HOME", None)
        else:
            os.environ["CDP_HOME"] = cls._old
        cls.tmp.cleanup()

    def _cli(self, *argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = main(["query", *argv, "--json", "--repo", str(self.repo)])
        return rc, json.loads(out.getvalue())

    def test_exclude_role_parity_with_the_cli(self) -> None:
        mcp = tools.cdp_query(str(self.repo), "symbol", "OrderService", exclude_role=["test"])
        _rc, cli = self._cli("symbol", "OrderService", "--exclude-role", "test")
        self.assertEqual(mcp, cli)
        everything = tools.cdp_query(str(self.repo), "symbol", "OrderService", exclude_role=list(ROLES))
        self.assertEqual(everything["found"], [])

    def test_tests_and_library_are_dropped_unless_asked_for(self) -> None:
        default = tools.cdp_query(str(self.repo), "claims", view="detail")
        self.assertIn("dropped by default: tests, library", default["default_filters"])
        self.assertFalse([c for c in default["claims"] if "library:" in c.get("subject", "")])
        kept = tools.cdp_query(str(self.repo), "claims", include_tests=True, include_library=True, view="detail")
        self.assertNotIn("default_filters", kept)
        self.assertGreaterEqual(kept["count"], default["count"])
        same = tools.cdp_query(str(self.repo), "symbol", "OrderService", exclude_role=["test"])
        self.assertEqual(same["found"], tools.cdp_query(str(self.repo), "symbol", "OrderService")["found"])
        with self.assertRaises(ValueError):  # include_library is a `claims` parameter only
            tools.cdp_query(str(self.repo), "symbol", "OrderService", include_library=True)

    def test_every_kind_answers_identically_over_both_channels(self) -> None:
        asks = {"trace": ("/orders",), "symbol": ("OrderService",), "file": ("OrderResource",),
                "module": ("root",), "routes": (), "table": ("orders",), "config": (),
                "search": ("order",), "claims": (), "unknowns": (), "conflicts": (),
                "stats": (), "coverage": ()}
        for kind, args in asks.items():
            for view in ((None,) if kind in ("stats", "coverage") else tuple(VIEWS)):
                rc, cli = self._cli(kind, *args, *(("--view", view) if view else ()))
                mcp = tools.cdp_query(str(self.repo), kind, *args, **({"view": view, "format": "json"} if view else {}))
                self.assertEqual(mcp, cli, "%s/%s" % (kind, view))
        rc, cli = self._cli("paths", "--from", "/orders")
        self.assertEqual(tools.cdp_query(str(self.repo), "paths", frm="/orders", format="json"), cli)
        # the text channel: the MCP tool text is the CLI text
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            main(["query", "routes", "--repo", str(self.repo)])
        self.assertEqual(tools.cdp_query(str(self.repo), "routes")["text"], out.getvalue().rstrip("\n"))

    def test_same_rejections_over_both_channels(self) -> None:
        with self.assertRaises(ValueError) as mcp:
            tools.cdp_query(str(self.repo), "paths", "term-not-used")
        self.assertIn("does not use `term`", str(mcp.exception))
        with self.assertRaises(ValueError):
            tools.cdp_query(str(self.repo), "routes", max_hops=2)

    def test_unknown_name_is_reported_not_silently_empty(self) -> None:
        result = tools.cdp_query(str(self.repo), "symbol", "OrderServce")
        self.assertIn("OrderService", result["not_found"]["did_you_mean"])

    def test_schema_rejects_bad_types_and_ranges_before_the_tool_runs(self) -> None:
        for bad in ({"max_hops": "2"}, {"budget": -1}, {"exclude_role": ["bogus"]}, {"claim_kind": "x"},
                    {"kind": "link"}):
            args = {"repo": str(self.repo), "kind": "stats", **bad}
            with self.assertRaises(server_mod.InvalidParams, msg=str(bad)):
                server_mod._call("cdp_query", args)

    def test_cdp_help_equals_cli_help_for_every_topic(self) -> None:
        topics = [None, "recipes", "reference"] + sorted(KINDS) + ["query", "scan", "link", "answer"]
        for topic in topics:
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rc = main(["help"] + ([topic] if topic else []))
            self.assertEqual(rc, 0)
            self.assertEqual(tools.cdp_help(topic)["text"].rstrip("\n"), out.getvalue().rstrip("\n"), topic)
        over_rpc = server_mod.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                                      "params": {"name": "cdp_help", "arguments": {"topic": "trace"}}})
        self.assertIn("WHAT", over_rpc["result"]["content"][0]["text"])

    def test_cdp_help_unknown_topic_is_an_error(self) -> None:
        with self.assertRaises(Exception):
            tools.cdp_help("nonesuch")


if __name__ == "__main__":
    unittest.main()
