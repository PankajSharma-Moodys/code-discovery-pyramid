"""QA round 2 weak spots in `trace` / `table` / `symbol` / `routes` output, each reproduced on a
small repo: a route path shared by several verbs, lambda-wrapped calls, a class term, a table
written by SQL scripts, a substring that matches several symbols."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from helpers import have_git
from repo_layouts import Cdp, new_repo

from cdp.query import Budget, q_routes, q_symbol, q_table, q_trace
from cdp.query import trace as trace_mod

API = """namespace Shop
{
    public interface ITenantApi
    {
        void Provision(string id);
        bool Deprovision(string id);
        string Status(string id);
    }
}
"""
RUNNER = """using System;
namespace Shop
{
    public static class Runner
    {
        public static T Invoke<T>(Func<T> f) => f();
        public static void Run(Action a) => a();
    }
}
"""
IMPL = """namespace Shop
{
    public class TenantApi : ITenantApi
    {
        private readonly Auditor _audit = new Auditor();
        private readonly Quota _quota = new Quota();
        public void Provision(string id) { _quota.Reserve(id); }
        public bool Deprovision(string id) { _audit.Record(id); return true; }
        public string Status(string id) { return id; }
    }
}
"""
SHAPES = """namespace Shop
{
    public class Base { public Base() { } }
    public class Derived : Base { public Derived() : base() { } }
    public class Maker { public Base Make() { return new Base(); } }
}
"""
AUDITOR = "namespace Shop { public class Auditor { public void Record(string id) { } } }\n"
QUOTA = "namespace Shop { public class Quota { public void Reserve(string id) { } } }\n"
CONTROLLER = """using Microsoft.AspNetCore.Mvc;
using System;
namespace Shop
{
    [Route("catalog/[controller]")]
    [ApiController]
    public class TenantController : ControllerBase
    {
        private readonly ITenantApi _api;
        public TenantController(ITenantApi api) { _api = api; }

        [HttpPost("{tenantId}")]
        public void Provision(string tenantId)
        {
            Runner.Run(() => Runner.Run(() => _api.Provision(tenantId)));
        }

        [HttpDelete("{tenantId}")]
        public bool Deprovision(string tenantId)
        {
            return Runner.Invoke(delegate { return _api.Deprovision(tenantId); });
        }

