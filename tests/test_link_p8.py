"""P8 link correctness: HTTP clients become channel edges (J8), route params normalise (M11),
verdicts are asked once and validated closed (M4, M5, M6), follow their call site (M10), and the
prompt is valid JSON (M7)."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import SKILL_ROOT, have_git
from test_link_store import Case, N, RUN_PY, edge, snapshots

from cdp.lang.base import ExtractContext
from cdp.lang.csharp import CSharpExtractor
from cdp.lang.python import PythonExtractor
from cdp.link import (build_tasks, fold_resolutions, render_task_prompt, scan_links, summarise,
                      unresolved_tasks, validate_task_patch)
from cdp.store.sqlite_backend import SqliteStore

REFIT = '''using Refit;
namespace Acme.Catalog;

public interface ISqlPoolServiceApi
{
    [Post("/sql-pool/v1/reservations")]
    public Task<Out> Make([Body] Req r);

    [Get("/sql-pool/v1/reservations/{reservationId}")]
    public Task<Out> Fetch(long reservationId);

    [Delete("/sql-pool/v1/reservations/{reservationId}")]
    public Task Remove(long reservationId);
}
'''
JAXRS = '''package com.acme.sp;

import javax.ws.rs.*;

@Path("/v1/reservations")
public class ReservationResource {
    @GET
    @Path("/{id}")
    public String get(@PathParam("id") long id) { return ""; }

    @POST
    public String create(String body) { return ""; }

    @DELETE
    @Path("/{reservation_id}")
    public void delete(@PathParam("reservation_id") long id) { }
}
'''
DROPWIZARD = "server:\n  applicationContextPath: /unified-store/sql-pool\n"


def csharp_edges(path, src):
    facts = CSharpExtractor().extract(ExtractContext(path=path, lines=src.splitlines(), module="root"))
    return [(e["source"], e["target"], e["channel"], e["anchor"]["line"]) for e in facts.io_edges
            if e["channel"] == "http_out" and e["target"].startswith("http:")]


class ClientExtractionTest(unittest.TestCase):
    def test_j8_refit_interface_methods_are_http_out_edges(self):
        got = csharp_edges("Contracts/ISqlPoolServiceApi.cs", REFIT)
        self.assertEqual(got, [
            ("Acme.Catalog.ISqlPoolServiceApi#Make", "http:POST /sql-pool/v1/reservations", "http_out", 6),
            ("Acme.Catalog.ISqlPoolServiceApi#Fetch", "http:GET /sql-pool/v1/reservations/{reservationId}", "http_out", 9),
            ("Acme.Catalog.ISqlPoolServiceApi#Remove", "http:DELETE /sql-pool/v1/reservations/{reservationId}", "http_out", 12),
        ])

    def test_j8_httpclient_calls_and_requests_are_http_out_edges(self):
        src = '''using System.Net.Http;
namespace A;
public class C
{
    private readonly HttpClient _http;
    public async Task Run(long id)
    {
        await _http.GetAsync($"{BaseUrl}/tenant/{id}");
        await _http.PostAsJsonAsync("/orders", x);
        var r = new HttpRequestMessage(HttpMethod.Delete, "/orders/1");
        var s = await repo.GetAsync(id);
    }
}
'''
        got = [t for _, t, _, _ in csharp_edges("src/C.cs", src)]
        self.assertEqual(got, ["http:GET /tenant/{id}", "http:POST /orders", "http:DELETE /orders/1"])

    def test_j8_a_test_project_is_not_a_client(self):
        self.assertEqual(csharp_edges("Svc.Tests/T.cs", REFIT), [])

    def test_j8_python_requests_calls_are_http_out_edges(self):  # python_io owns the extraction
        src = ('import requests\n\n\ndef load(uid):\n    return requests.get(f"{BASE}/api/users/{uid}")\n\n\n'
               'class Api:\n    def save(self, u):\n        return self.session.post("http://users/api/users", json=u)\n'
               '    def other(self, d):\n        return d.get("k")\n')
        facts = PythonExtractor().extract(ExtractContext(path="svc/api.py", lines=src.splitlines(), module="root"))
        got = [(e["source"].split(".", 1)[-1], e["target"]) for e in facts.io_edges if e["target"].startswith("http:")]
        self.assertEqual(got, [("api#load", "http:GET /api/users/{}"),
                               ("api.Api#save", "http:POST http://users/api/users")])


def _snap(repo, edges, head="h"):
    return {"repo": repo, "head": head, "dataflow": {"edges": edges}}


class RouteParamsTest(unittest.TestCase):
    CALLS = ["/api/users/${id}", "/api/users/{id}", "/api/users/:id", "/api/users/<int:uid>",
             "/api/users/{id:int}", "/api/users/${user.id}"]
    ROUTES = ["/api/users/<int:uid>", "/api/users/{id:int}", "/api/users/:x", "/api/users/{x}", "/api/users/<x>"]

    def test_m11_every_param_spelling_matches_every_other(self):
        callers = [edge("c%d" % i, "http:GET " + c, "http_out", "c%d.js" % i) for i, c in enumerate(self.CALLS)]
        routes = [edge("r%d" % i, "route:GET " + r, "http_in", "r%d.py" % i) for i, r in enumerate(self.ROUTES)]
        report = scan_links([_snap("web", callers), _snap("api", routes)])
        self.assertEqual(report["totals"]["links"], len(self.CALLS) * len(self.ROUTES))
        self.assertEqual(report["totals"]["unmatched"], 0)

    def test_j8_a_different_verb_is_not_the_same_endpoint(self):
        report = scan_links([_snap("a", [edge("c", "http:POST /v1/x", "http_out", "c.cs")]),
                             _snap("b", [edge("r", "route:GET /v1/x", "http_in", "r.java")])])
        self.assertEqual(report["totals"]["links"], 0)

    def test_j8_a_client_path_missing_the_servers_context_prefix_links_as_heuristic(self):
        report = scan_links([_snap("a", [edge("c", "http:GET /sql-pool/v1/reservations", "http_out", "c.cs")]),
                             _snap("b", [edge("r", "route:GET /unified-store/sql-pool/v1/reservations", "http_in", "r.java")])])
        self.assertEqual([l["match_kind"] for l in report["links"]], ["heuristic"])

    def test_j8_a_short_generic_suffix_does_not_link(self):
        report = scan_links([_snap("a", [edge("c", "http:GET /v1/health", "http_out", "c.cs")]),
                             _snap("b", [edge("r", "route:GET /other/v1/health", "http_in", "r.java")])])
        self.assertEqual(report["totals"]["links"], 0)


def git(cwd, *args):
    subprocess.run(["git", "-C", str(cwd)] + list(args), check=True, capture_output=True,
                   env=dict(os.environ, GIT_AUTHOR_NAME="x", GIT_AUTHOR_EMAIL="x@x", GIT_COMMITTER_NAME="x",
                            GIT_COMMITTER_EMAIL="x@x"))


@unittest.skipUnless(have_git(), "needs git")
class TwoRepoTest(unittest.TestCase):
    """A C# Refit client and a Java JAX-RS (Dropwizard) server, scanned into one store."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.home = self.tmp / "home"
        self.elsewhere = self.tmp / "elsewhere"
        self.elsewhere.mkdir()
        for name, files in (("cat", {"Contracts/ISqlPoolServiceApi.cs": REFIT, "Acme.csproj": "<Project/>"}),
                            ("sp", {"src/main/java/com/acme/sp/ReservationResource.java": JAXRS,
                                    "src/main/resources/dropwizard-service-config.yml": DROPWIZARD,
                                    "pom.xml": "<project><modelVersion>4.0.0</modelVersion><groupId>a</groupId>"
                                               "<artifactId>sp</artifactId><version>1</version></project>"})):
            repo = self.tmp / name
            for rel, text in files.items():
                (repo / rel).parent.mkdir(parents=True, exist_ok=True)
                (repo / rel).write_text(text)
            git(repo, "init", "-q")
            git(repo, "remote", "add", "origin", "https://github.com/acme/%s.git" % name)
            git(repo, "add", "-A")
            git(repo, "commit", "-qm", "i")
            self.cdp("scan", "--repo", str(repo), "--quiet")
        self.db = self.home / "index.db"

    def cdp(self, *args, check=True):
        proc = subprocess.run([sys.executable, "-m", "cdp.cli", *args], cwd=str(self.elsewhere),
                              capture_output=True, text=True,
                              env=dict(os.environ, CDP_HOME=str(self.home), PYTHONPATH=str(SKILL_ROOT)))
        if check and proc.returncode != 0:
            raise AssertionError("%s -> %d\n%s\n%s" % (args, proc.returncode, proc.stdout, proc.stderr))
        return proc

    def test_j8_the_refit_client_links_to_the_jaxrs_server_with_correct_labels(self):
        report = json.loads(self.cdp("link", "scan", "--json").stdout)
        http = [l for l in report["links"] if l["protocol"] == "http_out"]
        self.assertEqual(len(http), 3)
        for l in http:
            self.assertEqual(l["caller"]["repo"], "github.com/acme/cat")
            self.assertEqual(l["callee"]["repo"], "github.com/acme/sp")
            self.assertTrue(l["caller"]["anchor"]["file"].endswith("ISqlPoolServiceApi.cs"))
            self.assertTrue(l["callee"]["anchor"]["file"].endswith("ReservationResource.java"))
        post = [l for l in http if l["caller"]["target"].startswith("http:POST")][0]
        self.assertEqual((post["caller"]["anchor"]["line"], post["callee"]["anchor"]["line"]), (6, 11))
        self.assertEqual(post["callee"]["target"], "route:POST /unified-store/sql-pool/v1/reservations")
        text = self.cdp("link", "scan").stdout
        self.assertIn("caller [cat:", text)
        self.assertIn("-> callee [sp:", text)

    def test_j8_link_scan_writes_nothing_and_bare_db_persists(self):
        before = hashlib.md5(self.db.read_bytes()).hexdigest()
        self.cdp("link", "scan")
        self.cdp("link", "scan", "--json")
        self.assertEqual(hashlib.md5(self.db.read_bytes()).hexdigest(), before)
        store = SqliteStore(self.db, readonly=True)
        self.assertEqual(store.read_link_edges(), [])
        store.close()
        self.cdp("link", "scan", "--db")  # bare --db: the machine store
        store = SqliteStore(self.db, readonly=True)
        self.assertGreaterEqual(len(store.read_link_edges()), 3)
        store.close()

    def test_j8_query_labels_both_ends_and_an_unknown_service_is_an_error(self):
        self.cdp("link", "scan", "--db")
        as_server = self.cdp("link", "query", "--service", "sp").stdout
        self.assertIn("called by: [cat] http:POST /sql-pool/v1/reservations", as_server)
        self.assertIn("-> [sp] route:POST /unified-store/sql-pool/v1/reservations", as_server)
        as_client = self.cdp("link", "query", "--service", "cat").stdout
        self.assertIn("calls: [cat]", as_client)
        bad = self.cdp("link", "query", "--service", "nope", check=False)
        self.assertNotEqual(bad.returncode, 0)
        self.assertIn("unknown service", bad.stderr)

    def test_a_link_survives_an_unrelated_commit_and_shows_in_query(self):
        self.cdp("link", "scan", "--db")
        sp = self.tmp / "sp"
        (sp / "NOTES.md").write_text("hello\n")
        git(sp, "add", "-A")
        git(sp, "commit", "-qm", "unrelated")
        self.cdp("refresh", "--repo", str(sp), check=False)
        self.cdp("scan", "--repo", str(sp), "--quiet")
        self.cdp("link", "scan", "--db")
        out = self.cdp("link", "query", "--service", "sp", "--json").stdout
        self.assertEqual(len(json.loads(out)["links"]), 3)  # not 6: one id per pairing across commits


