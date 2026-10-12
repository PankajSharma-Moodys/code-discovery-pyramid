"""Annotations in query answers (ANNOTATIONS_PLAN P3): `search` finds them by name, fqn, text or
argument value (whitespace ignored), `symbol` and `file` show them verbatim with their lines, and
a method's answer carries its owner class's annotations and its annotated parameters."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from helpers import Pipeline

from cdp.query.lookup import q_file, q_symbol
from cdp.query.render import render
from cdp.query.search import q_search

JOB = """package a.jobs;

import de.spinscale.dropwizard.jobs.annotations.Every;

@Every(jobName = "AutoScaleJob",
       value = "60s")
public class AutoScaleJob {
    public void doJob() {}
}
"""

CONTROLLER = """package a.web;

import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/c")
public class C {
    @GetMapping("/x/{id}")
    public String x(@PathVariable("id") Long id, @RequestBody String body) { return ""; }
}
"""


class _Store:
    def __init__(self, p: Pipeline) -> None:
        self.extraction, self.xref, self.inventory = p.extraction, p.xref, p.inventory
        self.state = {"claims": [], "unknowns": [], "provenance": {}}

    def node_of(self, path):
        return "root"


class QueryAnnotationsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        root = Path(cls.tmp.name) / "annrepo"
        for rel, body in (("src/main/java/a/jobs/AutoScaleJob.java", JOB),
                          ("src/main/java/a/web/C.java", CONTROLLER)):
            path = root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(body)
        (root / "build.gradle").write_text("apply plugin: 'java'\n")
        cls.store = _Store(Pipeline(root))

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def hits(self, text):
        return q_search(self.store, text)["annotations"]

    def test_search_finds_an_annotation_by_name(self):
        (hit,) = self.hits("@Every")
        self.assertEqual(hit["owner"], "a.jobs.AutoScaleJob")
        self.assertTrue(hit["text"].startswith("@Every("))
        self.assertTrue(hit["at"].endswith("AutoScaleJob.java:5-6"), hit["at"])

    def test_search_finds_an_argument_value_ignoring_whitespace(self):
        self.assertEqual([h["owner"] for h in self.hits("value = \"60s\"")], ["a.jobs.AutoScaleJob"])
        self.assertEqual([h["owner"] for h in self.hits("60s")], ["a.jobs.AutoScaleJob"])

    def test_search_finds_by_fqn(self):
        self.assertEqual(len(self.hits("dropwizard.jobs.annotations.Every")), 1)

    def test_search_reaches_parameter_annotations(self):
        owners = [h["owner"] for h in self.hits("@PathVariable")]
        self.assertEqual(owners, ["a.web.C#x(id)"])

    def test_search_reports_true_counts_and_lists_annotations_as_searched(self):
        result = q_search(self.store, "@RequestMapping")
        self.assertEqual(result["counts"]["annotations"], 1)
        self.assertIn("annotations", result["searched"])
        self.assertIn("@RequestMapping(\"/c\")", render(result))

    def test_search_miss_stays_a_miss(self):
        self.assertEqual(self.hits("@Nonexistent"), [])

    def test_symbol_shows_member_class_and_parameter_annotations(self):
        (hit,) = q_symbol(self.store, "a.web.C#x")["found"]
        self.assertEqual([a["text"] for a in hit["annotations"]], ['@GetMapping("/x/{id}")'])
        self.assertEqual([a["text"] for a in hit["class_annotations"]],
                         ["@RestController", '@RequestMapping("/c")'])
        self.assertEqual([(p["name"], p["annotations"][0]["text"]) for p in hit["params"]],
                         [("id", '@PathVariable("id")'), ("body", "@RequestBody")])
        text = render({"query": "symbol", "name": "a.web.C#x", "match": "exact", "found": [hit]})
        self.assertIn('@GetMapping("/x/{id}")', text)
        self.assertIn("class @RestController", text)

    def test_file_outline_lists_annotations_under_each_definition(self):
        (entry,) = q_file(self.store, "AutoScaleJob.java")["found"]
        job = next(d for d in entry["defines"] if d["fqn"] == "a.jobs.AutoScaleJob")
        self.assertEqual(job["annotations"][0]["at"].rsplit(":", 1)[1], "5-6")
        self.assertIn("@Every(", render({"query": "file", "path": "x", "match": "exact", "found": [entry]}))


if __name__ == "__main__":
    unittest.main()
