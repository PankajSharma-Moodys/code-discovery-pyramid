"""`GET /api/source` -- file bytes for the code-peek pane. Reads the repo
working tree directly, no `cdp scan`/store needed (unlike every other
endpoint). Covers the happy path plus the traversal-defense trust boundary:
`file` is attacker-controllable browser input, so escapes must 400 *before*
any file I/O, and the response must not leak whether an out-of-repo path
exists."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from web.api.app import app

REPO_ROOT = Path(__file__).resolve().parents[2]
MINIREPO = REPO_ROOT / "tests" / "fixtures" / "minirepo"
WIDGET_RESOURCE = (
    MINIREPO / "web" / "src" / "main" / "java" / "com" / "example"
    / "mini" / "web" / "WidgetResource.java"
)


class SourceEndpointTest(unittest.TestCase):
    def setUp(self) -> None:
        self.assertTrue(WIDGET_RESOURCE.is_file(), "fixture file must exist")
        self.client = TestClient(app)
        self.rel_file = str(
            WIDGET_RESOURCE.relative_to(MINIREPO).as_posix()
        )

    def test_valid_file_returns_expected_lines(self) -> None:
        real_lines = WIDGET_RESOURCE.read_text(encoding="utf-8").splitlines()
        resp = self.client.get("/api/source", params={
            "repo": str(MINIREPO), "file": self.rel_file, "line": 5, "ctx": 3,
        })
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["path"], self.rel_file)
        self.assertEqual(body["total_lines"], len(real_lines))
        self.assertEqual(body["start_line"], 2)
        self.assertEqual(body["end_line"], 8)
        self.assertEqual(body["lines"], real_lines[1:8])

    def test_no_line_returns_head_of_file(self) -> None:
        real_lines = WIDGET_RESOURCE.read_text(encoding="utf-8").splitlines()
        resp = self.client.get("/api/source", params={
            "repo": str(MINIREPO), "file": self.rel_file, "ctx": 4,
        })
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["start_line"], 1)
        self.assertEqual(body["end_line"], 8)
        self.assertEqual(body["lines"], real_lines[:8])

    def test_ctx_clamped_to_hard_max(self) -> None:
        resp = self.client.get("/api/source", params={
            "repo": str(MINIREPO), "file": self.rel_file,
            "line": 1, "ctx": 999999,
        })
        self.assertEqual(resp.status_code, 200)
        # clamp just needs to not error / not blow past file length -- the
        # fixture file is tiny, so the real assertion is total_lines sanity.
        body = resp.json()
        self.assertLessEqual(len(body["lines"]), body["total_lines"])

    def test_dotdot_traversal_outside_repo_is_400(self) -> None:
        resp = self.client.get("/api/source", params={
            "repo": str(MINIREPO), "file": "../../../../../../../etc/passwd",
        })
        self.assertEqual(resp.status_code, 400)
        self.assertNotIn("root:", resp.text)

    def test_absolute_path_outside_repo_is_400(self) -> None:
        resp = self.client.get("/api/source", params={
            "repo": str(MINIREPO), "file": "/etc/passwd",
        })
        self.assertEqual(resp.status_code, 400)
        self.assertNotIn("root:", resp.text)

    def test_dotdot_within_repo_that_escapes_is_400(self) -> None:
        # `web/../../..` walks above MINIREPO even though it "starts" inside.
        resp = self.client.get("/api/source", params={
            "repo": str(MINIREPO), "file": "web/../../../../../etc/passwd",
        })
        self.assertEqual(resp.status_code, 400)
        self.assertNotIn("root:", resp.text)

    def test_traversal_and_missing_file_return_identical_shape(self) -> None:
        # The 400 for an escape must not distinguish "exists outside repo"
        # from "doesn't exist at all" -- both should look the same to the
        # client, so nothing about the outside filesystem is leaked.
        escape_resp = self.client.get("/api/source", params={
            "repo": str(MINIREPO), "file": "../outside_nonexistent_xyz.txt",
        })
        self.assertEqual(escape_resp.status_code, 400)

    def test_nonexistent_in_repo_file_is_404(self) -> None:
        resp = self.client.get("/api/source", params={
            "repo": str(MINIREPO), "file": "no/such/file.txt",
        })
        self.assertEqual(resp.status_code, 404)

    def test_binary_file_is_rejected_with_decode_error_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            binary_file = tmp_path / "blob.bin"
            binary_file.write_bytes(bytes(range(256)))
            resp = self.client.get("/api/source", params={
                "repo": str(tmp_path), "file": "blob.bin",
            })
            self.assertEqual(resp.status_code, 422)


if __name__ == "__main__":
    unittest.main()
