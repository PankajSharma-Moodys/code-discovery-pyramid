"""Budget, ranked elision and stated elision — `PHASE/phase_1_plan.md` M1.3.

The defect being closed (`RESEARCH_GRAPHIFY.md §10`) is not a cosmetic one. Ten
renderers dropped rows with no marker, in direct tension with `SKILL.md:58-61`:
*"Check coverage before saying 'there is no X'."* A renderer printing 6 of 47
config read-sites with no marker manufactures exactly the false absence that rule
exists to prevent — and it is invisible, because `coverage` still reads 100%.
"""

from __future__ import annotations

import io
import re
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from helpers import make_repo  # noqa: F401  (sets sys.path)

from cdp import query as query_mod
from cdp.cli import main
from cdp.query import Budget, Store, render

QUERY_SOURCE = Path(query_mod.__file__)


class NoSilentTruncationTest(unittest.TestCase):
    """The regression guard the milestone asks for, in its literal form.

    Greps `query.py` for slice literals and fails on a new one. Crude on
    purpose: the failure mode is someone reaching for `[:20]` again because it
    is the obvious thing to type, and the only defence that survives that is one
    that fires at the moment they do.
    """

    #: Slices that are not truncations of a result list, each justified here.
    ALLOWED = {
        'claim.get("statements", [])[1:]':
            "alternate wordings of one claim; the first is rendered above it",
        "rows[:1], rows[1:]":
            "splits the entry point out so `--budget 0` still returns it",
        'result["head"][:12]':
            "short-sha display, not a row list",
        'str(as_of.get("commit", "unpinned"))[:12]':
            "short-sha display, not a row list",
    }

    SLICE_RE = re.compile(r"\[\s*:\s*\d+\s*\]|\[\s*\d+\s*:\s*\]")

    @staticmethod
    def _mask_strings_and_comments(source: str):
        """Blank out every string and comment, character by character.

        Necessary because this module's own prose quotes the constants it
        replaced (`[:40]`, `[:25]`, ...), and a line-level skip would also hide
        `"claims": claims[:6],` — where the offending slice shares a line with a
        string key. Masking by column keeps the code and drops only the prose.
        """
        import io as io_mod
        import tokenize

        rows = [list(line) for line in source.splitlines()]
        for tok in tokenize.generate_tokens(io_mod.StringIO(source).readline):
            if tok.type not in (tokenize.STRING, tokenize.COMMENT):
                continue
            (start_row, start_col), (end_row, end_col) = tok.start, tok.end
            for number in range(start_row, end_row + 1):
                row = rows[number - 1]
                lo = start_col if number == start_row else 0
                hi = end_col if number == end_row else len(row)
                for col in range(lo, min(hi, len(row))):
                    row[col] = " "
        return ["".join(row) for row in rows]

    def test_no_unexplained_slice_literals(self) -> None:
        source = QUERY_SOURCE.read_text(encoding="utf-8")
        raw = source.splitlines()
        masked = self._mask_strings_and_comments(source)
        offenders = []
        for number, line in enumerate(masked, 1):
            if not self.SLICE_RE.search(line):
                continue
            if any(allowed in raw[number - 1] for allowed in self.ALLOWED):
                continue
            offenders.append("%s:%d  %s" % (QUERY_SOURCE.name, number,
                                            raw[number - 1].strip()))
        self.assertEqual(
            offenders, [],
            "New slice literal(s) in query.py. A result list must be cut through "
            "Budget.take, which counts the cut and reports it, not through a "
            "constant. If this slice is genuinely not a result list, add it to "
            "NoSilentTruncationTest.ALLOWED with the reason:\n  "
            + "\n  ".join(offenders),
        )

    def test_the_guard_can_fail(self) -> None:
        """A guard that cannot go red is not evidence.

        Drives the real scanner over the exact line this milestone deleted —
        including the string key on the same line, which is what a line-level
        docstring skip would have hidden.
        """
        source = 'x = {\n    "claims": claims[:6],\n}\n'
        masked = self._mask_strings_and_comments(source)
        hits = [line for line in masked if self.SLICE_RE.search(line)]
        self.assertEqual(len(hits), 1, masked)

    def test_the_guard_ignores_prose(self) -> None:
        source = '"""A docstring mentioning [:40] and [:20]."""\n# and a comment [:6]\n'
        masked = self._mask_strings_and_comments(source)
        self.assertEqual([line for line in masked if self.SLICE_RE.search(line)], [])


