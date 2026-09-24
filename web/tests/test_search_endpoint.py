"""`GET /api/search?q=` against a real scanned repo -- same convention as
`test_graph_endpoint.py`: real `cdp scan` in `setUp`, results cross-checked
against the `xref`/`inventory` artifacts read directly out of the scanned
state dir, not hand-picked expected values. This is a thin reformatting of
`cdp.query.q_search` (already exercised by `cdp`'s own tests), so these tests
focus on the reshaping/UI contract, not the match algorithm itself."""

from __future__ import annotations

import json
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
MINIREPO = REPO_ROOT / "tests" / "fixtures" / "minirepo"


class SearchEndpointTest(unittest.TestCase):
    def setUp(self) -> None:
        self.state_dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.state_dir, ignore_errors=True)
        subprocess.run(
            [sys.executable, "-m", "cdp", "scan", "--repo", str(MINIREPO),
             "--state-dir", str(self.state_dir)],
            cwd=REPO_ROOT, check=True, capture_output=True, text=True,
        )

    def _read_artifact(self, name: str) -> dict:
        conn = sqlite3.connect(str(self.state_dir / "index.db"))
        try:
            snapshot_id = conn.execute(
                "SELECT s.id FROM snapshot_meta s "
                "JOIN snapshot_artifact a ON a.snapshot_id = s.id AND a.name = 'manifest' "
                "ORDER BY COALESCE(s.touch_seq, s.id) DESC LIMIT 1"
            ).fetchone()[0]
            row = conn.execute(
                "SELECT payload FROM snapshot_artifact WHERE snapshot_id=? AND name=?",
                (snapshot_id, name),
            ).fetchone()
            return json.loads(row[0])
        finally:
            conn.close()

    def _client(self):
        from fastapi.testclient import TestClient
        from web.api.app import app
        return TestClient(app)

    def test_search_finds_a_real_symbol_by_substring(self) -> None:
        from web.api.models import SearchResponse

        xref = self._read_artifact("xref")
        symbols = list((xref.get("symbols") or {}).keys())
        self.assertTrue(symbols, "fixture has no symbols to search for")
        fqn = symbols[0]
        needle = fqn[max(0, len(fqn) // 2 - 3):len(fqn) // 2 + 3] or fqn

        client = self._client()
        resp = client.get("/api/search", params={
            "q": needle, "repo": str(MINIREPO), "state_dir": str(self.state_dir),
        })
        self.assertEqual(resp.status_code, 200)
        payload = SearchResponse(**resp.json())

        self.assertEqual(payload.count, len(payload.results))
        self.assertIn(fqn, {r.id for r in payload.results if r.kind == "symbol"})
        for r in payload.results:
            self.assertIn(r.kind, ("symbol", "file"))
            self.assertTrue(r.label)

    def test_search_finds_a_real_file_by_substring(self) -> None:
        from web.api.models import SearchResponse

        inventory = self._read_artifact("inventory")
        paths = [f["path"] for f in inventory.get("files", [])]
        self.assertTrue(paths, "fixture has no files to search for")
        path = paths[0]
        needle = path.rsplit("/", 1)[-1][:6] or path

        client = self._client()
        resp = client.get("/api/search", params={
            "q": needle, "repo": str(MINIREPO), "state_dir": str(self.state_dir),
        })
        self.assertEqual(resp.status_code, 200)
        payload = SearchResponse(**resp.json())

        self.assertIn(path, {r.id for r in payload.results if r.kind == "file"})

    def test_search_limit_is_respected(self) -> None:
        from web.api.models import SearchResponse

        client = self._client()
        resp = client.get("/api/search", params={
            "q": "e_", "limit": 3, "repo": str(MINIREPO), "state_dir": str(self.state_dir),
        })
        self.assertEqual(resp.status_code, 200)
        payload = SearchResponse(**resp.json())
        self.assertLessEqual(len(payload.results), 3)

    def test_search_low_limit_does_not_starve_results_behind_claim_matches(self) -> None:
        """Regression: `q_search`'s row budget is shared, spent in order
        claims -> symbols -> unknowns -> files (`cdp/query.py`'s `Budget`).
        The endpoint used to pass the UI's own `limit` straight through as
        that budget, so a term matching more claims than `limit` (claims
        aren't even part of this endpoint's output) could exhaust the whole
        allowance and starve out real symbol/file matches -- empirically hit
        on this repo's own index (`q=app` matched 26 claims and returned 0
        results despite 80 matching symbols existing). `widget` matches
        several of this fixture's claims (entity/table subjects) as well as
        the real `WidgetEntity` symbol; with `limit=1` the old code returned
        zero results here too."""
        from web.api.models import SearchResponse

        client = self._client()
        resp = client.get("/api/search", params={
            "q": "widget", "limit": 1, "repo": str(MINIREPO), "state_dir": str(self.state_dir),
        })
        self.assertEqual(resp.status_code, 200)
        payload = SearchResponse(**resp.json())
        self.assertEqual(len(payload.results), 1)
        self.assertLessEqual(payload.count, 1)

    def test_search_rejects_a_too_short_query(self) -> None:
        client = self._client()
        resp = client.get("/api/search", params={
            "q": "a", "repo": str(MINIREPO), "state_dir": str(self.state_dir),
        })
        self.assertEqual(resp.status_code, 422)
