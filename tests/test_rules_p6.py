"""ANNOTATIONS_PLAN P6: new join rules (scheduling values, messaging, HTTP clients, web parameters)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from helpers import Pipeline, extraction_of

from cdp import rules
from cdp.anchor import verify_anchor
from cdp.entail import entail_claims
from cdp.lang.base import ExtractContext
from cdp.lang.java import JavaExtractor
from cdp.query.lookup import q_routes
from cdp.query.render import render
from cdp.util import read_lines

JOB = """package a.jobs;

import io.dropwizard.jobs.annotations.DelayStart;
import io.dropwizard.jobs.annotations.Every;
import org.quartz.DisallowConcurrentExecution;

@DelayStart("50s")
@Every(
    jobName = "AutoScaleJob",
    misfirePolicy = Every.MisfirePolicy.NOW_WITH_REMAINING_COUNT,
    value = "60s")
@DisallowConcurrentExecution
public class AutoScaleJob {
    public void run() {}
}
"""

SPRING_JOBS = """package a.jobs;

import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.scheduling.annotation.Schedules;
import java.util.concurrent.TimeUnit;

public class Tasks {
    @Scheduled(fixedRate = 5000, initialDelay = 10, timeUnit = TimeUnit.SECONDS)
    void rate() {}

    @Schedules({@Scheduled(fixedDelay = 1000), @Scheduled(cron = "0 0 * * * *")})
    void both() {}

    @Scheduled(cron = "0 15 3 * * *")
    @Scheduled(cron = "0 15 4 * * *")
    void repeated() {}
}
"""

OTHER_EVERY = """package a.jobs;

import com.other.Every;

@Every("5s")
public class NotOurs {}
"""

QUARKUS = """package a.jobs;

import io.quarkus.scheduler.Scheduled;
import jakarta.ejb.Schedule;
import de.spinscale.dropwizard.jobs.annotations.On;
import de.spinscale.dropwizard.jobs.annotations.OnApplicationStart;

public class Mixed {
    @Scheduled(every = "10s", delayed = "5s")
    void q() {}

    @Schedule(minute = "*/5", hour = "*")
    void ejb() {}
}

@On("0 0 12 * * ?")
class Noon {}

@OnApplicationStart
class Boot {}
"""

NO_RULE = """package a.svc;

import org.springframework.transaction.annotation.Transactional;
import org.springframework.scheduling.annotation.Async;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.retry.annotation.Retryable;
import javax.annotation.PostConstruct;
import javax.annotation.security.RolesAllowed;

@Transactional
public class Plain {
    @Async @Cacheable("x") @Retryable @RolesAllowed("a")
    public void run() {}
    @PostConstruct void init() {}
}
"""

MESSAGING = """package a.msg;

import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import io.awspring.cloud.sqs.annotation.SqsListener;
import org.springframework.cloud.stream.annotation.StreamListener;
import org.springframework.context.event.EventListener;
import a.events.OrderPlaced;

public class Listeners {
    @KafkaListener(topics = {"orders", "refunds"}, groupId = "g")
    void kafka(String m) {}

    @JmsListener(destination = "jms.in")
    void jms(String m) {}

    @RabbitListener(queues = "rabbit.q")
    void rabbit(String m) {}

    @SqsListener("sqs-queue")
    void sqs(String m) {}

    @StreamListener("input")
    void stream(String m) {}

    @EventListener
    void placed(OrderPlaced e) {}

    @EventListener(classes = {OrderPlaced.class})
    void explicit() {}
}
"""

CLIENTS = """package a.cl;

import org.springframework.web.service.annotation.*;
import org.eclipse.microprofile.rest.client.inject.RegisterRestClient;
import javax.ws.rs.GET;
import javax.ws.rs.Path;

@HttpExchange("/api")
interface UserClient {
    @GetExchange("/users/{id}") String get(String id);
    @PostExchange("/users") void create();
    @HttpExchange(method = "DELETE", url = "/users/{id}") void remove(String id);
}

