"""Annotations in query answers (ANNOTATIONS_PLAN P3): `search` finds them by name, fqn, text or
argument value (whitespace ignored), `symbol` and `file` show them verbatim with their lines, and
a method's answer carries its owner class's annotations and its annotated parameters."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from helpers import Pipeline

from cdp.query.lookup import q_config, q_file, q_routes, q_symbol, q_table
from cdp.query.render import render
from cdp.query.search import q_search
from cdp.query.trace import q_trace

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
    public String x(@PathVariable("id") Long id, @RequestBody String body) { return svc.load(id); }
    private final a.svc.OrderService svc = null;
}
"""

SERVICE = """package a.svc;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

@Service("orders")
public class OrderService {
    @Value("${orders.url:http://x}")
    private String url;

    public String load(Long id) { return url; }
}
"""

ENTITY = """package a.svc;

import javax.persistence.Entity;
import javax.persistence.Table;

@Entity
@Table(name = "orders")
public class OrderEntity {
    Long id;
}
"""


class _Store:
    def __init__(self, p: Pipeline) -> None:
        self.extraction, self.xref, self.inventory = p.extraction, p.xref, p.inventory
        self.dataflow = p.dataflow
        self.state = {"claims": [], "unknowns": [], "provenance": {}}

    def node_of(self, path):
        return "root"


class QueryAnnotationsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        root = Path(cls.tmp.name) / "annrepo"
        for rel, body in (("src/main/java/a/jobs/AutoScaleJob.java", JOB),
                          ("src/main/java/a/web/C.java", CONTROLLER),
                          ("src/main/java/a/svc/OrderService.java", SERVICE),
                          ("src/main/java/a/svc/OrderEntity.java", ENTITY)):
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

    def test_routes_carry_the_handlers_annotations(self):
        (row,) = q_routes(self.store, "/x")["routes"]
        self.assertEqual([a["text"] for a in row["annotations"]], ['@GetMapping("/x/{id}")'])
        self.assertEqual([a["text"] for a in row["class_annotations"]], ["@RestController", '@RequestMapping("/c")'])
        self.assertEqual([p["name"] for p in row["params"]], ["id", "body"])
        text = render({"query": "routes", "count": 1, "routes": [row], "match": "all"})
        self.assertIn('@GetMapping("/x/{id}")', text)
        self.assertIn("class @RestController", text)

    def test_table_code_group_carries_annotations_and_script_group_none(self):
        (t,) = q_table(self.store, "orders")["tables"]
        groups = t["writers"] + t["readers"]
        g = next(g for g in groups if g["fqn"] == "a.svc.OrderEntity")
        self.assertEqual([a["text"] for a in g["annotations"]], ["@Entity", '@Table(name="orders")'])
        self.assertTrue(all("annotations" not in g for g in groups if g["kind"] == "script"))
        text = render({"query": "table", "count": 1, "tables": [t], "match": "all"})
        self.assertIn('@Table(name="orders")', text)

    def test_config_read_site_carries_its_reader_annotations(self):
        (key,) = q_config(self.store, "orders.url")["keys"]
        site = next(r for r in key["read"] if r["by"].startswith("a.svc.OrderService"))
        # Config reads are attributed to the class, so its own annotations are the reader's.
        self.assertEqual([a["text"] for a in site["annotations"]], ['@Service("orders")'])

    def test_trace_entry_and_hops_carry_annotations_where_one_symbol_is_cited(self):
        result = q_trace(self.store, "a.svc.OrderService#load")
        self.assertEqual([a["text"] for a in result["resolved_as"]["annotations"]], ['@Service("orders")'])
        route = q_trace(self.store, "/x/{id}")
        self.assertEqual([a["text"] for a in route["resolved_as"]["annotations"]], ['@GetMapping("/x/{id}")'])
        cited = [r for r in route["files"] if r.get("symbol")]
        self.assertTrue(cited, route["files"])
        for r in cited:
            self.assertTrue(r["why"].startswith("defines "))
            self.assertEqual([a["text"] for a in r["class_annotations"]], ['@Service("orders")'])
        self.assertTrue(all("annotations" not in r and "class_annotations" not in r
                            for r in route["files"] if not r.get("symbol")))
        self.assertIn("@Service", render(route))


if __name__ == "__main__":
    unittest.main()
