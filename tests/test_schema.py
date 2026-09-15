"""Schema validation and the closed vocabularies (§5.6).

Free-text categories are where determinism dies quietly: one run says
`"kind": "entrypoint"`, the next says `"entry point"`, and every downstream
aggregation, diff and stability score silently disagrees. The validator's job is
to make that loud.
"""

from __future__ import annotations

import copy
import unittest

from helpers import SKILL_ROOT

from cdp.schema import Validator, schema_path, validate_patch
from cdp.util import CdpError

VALID = {
    "schema_version": "1.0.0",
    "node": "root/core",
    "run_id": "cdp-test",
    "status": "complete",
    "claims": [
        {
            "id": "core.entrypoint.widgets",
            "kind": "entrypoint",
            "subject": "route:GET /v1/widgets",
            "channel": "http_in",
            "statement": "Exposes GET /v1/widgets returning a list of Widget DTOs.",
            "evidence": [
                {"file": "web/WidgetResource.java", "line": 9, "anchor": "@Path(ApiPaths.WIDGETS)"}
            ],
            "confidence": "high",
        }
    ],
    "unknowns": [
        {"question": "Which scopes guard this route?", "why_unresolved": "Auth is out of scope."}
    ],
}


class TestValidator(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.validator = Validator.load(schema_path(SKILL_ROOT))

    def check(self, mutate) -> list:
        patch = copy.deepcopy(VALID)
        mutate(patch)
        return validate_patch(patch, self.validator)

    def test_accepts_a_well_formed_patch(self):
        self.assertEqual(validate_patch(copy.deepcopy(VALID), self.validator), [])

    def test_rejects_an_out_of_vocabulary_kind(self):
        errors = self.check(lambda p: p["claims"][0].__setitem__("kind", "entry point"))
        self.assertTrue(any("not one of" in e for e in errors))

    def test_rejects_an_invented_channel(self):
        errors = self.check(lambda p: p["claims"][0].__setitem__("channel", "grpc"))
        self.assertTrue(any("not one of" in e for e in errors))

    def test_rejects_an_anchor_below_the_length_floor(self):
        errors = self.check(lambda p: p["claims"][0]["evidence"][0].__setitem__("anchor", "@Entity"))
        self.assertTrue(any("shorter than 12" in e for e in errors))

    def test_rejects_a_claim_with_no_evidence(self):
        errors = self.check(lambda p: p["claims"][0].__setitem__("evidence", []))
        self.assertTrue(any("at least 1" in e for e in errors))

    def test_rejects_a_claim_with_no_subject(self):
        # §5.5's conflict detection is defined on `subject`; a claim without one
        # cannot participate in merge at all.
        errors = self.check(lambda p: p["claims"][0].pop("subject"))
        self.assertTrue(any("subject" in e for e in errors))

    def test_rejects_an_unexpected_property(self):
        errors = self.check(lambda p: p["claims"][0].__setitem__("certainty", 0.9))
        self.assertTrue(any("unexpected property" in e for e in errors))

    def test_rejects_a_malformed_claim_id(self):
        errors = self.check(lambda p: p["claims"][0].__setitem__("id", "Core Entrypoint"))
        self.assertTrue(any("does not match" in e for e in errors))

    def test_rejects_a_schema_version_mismatch(self):
        # A run whose patches disagree with the orchestrator's schema version is
        # refused rather than coerced: silent coercion is how a "closed"
        # vocabulary quietly opens.
        errors = self.check(lambda p: p.__setitem__("schema_version", "1.1.0"))
        self.assertTrue(errors)

    def test_an_agent_may_not_declare_a_claim_contested(self):
        # 'contested' is a set-valued outcome the merge operator produces. An
        # agent asserting it would be claiming to have seen a disagreement it
        # has no scope to observe.
        errors = self.check(lambda p: p["claims"][0].__setitem__("confidence", "contested"))
        self.assertTrue(any("merge operator" in e for e in errors))


class TestValidatorRefusesWhatItCannotCheck(unittest.TestCase):
    def test_an_unsupported_keyword_raises_rather_than_being_ignored(self):
        # A validator that silently skips a keyword it does not implement lets
        # out-of-vocabulary values through while reporting success, which is
        # worse than having no validator.
        with self.assertRaises(CdpError):
            Validator({"type": "object", "properties": {"x": {"oneOf": [{"type": "string"}]}}})

    def test_a_dangling_ref_raises(self):
        with self.assertRaises(CdpError):
            Validator({"type": "object", "properties": {"x": {"$ref": "#/$defs/missing"}}}).validate({"x": 1})


if __name__ == "__main__":
    unittest.main()