        [HttpGet("{tenantId}")]
        public string Status(string tenantId)
        {
            return Runner.Invoke(() => _api.Status(tenantId));
        }
    }
}
"""


@unittest.skipUnless(have_git(), "needs git")
class CSharpTraceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        repo = new_repo(cls.tmp.name, "cs")
        repo.write("Api.cs", API)
        repo.write("Runner.cs", RUNNER)
        repo.write("Impl.cs", IMPL)
        repo.write("Shapes.cs", SHAPES)
        repo.write("Auditor.cs", AUDITOR)
        repo.write("Quota.cs", QUOTA)
        repo.write("Controllers/TenantController.cs", CONTROLLER)
        repo.commit("initial")
        cls.cdp = Cdp(cls.tmp.name, repo.path)
        cls.cdp.scan()
        cls.backend, cls.store = cls.cdp.open()

    @classmethod
    def tearDownClass(cls):
        cls.store.close()
        cls.tmp.cleanup()

    def files(self, term, **kw):
        return {r["file"]: r for r in q_trace(self.store, term, **kw)["files"]}

    def test_a_shared_route_path_traces_every_verb(self):
        result = q_trace(self.store, "/catalog/Tenant/{tenantId}")
        self.assertEqual(sorted(result["verbs"]), ["DELETE", "GET", "POST"])
        files = {r["file"]: r for r in result["files"]}
        # each verb's own chain, through the lambda / anonymous delegate, reaches the service layer
        self.assertIn("Impl.cs", files)
        self.assertIn("Api.cs", files)
        # ... and a file only one verb reaches says which
        self.assertEqual(sorted(files["Impl.cs"]["verbs"]), ["DELETE", "GET", "POST"])
        # a file only one verb reaches names it: Deprovision -> Auditor.Record, Provision -> Quota.Reserve
        self.assertEqual(files["Auditor.cs"]["verbs"], ["DELETE"])
        self.assertEqual(files["Quota.cs"]["verbs"], ["POST"])

    def test_verb_and_path_narrows_to_one_handler(self):
        post = q_trace(self.store, "POST /catalog/Tenant/{tenantId}")
        self.assertEqual(post["verbs"], ["POST"])
        self.assertEqual(post["resolved_as"]["label"], "POST /catalog/Tenant/{tenantId}")
        names = {r["file"] for r in post["files"]}
        self.assertIn("Quota.cs", names)
        self.assertNotIn("Auditor.cs", names)      # DELETE's callee is not POST's
        self.assertFalse(q_trace(self.store, "PUT /catalog/Tenant/{tenantId}")["found"])

    def test_lambda_wrapped_call_is_attributed_to_the_enclosing_member(self):
        uses = [u for u in self.store.xref["uses"]
                if u["fqn"] in ("Shop.ITenantApi#Provision", "Shop.ITenantApi#Deprovision", "Shop.ITenantApi#Status")]
        self.assertEqual({u["from_symbol"] for u in uses},
                         {"Shop.TenantController#Provision", "Shop.TenantController#Deprovision",
                          "Shop.TenantController#Status"})

    def test_a_class_term_walks_each_public_member_and_states_its_cap(self):
        result = q_trace(self.store, "TenantController")
        self.assertEqual(result["resolved_as"]["kind"], "symbol")
        self.assertEqual(len(result["resolved_as"]["members"]), 3)
        self.assertIn("Impl.cs", {r["file"] for r in result["files"]})
        self.assertEqual(result["capped"]["cap"], trace_mod.CLASS_TRACE_FILES)
        old = trace_mod.CLASS_TRACE_FILES
        trace_mod.CLASS_TRACE_FILES = 3
        try:
            small = q_trace(self.store, "TenantController")
        finally:
            trace_mod.CLASS_TRACE_FILES = old
        self.assertEqual(len(small["files"]), 3)
        self.assertGreater(small["capped"]["elided"], 0)
        self.assertEqual(small["elided"], small["capped"]["elided"])
        self.assertIn("capped at 3 files", small["budget_note"])
        # the entry point is still first and the nearest edges survive the cut
        self.assertTrue(small["files"][0]["why"].startswith("entry point"))

    def test_routes_matches_the_handler_class_and_says_so(self):
        result = q_routes(self.store, "TenantController")
        self.assertEqual(result["count"], 3)
        self.assertIn("handler", result["matched_on"])
        self.assertEqual({r["matched_via"] for r in result["routes"]}, {"handler"})
        self.assertEqual(q_routes(self.store, "Tenant#Status")["count"], 0)
        self.assertEqual(q_routes(self.store, "TenantController#Status", exact=True)["count"], 1)
        self.assertEqual(q_routes(self.store, "Status", exact=True)["count"], 1)
        self.assertEqual(q_routes(self.store, "delete /catalog")["count"], 1)

    def test_routes_elided_marker_follows_the_rows(self):
        out = self.cdp.run("query", "routes", "--view", "detail", "--budget", "1").stdout.splitlines()
        marker = [i for i, l in enumerate(out) if "more (cut by" in l]
        rows = [i for i, l in enumerate(out) if l.startswith("  ") and "/catalog/Tenant" in l]
        self.assertTrue(marker and rows)
        self.assertGreater(marker[0], rows[-1])

    def test_a_budgeted_trace_keeps_the_nearest_files_not_the_alphabetical_ones(self):
        full = [r["file"] for r in q_trace(self.store, "/catalog/Tenant/{tenantId}")["files"]]
        cut = q_trace(self.store, "/catalog/Tenant/{tenantId}", budget=Budget(3))
        self.assertEqual([r["file"] for r in cut["files"]], full[:4])   # the entry + 3 rows
        self.assertEqual(cut["elided"], len(full) - 4)

    def test_constructors_are_not_virtual_in_the_edge_graph(self):
        # `new Derived()` must not make `Base#<init>` reach every subclass constructor
        edges = [(e["source"], e["target"]) for e in self.store.dataflow["edges"]
                 if e["source"] == "Shop.Base#<init>" and e["target"].endswith("#<init>")]
        self.assertEqual(edges, [])
        self.assertTrue(any(e["source"] == "Shop.Maker#Make" and e["target"] == "Shop.Base#<init>"
                            for e in self.store.dataflow["edges"]))


SQL_A = "CREATE TABLE pool (id INT);\n"
SQL_B = "INSERT INTO pool (id) VALUES (1);\n"
SERVICE = """package com.acme;

