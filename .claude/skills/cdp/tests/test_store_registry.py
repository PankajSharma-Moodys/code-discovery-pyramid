"""Store resolution and repo identity (`PHASE/phase_2_plan.md` M2.6).

`REGISTRY_PATH` is `~/.cdp/config.toml` by construction (module docstring:
per-user, not per-repo). These tests monkeypatch it to a temp file so they
never touch the real one.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import make_repo

SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT))

from cdp.store import registry  # noqa: E402


class RegistryTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self._orig_path = registry.REGISTRY_PATH
        registry.REGISTRY_PATH = Path(self._tmp.name) / "registry" / "config.toml"
        self.addCleanup(setattr, registry, "REGISTRY_PATH", self._orig_path)


class TestRepoIdentity(RegistryTestCase):
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


class TestRegistryRoundTrip(RegistryTestCase):
    def test_register_then_lookup_finds_the_same_path(self):
        registry.register("repo-x", Path("/tmp/somewhere/.cdp"))
        self.assertEqual(registry.lookup("repo-x"), Path("/tmp/somewhere/.cdp").resolve())

    def test_lookup_of_an_unregistered_id_is_none(self):
        self.assertIsNone(registry.lookup("never-registered"))

    def test_registering_twice_is_idempotent_and_keeps_other_entries(self):
        registry.register("repo-x", Path("/tmp/x"))
        registry.register("repo-y", Path("/tmp/y"))
        registry.register("repo-x", Path("/tmp/x-moved"))
        self.assertEqual(registry.lookup("repo-x"), Path("/tmp/x-moved").resolve())
        self.assertEqual(registry.lookup("repo-y"), Path("/tmp/y").resolve())


class TestResolveStore(RegistryTestCase):
    def test_env_wins_over_registry(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(Path(tmp), fixture="minirepo")
            registry.register(registry.repo_identity(repo), Path("/tmp/from-registry"))
            resolved = registry.resolve_store(repo, env="/tmp/from-env")
            self.assertEqual(resolved, Path("/tmp/from-env").resolve())

    def test_registry_wins_over_default_when_no_team_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(Path(tmp), fixture="minirepo")
            target = Path(tmp) / "registered-state"
            registry.register(registry.repo_identity(repo), target)
            self.assertEqual(registry.resolve_store(repo), target.resolve())

    def test_default_is_returned_when_nothing_else_resolves(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(Path(tmp), fixture="minirepo")
            fallback = Path(tmp) / "fallback" / ".cdp"
            self.assertEqual(registry.resolve_store(repo, default=fallback), fallback.resolve())

    def test_team_file_wins_over_registry(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(Path(tmp), fixture="minirepo")
            registry.register(registry.repo_identity(repo), Path("/tmp/from-registry"))
            team_target = Path(tmp) / "team-state"
            (repo / registry.TEAM_CONFIG_FILE).write_text(
                'store = "%s"\n' % team_target, encoding="utf-8"
            )
            self.assertEqual(registry.resolve_store(repo), team_target.resolve())


if __name__ == "__main__":
    unittest.main()
