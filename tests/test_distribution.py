"""The vendored skill copy is generated, and this proves it.

`.claude/skills/cdp/` is the form CDP ships in — one directory, no install step.
It is also, now that the product lives at the repository root, a *copy*. A copy
that can be hand-edited is a second source of truth, and the drift is silent:
the edit works for whoever made it, because the skill is what their harness
loads, and is invisible to everyone running from the root.

So the copy is asserted byte-identical to its source. Editing the vendored tree
fails this test with the differing paths named; `cdp install --self` is the only
supported way to change it.
"""

from __future__ import annotations

import contextlib
import filecmp
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import SKILL_ROOT, make_repo  # noqa: F401  (sets sys.path)

from cdp.cli import main
from cdp.install import DIST_IGNORE, DIST_MEMBERS, TARGET_MEMBERS

VENDORED = SKILL_ROOT / ".claude" / "skills" / "cdp"


def _members(directory: Path) -> set:
    """Names in `directory`, minus anything `install` would not have copied."""
    names = {p.name for p in directory.iterdir()}
    return names - set(DIST_IGNORE(str(directory), sorted(names)))


def _compare(left: Path, right: Path, rel: str, differing: list, missing: list) -> None:
    """Recursively compare two trees, accumulating differences rather than
    stopping at the first — a drift report naming one file when six drifted
    sends the reader back round the loop five more times."""
    left_names, right_names = _members(left), _members(right)
    for name in sorted(left_names - right_names):
        missing.append("%s%s (absent from vendored copy)" % (rel, name))
    for name in sorted(right_names - left_names):
        missing.append("%s%s (present in vendored copy, not in source)" % (rel, name))
    for name in sorted(left_names & right_names):
        lp, rp = left / name, right / name
        if lp.is_dir() != rp.is_dir():
            differing.append("%s%s (file/directory mismatch)" % (rel, name))
        elif lp.is_dir():
            _compare(lp, rp, "%s%s/" % (rel, name), differing, missing)
        elif not filecmp.cmp(lp, rp, shallow=False):
            differing.append("%s%s" % (rel, name))


class VendoredCopyTest(unittest.TestCase):
    def test_vendored_copy_exists(self) -> None:
        self.assertTrue(
            VENDORED.is_dir(),
            "no vendored skill at %s — run `cdp install --self`" % VENDORED,
        )

    def test_vendored_copy_is_byte_identical(self) -> None:
        if not VENDORED.is_dir():
            self.skipTest("no vendored copy; covered by test_vendored_copy_exists")
        differing: list = []
        missing: list = []
        for member in DIST_MEMBERS:
            src, dst = SKILL_ROOT / member, VENDORED / member
            if not dst.exists():
                missing.append("%s (absent from vendored copy)" % member)
                continue
            if src.is_dir():
                _compare(src, dst, "%s/" % member, differing, missing)
            elif not filecmp.cmp(src, dst, shallow=False):
                differing.append(member)
        if differing or missing:
            self.fail(
                "vendored copy has drifted from the source tree.\n"
                "  differing: %s\n  structural: %s\n"
                "Do not edit .claude/skills/cdp/ by hand; run `cdp install --self`."
                % (differing or "none", missing or "none")
            )

    def test_distribution_excludes_the_repository(self) -> None:
        """The allow-list must not vendor the repo into every target.

        Before the move to the root, `install` was a `copytree` of the whole
        skill directory with an ignore list. At the root that same shape would
        ship `.git/`, `.venv/` and the design documents.
        """
        if not VENDORED.is_dir():
            self.skipTest("no vendored copy")
        self.assertEqual(_members(VENDORED), set(DIST_MEMBERS))
        for forbidden in (".git", ".venv", "PHASE", "RESEARCH_GRAPHIFY.md",
                          "CDP_CLI_SCOPE.md", "ARCHITECTURE.md", "pyproject.toml"):
            self.assertFalse(
                (VENDORED / forbidden).exists(),
                "%s was vendored into the skill copy" % forbidden,
            )


