"""Every documented example runs (E11).

Examples in `cdp/guide_*.py` -- per kind, per command, per recipe step -- are bound to
a fixture repo and executed against a throwaway `CDP_HOME` outside the repo. Examples
marked `parse` (they need a model, a second repo or are destructive) are checked
against the real parser, which still catches a wrong flag, a missing argument or the
wrong positional (`answer --scope`, `holdout <repo>`, `install --hook` vs `githook`).
"""

from __future__ import annotations

import contextlib
import io
import os
import shlex
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from helpers import FIXTURES, make_repo  # noqa: F401  (sets sys.path)

from cdp.cli import main
from cdp.guide_commands import COMMANDS, RECIPES
from cdp.guide_kinds import KINDS
from cdp.parser import build_parser


def _all_examples():
    for kind, k in KINDS.items():
        for e in k["examples"]:
            yield "kind " + kind, e, "run"
    for name, c in COMMANDS.items():
        for e, mode in c["examples"]:
            yield "command " + name, e, mode
    for r in RECIPES:
        for e, mode in r["steps"]:
            yield "recipe " + r["name"], e, mode


class DocumentedExamplesRun(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        root = Path(cls.tmp.name)
        # orderrepo (route -> service -> repository -> table) plus minirepo's Dockerfile for a config key.
        cls.repo = make_repo(root, "orderrepo")
        shutil.copy(FIXTURES / "minirepo" / "Dockerfile", cls.repo / "Dockerfile")
        env = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@x", "GIT_COMMITTER_NAME": "t",
               "GIT_COMMITTER_EMAIL": "t@x", "PATH": os.environ["PATH"], "HOME": str(root)}
        for args in (["add", "-A"], ["-c", "commit.gpgsign=false", "commit", "-q", "-m", "docker"]):
            subprocess.run(["git", "-C", str(cls.repo)] + args, check=True, capture_output=True, env=env)
        cls.sha = subprocess.run(["git", "-C", str(cls.repo), "rev-parse", "HEAD"], check=True,
                                 capture_output=True, text=True).stdout.strip()
        cls.old_home = os.environ.get("CDP_HOME")
        os.environ["CDP_HOME"] = str(root / "home")  # never ~/.cdp, never inside the repo
        with contextlib.redirect_stdout(io.StringIO()):
            assert main(["scan", "--repo", str(cls.repo), "--quiet"]) == 0
        cls.counter = 0
        cls.target = root / "install-target"
        cls.target.mkdir()

    @classmethod
    def tearDownClass(cls) -> None:
        if cls.old_home is None:
            os.environ.pop("CDP_HOME", None)
        else:
            os.environ["CDP_HOME"] = cls.old_home
        cls.tmp.cleanup()

    def _bind(self, text: str) -> str:
        cls = type(self)
        values = {
            "<symbol>": "OrderService", "<method>": "OrderService#placeOrder", "<route>": "/orders",
            "<file>": "src/main/java/com/acme/orders/OrderResource.java", "<table>": "orders",
            "<config-key>": "MINI_DB_URL", "<module>": "root", "<word>": "order", "<sha>": cls.sha,
            "<target>": str(cls.target), "<repo>": str(cls.repo), "<repo-name>": "orderrepo",
            "<cmd>": "true", "<run>": "run", "<db>": str(Path(cls.tmp.name) / "x.db"),
            "<old_state>": str(cls.tmp.name), "<new_state>": str(cls.tmp.name), "<patch.json>": "p.json",
        }
        if "<out>" in text:
            cls.counter += 1
            text = text.replace("<out>", str(Path(cls.tmp.name) / ("out%d" % cls.counter)))
        for key, value in values.items():
            text = text.replace(key, value)
        return text

    def _argv(self, example: str):
        argv = shlex.split(self._bind(example))
        self.assertNotIn("<", " ".join(argv).replace("<CDP_HOME>", ""), "unbound placeholder in %r" % example)
        if "--repo" not in argv and argv[0] not in ("help", "install", "link"):
            argv += ["--repo", str(self.repo)]
        return argv

    def test_every_example_parses(self) -> None:
        parser = build_parser()
        for where, example, _mode in _all_examples():
            argv = self._argv(example)
            try:
                with contextlib.redirect_stderr(io.StringIO()) as err:
                    parser.parse_args(argv)
            except SystemExit:
                self.fail("%s: `cdp %s` does not parse: %s" % (where, example, err.getvalue().strip()[-200:]))

    def test_every_run_example_exits_zero(self) -> None:
        for where, example, mode in _all_examples():
            if mode != "run":
                continue
            argv = self._argv(example)
            out, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                rc = main(argv)
            # A scan alone records no unknowns (leaves do), so a term can match none here: exit 1, as help says.
            expected = 1 if example.startswith("query unknowns <") else 0
            self.assertEqual(rc, expected, "%s: `cdp %s` exited %s\n%s%s" % (
                where, example, rc, out.getvalue()[-300:], err.getvalue()[-300:]))

    def test_the_repo_was_not_written_to(self) -> None:
        status = subprocess.run(["git", "-C", str(self.repo), "status", "--porcelain"],
                                capture_output=True, text=True).stdout
        self.assertEqual(status.strip(), "", "examples must keep state in CDP_HOME, not the repo")


if __name__ == "__main__":
    unittest.main()
