"""`GET /api/fs/list`: read-only folder browser backing the "Open folder..." picker."""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from web.api.app import app


class FsListTest(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.client = TestClient(app)

    def test_lists_sorted_subdirs_skipping_hidden_and_files(self) -> None:
        for name in ("beta", "Alpha", "gamma", ".hidden"):
            (self.root / name).mkdir()
        (self.root / "file.txt").write_text("x")
        body = self.client.get("/api/fs/list", params={"path": str(self.root)}).json()
        self.assertEqual(body["path"], str(self.root))
        self.assertEqual(body["parent"], str(self.root.parent))
        self.assertEqual([e["name"] for e in body["entries"]], ["Alpha", "beta", "gamma"])
        self.assertEqual(body["entries"][0]["path"], str(self.root / "Alpha"))

    def test_git_and_scan_flags(self) -> None:
        (self.root / "repo" / ".git").mkdir(parents=True)
        (self.root / "scanned" / ".cdp").mkdir(parents=True)
        (self.root / "scanned" / ".cdp" / "index.db").write_text("")
        (self.root / "emptycdp" / ".cdp" / "index.db").mkdir(parents=True)
        (self.root / ".git").mkdir()
        body = self.client.get("/api/fs/list", params={"path": str(self.root)}).json()
        self.assertTrue(body["is_git"])
        self.assertFalse(body["has_scan"])
        by = {e["name"]: e for e in body["entries"]}
        self.assertEqual((by["repo"]["is_git"], by["repo"]["has_scan"]), (True, False))
        self.assertEqual((by["scanned"]["is_git"], by["scanned"]["has_scan"]), (False, True))
        self.assertFalse(by["emptycdp"]["has_scan"])

    def test_default_path_is_home(self) -> None:
        (self.root / "child").mkdir()
        with mock.patch.object(Path, "home", return_value=self.root):
            body = self.client.get("/api/fs/list").json()
        self.assertEqual(body["path"], str(self.root))
        self.assertEqual([e["name"] for e in body["entries"]], ["child"])

    def test_root_has_no_parent(self) -> None:
        body = self.client.get("/api/fs/list", params={"path": "/"}).json()
        self.assertIsNone(body["parent"])

    def test_missing_path_404(self) -> None:
        r = self.client.get("/api/fs/list", params={"path": str(self.root / "nope")})
        self.assertEqual(r.status_code, 404)

    def test_file_path_404(self) -> None:
        f = self.root / "f.txt"
        f.write_text("x")
        self.assertEqual(self.client.get("/api/fs/list", params={"path": str(f)}).status_code, 404)

    def test_permission_error_403(self) -> None:
        with mock.patch.object(Path, "iterdir", side_effect=PermissionError):
            r = self.client.get("/api/fs/list", params={"path": str(self.root)})
        self.assertEqual(r.status_code, 403)


if __name__ == "__main__":
    unittest.main()