class TargetInstallTest(unittest.TestCase):
    """An install into *another* repository is the runtime skill only. This repository's own
    vendored copy keeps `tests/` (`DIST_MEMBERS`, byte-identical above); a target never gets
    them: their fixtures are Java/SQL/Python/C# sources that doubled every `grep -r` there."""

    BUDGET_BYTES = 1_600_000  # tests/fixtures alone are ~2 MB, so leaking them still fails

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.target = make_repo(Path(self.tmp.name))
        with contextlib.redirect_stdout(io.StringIO()):
            main(["install", str(self.target), "--harness"])
        self.skill = self.target / ".claude" / "skills" / "cdp"
        self.env = dict(os.environ, CDP_HOME=str(Path(self.tmp.name) / "home"))
        self.env.pop("PYTHONPATH", None)

    def files(self) -> list:
        return [p for p in self.skill.rglob("*") if p.is_file()]

    def test_members_are_the_runtime_set(self) -> None:
        self.assertNotIn("tests", TARGET_MEMBERS)
        self.assertEqual(set(TARGET_MEMBERS), set(DIST_MEMBERS) - {"tests"})
        self.assertEqual({p.name for p in self.skill.iterdir()}, set(TARGET_MEMBERS))

    def test_self_distribution_still_carries_the_tests(self) -> None:
        from cdp.install import copy_distribution

        dest = Path(self.tmp.name) / "selfcopy"
        copy_distribution(dest)
        self.assertEqual({p.name for p in dest.iterdir()}, set(DIST_MEMBERS))
        self.assertTrue((dest / "tests" / "fixtures").is_dir())

    def test_no_tests_or_fixtures_and_under_the_size_budget(self) -> None:
        rels = [p.relative_to(self.skill).as_posix() for p in self.files()]
        self.assertEqual([r for r in rels if "tests/" in r or "fixtures" in r or r.startswith("tests")], [])
        size = sum(p.stat().st_size for p in self.files())
        self.assertLess(size, self.BUDGET_BYTES, "install copied %d bytes into the target" % size)

    def test_installed_copy_runs_scan_query_help_and_mcp(self) -> None:
        run = [sys.executable, str(self.skill / "run.py")]

        def cdp(*argv: str) -> subprocess.CompletedProcess:
            return subprocess.run(run + list(argv), capture_output=True, text=True, env=self.env,
                                  cwd=str(self.target))

        scan = cdp("scan", "--repo", str(self.target), "--quiet")
        self.assertEqual(scan.returncode, 0, scan.stderr)
        stats = cdp("query", "stats", "--repo", str(self.target))
        self.assertEqual(stats.returncode, 0, stats.stderr)
        self.assertIn("symbols", stats.stdout)
        self.assertEqual(cdp("help").returncode, 0)
        selftest = cdp("selftest")  # repo-only: says so instead of running nothing
        self.assertNotEqual(selftest.returncode, 0)
        self.assertIn("no tests bundled", selftest.stderr)
        mcp = subprocess.run(
            [sys.executable, "-m", "mcp_server.server"], capture_output=True, text=True, cwd=str(self.target),
            env=dict(self.env, PYTHONPATH=str(self.skill)), timeout=60,
            input=json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                              "params": {"protocolVersion": "2025-06-18"}}) + "\n")
        self.assertEqual(json.loads(mcp.stdout.splitlines()[0])["result"]["serverInfo"]["name"], "cdp")

    def test_installed_hook_runs(self) -> None:
        proc = subprocess.run([sys.executable, str(self.skill / "cdp" / "hook.py"), "--explain"],
                              capture_output=True, text=True, env=self.env, cwd=str(self.target))
        self.assertEqual(proc.returncode, 0, proc.stderr)


class AgentsMdInstallTest(unittest.TestCase):
    """Tier-0 (RESEARCH_GRAPHIFY.md §7.9): a root AGENTS.md for hook-less
    assistants — Cursor, Codex, Copilot, Aider — none of which read
    `.claude/skills/cdp/`."""

    def setUp(self) -> None:
        self._quiet = contextlib.redirect_stdout(io.StringIO())
        self._quiet.__enter__()
        self.addCleanup(lambda: self._quiet.__exit__(None, None, None))

    def test_install_writes_agents_md_at_the_target_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "target"
            target.mkdir()
            main(["install", str(target), "--agents-md"])
            agents_md = target / "AGENTS.md"
            self.assertTrue(agents_md.is_dir() is False and agents_md.exists())
            text = agents_md.read_text(encoding="utf-8")
            self.assertIn("scan --repo", text)
            self.assertIn("query stats", text)
            self.assertIn("query symbol X", text)

    def test_install_does_not_write_agents_md_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "target"
            target.mkdir()
            main(["install", str(target)])
            self.assertFalse((target / "AGENTS.md").exists())

    def test_install_never_overwrites_an_existing_agents_md(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "target"
            target.mkdir()
            (target / "AGENTS.md").write_text("operator's own file\n", encoding="utf-8")
            main(["install", str(target), "--agents-md"])
            self.assertEqual(
                (target / "AGENTS.md").read_text(encoding="utf-8"),
                "operator's own file\n",
            )


if __name__ == "__main__":
    unittest.main()
