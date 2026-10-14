"""A failed `rollback` changes nothing, and `--as-of`/`--to-snapshot` accept a prefix that names one commit."""

from __future__ import annotations

import unittest

import test_p2_fold as P
from cdp.rollback import resolve_run_id
from cdp.util import CdpError


def _log(*run_ids):
    return [{"run_id": r, "patch_no": i + 1} for i, r in enumerate(run_ids)]


class ResolveRunIdTest(unittest.TestCase):
    def test_runs_of_one_commit_are_one_candidate(self):
        log = _log("cdp-601475302d04", "cdp-601475302d04-r2", "cdp-601475302d04-r3", "cdp-aaaa11112222")
        self.assertEqual(resolve_run_id("6014753", log), "cdp-601475302d04-r3")
        self.assertEqual(resolve_run_id("cdp-6014753", log), "cdp-601475302d04-r3")

    def test_the_latest_appended_run_of_the_commit_wins(self):
        log = _log("cdp-601475302d04-r2", "cdp-601475302d04", "cdp-aaaa11112222")
        self.assertEqual(resolve_run_id("6014", log), "cdp-601475302d04")

    def test_distinct_commits_still_collide(self):
        log = _log("cdp-601475302d04", "cdp-601475302d04-r2", "cdp-601499999999")
        with self.assertRaises(CdpError) as ctx:
            resolve_run_id("6014", log)
        msg = str(ctx.exception)
        self.assertIn("ambiguous", msg)
        self.assertEqual(msg.count("601475302d04"), 1)


class FailedRollbackChangesNothingTest(P.RepoCase):
    def archived(self, cdp):
        backend, _ = cdp.open()
        try:
            return backend._conn.execute("SELECT COUNT(*) FROM claim_patches_archive").fetchone()[0]
        finally:
            backend.close()

    def test_unknown_target_leaves_the_archive_alone(self):
        _, cdp = self.multi()
        cdp.inject_model_patch("root/a", [self.a_claim("t.one")])
        cdp.inject_model_patch("root/a", [self.a_claim("t.two", "com.example.a.Other")])
        cdp.run("compact", "--compact-threshold", "0")
        before = self.archived(cdp)
        self.assertGreater(before, 0)
        for flag in ("--to-run", "--to-snapshot"):
            proc = cdp.run("rollback", flag, "nope", check=False)
            self.assertEqual(proc.returncode, 2)
            self.assertNotIn("restored", proc.stdout)
            self.assertEqual(self.archived(cdp), before)

    def test_a_valid_rollback_still_restores_the_archive(self):
        _, cdp = self.multi()
        cdp.inject_model_patch("root/a", [self.a_claim("t.one")])
        cdp.inject_model_patch("root/a", [self.a_claim("t.two", "com.example.a.Other")])
        cdp.run("compact", "--compact-threshold", "0")
        backend, store = cdp.open()
        run_id = store.manifest["run_id"]
        backend.close()
        proc = cdp.run("rollback", "--to-run", run_id, check=False)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(self.archived(cdp), 0)


if __name__ == "__main__":
    unittest.main()
