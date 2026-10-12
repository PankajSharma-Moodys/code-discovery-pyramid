"""Intent-specific prompt text, call-specific PreToolUse nudges, and the opt-in install extras
(`--claude-md`, `--allow-mcp`, `--priority`)."""

from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from helpers import have_git, make_repo  # noqa: F401  (sets sys.path)

from cdp import hook as hook_mod, hook_intent, install_extras
from cdp.cli import main
from cdp.guide_kinds import KINDS


class PromptIntentTest(unittest.TestCase):
    CASES = [
        ("Who calls ReservationService.makeReservations in this repo?", "symbol", "makeReservations"),
        ("What breaks if I change the ServerService class?", "trace", "ServerService"),
        ("Which database tables does the POST /unified-store/sql-pool/v1/reservations route touch?", "trace",
         "/unified-store/sql-pool/v1/reservations"),
        ("Which tables does the app use?", "table", None),
        ("Where is the SQL_POOL_SCHEMA config key read?", "config", "SQL_POOL_SCHEMA"),
        ("What HTTP endpoints does this service expose?", "routes", None),
        ("How does the EventBus flow work in sql-pool-service?", "trace", "EventBus"),
        ('Where is the string constant "read-only" used?', "search", "read-only"),
    ]

    def test_each_question_gets_its_one_kind_and_term(self) -> None:
        for prompt, kind, term in self.CASES:
            got = hook_intent.prompt_intent(prompt)
            self.assertIsNotNone(got, prompt)
            self.assertEqual((got[1], got[2]), (kind, term), prompt)

    def test_jobs_names_the_jobs_kind_only_when_it_exists(self) -> None:
        q = "Which Quartz jobs exist in this repo and when does each run?"
        without = {k: v for k, v in KINDS.items() if k != "jobs"}
        with mock.patch.object(hook_intent, "KINDS", without):
            self.assertEqual(hook_intent.prompt_intent(q)[1], "search")
        with mock.patch.object(hook_intent, "KINDS", {**without, "jobs": {"summary": "x"}}):
            self.assertEqual(hook_intent.prompt_intent(q)[1], "jobs")

    def test_silent_when_the_prompt_is_not_about_code(self) -> None:
        for prompt in ("fix the typo in the readme", "thanks, that is all", "hi", "write a haiku about spring"):
            self.assertIsNone(hook_intent.prompt_hint(prompt, "/r"), prompt)

    def test_hint_is_short_names_the_call_and_the_coverage_check(self) -> None:
        text = hook_intent.prompt_hint(self.CASES[0][0], "/r")
        self.assertLessEqual(len(text.splitlines()), 3)
        self.assertIn('cdp_query(repo="/r", kind="symbol", term="makeReservations")', text)
        self.assertIn("coverage", text)
        self.assertNotIn("kinds:", text)  # the old generic list of every kind is gone

    def test_every_named_kind_exists_in_the_guide(self) -> None:
        for prompt, *_ in self.CASES:
            self.assertIn(hook_intent.prompt_intent(prompt)[1], KINDS)


class CallHintTest(unittest.TestCase):
    def hint(self, tool, **tool_input):
        got = hook_intent.call_hint(tool, tool_input, "/r", tool_input.pop("_rel", "a/B.java"))
        return got and got[1]

    def test_identifier_grep_names_symbol_with_that_term(self) -> None:
        self.assertIn('kind="symbol", term="ReservationService"', self.hint("Grep", pattern="ReservationService"))
        self.assertIn('kind="symbol", term="makeReservations"', self.hint("Bash", command="grep -rn makeReservations ."))

    def test_a_jobs_pattern_names_jobs_or_the_search_fallback(self) -> None:
        text = self.hint("Grep", pattern="cron|schedule|Quartz|Job")
        self.assertIn("kind=", text)
        self.assertRegex(text, r'kind="(jobs|search)"')

    def test_path_glob_and_find_name_the_file_kind(self) -> None:
        self.assertIn('kind="file", term="Server"', self.hint("Glob", pattern="**/Server*.java"))
        self.assertIn('kind="file", term="Job"', self.hint("Bash", command="find . -name '*Job*.java'"))

    def test_route_config_and_table_patterns(self) -> None:
        self.assertIn('kind="routes"', self.hint("Grep", pattern="@Path|@GetMapping"))
        self.assertIn('kind="config", term="SQL_POOL_SCHEMA"', self.hint("Grep", pattern="getenv\\(\"SQL_POOL_SCHEMA\"\\)"))
        self.assertIn('kind="table"', self.hint("Grep", pattern="insert into"))

    def test_whole_file_read_names_the_outline_and_a_ranged_read_is_silent(self) -> None:
        self.assertIn('kind="file", term="a/B.java"', self.hint("Read", file_path="/r/a/B.java"))
        self.assertIsNone(self.hint("Read", file_path="/r/a/B.java", offset=3, limit=9))


