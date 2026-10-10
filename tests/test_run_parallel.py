"""`cdp run --parallel N`: the scopes of a wave are dispatched concurrently.

`run` used to dispatch one scope at a time, so a wave cost the sum of its scopes'
model calls instead of the slowest one.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import SKILL_ROOT, have_git, make_repo

from cdp.store.sqlite_backend import SqliteStore

RUN_PY = SKILL_ROOT / "run.py"

# Sleeps, records its own start and end, and writes a valid (unknowns-only) patch.
SLOW_RUNNER = """\
import json, sys, time
from pathlib import Path
log, patch_path = Path(sys.argv[1]), Path(sys.argv[3])
start = time.time()
time.sleep(0.8)
node = patch_path.stem.replace('__', '/')
patch_path.write_text(json.dumps({'schema_version': '1.0.0', 'node': node,
    'run_id': 'x', 'status': 'complete', 'claims': [],
    'unknowns': [{'question': 'what is here?', 'why_unresolved': 'fake', 'needs': 'needs_human'}]}))
with log.open('a') as f:
    f.write(json.dumps([start, time.time()]) + chr(10))
"""


@unittest.skipUnless(have_git(), "needs a real git repository")
class ParallelRunTest(unittest.TestCase):
    def run_all(self, *extra):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        repo = make_repo(Path(tmp.name))
        state = Path(tmp.name) / "state"
        subprocess.run([sys.executable, str(RUN_PY), "scan", "--repo", str(repo),
                        "--state-dir", str(state), "--quiet"], check=True, capture_output=True)
        script, log = Path(tmp.name) / "runner.py", Path(tmp.name) / "log.jsonl"
        script.write_text(SLOW_RUNNER)
        proc = subprocess.run(
            [sys.executable, str(RUN_PY), "run", "--repo", str(repo), "--state-dir", str(state),
             "--wave-all", "--runner-cmd", "%s %s %s" % (sys.executable, script, log), *extra],
            capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
        spans = [json.loads(line) for line in log.read_text().splitlines()]
        backend = SqliteStore(state / "index.db")
        run_id = backend.read_artifact("manifest")["run_id"]
        states = {r["state"] for r in backend.task_rows(run_id)}
        backend.close()
        return spans, states, proc.stdout

    @staticmethod
    def max_overlap(spans):
        return max(sum(1 for s, e in spans if s <= t < e) for t, _ in spans)

    def test_serial_by_default(self):
        spans, states, _ = self.run_all()
        self.assertEqual(self.max_overlap(spans), 1)
        self.assertEqual(states, {"folded"})

    def test_parallel_overlaps_scopes_and_still_folds_every_one(self):
        spans, states, out = self.run_all("--parallel", "4")
        self.assertGreaterEqual(len(spans), 2, "fixture needs two scopes in one wave")
        self.assertGreaterEqual(self.max_overlap(spans), 2)
        self.assertEqual(states, {"folded"})
        self.assertIn("parallel", out)


if __name__ == "__main__":
    unittest.main()
