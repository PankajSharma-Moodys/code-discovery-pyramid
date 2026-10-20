"""Bug D: a deterministic fact on a line repeated more than `MAX_MATCHES_IN_FILE` times keeps
its row and its exact line; claims (model or human) still follow the text-uniqueness rule."""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from helpers import SKILL_ROOT  # noqa: F401

from cdp.anchor import EXACT, MAX_MATCHES_IN_FILE, TOO_COMMON, build_anchor, build_fact_anchor
from cdp.derive import _claim
from cdp.extract import run_extract
from cdp.inventory import build_inventory
from cdp.lang import extract_file
from cdp.refresh import incremental_extract
from cdp.verify import FileCache, verify_patch

CALL = '        lockTestData.setRequestUrl(Constants.WORKFLOW_URI.getConstant() + "/lock");'
REPEAT = 9


def java(pad: int = 0) -> str:
    """`REPEAT` identical consecutive call lines: no span of up to 4 lines is unique."""
    return ("package com.ex;\n\nimport com.ex.util.Constants;\n" + "\n" * pad
            + "public class LockTest {\n    void run(Data lockTestData) {\n"
            + (CALL + "\n") * REPEAT + "    }\n}\n")


def call_lines(lines, path="src/LockTest.java"):
    facts = extract_file(path, lines, "m")
    return [u["anchor"] for u in facts.uses if u["fqn"].endswith("Constants#getConstant")]


class RepeatedLineFactsTest(unittest.TestCase):
    def test_line_repeated_nine_times_keeps_all_nine_rows(self) -> None:
        lines = java().splitlines()
        first = lines.index(CALL) + 1
        self.assertGreater(REPEAT, MAX_MATCHES_IN_FILE)
        middle = range(first + 3, first + REPEAT - 3)   # rows within 4 of an edge grow a unique span
        for n in middle:
            self.assertIsNone(build_anchor("src/LockTest.java", lines, n - 1))   # the old drop
        anchors = call_lines(lines)
        self.assertEqual([a["line"] for a in anchors], list(range(first, first + REPEAT)))
        for a in anchors:
            if a["line"] in middle:
                self.assertTrue(a[EXACT])
                self.assertEqual(a["anchor"], CALL.strip())

    def test_unique_line_is_unchanged_and_unmarked(self) -> None:
        lines = ["class A {", "    int alpha = computeAlpha(1);", "}"]
        self.assertEqual(build_fact_anchor("A.java", lines, 1), build_anchor("A.java", lines, 1))
        self.assertNotIn(EXACT, build_fact_anchor("A.java", lines, 1))

    def test_upward_grown_span_keeps_the_facts_own_line(self) -> None:
        # the cited line is ambiguous going down; only a span ending on it is unique
        lines = ["unique opening line here();"] + ["    repeated.call(argument);"] * 5
        grown = build_anchor("A.java", lines, 1)
        self.assertEqual(grown["line"], 1)                      # the claim rule cites the span start
        fact = build_fact_anchor("A.java", lines, 1)
        self.assertEqual((fact["line"], fact["anchor"]), (2, grown["anchor"]))
        self.assertNotIn(EXACT, fact)

    def test_blank_line_is_still_not_citable(self) -> None:
        self.assertIsNone(build_fact_anchor("A.java", ["a();", "   ", "b();"], 1))


class SqlFirstOccurrenceTest(unittest.TestCase):
    """The SQL extractor keeps one edge per (table, channel): a unique occurrence still wins over
    an earlier repeated one (claims cite it), and a table seen only on repeated lines is kept."""

    def test_unique_occurrence_preferred_and_repeated_only_table_kept(self) -> None:
        lines = (["INSERT INTO address VALUES (1, 'x');"] * 6
                 + ["INSERT INTO address (id, name) VALUES (2, 'y');"])
        edges = {e["target"]: e["anchor"] for e in extract_file("db/V1__x.sql", lines, "m").io_edges}
        only = ["INSERT INTO property VALUES (1, 'x');"] * 9
        edges.update((e["target"], e["anchor"]) for e in extract_file("db/V2__y.sql", only, "m").io_edges)
        self.assertEqual(edges["table:address"]["line"], 4)    # the first line whose span is unique
        self.assertNotIn(EXACT, edges["table:address"])
        self.assertTrue(edges["table:property"][EXACT])


class ClaimsKeepUniquenessTest(unittest.TestCase):
    def test_model_claim_on_repeated_text_is_demoted(self) -> None:
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        (tmp / "LockTest.java").write_text(java())
        lines = java().splitlines()
        claim = {"id": "c1", "kind": "behavior", "subject": "x", "statement": "sets the lock url",
                 "evidence": [{"file": "LockTest.java", "line": lines.index(CALL) + 1,
                               "anchor": CALL.strip()}]}
        out, stats = verify_patch({"claims": [claim]}, FileCache(tmp))
        self.assertEqual(out["claims"], [])
        self.assertEqual(stats["reasons"], {TOO_COMMON: 1})

    def test_derived_claim_drops_exact_fact_anchors(self) -> None:
        lines = java().splitlines()
        exact = call_lines(lines)[REPEAT // 2]
        self.assertTrue(exact[EXACT])
        self.assertIsNone(_claim({}, "config", "k", "a statement long enough", [exact]))
        unique = {"file": "A.java", "line": 2, "anchor": "int alpha = computeAlpha(1);"}
        got = _claim({}, "config", "k", "a statement long enough", [exact, unique])
        self.assertEqual(got["evidence"], [unique])


class RefreshReCitesTest(unittest.TestCase):
    def test_edit_that_shifts_lines_re_cites_every_row(self) -> None:
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        src = tmp / "src" / "main" / "java" / "com" / "ex"
        src.mkdir(parents=True)
        path = src / "LockTest.java"
        path.write_text(java())
        inventory = build_inventory(tmp)
        prior = run_extract(tmp, inventory)
        rel = path.relative_to(tmp).as_posix()

        def rows(extraction):
            return sorted(u["anchor"]["line"] for u in extraction["uses"]
                          if u["file"] == rel and u["fqn"].endswith("Constants#getConstant"))

        before = rows(prior)
        self.assertEqual(len(before), REPEAT)
        path.write_text(java(pad=3))
        inventory = build_inventory(tmp)
        after = rows(incremental_extract(tmp, inventory, prior, {rel}))
        self.assertEqual(after, [n + 3 for n in before])
        self.assertEqual(after, rows(run_extract(tmp, inventory)))


if __name__ == "__main__":
    unittest.main()
