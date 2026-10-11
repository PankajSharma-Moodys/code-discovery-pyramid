"""Review fixes for the Claude harness: the gate stands down on edited files and on searches
the index does not cover; write redirects and silent greps are not misread; install touches
only what it wrote; route_path relativises same-repo absolute paths."""

from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from helpers import have_git, make_repo

from cdp import hook_rules, install as install_mod
from cdp import hook as hook_mod
from cdp.cli import main
from cdp.session import Paths, route_path
from cdp.util import CdpError
from test_hook_gate import _Indexed

ROOT = Path(__file__).resolve().parent.parent
PKG = "src/main/java/com/acme/res/"


def _git(repo: Path, *args: str) -> None:
    env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@e.invalid",
               GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@e.invalid")
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, env=env)


def _big(name: str, members: int = 40) -> str:
    body = "".join("    void m%d() {\n        int a = %d;\n        a++;\n        a--;\n        a += 2;\n"
                   "        a -= 2;\n        a *= 1;\n        a /= 1;\n    }\n" % (i, i) for i in range(members))
    return "package com.acme.res;\n\nclass %s {\n%s}\n" % (name, body)


@unittest.skipUnless(have_git(), "needs a real git repository")
class DirtyTreeGateTest(_Indexed, unittest.TestCase):
    GREP = "grep -rn processPendingReservations ."

    def setUp(self) -> None:
        super().setUp()
        for name in ("Big", "Big2"):
            (self.repo / PKG / (name + ".java")).write_text(_big(name))
        res = self.repo / "src/main/resources"
        res.mkdir(parents=True)
        (res / "application.properties").write_text("a=ServerService\n")
        _git(self.repo, "add", "-A")
        _git(self.repo, "commit", "-m", "big")
        main(["scan", "--repo", str(self.repo), "--quiet"])

    def read(self, name: str, session: str):
        return hook_mod.gate_decide(self.ev("Read", session, file_path=str(self.repo / PKG / name)))

    def edit(self, name: str) -> None:
        path = self.repo / PKG / name
        path.write_text(path.read_text().replace("class %s {\n" % name[:-5],
                                                 "class %s {\n%s" % (name[:-5], "    // x\n" * 30)))

    def test_a_clean_tree_is_denied_with_the_outline(self) -> None:
        self.assertIn("Not read yet", self.read("Big.java", "c")["message"])

    def test_read_of_an_edited_file_is_not_denied_with_a_stale_outline(self) -> None:
        self.edit("Big.java")
        self.assertIsNone(self.read("Big.java", "r1"))
        self.assertIn("Not read yet", self.read("Big2.java", "r2")["message"])  # untouched file: still gated

    def test_a_search_over_a_tree_with_edited_source_runs(self) -> None:
        self.assertIsNotNone(self.bash(self.GREP, "s0"))
        self.edit("Big.java")
        self.assertIsNone(self.bash(self.GREP, "s1"))
        self.assertIsNone(hook_mod.gate_decide(self.ev("Grep", "s2", pattern="processPendingReservations")))

    def test_an_edit_that_is_in_the_index_does_not_stand_the_gate_down(self) -> None:
        self.edit("Big.java")
        main(["scan", "--repo", str(self.repo), "--quiet"])  # indexes the working tree as is
        self.assertIn("Not read yet", self.read("Big.java", "e1")["message"])
        self.assertIsNotNone(self.bash(self.GREP, "e2"))


