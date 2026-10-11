"""L10: bounded reflect values, claim-level holdout verdicts, per-repo lesson resolution."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from cdp import holdout as holdout_mod, reflect as reflect_mod
from cdp.trajectory import TrajectoryStore


def _arm(**kw):
    base = {"scopes": 4, "claims": 10, "t3_rate": 0.25, "tokens_est": 1000, "elided_claims": 0,
            "elided_verified": 0, "elision_regret": 0, "entailed_rate": 0.5, "consistent_rate": 0.5,
            "contradicted_rate": 0.0, "claims_per_ktok": 10.0}
    return dict(base, **kw)


class AbsurdValuesTest(unittest.TestCase):
    def test_absurd_budget_values_are_rejected_and_never_applied(self):
        for bad in (-999999, 0, 10 ** 9, True, "5"):
            err = reflect_mod.validate_promotion({"promotion": "budget_change", "parameter": "max_inherited", "new_value": bad})
            self.assertIsNotNone(err, bad)
        self.assertIsNone(reflect_mod.validate_promotion(
            {"promotion": "budget_change", "parameter": "max_inherited", "new_value": 100}))
        # a row stored before the bound existed must not reach a prompt either
        hints = reflect_mod.apply_lessons([{"payload": {"promotion": "budget_change", "parameter": "max_inherited",
                                                        "new_value": -999999}}])
        self.assertIsNone(hints["max_inherited"])


class HoldoutVerdictTest(unittest.TestCase):
    def test_a_lesson_that_loses_verified_claims_or_raises_contradictions_is_rejected(self):
        ok, why = holdout_mod.compare(_arm(), _arm())
        self.assertTrue(ok, why)
        for field, worse in (("elided_verified", 3), ("elision_regret", 1), ("t3_rate", 0.5), ("contradicted_rate", 0.1)):
            ok, why = holdout_mod.compare(_arm(), _arm(**{field: worse}))
            self.assertFalse(ok, field)
            self.assertIn(field, why)

    def test_cost_growth_beyond_the_slack_is_a_regression_and_a_repo_without_claims_cannot_be_judged(self):
        self.assertFalse(holdout_mod.compare(_arm(), _arm(tokens_est=1300))[0])
        self.assertTrue(holdout_mod.compare(_arm(), _arm(tokens_est=1050))[0])
        self.assertFalse(holdout_mod.compare(_arm(claims=0), _arm(claims=0))[0])

    def test_prompt_fix_cannot_be_measured(self):
        self.assertEqual(holdout_mod.unmeasurable([{"kind": "prompt_fix"}, {"kind": "budget_change"}]), ["prompt_fix"])


class PerRepoResolutionTest(unittest.TestCase):
    def test_a_cut_applies_to_its_repos_only_and_holdouts_accumulate(self):
        with tempfile.TemporaryDirectory() as tmp:
            with TrajectoryStore(Path(tmp) / "t.db") as t:
                t.record_leaf_run(run_id="r", node="n", scope_hash="h", repo_id="repo-A", model="m",
                                  scope_shape_key="s", template_version="1", tier="T2", task_kind="scope", state="folded")
                t.record_promotion(run_id="r", node="n", promotion={"promotion": "budget_change",
                                                                     "parameter": "max_inherited", "new_value": 50})
                v = t.cut_lessons()
                t.promote_cut(v, "repo-B", {})
                t.promote_cut(v, "repo-C", {})
                self.assertEqual(t.latest_lesson_version("repo-A"), v)
                self.assertEqual(t.latest_lesson_version("repo-B"), v)
                self.assertEqual(t.latest_lesson_version("repo-C"), v)
                self.assertIsNone(t.latest_lesson_version("repo-D"))


if __name__ == "__main__":
    unittest.main()
