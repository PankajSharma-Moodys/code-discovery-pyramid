"""Lane 4: rule gates open for Scala rows (`languages` family key, JVM_LANGS), Java unchanged, JDBI Scala SQL text."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from helpers import extraction_of
from cdp import rules
from cdp.lang.base import ExtractContext
from cdp.lang.java import JavaExtractor

JDBI = ('package a;\nimport org.jdbi.v3.sqlobject.statement.SqlQuery;\n'
        'interface D {\n  @SqlQuery("select * from server where id = :id") X a(long id);\n}\n')
JPA = ('package a;\nimport org.springframework.data.jpa.repository.Query;\n'
       'interface R {\n  @Query(value = "select * from server", nativeQuery = true)\n  X a();\n}\n')
WEB = ('package a;\nimport org.springframework.web.bind.annotation.GetMapping;\n'
       'class C {\n  @GetMapping("/x") String x() { return ""; }\n}\n')


def run(src: str, language: str, path: str = "a/C.java"):
    facts = JavaExtractor().extract(ExtractContext(path, src.split("\n"), "a"))
    facts.language = language
    return sorted((e["target"], e["rule"]) for e in rules.all_edges(extraction_of(facts)) if e.get("rule"))


class GateTest(unittest.TestCase):
    def test_java_unchanged(self):
        self.assertEqual(run(JDBI, "java"), [("table:server", "sql.jdbi")])
        self.assertEqual(run(JPA, "java"), [("table:server", "sql.spring_data.native")])

    def test_scala_gate_opens_for_listed_families(self):
        self.assertEqual(run(JDBI, "scala", "a/C.scala"), [("table:server", "sql.jdbi")])

    def test_spring_data_native_is_in_a_scala_family(self):
        self.assertEqual(run(JPA, "scala", "a/C.scala"), [("table:server", "sql.spring_data.native")])

    def test_java_only_family_stays_closed_for_scala(self):
        self.assertTrue(run(WEB, "java"))
        self.assertEqual(run(WEB, "scala", "a/C.scala"), [])

    def test_other_language_closed(self):
        self.assertEqual(run(JDBI, "kotlin", "a/C.kt"), [])

    def test_signals_refreshed_for_scala_file(self):
        facts = JavaExtractor().extract(ExtractContext("a/C.scala", JDBI.split("\n"), "a"))
        facts.language = "scala"
        ex = extraction_of(facts)
        self.assertEqual(ex["files"]["a/C.scala"]["io_edges"], 1)


class SchemaTest(unittest.TestCase):
    def fam(self, **kw):
        d = Path(tempfile.mkdtemp())
        body = {"family": "x", "rules": [{"id": "x.r", "match": {"fqn": "a.B", "on": "class"},
                                          "emit": {"channel": "read", "target": "t:{value}"}}]}
        body.update(kw)
        (d / "x.json").write_text(json.dumps(body))
        return rules.load_rules(d)[0]

    def test_string_list_and_default(self):
        self.assertEqual(self.fam(language="java")["languages"], {"java"})
        self.assertEqual(self.fam(languages=["java", "scala"])["languages"], {"java", "scala"})
        self.assertEqual(self.fam()["languages"], {"java"})

    def test_bad_languages(self):
        with self.assertRaises(rules.RuleError):
            self.fam(languages=[""])

    def test_shipped_families(self):
        by = {}
        for r in rules.builtin_rules():
            by.setdefault(r["family"], set()).update(r["languages"])
        for f in ("jaxrs", "scheduling", "sql_annotations", "messaging", "http_clients", "spring_config"):
            self.assertEqual(by[f], {"java", "scala"}, f)
        for f in ("jpa", "spring_web"):
            self.assertEqual(by[f], {"java"}, f)


class ScalaSqlTextTest(unittest.TestCase):
    def test_triple_quoted_stripmargin(self):
        text = ('"""\n      |select a.id\n      |  from workflow w\n      |  INNER JOIN label AS l ON upper(w.n) = upper(l.n)'
                '""".stripMargin')
        self.assertEqual(rules._native_sql_edges(text), [("table:workflow", "read"), ("table:label", "read")])

    def test_triple_quoted_write_and_interpolator(self):
        self.assertEqual(rules._native_sql_edges('"""insert into job_rec (a)\n  |values (:a)\n  |""".stripMargin'),
                         [("table:job_rec", "persist")])
        self.assertEqual(rules._native_sql_edges('s"""update job set a = 1\n |where id = :id""".stripMargin'),
                         [("table:job", "persist")])

    def test_plain_and_java_text_unchanged(self):
        self.assertEqual(rules._sql_text("select a || b from t"), "select a || b from t")
        self.assertEqual(rules._sql_text("select a\n  || b from t"), "select a\n  || b from t")
        self.assertEqual(rules._native_sql_edges("select * from server"), [("table:server", "read")])


if __name__ == "__main__":
    unittest.main()
