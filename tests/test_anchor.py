"""Span anchors — the C7 amendment.

The headline case: `@Entity` is 7 characters and sits alone on its own line, so
the schema's 12-character floor makes it uncitable as a per-line anchor. It is
also one of the required detection signals for the `persist` channel, which
means the schema as written forbids citing the evidence the channel vocabulary
is defined on. These tests pin the fix.
"""

from __future__ import annotations

import unittest

from helpers import SKILL_ROOT  # noqa: F401  (sets sys.path)

from cdp.anchor import (
    AMBIGUOUS,
    MAX_SPAN,
    MIN_ANCHOR_LEN,
    NOT_FOUND,
    TOO_COMMON,
    build_anchor,
    find_matches,
    verify_anchor,
)
from cdp.util import normalise_ws

ENTITY = [
    "package com.example;",
    "",
    "@Entity",
    '@Table(name = "widget")',
    "public class WidgetEntity {",
    "  private Long id;",
    "}",
]


class TestBuild(unittest.TestCase):
    def test_short_annotation_grows_into_a_citable_span(self):
        anchor = build_anchor("W.java", ENTITY, 2)
        self.assertIsNotNone(anchor)
        self.assertEqual(anchor["line"], 3)
        self.assertGreaterEqual(len(anchor["anchor"]), MIN_ANCHOR_LEN)
        # The span must still contain the signal it exists to evidence, and
        # must be more specific than either line alone.
        self.assertIn("@Entity", anchor["anchor"])
        self.assertIn("@Table", anchor["anchor"])

    def test_interior_whitespace_is_normalised(self):
        anchor = build_anchor("W.java", ENTITY, 2)
        self.assertNotIn("\n", anchor["anchor"])
        self.assertNotIn("  ", anchor["anchor"])

    def test_returns_none_when_no_citable_anchor_exists(self):
        # A file of repeated closing braces can produce nothing specific enough.
        lines = ["}"] * 20
        self.assertIsNone(build_anchor("x.java", lines, 5))

    def test_grows_upward_when_there_is_nothing_below(self):
        lines = ["public class A {", "  int x;", "}"]
        anchor = build_anchor("A.java", lines, 2)
        self.assertIsNotNone(anchor)
        self.assertIn("}", anchor["anchor"])


class TestMatching(unittest.TestCase):
    def test_a_span_match_is_reported_once_at_its_start(self):
        # Without the "begins here" rule a one-line anchor at line 4 also
        # reports matches at lines 3, 2 and 1, because a wider window covers it.
        # Every anchor would then look anchor_too_common.
        hits = find_matches(ENTITY, "public class WidgetEntity")
        self.assertEqual(hits, [5])

    def test_multi_line_span_matches_at_its_first_line(self):
        hits = find_matches(ENTITY, '@Entity @Table(name = "widget")')
        self.assertEqual(hits, [3])

    def test_substring_of_a_line_matches(self):
        hits = find_matches(ENTITY, 'Table(name = "widget")')
        self.assertEqual(hits, [4])


class TestVerify(unittest.TestCase):
    def test_accepts_and_rewrites_within_the_tolerance_window(self):
        # §5.4: line numbers drift more easily than content, so a match at 5
        # for a citation of 3 is accepted -- and the line is *rewritten*.
        # Silent acceptance without rewriting would let citations decay.
        ok, line, reason = verify_anchor(
            ENTITY, {"file": "W.java", "line": 3, "anchor": "public class WidgetEntity"}
        )
        self.assertTrue(ok)
        self.assertEqual(line, 5)
        self.assertIsNone(reason)

    def test_rejects_a_match_outside_the_window(self):
        lines = ["public class Far {"] + ["  // filler"] * 40 + ["  int marker_value = 1;"]
        ok, _, reason = verify_anchor(
            lines, {"file": "F.java", "line": 2, "anchor": "int marker_value = 1;"}
        )
        self.assertFalse(ok)
        self.assertEqual(reason, NOT_FOUND)

    def test_rejects_an_anchor_that_is_too_common(self):
        lines = ["  return Optional.empty();"] * 6
        ok, _, reason = verify_anchor(
            lines, {"file": "X.java", "line": 1, "anchor": "return Optional.empty();"}
        )
        self.assertFalse(ok)
        self.assertEqual(reason, TOO_COMMON)

    def test_rejects_an_ambiguous_anchor_inside_the_window(self):
        lines = ["  int alpha = 1;", "  int beta = 2;", "  int alpha = 1;"]
        ok, _, reason = verify_anchor(
            lines, {"file": "X.java", "line": 2, "anchor": "int alpha = 1;"}
        )
        self.assertFalse(ok)
        self.assertEqual(reason, AMBIGUOUS)

    def test_rejects_a_missing_anchor(self):
        ok, _, reason = verify_anchor(
            ENTITY, {"file": "W.java", "line": 3, "anchor": "public class Nonexistent"}
        )
        self.assertFalse(ok)
        self.assertEqual(reason, NOT_FOUND)

    def test_rejects_an_anchor_below_the_length_floor(self):
        ok, _, reason = verify_anchor(ENTITY, {"file": "W.java", "line": 3, "anchor": "@Entity"})
        self.assertFalse(ok)
        self.assertEqual(reason, NOT_FOUND)

    def test_survives_reindentation(self):
        reformatted = [line.replace("  ", "    ") for line in ENTITY]
        ok, _, _ = verify_anchor(
            reformatted, {"file": "W.java", "line": 6, "anchor": "private Long id;"}
        )
        self.assertTrue(ok)


