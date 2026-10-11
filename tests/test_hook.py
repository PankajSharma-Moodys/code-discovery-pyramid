"""The PreToolUse hook — `PHASE/phase_1_plan.md` M1.6.

A hook is in the path of every file read in the session, so the tests that
matter are the ones that prove it **stays quiet**. Each of the three mandatory
no-ops is asserted independently, because a single combined test passes just as
happily when two of the three conditions are unimplemented.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import SKILL_ROOT, have_git, make_repo  # noqa: F401  (sets sys.path)

from unittest import mock

from cdp import hook as hook_mod, snapshot as snapshot_mod
from cdp.cli import main
from cdp.store import SqliteStore, registry


class _OwnHome:
    """A machine home of the test's own, so the hook (which reads `CDP_HOME`,
    in-process and in a subprocess alike) sees exactly what the test scanned."""

    def make_home(self) -> None:
        self.home = Path(self.tmp.name) / "home"
        patcher = mock.patch.dict(os.environ, {"CDP_HOME": str(self.home)})
        patcher.start()
        self.addCleanup(patcher.stop)

    def open_snapshot(self, repo=None) -> SqliteStore:
        """The store, pointed at `repo`'s current snapshot, for tests that
        doctor what a scan wrote."""
        repo = repo or self.repo
        backend = SqliteStore(self.home / "index.db")
        snapshot_mod.select(backend, repo, registry.repo_identity(repo))
        return backend


def event(tool: str, path: str, repo: Path, session: str = "s1") -> dict:
    return {
        "session_id": session,
        "hook_event_name": "PreToolUse",
        "cwd": str(repo),
        "tool_name": tool,
        "tool_input": {"file_path": path} if tool == "Read" else {"path": path},
    }


@unittest.skipUnless(have_git(), "the HEAD check needs a real git repository")
class HookTest(_OwnHome, unittest.TestCase):
    """Scanned into the machine store; the hook finds the repo's rows in it."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.make_home()
        self.repo = make_repo(Path(self.tmp.name))
        main(["scan", "--repo", str(self.repo), "--quiet"])
        self.source = "core/src/main/java/COM/Example/mini/core/Widget.java"
        # Every test gets a distinct session id: the hook fires at most once per
        # session, so sharing one would make the second assertion in any test
        # pass for the wrong reason.
        self.session = self.id()

    def fire(self, tool="Read", path=None, session=None):
        return hook_mod.decide(event(tool, path or str(self.repo / self.source),
                                     self.repo, session or self.session))

    # --------------------------------------------------------------- it fires

    def test_fires_on_a_source_read(self) -> None:
        message = self.fire()
        self.assertIsNotNone(message)
        self.assertIn("cdp query", message)
        self.assertIn("query coverage", message)
        self.assertIn(self.source, message)

    def test_fires_at_most_once_per_session(self) -> None:
        self.assertIsNotNone(self.fire())
        self.assertIsNone(self.fire())

    def test_a_new_session_gets_its_own_nudge(self) -> None:
        self.assertIsNotNone(self.fire(session=self.session + "-a"))
        self.assertIsNotNone(self.fire(session=self.session + "-b"))

    def test_fires_on_grep_of_a_source_directory(self) -> None:
        """Grep and Glob name a directory or a pattern, not a file. An exact
        path match alone would make the hook fire on Read and never on the two
        tools that cost the most."""
        message = self.fire(tool="Grep", path=str(self.repo / "core"))
        self.assertIsNotNone(message)

    # ------------------------------------------------ the three mandatory no-ops

    def test_noop_when_state_is_missing(self) -> None:
        """No-op 1: nothing scanned."""
        shutil.rmtree(self.home)
        self.assertIsNone(self.fire())

    def test_noop_when_the_index_does_not_describe_the_working_tree(self) -> None:
        """No-op 2: `inventory.head != git HEAD`.

        A hook nagging about an index that does not describe the working tree is
        worse than no hook.
        """
        backend = self.open_snapshot()
        inventory = backend.read_artifact("inventory")
        inventory["head"] = "0" * 40
        backend.write_artifact("inventory", inventory)
        backend.close()
        self.assertIsNone(self.fire())

    def test_noop_after_a_commit_moves_head(self) -> None:
        """The same condition, produced the way it actually occurs."""
        env = {"GIT_AUTHOR_NAME": "cdp", "GIT_AUTHOR_EMAIL": "c@example.invalid",
               "GIT_COMMITTER_NAME": "cdp", "GIT_COMMITTER_EMAIL": "c@example.invalid",
               "PATH": "/usr/bin:/bin:/usr/local/bin", "HOME": self.tmp.name}
        (self.repo / "NOTES.md").write_text("moved\n")
        subprocess.run(["git", "-C", str(self.repo), "add", "-A"],
                       check=True, capture_output=True, env=env)
        subprocess.run(["git", "-C", str(self.repo), "-c", "commit.gpgsign=false",
                        "commit", "-q", "-m", "move HEAD"],
                       check=True, capture_output=True, env=env)
        self.assertIsNone(self.fire())

    def test_noop_when_the_scan_lives_in_another_home(self) -> None:
        """A scan written with `--state-dir` elsewhere is a different store; the
        hook reads the machine's `CDP_HOME` and does not go looking."""
        with tempfile.TemporaryDirectory() as other:
            shutil.rmtree(self.home)
            main(["scan", "--repo", str(self.repo), "--state-dir", str(Path(other) / "h"), "--quiet"])
            self.assertIsNone(self.fire())

    # ----------------------------------------------- one store, many repos

    def _commit(self, name: str) -> None:
        env = {"GIT_AUTHOR_NAME": "cdp", "GIT_AUTHOR_EMAIL": "c@example.invalid",
               "GIT_COMMITTER_NAME": "cdp", "GIT_COMMITTER_EMAIL": "c@example.invalid",
               "PATH": "/usr/bin:/bin:/usr/local/bin", "HOME": self.tmp.name}
        (self.repo / name).write_text("x\n")
        subprocess.run(["git", "-C", str(self.repo), "add", "-A"], check=True, capture_output=True, env=env)
        subprocess.run(["git", "-C", str(self.repo), "-c", "commit.gpgsign=false", "commit", "-q",
                        "-m", name], check=True, capture_output=True, env=env)

    def test_still_fires_after_the_repos_second_scan(self) -> None:
        """Bug F: the hook used to read the oldest snapshot in the file, so it
        went silent as soon as a repo had been scanned at a second commit."""
        self._commit("NOTES.md")
        main(["scan", "--repo", str(self.repo), "--quiet"])
        self.assertEqual(len(SqliteStore(self.home / "index.db").list_snapshots()), 2)
        message = self.fire()
        self.assertIsNotNone(message)
        self.assertIn(hook_mod.git_head(self.repo)[:12], message)

    def test_follows_head_back_to_an_older_scanned_commit(self) -> None:
        first = hook_mod.git_head(self.repo)
        self._commit("NOTES.md")
        main(["scan", "--repo", str(self.repo), "--quiet"])
        subprocess.run(["git", "-C", str(self.repo), "checkout", "-q", first], check=True,
                       capture_output=True)
        message = self.fire()
        self.assertIsNotNone(message)
        self.assertIn(first[:12], message)

    def test_a_second_repo_in_the_store_does_not_hijack_the_answer(self) -> None:
        other = make_repo(Path(self.tmp.name) / "other", fixture="solorepo")
        main(["scan", "--repo", str(other), "--quiet"])
        message = self.fire()
        self.assertIsNotNone(message)
        self.assertIn(hook_mod.git_head(self.repo)[:12], message)

    def test_a_scanned_subfolder_is_found_and_is_its_own_repo(self) -> None:
        shutil.rmtree(self.home)
        main(["scan", "--repo", str(self.repo / "core"), "--quiet"])
        found = hook_mod.find_state(self.repo / self.source)
        self.assertIsNotNone(found)
        self.assertEqual(found[2], (self.repo / "core").resolve())
        self.assertIn("#core", found[1])

    # ------------------------------------------------------------ role scoping

    def test_does_not_fire_on_docs(self) -> None:
        """*"Fix the typo in README.md."* — the whole false-positive class the
        peer system cannot eliminate, deleted by one role check."""
        (self.repo / "README.md").write_text("# mini\n")
        main(["scan", "--repo", str(self.repo), "--quiet"])
        self.assertIsNone(self.fire(path=str(self.repo / "README.md")))

    def test_does_not_fire_on_a_build_manifest(self) -> None:
        self.assertIsNone(self.fire(path=str(self.repo / "core" / "build.gradle")))

    def test_does_not_fire_on_an_untracked_file(self) -> None:
        self.assertIsNone(self.fire(path=str(self.repo / "not-in-the-index.java")))

    def test_does_not_fire_on_an_unwatched_tool(self) -> None:
        self.assertIsNone(hook_mod.decide(
            event("Bash", str(self.repo / self.source), self.repo, self.session)))

    # ---------------------------------------------------------- dirty worktree

    def test_a_dirty_tree_nudges_with_a_qualifier(self) -> None:
        """HEAD matches but files are edited: the index is stale in a way the
        HEAD check structurally cannot see. Recorded decision — nudge, qualified.
        """
        (self.repo / self.source).write_text("// edited\n")
        message = self.fire()
        self.assertIsNotNone(message)
        self.assertIn("working tree is dirty", message)

    def test_a_clean_tree_carries_no_qualifier(self) -> None:
        self.assertNotIn("working tree is dirty", self.fire())


