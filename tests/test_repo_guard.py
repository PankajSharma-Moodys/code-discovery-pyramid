"""`--repo` must match the repo a state was scanned from -- found live:
`cdp run` defaulted `--repo` to cwd when omitted, verified every claim
against the wrong tree, and every anchor failed, indistinguishable at a
glance from a genuinely bad leaf run. `manifest["repo"]` is already
recorded by `cmd_scan`; these commands now cross-check it before touching
any file content.
"""

from __future__ import annotations

import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from helpers import make_repo  # noqa: F401  (sets sys.path)

from cdp.cli import main


def run(argv, expect_code=None):
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = main(argv)
    if expect_code is not None:
        assert code == expect_code, (code, argv, buf.getvalue())
    return code, buf.getvalue()


class RepoMismatchTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        cls.repo = make_repo(Path(cls.tmp.name) / "repo")
        cls.other_repo = make_repo(Path(cls.tmp.name) / "other", fixture="solorepo")
        cls.state = Path(cls.tmp.name) / "state"
        code, _ = run(["scan", "--repo", str(cls.repo), "--state-dir", str(cls.state), "--quiet"])
        assert code == 0

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def _assert_mismatch(self, argv):
        buf = io.StringIO()
        with redirect_stdout(buf):
            import sys
            err = io.StringIO()
            old_stderr = sys.stderr
            sys.stderr = err
            try:
                code = main(argv)
            finally:
                sys.stderr = old_stderr
        self.assertEqual(code, 2)
        self.assertIn("does not match the repo this state was scanned from", err.getvalue())
        self.assertIn(str(self.repo), err.getvalue())
        self.assertIn(str(self.other_repo), err.getvalue())

    def test_run_rejects_a_mismatched_repo(self) -> None:
        self._assert_mismatch(
            ["run", "--repo", str(self.other_repo), "--state-dir", str(self.state),
             "--stale-only"]
        )

    def test_collect_rejects_a_mismatched_repo(self) -> None:
        self._assert_mismatch(
            ["collect", "--repo", str(self.other_repo), "--state-dir", str(self.state)]
        )

    def test_fold_check_rejects_a_mismatched_repo(self) -> None:
        self._assert_mismatch(
            ["fold", "--check", "--repo", str(self.other_repo), "--state-dir", str(self.state)]
        )

    def test_refresh_rejects_a_mismatched_repo(self) -> None:
        self._assert_mismatch(
            ["refresh", "--repo", str(self.other_repo), "--state-dir", str(self.state)]
        )

    def test_answer_rejects_a_mismatched_repo(self) -> None:
        self._assert_mismatch(
            ["answer", "root", "--repo", str(self.other_repo), "--state-dir", str(self.state),
             "--subject", "x", "--kind", "config", "--claim", "x", "--anchor", "x",
             "--channel", "config_read"]
        )

    def test_matching_repo_does_not_raise_the_mismatch_error(self) -> None:
        code, out = run(
            ["collect", "--repo", str(self.repo), "--state-dir", str(self.state)],
            expect_code=0,
        )
        self.assertNotIn("does not match", out)

    def test_no_recorded_repo_is_not_an_error(self) -> None:
        """A state with nothing recorded yet (or an older one) has nothing
        to cross-check against -- this guard must not invent a failure."""
        from cdp.cli import _check_repo_matches_manifest, Paths
        _check_repo_matches_manifest(Paths(repo=Path("/anything"), state=Path(".")), {})


class RunnerFallbackWarningTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        cls.repo = make_repo(Path(cls.tmp.name) / "repo")
        cls.state = Path(cls.tmp.name) / "state"
        code, _ = run(["scan", "--repo", str(cls.repo), "--state-dir", str(cls.state), "--quiet"])
        assert code == 0

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def test_warns_when_runner_cmd_is_omitted(self) -> None:
        _, out = run(
            ["run", "--repo", str(self.repo), "--state-dir", str(self.state), "--stale-only"],
            expect_code=0,
        )
        self.assertIn("no --runner-cmd given", out)

    def test_silent_when_runner_cmd_is_given(self) -> None:
        _, out = run(
            ["run", "--repo", str(self.repo), "--state-dir", str(self.state), "--stale-only",
             "--runner-cmd", "true"],
            expect_code=0,
        )
        self.assertNotIn("no --runner-cmd given", out)


if __name__ == "__main__":
    unittest.main()
