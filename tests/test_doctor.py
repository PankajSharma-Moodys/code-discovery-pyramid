"""M6.1 -- `cdp doctor` scores a runner's patch against the hand-authored
minirepo golden set. Two fake runners stand in for the acceptance criterion's
"at least one model fails false-unknown rate while passing recall": a
well-behaved one and a collapsed (all-unknowns) one.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from helpers import Pipeline, make_repo

from cdp.doctor import GOLDEN_MINIREPO, aggregate, doctor_scope
from cdp.schema import Validator, schema_path
from cdp.runner import RunResult

SKILL_ROOT = Path(__file__).resolve().parent.parent


class ScriptedRunner:
    """Writes a fixed patch dict for whichever node it is asked about,
    matched by reading the prompt file's header for the node name."""

    def __init__(self, patch_by_node):
        self.patch_by_node = patch_by_node

    def run(self, prompt_path, patch_path):
        text = prompt_path.read_text()
        node = next(n for n in self.patch_by_node if n in text)
        patch_path.write_text(json.dumps(self.patch_by_node[node]))
        return RunResult(ok=True, wall_ms=1)


class CollapseRunner:
    """Emits schema-valid patches with zero claims and an unknown per gold
    subject -- the false-unknown-rate failure mode doctor exists to catch."""

    def __init__(self, node_subjects):
        self.node_subjects = node_subjects

    def run(self, prompt_path, patch_path):
        text = prompt_path.read_text()
        node = next(n for n in self.node_subjects if n in text)
        patch = {
            "schema_version": "1.0.0", "node": node, "run_id": "doctor-test",
            "status": "complete", "claims": [],
            "unknowns": [
                {"question": "what does %s do?" % subj, "why_unresolved": "collapsed",
                 "subject": subj}
                for subj in self.node_subjects[node]
            ],
        }
        patch_path.write_text(json.dumps(patch))
        return RunResult(ok=True, wall_ms=1)


GOOD_PATCHES = {
    "core": {
        "schema_version": "1.0.0", "node": "core", "run_id": "doctor-test", "status": "complete",
        "claims": [
            {
                "id": "core.widget_repository.no_custom", "kind": "public_api",
                "subject": "com.example.mini.core.WidgetRepository",
                "statement": "WidgetRepository declares no custom query methods; every "
                             "operation is inherited CRUD from JpaRepository.",
                "evidence": [{"file": "core/src/main/java/COM/Example/mini/core/WidgetRepository.java",
                              "line": 7, "anchor": "extends JpaRepository<WidgetEntity, Long> {}"}],
                "confidence": "high",
            },
            {
                "id": "core.widget.duplicate", "kind": "naming",
                "subject": "com.example.mini.core.Widget",
                "statement": "com.example.mini.core.Widget is a duplicate FQN across main and test.",
                "evidence": [{"file": "core/src/test/java/com/example/mini/core/Widget.java",
                              "line": 4, "anchor": "public class Widget {"}],
                "confidence": "high",
            },
        ],
        "unknowns": [],
    },
    "web": {
        "schema_version": "1.0.0", "node": "web", "run_id": "doctor-test", "status": "complete",
        "claims": [
            {
                "id": "web.widget_resource.empty", "kind": "test_behaviour",
                "subject": "com.example.mini.web.WidgetResource",
                "statement": "WidgetResource.list() always returns an empty list.",
                "evidence": [{"file": "web/src/main/java/com/example/mini/web/WidgetResource.java",
                              "line": 21, "anchor": "return List.of();"}],
                "confidence": "high",
            },
            {
                "id": "web.web_application.log", "kind": "entrypoint",
                "subject": "com.example.mini.web.WebApplication",
                "statement": "WebApplication only prints a startup log line.",
                "evidence": [{"file": "web/src/main/java/com/example/mini/web/WebApplication.java",
                              "line": 6, "anchor": "System.out.println(\"mini-svc web starting\");"}],
                "confidence": "high",
            },
        ],
        "unknowns": [],
    },
}


class DoctorTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        repo = make_repo(Path(self.tmp.name))
        self.pipeline = Pipeline(repo)
        self.repo = repo
        self.validator = Validator.load(schema_path(SKILL_ROOT))
        self.scratch = Path(self.tmp.name) / "scratch"
        self.scratch.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def _run_all_scopes(self, runner):
        reports = []
        for scope in self.pipeline.partition["scopes"]:
            golden = GOLDEN_MINIREPO.get(scope["module"], [])
            reports.append(doctor_scope(
                scope, self.pipeline.inventory, self.pipeline.extraction,
                self.pipeline.xref, self.pipeline.schedule, [], "doctor-test",
                runner, self.repo, self.scratch / "prompt.md", self.scratch / "patch.json",
                self.validator, golden,
            ))
        return reports

    def test_well_formed_patches_score_full_recall_and_zero_false_unknown(self):
        reports = self._run_all_scopes(ScriptedRunner(GOOD_PATCHES))
        agg = aggregate(reports)
        self.assertEqual(agg["recall"], 1.0)
        self.assertEqual(agg["false_unknown_rate"], 0.0)
        self.assertEqual(agg["schema_validity_rate"], 1.0)
        self.assertGreater(agg["golden_total"], 0)

    def test_yield_collapse_is_caught_by_false_unknown_rate_not_masked_by_precision(self):
        node_subjects = {
            module: [f["subject_contains"] for f in facts]
            for module, facts in GOLDEN_MINIREPO.items()
        }
        reports = self._run_all_scopes(CollapseRunner(node_subjects))
        agg = aggregate(reports)
        # Recall alone would score this model perfectly (zero false claims);
        # false-unknown rate is the metric that must instead read 1.0.
        self.assertEqual(agg["recall"], 0.0)
        self.assertEqual(agg["false_unknown_rate"], 1.0)
        self.assertEqual(agg["schema_validity_rate"], 1.0)

    def test_a_runner_that_writes_nothing_is_reported_as_empty_not_a_crash(self):
        class SilentRunner:
            def run(self, prompt_path, patch_path):
                return RunResult(ok=True, wall_ms=1)

        reports = self._run_all_scopes(SilentRunner())
        for r in reports:
            self.assertTrue(r["empty"])
            self.assertFalse(r["schema_valid"])


if __name__ == "__main__":
    unittest.main()