class BudgetMechanicsTest(unittest.TestCase):
    def rows(self, n):
        return [{"subject": "s%02d" % i, "evidence": [1] * (n - i)} for i in range(n)]

    def test_spends_across_lists_not_per_list(self) -> None:
        budget = Budget(10)
        self.assertEqual(len(budget.take(self.rows(6))), 6)
        self.assertEqual(len(budget.take(self.rows(6))), 4)
        self.assertEqual(budget.elided, 2)

    def test_drops_lowest_evidence_first(self) -> None:
        budget = Budget(2)
        kept = budget.take(self.rows(4))
        # rows[0] has 4 anchors, rows[3] has 1.
        self.assertEqual([r["subject"] for r in kept], ["s00", "s01"])
        self.assertEqual(budget.elided, 2)

    def test_survivors_keep_their_original_order(self) -> None:
        """Ranking decides what is dropped, never what the output looks like."""
        rows = [
            {"subject": "b", "evidence": [1, 1]},
            {"subject": "a", "evidence": [1]},
            {"subject": "c", "evidence": [1, 1, 1]},
        ]
        self.assertEqual([r["subject"] for r in Budget(2).take(rows)], ["b", "c"])

    def test_ties_break_totally_and_deterministically(self) -> None:
        """Equal evidence and equal subject must still order identically on
        every run, or the determinism gate fails intermittently — the worst
        failure mode to debug, because a re-run hides it."""
        rows = [{"subject": "same", "evidence": [1], "id": "z"},
                {"subject": "same", "evidence": [1], "id": "a"},
                {"subject": "same", "evidence": [1], "id": "m"}]
        first = [r["id"] for r in Budget(2).take(list(rows))]
        for _ in range(20):
            self.assertEqual([r["id"] for r in Budget(2).take(list(rows))], first)
        self.assertEqual(first, ["a", "m"])  # ranked on id, emitted in order

    def test_zero_budget_returns_nothing_and_says_why(self) -> None:
        budget = Budget(0)
        self.assertEqual(budget.take(self.rows(5)), [])
        self.assertEqual(budget.elided, 5)
        self.assertIn("admits no rows", budget.note())

    def test_never_returns_a_row_over_budget(self) -> None:
        for limit in range(0, 8):
            budget = Budget(limit)
            kept = budget.take(self.rows(7))
            self.assertLessEqual(len(kept), limit)
            self.assertEqual(len(kept) + budget.elided, 7)


class BudgetedQueryTest(unittest.TestCase):
    """End to end, through the CLI, on a real scanned repository."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        cls.repo = make_repo(Path(cls.tmp.name))
        cls.state = Path(cls.tmp.name) / "state"
        main(["scan", "--repo", str(cls.repo), "--state-dir", str(cls.state),
              "--quiet"])
        cls.store = Store(cls.state)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def run_cli(self, *argv) -> str:
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = main(list(argv) + ["--state-dir", str(self.state)])
        self.assertEqual(code, 0)
        return buf.getvalue()

    def test_every_query_reports_elided_and_provenance(self) -> None:
        for kind in sorted(query_mod.QUERIES):
            term = {"symbol": "Widget", "file": "Widget.java", "module": "core",
                    "search": "widget", "trace": "/v1/widgets"}.get(kind)
            argv = ["query", kind] + ([term] if term else [])
            out = self.run_cli(*argv)
            self.assertRegex(out, r"elided: \d+", kind)
            self.assertRegex(out, r"as of \S+@\S+, state v\d+", kind)

    def test_json_and_text_are_cut_by_the_same_budget(self) -> None:
        """They used to disagree: `defines[:40]` in the JSON, `[:20]` on screen,
        and neither said so."""
        import json

        data = json.loads(self.run_cli("query", "claims", "--json", "--budget", "3"))
        text = self.run_cli("query", "claims", "--budget", "3")
        self.assertEqual(len(data["claims"]), 3)
        self.assertEqual(data["elided"], data["count"] - 3)
        self.assertIn("... %d more" % data["elided"], text)

    def test_a_bound_budget_states_the_count(self) -> None:
        out = self.run_cli("query", "claims", "--budget", "2")
        self.assertIn("elided: ", out)
        self.assertNotIn("elided: 0", out)

    def test_budget_smaller_than_one_row(self) -> None:
        out = self.run_cli("query", "claims", "--budget", "0")
        self.assertIn("admits no rows", out)
        self.assertNotIn("elided: 0\n", out)

    def test_stats_is_never_budgeted(self) -> None:
        """`query stats --budget 1` must still return complete stats."""
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = main(["query", "stats", "--budget", "1",
                         "--state-dir", str(self.state)])
        self.assertEqual(code, 2, "budgeting a guardrail must be refused")

        out = self.run_cli("query", "stats")
        self.assertIn("elided: 0", out)
        self.assertIn("never budgeted", out)

    def test_coverage_is_never_budgeted(self) -> None:
        out = self.run_cli("query", "coverage")
        self.assertIn("elided: 0", out)
        self.assertIn("never budgeted", out)

    def test_no_query_function_loses_its_true_count(self) -> None:
        """A budgeted list is shown beside the number of rows there really are;
        otherwise the elision is stated but the scale of it is not."""
        import json

        data = json.loads(self.run_cli("query", "claims", "--json", "--budget", "1"))
        self.assertGreater(data["count"], len(data["claims"]))


if __name__ == "__main__":
    unittest.main()
