"""Rule gates driven by REAL `ScalaExtractor` rows (test_jvm_gates.py relabels Java output as Scala).

Sources mirror ~/git/workflow-service: StatusWorkflowResource.scala (@Path/@GET), JobDao.scala (@SqlUpdate
with `"..." +` concatenation), CleanupJob.scala (companion object + @DelayStart/@Every/@DisallowConcurrentExecution).
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from helpers import extraction_of, make_repo, Pipeline  # noqa: F401
from cdp import rules, schedfacts
from cdp.lang.base import ExtractContext
from cdp.lang.scala import ScalaExtractor

REST = '''package com.x.api

import jakarta.ws.rs._
import jakarta.ws.rs.core.MediaType

@Path("/status")
@Produces(Array(MediaType.APPLICATION_JSON))
class StatusResource {

  @GET
  @Path("/workflows")
  def getWorkflows(@QueryParam("id") id: Long): String = ""

  @POST
  @Path("/submit")
  def submit(): String = ""
}
'''

COMPANION = '''package com.x.api

import jakarta.ws.rs._

object StatusResource {
  final val Name = "x"
}

@Path("/status")
class StatusResource {
  @GET
  @Path("/ping")
  def ping(): String = ""
}
'''

DAO_SINGLE = '''package com.x.dal

import org.jdbi.v3.sqlobject.statement.SqlQuery

trait ServerDao {
  @SqlQuery("select * from server where id = :id")
  def one(id: Long): String
}
'''

DAO_PLUS = '''package com.x.dal

import org.jdbi.v3.sqlobject.statement.SqlUpdate

trait JobDao {
  @SqlUpdate(
    "UPDATE job " +
      "SET status = 'Created', " +
      "started = null " +
      "WHERE tenant_id = :tenant_id AND job.id = :job_id"
  )
  def reset(tenant: String, job: String): Int
}
'''

DAO_TRIPLE = '''package com.x.dal

import org.jdbi.v3.sqlobject.statement.SqlQuery

trait LabelDao {
  @SqlQuery("""
      |select l.id
      |  from label l
      |  join workflow w on w.id = l.wid
      |""".stripMargin)
  def ids(): List[Long]
}
'''

JOB = '''package com.x.quartz

import io.dropwizard.jobs.annotations.Every.MisfirePolicy
import io.dropwizard.jobs.annotations.{DelayStart, Every}
import org.quartz.DisallowConcurrentExecution

object CleanupJob {
  final val CleanupJobName = "CleanupJob"
}

@DelayStart("5s")
@Every(jobName = CleanupJobName, misfirePolicy = MisfirePolicy.NOW_WITH_REMAINING_COUNT, value = "20s")
@DisallowConcurrentExecution
class CleanupJob(groupName: String) extends AbstractJob(groupName) {
  def run(): Unit = {}
}
'''

JPA = '''package com.x

import org.springframework.data.jpa.repository.Query
import org.springframework.web.bind.annotation.GetMapping

class C {
  @GetMapping("/x")
  def x(): String = ""
}
'''


def scala_extraction(src: str, path: str = "src/main/scala/com/x/F.scala"):
    facts = ScalaExtractor().extract(ExtractContext(path, src.split("\n"), "m"))
    return facts, extraction_of(facts)


def rule_edges(src: str):
    facts, ex = scala_extraction(src)
    assert facts.language == "scala", facts.language
    return sorted((e["target"], e["rule"]) for e in rules.all_edges(ex) if e.get("rule"))


class JaxrsScalaTest(unittest.TestCase):
    def test_routes_joined_path(self):
        got = rule_edges(REST)
        targets = {t for t, _ in got}
        self.assertEqual(targets, {"route:GET /status/workflows", "route:POST /status/submit"}, got)

    def test_companion_object_before_class(self):
        facts, ex = scala_extraction(COMPANION)
        self.assertEqual(facts.primary, "com.x.api.StatusResource")
        targets = {e["target"] for e in rules.all_edges(ex) if e.get("rule")}
        self.assertIn("route:GET /status/ping", targets)


class SqlScalaTest(unittest.TestCase):
    def test_single_line(self):
        self.assertEqual([t for t, _ in rule_edges(DAO_SINGLE)], ["table:server"])

    def test_plus_concatenation(self):
        self.assertEqual([t for t, _ in rule_edges(DAO_PLUS)], ["table:job"])

    def test_triple_quoted_without_stripmargin(self):
        src = DAO_TRIPLE.replace('""".stripMargin', '"""')
        self.assertEqual(sorted(t for t, _ in rule_edges(src)), ["table:label", "table:workflow"])

    def test_triple_quoted_stripmargin(self):
        self.assertEqual(sorted(t for t, _ in rule_edges(DAO_TRIPLE)), ["table:label", "table:workflow"])

    def test_stripmargin_trim_chain_and_margin_removed(self):
        src = DAO_TRIPLE.replace('""".stripMargin', '""".stripMargin.trim')
        self.assertEqual(sorted(t for t, _ in rule_edges(src)), ["table:label", "table:workflow"])
        _, ex = scala_extraction(src)
        values = [a for d in ex["defines"] for ann in d.get("annotations", []) for a in [ann.get("args", {}).get("value")]
                  if isinstance(a, str)]
        self.assertTrue(values and all("|" not in v for v in values), values)


class ScheduleScalaTest(unittest.TestCase):
    def test_every_interval_fact(self):
        _, ex = scala_extraction(JOB)
        srcs = schedfacts.schedule_sources(ex)
        self.assertEqual(len(srcs), 1, srcs)
        self.assertEqual(srcs[0]["source"].split(".")[-1], "CleanupJob")
        text = schedfacts.describe("CleanupJob", srcs[0]["items"])
        self.assertIn("20s", text)
        self.assertIn("no concurrent runs", text)

    def test_schedule_edge_target_is_the_class(self):
        _, ex = scala_extraction(JOB)
        edges = [e for e in rules.all_edges(ex) if (e.get("rule") or "").startswith("schedule.")]
        self.assertTrue(edges)
        self.assertTrue(all(not e["target"].endswith("CleanupJobName") for e in edges), edges)


class NegativeTest(unittest.TestCase):
    def test_java_only_families_stay_closed_on_scala_row(self):
        self.assertEqual(rule_edges(JPA), [])


if __name__ == "__main__":
    unittest.main()
