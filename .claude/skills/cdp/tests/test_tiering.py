"""Phase 6 (M6.4) — tiering v1: the rule, not the score."""

import unittest

from cdp.tiering import (
    apply_leaf_escalation,
    build_symbol_index_for_tiering,
    compute_tier,
    scope_unresolved_imports,
)


def _extraction(imports):
    return {"imports": imports, "defines": []}


class ScopeUnresolvedImportsTest(unittest.TestCase):
    def test_internal_import_is_not_unresolved(self):
        extraction = _extraction([
            {"file": "a/A.java", "module": "a", "fqn": "b.B", "anchor": "a/A.java:1"},
        ])
        symbol_owner, namespace_owner = build_symbol_index_for_tiering(
            {"defines": [{"fqn": "b.B", "module": "b", "kind": "class"}]}
        )
        scope = {"module": "a", "files": ["a/A.java"]}
        count = scope_unresolved_imports(scope, extraction, {"a", "b"}, symbol_owner, namespace_owner)
        self.assertEqual(count, 0)

    def test_third_party_import_is_not_unresolved(self):
        extraction = _extraction([
            {"file": "a/A.java", "module": "a", "fqn": "com.google.common.base.Strings",
             "anchor": "a/A.java:1"},
        ])
        symbol_owner, namespace_owner = build_symbol_index_for_tiering({"defines": []})
        scope = {"module": "a", "files": ["a/A.java"]}
        count = scope_unresolved_imports(scope, extraction, {"a"}, symbol_owner, namespace_owner)
        self.assertEqual(count, 0)

    def test_unresolved_internal_looking_import_counts(self):
        extraction = _extraction([
            {"file": "a/A.java", "module": "a", "fqn": "a.internal.Ghost", "anchor": "a/A.java:2"},
        ])
        symbol_owner, namespace_owner = build_symbol_index_for_tiering({"defines": []})
        scope = {"module": "a", "files": ["a/A.java"]}
        count = scope_unresolved_imports(scope, extraction, {"a"}, symbol_owner, namespace_owner)
        self.assertEqual(count, 1)

    def test_import_outside_scope_files_is_ignored(self):
        extraction = _extraction([
            {"file": "a/Other.java", "module": "a", "fqn": "a.internal.Ghost", "anchor": "a/Other.java:2"},
        ])
        symbol_owner, namespace_owner = build_symbol_index_for_tiering({"defines": []})
        scope = {"module": "a", "files": ["a/A.java"]}
        count = scope_unresolved_imports(scope, extraction, {"a"}, symbol_owner, namespace_owner)
        self.assertEqual(count, 0)


class ComputeTierTest(unittest.TestCase):
    def test_default_is_t2(self):
        extraction = _extraction([
            {"file": "a/A.java", "module": "a", "fqn": "com.google.common.base.Strings",
             "anchor": "a/A.java:1"},
        ])
        symbol_owner, namespace_owner = build_symbol_index_for_tiering({"defines": []})
        scope = {"module": "a", "files": ["a/A.java"]}
        row = compute_tier(scope, extraction, {"a"}, symbol_owner, namespace_owner)
        self.assertEqual(row, {"tier": "T2", "reason": None, "unresolved_imports": 0})

    def test_unresolved_import_escalates_to_t3(self):
        extraction = _extraction([
            {"file": "a/A.java", "module": "a", "fqn": "a.internal.Ghost", "anchor": "a/A.java:2"},
        ])
        symbol_owner, namespace_owner = build_symbol_index_for_tiering({"defines": []})
        scope = {"module": "a", "files": ["a/A.java"]}
        row = compute_tier(scope, extraction, {"a"}, symbol_owner, namespace_owner)
        self.assertEqual(row["tier"], "T3")
        self.assertEqual(row["reason"], "unresolved_imports")
        self.assertEqual(row["unresolved_imports"], 1)


class ApplyLeafEscalationTest(unittest.TestCase):
    def test_escalated_claim_upgrades_t2_to_t3(self):
        tiering = {"root/a": {"tier": "T2", "reason": None, "unresolved_imports": 0}}
        upgraded = apply_leaf_escalation(tiering, "root/a", [{"escalated": True}])
        self.assertTrue(upgraded)
        self.assertEqual(tiering["root/a"]["tier"], "T3")
        self.assertEqual(tiering["root/a"]["reason"], "leaf_escalated")

    def test_no_escalated_claim_is_a_no_op(self):
        tiering = {"root/a": {"tier": "T2", "reason": None, "unresolved_imports": 0}}
        upgraded = apply_leaf_escalation(tiering, "root/a", [{"escalated": False}, {}])
        self.assertFalse(upgraded)
        self.assertEqual(tiering["root/a"]["tier"], "T2")

    def test_existing_t3_reason_is_not_overwritten(self):
        tiering = {"root/a": {"tier": "T3", "reason": "unresolved_imports", "unresolved_imports": 1}}
        upgraded = apply_leaf_escalation(tiering, "root/a", [{"escalated": True}])
        self.assertFalse(upgraded)
        self.assertEqual(tiering["root/a"]["reason"], "unresolved_imports")

    def test_missing_node_defaults_to_t2_then_upgrades(self):
        tiering = {}
        upgraded = apply_leaf_escalation(tiering, "root/new", [{"escalated": True}])
        self.assertTrue(upgraded)
        self.assertEqual(tiering["root/new"]["tier"], "T3")


if __name__ == "__main__":
    unittest.main()