@unittest.skipUnless(have_git(), "needs a real git repository")
class SearchPathGateTest(_Indexed, unittest.TestCase):
    TERM = "processPendingReservations"

    def setUp(self) -> None:
        super().setUp()
        res = self.repo / "src/main/resources"
        res.mkdir(parents=True)
        (res / "application.properties").write_text("a=1\n")
        _git(self.repo, "add", "-A")
        _git(self.repo, "commit", "-m", "res")
        main(["scan", "--repo", str(self.repo), "--quiet"])

    def test_searches_outside_the_repo_or_source_run(self) -> None:
        for i, command in enumerate((
                "grep -rn %s /var/log" % self.TERM,
                "grep -rn %s src/main/resources" % self.TERM,
                "grep -rn %s %s/../elsewhere" % (self.TERM, self.repo),
                "grep -rn --exclude-dir=test %s ." % self.TERM,
                "grep -rn --exclude-dir test %s ." % self.TERM,
                "grep -rn --exclude=*Test.java %s ." % self.TERM,
                "rg -g '!test' %s" % self.TERM,
                "find / -name ReservationService.java",
                'find . -not -path "*/test/*" -name ReservationService.java',
                'find . ! -path "*/test/*" -name ReservationService.java',
                "find . -path ./test -prune -o -name ReservationService.java -print")):
            self.assertIsNone(self.bash(command, "p%d" % i), command)

    def test_searches_of_source_inside_the_repo_are_still_answered(self) -> None:
        for i, command in enumerate(("grep -rn %s src/main/java" % self.TERM,
                                     "grep -rn %s %s/src" % (self.TERM, self.repo),
                                     "grep -rn %s ." % self.TERM,
                                     "find src -name ReservationService.java")):
            self.assertIsNotNone(self.bash(command, "ok%d" % i), command)

    def test_redirects_that_write_a_file_are_never_denied(self) -> None:
        for i, command in enumerate(("grep -rn %s . &> out.txt" % self.TERM,
                                     "grep -rn %s .>/tmp/cdp-out" % self.TERM,
                                     "grep -rn %s . | sort -o out.txt" % self.TERM)):
            self.assertIsNone(self.bash(command, "w%d" % i), command)
        self.assertIsNotNone(self.bash("grep -rn %s . 2>/dev/null | sort | head" % self.TERM, "w9"))


class PureSearchTest(unittest.TestCase):
    def test_write_redirects_and_sort_output(self) -> None:
        for command in ("grep -rn Foo . &> f", "grep -rn FooBar .>/tmp/out", "grep -rn FooBar . >f",
                        "grep -rn FooBar . | sort -o f", "grep -rn FooBar . | sort -uo f",
                        "grep -rn FooBar . | sort --output=f", "grep -rn FooBar . | uniq a b",
                        "grep -rn FooBar . >>f", "grep -rn FooBar . 2>f"):
            self.assertFalse(hook_rules.is_pure_search(command), command)
        for command in ("grep -rn FooBar . 2>&1 | head", "grep -rn 'a>b' .", "grep -rn FooBar . 2>/dev/null",
                        "grep -rn FooBar . | sort -u", "grep -rn FooBar . &>/dev/null"):
            self.assertTrue(hook_rules.is_pure_search(command), command)


class EmptyResultTest(unittest.TestCase):
    NOMATCH = {"stdout": "", "stderr": "", "returnCodeInterpretation": "No matches found"}

    def test_empty_is_nothing_found_only_when_the_harness_says_so(self) -> None:
        grep = {"command": "grep -rn FooBar ."}
        self.assertTrue(hook_rules.is_empty_result("Bash", self.NOMATCH, grep))
        self.assertFalse(hook_rules.is_empty_result("Bash", {"stdout": "", "stderr": ""}, grep))
        self.assertFalse(hook_rules.is_empty_result("Bash", {"stdout": "", "stderr": "",
                                                              "returnCodeInterpretation": ""}, grep))

    def test_silent_by_design_commands_are_not_empty_results(self) -> None:
        for command in ("grep -q FooBar src/A.java", "grep -rqn FooBar .", "grep --quiet FooBar a",
                        "grep -rn FooBar . > out.txt", "grep -rn FooBar . >/dev/null",
                        "grep -rn FooBar . &> out.txt"):
            self.assertFalse(hook_rules.is_empty_result("Bash", self.NOMATCH, {"command": command}), command)
        self.assertTrue(hook_rules.is_empty_result("Bash", self.NOMATCH, {"command": "grep -rn FooBar . 2>/dev/null"}))


