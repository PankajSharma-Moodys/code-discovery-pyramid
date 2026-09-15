"""The merge operator (§5.5).

Detection is the harder half, and both obvious definitions are wrong: matching
on claim `id` fires almost never because ids are agent-coined, and matching on
"these statements read differently" fires constantly on claims written from
different vantage points.

The `DServer` case is the one to keep in mind. `sql-pool-api` calls it an
API-facing domain type; `sql-pool-common` calls it a shared internal model.
Both are true from where each agent was standing. A detector that flags that
pair flags most of the corpus.
"""

from __future__ import annotations

import unittest

from helpers import SKILL_ROOT  # noqa: F401

from cdp.merge import merge_claims
from cdp.util import stable_hash

SYMBOLS = {
    "common.DServer": {"fqn": "common.DServer", "kind": "class", "visibility": "public",
                       "modules": ["sql-pool-common"], "sites": []},
    "shared.table": {"fqn": "shared.table", "kind": "table", "visibility": "public",
                     "modules": [], "sites": []},
}


def claim(node, subject, kind="ownership", statement="A statement long enough.", **kw):
    row = {
        "id": "x.y",
        "kind": kind,
        "subject": subject,
        "statement": statement,
        "evidence": kw.pop("evidence", [{"file": node + ".java", "line": 1, "anchor": "anchor text here"}]),
        "confidence": kw.pop("confidence", "high"),
        "source_node": node,
    }
    row.update(kw)
    return row


class TestDetection(unittest.TestCase):
    def test_differing_prose_on_identical_enums_is_not_a_conflict(self):
        result = merge_claims(
            [
                claim("root/sql-pool-api", "common.DServer",
                      statement="An API-facing domain type returned by the server routes."),
                claim("root/sql-pool-common", "common.DServer",
                      statement="A shared internal model used across every module."),
            ],
            SYMBOLS,
        )
        self.assertEqual(result["stats"]["conflicts"], 0)
        self.assertEqual(result["stats"]["unanimous"], 1)
        # Both descriptions survive with both evidence sets attached.
        merged = result["claims"][0]
        self.assertEqual(len(merged["statements"]), 2)
        self.assertEqual(len(merged["evidence"]), 2)

    def test_that_pair_is_counted_as_a_near_miss(self):
        # C4 instrumentation: the number that distinguishes "the rule is
        # well-calibrated" from "the rule never fires".
        result = merge_claims(
            [
                claim("root/a", "common.DServer", statement="One wording of the same fact."),
                claim("root/b", "common.DServer", statement="Another wording of the same fact."),
            ],
            SYMBOLS,
        )
        self.assertEqual(result["stats"]["near_misses"], 1)

    def test_differing_enum_on_the_same_subject_and_kind_is_a_conflict(self):
        result = merge_claims(
            [
                claim("root/sql-pool-api", "common.DServer", visibility="public"),
                claim("root/sql-pool-common", "common.DServer", visibility="internal"),
            ],
            SYMBOLS,
        )
        self.assertEqual(result["stats"]["conflicts"], 1)

    def test_different_kinds_about_one_subject_are_complementary_not_contested(self):
        result = merge_claims(
            [
                claim("root/a", "common.DServer", kind="ownership"),
                claim("root/b", "common.DServer", kind="data_model"),
            ],
            SYMBOLS,
        )
        self.assertEqual(result["stats"]["conflicts"], 0)
        self.assertEqual(len(result["claims"]), 2)


class TestResolution(unittest.TestCase):
    def test_the_module_that_defines_the_subject_wins(self):
        result = merge_claims(
            [
                claim("root/sql-pool-api", "common.DServer", visibility="public",
                      evidence=[{"file": "a.java", "line": 1, "anchor": "anchor one here"},
                                {"file": "b.java", "line": 1, "anchor": "anchor two here"},
                                {"file": "c.java", "line": 1, "anchor": "anchor three here"}]),
                claim("root/sql-pool-common", "common.DServer", visibility="internal"),
            ],
            SYMBOLS,
        )
        self.assertEqual(result["stats"]["resolved_by_ownership"], 1)
        # Ownership outranks evidence count even though api cited three anchors
        # to common's one. Evidence count rewards verbosity; a conflict about
        # what a symbol means turns on authority, not volume.
        self.assertEqual(result["claims"][0]["visibility"], "internal")

    def test_evidence_count_breaks_a_tie_when_nobody_owns_the_subject(self):
        result = merge_claims(
            [
                claim("root/a", "shared.table", visibility="public",
                      evidence=[{"file": "a.java", "line": 1, "anchor": "anchor one here"},
                                {"file": "b.java", "line": 2, "anchor": "anchor two here"}]),
                claim("root/b", "shared.table", visibility="internal"),
            ],
            SYMBOLS,
        )
        self.assertEqual(result["stats"]["resolved_by_evidence"], 1)
        self.assertEqual(result["claims"][0]["visibility"], "public")

    def test_a_genuine_tie_escalates_rather_than_picking(self):
        # A merge operator that always produces an answer fabricates under
        # contention, and contention is where the interesting knowledge lives.
        result = merge_claims(
            [
                claim("root/a", "shared.table", visibility="public"),
                claim("root/b", "shared.table", visibility="internal"),
            ],
            SYMBOLS,
        )
        self.assertEqual(result["stats"]["contested"], 1)
        self.assertEqual(result["claims"][0]["confidence"], "contested")
        self.assertEqual(len(result["conflicts"]), 1)
        self.assertIsNone(result["conflicts"][0]["resolved_by"])
        self.assertEqual(sorted(result["claims"][0]["contested_with"]), ["root/a", "root/b"])

    def test_an_n_way_tie_keeps_every_position(self):
        # `contested` is a set-valued outcome; pairwise folding is exactly where
        # an n-way tie degrades into an arbitrary pair.
        result = merge_claims(
            [
                claim("root/a", "shared.table", visibility="public"),
                claim("root/b", "shared.table", visibility="internal"),
                claim("root/c", "shared.table", visibility="private"),
            ],
            SYMBOLS,
        )
        self.assertEqual(len(result["conflicts"][0]["positions"]), 3)


class TestOrderIndependence(unittest.TestCase):
    """Any merge policy admitted into CDP must produce the same result whatever
    order sibling patches arrive in. Arrival order encodes *scheduling*, not
    authority; letting it decide would make `--max-concurrent` an input to the
    architecture documentation — and the failure would be invisible, since an
    order-dependent merge is deterministic-but-arbitrary and would score 1.0."""

    def test_result_is_identical_under_permutation(self):
        claims = [
            claim("root/a", "shared.table", visibility="public"),
            claim("root/b", "shared.table", visibility="internal"),
            claim("root/sql-pool-common", "common.DServer", visibility="internal"),
            claim("root/sql-pool-api", "common.DServer", visibility="public"),
            claim("root/c", "other.thing", kind="config"),
        ]
        baseline = stable_hash(merge_claims(claims, SYMBOLS)["claims"])
        for permutation in (
            list(reversed(claims)),
            claims[2:] + claims[:2],
            sorted(claims, key=lambda c: c["source_node"], reverse=True),
        ):
            self.assertEqual(stable_hash(merge_claims(permutation, SYMBOLS)["claims"]), baseline)


if __name__ == "__main__":
    unittest.main()
