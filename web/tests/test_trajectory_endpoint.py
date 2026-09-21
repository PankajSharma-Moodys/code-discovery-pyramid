"""`GET /api/trajectory?shape=` -- reads `~/.cdp/trajectories.db`
(`cdp/trajectory.py`), overridden via `CDP_TRAJECTORY_DB` so this test never
touches the real corpus. Rows are written via the real `TrajectoryStore.
record_leaf_run` (the actual write path `cdp run` uses), then read back
through `ReadOnlyTrajectoryConnection`/`GET /api/trajectory` -- this is the
"read what was really written" test the plan calls for, not hand-built JSON."""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from cdp.trajectory import TrajectoryStore


class TrajectoryEndpointTest(unittest.TestCase):
    def setUp(self) -> None:
        self.db_dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.db_dir, ignore_errors=True)
        self.db_path = self.db_dir / "trajectories.db"

        self.env_patch = mock.patch.dict(
            "os.environ", {"CDP_TRAJECTORY_DB": str(self.db_path)},
        )
        self.env_patch.start()
        self.addCleanup(self.env_patch.stop)

        store = TrajectoryStore(self.db_path)
        try:
            store.record_leaf_run(
                run_id="run-1", node="scopes/a", scope_hash="h1", repo_id="repo-x",
                model="model-a", scope_shape_key="files<=4|langs=py|roles=source",
                template_version="v1", tier="t1", task_kind="scope", state="folded",
                attempts=1, wall_ms=1000, claims_emitted=3, unknowns_emitted=1,
            )
            store.record_leaf_run(
                run_id="run-1", node="scopes/b", scope_hash="h2", repo_id="repo-x",
                model="model-a", scope_shape_key="files<=16|langs=py|roles=test",
                template_version="v1", tier="t1", task_kind="scope", state="folded",
                attempts=1, wall_ms=2000, claims_emitted=1, unknowns_emitted=0,
            )
        finally:
            store._conn.close()

    def _client(self):
        from fastapi.testclient import TestClient
        from web.api.app import app
        return TestClient(app)

    def test_no_shape_filter_returns_all_rows(self) -> None:
        from web.api.models import TrajectoryResponse

        resp = self._client().get("/api/trajectory")
        self.assertEqual(resp.status_code, 200)
        payload = TrajectoryResponse(**resp.json())
        self.assertEqual(len(payload.runs), 2)
        self.assertEqual({r.node for r in payload.runs}, {"scopes/a", "scopes/b"})

    def test_shape_filter_narrows_to_one_row(self) -> None:
        from web.api.models import TrajectoryResponse

        resp = self._client().get("/api/trajectory", params={
            "shape": "files<=4|langs=py|roles=source",
        })
        self.assertEqual(resp.status_code, 200)
        payload = TrajectoryResponse(**resp.json())
        self.assertEqual(len(payload.runs), 1)
        self.assertEqual(payload.runs[0].node, "scopes/a")
        self.assertEqual(payload.runs[0].repo_id, "repo-x")
        self.assertEqual(payload.runs[0].model, "model-a")

    def test_no_corpus_yet_404s(self) -> None:
        with mock.patch.dict("os.environ", {"CDP_TRAJECTORY_DB": str(self.db_dir / "nope.db")}):
            resp = self._client().get("/api/trajectory")
        self.assertEqual(resp.status_code, 404)


if __name__ == "__main__":
    unittest.main()