class RoutePathTest(unittest.TestCase):
    @unittest.skipUnless(have_git(), "needs a real git repository")
    def test_an_absolute_path_inside_the_same_repo_is_relativised(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            with mock.patch.dict(os.environ, {"CDP_HOME": str(home)}):
                repo = make_repo(Path(tmp), "reservrepo")
                with contextlib.redirect_stdout(io.StringIO()):
                    main(["scan", "--repo", str(repo), "--quiet"])
                paths = Paths(repo.resolve(), home)
                rel = PKG + "ReservationService.java"
                self.assertEqual(route_path(paths, str(repo / rel))[1], rel)
                self.assertEqual(route_path(paths, rel)[1], rel)
                self.assertEqual(route_path(paths, str(repo))[1], ".")


class InstallPreservesUserSettingsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.target = Path(self.tmp.name)
        self.dest = self.target / ".claude" / "skills" / "cdp"
        self.settings = self.target / ".claude" / "settings.json"
        self.settings.parent.mkdir(parents=True)

    def write(self, text: str) -> None:
        self.settings.write_text(text)

    def test_remove_keeps_user_empty_lists_groups_and_key_order(self) -> None:
        original = ('{\n  "zeta": 1,\n  "hooks": {\n    "Stop": [],\n    "PreToolUse": [{"matcher": "X", "hooks": []}],\n'
                    '    "Alpha": [{"hooks": [{"type": "command", "command": "mine"}]}]\n  },\n  "alpha": 2\n}\n')
        self.write(original)
        with contextlib.redirect_stdout(io.StringIO()):
            install_mod.install_hook(self.target, self.dest)
            install_mod.install_session_hook(self.target, self.dest)
        installed = json.loads(self.settings.read_text())
        self.assertEqual(list(installed), ["zeta", "hooks", "alpha"])  # not re-sorted
        self.assertEqual(list(installed["hooks"])[:3], ["Stop", "PreToolUse", "Alpha"])
        install_mod.remove_harness(self.target)
        self.assertEqual(json.loads(self.settings.read_text()), json.loads(original))

    def test_malformed_shapes_raise_cdp_error_and_change_nothing(self) -> None:
        for text in ('{"hooks": []}', '{"hooks": {"PreToolUse": {}}}', '{"hooks": {"SessionStart": "x"}}',
                     '{"hooks": 5}'):
            self.write(text)
            for call in (lambda: install_mod.install_hook(self.target, self.dest),
                         lambda: install_mod.install_gate_hook(self.target, self.dest),
                         lambda: install_mod.install_session_hook(self.target, self.dest)):
                with self.assertRaises(CdpError, msg=text):
                    call()
            self.assertEqual(self.settings.read_text(), text)
        (self.target / ".mcp.json").write_text('{"mcpServers": []}')
        with self.assertRaises(CdpError):
            install_mod.install_mcp(self.target, self.dest)

    def test_full_install_refuses_malformed_before_copying(self) -> None:
        self.write('{"hooks": {"PreToolUse": 3}}')
        with self.assertRaises(CdpError):
            install_mod.install(self.target, harness=True)
        self.assertFalse(self.dest.exists())


class GenGuideCliTest(unittest.TestCase):
    def run_script(self, *args: str):
        return subprocess.run([sys.executable, str(ROOT / "scripts" / "gen_guide.py"), *args],
                              capture_output=True, text=True)

    def test_unknown_flag_errors_without_writing(self) -> None:
        before = (ROOT / "SKILL.md").read_bytes()
        proc = self.run_script("--chek")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("unrecognized", proc.stderr)
        self.assertEqual((ROOT / "SKILL.md").read_bytes(), before)

    def test_help_and_check_work(self) -> None:
        self.assertEqual(self.run_script("--help").returncode, 0)
        self.assertIn(self.run_script("--check").returncode, (0, 1))


if __name__ == "__main__":
    unittest.main()