class VerdictsTest(Case):
    def task(self):
        return build_tasks(scan_links(snapshots()))[0]

    def patch(self, task, **over):
        c = task["candidates"][0]
        res = {"link_id": c["link_id"], "verdict": "match", "reason": "same endpoint", "anchor": dict(c["caller_sites"][0])}
        res.update(over)
        return {"task_id": task["task_id"], "resolutions": [res]}

    def test_m6_unknown_keys_are_rejected_at_every_level(self):
        task = self.task()
        p = self.patch(task, evil="x")
        self.assertTrue(any("evil" in e for e in validate_task_patch(p, task)))
        p = self.patch(task)
        p["extra"] = 1
        self.assertTrue(any("extra" in e for e in validate_task_patch(p, task)))
        p = self.patch(task)
        p["resolutions"][0]["anchor"]["evil"] = 1
        self.assertTrue(any("evil" in e for e in validate_task_patch(p, task)))

    def test_m6_a_numeric_string_line_is_accepted_and_stored_as_a_number(self):
        task = self.task()
        site = task["candidates"][0]["caller_sites"][0]
        p = self.patch(task, anchor={"file": site["file"], "line": str(site["line"])})
        self.assertEqual(validate_task_patch(p, task), [])
        report = scan_links(snapshots())
        fold_resolutions(report, task, p, "r")
        self.assertEqual(report["links"][0]["resolution"]["anchor"]["line"], site["line"])
        self.assertTrue(validate_task_patch(self.patch(task, anchor={"file": site["file"], "line": "x"}), task))
        self.assertTrue(validate_task_patch(self.patch(task, anchor={"file": site["file"], "line": True}), task))

    def test_m6_a_citation_in_the_wrong_repo_is_rejected(self):
        task = self.task()
        site = task["candidates"][0]["caller_sites"][0]  # billing's file and line
        self.assertEqual(validate_task_patch(self.patch(task, anchor=dict(site, repo="billing")), task), [])
        wrong = validate_task_patch(self.patch(task, anchor=dict(site, repo="svc")), task)
        self.assertTrue(any("anchor" in e for e in wrong), wrong)

    def test_m6_a_site_of_another_link_is_not_a_citation_for_this_one(self):
        caller = [edge("C#a", "http:GET /x/{id}", "http_out", "A.java", 5)]
        callees = [edge("H#one", "route:GET /x/:id", "http_in", "H1.java", 9),
                   edge("H#two", "route:GET /x/<id>", "http_in", "H2.java", 11)]
        task = build_tasks(scan_links([_snap("billing", caller), _snap("svc", callees)]))[0]
        first, second = task["candidates"]
        stray = [s for s in second["callee_sites"] if s not in first["callee_sites"]][0]
        patch = {"task_id": task["task_id"], "resolutions": [
            {"link_id": first["link_id"], "verdict": "match", "reason": "r", "anchor": stray}]}
        self.assertTrue(validate_task_patch(patch, task))
        patch["resolutions"][0]["anchor"] = first["callee_sites"][0]
        self.assertEqual(validate_task_patch(patch, task), [])

    def test_m4_contradictory_duplicate_resolutions_are_rejected(self):
        task = self.task()
        p = self.patch(task)
        p["resolutions"].append(dict(p["resolutions"][0], verdict="no_match"))
        self.assertTrue(any("twice" in e for e in validate_task_patch(p, task)))

    def test_m4_a_second_answer_for_a_resolved_link_does_not_overwrite(self):
        task = self.task()
        report = scan_links(snapshots())
        self.assertEqual(fold_resolutions(report, task, self.patch(task), "r1"), 1)
        self.assertEqual(fold_resolutions(report, task, self.patch(task, verdict="no_match"), "r2"), 0)
        self.assertEqual(report["links"][0]["resolution"]["verdict"], "match")

    def test_m4_a_second_run_and_a_second_prompts_dispatch_nothing(self):
        self.assertEqual(self.link("run").returncode, 0)
        again = self.link("run")
        self.assertIn("0 task(s)", again.stdout)
        self.assertIn("nothing to dispatch", again.stdout)
        out = self.tmp / "p"
        proc = self.link("prompts", "--out", str(out))
        self.assertIn("0 ambiguous task(s)", proc.stdout)
        self.assertEqual(list((out / "tasks").glob("*.md")), [])

    def test_m4_a_partly_resolved_task_asks_only_about_the_open_links(self):
        two = [edge("C#a", "http:GET /x/{id}", "http_out", "A.java", 5), edge("C#b", "http:GET /x/{id}", "http_out", "B.java", 6)]
        callee = [edge("H#g", "route:GET /x/:id", "http_in", "H.java", 9)]
        report = scan_links([_snap("billing", two), _snap("svc", callee)])
        task = build_tasks(report)[0]
        self.assertEqual(len(task["candidates"]), 2)
        p = {"task_id": task["task_id"], "resolutions": [
            {"link_id": task["candidates"][0]["link_id"], "verdict": "match", "reason": "r",
             "anchor": task["candidates"][0]["caller_sites"][0]}]}
        fold_resolutions(report, task, p, "r")
        left = unresolved_tasks(report)
        self.assertEqual([len(t["candidates"]) for t in left], [1])
        self.assertNotEqual(left[0]["candidates"][0]["link_id"], task["candidates"][0]["link_id"])

    def test_m5_a_link_patch_never_lands_in_the_scope_inbox(self):
        from cdp.link import dispatch_link_task
        from test_supervisor import ScriptedRunner, _write

        store = SqliteStore(self.db)
        task = self.task()
        prompts = self.tmp / "prompts"
        prompts.mkdir()
        good = dispatch_link_task(task, "r", ScriptedRunner([_write(self.patch(task))]), store, prompts, max_attempts=1)
        self.assertEqual(good["state"], "validated")
        self.assertEqual(list(store._inbox_dir().glob("*.json")) if store._inbox_dir().is_dir() else [], [])
        self.assertTrue((prompts / "inbox" / (task["task_id"] + ".json")).exists())
        bad = dispatch_link_task(task, "r2", ScriptedRunner([_write({"task_id": task["task_id"], "resolutions": [1]})]),
                                 store, prompts, max_attempts=1)
        self.assertEqual(bad["state"], "abandoned")
        self.assertEqual(list(store._inbox_dir().glob("*.json")) if store._inbox_dir().is_dir() else [], [])
        self.assertEqual(list((prompts / "inbox").glob("*.json")), [])
        store.close()

    def test_m10_a_resolution_follows_its_call_site_when_it_moves(self):
        self.assertEqual(self.link("run").returncode, 0)
        store = SqliteStore(self.db)
        store.write_link_edges(scan_links(snapshots("n1", "n2", shift=9)))  # every call site moves 9 lines down
        store.close()
        for e in self.edges():
            if e["kind"] == "link":
                res = e["data"]["resolution"]
                self.assertEqual(res["anchor"]["line"], e["data"]["caller"]["anchor"]["line"])
                self.assertEqual(res["anchor"]["line"], 19)

    def test_m7_the_prompt_example_is_valid_json_a_patch_can_copy(self):
        task = self.task()
        prompt = render_task_prompt(task)
        block = prompt.split("e.g.:\n\n", 1)[1].split("\n\n", 1)[0]
        example = json.loads(block)
        self.assertEqual(example["task_id"], task["task_id"])
        self.assertEqual(validate_task_patch(example, task), [])

    def test_m7_every_call_site_of_one_pairing_is_shown(self):
        two = [edge("C#a", "http:GET /x/{id}", "http_out", "A.java", 5), edge("C#a", "http:GET /x/{id}", "http_out", "A.java", 30)]
        callee = [edge("H#g", "route:GET /x/:id", "http_in", "H.java", 9)]
        task = build_tasks(scan_links([_snap("billing", two), _snap("svc", callee)]))[0]
        self.assertEqual(len(task["candidates"]), 1)
        prompt = render_task_prompt(task)
        self.assertIn("A.java:5, A.java:30", prompt)
        c = task["candidates"][0]
        site = {"file": "A.java", "line": 30}
        self.assertEqual(validate_task_patch({"task_id": task["task_id"], "resolutions": [
            {"link_id": c["link_id"], "verdict": "no_match", "reason": "r", "anchor": site}]}, task), [])

    def test_m7_the_no_match_verdict_is_shown_in_text_output(self):
        task = self.task()
        report = scan_links(snapshots())
        fold_resolutions(report, task, self.patch(task, verdict="no_match"), "r")
        self.assertTrue(any("no_match" in l for l in summarise(report)))

    def test_m7_prompts_runner_cmd_is_split_like_a_shell(self):
        out = self.tmp / "o"
        cmd = "%s -c 'import sys; sys.exit(0)'" % sys.executable
        proc = subprocess.run([sys.executable, str(RUN_PY), "--state-dir", str(self.home), "link", "prompts", "--db",
                               str(self.db), "--out", str(out), "--runner-cmd", cmd], capture_output=True, text=True,
                              cwd=str(self.elsewhere), env=dict(os.environ, CDP_HOME=str(self.home)))
        self.assertIn("ran %d via --runner-cmd" % N, proc.stdout, proc.stdout + proc.stderr)
        self.assertEqual(proc.returncode, 0)


def _snap(repo, edges, head="h"):  # noqa: F811 -- module level helper shared above
    return {"repo": repo, "head": head, "dataflow": {"edges": edges}}


if __name__ == "__main__":
    unittest.main()