public class PoolService {
    public void a() {}
    public void b() {}
    public void c() {}
    public void d() {}
}
"""
POOL_ENTITY = """package com.acme;

import javax.persistence.Entity;
import javax.persistence.Table;

@Entity
@Table(name = "pool")
public class PoolEntity {
}
"""


def _callers(n):
    return "".join(
        "package com.acme;\npublic class Use%d {\n    PoolService s;\n    PoolEntity e;\n"
        "    void run() { s.a(); s.b(); s.c(); s.d(); }\n}\n" % i for i in range(n))


@unittest.skipUnless(have_git(), "needs git")
class QueryOutputTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        repo = new_repo(cls.tmp.name, "j")
        repo.write("src/main/resources/db/migration/V001__create.sql", SQL_A)
        for i in range(2, 7):
            repo.write("src/main/resources/db/migration/V%03d__insert.sql" % i, SQL_B)
        repo.write("src/main/java/com/acme/PoolService.java", SERVICE)
        repo.write("src/main/java/com/acme/PoolEntity.java", POOL_ENTITY)
        for i in range(6):
            repo.write("src/main/java/com/acme/Use%d.java" % i, _callers(1).replace("Use0", "Use%d" % i))
        repo.commit("initial")
        cls.cdp = Cdp(cls.tmp.name, repo.path)
        cls.cdp.scan()
        cls.backend, cls.store = cls.cdp.open()

    @classmethod
    def tearDownClass(cls):
        cls.store.close()
        cls.tmp.cleanup()

    def test_table_written_by_sql_scripts_lists_sites_not_repeated_labels(self):
        t = q_table(self.store, "pool", exact=True)["tables"][0]
        scripts = [g for g in t["writers"] if g["kind"] == "script"]
        self.assertEqual(len(scripts), 1)
        self.assertEqual(scripts[0]["count"], 5)
        self.assertEqual(scripts[0]["files"], 5)
        self.assertTrue(all(":" in s for s in scripts[0]["sites"]))
        text = self.cdp.run("query", "table", "--view", "detail", "pool", "--exact").stdout
        self.assertNotIn("sql, sql", text)
        self.assertIn("SQL migration scripts: 5 site(s) in 5 script file(s)", text)
        self.assertIn("V002__insert.sql:1", text)
        self.assertIn("... 2 more", text)
        # one citation per site: a line that is both a write and a read is listed once
        cites = t["evidence"]
        self.assertEqual(len(cites), len(set(cites)))

    def test_symbol_substring_gives_every_match_a_share_of_the_budget(self):
        result = q_symbol(self.store, "Pool", budget=Budget(28))
        shown = {f["fqn"]: (len(f["used_by"]), f["used_by_count"]) for f in result["found"]}
        # no match is starved: every one with uses shows some (the old first-come budget gave
        # all of it to the first class), and the totals stay true
        with_uses = [f for f in result["found"] if f["used_by_count"]]
        self.assertGreaterEqual(len(with_uses), 6, shown)
        self.assertTrue(all(f["used_by"] for f in with_uses), shown)
        self.assertTrue(any(len(f["used_by"]) < f["used_by_count"] for f in with_uses))

    def test_symbol_elision_names_the_exact_command(self):
        result = q_symbol(self.store, "Pool", budget=Budget(9))
        cut = [f for f in result["found"] if f["see_all"]]
        self.assertTrue(cut)
        for f in cut:
            self.assertEqual(f["see_all"], "cdp query symbol %s --exact" % f["fqn"])
        text = self.cdp.run("query", "symbol", "--view", "detail", "Pool", "--budget", "9").stdout
        self.assertIn("all of them: `cdp query symbol ", text)
