"""QA round 2: `link query --service` by name, the link-scan footprint, `doctor` recall off the
repo's content, census/refresh counts that ignore excluded paths, the 0.0% coverage wording."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import SKILL_ROOT, have_git, make_repo

RUN = [sys.executable, str(SKILL_ROOT / "run.py")]
GIT_ENV = {"GIT_AUTHOR_NAME": "cdp", "GIT_AUTHOR_EMAIL": "cdp@example.invalid",
           "GIT_COMMITTER_NAME": "cdp", "GIT_COMMITTER_EMAIL": "cdp@example.invalid"}
RUNNER = ('import json, sys\n'
          'json.dump({"schema_version": "1.0.0", "node": "x", "run_id": "doctor-test", "status": "complete",'
          ' "claims": [], "unknowns": []}, open(sys.argv[-1], "w"))\n')


class Case(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.home = self.tmp / "home"
        self.cwd = self.tmp / "elsewhere"  # not a parent of CDP_HOME
        self.cwd.mkdir()
        self.env = dict(os.environ, CDP_HOME=str(self.home))
        self.env.pop("PYTHONPATH", None)

    def cdp(self, *argv, cwd=None):
        return subprocess.run(RUN + [str(a) for a in argv], capture_output=True, text=True, env=self.env,
                              cwd=str(cwd or self.cwd))

    def scan(self, repo: Path) -> None:
        proc = self.cdp("scan", "--repo", repo, "--quiet")
        self.assertEqual(proc.returncode, 0, proc.stderr)


@unittest.skipUnless(have_git(), "needs git")
class LinkServiceByNameTest(Case):
    def setUp(self) -> None:
        super().setUp()
        (self.tmp / "repos").mkdir()
        self.caller = make_repo(self.tmp / "repos", "callerrepo")
        self.callee = make_repo(self.tmp / "repos", "calleerepo")
        self.scan(self.caller)
        self.scan(self.callee)

    def test_query_accepts_name_path_and_unique_prefix(self) -> None:
        self.assertEqual(self.cdp("link", "scan", "--db").returncode, 0)
        for service in ("calleerepo", str(self.callee), str(self.callee) + "/"):
            proc = self.cdp("link", "query", "--service", service)
            self.assertEqual(proc.returncode, 0, "%s: %s" % (service, proc.stderr))
            self.assertIn("called by", proc.stdout)
            self.assertIn("[callerrepo]", proc.stdout)  # named, not a UUID
        listing = self.cdp("link", "query", "--service", "nope")
        self.assertNotEqual(listing.returncode, 0)
        self.assertIn("calleerepo", listing.stderr)  # the error lists the known names
        self.assertIn("callerrepo", listing.stderr)
        ident = json.loads(self.cdp("link", "query", "--service", "callerrepo", "--json").stdout)["service"]
        uuid_prefix = ident[:8]
        again = self.cdp("link", "query", "--service", uuid_prefix)
        self.assertEqual(again.returncode, 0, again.stderr)
        self.assertIn("calls", again.stdout)

    def test_scan_does_not_modify_the_index_and_reuses_one_lock_file(self) -> None:
        def digest(name):
            p = self.home / name
            return hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None

        self.assertEqual(self.cdp("link", "scan", "--db").returncode, 0)
        before = (digest("index.db"), digest("index.db-wal"))
        for _ in range(3):
            self.assertEqual(self.cdp("link", "scan").returncode, 0)
        self.assertEqual((digest("index.db"), digest("index.db-wal")), before)
        self.assertEqual(len(list((self.home / "locks").glob("links-*.lock"))), 1)
        self.assertIn("does not modify the index", self.cdp("link", "scan", "--help").stdout.replace("\n", " "))


@unittest.skipUnless(have_git(), "needs git")
class DoctorRecallTest(Case):
    def doctor(self, repo: Path):
        (self.tmp / "runner.py").write_text(RUNNER)
        self.scan(repo)
        return self.cdp("doctor", "--repo", repo, "--model", "m1",
                        "--runner-cmd", "%s %s" % (sys.executable, self.tmp / "runner.py"))

    def test_golden_set_follows_the_content_not_the_directory_name(self) -> None:
        (self.tmp / "a").mkdir()
        mini = make_repo(self.tmp / "a", "minirepo").rename(self.tmp / "a" / "widgets")
        proc = self.doctor(mini)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("recall=0%", proc.stdout)
        self.assertNotIn("recall=?", proc.stdout)
        self.assertNotIn("n/a (no golden set", proc.stdout)

    def test_a_repo_with_no_golden_set_says_so_and_is_not_a_failure(self) -> None:
        (self.tmp / "b").mkdir()
        proc = self.doctor(make_repo(self.tmp / "b", "solorepo"))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("recall: n/a (no golden set for this repo)", proc.stdout)
        self.assertNotIn("?%", proc.stdout)


@unittest.skipUnless(have_git(), "needs git")
class ExcludedPathsAreNotCountedTest(Case):
    def commit_all(self, repo: Path, msg: str) -> None:
        env = dict(os.environ, **GIT_ENV)
        subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True, capture_output=True, env=env)
        subprocess.run(["git", "-C", str(repo), "-c", "commit.gpgsign=false", "commit", "-q", "-m", msg],
                       check=True, capture_output=True, env=env)

    def test_census_and_refresh_ignore_the_harness_files(self) -> None:
        (self.tmp / "r").mkdir()
        repo = make_repo(self.tmp / "r")
        self.scan(repo)
        before = json.loads(self.cdp("query", "stats", "--json", "--repo", repo).stdout)["census"]
        for rel in (".claude/skills/cdp/x.py", ".claude/settings.json", ".mcp.json"):
            (repo / rel).parent.mkdir(parents=True, exist_ok=True)
            (repo / rel).write_text("{}\n")
        self.commit_all(repo, "harness")
        proc = self.cdp("refresh", "--repo", repo)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("0 file(s) changed", proc.stdout)
        self.assertIn("0 added", proc.stdout)
        after = json.loads(self.cdp("query", "stats", "--json", "--repo", repo).stdout)["census"]
        self.assertEqual(after["tracked"], before["tracked"])
        self.assertEqual(after["on_disk"], before["on_disk"])  # was +3: the excluded files were counted


@unittest.skipUnless(have_git(), "needs git")
class CoverageWordingTest(Case):
    def test_status_keeps_the_number_and_explains_it(self) -> None:
        (self.tmp / "r").mkdir()
        repo = make_repo(self.tmp / "r")
        self.scan(repo)
        out = self.cdp("status", "--repo", repo).stdout
        self.assertIn("coverage  0.0% model-reviewed (deterministic index complete; run `cdp run` for AI review)", out)


if __name__ == "__main__":
    unittest.main()