@unittest.skipUnless(have_git(), "the HEAD check needs a real git repository")
class StrictModeTest(_OwnHome, unittest.TestCase):
    """Phase 9: `--strict` blocks the first source read instead of nudging,
    but only when coverage and freshness both clear the bar (the stress test
    named in `phase_9_plan.md`: coverage is not freshness, R8)."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.make_home()
        self.repo = make_repo(Path(self.tmp.name))
        main(["scan", "--repo", str(self.repo), "--quiet"])
        self.source = "core/src/main/java/COM/Example/mini/core/Widget.java"
        self.session = self.id()

    def _set_coverage(self, fraction: float) -> None:
        backend = self.open_snapshot()
        state = backend.read_artifact("state", {})
        state["coverage"]["fraction"] = fraction
        backend.write_artifact("state", state)
        backend.close()

    def fire(self, session=None):
        return hook_mod.strict_decide(
            event("Read", str(self.repo / self.source), self.repo, session or self.session))

    def test_below_threshold_degrades_to_a_nudge_not_a_block(self) -> None:
        # The fixture's own real coverage after a bare scan (no agent dispatch)
        # is well under STRICT_MIN_COVERAGE -- exercised as-is, not forced.
        result = self.fire()
        self.assertIsNotNone(result)
        self.assertFalse(result["block"])
        self.assertIn("cdp query", result["message"])

    def test_full_coverage_and_fresh_head_blocks(self) -> None:
        self._set_coverage(1.0)
        result = self.fire()
        self.assertIsNotNone(result)
        self.assertTrue(result["block"])
        self.assertIn("Blocked", result["message"])

    def test_full_coverage_but_stale_head_still_degrades_to_a_nudge(self) -> None:
        """The named stress test: 100% coverage does not license a block when
        the index no longer describes the working tree (R8, two dates)."""
        self._set_coverage(1.0)
        backend = self.open_snapshot()
        inventory = backend.read_artifact("inventory")
        inventory["head"] = "0" * 40
        backend.write_artifact("inventory", inventory)
        backend.close()
        self.assertIsNone(self.fire())

    def test_blocks_at_most_once_per_session_then_stays_silent(self) -> None:
        self._set_coverage(1.0)
        first = self.fire()
        self.assertTrue(first["block"])
        self.assertIsNone(self.fire())

    def test_strict_flag_makes_main_emit_a_deny_decision(self) -> None:
        self._set_coverage(1.0)
        proc = subprocess.run(
            [sys.executable, "-m", "cdp.hook", "--strict"],
            input=json.dumps(event("Read", str(self.repo / self.source),
                                    self.repo, "cli-session")),
            capture_output=True, text=True, cwd=str(SKILL_ROOT))
        self.assertEqual(proc.returncode, 0)
        body = json.loads(proc.stdout)
        self.assertEqual(
            body["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIn("permissionDecisionReason", body["hookSpecificOutput"])


class HookSafetyTest(unittest.TestCase):
    """It fails open, always. Breaking every file read is far worse than
    missing a nudge."""

    def test_garbage_input_is_silent(self) -> None:
        for payload in ({}, {"tool_name": "Read"}, {"tool_name": "Read", "tool_input": 3}):
            self.assertIsNone(hook_mod.decide(payload))
            self.assertIsNone(hook_mod.strict_decide(payload))

    def test_non_json_stdin_exits_zero_with_no_output(self) -> None:
        proc = subprocess.run([sys.executable, "-m", "cdp.hook"],
                              input="not json", capture_output=True, text=True,
                              cwd=str(SKILL_ROOT))
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stdout.strip(), "")

    def test_explain_describes_the_contract(self) -> None:
        proc = subprocess.run([sys.executable, "-m", "cdp.hook", "--explain"],
                              capture_output=True, text=True, cwd=str(SKILL_ROOT))
        self.assertEqual(proc.returncode, 0)
        self.assertIn("role == \"source\"", proc.stdout)
        self.assertIn("Sample nudge:", proc.stdout)

    def test_payload_reports_no_permission_decision(self) -> None:
        """A nudge must not decide permission. Exit 0 with no
        `permissionDecision` reports no decision and leaves the call to the
        normal permission flow, which is exactly what this should do."""
        body = hook_mod.payload("hello")
        self.assertNotIn("permissionDecision", body["hookSpecificOutput"])
        self.assertEqual(body["hookSpecificOutput"]["hookEventName"], "PreToolUse")
        self.assertIn("additionalContext", body["hookSpecificOutput"])
        self.assertIn("systemMessage", body)

    def test_payload_blocks_only_when_asked(self) -> None:
        body = hook_mod.payload("blocked reason", block=True)
        self.assertEqual(body["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertEqual(
            body["hookSpecificOutput"]["permissionDecisionReason"], "blocked reason")
        self.assertNotIn("additionalContext", body["hookSpecificOutput"])


class InstallHookTest(unittest.TestCase):
    def setUp(self) -> None:
        import contextlib
        import io

        # `install` is chatty by design; the assertions here are about the file
        # it writes, and the one test that reads the output captures it itself.
        self._quiet = contextlib.redirect_stdout(io.StringIO())
        self._quiet.__enter__()
        self.addCleanup(lambda: self._quiet.__exit__(None, None, None))

    def test_install_writes_an_idempotent_settings_entry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "target"
            target.mkdir()
            main(["install", str(target), "--hook"])
            main(["install", str(target), "--hook"])
            settings = json.loads(
                (target / ".claude" / "settings.json").read_text(encoding="utf-8"))
            groups = settings["hooks"]["PreToolUse"]
            self.assertEqual(len(groups), 1)
            self.assertEqual(groups[0]["matcher"], "Read|Grep|Glob|Bash")
            self.assertEqual(len(groups[0]["hooks"]), 1, "duplicated on re-install")

    def test_reinstall_replaces_an_older_wider_matcher(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "target"
            (target / ".claude").mkdir(parents=True)
            old = {"hooks": {"PreToolUse": [{"matcher": "Read|Grep", "hooks": [
                {"type": "command", "args": [], "command":
                 "python3 %s" % (target.resolve() / ".claude/skills/cdp/cdp/hook.py")}]}]}}
            (target / ".claude" / "settings.json").write_text(json.dumps(old))
            main(["install", str(target), "--hook"])
            groups = json.loads((target / ".claude" / "settings.json").read_text())["hooks"]["PreToolUse"]
            self.assertEqual([g["matcher"] for g in groups], ["Read|Grep|Glob|Bash"])
            self.assertEqual(len(groups[0]["hooks"]), 1)
            self.assertNotIn("args", groups[0]["hooks"][0])

    def test_install_strict_writes_the_flag_and_reinstall_updates_it(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "target"
            target.mkdir()
            main(["install", str(target), "--hook", "--strict"])
            settings = json.loads(
                (target / ".claude" / "settings.json").read_text(encoding="utf-8"))
            handlers = settings["hooks"]["PreToolUse"][0]["hooks"]
            self.assertEqual(len(handlers), 1)
            self.assertTrue(handlers[0]["command"].endswith('hook.py" --strict'))
            self.assertNotIn("args", handlers[0])

            # Re-installing without --strict updates the existing entry in
            # place rather than leaving the old choice or stacking a duplicate.
            main(["install", str(target), "--hook"])
            settings = json.loads(
                (target / ".claude" / "settings.json").read_text(encoding="utf-8"))
            handlers = settings["hooks"]["PreToolUse"][0]["hooks"]
            self.assertEqual(len(handlers), 1)
            self.assertTrue(handlers[0]["command"].endswith('hook.py"'))

    def test_install_states_no_scan_yet_without_requiring_in_repo(self) -> None:
        # M2.6: the hook is no longer `--in-repo` only (`store.registry`
        # dissolves the constraint), but installing against a repo that has
        # never been scanned must still say so rather than silently no-op.
        import contextlib
        import io

        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "target"
            target.mkdir()
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                main(["install", str(target), "--hook"])
            out = buf.getvalue()
            self.assertIn("no scan of", out)
            self.assertIn("no-op", out)
            self.assertNotIn("--in-repo", out)

    def test_install_preserves_existing_settings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "target"
            (target / ".claude").mkdir(parents=True)
            (target / ".claude" / "settings.json").write_text(
                json.dumps({"model": "opus", "hooks": {"PostToolUse": []}}))
            main(["install", str(target), "--hook"])
            settings = json.loads(
                (target / ".claude" / "settings.json").read_text(encoding="utf-8"))
            self.assertEqual(settings["model"], "opus")
            self.assertIn("PostToolUse", settings["hooks"])
            self.assertIn("PreToolUse", settings["hooks"])


if __name__ == "__main__":
    unittest.main()


class SessionStartAndScriptEntryTest(unittest.TestCase):
    """Run the way install registers it: `python3 .../cdp/hook.py`."""

    HOOK = Path(__file__).resolve().parent.parent / "cdp" / "hook.py"

    def _run(self, *args, stdin="{}"):
        import subprocess, sys, tempfile
        with tempfile.TemporaryDirectory() as home:
            env = dict(os.environ, CDP_HOME=home)
            return subprocess.run([sys.executable, str(self.HOOK), *args], input=stdin,
                                  capture_output=True, text=True, env=env, timeout=60)

    def test_script_entry_imports_the_package(self) -> None:
        result = self._run("--explain")
        self.assertEqual(result.returncode, 0)
        self.assertIn("Sample nudge", result.stdout)

    def test_session_start_is_silent_for_an_unscanned_repo(self) -> None:
        result = self._run("--session-start", stdin='{"cwd": "/tmp"}')
        self.assertEqual((result.returncode, result.stdout), (0, ""))


@unittest.skipUnless(have_git(), "needs a real git repository")
class SessionStartFromSubfolderTest(_OwnHome, unittest.TestCase):
    """A session launched in `repo/sub` must still get the status line: the scan
    is registered under the repo root, and refresh/status must be told that."""

    def test_status_line_from_a_subfolder_of_the_scanned_repo(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.make_home()
        repo = make_repo(Path(self.tmp.name))
        main(["scan", "--repo", str(repo), "--quiet"])
        message = hook_mod.session_start({"cwd": str(repo / "core")})
        self.assertIsNotNone(message)
        self.assertIn("CDP index for this repo is ready", message)
        self.assertNotIn("could not be read", message)


@unittest.skipUnless(have_git(), "needs a real git repository")
class PromptSubmitTest(_OwnHome, unittest.TestCase):
    def test_once_per_session_and_silent_without_a_scan(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.make_home()
        repo = make_repo(Path(self.tmp.name))
        ev = {"cwd": str(repo), "session_id": self.id()}
        self.assertIsNone(hook_mod.prompt_submit(ev))  # not scanned yet
        main(["scan", "--repo", str(repo), "--quiet"])
        self.assertIn("cdp_query", hook_mod.prompt_submit(ev))
        self.assertIsNone(hook_mod.prompt_submit(ev))


@unittest.skipUnless(have_git(), "needs a real git repository")
class GateTest(_OwnHome, unittest.TestCase):
    """`--gate`: a search or read the index can answer is answered, not run."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.make_home()
        self.repo = make_repo(Path(self.tmp.name), "reservrepo")
        main(["scan", "--repo", str(self.repo), "--quiet"])
        self.service = str(self.repo / "src/main/java/com/acme/res/ReservationService.java")

    def ev(self, tool, session, **tool_input):
        return {"session_id": self.id() + session, "cwd": str(self.repo),
                "tool_name": tool, "tool_input": tool_input}

    def bash(self, command, session="a"):
        return hook_mod.gate_decide(self.ev("Bash", session, command=command))

    def test_recursive_grep_of_a_known_name_is_answered_with_its_callers(self) -> None:
        result = self.bash('grep -rn "processPendingReservations" --include=*.java . | head')
        self.assertTrue(result["block"])
        self.assertIn("ProcessPendingJob.java", result["message"])
        self.assertIn("ReservationService.java:", result["message"])

    def test_the_retry_runs(self) -> None:
        self.assertIsNotNone(self.bash("grep -rn processPendingReservations ."))
        self.assertIsNone(self.bash("grep -rn processPendingReservations ."))

    def test_calls_the_index_cannot_improve_on_run(self) -> None:
        for command in ("grep -rIl -i reservations .",                      # plain word
                        "grep -rn NoSuchSymbolAnywhere .",                   # unknown to the index
                        "grep -n validateMakeReservation ReservationService.java",  # one file
                        "cat x | grep processPendingReservations",           # piped, not a repo search
                        "git status", "ls src"):
            self.assertIsNone(self.bash(command, session=command), command)

    def test_find_by_name_is_answered_with_the_path(self) -> None:
        result = self.bash("find . -name 'ReservationService*.java'")
        self.assertIn("ReservationService.java", result["message"])
        # an exclusion narrows the search the index answers whole: it runs as written
        self.assertIsNone(self.bash("find . -name 'ReservationService*.java' -not -path '*/build/*'", "x"))

    def test_grep_tool_without_a_path_is_covered(self) -> None:
        result = hook_mod.gate_decide(self.ev("Grep", "g", pattern="createReservationCredentials"))
        self.assertIn("PostgresServerHelper", result["message"])
        self.assertIn("MssqlServerHelper", result["message"])

    def test_whole_file_read_gets_the_outline_once(self) -> None:
        from unittest import mock
        with mock.patch.object(hook_mod, "READ_MIN_LOC", 5):
            first = hook_mod.gate_decide(self.ev("Read", "r", file_path=self.service))
            self.assertTrue(first["block"])
            self.assertIn("ReservationService#validateMakeReservation", first["message"])
            self.assertIn("private", first["message"])
            self.assertIn("L15-24", first["message"])  # makeReservations, start-end
            self.assertIsNone(hook_mod.gate_decide(self.ev("Read", "r", file_path=self.service)))

    def test_ranged_and_short_reads_run(self) -> None:
        from unittest import mock
        with mock.patch.object(hook_mod, "READ_MIN_LOC", 5):
            self.assertIsNone(hook_mod.gate_decide(
                self.ev("Read", "r2", file_path=self.service, offset=10, limit=20)))
        self.assertIsNone(hook_mod.gate_decide(self.ev("Read", "r3", file_path=self.service)))

    def test_silent_without_a_fresh_index(self) -> None:
        shutil.rmtree(self.home)
        self.assertIsNone(self.bash("grep -rn processPendingReservations .", session="z"))

    def test_harness_installs_the_nudge_by_default_and_the_gate_with_strict(self) -> None:
        target = Path(self.tmp.name) / "target"
        target.mkdir()
        main(["install", str(target), "--harness"])
        settings = json.loads((target / ".claude" / "settings.json").read_text())
        pre = settings["hooks"]["PreToolUse"]
        self.assertEqual(len(pre), 1)
        command = pre[0]["hooks"][0]["command"]
        self.assertTrue(command.endswith('hook.py"'), command)   # nudge: no --gate / --strict
        self.assertNotIn("$HOME", command)
        self.assertIn("$CLAUDE_PROJECT_DIR", command)
        self.assertFalse((target / "AGENTS.md").exists())
        main(["install", str(target), "--harness", "--strict"])
        settings = json.loads((target / ".claude" / "settings.json").read_text())
        pre = settings["hooks"]["PreToolUse"]
        self.assertEqual(len(pre), 1)
        self.assertTrue(pre[0]["hooks"][0]["command"].endswith('hook.py" --gate'))
        self.assertIn("mcp__.*cdp_query", pre[0]["matcher"])
        main(["install", str(target), "--harness"])       # back to the nudge: no stale gate
        settings = json.loads((target / ".claude" / "settings.json").read_text())
        self.assertEqual([h["command"].endswith('hook.py"') for g in settings["hooks"]["PreToolUse"]
                          for h in g["hooks"]], [True])


