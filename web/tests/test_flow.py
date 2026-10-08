"""`web/api/flow.py` (Flow tab, spec 2026-10-08-flow-tab-design.md): pure
role/group/orientation rules over synthetic dataflow graphs, plus one
end-to-end `/api/flow` call against a real `cdp scan` of the minirepo."""
from __future__ import annotations

import shutil, subprocess, sys, tempfile, unittest
from pathlib import Path

from web.api.flow import build_flow

REPO_ROOT = Path(__file__).resolve().parents[2]
MINIREPO = REPO_ROOT / "tests" / "fixtures" / "minirepo"


def n(id, type, file=None, role="source", label=None):
    return {"id": id, "label": label or id, "type": type, "role": role, "file": file, "node_id": "sym:" + id}


def e(s, t, kind):
    return {"source": s, "target": t, "kind": kind, "count": 1}


NODES = [
    n("api.Res", "module", "svc-api/src/Res.java"),
    n("dal.Repo", "module", "svc-dal/src/Repo.java"),
    n("jobs.Nightly", "module", "svc-jobs/src/Nightly.java"),
    n("jobs.NightlyTest", "module", "svc-jobs/test/NightlyTest.java", role="test"),
    n("route:GET /x", "route", None, role=None),
    n("table:users", "table", None, role=None),
    n("entity:EUser", "entity", None, role=None),
    n("library:okhttp", "library", None, role=None, label="okhttp"),
    n("library:spring-data", "library", None, role=None),
    n("library:io.dropwizard.jobs", "library", None, role=None),
    n("config:DB_URL", "config", None, role=None),
    n("orphan.NoFile", "module", None),
]


class BuildFlowTest(unittest.TestCase):
    def flow(self, edges, include=()):
        return build_flow(NODES, edges, include)

    def test_http_in_is_reversed_route_to_code(self):
        out = self.flow([e("api.Res", "route:GET /x", "http_in")])
        self.assertEqual(out["edges"], [{"source": "route:GET /x", "target": "api.Res", "kind": "http_in", "count": 1}])
        roles = {x["id"]: (x["role"], x["group"]) for x in out["nodes"]}
        self.assertEqual(roles["route:GET /x"], ("source", "group:routes"))
        self.assertEqual(roles["api.Res"], ("transform", "code:svc-api"))

    def test_persist_to_table_and_entity_are_sinks_library_dropped(self):
        out = self.flow([
            e("dal.Repo", "table:users", "persist"),
            e("dal.Repo", "entity:EUser", "persist"),
            e("dal.Repo", "library:spring-data", "persist"),
        ])
        groups = {x["id"]: x["group"] for x in out["nodes"]}
        self.assertEqual(groups["table:users"], "group:tables")
        self.assertEqual(groups["entity:EUser"], "group:entities")
        self.assertNotIn("library:spring-data", groups)

    def test_http_out_becomes_labelled_synthetic_sink(self):
        out = self.flow([e("api.Res", "library:okhttp", "http_out"), e("api.Res", "library:okhttp", "http_out")])
        sink = "flow-sink:http_out:library:okhttp"
        node = next(x for x in out["nodes"] if x["id"] == sink)
        self.assertEqual((node["label"], node["role"], node["group"], node["node_id"]),
                         ("HTTP out · okhttp", "sink", "group:http-out", None))
        self.assertEqual(out["edges"], [{"source": "api.Res", "target": sink, "kind": "http_out", "count": 2}])

    def test_scheduled_job_is_a_source_once_even_when_it_writes(self):
        out = self.flow([
            e("jobs.Nightly", "library:io.dropwizard.jobs", "schedule"),
            e("jobs.Nightly", "table:users", "persist"),
        ])
        jobs = [x for x in out["nodes"] if x["id"] == "jobs.Nightly"]
        self.assertEqual(len(jobs), 1)
        self.assertEqual((jobs[0]["role"], jobs[0]["group"]), ("source", "group:jobs"))
        self.assertNotIn("schedule", {x["kind"] for x in out["edges"]})

    def test_tests_excluded(self):
        out = self.flow([e("jobs.NightlyTest", "table:users", "persist")])
        self.assertEqual(out, {"nodes": [], "groups": [], "edges": []})

    def test_calls_and_config_only_when_included(self):
        edges = [e("api.Res", "dal.Repo", "call"), e("api.Res", "config:DB_URL", "config_read"),
                 e("dal.Repo", "table:users", "persist")]
        self.assertEqual({x["kind"] for x in self.flow(edges)["edges"]}, {"persist"})
        both = self.flow(edges, ["calls", "config"])
        self.assertIn({"source": "config:DB_URL", "target": "api.Res", "kind": "config_read", "count": 1}, both["edges"])
        self.assertIn({"source": "api.Res", "target": "dal.Repo", "kind": "call", "count": 1}, both["edges"])

    def test_self_loop_call_dropped_and_no_file_groups_as_other(self):
        out = self.flow([e("orphan.NoFile", "orphan.NoFile", "call"), e("orphan.NoFile", "table:users", "persist")], ["calls"])
        self.assertEqual([x["kind"] for x in out["edges"]], ["persist"])
        self.assertEqual(next(x for x in out["nodes"] if x["id"] == "orphan.NoFile")["group"], "code:(other)")

    def test_groups_count_members_sources_first(self):
        out = self.flow([e("api.Res", "route:GET /x", "http_in"), e("api.Res", "table:users", "persist"),
                         e("dal.Repo", "table:users", "persist")])
        self.assertEqual([(g["id"], g["role"], g["count"]) for g in out["groups"]],
                         [("group:routes", "source", 1), ("code:svc-api", "transform", 1),
                          ("code:svc-dal", "transform", 1), ("group:tables", "sink", 1)])


class FlowEndpointTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.state_dir = Path(tempfile.mkdtemp())
        subprocess.run([sys.executable, "-m", "cdp", "scan", "--repo", str(MINIREPO), "--state-dir", str(cls.state_dir)],
                       cwd=REPO_ROOT, check=True, capture_output=True, text=True)

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.state_dir, ignore_errors=True)

    def get(self, **params):
        from fastapi.testclient import TestClient
        from web.api.app import app
        return TestClient(app).get("/api/flow", params={"repo": str(MINIREPO), "state_dir": str(self.state_dir), **params})

    def test_minirepo_flow_has_routes_and_table_sinks(self):
        resp = self.get()
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        kinds = {x["kind"] for x in body["edges"]}
        self.assertTrue(kinds <= {"http_in", "persist", "http_out", "metric_emit"}, kinds)
        roles = {x["role"] for x in body["nodes"]}
        self.assertIn("source", roles)
        self.assertIn("sink", roles)

    def test_unknown_include_is_400(self):
        self.assertEqual(self.get(include="bogus").status_code, 400)
