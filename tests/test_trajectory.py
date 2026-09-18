"""Phase 9 (M9.1) -- the trajectory store, exercised through a real `cdp run`."""

from __future__ import annotations

import contextlib
import io
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import SKILL_ROOT, make_repo

from cdp.store.sqlite_backend import SqliteStore
from cdp.trajectory import LESSONS_HINT_EVERY, TrajectoryStore, elision_regret, scope_shape_key
from cdp.cli import _maybe_print_lessons_hint

RUN_PY = SKILL_ROOT / "run.py"

FAKE_RUNNER = (
    "import json, sys\n"
    "from pathlib import Path\n"
    "patch_path = Path(sys.argv[2])\n"
    "node = patch_path.stem.replace('__', '/')\n"
    "patch = {'schema_version': '1.0.0', 'node': node, 'run_id': 'test-run',\n"
    "         'status': 'complete', 'claims': [],\n"
    "         'unknowns': [{'question': 'what is here?',\n"
    "                       'why_unresolved': 'fake runner never knows',\n"
    "                       'needs': 'needs_human'}]}\n"
    "patch_path.write_text(json.dumps(patch))\n"
)


class TrajectoryStoreUnitTest(unittest.TestCase):
    def test_scope_shape_key_is_deterministic_and_coarse(self):
        a = {"file_count": 3, "by_language": {"java": 3}, "by_role": {"source": 3}}
        b = {"file_count": 4, "by_language": {"java": 4}, "by_role": {"source": 4}}
        self.assertEqual(scope_shape_key(a), scope_shape_key(b))  # both bucket to <=4

    def test_dim_task_kind_is_a_closed_vocabulary(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "trajectories.db"
            with TrajectoryStore(db) as store:
                with self.assertRaises(ValueError):
                    store.dim_task_kind("bogus")

    def test_elision_regret_is_a_subject_intersection(self):
        self.assertTrue(elision_regret(["Foo.bar"], ["Foo.bar"]))
        self.assertFalse(elision_regret(["Foo.bar"], ["Baz.qux"]))
        self.assertFalse(elision_regret([], []))

    def test_finished_run_count_is_global_across_repos(self):
        with tempfile.TemporaryDirectory() as tmp:
            with TrajectoryStore(Path(tmp) / "t.db") as store:
                self.assertEqual(store.finished_run_count(), 0)
                store.record_run_event(run_id="r1", repo_id="repo-a", event="started")
                self.assertEqual(store.finished_run_count(), 0)  # started, not finished
                store.record_run_event(run_id="r1", repo_id="repo-a", event="finished", reason="complete")
                store.record_run_event(run_id="r2", repo_id="repo-b", event="finished", reason="complete")
                self.assertEqual(store.finished_run_count(), 2)  # counts across repos

    def test_migration_adds_m92_columns_to_a_pre_m92_db(self):
        """M9.2 (6.3): a `trajectories.db` written by M9.1's code (no
        `rows_elided`/`entailed`/... columns) must not break -- the new
        columns are added in place, existing rows keep NULL for them."""
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "trajectories.db"
            import sqlite3
            pre_m92_schema = (
                "CREATE TABLE dim_model (id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL);"
                "CREATE TABLE dim_scope_shape (id INTEGER PRIMARY KEY, key TEXT UNIQUE NOT NULL);"
                "CREATE TABLE dim_template (id INTEGER PRIMARY KEY, version TEXT UNIQUE NOT NULL);"
                "CREATE TABLE dim_repo (id INTEGER PRIMARY KEY, repo_id TEXT UNIQUE NOT NULL);"
                "CREATE TABLE dim_tier (id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL);"
                "CREATE TABLE dim_task_kind (id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL);"
                "CREATE TABLE fact_leaf_run (id INTEGER PRIMARY KEY, run_id TEXT NOT NULL, "
                "node TEXT NOT NULL, scope_hash TEXT, repo_dim INTEGER NOT NULL, "
                "model_dim INTEGER NOT NULL, scope_shape_dim INTEGER NOT NULL, "
                "template_dim INTEGER NOT NULL, tier_dim INTEGER NOT NULL, "
                "task_kind_dim INTEGER NOT NULL, state TEXT, attempts INTEGER, "
                "wall_ms INTEGER, patch_hash TEXT, claims_emitted INTEGER, "
                "unknowns_emitted INTEGER, created_at TEXT NOT NULL);"
            )
            conn = sqlite3.connect(db)
            conn.executescript(pre_m92_schema)
            conn.execute(
                "INSERT INTO dim_repo (repo_id) VALUES ('r'); "
            )
            conn.commit()
            conn.close()

            with TrajectoryStore(db) as store:
                store.record_leaf_run(
                    run_id="run-1", node="root", scope_hash="h", repo_id="r2",
                    model=None, scope_shape_key="k", template_version=None,
                    tier=None, task_kind="scope", state="validated",
                    rows_elided=2, tokens_est=500, digest_mode=True,
                    entailed=1, consistent=2, contradicted=0, elision_regret=True,
                )
                rows = store.leaf_runs_for("run-1")
            self.assertEqual(rows[0]["rows_elided"], 2)
            self.assertEqual(rows[0]["elision_regret"], 1)

    def test_routing_prior_is_a_group_by_over_the_star(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "trajectories.db"
            with TrajectoryStore(db) as store:
                for i in range(3):
                    store.record_leaf_run(
                        run_id="run-%d" % i, node="root", scope_hash="h%d" % i,
                        repo_id="r", model=None, scope_shape_key="shape-a",
                        template_version=None, tier=None, task_kind="scope",
                        state="validated", claims_emitted=4, unknowns_emitted=1,
                        tokens_est=100,
                    )
                prior = store.routing_prior("shape-a", "scope")
                self.assertEqual(prior["n"], 3)
                self.assertEqual(prior["avg_claims_emitted"], 4.0)
                self.assertEqual(prior["validated_rate"], 1.0)
                empty = store.routing_prior("no-such-shape", "scope")
                self.assertEqual(empty["n"], 0)
                self.assertIsNone(empty["validated_rate"])


class LessonSetTest(unittest.TestCase):
    """M9.3 (6.7): cut, pin, reproduce -- and R10 surviving the round trip."""

    def _promo(self, section="header"):
        return {"promotion": "prompt_fix", "section": section, "instruction": "do X"}

    def test_no_cut_means_latest_version_is_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            with TrajectoryStore(Path(tmp) / "t.db") as store:
                self.assertIsNone(store.latest_lesson_version())  # 6.7: off for run #1

    def test_cutting_nothing_pending_is_a_noop(self):
        with tempfile.TemporaryDirectory() as tmp:
            with TrajectoryStore(Path(tmp) / "t.db") as store:
                self.assertIsNone(store.cut_lessons())

    def test_cut_numbers_and_freezes_pending_promotions(self):
        with tempfile.TemporaryDirectory() as tmp:
            with TrajectoryStore(Path(tmp) / "t.db") as store:
                store.record_promotion(run_id="r1", node="root/a", promotion=self._promo("header"))
                store.record_promotion(run_id="r1", node="root/b", promotion=self._promo("task"))
                v1 = store.cut_lessons()
                self.assertEqual(v1, 1)
                # M9.3 (6.8): a fresh cut is not "latest" until a holdout A/B
                # promotes it -- it still loads by explicit version.
                self.assertIsNone(store.latest_lesson_version())
                self.assertFalse(store.cut_promoted(1))
                store.promote_cut(1, repo_id="held-out-repo", metric={"t3_rate_before": 0.5, "t3_rate_after": 0.4})
                self.assertTrue(store.cut_promoted(1))
                self.assertEqual(store.latest_lesson_version(), 1)
                lessons = store.load_lessons(1)
                self.assertEqual(len(lessons), 2)
                self.assertEqual([r["node"] for r in lessons], ["root/a", "root/b"])

                # a promotion accepted after the cut is not retroactively in v1
                store.record_promotion(run_id="r2", node="root/c", promotion=self._promo("gaps"))
                self.assertEqual(store.load_lessons(1), lessons)  # v1 is immutable
                v2 = store.cut_lessons()
                self.assertEqual(v2, 2)
                self.assertEqual(len(store.load_lessons(2)), 1)

    def test_unpromote_reverts_promoted_flag_but_keeps_holdout_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            with TrajectoryStore(Path(tmp) / "t.db") as store:
                store.record_promotion(run_id="r1", node="root/a", promotion=self._promo())
                v1 = store.cut_lessons()
                store.promote_cut(v1, repo_id="held-out-repo", metric={"t3_rate_before": 0.5})
                self.assertTrue(store.cut_promoted(v1))
                self.assertTrue(store.unpromote_cut(v1, reason="regressed on repo X"))
                self.assertFalse(store.cut_promoted(v1))
                self.assertIsNone(store.latest_lesson_version())
                # R4: the promotion record itself is not erased, only reverted.
                row = store._conn.execute(
                    "SELECT holdout_repo, unpromote_reason FROM lesson_cut WHERE version=?", (v1,)
                ).fetchone()
                self.assertEqual(row[0], "held-out-repo")
                self.assertEqual(row[1], "regressed on repo X")
                # an explicit --lessons pin is unaffected by promoted state either way
                self.assertEqual(len(store.load_lessons(v1)), 1)

    def test_unpromote_falls_back_to_next_highest_promoted_cut(self):
        with tempfile.TemporaryDirectory() as tmp:
            with TrajectoryStore(Path(tmp) / "t.db") as store:
                store.record_promotion(run_id="r1", node="root/a", promotion=self._promo())
                v1 = store.cut_lessons()
                store.promote_cut(v1, repo_id="repo-a", metric={})
                store.record_promotion(run_id="r2", node="root/b", promotion=self._promo())
                v2 = store.cut_lessons()
                store.promote_cut(v2, repo_id="repo-b", metric={})
                self.assertEqual(store.latest_lesson_version(), v2)
                store.unpromote_cut(v2)
                self.assertEqual(store.latest_lesson_version(), v1)  # falls back, not to None
                store.unpromote_cut(v1)
                self.assertIsNone(store.latest_lesson_version())  # no promoted cut remains

    def test_unpromote_a_cut_that_is_not_promoted_is_a_noop(self):
        with tempfile.TemporaryDirectory() as tmp:
            with TrajectoryStore(Path(tmp) / "t.db") as store:
                store.record_promotion(run_id="r1", node="root/a", promotion=self._promo())
                v1 = store.cut_lessons()
                self.assertFalse(store.unpromote_cut(v1))  # never promoted
                self.assertFalse(store.unpromote_cut(999))  # doesn't even exist

    def test_reproduces_byte_identically_on_repeated_load(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "t.db"
            with TrajectoryStore(db) as store:
                store.record_promotion(run_id="r1", node="root/a", promotion=self._promo())
                v = store.cut_lessons()
            # a fresh process/connection against the same file sees the same cut
            with TrajectoryStore(db) as store:
                first = store.load_lessons(v)
                second = store.load_lessons(v)
                self.assertEqual(first, second)

    def test_r10_a_claim_shaped_payload_cannot_survive_the_cut_load_round_trip(self):
        """The persistence layer must not be a second place a claim-shaped
        field could sneak in -- round-tripping a validated promotion through
        cut/load must yield the exact same closed schema, no more keys."""
        with tempfile.TemporaryDirectory() as tmp:
            with TrajectoryStore(Path(tmp) / "t.db") as store:
                promo = self._promo()
                store.record_promotion(run_id="r1", node="root/a", promotion=promo)
                v = store.cut_lessons()
                loaded = store.load_lessons(v)[0]["payload"]
                self.assertEqual(set(loaded.keys()), set(promo.keys()))
                for forbidden in ("subject", "anchor", "evidence", "kind", "claim"):
                    self.assertNotIn(forbidden, loaded)


class LessonsHintTest(unittest.TestCase):
    """User decision: no auto-cut cadence -- instead, every LESSONS_HINT_EVERY
    finished runs, nudge that lessons are pending and name the cut command."""

    def _promo(self):
        return {"promotion": "prompt_fix", "section": "header", "instruction": "do X"}

    def test_silent_off_cadence_even_with_pending_promotions(self):
        with tempfile.TemporaryDirectory() as tmp:
            with TrajectoryStore(Path(tmp) / "t.db") as store:
                store.record_promotion(run_id="r1", node="root/a", promotion=self._promo())
                for i in range(LESSONS_HINT_EVERY - 1):
                    store.record_run_event(run_id="r%d" % i, repo_id="repo", event="finished", reason="complete")
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    _maybe_print_lessons_hint(store)
                self.assertEqual(buf.getvalue(), "")

    def test_silent_on_cadence_with_nothing_pending(self):
        with tempfile.TemporaryDirectory() as tmp:
            with TrajectoryStore(Path(tmp) / "t.db") as store:
                for i in range(LESSONS_HINT_EVERY):
                    store.record_run_event(run_id="r%d" % i, repo_id="repo", event="finished", reason="complete")
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    _maybe_print_lessons_hint(store)
                self.assertEqual(buf.getvalue(), "")

    def test_hints_on_cadence_with_pending_promotions_and_names_the_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            with TrajectoryStore(Path(tmp) / "t.db") as store:
                store.record_promotion(run_id="r1", node="root/a", promotion=self._promo())
                store.record_promotion(run_id="r1", node="root/b", promotion=self._promo())
                for i in range(LESSONS_HINT_EVERY):
                    store.record_run_event(run_id="r%d" % i, repo_id="repo", event="finished", reason="complete")
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    _maybe_print_lessons_hint(store)
                out = buf.getvalue()
                self.assertIn("2 promotion(s) pending", out)
                self.assertIn("cdp lessons cut", out)


class HoldoutSplitTest(unittest.TestCase):
    """M9.3 (6.8): "learn on repos A-E, benchmark on F -- verify the split is
    real." `learned_repos_for_cut` is that verification."""

    def test_learned_repos_for_cut_names_the_repo_a_promotion_came_from(self):
        with tempfile.TemporaryDirectory() as tmp:
            with TrajectoryStore(Path(tmp) / "t.db") as store:
                store.record_leaf_run(
                    run_id="r1", node="root/a", scope_hash="h1", repo_id="repo-a",
                    model="haiku", scope_shape_key="s1", template_version="1",
                    tier="T2", task_kind="scope", state="folded",
                )
                store.record_promotion(
                    run_id="r1", node="root/a",
                    promotion={"promotion": "import_channel_hint", "pattern": "com.acme.sdk", "channel": "call"},
                )
                v = store.cut_lessons()
                self.assertEqual(store.learned_repos_for_cut(v), {"repo-a"})
                self.assertNotIn("repo-f", store.learned_repos_for_cut(v))


class RealRunPopulatesTrajectoryTest(unittest.TestCase):
    def test_fact_tables_populate_from_a_real_run_and_survive_workspace_deletion(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(Path(tmp))
            state = Path(tmp) / "state"
            traj_db = Path(tmp) / "trajectories.db"
            script = Path(tmp) / "fake_runner.py"
            script.write_text(FAKE_RUNNER)

            env = dict(os.environ)
            env["CDP_TRAJECTORY_DB"] = str(traj_db)

            subprocess.run(
                [sys.executable, str(RUN_PY), "scan", "--repo", str(repo),
                 "--state-dir", str(state), "--quiet"],
                check=True, capture_output=True, env=env,
            )
            subprocess.run(
                [sys.executable, str(RUN_PY), "run", "--repo", str(repo), "--state-dir", str(state),
                 "--wave-all", "--runner-cmd", "%s %s" % (sys.executable, script)],
                check=True, capture_output=True, text=True, env=env,
            )

            backend = SqliteStore(state / "index.db")
            run_id = backend.read_artifact("manifest").get("run_id")
            backend.close()

            self.assertTrue(traj_db.exists(), "trajectory DB was not created")
            store = TrajectoryStore(traj_db)
            leaf_rows = store.leaf_runs_for(run_id)
            events = store.events_for(run_id)
            store.close()

            self.assertTrue(leaf_rows, "expected at least one fact_leaf_run row from the real run")
            self.assertTrue(all(r["state"] == "validated" for r in leaf_rows), leaf_rows)
            event_names = [e["event"] for e in events]
            self.assertIn("started", event_names)
            self.assertIn("finished", event_names)

            # 0.17's whole reason for a second file: deleting the workspace
            # store must not touch the trajectory DB.
            import shutil
            shutil.rmtree(state)
            self.assertTrue(traj_db.exists(), "trajectory DB deleted along with the workspace store")
            store = TrajectoryStore(traj_db)
            self.assertEqual(store.leaf_runs_for(run_id), leaf_rows)
            store.close()


if __name__ == "__main__":
    unittest.main()