class ShellSearchParsingTest(unittest.TestCase):
    """The commands Claude actually ran against the real repo."""

    def terms(self, command):
        from cdp import hook_rules
        return [(s["kind"], s["terms"]) for s in hook_rules.shell_searches(command)]

    def test_commands_from_real_sessions(self) -> None:
        self.assertEqual(self.terms("grep -rIl --include=*.java -i \"reservations\" . | grep -v /build/ | head -40"), [])
        self.assertEqual(self.terms("grep -rn 'processPendingReservations\\|createReservationCredentials' --include='*.java' . | head"),
                         [("grep", ["processPendingReservations", "createReservationCredentials"])])
        self.assertEqual(self.terms("cd sql-pool && grep -rnE \"validateMakeReservation|checkIdempotency\" ."),
                         [("grep", ["validateMakeReservation", "checkIdempotency"])])
        self.assertEqual(self.terms("find . -name 'ReservationService*.java' -not -path '*/build/*' | head"),
                         [("find", ["ReservationService"])])

    def test_targeted_or_piped_greps_are_not_repo_searches(self) -> None:
        self.assertEqual(self.terms("grep -n FooBarBaz src/main/Foo.java"), [])
        self.assertEqual(self.terms("grep -rn FooBarBaz src/main/Foo.java"), [])
        self.assertEqual(self.terms("cat x | grep FooBarBaz"), [])
        self.assertEqual(self.terms("echo 'unterminated"), [])

    def test_ripgrep_is_recursive_by_default(self) -> None:
        self.assertEqual(self.terms("rg ReservationService"), [("grep", ["ReservationService"])])
        self.assertEqual(self.terms("rg ReservationService src/File.java"), [])


class LeafSessionTest(unittest.TestCase):
    """A leaf session (`CDP_LEAF_SESSION` set) is never gated, nudged or briefed."""

    def test_every_hook_mode_stands_down(self) -> None:
        hook = Path(__file__).resolve().parent.parent / "cdp" / "hook.py"
        env = dict(os.environ, CDP_LEAF_SESSION="1")
        for flag in ("--gate", "--session-start", "--prompt-submit", ""):
            result = subprocess.run(
                [sys.executable, str(hook)] + ([flag] if flag else []),
                input='{"tool_name": "Bash", "tool_input": {"command": "grep -rn FooBarBaz ."}, "cwd": "/tmp"}',
                capture_output=True, text=True, env=env, timeout=60)
            self.assertEqual((result.returncode, result.stdout), (0, ""), flag)
