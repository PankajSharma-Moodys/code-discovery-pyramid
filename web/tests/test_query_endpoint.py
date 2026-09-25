"""`GET /api/query` and `GET /api/trace` against a real scanned repo -- ground
truth, not hand-built fixtures, same posture as `test_status_contract.py`.
Cross-checks the API response against `cdp query <kind> --json` subprocess
output for the CLI-parity guarantee `WEB_RESEARCH.md` §7.2.1 requires."""

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


class QueryEndpointTest(unittest.TestCase):
    def setUp(self) -> None:
        self.state_dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.state_dir, ignore_errors=True)
        subprocess.run(
            [sys.executable, "-m", "cdp", "scan", "--repo", str(MINIREPO),
             "--state-dir", str(self.state_dir)],
            cwd=REPO_ROOT, check=True, capture_output=True, text=True,
        )

    def _cli_json(self, *args: str) -> dict:
        proc = subprocess.run(
            [sys.executable, "-m", "cdp", "query", *args, "--repo", str(MINIREPO),
             "--state-dir", str(self.state_dir), "--json"],
            cwd=REPO_ROOT, check=True, capture_output=True, text=True,
        )
        return json.loads(proc.stdout)

    def _client(self):
        from fastapi.testclient import TestClient

        from web.api.app import app

        return TestClient(app)

    def _params(self, **extra):
        return {"repo": str(MINIREPO), "state_dir": str(self.state_dir), **extra}

    def test_symbol_query_matches_cli(self) -> None:
        cli = self._cli_json("symbol", "Widget")
        resp = self._client().get("/api/query", params=self._params(kind="symbol", term="Widget"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), cli)

    def test_unknowns_query_matches_cli(self) -> None:
        cli = self._cli_json("unknowns")
        resp = self._client().get("/api/query", params=self._params(kind="unknowns"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), cli)

    def test_trace_query_matches_cli(self) -> None:
        # Find a real dataflow source to trace from this fixture's own paths.
        paths = self._cli_json("paths")
        if not paths.get("paths"):
            self.skipTest("fixture scan produced no dataflow paths to trace")
        entry = paths["paths"][0]["trigger"]

        cli = self._cli_json("trace", entry)
        resp = self._client().get("/api/query", params=self._params(kind="trace", term=entry))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), cli)

        resp2 = self._client().get("/api/trace", params=self._params(entry=entry))
        self.assertEqual(resp2.status_code, 200)
        self.assertEqual(resp2.json(), cli)

    def test_unknown_kind_is_400(self) -> None:
        resp = self._client().get("/api/query", params=self._params(kind="not_a_real_kind"))
        self.assertEqual(resp.status_code, 400)

    def test_never_scanned_state_dir_is_404(self) -> None:
        empty_dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, empty_dir, ignore_errors=True)
        resp = self._client().get("/api/query", params={
            "repo": str(MINIREPO), "state_dir": str(empty_dir), "kind": "stats",
        })
        self.assertEqual(resp.status_code, 404)

    def test_trace_without_entry_or_from_to_is_400(self) -> None:
        resp = self._client().get("/api/trace", params=self._params())
        self.assertEqual(resp.status_code, 400)

    def test_trace_by_entry_is_200_not_500(self) -> None:
        # Regression test: `get_trace` calls `get_query` as a plain in-process
        # function call, which previously left `exclude_role` unbound to its
        # FastAPI `Query(...)` default (an unresolved sentinel object, not
        # `None`) rather than the real value FastAPI's own request pipeline
        # would have resolved it to -- `q_trace`'s `exclude_role` truthy-guard
        # then crashed on `not in <Query object>`. `/v1/widgets` is a known
        # route entry point in this fixture (`tests/test_trace.py`), so this
        # doesn't depend on the fixture producing any dataflow `paths`
        # (unlike `test_trace_query_matches_cli`, which skips when it doesn't).
        resp = self._client().get("/api/trace", params=self._params(entry="/v1/widgets"))
        self.assertEqual(resp.status_code, 200)
        self.assertIn("found", resp.json())


if __name__ == "__main__":
    unittest.main()
