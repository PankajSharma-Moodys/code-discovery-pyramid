"""Phase 3, M3.8 -- git `post-commit`/`post-checkout` hooks that auto-refresh.

The acceptance line from `phase_3_plan.md`: "Commit triggers refresh; branch
switch triggers refresh; `git checkout -- <path>` does not." The integration
test below drives real `git commit`/`git checkout` subprocesses (not a direct
call to `cdp refresh`) so the hook scripts themselves are what is exercised.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import have_git, make_repo

from cdp import githooks
from cdp.store.sqlite_backend import SqliteStore
from cdp.util import CdpError

CDP_ROOT = Path(__file__).resolve().parent.parent


def _git(repo: Path, *args: str, env=None) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo)] + list(args),
                           capture_output=True, text=True, env=env)


def _commit(repo: Path, message: str, env) -> str:
    _git(repo, "add", "-A", env=env)
    proc = _git(repo, "-c", "user.name=cdp", "-c", "user.email=cdp@example.invalid",
                "-c", "commit.gpgsign=false", "commit", "-q", "-m", message, env=env)
    assert proc.returncode == 0, proc.stderr
    return _git(repo, "rev-parse", "HEAD", env=env).stdout.strip()


@unittest.skipUnless(have_git(), "git required")
class InstallUninstallTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = make_repo(Path(self.tmp.name))

    def test_installs_both_hooks_with_marker_and_exec_bit(self) -> None:
        lines = githooks.install(self.repo)
        hdir = githooks.hooks_dir(self.repo)
        for name in githooks.HOOK_NAMES:
            target = hdir / name
            self.assertTrue(target.exists())
            self.assertIn(githooks.MARKER, target.read_text())
            self.assertTrue(target.stat().st_mode & 0o111, "hook must be executable")
        self.assertTrue(any("cost" in l for l in lines))

    def test_install_is_idempotent(self) -> None:
        githooks.install(self.repo)
        githooks.install(self.repo)  # must not raise "already exists"
        hdir = githooks.hooks_dir(self.repo)
        self.assertIn(githooks.MARKER, (hdir / "post-commit").read_text())

    def test_refuses_to_clobber_a_foreign_hook(self) -> None:
        hdir = githooks.hooks_dir(self.repo)
        hdir.mkdir(parents=True, exist_ok=True)
        (hdir / "post-commit").write_text("#!/bin/sh\necho not cdp's\n")
        with self.assertRaises(CdpError):
            githooks.install(self.repo)
        # the untouched hook and the never-written post-checkout both prove
        # the refusal aborted before writing anything
        self.assertNotIn(githooks.MARKER, (hdir / "post-commit").read_text())
        self.assertFalse((hdir / "post-checkout").exists())

    def test_uninstall_removes_only_what_it_installed(self) -> None:
        hdir = githooks.hooks_dir(self.repo)
        hdir.mkdir(parents=True, exist_ok=True)
        (hdir / "post-commit").write_text("#!/bin/sh\necho foreign\n")
        # install a cdp-managed script only for post-checkout, alongside the
        # foreign post-commit it must not touch
        target = hdir / "post-checkout"
        target.write_text(githooks._script("post-checkout", sys.executable, self.repo))
        lines = githooks.uninstall(self.repo)
        self.assertFalse(target.exists())
        self.assertTrue((hdir / "post-commit").exists())  # foreign hook left alone
        self.assertTrue(any("skipped" in l for l in lines))


@unittest.skipUnless(have_git(), "git required")
class RealHookFiringTest(unittest.TestCase):
    """Drives the installed hook scripts via real `git commit`/`git checkout`,
    not via a direct `cdp refresh` call -- the hook script is the thing under
    test."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name) / "home"
        self.home.mkdir()
        self.scancwd = Path(self.tmp.name) / "scancwd"
        self.scancwd.mkdir()
        self.repo = make_repo(Path(self.tmp.name) / "work")
        self.env = {
            "HOME": str(self.home), "PATH": "/usr/bin:/bin:/usr/local/bin",
            "PYTHONPATH": str(CDP_ROOT),
        }
        # No `--state-dir`: state lands at `cwd/.cdp` and gets registered under
        # this repo's identity (`~/.cdp/config.toml`, HOME redirected above), so
        # the hook's own `cdp refresh --repo <repo>` -- run from whatever cwd git
        # gives the hook -- resolves the same store via the registry, exactly
        # the "store pointer from 2.3" the plan names.
        scan = subprocess.run(
            [sys.executable, "-m", "cdp.cli", "scan", "--repo", str(self.repo), "--quiet"],
            cwd=str(self.scancwd), env=self.env, capture_output=True, text=True,
        )
        assert scan.returncode == 0, scan.stderr
        self.db = self.scancwd / ".cdp" / "index.db"
        assert self.db.exists(), "scan should have registered cwd/.cdp via the registry"
        githooks.install(self.repo)

    def _head(self) -> str:
        # Matches what `cdp status`/`cdp query` actually do (`query.Store`
        # resolves to the latest snapshot before reading) -- a bare
        # `read_artifact` would silently re-check the lazy `id=1` default.
        store = SqliteStore(self.db)
        store.use_latest_snapshot()
        head = store.read_artifact("manifest", {}).get("head")
        store.close()
        return head

    def test_commit_triggers_refresh(self) -> None:
        before = self._head()
        (self.repo / "README.md").write_text("edited\n")
        new_sha = _commit(self.repo, "edit for post-commit", self.env)
        self.assertNotEqual(before, new_sha)
        self.assertEqual(self._head(), new_sha)

    def test_branch_checkout_triggers_refresh_but_file_checkout_does_not(self) -> None:
        (self.repo / "README.md").write_text("first edit\n")
        first_sha = _commit(self.repo, "first", self.env)
        self.assertEqual(self._head(), first_sha)

        _git(self.repo, "checkout", "-q", "-b", "feature", env=self.env)
        (self.repo / "README.md").write_text("second edit on branch\n")
        branch_sha = _commit(self.repo, "second", self.env)
        _git(self.repo, "checkout", "-q", "main", env=self.env)
        self.assertEqual(self._head(), first_sha)  # post-checkout back to main refreshed

        _git(self.repo, "checkout", "-q", "feature", env=self.env)
        self.assertEqual(self._head(), branch_sha)  # branch switch refreshed forward again

        # File-level checkout (`git checkout -- <path>`) is flag 0, not a ref
        # move, and must not fire -- the head recorded above must survive it.
        (self.repo / "README.md").write_text("dirty, about to be discarded\n")
        _git(self.repo, "checkout", "--", "README.md", env=self.env)
        self.assertEqual(self._head(), branch_sha)


if __name__ == "__main__":
    unittest.main()
