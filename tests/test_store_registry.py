"""Machine home and repo identity (`cdp/store/registry.py`)."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from helpers import make_repo

SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT))

from cdp.store import registry  # noqa: E402


class TestRepoIdentity(unittest.TestCase):
    def test_two_clones_of_the_same_remote_share_an_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            origin = Path(tmp) / "origin.git"
            subprocess.run(["git", "init", "-q", "--bare", str(origin)], check=True)
            clone_a = Path(tmp) / "a"
            clone_b = Path(tmp) / "b"
            for clone in (clone_a, clone_b):
                subprocess.run(["git", "clone", "-q", str(origin), str(clone)], check=True,
                                capture_output=True)
            self.assertEqual(registry.repo_identity(clone_a), registry.repo_identity(clone_b))

    def test_two_different_remotes_get_different_identities(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = make_repo(Path(tmp), fixture="minirepo")
            b = make_repo(Path(tmp), fixture="solorepo")
            subprocess.run(["git", "-C", str(a), "remote", "add", "origin",
                            "git@github.com:acme/repo-a.git"], check=True, capture_output=True)
            subprocess.run(["git", "-C", str(b), "remote", "add", "origin",
                            "https://github.com/acme/repo-b"], check=True, capture_output=True)
            self.assertNotEqual(registry.repo_identity(a), registry.repo_identity(b))

    def test_ssh_and_https_remotes_normalise_to_the_same_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = make_repo(Path(tmp), fixture="minirepo")
            b = make_repo(Path(tmp), fixture="solorepo")
            subprocess.run(["git", "-C", str(a), "remote", "add", "origin",
                            "git@github.com:acme/repo.git"], check=True, capture_output=True)
            subprocess.run(["git", "-C", str(b), "remote", "add", "origin",
                            "https://github.com/acme/repo.git"], check=True, capture_output=True)
            self.assertEqual(registry.repo_identity(a), registry.repo_identity(b))

    def test_a_repo_with_no_remote_gets_a_uuid_that_survives_a_move(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(Path(tmp), fixture="minirepo")
            first = registry.repo_identity(repo)

            moved = Path(tmp) / "moved-elsewhere"
            shutil.move(str(repo), str(moved))
            second = registry.repo_identity(moved)
            self.assertEqual(first, second)

    def test_a_declared_id_wins_over_a_remote(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(Path(tmp), fixture="minirepo")
            subprocess.run(["git", "-C", str(repo), "remote", "add", "origin",
                            "https://github.com/acme/repo.git"], check=True, capture_output=True)
            (repo / registry.DECLARED_ID_FILE).write_text("acme-repo\n", encoding="utf-8")
            self.assertEqual(registry.repo_identity(repo), "acme-repo")


class TestFolderIdentity(unittest.TestCase):
    """A folder below the git root is its own repo (`<remote>#<path>`)."""

    def _repo_with_remote(self, tmp: Path) -> Path:
        repo = make_repo(tmp, fixture="minirepo")
        subprocess.run(["git", "-C", str(repo), "remote", "add", "origin",
                        "https://github.com/acme/mono.git"], check=True, capture_output=True)
        return repo

    def test_a_subfolder_and_its_parent_are_two_repos(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._repo_with_remote(Path(tmp))
            self.assertEqual(registry.repo_identity(repo), "github.com/acme/mono")
            self.assertEqual(registry.repo_identity(repo / "core"), "github.com/acme/mono#core")
            nested = repo / "core" / "src"
            self.assertEqual(registry.repo_identity(nested), "github.com/acme/mono#core/src")

    def test_a_clone_of_the_same_folder_shares_the_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = self._repo_with_remote(Path(tmp) / "a")
            b = self._repo_with_remote(Path(tmp) / "b")
            self.assertEqual(registry.repo_identity(a / "web"), registry.repo_identity(b / "web"))

    def test_a_folders_own_declared_id_is_a_full_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._repo_with_remote(Path(tmp))
            (repo / "core" / registry.DECLARED_ID_FILE).write_text("core-svc\n", encoding="utf-8")
            self.assertEqual(registry.repo_identity(repo / "core"), "core-svc")

    def test_a_folder_outside_git_is_identified_by_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "plain"
            folder.mkdir()
            self.assertTrue(registry.repo_identity(folder).startswith("path:"))
            self.assertEqual(registry.repo_identity(folder), registry.repo_identity(folder))

    def test_candidates_run_from_the_folder_up_to_the_git_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._repo_with_remote(Path(tmp))
            got = [i for _, i in registry.candidate_identities(repo / "core" / "src")]
            self.assertEqual(got, ["github.com/acme/mono#core/src", "github.com/acme/mono#core",
                                   "github.com/acme/mono"])

    def test_work_dirs_never_collide_for_distinct_ids(self):
        a, b = registry.repo_slug("x/y#a"), registry.repo_slug("x/y_a")
        self.assertNotEqual(a, b)


class TestHome(unittest.TestCase):
    def test_cdp_home_overrides_the_default(self):
        with mock.patch.dict(os.environ, {"CDP_HOME": "/tmp/somewhere-else"}):
            self.assertEqual(registry.cdp_home(), Path("/tmp/somewhere-else").resolve())

    def test_default_is_dot_cdp_in_the_users_home(self):
        env = {k: v for k, v in os.environ.items() if k != "CDP_HOME"}
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertEqual(registry.cdp_home(), Path.home() / ".cdp")

    def test_the_backend_is_chosen_once_in_the_machine_config(self):
        with tempfile.TemporaryDirectory() as home:
            self.assertEqual(registry.machine_backend(Path(home)), "sqlite")
            (Path(home) / "config.toml").write_text(
                'backend = "postgres"\n[postgres]\ndsn = "postgresql://x/y"\n', encoding="utf-8")
            self.assertEqual(registry.machine_backend(Path(home)), "postgres")
            self.assertEqual(registry.machine_postgres_config(Path(home)),
                             {"dsn": "postgresql://x/y", "schema": None})

    def test_a_leftover_repos_registry_is_ignored(self):
        with tempfile.TemporaryDirectory() as home:
            (Path(home) / "config.toml").write_text('[repos]\n"x" = "/old/.cdp"\n', encoding="utf-8")
            self.assertEqual(registry.machine_backend(Path(home)), "sqlite")


if __name__ == "__main__":
    unittest.main()
