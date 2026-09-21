"""`agent_adapter`'s own test suite (Phase 9, 7.4).

Run by `make check-interfaces`, never by `make check` -- see
`mcp_server/tests/test_mcp_server.py` for why. The SDK-free core
(`tool_specs()`) is exercised directly; the two thin wrappers
(`langgraph.py`/`adk.py`) are only smoke-tested for their "not installed"
failure mode, since neither SDK is present in this environment.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import agent_adapter  # noqa: E402
from mcp_server import tools as mcp_tools  # noqa: E402


class AgentAdapterScaffoldTest(unittest.TestCase):
    def test_package_imports(self) -> None:
        self.assertTrue(agent_adapter.__doc__)

    def test_real_langgraph_package_is_optional(self) -> None:
        try:
            import langchain_core  # noqa: F401
        except ImportError:
            self.skipTest("`langchain-core` not installed -- pip install cdp[agent]")

    def test_real_adk_package_is_optional(self) -> None:
        try:
            import google.adk  # noqa: F401
        except ImportError:
            self.skipTest("`google-adk` not installed -- pip install cdp[agent]")


class ToolSpecsTest(unittest.TestCase):
    def test_specs_cover_the_same_three_tools_as_mcp_server(self) -> None:
        specs = agent_adapter.tool_specs()
        self.assertEqual(set(specs), set(mcp_tools.TOOLS))

    def test_each_spec_has_a_nonempty_description_from_cdp_help(self) -> None:
        for name, spec in agent_adapter.tool_specs().items():
            self.assertEqual(spec.name, name)
            self.assertTrue(spec.description)
            self.assertIs(spec.func, mcp_tools.TOOLS[name])

    def test_missing_help_command_raises_rather_than_silently_dropping_a_tool(self) -> None:
        with unittest.mock.patch.object(
            agent_adapter, "_command_summaries", return_value={"query": "x", "status": "y"}
        ):
            with self.assertRaises(KeyError):
                agent_adapter.tool_specs()


class LangGraphWrapperTest(unittest.TestCase):
    def test_raises_a_clear_error_without_langchain_core(self) -> None:
        try:
            import langchain_core  # noqa: F401
        except ImportError:
            pass
        else:
            self.skipTest("langchain-core is installed -- this test only covers its absence")
        from agent_adapter.langgraph import build_langgraph_tools

        with self.assertRaises(ImportError):
            build_langgraph_tools()


class AdkWrapperTest(unittest.TestCase):
    def test_raises_a_clear_error_without_google_adk(self) -> None:
        try:
            import google.adk  # noqa: F401
        except ImportError:
            pass
        else:
            self.skipTest("google-adk is installed -- this test only covers its absence")
        from agent_adapter.adk import build_adk_tools

        with self.assertRaises(ImportError):
            build_adk_tools()


class LangGraphLeafTest(unittest.TestCase):
    def test_raises_without_a_model(self) -> None:
        from agent_adapter.langgraph_leaf import run_leaf

        with unittest.mock.patch("pathlib.Path.read_text", return_value="node: x\nrun_id: y\n"):
            with self.assertRaises(ValueError):
                run_leaf(Path("prompt.md"), Path("patch.json"), model=None)

    def test_invalid_patch_from_model_is_written_as_failed(self) -> None:
        from agent_adapter.langgraph_leaf import run_leaf

        class _FakeStructuredModel:
            def invoke(self, _messages):
                return {"schema_version": "1.0.0"}  # missing required fields

        class _FakeModel:
            def with_structured_output(self, _schema, include_raw=False):
                return _FakeStructuredModel()

        try:
            import langchain_core  # noqa: F401
        except ImportError:
            self.skipTest("langchain-core not installed -- pip install cdp[agent]")

        with tempfile.TemporaryDirectory() as tmp:
            prompt_path = Path(tmp) / "prompt.md"
            prompt_path.write_text("node: root/x\nrun_id: r1\n")
            inbox_path = Path(tmp) / "patch.json"

            run_leaf(prompt_path, inbox_path, model=_FakeModel())

            written = json.loads(inbox_path.read_text())
            self.assertEqual(written["status"], "failed")
            self.assertEqual(written["node"], "root/x")
            self.assertIn("error", written)


class AdkLeafTest(unittest.TestCase):
    def test_raises_without_an_agent(self) -> None:
        from agent_adapter.adk_leaf import run_leaf

        with unittest.mock.patch("pathlib.Path.read_text", return_value="node: x\nrun_id: y\n"):
            with self.assertRaises(ValueError):
                run_leaf(Path("prompt.md"), Path("patch.json"), agent=None)

    def test_raises_a_clear_error_without_google_adk(self) -> None:
        try:
            import google.adk  # noqa: F401
        except ImportError:
            pass
        else:
            self.skipTest("google-adk is installed -- this test only covers its absence")
        from agent_adapter.adk_leaf import run_leaf

        class _FakeAgent:
            tools = []

            def run(self, _prompt):
                raise AssertionError("should not reach agent.run without google.adk")

        with tempfile.TemporaryDirectory() as tmp:
            prompt_path = Path(tmp) / "prompt.md"
            prompt_path.write_text("node: root/x\nrun_id: r1\n")
            with self.assertRaises(ImportError):
                run_leaf(prompt_path, Path(tmp) / "patch.json", agent=_FakeAgent())


if __name__ == "__main__":
    unittest.main()