if __name__ == "__main__":
    unittest.main()


class IndexedMatchingEquivalenceTest(unittest.TestCase):
    """`find_matches` is an index, not a scan — and must answer identically.

    Profiling put 83% of a whole scan inside `find_matches`, re-normalising
    every line of every file once per anchor per span width: 7,168,250
    `normalise_ws` calls for 6,476 anchors. It now normalises each file once
    into a single string and lets `str.find` search it in C, which is ~160x
    faster on the same input.

    That is a rewrite of the anchoring trust boundary, so the speed is not the
    thing to test. **Every claim CDP publishes is anchored by this function**,
    and an off-by-one here does not crash — it silently cites the wrong line.
    So this test keeps the naive implementation alive as an oracle and asserts
    the two agree, over real source files rather than hand-built strings.
    """

    @staticmethod
    def naive(lines, anchor, max_span=MAX_SPAN):
        """The pre-index implementation, verbatim, as a differential oracle."""
        needle = normalise_ws(anchor)
        if not needle:
            return []
        hits, n = [], len(lines)
        for i in range(n):
            span = None
            for width in range(1, max_span + 1):
                if i + width > n:
                    break
                if needle in normalise_ws(" ".join(lines[i:i + width])):
                    span = width
                    break
            if span is None:
                continue
            if span > 1 and needle in normalise_ws(" ".join(lines[i + 1:i + span])):
                continue
            hits.append(i + 1)
        return hits

    def probes(self, lines):
        """Real anchors, multi-line spans, short fragments and absent needles.

        The multi-line probes are the ones that matter: they straddle blank
        lines, and span width is counted in *source* lines, so an index that
        counted only non-blank lines would accept a match the scan rejects.
        """
        body = [l.strip() for l in lines if l.strip()]
        spans = [" ".join(lines[i:i + 3]) for i in range(0, len(lines), 37)]
        return (body[:40] + spans[:20] + [s[:15] for s in body[:10]]
                + ["", "   ", "}", "zzz-definitely-not-present"])

    def test_agrees_with_the_naive_scan_on_real_files(self) -> None:
        import glob

        checked = 0
        for path in sorted(glob.glob(str(SKILL_ROOT / "cdp" / "**" / "*.py"),
                                     recursive=True)):
            with open(path, encoding="utf-8", errors="replace") as handle:
                lines = handle.read().splitlines()
            if not lines:
                continue
            for probe in self.probes(lines):
                for max_span in (1, 2, MAX_SPAN, 6):
                    checked += 1
                    self.assertEqual(
                        self.naive(lines, probe, max_span),
                        find_matches(lines, probe, max_span),
                        "%s  max_span=%d  probe=%r" % (path, max_span, probe[:60]),
                    )
        self.assertGreater(checked, 5000, "the oracle found nothing to compare")

    def test_span_width_counts_blank_lines(self) -> None:
        """Explicit, because it is the one way the index could diverge."""
        lines = ["alpha beta gamma", "", "", "", "delta epsilon zeta"]
        needle = "alpha beta gamma delta epsilon zeta"
        # Five source lines apart: inside a span of 5, outside a span of 4.
        self.assertEqual(find_matches(lines, needle, 5), [1])
        self.assertEqual(find_matches(lines, needle, 4), [])
        self.assertEqual(self.naive(lines, needle, 4), [])

    def test_cache_cannot_answer_about_the_wrong_file(self) -> None:
        """The memo is keyed on `id(lines)`, which is only sound because the
        entry holds the list alive. Churning many short-lived lists is how a
        recycled address would show up."""
        seen = []
        for n in range(200):
            lines = ["unique marker number %d here" % n, "filler line"]
            seen.append(find_matches(lines, "unique marker number %d here" % n))
            del lines
        self.assertEqual(seen, [[1]] * 200)
