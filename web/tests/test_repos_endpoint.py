"""`GET /api/repos` (`WEB_RESEARCH.md` §7.1 item 5): every state dir this
machine's `cdp.store.registry` knows about, with per-repo freshness (current
git HEAD vs. the pinned snapshot's `as_of` commit).

Registry-isolation note: `cdp.store.registry.REGISTRY_PATH` is a hardcoded
`Path.home() / ".cdp" / "config.toml"` -- there is no `CDP_REGISTRY`-style env
var override in `registry.py` (only `CDP_STORE` exists, for the *store* path,
not the registry file). A `cdp scan` subprocess with an unmodified `HOME`
would therefore register straight into the real machine's `~/.cdp/config.toml`
-- a real bug/gap in `registry.py`, not something this test silently works
around. Instead: the `cdp scan` subprocess is given a temp `$HOME`, so its own
`Path.home()` (and therefore its own `REGISTRY_PATH`) resolves under the temp
dir; this test process then points `registry_mod.REGISTRY_PATH` (read
dynamically per-call, not cached, by `web/api/app.py`) at that same temp
file via `mock.patch.object`, so the running `TestClient` reads the same
registry the subprocess wrote -- without ever touching the real one."""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[2]
MINIREPO = REPO_ROOT / "tests" / "fixtures" / "minirepo"


class ReposEndpointTest(unittest.TestCase):
    def setUp(self) -> None:
        self.state_dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.state_dir, ignore_errors=True)

        self.fake_home = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.fake_home, ignore_errors=True)
        self.registry_path = self.fake_home / ".cdp" / "config.toml"

        import os

        env = dict(os.environ)
        env["HOME"] = str(self.fake_home)
        # `cmd_scan` only calls `registry_mod.register(...)` when neither
        # `--in-repo` nor `--state-dir` was passed explicitly (`cdp/cli.py`,
        # M2.6 comment on `cmd_scan`) -- an explicit `--state-dir` is the
        # whole point of never touching the registry from a test that always
        # passes one. So this scan is pointed at a deterministic state dir
        # via `CDP_STORE` instead (still wins the same fallback chain, but
        # *with* registration), leaving `--state-dir` unset.
        env["CDP_STORE"] = str(self.state_dir)
        subprocess.run(
            [sys.executable, "-m", "cdp", "scan", "--repo", str(MINIREPO)],
            cwd=REPO_ROOT, check=True, capture_output=True, text=True, env=env,
        )

        from cdp.store import registry as registry_mod

        self.registry_patch = mock.patch.object(registry_mod, "REGISTRY_PATH", self.registry_path)
        self.registry_patch.start()
        self.addCleanup(self.registry_patch.stop)

        # Ground truth: read the same artifacts directly for comparison.
        from web.api.store_reader import ReadOnlyConnection

        conn = ReadOnlyConnection(self.state_dir / "index.db")
        snapshot_id = conn.latest_pinned_snapshot()
        self.inventory = conn.read_artifact(snapshot_id, "inventory")
        conn.close()

    def test_registry_file_was_written_under_fake_home(self) -> None:
        # Confirms the isolation actually worked -- the real `~/.cdp/config.toml`
        # was never touched by this test.
        self.assertTrue(self.registry_path.is_file())

    def test_scanned_repo_appears_with_correct_head_and_as_of(self) -> None:
        from fastapi.testclient import TestClient

        from web.api.app import app

        client = TestClient(app)
        resp = client.get("/api/repos")
        self.assertEqual(resp.status_code, 200)
        payload = resp.json()

        from web.api.models import ReposResponse

        ReposResponse(**payload)  # raises on schema mismatch

        matches = [
            r for r in payload["repos"]
            if Path(r["state_dir"]) == self.state_dir.resolve()
        ]
        self.assertEqual(len(matches), 1, payload["repos"])
        row = matches[0]

        expected_as_of = self.inventory.get("head")
        expected_repo_path = self.inventory.get("repo")

        self.assertIsNone(row["error"])
        self.assertEqual(row["as_of_commit"], expected_as_of)
        self.assertEqual(row["repo_path"], expected_repo_path)
        # `minirepo` lives inside this checkout's own git working tree, so its
        # "current HEAD" is this repo's HEAD -- same value the scan pinned.
        self.assertEqual(row["head"], expected_as_of)
        self.assertEqual(row["behind"], 0)

    def test_broken_state_dir_gets_error_row_not_500(self) -> None:
        from cdp.store import registry as registry_mod
        from fastapi.testclient import TestClient

        from web.api.app import app

        vanished = Path(tempfile.mkdtemp())
        shutil.rmtree(vanished)  # registered, but the dir no longer exists
        registry_mod.register("vanished-repo-id", vanished)

        client = TestClient(app)
        resp = client.get("/api/repos")
        self.assertEqual(resp.status_code, 200)
        payload = resp.json()

        matches = [r for r in payload["repos"] if r["repo_id"] == "vanished-repo-id"]
        self.assertEqual(len(matches), 1, payload["repos"])
        row = matches[0]
        self.assertIsNotNone(row["error"])
        self.assertIsNone(row["head"])
        self.assertIsNone(row["as_of_commit"])


if __name__ == "__main__":
    unittest.main()
