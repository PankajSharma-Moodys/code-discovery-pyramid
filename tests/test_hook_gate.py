"""The gate and the empty-search hook never act wrongly (D1-D5, E1, E12), and what
`install --harness` writes is safe by default (J4, J9)."""

from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from helpers import have_git, make_repo

from cdp import hook as hook_mod
from cdp.cli import main

HOOK = Path(__file__).resolve().parent.parent / "cdp" / "hook.py"


class _Indexed:
    """A scanned reservrepo in its own machine home."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name) / "home"
        patcher = mock.patch.dict(os.environ, {"CDP_HOME": str(self.home)})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.repo = make_repo(Path(self.tmp.name), "reservrepo")
        main(["scan", "--repo", str(self.repo), "--quiet"])

    def ev(self, tool, session, **tool_input):
        return {"session_id": self.id() + session, "cwd": str(self.repo),
                "tool_name": tool, "tool_input": tool_input}

    def bash(self, command, session="a"):
        return hook_mod.gate_decide(self.ev("Bash", session, command=command))

    def run_hook(self, flag, event):
        return subprocess.run([sys.executable, str(HOOK), flag], input=json.dumps(event),
                              capture_output=True, text=True, timeout=60,
                              env=dict(os.environ, CDP_HOME=str(self.home)))


@unittest.skipUnless(have_git(), "needs a real git repository")
class GateWrongBlockTest(_Indexed, unittest.TestCase):
    """E1, D1-D4: the gate never blocks on a partial, empty or compound answer."""

    GREP = "grep -rn processPendingReservations ."

    def test_mcp_query_counts_as_the_index_being_asked(self) -> None:
        self.assertIsNotNone(self.bash(self.GREP, session="control"))   # without a query: denied
        for i, name in enumerate(("mcp__cdp__cdp_query", "mcp__myidx__cdp_query",
                                  "mcp__plugin_cdp_cdp__cdp_query")):
            sid = "asked%d" % i
            self.assertIsNone(hook_mod.gate_decide(self.ev(name, sid, repo=str(self.repo), kind="symbol")))
            self.assertIsNone(self.bash(self.GREP, session=sid), name)
            self.assertIsNone(hook_mod.gate_decide(self.ev("Grep", sid, pattern="processPendingReservations")))
        hook_mod.gate_decide(self.ev("mcp__github__list_issues", "other"))  # not the index
        self.assertIsNotNone(self.bash(self.GREP, session="other"))

    def test_gate_entry_point_honours_the_mcp_query(self) -> None:
        self.assertEqual(self.run_hook("--gate", self.ev("mcp__cdp__cdp_query", "cli", kind="symbol")).stdout, "")
        grep = self.ev("Bash", "cli", command=self.GREP)
        self.assertEqual(self.run_hook("--gate", grep).stdout, "")
        grep["session_id"] = "fresh-session"
        self.assertIn('"deny"', self.run_hook("--gate", grep).stdout)

    def test_a_search_with_any_unanswered_term_runs(self) -> None:
        for i, command in enumerate((
                'grep -rn "jdbc:sqlserver\\|processPendingReservations" .',        # no symbol for one term
                "grep -rn 'processPendingReservations\\|NoSuchSymbolAnywhere' .",  # unknown name
                "grep -rnE 'processPendingReservations|makeReservations|checkIdempotency|getReservationCapacity' .",
                "grep -rn processPendingReservations --include=*.xml .",           # a type the index lacks
                "grep -rn -A3 processPendingReservations .",                       # asks for context lines
                "grep -rnv processPendingReservations .")):
            self.assertIsNone(self.bash(command, session="d1%d" % i), command)

    def test_compound_commands_are_never_blocked(self) -> None:
        for i, command in enumerate((
                "git log -S processPendingReservations --oneline ; grep -rn processPendingReservations .",
                "grep -rn processPendingReservations . && echo done",
                "cd src && grep -rn processPendingReservations .",
                "grep -rn processPendingReservations . | grep -v test",
                "grep -rn processPendingReservations . > out.txt",
                "grep -rn processPendingReservations $(pwd)")):
            self.assertIsNone(self.bash(command, session="d2%d" % i), command)
        self.assertIsNotNone(self.bash(self.GREP + " 2>&1 | head -20", session="d2ok"))  # a limiter is still a search

    def test_an_empty_answer_never_blocks(self) -> None:
        # ProcessPendingJob is indexed but has no recorded use: a who-uses-it grep is not answered
        self.assertIsNone(self.bash("grep -rn ProcessPendingJob .", session="d3"))
        self.assertIsNone(hook_mod.gate_decide(self.ev("Grep", "d3b", pattern="ProcessPendingJob")))
        self.assertIsNotNone(self.bash(self.GREP, session="d3"))  # and the denial was not spent

    def test_find_by_glob_is_answered_with_every_match(self) -> None:
        result = self.bash("find . -name 'Reservation*.java'", session="f1")
        self.assertIn("ReservationService.java", result["message"])
        self.assertIn("ReservationResource.java", result["message"])
        self.assertIsNone(self.bash("find . -name '*Service.java'", session="f2"))
        self.assertIsNone(self.bash("find . -type d -name ReservationService", session="f3"))

    def test_the_deny_payload_has_no_system_message(self) -> None:
        body = hook_mod.payload("m", block=True)
        self.assertNotIn("systemMessage", body)
        self.assertEqual(body["hookSpecificOutput"]["permissionDecision"], "deny")


@unittest.skipUnless(have_git(), "needs a real git repository")
class SessionStartTextTest(_Indexed, unittest.TestCase):
    def test_a_deterministic_scan_is_not_called_model_reviewed(self) -> None:
        text = hook_mod.session_start({"cwd": str(self.repo)})
        self.assertIn("0.0% model-reviewed (deterministic index complete; run `cdp run` for AI review)", text)
        self.assertNotIn("model-reviewed coverage", text)
        self.assertIn("cdp_query", text)


class NudgeAndMarkerTest(unittest.TestCase):
    def test_nudge_without_a_file_does_not_suggest_a_file_outline(self) -> None:
        for path in (".", ""):
            text = hook_mod.nudge_text("a" * 40, path, False)
            self.assertNotIn("query file .", text)
            self.assertNotIn("outline", text)
        self.assertIn("`file` with term `src/A.java`", hook_mod.nudge_text("a" * 40, "src/A.java", False))

    def test_markers_are_pruned_by_age_and_count(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            d, now = Path(tmp), time.time()
            for i in range(10):
                (d / ("cdp-gate-%d" % i)).touch()
                os.utime(d / ("cdp-gate-%d" % i), (now - 3 * 86400,) * 2)
            for i in range(30):
                (d / ("cdp-hook-%d" % i)).touch()
                os.utime(d / ("cdp-hook-%d" % i), (now - i,) * 2)
            (d / "other-file").touch()
            self.assertEqual(hook_mod.prune_markers(d, max_age=86400, max_count=20), 20)
            self.assertEqual(len([p for p in d.iterdir() if p.name.startswith("cdp-")]), 20)
            self.assertTrue((d / "other-file").exists())
            self.assertTrue((d / "cdp-hook-0").exists())      # newest kept
            self.assertFalse((d / "cdp-hook-29").exists())    # oldest beyond the bound gone

    def test_claiming_prunes_old_markers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(tempfile, "tempdir", tmp):
            old = Path(tmp) / "cdp-gate-stale"
            old.touch()
            os.utime(old, (time.time() - 5 * 86400,) * 2)
            self.assertTrue(hook_mod.claim_session(Path(tmp) / "state", "s"))
            self.assertFalse(old.exists())

    def test_only_one_turns_the_leaf_switch_on(self) -> None:
        sample = '{"tool_name": "Bash", "tool_input": {"command": "x"}, "cwd": "/tmp"}'
        for value, stands_down in (("1", True), ("0", False), ("", False)):
            called = []
            with mock.patch.dict(os.environ, {"CDP_LEAF_SESSION": value}), \
                    mock.patch.object(hook_mod, "gate_decide", lambda e: called.append(e)), \
                    mock.patch.object(sys, "stdin", io.StringIO(sample)):
                hook_mod.main(["--gate"])
            self.assertEqual(not called, stands_down, "CDP_LEAF_SESSION=%r" % value)


REAL_EMPTY_GREP = {  # captured from Claude Code 2.1.296: the PostToolUse of an empty Bash grep
    "hook_event_name": "PostToolUse", "tool_name": "Bash",
    "tool_response": {"stdout": "", "stderr": "", "interrupted": False, "isImage": False,
                      "returnCodeInterpretation": "No matches found", "noOutputExpected": False},
}


@unittest.skipUnless(have_git(), "needs a real git repository")
class PostSearchTest(_Indexed, unittest.TestCase):
    """E12: an empty search for a name the index knows gets a pointer to `cdp_query`."""

    def post(self, session, command=None, tool="Bash", response=None, **tool_input):
        ev = dict(REAL_EMPTY_GREP, session_id=self.id() + session, cwd=str(self.repo), tool_name=tool,
                  tool_input=({"command": command} if command else tool_input))
        if response is not None:
            ev["tool_response"] = response
        return hook_mod.post_search(ev)

    def test_empty_grep_for_a_known_symbol_points_at_cdp_query(self) -> None:
        command = "grep -rn processPendingReservations --include=*.xml ."
        message = self.post("p1", command)
        for needle in ("processPendingReservations", "cdp_query", "symbol", "ReservationService.java"):
            self.assertIn(needle, message)
        self.assertIsNone(self.post("p1", command), "once per subject")

    def test_a_typo_gets_the_near_name(self) -> None:
        self.assertIn("processPendingReservations", self.post("p2", "grep -rn processPendingReservation ."))

    def test_silent_for_unknown_terms_non_empty_results_and_non_searches(self) -> None:
        self.assertIsNone(self.post("p3", "grep -rn QuiteUnknownIdentifier ."))
        self.assertIsNone(self.post("p4", "grep -rn processPendingReservations .",
                                    response={"stdout": "a.java:1:x", "stderr": ""}))
        self.assertIsNone(self.post("p5", "ls nothing"))

    def test_grep_and_glob_tool_shapes(self) -> None:
        self.assertIn("cdp_query", self.post("p6", tool="Grep", pattern="processPendingReservations",
                                             response={"mode": "files_with_matches", "numFiles": 0, "filenames": []}))
        self.assertIn("ReservationService", self.post("p7", tool="Glob", pattern="**/ReservationService*.kt",
                                                       response={"filenames": [], "numFiles": 0}))

    def test_entry_point_emits_post_tool_use_context(self) -> None:
        ev = dict(REAL_EMPTY_GREP, session_id="cli-post", cwd=str(self.repo),
                  tool_input={"command": "grep -rn processPendingReservations --include=*.xml ."})
        out = json.loads(self.run_hook("--post-search", ev).stdout)["hookSpecificOutput"]
        self.assertEqual(out["hookEventName"], "PostToolUse")
        self.assertIn("cdp_query", out["additionalContext"])


class HarnessInstallTest(unittest.TestCase):
    def setUp(self) -> None:
        import contextlib
        self._quiet = contextlib.redirect_stdout(io.StringIO())
        self._quiet.__enter__()
        self.addCleanup(lambda: self._quiet.__exit__(None, None, None))
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.target = Path(self.tmp.name) / "t"
        self.target.mkdir()

    def settings(self):
        return json.loads((self.target / ".claude" / "settings.json").read_text())

    def test_default_harness_writes_no_deny_hook_and_no_new_repo_file(self) -> None:
        main(["install", str(self.target), "--harness"])
        settings = self.settings()
        commands = [h["command"] for g in settings["hooks"]["PreToolUse"] for h in g["hooks"]]
        self.assertFalse([c for c in commands if "--gate" in c or "--strict" in c], commands)
        self.assertFalse((self.target / "AGENTS.md").exists())
        post = settings["hooks"]["PostToolUse"][0]
        self.assertIn("Bash", post["matcher"])
        self.assertTrue(post["hooks"][0]["command"].endswith('hook.py" --post-search'))
        main(["install", str(self.target), "--agents-md"])
        self.assertTrue((self.target / "AGENTS.md").exists())

    def test_strict_installs_the_gate_and_back_again(self) -> None:
        main(["install", str(self.target), "--harness", "--strict"])
        pre = self.settings()["hooks"]["PreToolUse"]
        self.assertEqual(len(pre), 1)
        self.assertTrue(pre[0]["hooks"][0]["command"].endswith('hook.py" --gate'))
        self.assertIn("mcp__.*cdp_query", pre[0]["matcher"])
        main(["install", str(self.target), "--harness"])
        pre = self.settings()["hooks"]["PreToolUse"]
        self.assertEqual([h["command"].endswith('hook.py"') for g in pre for h in g["hooks"]], [True])

    def test_paths_are_portable_and_uninstall_leaves_no_empty_files(self) -> None:
        main(["install", str(self.target), "--harness"])
        text = (self.target / ".claude" / "settings.json").read_text() + (self.target / ".mcp.json").read_text()
        self.assertNotIn(str(self.target), text)
        self.assertNotIn(str(Path(__file__).resolve().parent.parent), text)
        self.assertIn("$CLAUDE_PROJECT_DIR", text)
        # `${CLAUDE_PROJECT_DIR}` alone is undefined for MCP config (the server then fails to start)
        self.assertIn("${CLAUDE_PROJECT_DIR:-.}/.claude/skills/cdp", (self.target / ".mcp.json").read_text())
        self.assertTrue((self.target / ".claude" / "skills" / "cdp" / "mcp_server" / "server.py").exists())
        main(["install", "--remove-harness", str(self.target)])
        self.assertFalse((self.target / ".claude" / "settings.json").exists())
        self.assertFalse((self.target / ".mcp.json").exists())

    def test_uninstall_keeps_files_that_have_other_content(self) -> None:
        (self.target / ".claude").mkdir()
        (self.target / ".claude" / "settings.json").write_text('{"model": "opus"}')
        (self.target / ".mcp.json").write_text('{"mcpServers": {"other": {"command": "x"}}}')
        main(["install", str(self.target), "--harness"])
        main(["install", "--remove-harness", str(self.target)])
        self.assertEqual(self.settings(), {"model": "opus"})
        self.assertEqual(list(json.loads((self.target / ".mcp.json").read_text())["mcpServers"]), ["other"])

    def test_strict_without_a_hook_is_an_error_not_silently_ignored(self) -> None:
        self.assertNotEqual(main(["install", str(self.target), "--strict"]), 0)

    def test_bad_settings_refuses_before_copying_anything(self) -> None:
        (self.target / ".claude").mkdir()
        (self.target / ".claude" / "settings.json").write_text("{not json")
        self.assertNotEqual(main(["install", str(self.target), "--harness"]), 0)
        self.assertFalse((self.target / ".claude" / "skills").exists())


if __name__ == "__main__":
    unittest.main()
