"""Phase 2: one machine-level index (`CDP_HOME`).

Every command here is a real subprocess with `CDP_HOME` pointing at a throwaway
home, started from a folder that is *not* the repo -- the situation the old
`./.cdp` default got wrong.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import SKILL_ROOT, have_git, make_repo

from cdp.store import SqliteStore, registry


def cdp(args, cwd, home, check=True, **env):
    proc = subprocess.run(
        [sys.executable, "-m", "cdp.cli"] + list(args), cwd=str(cwd), capture_output=True, text=True,
        env=dict(os.environ, CDP_HOME=str(home), PYTHONPATH=str(SKILL_ROOT), **env),
    )
    if check and proc.returncode != 0:
        raise AssertionError("cdp %s -> %d\n%s\n%s" % (args, proc.returncode, proc.stdout, proc.stderr))
    return proc


def listing(root: Path):
    return sorted(str(p.relative_to(root)) for p in root.rglob("*") if ".git" not in p.parts)


@unittest.skipUnless(have_git(), "identity and HEAD need real git")
class OneStoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.home = self.root / "home"
        self.elsewhere = self.root / "elsewhere"
        self.elsewhere.mkdir()

    def test_scan_and_link_write_nothing_into_the_folder_they_run_from(self):
        caller = make_repo(self.root / "r1", fixture="callerrepo")
        callee = make_repo(self.root / "r2", fixture="calleerepo")
        before = (listing(self.elsewhere), listing(caller), listing(callee))
        for repo in (caller, callee):
            cdp(["scan", "--repo", repo, "--quiet"], self.elsewhere, self.home)
        cdp(["link", "scan"], self.elsewhere, self.home)
        self.assertEqual(before, (listing(self.elsewhere), listing(caller), listing(callee)))
        self.assertTrue((self.home / "index.db").is_file())

    def test_a_subfolder_and_its_parent_are_two_repos(self):
        repo = make_repo(self.root / "mono")
        cdp(["scan", "--repo", repo, "--quiet"], self.elsewhere, self.home)
        cdp(["scan", "--repo", repo / "core", "--quiet"], self.elsewhere, self.home)
        store = SqliteStore(self.home / "index.db")
        ids = sorted(s["repo_id"] for s in store.list_snapshots())
        store.close()
        self.assertEqual(len(ids), 2)
        self.assertEqual(ids[1], ids[0] + "#core")

        whole = json.loads(cdp(["query", "stats", "--json"], repo, self.home).stdout)
        sub = json.loads(cdp(["query", "stats", "--json"], repo / "core", self.home).stdout)
        # The parent's index survived the subfolder's scan, and the two differ.
        self.assertGreater(whole["census"]["tracked"], sub["census"]["tracked"])

    def test_scans_of_two_repos_run_at_once_and_link_scan_covers_both(self):
        caller = make_repo(self.root / "r1", fixture="callerrepo")
        callee = make_repo(self.root / "r2", fixture="calleerepo")
        env = dict(os.environ, CDP_HOME=str(self.home), PYTHONPATH=str(SKILL_ROOT))
        procs = [
            subprocess.Popen([sys.executable, "-m", "cdp.cli", "scan", "--repo", str(r), "--quiet"],
                             cwd=str(self.elsewhere), env=env, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, text=True)
            for r in (caller, callee) * 2
        ]
        for proc in procs:
            _, err = proc.communicate(timeout=120)
            self.assertEqual(proc.returncode, 0, err)

        out = cdp(["link", "scan", "--json"], self.elsewhere, self.home).stdout
        report = json.loads(out)
        self.assertEqual(len(report["links"]), 1)
        self.assertEqual(report["links"][0]["caller"]["repo"], registry.repo_identity(caller))
        self.assertEqual(report["links"][0]["callee"]["repo"], registry.repo_identity(callee))

        # `query` from inside either repo answers for that repo.
        for repo, expect in ((caller, "BillingClient"), (callee, "ChargeResource")):
            out = cdp(["query", "search", expect], repo, self.home).stdout
            self.assertIn(expect, out)
        other = cdp(["query", "search", "ChargeResource"], caller, self.home).stdout
        self.assertNotIn("com.acme.billing.ChargeResource", other)

    def test_a_backend_key_in_a_repos_cdp_toml_is_rejected(self):
        repo = make_repo(self.root / "r")
        (repo / ".cdp.toml").write_text('backend = "postgres"\n', encoding="utf-8")
        proc = cdp(["scan", "--repo", repo, "--quiet"], self.elsewhere, self.home, check=False)
        self.assertEqual(proc.returncode, 2)
        self.assertIn("config.toml", proc.stderr)
        self.assertFalse((self.home / "index.db").exists())

    def test_cdp_store_is_no_longer_read(self):
        repo = make_repo(self.root / "r")
        proc = cdp(["scan", "--repo", repo, "--quiet"], self.elsewhere, self.home, check=False,
                   CDP_STORE=str(self.root / "old"))
        self.assertEqual(proc.returncode, 2)
        self.assertIn("CDP_HOME", proc.stderr)

    def test_state_dir_is_an_alias_for_cdp_home(self):
        repo = make_repo(self.root / "r")
        alias = self.root / "alias"
        cdp(["scan", "--repo", repo, "--state-dir", alias, "--quiet"], self.elsewhere, self.home)
        self.assertTrue((alias / "index.db").is_file())
        self.assertFalse(self.home.exists())

    def test_work_files_live_under_the_home_per_repo(self):
        repo = make_repo(self.root / "r")
        cdp(["scan", "--repo", repo, "--quiet"], self.elsewhere, self.home)
        cdp(["prompts", "--repo", repo], self.elsewhere, self.home)
        work = registry.work_dir(self.home, registry.repo_identity(repo))
        self.assertTrue(list((work / "prompts").glob("*.md")))
        self.assertTrue((work / "docs").is_dir())

    def test_reading_an_unscanned_repo_says_so_and_does_not_borrow_another(self):
        scanned = make_repo(self.root / "a")
        unscanned = make_repo(self.root / "b", fixture="solorepo")
        cdp(["scan", "--repo", scanned, "--quiet"], self.elsewhere, self.home)
        proc = cdp(["query", "stats"], unscanned, self.home, check=False)
        self.assertEqual(proc.returncode, 2)
        self.assertIn("no scan of", proc.stderr)
        self.assertIn(registry.repo_identity(scanned), proc.stderr)


if __name__ == "__main__":
    unittest.main()
