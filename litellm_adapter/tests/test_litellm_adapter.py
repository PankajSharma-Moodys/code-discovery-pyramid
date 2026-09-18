"""`litellm_adapter`'s own test suite -- run by `make check-interfaces`, never
by `make check` (see `mcp_server/tests/test_mcp_server.py` for why)."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import litellm_adapter  # noqa: E402
from cdp.runner import RunResult  # noqa: E402


class LiteLLMAdapterScaffoldTest(unittest.TestCase):
    def test_package_imports(self) -> None:
        self.assertTrue(litellm_adapter.__doc__)

    def test_real_litellm_package_is_optional(self) -> None:
        try:
            import litellm  # noqa: F401
        except ImportError:
            self.skipTest("`litellm` not installed -- pip install cdp[litellm]")


class CompleteIsolationTest(unittest.TestCase):
    """`_complete` is the only function that touches the `litellm` SDK; it
    must fail with a clear, actionable error when the SDK is absent, per
    the `mcp_server.server.create_server` precedent."""

    def test_raises_clear_import_error_when_litellm_missing(self) -> None:
        try:
            import litellm  # noqa: F401
        except ImportError:
            pass
        else:
            self.skipTest("litellm is installed in this environment")
        with self.assertRaises(ImportError) as ctx:
            litellm_adapter._complete("fake-model", "hello")
        self.assertIn("cdp[litellm]", str(ctx.exception))


class LiteLLMRunnerTest(unittest.TestCase):
    """Everything below is fully tested without the `litellm` SDK present,
    by stubbing `_complete` -- the one function that touches it."""

    def setUp(self) -> None:
        self.tmp = Path(self._get_tmp_dir())
        self.prompt_path = self.tmp / "prompt.md"
        self.patch_path = self.tmp / "patch.json"
        self.prompt_path.write_text("scope prompt text", encoding="utf-8")

    def _get_tmp_dir(self) -> str:
        import tempfile
        d = tempfile.mkdtemp(prefix="litellm-adapter-test-")
        self.addCleanup(lambda: __import__("shutil").rmtree(d, ignore_errors=True))
        return d

    def _fake_response(self, content: str, total_tokens=42):
        message = SimpleNamespace(content=content)
        choice = SimpleNamespace(message=message)
        usage = SimpleNamespace(total_tokens=total_tokens)
        return SimpleNamespace(choices=[choice], usage=usage)

    def test_writes_schema_shaped_patch_on_success(self) -> None:
        patch = {"claims": [{"subject": "X", "statement": "Y", "kind": "naming", "anchor": "f.py:1"}]}
        with mock.patch.object(litellm_adapter, "_complete",
                                return_value=self._fake_response(json.dumps(patch))):
            result = litellm_adapter.LiteLLMRunner("fake-model").run(self.prompt_path, self.patch_path)
        self.assertTrue(result.ok)
        self.assertEqual(result.tokens, 42)
        self.assertEqual(json.loads(self.patch_path.read_text(encoding="utf-8")), patch)

    def test_unparseable_content_is_ok_but_writes_no_patch(self) -> None:
        """Matches runner.py's own contract: a well-formed-but-wrong patch is
        collect's problem, and no patch on disk is yield collapse for
        `cdp run` to classify -- neither is a runner-level failure."""
        with mock.patch.object(litellm_adapter, "_complete",
                                return_value=self._fake_response("not json at all")):
            result = litellm_adapter.LiteLLMRunner("fake-model").run(self.prompt_path, self.patch_path)
        self.assertTrue(result.ok)
        self.assertFalse(self.patch_path.exists())

    def test_sdk_exception_never_escapes_run(self) -> None:
        with mock.patch.object(litellm_adapter, "_complete", side_effect=RuntimeError("rate limited")):
            result = litellm_adapter.LiteLLMRunner("fake-model").run(self.prompt_path, self.patch_path)
        self.assertFalse(result.ok)
        self.assertIn("rate limited", result.error)

    def test_missing_prompt_file_is_a_clean_failure(self) -> None:
        result = litellm_adapter.LiteLLMRunner("fake-model").run(self.tmp / "absent.md", self.patch_path)
        self.assertFalse(result.ok)
        self.assertIsInstance(result, RunResult)

    def test_malformed_response_shape_is_a_clean_failure(self) -> None:
        with mock.patch.object(litellm_adapter, "_complete", return_value=SimpleNamespace()):
            result = litellm_adapter.LiteLLMRunner("fake-model").run(self.prompt_path, self.patch_path)
        self.assertFalse(result.ok)
        self.assertIn("unrecognised response shape", result.error)


class PreflightRealTargetTest(unittest.TestCase):
    """Real-input exercise (`PHASE/EXECUTION_RULES.md` R-E7): runs the actual
    `cdp scan` + `cdp doctor` subprocess pipeline against
    `tests/fixtures/minirepo`, with no `litellm` SDK installed. This is the
    plan's own stress test ("LiteLLM to a local 8B that collapses -- doctor
    catches it") reproduced mechanically: the model can't even be called, and
    `preflight` must report that honestly (`ok: False`) rather than crash or
    silently report success."""

    def test_preflight_reports_failure_without_a_real_llm_backend(self) -> None:
        try:
            import litellm  # noqa: F401
        except ImportError:
            pass
        else:
            self.skipTest("litellm is installed -- this exercise needs the SDK absent")
        agg = litellm_adapter.preflight("fake-model-no-such-provider", timeout_s=60)
        self.assertFalse(agg.get("ok"))


if __name__ == "__main__":
    unittest.main()
