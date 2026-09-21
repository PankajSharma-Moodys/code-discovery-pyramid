"""`GET /api/events` -- SSE progress stream over `snapshot_task`/`snapshot_run`
(`cdp/store/sqlite_backend.py`). The run is written already-`complete` before
the request so the stream emits exactly one `task` batch, one `wave` summary,
and a `complete` event, then returns -- this exercises the real end condition
(`snapshot_run.status == "complete"`) rather than needing a live `cdp run`
process or a multi-second real-time wait."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
MINIREPO = REPO_ROOT / "tests" / "fixtures" / "minirepo"


class EventsEndpointTest(unittest.TestCase):
    def setUp(self) -> None:
        self.state_dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.state_dir, ignore_errors=True)
        subprocess.run(
            [sys.executable, "-m", "cdp", "scan", "--repo", str(MINIREPO),
             "--state-dir", str(self.state_dir)],
            cwd=REPO_ROOT, check=True, capture_output=True, text=True,
        )

        from cdp.store.sqlite_backend import SqliteStore

        store = SqliteStore(self.state_dir / "index.db")
        try:
            manifest = store.read_artifact("manifest")
            self.run_id = str(manifest["run_id"])
            store.begin_run(self.run_id)
            store.upsert_task(self.run_id, "scope-a", state="complete", attempts=1)
            store.finish_run(self.run_id, "complete")
        finally:
            store.close()

    def _client(self):
        from fastapi.testclient import TestClient
        from web.api.app import app
        return TestClient(app)

    def _parse_sse(self, body: str) -> list:
        events = []
        event_type, data = None, None
        for line in body.splitlines():
            if line.startswith("event:"):
                event_type = line.split(":", 1)[1].strip()
            elif line.startswith("data:"):
                data = line.split(":", 1)[1].strip()
            elif line == "" and event_type is not None:
                events.append((event_type, json.loads(data) if data else None))
                event_type, data = None, None
        return events

    def test_stream_emits_task_wave_then_complete(self) -> None:
        client = self._client()
        with client.stream("GET", "/api/events", params={
            "repo": str(MINIREPO), "state_dir": str(self.state_dir),
        }) as resp:
            self.assertEqual(resp.status_code, 200)
            body = "".join(resp.iter_text())

        events = self._parse_sse(body)
        kinds = [e[0] for e in events]
        self.assertIn("task", kinds)
        self.assertIn("wave", kinds)
        self.assertEqual(kinds[-1], "complete")

        task_event = next(e for e in events if e[0] == "task")[1]
        self.assertEqual(task_event["scope_hash"], "scope-a")
        self.assertEqual(task_event["state"], "complete")

        wave_event = next(e for e in events if e[0] == "wave")[1]
        self.assertEqual(wave_event, {"done": 1, "total": 1})

    def test_never_scanned_state_dir_404s(self) -> None:
        empty_dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, empty_dir, ignore_errors=True)
        client = self._client()
        resp = client.get("/api/events", params={
            "repo": str(MINIREPO), "state_dir": str(empty_dir),
        })
        self.assertEqual(resp.status_code, 404)


if __name__ == "__main__":
    unittest.main()
