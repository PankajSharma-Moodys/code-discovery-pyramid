"""The PreToolUse hook — `PHASE/phase_1_plan.md` M1.6.

A hook is in the path of every file read in the session, so the tests that
matter are the ones that prove it **stays quiet**. Each of the three mandatory
no-ops is asserted independently, because a single combined test passes just as
happily when two of the three conditions are unimplemented.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import SKILL_ROOT, have_git, make_repo  # noqa: F401  (sets sys.path)

from cdp import hook as hook_mod
from cdp.cli import main


def event(tool: str, path: str, repo: Path, session: str = "s1") -> dict:
    return {
        "session_id": session,
        "hook_event_name": "PreToolUse",
        "cwd": str(repo),
        "tool_name": tool,
        "tool_input": {"file_path": path} if tool == "Read" else {"path": path},
    }


@unittest.skipUnless(have_git(), "the HEAD check needs a real git repository")
class HookTest(unittest.TestCase):
    """An in-repo install, which is the only configuration the hook supports."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = make_repo(Path(self.tmp.name))
        main(["scan", "--repo", str(self.repo), "--in-repo", "--quiet"])
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
        """No-op 1: `.cdp/` missing."""
        import shutil

        shutil.rmtree(self.repo / ".cdp")
        self.assertIsNone(self.fire())

    def test_noop_when_the_index_does_not_describe_the_working_tree(self) -> None:
        """No-op 2: `inventory.head != git HEAD`.

        A hook nagging about an index that does not describe the working tree is
        worse than no hook.
        """
        inventory_path = self.repo / ".cdp" / "inventory.json"
        inventory = json.loads(inventory_path.read_text())
        inventory["head"] = "0" * 40
        inventory_path.write_text(json.dumps(inventory))
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

    def test_noop_when_state_is_not_resolvable_from_the_repo(self) -> None:
        """No-op 3: an out-of-repo state directory is invisible to the hook.

        This is why the milestone is `--in-repo` only, and why
        `cdp install --hook` says so rather than installing a hook that no-ops
        on every invocation — which looks identical, from outside, to a hook
        that is working and finding nothing worth saying.
        """
        with tempfile.TemporaryDirectory() as other:
            elsewhere = Path(other) / "clean"
            elsewhere.mkdir()
            main(["scan", "--repo", str(self.repo), "--state-dir",
                  str(elsewhere / ".cdp"), "--quiet"])
            import shutil

            shutil.rmtree(self.repo / ".cdp")
            self.assertIsNone(self.fire())

    # ------------------------------------------------------------ role scoping

    def test_does_not_fire_on_docs(self) -> None:
        """*"Fix the typo in README.md."* — the whole false-positive class the
        peer system cannot eliminate, deleted by one role check."""
        (self.repo / "README.md").write_text("# mini\n")
        main(["scan", "--repo", str(self.repo), "--in-repo", "--quiet"])
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


class HookSafetyTest(unittest.TestCase):
    """It fails open, always. Breaking every file read is far worse than
    missing a nudge."""

    def test_garbage_input_is_silent(self) -> None:
        for payload in ({}, {"tool_name": "Read"}, {"tool_name": "Read", "tool_input": 3}):
            self.assertIsNone(hook_mod.decide(payload))

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
            self.assertEqual(groups[0]["matcher"], "Read|Grep|Glob")
            self.assertEqual(len(groups[0]["hooks"]), 1, "duplicated on re-install")

    def test_install_states_the_in_repo_constraint(self) -> None:
        import contextlib
        import io

        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "target"
            target.mkdir()
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                main(["install", str(target), "--hook"])
            out = buf.getvalue()
            self.assertIn("--in-repo", out)
            self.assertIn("no-op", out)

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
