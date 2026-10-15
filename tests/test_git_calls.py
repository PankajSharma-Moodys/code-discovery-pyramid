"""A query asks git where the repo root is once, not once per helper that needs it (it asked 6 times:
12 subprocesses, ~0.2 s of every query), and the next command asks again."""

from __future__ import annotations

import contextlib
import io
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from helpers import make_repo  # noqa: F401  (sets sys.path)

from cdp.cli import main
from cdp.store import registry


class GitAnswersTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory()
        root = Path(cls._tmp.name)
        cls.repo, cls.state = root / "repo", root / "state"
        (cls.repo / "a").mkdir(parents=True)
        (cls.repo / "a" / "m.py").write_text("def f():\n    return 1\n")
        git = lambda *a: subprocess.run(["git", "-C", str(cls.repo), *a], check=True, capture_output=True)
        git("init", "-q"); git("add", "-A")
        git("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init")
        cls.run_cdp("scan", "--quiet", "--no-docs")

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    @classmethod
    def run_cdp(cls, *args: str) -> int:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return main([args[0], *args[1:], "--repo", str(cls.repo), "--state-dir", str(cls.state)]) \
                if args[0] == "scan" else \
                main(["query", *args, "--repo", str(cls.repo), "--state-dir", str(cls.state)])

    def toplevel_calls(self) -> int:
        real, seen = registry.run_git, []
        def spy(repo, *args):
            seen.append(args)
            return real(repo, *args)
        with mock.patch.object(registry, "run_git", spy):
            self.assertEqual(self.run_cdp("symbol", "f"), 0)
        return seen.count(("rev-parse", "--show-toplevel"))

    def test_a_query_asks_for_the_repo_root_once(self):
        self.assertEqual(self.toplevel_calls(), 1)

    def test_the_next_command_asks_again(self):
        self.toplevel_calls()
        self.assertEqual(self.toplevel_calls(), 1)


if __name__ == "__main__":
    unittest.main()
