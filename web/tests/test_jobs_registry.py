"""`web/api/jobs.py`'s single-flight registry (`WEB_RESEARCH.md` §7.2.4): a
second `spawn_or_join` call for the same `(repo, state_dir)` while the first
is still running must return the *same* job, not spawn a second process.
`subprocess.Popen` is patched to launch a slow `sleep` instead of a real `cdp
run`/`cdp refresh` invocation, so the race is deterministic rather than
depending on how fast a real command happens to finish."""

from __future__ import annotations

import subprocess
import sys
import unittest
from unittest import mock

from web.api import jobs as jobs_mod

_REAL_POPEN = subprocess.Popen


class JobsRegistryTest(unittest.TestCase):
    def _slow_popen(self, command, **kwargs):
        return _REAL_POPEN(
            [sys.executable, "-c", "import time; time.sleep(5)"], **kwargs,
        )

    def test_second_call_joins_first_while_running(self) -> None:
        with mock.patch.object(jobs_mod.subprocess, "Popen", side_effect=self._slow_popen):
            job1, joined1 = jobs_mod.spawn_or_join("run", "/tmp/repo-a", "/tmp/state-a", ["--wave-all"])
            job2, joined2 = jobs_mod.spawn_or_join("run", "/tmp/repo-a", "/tmp/state-a", ["--wave-all"])

        try:
            self.assertFalse(joined1)
            self.assertTrue(joined2)
            self.assertEqual(job1.job_id, job2.job_id)
        finally:
            job1.process.terminate()
            job1.process.wait(timeout=10)

    def test_different_state_dir_gets_its_own_job(self) -> None:
        with mock.patch.object(jobs_mod.subprocess, "Popen", side_effect=self._slow_popen):
            job1, _ = jobs_mod.spawn_or_join("run", "/tmp/repo-b", "/tmp/state-b1", ["--wave-all"])
            job2, joined2 = jobs_mod.spawn_or_join("run", "/tmp/repo-b", "/tmp/state-b2", ["--wave-all"])

        try:
            self.assertFalse(joined2)
            self.assertNotEqual(job1.job_id, job2.job_id)
        finally:
            job1.process.terminate()
            job1.process.wait(timeout=10)
            job2.process.terminate()
            job2.process.wait(timeout=10)

    def test_new_job_spawned_once_previous_finished(self) -> None:
        def _fast_popen(command, **kwargs):
            return _REAL_POPEN([sys.executable, "-c", "pass"], **kwargs)

        with mock.patch.object(jobs_mod.subprocess, "Popen", side_effect=_fast_popen):
            job1, joined1 = jobs_mod.spawn_or_join("refresh", "/tmp/repo-c", "/tmp/state-c", [])
            job1.process.wait(timeout=10)
            job2, joined2 = jobs_mod.spawn_or_join("refresh", "/tmp/repo-c", "/tmp/state-c", [])

        self.assertFalse(joined1)
        self.assertFalse(joined2)
        self.assertNotEqual(job1.job_id, job2.job_id)
        job2.process.wait(timeout=10)


if __name__ == "__main__":
    unittest.main()