@RegisterRestClient(baseUri = "http://billing")
@Path("/b")
interface BillingClient {
    @GET @Path("/invoices") String invoices();
}
"""

WEB = """package a.web;

import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/c")
public class C {
    @PostMapping("/x/{id}")
    public String x(@PathVariable("id") Long id,
                    @RequestParam(value = "q", required = false, defaultValue = "all") String q,
                    @RequestHeader("X-Trace") String trace,
                    @RequestBody a.web.Dto body) { return ""; }
}
"""

JAXRS = """package a.web;

import javax.ws.rs.*;

@Path("/r")
public class R {
    @GET @Path("/{id}")
    public String get(@PathParam("id") long id, @QueryParam("n") @DefaultValue("5") int n, @HeaderParam("H") String h) { return ""; }
}
"""


def build(files) -> Pipeline:
    tmp = tempfile.TemporaryDirectory()
    root = Path(tmp.name) / "p6repo"
    for rel, body in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body)
    (root / "build.gradle").write_text("apply plugin: 'java'\n")
    pl = Pipeline(root)
    pl._tmp = tmp
    return pl


def java(name: str, body: str) -> dict:
    return {"src/main/java/a/%s.java" % name: body}


def extract(src: str, path: str = "a/C.java"):
    return extraction_of(JavaExtractor().extract(ExtractContext(path, src.split("\n"), "a")))


def edges(ex, rule_prefix: str):
    return sorted((e["source"], e["target"], e["anchor"]["line"]) for e in rules.all_edges(ex)
                  if (e.get("rule") or "").startswith(rule_prefix))


class _Store:
    def __init__(self, p: Pipeline) -> None:
        self.extraction, self.xref, self.inventory, self.dataflow = p.extraction, p.xref, p.inventory, p.dataflow
        self.state = {"claims": [], "unknowns": [], "provenance": {}}

    def node_of(self, path):
        return "root"


class ScheduleClaimTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pl = build({**java("jobs/AutoScaleJob", JOB), **java("jobs/Tasks", SPRING_JOBS),
                        **java("jobs/NotOurs", OTHER_EVERY), **java("jobs/Mixed", QUARKUS)})
        cls.claims = {c["subject"]: c for c in cls.pl.claims_of("entrypoint") if c.get("channel") == "schedule"}

    def test_dropwizard_claim_states_interval_delay_misfire_and_concurrency(self):
        c = self.claims["a.jobs.AutoScaleJob"]
        self.assertEqual(c["statement"], "AutoScaleJob runs every 60s after a 50s start delay "
                                         "(misfire NOW_WITH_REMAINING_COUNT, no concurrent runs)")
        file = "src/main/java/a/jobs/AutoScaleJob.java"
        lines = [(a["file"], a["line"]) for a in c["evidence"]]
        self.assertEqual(lines, [(file, 7), (file, 8), (file, 12), (file, 13)])
        multi = c["evidence"][1]["anchor"]
        for needle in ('jobName = "AutoScaleJob"', "NOW_WITH_REMAINING_COUNT", 'value = "60s"'):
            self.assertIn(needle, multi)
        self.assertIn("public class AutoScaleJob", c["evidence"][-1]["anchor"])

    def test_claim_passes_the_gates(self):
        lines = read_lines(self.pl.repo / "src/main/java/a/jobs/AutoScaleJob.java")
        for c in self.claims.values():
            for a in c["evidence"]:
                if a["file"].endswith("AutoScaleJob.java"):
                    self.assertTrue(verify_anchor(lines, a)[0], a)
        verdicts = {c["subject"]: c["verdict"] for c in entail_claims(list(self.claims.values()), self.pl.extraction)}
        self.assertEqual(set(verdicts.values()), {"entailed"})

    def test_spring_values_use_units_and_text(self):
        c = self.claims["a.jobs.Tasks#rate"]
        self.assertEqual(c["statement"], "Tasks#rate runs at a fixed rate of 5000 seconds after a 10 seconds start delay")

    def test_schedules_container_is_one_claim_and_repeats_are_listed(self):
        self.assertEqual(self.claims["a.jobs.Tasks#both"]["statement"],
                         'Tasks#both runs with a fixed delay of 1000ms between runs and on cron 0 0 * * * *')
        self.assertEqual(self.claims["a.jobs.Tasks#repeated"]["statement"],
                         "Tasks#repeated runs on cron 0 15 3 * * * and on cron 0 15 4 * * *")
        subjects = [s for s in self.claims if s.startswith("a.jobs.Tasks#")]
        self.assertEqual(sorted(subjects), ["a.jobs.Tasks#both", "a.jobs.Tasks#rate", "a.jobs.Tasks#repeated"])
        ids = [c["id"] for c in self.pl.claims]
        self.assertEqual(len(ids), len(set(ids)))

    def test_edges_are_deduped_per_annotation_line(self):
        ex = extract(SPRING_JOBS.replace("a.jobs", "a"))
        got = [(s, line) for s, _t, line in edges(ex, "schedule.")]
        self.assertEqual(got, [("a.Tasks#both", 11), ("a.Tasks#rate", 8), ("a.Tasks#repeated", 14),
                               ("a.Tasks#repeated", 15)])

    def test_quarkus_jakarta_and_dropwizard_triggers(self):
        self.assertEqual(self.claims["a.jobs.Mixed#q"]["statement"], "Mixed#q runs every 10s after a 5s start delay")
        self.assertEqual(self.claims["a.jobs.Mixed#ejb"]["statement"],
                         "Mixed#ejb runs on a calendar schedule (minute=*/5, hour=*)")
        self.assertEqual(self.claims["a.jobs.Noon"]["statement"], "Noon runs on cron 0 0 12 * * ?")
        self.assertEqual(self.claims["a.jobs.Boot"]["statement"], "Boot runs on application start")

    def test_same_simple_name_from_another_package_is_not_matched(self):
        self.assertNotIn("a.jobs.NotOurs", self.claims)
        ex = extract(OTHER_EVERY.replace("a.jobs", "a"))
        self.assertEqual(edges(ex, "schedule."), [])

    def test_a_bare_marker_makes_no_claim(self):
        src = "package a;\nimport org.quartz.DisallowConcurrentExecution;\n@DisallowConcurrentExecution\npublic class J {}\n"
        pl = build(java("J", src))
        self.assertEqual([c for c in pl.claims_of("entrypoint") if c.get("channel") == "schedule"], [])


class MessagingTest(unittest.TestCase):
    def test_listeners_make_event_subscribe_edges_in_the_event_namespace(self):
        ex = extract(MESSAGING.replace("a.msg", "a"))
        got = sorted((s.split("#")[1], t) for s, t, _ in edges(ex, "messaging."))
        self.assertEqual(got, [("explicit", "event:a.events.OrderPlaced"), ("jms", "event:jms.in"),
                               ("kafka", "event:orders"), ("kafka", "event:refunds"), ("placed", "event:a.events.OrderPlaced"),
                               ("rabbit", "event:rabbit.q"), ("sqs", "event:sqs-queue"), ("stream", "event:input")])
        self.assertTrue(all(e["channel"] == "event_subscribe" for e in rules.all_edges(ex) if e.get("rule")))
        self.assertIn("message_listener", ex["files"]["a/C.java"]["signals"])

    def test_same_name_from_another_package_is_not_matched(self):
        src = 'package a;\nimport com.other.KafkaListener;\nclass K {\n  @KafkaListener(topics = "t")\n  void m() {}\n}\n'
        self.assertEqual(edges(extract(src), "messaging."), [])

    def test_unresolved_import_falls_back_to_the_alias(self):
        src = 'package a;\nimport org.springframework.kafka.annotation.*;\nclass K {\n  @KafkaListener(topics = "t")\n  void m() {}\n}\n'
        self.assertEqual([t for _, t, _ in edges(extract(src), "messaging.")], ["event:t"])

    def test_sends_stay_in_code_and_no_rule_annotations_make_no_edges(self):
        ex = extract(NO_RULE.replace("a.svc", "a"))
        self.assertEqual([e for e in rules.all_edges(ex) if e.get("rule")], [])


class HttpClientTest(unittest.TestCase):
    def test_exchange_interfaces_and_restclient_make_http_out_edges(self):
        ex = extract(CLIENTS.replace("a.cl", "a"))
        got = sorted((s.split(".")[-1], t) for s, t, _ in edges(ex, "http_client."))
        self.assertEqual(got, [("BillingClient#invoices", "http:GET http://billing/b/invoices"),
                               ("UserClient#create", "http:POST /api/users"),
                               ("UserClient#get", "http:GET /api/users/{id}"),
                               ("UserClient#remove", "http:DELETE /api/users/{id}")])
        self.assertEqual({e["channel"] for e in rules.all_edges(ex) if (e.get("rule") or "").startswith("http_client.")},
                         {"http_out"})

    def test_a_rest_client_interface_is_not_a_route(self):
        ex = extract(CLIENTS.replace("a.cl", "a"))
        self.assertEqual([e for e in rules.all_edges(ex) if e["channel"] == "http_in" and e.get("rule")], [])

    def test_same_name_from_another_package_is_not_matched(self):
        src = 'package a;\nimport com.other.GetExchange;\ninterface I {\n  @GetExchange("/x") String m();\n}\n'
        self.assertEqual(edges(extract(src), "http_client."), [])

    def test_a_plain_jaxrs_resource_stays_a_route(self):
        ex = extract(JAXRS.replace("a.web", "a"))
        self.assertEqual([(t) for _, t, _ in edges(ex, "jaxrs.")], ["route:GET /r/{id}"])


class RouteInputsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pl = build({**java("web/C", WEB), **java("web/R", JAXRS)})
        cls.store = _Store(cls.pl)
        cls.result = q_routes(cls.store)
        cls.by_route = {r["route"]: r for r in cls.result["routes"]}

    def test_spring_inputs_carry_name_kind_type_required_and_default(self):
        got = self.by_route["/c/x/{id}"]["inputs"]
        self.assertEqual([(i["kind"], i["name"], i["type"], i.get("required"), i.get("default")) for i in got],
                         [("path", "id", "Long", None, None), ("query", "q", "String", False, "all"),
                          ("header", "X-Trace", "String", None, None), ("body", None, "a.web.Dto", None, None)])
        self.assertTrue(got[0]["at"].endswith("C.java:9"))

    def test_jaxrs_inputs_and_default_value(self):
        got = self.by_route["/r/{id}"]["inputs"]
        self.assertEqual([(i["kind"], i["name"], i["type"], i.get("default")) for i in got],
                         [("path", "id", "long", None), ("query", "n", "int", "5"), ("header", "H", "String", None)])

    def test_text_output_is_one_inputs_line_per_route(self):
        text = render(self.result)
        self.assertIn("inputs: path id:Long, query q:String?=all, header X-Trace:String, body Dto", text)
        self.assertIn("inputs: path id:long, query n:int=5, header H:String", text)
        self.assertEqual(text.count("inputs:"), 2)
        self.assertNotIn("@PathVariable", text)       # the inputs line replaces the per-parameter lines

    def test_routes_without_annotated_parameters_gain_no_key(self):
        pl = build(java("web/P", "package a.web;\nimport org.springframework.web.bind.annotation.*;\n"
                                  "@RestController\npublic class P {\n  @GetMapping(\"/p\")\n  String p() { return \"\"; }\n}\n"))
        (r,) = q_routes(_Store(pl))["routes"]
        self.assertNotIn("inputs", r)


if __name__ == "__main__":
    unittest.main()
