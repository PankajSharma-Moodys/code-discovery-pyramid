"""The reproducibility gate.

`cmd_scan` writes, into `manifest.json`, the claim that it is "the only state
file containing a timestamp, and is excluded from the byte-identical
reproducibility check for that reason". Until this module existed there was no
such check — the note described an intention.

Every phase after this one rewrites load-bearing code (`state.fold`, every JSON
write, `verify`). Without a gate, those rewrites are unfalsifiable: a merge that
silently became order-dependent, or a `set()` that leaked iteration order into
`state.json`, produces output that still looks plausible.

The complementary gate is `check_order_independence` (`state.py:258`), which
catches the failure this one cannot: a merge that is deterministic but
*arbitrary* passes a two-run comparison perfectly.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from helpers import SKILL_ROOT, have_git, make_repo  # noqa: F401  (sets sys.path)

from cdp.cli import VOLATILE_FIELDS, VOLATILE_FILE, check_determinism


class DeterminismTest(unittest.TestCase):
    def test_minirepo_scans_reproducibly(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(Path(tmp))
            problems = check_determinism(repo)
        self.assertEqual(problems, [], "\n".join(problems))

    def test_this_repository_scans_reproducibly(self) -> None:
        """Real, non-fixture input. A 12-file fixture is not evidence about a
        multi-thousand-file repository: the orderings that leak are the ones
        that only have enough elements to be observable at scale."""
        problems = check_determinism(SKILL_ROOT)
        self.assertEqual(problems, [], "\n".join(problems))


class GateSensitivityTest(unittest.TestCase):
    """The gate must fail when it should.

    A green reproducibility check is only evidence if the check can go red.
    These drive `check_determinism` with a stub scanner so the failure modes
    can be produced exactly, without corrupting a real pipeline module.
    """

    @staticmethod
    def _writer(payload):
        """Build a scan stub whose output varies per call via `payload(n)`."""
        counter = {"n": 0}

        def scan(repo: Path, state: Path) -> None:
            counter["n"] += 1
            state.mkdir(parents=True, exist_ok=True)
            files = payload(counter["n"])
            for rel, text in files.items():
                path = state / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text)

        return scan

    def _manifest(self, **extra) -> str:
        base = {"generated_at": "2026-01-01T00:00:00+00:00", "head": "abc123"}
        base.update(extra)
        return json.dumps(base, indent=2, sort_keys=True)

    def test_passes_when_only_generated_at_differs(self) -> None:
        scan = self._writer(lambda n: {
            "state.json": '{"claims": []}',
            VOLATILE_FILE: self._manifest(generated_at="2026-01-0%dT00:00:00+00:00" % n),
        })
        self.assertEqual(check_determinism(Path("/nonexistent"), scan=scan), [])

    def test_catches_a_differing_state_file(self) -> None:
        """The `set()`-iteration failure mode, in its observable form."""
        scan = self._writer(lambda n: {
            "state.json": '{"claims": ["a", "b"]}' if n == 1 else '{"claims": ["b", "a"]}',
            VOLATILE_FILE: self._manifest(),
        })
        problems = check_determinism(Path("/nonexistent"), scan=scan)
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("state.json", problems[0])
        # The message must locate the difference, not merely announce one.
        self.assertIn("line 1", problems[0])

    def test_catches_a_non_volatile_manifest_field(self) -> None:
        """`manifest.json` is excepted, but only for its declared fields.
        A clock leaking into `head` must not ride in on that exemption."""
        scan = self._writer(lambda n: {
            VOLATILE_FILE: self._manifest(head="abc%d" % n),
        })
        problems = check_determinism(Path("/nonexistent"), scan=scan)
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("head", problems[0])
        self.assertIn("not declared volatile", problems[0])

    def test_catches_a_file_written_by_only_one_scan(self) -> None:
        scan = self._writer(lambda n: (
            {VOLATILE_FILE: self._manifest()} if n == 1
            else {VOLATILE_FILE: self._manifest(), "reports/extra.json": "{}"}
        ))
        problems = check_determinism(Path("/nonexistent"), scan=scan)
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("reports/extra.json", problems[0])

    def test_volatile_declaration_is_narrow(self) -> None:
        """Guard against the exemption being widened to make a failure go away."""
        self.assertEqual(VOLATILE_FILE, "manifest.json")
        self.assertEqual(VOLATILE_FIELDS, ("generated_at",))


if __name__ == "__main__":
    unittest.main()
