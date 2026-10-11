"""Anchor search stays equivalent to the naive per-window definition and no longer goes quadratic."""

from __future__ import annotations

import random
import time
import unittest
from unittest import mock

from helpers import SKILL_ROOT  # noqa: F401

from cdp import anchor
from cdp.anchor import build_anchor, find_matches
from cdp.util import normalise_ws


def naive(lines, needle_raw, max_span=4):
    needle = normalise_ws(needle_raw)
    hits = []
    for i in range(len(lines)):
        for w in range(1, max_span + 1):
            if i + w > len(lines):
                break
            text = normalise_ws(" ".join(lines[i:i + w]))
            if not normalise_ws(lines[i]):
                break
            # a match that begins inside line i and ends within w source lines
            pos = text.find(needle)
            if pos >= 0 and pos < len(normalise_ws(lines[i])) + 1 and needle:
                hits.append(i + 1)
                break
    return hits


class IndexEquivalenceTest(unittest.TestCase):
    def _files(self):
        rnd = random.Random(7)
        words = ["foo", "bar(x);", "m();", "  }", "{", "var a = b.c(d, e);", "", "xm();", "call(1, 2)"]
        for _ in range(6):
            yield ["    " + rnd.choice(words) for _ in range(rnd.randint(30, 120))]

    def test_indexed_search_matches_the_plain_scan(self):
        for lines in self._files():
            needles = set()
            for i in range(len(lines)):
                for w in (1, 2, 3):
                    t = normalise_ws(" ".join(lines[i:i + w]))
                    needles.add(t)
                    needles.add(t[3:])           # starts mid-line
            needles = {n for n in needles if len(n) >= 12}
            for n in sorted(needles):
                plain = find_matches(list(lines), n)
                with mock.patch.object(anchor, "INDEX_MIN_BLOB", 0):
                    indexed = find_matches(list(lines), n)
                    capped = find_matches(list(lines), n, limit=2)
                self.assertEqual(plain, indexed, n)
                self.assertEqual(plain[:2], capped, n)

    def test_limit_returns_only_the_first_hits(self):
        lines = ["    m();  // same"] * 50
        self.assertEqual([1, 2, 3, 4], find_matches(lines, "m(); // same", limit=4))


class QuadraticCliffTest(unittest.TestCase):
    def test_thousands_of_identical_lines_stay_fast(self):
        lines = ["    m();"] * 4000
        t = time.time()
        for i in range(len(lines)):
            build_anchor("f.cs", lines, i)
        self.assertLess(time.time() - t, 2.0)

    def test_a_large_file_of_distinct_calls_stays_fast(self):
        lines = ["    obj%d.call%d(arg);" % (i, i) for i in range(40000)]
        t = time.time()
        got = [build_anchor("f.cs", lines, i) for i in range(0, len(lines), 20)]
        self.assertLess(time.time() - t, 5.0)
        self.assertTrue(sum(1 for g in got if g) > len(got) // 2)


if __name__ == "__main__":
    unittest.main()
