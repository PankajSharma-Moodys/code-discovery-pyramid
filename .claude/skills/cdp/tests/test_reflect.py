"""Phase 9 (M9.3, 6.6 only) -- outlier reflection."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import helpers  # noqa: F401 -- adds the repo root to sys.path for `cdp`

from cdp.reflect import (
    PROMOTION_KINDS,
    apply_lessons,
    reflect,
    select_outliers,
    validate_promotion,
)


class ApplyLessonsTest(unittest.TestCase):
    """M9.3 (6.8): the missing consumer -- turns cut, pinned promotion rows
    into the two routing knobs `prompts.py`/`graph.py` actually expose."""

    def test_import_channel_hint_patterns_union(self):
        lessons = [
            {"node": "a", "kind": "import_channel_hint",
             "payload": {"promotion": "import_channel_hint", "pattern": "com.acme.sdk", "channel": "call"}},
            {"node": "b", "kind": "import_channel_hint",
             "payload": {"promotion": "import_channel_hint", "pattern": "org.foo.lib", "channel": "call"}},
        ]
        hints = apply_lessons(lessons)
        self.assertEqual(hints["third_party_patterns"], frozenset({"com.acme.sdk", "org.foo.lib"}))
        self.assertIsNone(hints["max_inherited"])

    def test_last_budget_change_wins(self):
        lessons = [
            {"payload": {"promotion": "budget_change", "parameter": "max_inherited", "new_value": 5}},
            {"payload": {"promotion": "budget_change", "parameter": "max_inherited", "new_value": 9}},
        ]
        self.assertEqual(apply_lessons(lessons)["max_inherited"], 9)

    def test_prompt_fix_carries_no_claim_shaped_field(self):
        lessons = [{"payload": {"promotion": "prompt_fix", "section": "gaps", "instruction": "be terse"}}]
        fixes = apply_lessons(lessons)["prompt_fixes"]
        self.assertEqual(fixes, [{"section": "gaps", "instruction": "be terse"}])

    def test_no_lessons_is_a_no_op(self):
        hints = apply_lessons([])
        self.assertEqual(hints["third_party_patterns"], frozenset())
        self.assertIsNone(hints["max_inherited"])


class SelectOutliersTest(unittest.TestCase):
    def test_contradicted_scope_is_an_outlier(self):
        rows = [{"node": "a", "contradicted": 1, "tokens_est": 100, "claims_emitted": 5}]
        out = select_outliers(rows)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["reason"], "high_contradiction")

    def test_high_spend_zero_yield_is_an_outlier(self):
        rows = [{"node": "a", "contradicted": 0, "tokens_est": 9000, "claims_emitted": 0}]
        out = select_outliers(rows)
        self.assertEqual(out[0]["reason"], "high_spend_low_yield")

    def test_ordinary_scope_is_not_an_outlier(self):
        rows = [{"node": "a", "contradicted": 0, "tokens_est": 200, "claims_emitted": 3}]
        self.assertEqual(select_outliers(rows), [])

    def test_capped_at_limit_worst_first(self):
        rows = [{"node": "low", "contradicted": 1, "tokens_est": 10},
                {"node": "high", "contradicted": 5, "tokens_est": 10}]
        out = select_outliers(rows, limit=1)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["node"], "high")


class ValidatePromotionTest(unittest.TestCase):
    def test_none_is_discarded_as_unactionable(self):
        self.assertEqual(validate_promotion({"promotion": "none"}), "no actionable promotion")

    def test_unrecognised_kind_is_rejected(self):
        self.assertIsNotNone(validate_promotion({"promotion": "add_a_lesson"}))

    def test_valid_import_channel_hint(self):
        self.assertIsNone(validate_promotion(
            {"promotion": "import_channel_hint", "pattern": "com.acme.config.*", "channel": "config"}
        ))

    def test_valid_prompt_fix(self):
        self.assertIsNone(validate_promotion(
            {"promotion": "prompt_fix", "section": "gaps", "instruction": "cap gaps section at 20 lines"}
        ))

    def test_valid_budget_change(self):
        self.assertIsNone(validate_promotion(
            {"promotion": "budget_change", "parameter": "max_inherited", "new_value": 12}
        ))

    def test_prompt_fix_rejects_an_unknown_section(self):
        err = validate_promotion({"promotion": "prompt_fix", "section": "vibes", "instruction": "x"})
        self.assertIn("section", err)

    def test_budget_change_rejects_an_unknown_parameter(self):
        err = validate_promotion({"promotion": "budget_change", "parameter": "temperature", "new_value": 1})
        self.assertIn("parameter", err)

    def test_r10_a_claim_shaped_payload_is_structurally_impossible(self):
        """R10: learning may steer routing, never claim content. A model
        cannot smuggle a claim (subject/anchor/evidence/kind='naming', etc.)
        through a promotion -- the closed per-kind allowlist rejects any
        extra field, and 'none' is the only kind with no fields at all."""
        smuggled = {
            "promotion": "budget_change", "parameter": "max_inherited", "new_value": 5,
            "subject": "Foo.bar", "anchor": "Foo.java:10", "evidence": "trust me",
        }
        err = validate_promotion(smuggled)
        self.assertIsNotNone(err)
        self.assertIn("R10", err)

    def test_not_a_dict_is_rejected(self):
        self.assertIsNotNone(validate_promotion("just a vague lesson in prose"))


class _FakeResult:
    def __init__(self, ok, error=None):
        self.ok = ok
        self.error = error
        self.wall_ms = 1


class _WritesPromotion:
    def __init__(self, promotion):
        self.promotion = promotion

    def run(self, prompt_path, out_path):
        Path(out_path).write_text(json.dumps(self.promotion))
        return _FakeResult(ok=True)


class _RunnerFails:
    def run(self, prompt_path, out_path):
        return _FakeResult(ok=False, error="boom")


class _WritesNothing:
    def run(self, prompt_path, out_path):
        return _FakeResult(ok=True)


class ReflectEndToEndTest(unittest.TestCase):
    def test_accepted_promotion_round_trips(self):
        with tempfile.TemporaryDirectory() as tmp:
            outliers = [{"node": "root/gateway", "reason": "high_contradiction",
                         "tokens_est": 1000, "claims_emitted": 0, "contradicted": 2}]
            runner = _WritesPromotion(
                {"promotion": "prompt_fix", "section": "inherited", "instruction": "narrow the fan-in sort"}
            )
            accepted, discarded = reflect(outliers, runner, Path(tmp))
            self.assertEqual(discarded, [])
            self.assertEqual(len(accepted), 1)
            self.assertEqual(accepted[0]["promotion"]["promotion"], "prompt_fix")

    def test_runner_failure_is_discarded_with_a_reason(self):
        with tempfile.TemporaryDirectory() as tmp:
            outliers = [{"node": "root/a", "reason": "high_contradiction", "contradicted": 1}]
            accepted, discarded = reflect(outliers, _RunnerFails(), Path(tmp))
            self.assertEqual(accepted, [])
            self.assertIn("runner failure", discarded[0]["reason"])

    def test_no_output_written_is_discarded(self):
        with tempfile.TemporaryDirectory() as tmp:
            outliers = [{"node": "root/a", "reason": "high_contradiction", "contradicted": 1}]
            accepted, discarded = reflect(outliers, _WritesNothing(), Path(tmp))
            self.assertEqual(accepted, [])
            self.assertIn("no reflection", discarded[0]["reason"])

    def test_unactionable_reflection_is_discarded_not_stored_as_a_lesson(self):
        with tempfile.TemporaryDirectory() as tmp:
            outliers = [{"node": "root/a", "reason": "high_spend_low_yield", "contradicted": 0}]
            accepted, discarded = reflect(outliers, _WritesPromotion({"promotion": "none"}), Path(tmp))
            self.assertEqual(accepted, [])
            self.assertEqual(discarded[0]["reason"], "no actionable promotion")


if __name__ == "__main__":
    unittest.main()
