"""`cdp install --framework` — Phase 9, 7.4 follow-up.

`.claude/agents/cdp-leaf.md` is a Claude Code discovery convention; a target
repo driving its leaves through LangGraph or ADK has no use for it. These
tests pin the three things that must hold: the default (`claude-code`) is
unchanged from before `--framework` existed, `langgraph`/`adk`/`none` copy no
agent-registration file, and `--hook` (a Claude Code concept) refuses to
combine with any other framework.
"""

from __future__ import annotations

import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from helpers import SKILL_ROOT  # noqa: F401  (sets sys.path)

from cdp.cli import main


class InstallFrameworkTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def _install(self, target: Path, *extra_args: str) -> None:
        with contextlib.redirect_stdout(io.StringIO()):
            main(["install", str(target), *extra_args])

    def test_default_framework_still_installs_cdp_leaf(self) -> None:
        target = Path(self.tmp.name) / "default"
        target.mkdir()
        self._install(target)
        self.assertTrue((target / ".claude" / "agents" / "cdp-leaf.md").exists())

    def test_explicit_claude_code_installs_cdp_leaf(self) -> None:
        target = Path(self.tmp.name) / "explicit"
        target.mkdir()
        self._install(target, "--framework", "claude-code")
        self.assertTrue((target / ".claude" / "agents" / "cdp-leaf.md").exists())

    def test_langgraph_writes_no_agent_file(self) -> None:
        target = Path(self.tmp.name) / "langgraph"
        target.mkdir()
        self._install(target, "--framework", "langgraph")
        self.assertFalse((target / ".claude" / "agents").exists())

    def test_adk_writes_no_agent_file(self) -> None:
        target = Path(self.tmp.name) / "adk"
        target.mkdir()
        self._install(target, "--framework", "adk")
        self.assertFalse((target / ".claude" / "agents").exists())

    def test_none_writes_no_agent_file(self) -> None:
        target = Path(self.tmp.name) / "none"
        target.mkdir()
        self._install(target, "--framework", "none")
        self.assertFalse((target / ".claude" / "agents").exists())

    def test_hook_with_non_claude_code_framework_raises(self) -> None:
        target = Path(self.tmp.name) / "bad-hook"
        target.mkdir()
        with contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()):
            code = main(["install", str(target), "--framework", "langgraph", "--hook"])
        self.assertEqual(code, 2)
        # and no partial installation was left half-configured by the hook step
        self.assertFalse((target / ".claude" / "settings.json").exists())


if __name__ == "__main__":
    unittest.main()
