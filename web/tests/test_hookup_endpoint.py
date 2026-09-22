"""Agent-layer hookup tab backend (`WEB_RESEARCH.md` §4 item 1). `preview`
and `mcp-tools` are read-only queries over `cdp.cli`/`mcp_server.schemas`
constants; `install` drives a real `cdp install` subprocess against a scratch
target dir; `liveness` drives a real `cdp doctor` subprocess with a fake
`--runner-cmd` script that writes a fixed, schema-valid, empty-claims patch
(`cdp/runner.py`'s `command + [prompt_path, patch_path]` protocol) -- schema
validity is `collect`'s job, not the runner's, so an empty-claims patch is a
legitimate `schema_valid=True` result, sufficient to prove the endpoint/job/
poll wiring without needing a real model."""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
MINIREPO = REPO_ROOT / "tests" / "fixtures" / "minirepo"

FAKE_RUNNER_SCRIPT = """
import json
import sys

patch_path = sys.argv[2]
patch = {
    "schema_version": "1.0.0",
    "node": "root",
    "run_id": "doctor-test",
    "status": "complete",
}
with open(patch_path, "w", encoding="utf-8") as fh:
    json.dump(patch, fh)
"""


class HookupEndpointTest(unittest.TestCase):
    def setUp(self) -> None:
        self.state_dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.state_dir, ignore_errors=True)
        subprocess.run(
            [sys.executable, "-m", "cdp", "scan", "--repo", str(MINIREPO),
             "--state-dir", str(self.state_dir)],
            cwd=REPO_ROOT, check=True, capture_output=True, text=True,
        )
        self.target_dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.target_dir, ignore_errors=True)

    def _client(self):
        from fastapi.testclient import TestClient
        from web.api.app import app
        return TestClient(app)

    def _token(self) -> str:
        from web.api import auth as auth_mod
        return auth_mod.WEB_TOKEN

    # ------------------------------------------------------------- preview

    def test_preview_claude_code_lists_leaf_agent_file(self) -> None:
        from web.api.models import InstallPreviewResponse

        resp = self._client().get("/api/hookup/preview", params={
            "target": str(self.target_dir), "framework": "claude-code",
        })
        self.assertEqual(resp.status_code, 200, resp.text)
        payload = InstallPreviewResponse(**resp.json())
        self.assertTrue(payload.skill_members)
        self.assertIsNotNone(payload.leaf_agent_file)
        self.assertIn("cdp-leaf.md", payload.leaf_agent_file)
        self.assertIsNone(payload.framework_note)
        self.assertEqual(payload.agents_md_action, "written")

    def test_preview_langgraph_has_framework_note_and_no_leaf_file(self) -> None:
        from web.api.models import InstallPreviewResponse

        resp = self._client().get("/api/hookup/preview", params={
            "target": str(self.target_dir), "framework": "langgraph",
        })
        self.assertEqual(resp.status_code, 200, resp.text)
        payload = InstallPreviewResponse(**resp.json())
        self.assertIsNone(payload.leaf_agent_file)
        self.assertIsNotNone(payload.framework_note)
        self.assertIn("langgraph", payload.framework_note)

    def test_preview_kept_when_agents_md_already_exists(self) -> None:
        from web.api.models import InstallPreviewResponse

        (self.target_dir / "AGENTS.md").write_text("custom\n", encoding="utf-8")
        resp = self._client().get("/api/hookup/preview", params={
            "target": str(self.target_dir), "framework": "none",
        })
        self.assertEqual(resp.status_code, 200, resp.text)
        payload = InstallPreviewResponse(**resp.json())
        self.assertEqual(payload.agents_md_action, "kept")

    def test_preview_unknown_target_400s(self) -> None:
        resp = self._client().get("/api/hookup/preview", params={
            "target": str(self.target_dir / "does-not-exist"), "framework": "claude-code",
        })
        self.assertEqual(resp.status_code, 400)

    def test_preview_unknown_framework_400s(self) -> None:
        resp = self._client().get("/api/hookup/preview", params={
            "target": str(self.target_dir), "framework": "bogus",
        })
        self.assertEqual(resp.status_code, 400)

    # -------------------------------------------------------------- install

    def test_install_missing_token_is_rejected(self) -> None:
        resp = self._client().post("/api/hookup/install", params={
            "target": str(self.target_dir), "framework": "none",
        })
        self.assertEqual(resp.status_code, 403)

    def test_install_wrong_token_is_rejected(self) -> None:
        resp = self._client().post(
            "/api/hookup/install",
            params={"target": str(self.target_dir), "framework": "none"},
            headers={"X-CDP-Web-Token": "not-the-token"},
        )
        self.assertEqual(resp.status_code, 403)

    def test_install_copies_skill_and_leaf_agent_and_is_idempotent(self) -> None:
        from web.api.models import InstallResultResponse

        resp = self._client().post(
            "/api/hookup/install",
            params={"target": str(self.target_dir), "framework": "claude-code"},
            headers={"X-CDP-Web-Token": self._token()},
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        payload = InstallResultResponse(**resp.json())
        self.assertEqual(payload.returncode, 0, payload.stderr)
        self.assertTrue((self.target_dir / ".claude" / "skills" / "cdp").is_dir())
        self.assertTrue((self.target_dir / ".claude" / "agents" / "cdp-leaf.md").is_file())

        # rerun: replace-wholesale contract, not an error
        resp2 = self._client().post(
            "/api/hookup/install",
            params={"target": str(self.target_dir), "framework": "claude-code"},
            headers={"X-CDP-Web-Token": self._token()},
        )
        self.assertEqual(resp2.status_code, 200, resp2.text)
        payload2 = InstallResultResponse(**resp2.json())
        self.assertEqual(payload2.returncode, 0, payload2.stderr)

    # ------------------------------------------------------------ mcp-tools

    def test_mcp_tools_match_schema_source_of_truth(self) -> None:
        from mcp_server.schemas import TOOL_SCHEMAS
        from web.api.models import McpToolsResponse

        resp = self._client().get("/api/hookup/mcp-tools")
        self.assertEqual(resp.status_code, 200, resp.text)
        payload = McpToolsResponse(**resp.json())
        self.assertEqual({t.name for t in payload.tools}, set(TOOL_SCHEMAS))
        self.assertIn("mcp_server.server", payload.client_config)

    # ------------------------------------------------------------- liveness

    def test_liveness_missing_token_is_rejected(self) -> None:
        resp = self._client().post("/api/hookup/liveness", params={
            "target": str(MINIREPO), "state_dir": str(self.state_dir),
            "runner_cmd": "true", "model": "fake-model",
        })
        self.assertEqual(resp.status_code, 403)

    def test_liveness_unscanned_target_404s(self) -> None:
        unscanned_state_dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, unscanned_state_dir, ignore_errors=True)
        resp = self._client().post(
            "/api/hookup/liveness",
            params={
                "target": str(MINIREPO), "state_dir": str(unscanned_state_dir),
                "runner_cmd": "true", "model": "fake-model",
            },
            headers={"X-CDP-Web-Token": self._token()},
        )
        self.assertEqual(resp.status_code, 404)

    def test_liveness_happy_path_writes_doctor_report(self) -> None:
        from web.api.models import JobResponse, JobStatusResponse, DoctorResponse

        runner_script = self.state_dir / "fake_runner.py"
        runner_script.write_text(FAKE_RUNNER_SCRIPT, encoding="utf-8")
        runner_cmd = "%s %s" % (sys.executable, runner_script)

        resp = self._client().post(
            "/api/hookup/liveness",
            params={
                "target": str(MINIREPO), "state_dir": str(self.state_dir),
                "runner_cmd": runner_cmd, "model": "fake-model", "timeout": 30,
            },
            headers={"X-CDP-Web-Token": self._token()},
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        job = JobResponse(**resp.json())
        self.assertEqual(job.kind, "doctor")

        deadline = time.monotonic() + 20
        status: JobStatusResponse
        while True:
            status_resp = self._client().get("/api/job/%s" % job.job_id)
            self.assertEqual(status_resp.status_code, 200, status_resp.text)
            status = JobStatusResponse(**status_resp.json())
            if not status.running:
                break
            if time.monotonic() > deadline:
                self.fail("doctor job did not finish within 20s")
            time.sleep(0.2)
        self.assertEqual(status.returncode, 0)

        doctor_resp = self._client().get("/api/doctor", params={
            "repo": str(MINIREPO), "state_dir": str(self.state_dir),
        })
        self.assertEqual(doctor_resp.status_code, 200, doctor_resp.text)
        doctor_payload = DoctorResponse(**doctor_resp.json())
        self.assertIn("fake-model", doctor_payload.models)

    def test_job_status_unknown_id_404s(self) -> None:
        resp = self._client().get("/api/job/does-not-exist")
        self.assertEqual(resp.status_code, 404)


if __name__ == "__main__":
    unittest.main()
