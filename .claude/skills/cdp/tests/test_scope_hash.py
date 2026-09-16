"""Phase 3, M3.4 -- scope-hash caching and the supersession fix.

Two independent things, tested separately: `state.fold` must yield one
generation's claims per node, not an accumulation of every attempt ever
appended to the log (`ARCHITECTURE.md`'s sharp-edges table); and `scope_hash`
must be a stable content fingerprint that `changed_scopes` can diff across a
commit to name which scopes actually need re-dispatch.
"""

from __future__ import annotations

import random
import unittest
from pathlib import Path

from helpers import MiniRepoTest

from cdp.refresh import annotate_scope_hashes, changed_scopes, scope_hash
from cdp.state import fold


def _patch(node: str, generation: int, claim_id: str) -> dict:
    return {
        "schema_version": "1.0.0",
        "node": node,
        "run_id": "r1",
        "status": "complete",
        "generation": generation,
        "claims": [
            {
                "id": claim_id,
                "kind": "defines",
                "subject": claim_id,
                "statement": "x",
                "evidence": [],
                "confidence": "high",
            }
        ],
        "unknowns": [],
    }


class SupersessionTest(unittest.TestCase):
    def test_rerunning_a_node_yields_one_generation_not_two(self) -> None:
        patches = [_patch("root/a", 1, "a.first"), _patch("root/a", 2, "a.second")]
        result = fold(patches, {"symbols": {}}, None)
        subjects = {c["subject"] for c in result["claims"]}
        self.assertEqual(subjects, {"a.second"})
        self.assertEqual(len(result["claims"]), 1)

    def test_supersession_is_order_independent(self) -> None:
        patches = [_patch("root/a", 1, "a.first"), _patch("root/a", 2, "a.second")]
        forward = fold(patches, {"symbols": {}}, None)
        backward = fold(list(reversed(patches)), {"symbols": {}}, None)
        shuffled = list(patches)
        random.Random(0).shuffle(shuffled)
        reshuffled = fold(shuffled, {"symbols": {}}, None)
        self.assertEqual(
            {c["subject"] for c in forward["claims"]},
            {c["subject"] for c in backward["claims"]},
        )
        self.assertEqual(
            {c["subject"] for c in forward["claims"]},
            {c["subject"] for c in reshuffled["claims"]},
        )

    def test_missing_generation_defaults_to_one_and_does_not_double_count(self) -> None:
        a = _patch("root/a", 1, "a.only")
        del a["generation"]
        b = _patch("root/a", 1, "a.only")
        del b["generation"]
        result = fold([a, b], {"symbols": {}}, None)
        # Two patches, same (defaulted) generation, same node: exactly one
        # survives -- an order-independent tiebreak, not an accumulation.
        self.assertEqual(len(result["claims"]), 1)


class ScopeHashTest(MiniRepoTest):
    def test_unchanged_content_yields_the_same_hash(self) -> None:
        scope = self.pipeline.partition["scopes"][0]
        self.assertEqual(scope_hash(self.repo, scope), scope_hash(self.repo, scope))

    def test_editing_a_file_in_the_scope_changes_its_hash(self) -> None:
        scope = next(s for s in self.pipeline.partition["scopes"] if s["files"])
        before = scope_hash(self.repo, scope)
        target = Path(self.repo) / scope["files"][0]
        original = target.read_text()
        try:
            target.write_text(original + "\n// touched\n")
            after = scope_hash(self.repo, scope)
        finally:
            target.write_text(original)
        self.assertNotEqual(before, after)

    def test_changed_scopes_reports_only_the_edited_scope(self) -> None:
        import copy

        old_part = copy.deepcopy(self.pipeline.partition)
        annotate_scope_hashes(self.repo, old_part)
        new_part = copy.deepcopy(old_part)

        edited_scope = next(s for s in new_part["scopes"] if s["files"])
        edited_scope["scope_hash"] = "deliberately-different"

        dispatch = changed_scopes(old_part, new_part)
        self.assertEqual(dispatch, {edited_scope["node"]})

    def test_no_prior_partition_means_every_scope_is_new(self) -> None:
        new_part = copy_partition_with_hashes(self)
        dispatch = changed_scopes(None, new_part)
        self.assertEqual(dispatch, {s["node"] for s in new_part["scopes"]})


def copy_partition_with_hashes(test: ScopeHashTest) -> dict:
    import copy

    part = copy.deepcopy(test.pipeline.partition)
    annotate_scope_hashes(test.repo, part)
    return part


if __name__ == "__main__":
    unittest.main()
