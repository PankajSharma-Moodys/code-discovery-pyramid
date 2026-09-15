"""The golden baseline, and the properties that make it worth keeping.

Two layers, because they fail for different reasons and a test suite that
conflates them wastes the reader's time:

- `NormalisationTest` / `CompareTest` exercise the machinery directly. They are
  fast and hermetic, and they are what catches a normalisation rule that stopped
  matching.
- `FixtureGoldenTest` runs the real pipeline end to end against `minirepo` and
  diffs it against a checked-in baseline. It is what catches a refactor that
  changed an answer.

`$TARGET_REPO` is deliberately *not* exercised here: a 4,728-file scan takes
~2m30s twice over, which does not belong in a unit-test run, and the path is
private to one machine. `make golden` covers it, and `PHASE/TARGET.md` records
the pin.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from helpers import SKILL_ROOT, make_repo  # noqa: F401  (sets sys.path)

from cdp import golden
from cdp.cli import GOLDEN_ROOT, run_golden

FIXTURE_SLUG = "minirepo@fixture"


class NormalisationTest(unittest.TestCase):
    """Everything environment-derived must be normalised away.

    The Phase 0 stress test that matters most: `inventory["repo"]` is an
    absolute path (`inventory.py:85`), so a baseline that keeps it passes only
    on the machine that blessed it.
    """

    def test_absolute_repo_path_is_replaced(self) -> None:
        text = '{"repo": "/Users/alice/src/thing", "n": 1}'
        out = golden.normalise_text(text, Path("/Users/alice/src/thing"), None)
        self.assertNotIn("/Users/alice", out)
        self.assertIn("<REPO>", out)

    def test_a_second_developer_gets_the_same_baseline(self) -> None:
        """The concrete form of the failure: two checkouts, one baseline."""
        alice = golden.normalise_text(
            '{"repo": "/Users/alice/src/thing"}', Path("/Users/alice/src/thing"), None)
        bob = golden.normalise_text(
            '{"repo": "/home/bob/work/thing"}', Path("/home/bob/work/thing"), None)
        self.assertEqual(alice, bob)

    def test_commit_sha_and_derived_run_id_are_replaced(self) -> None:
        head = "7e10575adf69a193da7f547aed088f7409f1f7c4"
        text = '{"head": "%s", "run_id": "cdp-%s"}' % (head, head[:12])
        out = golden.normalise_text(text, Path("/x"), head)
        self.assertNotIn(head, out)
        self.assertNotIn(head[:12], out)
        self.assertEqual(out.count("<HEAD>"), 2)

    def test_timestamps_are_replaced(self) -> None:
        out = golden.normalise_text(
            '{"generated_at": "2026-09-15T16:25:31+00:00"}', Path("/x"), None)
        self.assertIn("<TIME>", out)
        self.assertNotIn("2026-09-15", out)

    def test_unpinned_head_does_not_blank_the_document(self) -> None:
        """`head` is the string 'unpinned' for a non-git target; substituting it
        would rewrite every unrelated occurrence of that word."""
        text = '{"head": "unpinned", "note": "unpinned targets are noisier"}'
        self.assertEqual(golden.normalise_text(text, Path("/x"), "unpinned"), text)

    def test_manifest_is_excluded_from_capture(self) -> None:
        captured = golden.capture(
            {"scan/manifest.json": "{}", "scan/state.json": "{}"}, Path("/x"), None)
        self.assertNotIn("scan/manifest.json", captured)
        self.assertIn("scan/state.json", captured)

    def test_oversized_artifacts_are_stored_as_digests(self) -> None:
        """The 'golden set is enormous' stress test, with its decision made
        visible: the stored value says the body was elided."""
        big = "x" * (golden.FULL_BODY_LIMIT + 1)
        captured = golden.capture(
            {"scan/extract.json": big, "scan/state.json": big}, Path("/x"), None)
        self.assertIn("body elided", captured["scan/extract.json"])
        self.assertTrue(captured["scan/extract.json"].startswith("sha256:"))
        # ALWAYS_FULL wins over the size limit: state.json is what queries are
        # answered from, and a hash says nothing about what moved.
        self.assertNotIn("body elided", captured["scan/state.json"])


class CompareTest(unittest.TestCase):
    """The diff must be readable. A regression test whose failure message is
    `False != True` costs more than it saves."""

    def test_identical_sets_produce_no_report(self) -> None:
        self.assertEqual(golden.compare({"a": "x\n"}, {"a": "x\n"}), [])

    def test_a_changed_line_is_shown_in_context(self) -> None:
        reports = golden.compare(
            {"state.json": "a\nb\nc\n"}, {"state.json": "a\nB\nc\n"})
        self.assertEqual(len(reports), 1)
        body = reports[0]
        self.assertIn("-b", body)
        self.assertIn("+B", body)
        self.assertIn("baseline/state.json", body)

    def test_a_removed_artifact_is_named(self) -> None:
        reports = golden.compare({"query/routes.json": "{}"}, {})
        self.assertEqual(len(reports), 1)
        self.assertIn("query/routes.json", reports[0])
        self.assertIn("not produced by this run", reports[0])

    def test_an_added_artifact_is_named(self) -> None:
        reports = golden.compare({}, {"query/new.json": "{}"})
        self.assertIn("absent from the baseline", reports[0])

    def test_summary_is_bounded(self) -> None:
        reports = ["artifact %d differs" % n for n in range(50)]
        summary = golden.summarise(reports, limit=3)
        self.assertIn("50 artifact(s) differ", summary)
        self.assertIn("and 47 more", summary)

    def test_empty_reports_summarise_as_ok(self) -> None:
        self.assertIn("ok", golden.summarise([]))


class WriteReadTest(unittest.TestCase):
    def test_blessing_removes_artifacts_no_longer_produced(self) -> None:
        """Total, not incremental. An additive bless would keep a stale
        baseline for a query that was deleted, and pass over its removal."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp) / "golden"
            golden.write(d, {"a.json": "1\n", "b.json": "2\n"})
            golden.write(d, {"a.json": "1\n"})
            self.assertEqual(set(golden.read(d)), {"a.json"})

    def test_nested_paths_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp) / "golden"
            payload = {"scan/patches/0000-derived.json": "{}\n", "docs/x.md": "hi\n"}
            golden.write(d, payload)
            self.assertEqual(golden.read(d), payload)

    def test_slug_shape(self) -> None:
        self.assertEqual(golden.slug("repo", "abcdef1234567890"), "repo@abcdef123456")
        self.assertEqual(golden.slug("repo", "unpinned"), "repo@unpinned")
        self.assertEqual(golden.slug("repo", None), "repo@unpinned")


class FixtureGoldenTest(unittest.TestCase):
    """End-to-end over the real pipeline.

    `minirepo` rather than this repository: since M0.1 vendored a second copy of
    the fixture into `.claude/skills/cdp/`, this repository has two modules named
    `core` and its own output is non-deterministic (`PHASE/FINDINGS.md` F1).
    The fixture has unique module basenames and is stable.
    """

    def test_fixture_matches_its_baseline(self) -> None:
        baseline = GOLDEN_ROOT / FIXTURE_SLUG
        if not baseline.is_dir():
            self.skipTest(
                "no fixture baseline at %s; bless it with `make bless-fixture`" % baseline)
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(Path(tmp))
            code, report = run_golden(repo, name=FIXTURE_SLUG)
        self.assertEqual(code, 0, report)

    @unittest.skipUnless(os.environ.get("TARGET_REPO"), "TARGET_REPO not set")
    def test_target_repo_matches_its_baseline(self) -> None:
        """Opt-in, because it is a ~5 minute scan of a private repository.
        `make golden` is the normal way to run it."""
        repo = Path(os.environ["TARGET_REPO"]).expanduser().resolve()
        code, report = run_golden(repo)
        self.assertEqual(code, 0, report)


if __name__ == "__main__":
    unittest.main()
