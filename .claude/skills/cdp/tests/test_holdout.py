"""Phase 9 (M9.3, 6.8 only) -- holdout A/B, exercised end to end via the real
`cdp holdout` subcommand against two real fixture repos."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import SKILL_ROOT, make_repo

from cdp.store.registry import repo_identity
from cdp.trajectory import TrajectoryStore

RUN_PY = SKILL_ROOT / "run.py"


def _run(args, env, **kw):
    return subprocess.run(
        [sys.executable, str(RUN_PY)] + args, env=env, capture_output=True, text=True, **kw
    )


class HoldoutEndToEndTest(unittest.TestCase):
    """6.8's own acceptance line: "learn on repos A-E, benchmark on F", A/B'd
    for real via `cdp prompts`' deterministic tiering rule -- no live model
    call needed, since T3 escalation is the one signal a lesson can move."""

    def test_holdout_on_a_real_different_repo_promotes_and_gates_latest(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            learned_repo = make_repo(tmp / "learned", "minirepo")
            holdout_repo = make_repo(tmp / "holdout", "solorepo")
            state_learned = tmp / "state_learned"
            state_holdout = tmp / "state_holdout"
            traj_db = tmp / "trajectories.db"

            env = dict(os.environ)
            env["CDP_TRAJECTORY_DB"] = str(traj_db)

            _run(["scan", "--repo", str(learned_repo), "--state-dir", str(state_learned), "--quiet"], env, check=True)
            _run(["scan", "--repo", str(holdout_repo), "--state-dir", str(state_holdout), "--quiet"], env, check=True)

            # A promotion recorded against the *learned* repo only -- never
            # touching the holdout repo, which is the split 6.8 requires.
            learned_id = repo_identity(learned_repo)
            with TrajectoryStore(traj_db) as store:
                store.record_leaf_run(
                    run_id="learn-run", node="root", scope_hash="h1", repo_id=learned_id,
                    model="haiku", scope_shape_key="s1", template_version="1",
                    tier="T2", task_kind="scope", state="folded",
                )
                store.record_promotion(
                    run_id="learn-run", node="root",
                    promotion={"promotion": "import_channel_hint", "pattern": "com.acme.sdk", "channel": "call"},
                )
                version = store.cut_lessons()
                self.assertEqual(version, 1)
                self.assertIsNone(store.latest_lesson_version())  # not promoted yet

            # Before promotion, `cdp prompts` (default: latest *promoted* cut)
            # applies no lesson -- the pinned explicit `--lessons 1` still can.
            result = _run(
                ["prompts", "--repo", str(holdout_repo), "--state-dir", str(state_holdout), "--lessons", "1"],
                env,
            )
            self.assertEqual(result.returncode, 0, result.stderr)

            holdout_result = _run(
                ["holdout", "--repo", str(holdout_repo), "--state-dir", str(state_holdout), "--lessons", "1"],
                env,
            )
            self.assertEqual(holdout_result.returncode, 0, holdout_result.stderr)
            self.assertIn("PROMOTE", holdout_result.stdout)

            with TrajectoryStore(traj_db) as store:
                self.assertEqual(store.latest_lesson_version(), 1)
                self.assertTrue(store.cut_promoted(1))

            # Now `cdp run --repo <holdout>` (no --lessons flag) picks up v1
            # as the default latest -- the gate this milestone exists for.
            script = tmp / "fake_runner.py"
            script.write_text(
                "import json, sys\n"
                "patch = {'node': 'stub', 'model': 'fake', 'template_version': 'v1', "
                "'kind': 'complete', 'claims': [], 'unknowns': []}\n"
                "json.dump(patch, open(sys.argv[2], 'w'))\n"
            )
            run_result = _run(
                ["run", "--repo", str(holdout_repo), "--state-dir", str(state_holdout), "--wave-all",
                 "--runner-cmd", "%s %s" % (sys.executable, script)],
                env,
            )
            self.assertEqual(run_result.returncode, 0, run_result.stderr)
            self.assertIn("lessons   pinned v1", run_result.stdout)

    def test_holdout_refuses_a_repo_in_the_cuts_own_learning_corpus(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            repo = make_repo(tmp / "repo", "minirepo")
            state = tmp / "state"
            traj_db = tmp / "trajectories.db"
            env = dict(os.environ)
            env["CDP_TRAJECTORY_DB"] = str(traj_db)

            _run(["scan", "--repo", str(repo), "--state-dir", str(state), "--quiet"], env, check=True)

            repo_id = repo_identity(repo)
            with TrajectoryStore(traj_db) as store:
                store.record_leaf_run(
                    run_id="r1", node="root", scope_hash="h1", repo_id=repo_id,
                    model="haiku", scope_shape_key="s1", template_version="1",
                    tier="T2", task_kind="scope", state="folded",
                )
                store.record_promotion(
                    run_id="r1", node="root",
                    promotion={"promotion": "import_channel_hint", "pattern": "com.acme.sdk", "channel": "call"},
                )
                store.cut_lessons()

            result = _run(["holdout", "--repo", str(repo), "--state-dir", str(state), "--lessons", "1"], env)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("own learning corpus", result.stderr)

            with TrajectoryStore(traj_db) as store:
                self.assertFalse(store.cut_promoted(1))


if __name__ == "__main__":
    unittest.main()
