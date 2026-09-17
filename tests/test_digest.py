"""Digest-first leaves (M6.3, 4.2) -- prompts.py's digest builder and the
`--digest` flag, plus the escalation-rate metric in `cdp collect`."""

from __future__ import annotations

import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from helpers import make_repo  # noqa: F401  (sets sys.path)

from cdp.cli import Paths, _escalation_rate, _open_store, main
from cdp.prompts import build_prompt
from cdp.query import Store


class BuildPromptDigestModeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        cls.repo = make_repo(Path(cls.tmp.name))
        cls.state = Path(cls.tmp.name) / "state"
        main(["scan", "--repo", str(cls.repo), "--state-dir", str(cls.state), "--quiet"])
        cls.store = Store(cls.state)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.store.close()
        cls.tmp.cleanup()

    def _scope(self):
        return self.store.partition["scopes"][0]

    def _sched(self):
        return self.store._load("schedule")

    def test_default_mode_is_unchanged_no_digest_section(self) -> None:
        text, stats = build_prompt(
            self._scope(), self.store.inventory, self.store.extraction, self.store.xref,
            self._sched(), [], "run1",
        )
        self.assertFalse(stats["digest_mode"])
        self.assertIsNone(stats["digest_fingerprint"])
        self.assertNotIn("## Digest", text)
        self.assertIn("read every file in scope", text)

    def test_digest_mode_inlines_file_text_and_fingerprints_it(self) -> None:
        scope = self._scope()
        text, stats = build_prompt(
            scope, self.store.inventory, self.store.extraction, self.store.xref,
            self._sched(), [], "run1", digest_mode=True, repo_root=self.repo,
        )
        self.assertTrue(stats["digest_mode"])
        self.assertIsNotNone(stats["digest_fingerprint"])
        self.assertIn("## Digest", text)
        self.assertIn("digest_fingerprint", text)
        self.assertIn("escalated", text)
        one_file = sorted(scope["files"])[0]
        real_text = (self.repo / one_file).read_text(encoding="utf-8")
        first_line = real_text.splitlines()[0]
        self.assertIn(first_line, text)

    def test_digest_fingerprint_is_deterministic(self) -> None:
        scope = self._scope()
        _, stats1 = build_prompt(
            scope, self.store.inventory, self.store.extraction, self.store.xref,
            self._sched(), [], "run1", digest_mode=True, repo_root=self.repo,
        )
        _, stats2 = build_prompt(
            scope, self.store.inventory, self.store.extraction, self.store.xref,
            self._sched(), [], "run2", digest_mode=True, repo_root=self.repo,
        )
        self.assertEqual(stats1["digest_fingerprint"], stats2["digest_fingerprint"])


class EscalationRateTest(unittest.TestCase):
    def test_none_when_no_claims(self) -> None:
        self.assertIsNone(_escalation_rate([]))
        self.assertIsNone(_escalation_rate([{"claims": []}]))

    def test_fraction_of_escalated_claims(self) -> None:
        patches = [
            {"claims": [{"escalated": True}, {"escalated": False}]},
            {"claims": [{}]},
        ]
        self.assertAlmostEqual(_escalation_rate(patches), 1 / 3)


class CliDigestFlagTest(unittest.TestCase):
    """End to end through the CLI, on the fixture -- the flag actually reaches
    `build_prompt` and the written prompt file reflects it."""

    def test_prompts_digest_flag_writes_digest_section(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(Path(tmp))
            state = Path(tmp) / "state"
            self.assertEqual(
                main(["scan", "--repo", str(repo), "--state-dir", str(state), "--quiet"]),
                0,
            )
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = main(["prompts", "--digest", "--repo", str(repo), "--state-dir", str(state)])
            self.assertEqual(code, 0)

            backend = _open_store(Paths(repo=repo, state=state))
            report = backend.read_report("prompts")
            backend.close()
            self.assertTrue(report["prompts"])
            for row in report["prompts"]:
                self.assertTrue(row["digest_mode"])
                self.assertIsNotNone(row["digest_fingerprint"])
                prompt_text = Path(row["prompt"]).read_text(encoding="utf-8")
                self.assertIn("## Digest", prompt_text)

    def test_digest_mode_refuses_a_mismatched_repo(self) -> None:
        """A found-live defect (this session): omitting --repo used to
        silently degrade every digest to empty text instead of failing, the
        same failure class as FINDINGS.md F16. `cmd_prompts --digest` must
        now raise before writing anything wrong."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(Path(tmp))
            state = Path(tmp) / "state"
            self.assertEqual(
                main(["scan", "--repo", str(repo), "--state-dir", str(state), "--quiet"]),
                0,
            )
            code = main(["prompts", "--digest", "--state-dir", str(state)])
            self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