@unittest.skipUnless(have_git(), "needs a real git repository")
class NudgeFlowTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        patcher = mock.patch.dict(os.environ, {"CDP_HOME": str(Path(self.tmp.name) / "home")})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.repo = make_repo(Path(self.tmp.name), "reservrepo")
        main(["scan", "--repo", str(self.repo), "--quiet"])

    def ev(self, tool, session="s", **tool_input):
        return {"session_id": self.id() + session, "cwd": str(self.repo), "tool_name": tool, "tool_input": tool_input}

    def test_once_per_subject_then_a_new_subject_nudges_again(self) -> None:
        first = hook_mod.decide(self.ev("Grep", pattern="ReservationService"))
        self.assertIn('term="ReservationService"', first)
        self.assertIsNone(hook_mod.decide(self.ev("Grep", pattern="ReservationService")))
        self.assertIn('term="ProcessPendingJob"', hook_mod.decide(self.ev("Grep", pattern="ProcessPendingJob")))

    def test_at_most_max_nudges_a_session(self) -> None:
        names = ["ReservationService", "ProcessPendingJob", "PostgresServerHelper", "MssqlServerHelper"]
        got = [hook_mod.decide(self.ev("Grep", pattern=n)) for n in names]
        self.assertEqual(sum(1 for g in got if g), hook_mod.MAX_NUDGES)

    def test_silent_for_the_rest_of_the_session_once_cdp_was_used(self) -> None:
        self.assertIsNone(hook_mod.decide(self.ev("mcp__cdp__cdp_query", kind="symbol", term="x")))
        self.assertIsNone(hook_mod.decide(self.ev("Grep", pattern="ReservationService")))
        # another session is unaffected
        self.assertIsNotNone(hook_mod.decide(self.ev("Grep", session="other", pattern="ReservationService")))

    def test_the_nudge_matcher_also_sees_cdp_query_so_it_can_go_quiet(self) -> None:
        from cdp.install import HOOK_MATCHER
        import re
        self.assertTrue(re.match(HOOK_MATCHER, "mcp__cdp__cdp_query"))
        self.assertTrue(re.match(HOOK_MATCHER, "Grep"))
        self.assertFalse(re.match(HOOK_MATCHER, "Edit"))


class InstallExtrasTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.target = Path(self.tmp.name) / "t"
        self.target.mkdir()
        patcher = mock.patch.dict(os.environ, {"CDP_HOME": str(Path(self.tmp.name) / "home")})
        patcher.start()
        self.addCleanup(patcher.stop)

    def install(self, *flags):
        with contextlib.redirect_stdout(io.StringIO()) as out:
            main(["install", str(self.target), *flags])
        return out.getvalue()

    # ----------------------------------------------------------- CLAUDE.md
    def test_claude_md_is_created_idempotent_and_removed(self) -> None:
        path = self.target / "CLAUDE.md"
        self.install("--claude-md")
        first = path.read_text()
        self.install("--claude-md")
        self.assertEqual(path.read_text(), first)
        self.assertEqual(first.count(install_extras.END), 1)
        self.install("--remove-harness")
        self.assertFalse(path.exists())

    def test_claude_md_never_touches_text_outside_the_markers(self) -> None:
        path = self.target / "CLAUDE.md"
        before, after = "# Mine\n\nrule one\n", "\n## Later\nrule two\n"
        path.write_text(before)
        self.install("--claude-md")
        path.write_text(path.read_text() + after)
        self.install("--claude-md")  # refresh in place
        self.assertEqual(path.read_text().count(install_extras.END), 1)
        self.install("--remove-harness")
        self.assertEqual(path.read_text(), before + after)

    def test_claude_md_block_is_generated_from_the_guide_and_is_a_must_rule(self) -> None:
        block = install_extras.claude_md_block()
        self.assertIn("MUST", block)
        for kind in ("symbol", "trace", "routes", "table", "config", "coverage"):
            self.assertIn("`%s`" % kind, block)
        rows = [r for r in block.splitlines() if r.startswith("| ") and "`" in r and "Question" not in r]
        self.assertEqual(len(rows), 6)
        # The five usage rules: CDP first for discovery, no grep first, cited ranges, help, memory.
        for rule in ("MUST use CDP for code discovery", "Do not grep first", "offset`/`limit",
                     "`cdp_help`", "memory note"):
            self.assertIn(rule, block)
        self.assertEqual([r[:2] for r in block.splitlines() if r[:1].isdigit()], ["1.", "2.", "3.", "4.", "5."])
        with mock.patch.object(install_extras, "KINDS", {**KINDS, "jobs": {"summary": "scheduled jobs and when they run"}}):
            self.assertIn("`jobs`", install_extras.claude_md_block())

    def test_a_dangling_begin_marker_is_refused_not_clobbered(self) -> None:
        path = self.target / "CLAUDE.md"
        path.write_text("keep\n" + install_extras.BEGIN + "\nhalf a block, no end\n")
        from cdp.util import CdpError
        with self.assertRaises(CdpError):
            install_extras.install_claude_md(self.target)
        self.assertIn("half a block", path.read_text())

    # --------------------------------------------------------- allow-mcp
    def test_allow_mcp_preserves_the_users_settings_and_removes_exactly_its_entry(self) -> None:
        settings = self.target / ".claude" / "settings.json"
        settings.parent.mkdir()
        original = {"model": "x", "permissions": {"deny": ["Bash(rm:*)"], "allow": ["Read", "Bash(ls:*)"]}, "env": {"A": "1"}}
        settings.write_text(json.dumps(original, indent=2) + "\n")
        out = self.install("--allow-mcp")
        self.assertIn("mcp__cdp__*", out)
        self.assertIn("without a prompt", out)  # states exactly what is granted
        got = json.loads(settings.read_text())
        self.assertEqual(got["permissions"]["allow"], ["Read", "Bash(ls:*)", "mcp__cdp__*"])
        self.assertEqual(list(got), list(original))  # key order kept
        self.install("--allow-mcp")
        self.assertEqual(json.loads(settings.read_text())["permissions"]["allow"].count("mcp__cdp__*"), 1)
        self.install("--remove-harness")
        self.assertEqual(json.loads(settings.read_text()), original)
        self.assertFalse((settings.parent / install_extras.ALLOW_STATE).exists())

    def test_a_permission_the_user_already_had_is_not_removed(self) -> None:
        settings = self.target / ".claude" / "settings.json"
        settings.parent.mkdir()
        settings.write_text(json.dumps({"permissions": {"allow": ["mcp__cdp__*"]}}))
        self.install("--allow-mcp")
        self.install("--remove-harness")
        self.assertEqual(json.loads(settings.read_text())["permissions"]["allow"], ["mcp__cdp__*"])

    def test_allow_mcp_alone_creates_then_removes_the_settings_file(self) -> None:
        self.install("--allow-mcp")
        settings = self.target / ".claude" / "settings.json"
        self.assertEqual(json.loads(settings.read_text()), {"permissions": {"allow": ["mcp__cdp__*"]}})
        self.install("--remove-harness")
        self.assertFalse(settings.exists())

    # ----------------------------------------------------------- priority
    def test_priority_is_harness_strict_claude_md_allow_mcp(self) -> None:
        self.install("--priority")
        settings = json.loads((self.target / ".claude" / "settings.json").read_text())
        pre = settings["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
        self.assertTrue(pre.endswith('hook.py" --gate'), pre)  # strict = the gate
        self.assertIn("mcp__cdp__*", settings["permissions"]["allow"])
        self.assertIn("UserPromptSubmit", settings["hooks"])
        self.assertIn("cdp", json.loads((self.target / ".mcp.json").read_text())["mcpServers"])
        self.assertIn(install_extras.END, (self.target / "CLAUDE.md").read_text())
        self.install("--remove-harness")
        for rel in (".claude/settings.json", ".mcp.json", "CLAUDE.md"):
            self.assertFalse((self.target / rel).exists(), rel)

    def test_default_harness_installs_none_of_the_extras(self) -> None:
        self.install("--harness")
        self.assertFalse((self.target / "CLAUDE.md").exists())
        self.assertNotIn("permissions", json.loads((self.target / ".claude" / "settings.json").read_text()))

    def test_remove_harness_cannot_be_combined_with_the_new_flags(self) -> None:
        for flag in ("--claude-md", "--allow-mcp", "--priority"):
            with contextlib.redirect_stderr(io.StringIO()) as err:
                self.assertNotEqual(main(["install", str(self.target), "--remove-harness", flag]), 0)
            self.assertIn("cannot be combined", err.getvalue())


if __name__ == "__main__":
    unittest.main()
