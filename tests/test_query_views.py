"""`view` / `format` / `match` / `offset` / `max_tokens` / `[query]` (CONTEXT_PLAN.md): the accuracy guarantee.

One scanned repo (routes with nested Swagger-style annotations, tables, config, source text), queried
in-process. Every projection must carry the facts of the full answer; a cut must say what it cut.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import have_git
from repo_layouts import Cdp, new_repo, pom

from cdp import query as query_mod
from cdp.query import common, search, views
from cdp.query.common import INPUT_SIMPLE
from cdp.store import registry
from cdp.util import CdpError

SQL = """CREATE TABLE server (id BIGINT PRIMARY KEY);
CREATE TABLE pool_servers (id BIGINT PRIMARY KEY);
"""


def _resource(name: str, base: str, verbs: int) -> str:
    methods = "".join("""
    @GET
    @Path("/op%d/{id}")
    @ApiOperation(value = "op %d of %s", notes = "nested", response = Void.class)
    @ApiResponses(value = {@ApiResponse(code = 200, message = "ok"), @ApiResponse(code = 404, message = "missing")})
    public int op%d(@PathParam("id") long id, @QueryParam("q") String q) {
        return System.getenv("%s_OP%d") == null ? 0 : %d;
    }
""" % (i, i, name, i, name.upper(), i, i) for i in range(verbs))
    return """package com.acme.web;

import javax.ws.rs.GET;
import javax.ws.rs.Path;
import javax.ws.rs.PathParam;
import javax.ws.rs.QueryParam;

@Path("%s")
@Api(value = "%s", description = "%s resource")
public class %sResource {
%s}
""" % (base, name, name, name, methods)


CONSTANTS = """package com.acme.web;

public class ApiConstants {
    public static final String BASE = "/v1/reservations";
    public static final String POST = "POST";
    public static final String OK = "OK";
    public static final String STATUS = "RESERVED";
    public static final String KEY = "client";
}
"""

# Named without `Resource` so the `Resource$` regex test still sees three classes. The @Operation text
# runs past ANNOTATION_TEXT_MAX (400) before its nested @ApiResponse, so compact must keep `args`.
ENDPOINT = """package com.acme.web;

import javax.ws.rs.DefaultValue;
import javax.ws.rs.GET;
import javax.ws.rs.Path;
import javax.ws.rs.QueryParam;

@Path(ApiConstants.BASE)
public class ReservationEndpoint {
    @GET
    @Operation(method = ApiConstants.POST, description = "%s", responses = {@ApiResponse(responseCode = "200", description = ApiConstants.OK)})
    public int list(@DefaultValue(ApiConstants.STATUS) @QueryParam("status") String status,
                    @QueryParam(ApiConstants.KEY) String client) {
        return 0;
    }
}
""" % ("long description " * 30)

ROUTES = 11  # 4 + 3 + 3 resource routes, plus GET /v1/reservations


def build(tmp):
    repo = new_repo(tmp, "views")
    repo.write("pom.xml", pom("svc"))
    repo.write("src/main/resources/db/migration/V1__init.sql", SQL)
    repo.write("src/main/java/com/acme/web/ServerResource.java", _resource("Server", "/v1/servers", 4))
    repo.write("src/main/java/com/acme/web/PoolResource.java", _resource("Pool", "/v1/pools", 3))
    repo.write("src/main/java/com/acme/web/JobResource.java", _resource("Job", "/v1/jobs", 3))
    repo.write("src/main/java/com/acme/web/ApiConstants.java", CONSTANTS)
    repo.write("src/main/java/com/acme/web/ReservationEndpoint.java", ENDPOINT)
    # a line past REGEX_MAX_LINE, so the line guard has something to skip
    repo.write("src/main/java/com/acme/web/Long.java",
               "package com.acme.web;\n// needle %s\npublic class Long { int needle = 1; }\n" % ("x" * 2500))
    repo.commit("initial")
    return repo


CITE = re.compile(r"^[\w./\-@{}]+:\d+(-\d+)?$")


def facts(value, ctx=None, out=None):
    """The fact set of a detail or compact answer: cites, annotation text, resolved values, claims,
    routes, inputs, table readers/writers. A compact row's `annotations_in` + `line` is the detail `at`."""
    out = set() if out is None else out
    if isinstance(value, list):
        for v in value:
            facts(v, ctx, out)
        return out
    if not isinstance(value, dict):
        if isinstance(value, str) and CITE.match(value):
            out.add(("cite", value))
        return out
    ctx = value.get("annotations_in", value.get("file", ctx)) if "annotations" in value else ctx
    is_ann = isinstance(value.get("text"), str) and value["text"].startswith("@")
    if is_ann:
        # An input annotation (`@QueryParam`, `@DefaultValue`, ...) may be stated by the route's `inputs`
        # row instead, so its text is not a fact here -- but any constant value it carries still is.
        if value["text"][1:].split("(", 1)[0].rsplit(".", 1)[-1] not in INPUT_SIMPLE:
            at = value.get("at") or "%s:%s" % (ctx, value.get("line"))
            out.add(("ann", at, value["text"]))
            out.add(("cite", at))
        for ref, resolved in _refs(value.get("args"), {}).items():
            out.add(("resolved", ref, resolved))
        for ref, resolved in (value.get("resolved") or {}).items():
            out.add(("resolved", ref, resolved))
        if value["text"][1:].split("(", 1)[0].rsplit(".", 1)[-1] in INPUT_SIMPLE:
            return out  # its cite and text are compared through the `inputs` row
        if value["text"].endswith("..."):  # truncated: every argument past the cut lives only in `args`
            out.add(("args", value["text"], json.dumps(value.get("args"), sort_keys=True)))
    elif isinstance(value.get("resolved"), dict):  # compact hoists constant values to the answer
        for ref, resolved in value["resolved"].items():
            out.add(("resolved", ref, resolved))
    if "verb" in value and "route" in value:
        out.add(("route", value["verb"], value["route"]))
    if "param" in value and "kind" in value and "at" in value:
        out.add(("input", value["at"], value["kind"], value.get("name"), value["param"], value.get("default")))
        out.add(("cite", value["at"]))
        for ref, val in ((value.get("default_ref"), value.get("default")), (value.get("name_ref"), value.get("name"))):
            if ref:
                out.add(("resolved", ref, val))
    if "statement" in value and "id" in value:
        out.add(("claim", value["id"], value["statement"]))
    if "by" in value and "sites" in value:
        out.add(("site-owner", value["by"]))
    ev = value.get("evidence")
    if isinstance(ev, dict):  # compact: {file: [[line, anchor], ...]}
        for file, rows in ev.items():
            for line, anchor in rows:
                out.add(("cite", "%s:%s" % (file, line)))
                out.add(("anchor", file, line, anchor))
    elif isinstance(ev, list) and ev and isinstance(ev[0], dict):  # detail: [{file, line, anchor}]
        for e in ev:
            out.add(("cite", "%s:%s" % (e["file"], e["line"])))
            out.add(("anchor", e["file"], e["line"], e["anchor"]))
    for k, v in value.items():
        if k in ("evidence", "args", "resolved", "compact", "as_of"):
            continue
        facts(v, ctx if k != "classes" else None, out)
    return out


def _refs(value, acc):
    if isinstance(value, dict):
        if "ref" in value and "resolved" in value:
            acc[value["ref"]] = value["resolved"]
        for v in value.values():
            _refs(v, acc)
    elif isinstance(value, list):
        for v in value:
            _refs(v, acc)
    return acc


def leaves(value, out=None, skip=()):
    out = [] if out is None else out
    if isinstance(value, dict):
        for k, v in value.items():
            if k not in ("compact", "view", "capped", "as_of") + tuple(skip):  # `as_of` is abbreviated in text
                leaves(v, out, skip)
        if value.get("match") == "all":  # not stated in text: nothing was matched
            out.remove("all")
    elif isinstance(value, list):
        for v in value:
            leaves(v, out, skip)
    elif isinstance(value, str) and "\n" not in value:
        out.append(value)
    return out


@unittest.skipUnless(have_git(), "needs git")
class ViewsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.repo = build(cls.tmp.name)
        cls.cdp = Cdp(cls.tmp.name, cls.repo.path)
        cls.cdp.scan()
        cls.backend, cls.store = cls.cdp.open()

    @classmethod
    def tearDownClass(cls):
        cls.store.close()
        cls.tmp.cleanup()

    def q(self, kind, term=None, **kw):
        kw.setdefault("format", "json")
        kw.setdefault("max_tokens", 0)
        return query_mod.dispatch(self.store, kind, term, **kw)

    KINDS = (("routes", None), ("claims", "entrypoint"), ("table", None), ("config", None),
             ("symbol", "ServerResource"), ("file", "ServerResource.java"), ("module", "svc"),
             ("trace", "/v1/servers/op0/{id}"), ("search", "ServerResource"))

    # ---- lossless compact

    def test_compact_has_every_fact_of_detail(self):
        for kind, term in self.KINDS:
            detail = self.q(kind, term, view="detail", budget=10000)
            compact = self.q(kind, term, view="compact", budget=10000)
            want, got = facts(detail), facts(compact)
            self.assertEqual(want, got, "%s: lost %s; invented %s" % (
                kind, sorted(want - got, key=str)[:3], sorted(got - want, key=str)[:3]))

    def test_compact_is_smaller_than_detail_on_routes(self):
        detail = len(json.dumps(self.q("routes", view="detail")))
        compact = len(json.dumps(self.q("routes", view="compact")))
        self.assertLess(compact, detail * 0.7)

    def test_nested_annotations_resolve_in_compact(self):
        got = facts(self.q("routes", "/v1/servers", view="compact"))
        self.assertIn(("ann", "src/main/java/com/acme/web/ServerResource.java:12", '@GET'), got)
        self.assertTrue(any(f[0] == "ann" and f[2].startswith("@ApiResponses") for f in got))

    def test_constant_values_survive_compact(self):
        """Constants are where text alone is not enough: a default, an input name and an @Operation
        method declared through `ApiConstants` must reach compact with their values."""
        for view in ("detail", "compact"):
            out = self.q("routes", "GET /v1/reservations", match="exact", view=view)
            (row,) = out["routes"]
            inputs = {i["param"]: i for i in row["inputs"]}
            self.assertEqual((inputs["status"]["default"], inputs["status"]["default_ref"]),
                             ("RESERVED", "ApiConstants.STATUS"), view)
            self.assertEqual((inputs["client"]["name"], inputs["client"]["name_ref"]),
                             ("client", "ApiConstants.KEY"), view)
        got = facts(out)
        for ref, val in (("ApiConstants.POST", "POST"), ("ApiConstants.OK", "OK"), ("ApiConstants.BASE", "/v1/reservations")):
            self.assertIn(("resolved", ref, val), got)

    def test_truncated_annotation_keeps_its_args(self):
        out = self.q("routes", "GET /v1/reservations", match="exact", view="compact")
        (op,) = [a for a in out["routes"][0]["annotations"] if a["text"].startswith("@Operation")]
        self.assertTrue(op["text"].endswith("..."))
        self.assertEqual(op["args"]["responses"][0]["text"], '@ApiResponse(responseCode="200",description=ApiConstants.OK)')

    def test_a_plain_argument_past_the_cut_survives(self):
        """`parts` (nested annotations only) lost this; `args` keeps every argument."""
        from cdp.query import compact as compact_mod
        from cdp.lang.base import ANNOTATION_TEXT_MAX
        full = '@Operation(description="%s",operationId="makeReservations")' % ("x" * 420)
        ann = {"text": full[:ANNOTATION_TEXT_MAX - 3] + "...", "at": "R.java:10",
               "args": {"description": "x" * 420, "operationId": "makeReservations"}}
        out = compact_mod.compact({"query": "routes", "as_of": {"commit": "h"},
                                   "routes": [{"verb": "POST", "route": "/r", "handler": "R#m", "annotations": [ann]}]})
        self.assertEqual(out["routes"][0]["annotations"][0]["args"]["operationId"], "makeReservations")

    def test_one_constant_name_with_two_values_keeps_both(self):
        from cdp.query import compact as compact_mod
        def ann(line, value):
            return {"text": "@ApiResponse(description=ApiConstants.OK)", "at": "R.java:%d" % line,
                    "args": {"description": {"ref": "ApiConstants.OK", "resolved": value}}}
        row = {"verb": "GET", "route": "/r", "handler": "R#m", "annotations": [ann(1, "OK"), ann(2, "Okay")]}
        out = compact_mod.compact({"query": "routes", "routes": [row], "as_of": {"commit": "h"}})
        first, second = out["routes"][0]["annotations"]
        self.assertEqual(out["resolved"]["ApiConstants.OK"], "OK")  # the shared map holds the first value
        self.assertNotIn("resolved", first)
        self.assertEqual(second["resolved"], {"ApiConstants.OK": "Okay"})  # the differing one stays inline

    def test_a_default_compact_cannot_read_keeps_its_annotation(self):
        """If an input row has no `default`, compact must keep the `@DefaultValue` that states it."""
        from cdp.query import compact as compact_mod
        ann = {"text": "@DefaultValue(Unknown.X)", "at": "A.java:3", "args": {"value": {"ref": "Unknown.X"}}}
        row = {"verb": "GET", "route": "/x", "handler": "A#m", "inputs": [
            {"param": "s", "name": "s", "kind": "query", "at": "A.java:3"}],
            "params": [{"name": "s", "annotations": [ann, {"text": "@QueryParam(\"s\")", "at": "A.java:3"}]}]}
        out = compact_mod.compact({"query": "routes", "routes": [row], "as_of": {"commit": "h"}})
        kept = [a["text"] for p in out["routes"][0].get("params", []) for a in p["annotations"]]
        self.assertEqual(kept, ["@DefaultValue(Unknown.X)"])  # @QueryParam is stated by the input row

    def test_claim_timestamps_kept_unless_head(self):
        from cdp.query import compact as compact_mod
        base = {"id": "c", "kind": "entrypoint", "statement": "s", "subject": "x",
                "evidence": [{"file": "A.java", "line": 1, "anchor": "a"}]}
        claims = [dict(base, id="fresh", anchor_verified_at="h", claim_reviewed_at="h"),
                  dict(base, id="moved", anchor_verified_at="h", claim_reviewed_at="older"),
                  dict(base, id="edited", anchor_verified_at="h", claim_reviewed_at=None)]
        out = {c["id"]: c for c in compact_mod.compact({"query": "claims", "claims": claims,
                                                         "as_of": {"commit": "h"}})["claims"]}
        self.assertNotIn("claim_reviewed_at", out["fresh"])
        self.assertNotIn("anchor_verified_at", out["fresh"])
        self.assertEqual(out["moved"]["claim_reviewed_at"], "older")
        self.assertIn("claim_reviewed_at", out["edited"])  # None = edited since review: the staleness signal
        self.assertIsNone(out["edited"]["claim_reviewed_at"])

    # ---- lossless list

    def test_list_has_name_and_cite_of_every_detail_row(self):
        detail = self.q("routes", view="detail")
        rows = self.q("routes", view="list")["routes"]
        self.assertEqual(len(detail["routes"]), len(rows))
        for full, row in zip(detail["routes"], rows):
            self.assertEqual(row["name"], "%s %s" % (full["verb"], full["route"]))
            self.assertEqual(row["at"], full["evidence"][0])
        names = {r["name"] for r in self.q("table", view="list")["table" if False else "tables"]}
        self.assertEqual(names, {t["table"] for t in self.q("table", view="detail")["tables"]})
        keys = {r["name"] for r in self.q("config", view="list")["keys"]}
        self.assertEqual(keys, {k["key"] for k in self.q("config", view="detail")["keys"]})
        claims = self.q("claims", view="list")["claims"]
        full = self.q("claims", view="detail")["claims"]
        self.assertEqual([c["name"] for c in claims], [c["subject"] for c in full])

    def test_count_is_the_true_total(self):
        counts = self.q("routes", view="count")["counts"]
        self.assertEqual(counts, {"routes": len(self.q("routes", view="detail", budget=10000)["routes"])})
        small = self.q("routes", view="count", budget=2)
        self.assertEqual(small["counts"]["routes"], counts["routes"])  # the budget does not shrink a count
        self.assertEqual(self.q("search", "Resource", view="count")["counts"]["files"],
                         self.q("search", "Resource", view="detail", budget=10000)["counts"]["files"])

    # ---- paging and the cap

    def test_compact_pages_reach_every_row(self):
        """No pre-cut: compact/detail page over every row, as list does."""
        for view in ("compact", "detail"):
            seen, offset, whole = 0, 0, None
            while True:
                page = self.q("symbol", "op", view=view, max_tokens=400, offset=offset)
                whole = page["count"]  # a cut page always states the true total
                n = int(page["shown"].split("-")[1]) - offset
                seen += n
                if not page.get("next"):
                    break
                offset += n
            self.assertGreater(whole, 1, "the cap must bind in this test")
            self.assertEqual(seen, whole, view)
            self.assertEqual(self.q("symbol", "op", view=view).get("elided", 0), 0, view)

    def test_no_view_is_pre_cut_by_the_row_budget(self):
        """The fixture is too small for 200 rows to bind, so check what the query is asked for instead."""
        from unittest import mock
        real = query_mod._dispatch
        for view in ("count", "list", "compact", "detail"):
            with mock.patch.object(query_mod, "_dispatch", side_effect=real) as spy:
                self.q("symbol", "op", view=view)
            self.assertEqual(spy.call_args.kwargs.get("budget"), views.UNLIMITED_ROWS, view)
            with mock.patch.object(query_mod, "_dispatch", side_effect=real) as spy:
                self.q("symbol", "op", view=view, budget=5)  # an explicit budget is still honoured
            self.assertEqual(spy.call_args.kwargs.get("budget"), 5, view)

    def test_a_row_too_big_for_the_cap_says_how_to_get_all_of_it(self):
        out = self.q("symbol", "ServerResource", view="detail", max_tokens=100)
        self.assertIn("max_tokens=0 returns the whole row", out["capped"])
        self.assertEqual(out["shown"], "1-1")
        whole = self.q("symbol", "ServerResource", view="detail", max_tokens=0, offset=0)
        self.assertGreater(len(json.dumps(whole)), len(json.dumps(out)))

    def test_pages_joined_equal_the_uncapped_list(self):
        def rows_of(page, buckets):
            return [r["name"] + r.get("at", "") for b in buckets for r in page.get(b, [])]
        for kind, term, buckets in (("routes", None, ("routes",)), ("claims", None, ("claims",)),
                                    ("search", "Resource", views.PRIMARY["search"])):
            whole = rows_of(self.q(kind, term, view="list"), buckets)
            seen, offset, pages = [], 0, 0
            while True:
                page = self.q(kind, term, view="list", max_tokens=60, offset=offset)
                rows = rows_of(page, buckets)
                self.assertTrue(rows or not page.get("next"), "an empty page must not promise a next one")
                seen += rows
                pages += 1
                if not page.get("next"):
                    break
                self.assertIn("offset=%d" % (offset + len(rows)), page["next"])
                offset += len(rows)
                self.assertLess(pages, 500)
            self.assertEqual(whole, seen, kind)
            self.assertGreater(pages, 1, "the cap must bind in this test")

    def test_a_cut_answer_reports_count_shown_and_next(self):
        for view in ("list", "compact", "detail"):
            out = self.q("routes", view=view, max_tokens=150)
            self.assertEqual(out["count"], ROUTES, view)
            self.assertRegex(out["shown"], r"^1-\d+$")
            self.assertIn("offset=", out["next"])
            self.assertIn("capped", out)
            if view == "list":  # compact/detail always keep at least one row, which can alone pass a tiny cap
                self.assertLessEqual(len(json.dumps(out, separators=(",", ":"), sort_keys=True)), 150 * 4)
        out = self.q("routes", view="list", max_tokens=150, format="text")
        self.assertIn("next: view=list offset=", out["text"])

    def test_an_uncut_answer_has_no_cut_fields(self):
        out = self.q("routes", view="list")
        self.assertNotIn("next", out)
        self.assertNotIn("shown", out)

    def test_documented_cap_is_the_built_in_cap(self):
        from cdp.guide_kinds import PARAMS
        self.assertIn("default %d" % views.DEFAULT_MAX_TOKENS, PARAMS["max_tokens"][1])

    def test_default_cap_bounds_a_default_answer(self):
        out = query_mod.dispatch(self.store, "claims", None, include_library=True)
        self.assertLessEqual(len(out["text"]), views.DEFAULT_MAX_TOKENS * views.CHARS_PER_TOKEN + 800)

    def test_offset_past_the_end_is_an_error(self):
        with self.assertRaises(ValueError):
            self.q("routes", view="list", offset=999)

    # ---- format parity

    def test_text_carries_every_string_of_json(self):
        for kind, term in self.KINDS:
            for view in ("count", "list", "compact", "detail"):
                as_json = self.q(kind, term, view=view)
                as_text = self.q(kind, term, view=view, format="text")
                self.assertEqual(as_text["format"], "text")
                text = as_text["text"]

                def present(s):
                    # the text `list` shows names without their package and cites as the shortest unique suffix
                    return s in text or (view == "list" and (s.rsplit("/", 1)[-1] in text or s.rsplit(".", 1)[-1] in text))
                missing = [s for s in (x.replace(" format=json", "") for x in  # `next` repeats a json format
                                       leaves(as_json, skip=("kind",) if view == "list" else ()))
                           if len(s) > 1 and not present(s)]  # (`list` shows a row's kind only where kinds differ)
                self.assertEqual(missing[:3], [], "%s/%s" % (kind, view))

    def test_every_text_cite_opens_a_real_file(self):
        """Text rows print the full repo-relative path, as grep does: a cite must open directly in Read,
        and a shortened one can name two files."""
        cite = re.compile(r"(?<![\w/.-])([\w./\-{}@]+\.\w+):\d+")
        for kind, term in (("routes", None), ("claims", None), ("table", None), ("config", None),
                           ("search", "Resource")):
            text = self.q(kind, term, view="list", format="text")["text"]
            cites = cite.findall(text)
            self.assertTrue(cites, kind)
            for path in cites:
                self.assertTrue((Path(self.repo.path) / path).is_file(), "%s: %s" % (kind, path))

    def test_default_format_by_view(self):
        self.assertEqual(query_mod.dispatch(self.store, "routes", None)["format"], "text")
        self.assertEqual(query_mod.dispatch(self.store, "routes", None, view="count")["format"], "text")
        self.assertNotIn("format", query_mod.dispatch(self.store, "routes", None, view="compact"))
        self.assertNotIn("format", query_mod.dispatch(self.store, "routes", None, view="detail"))

    def test_default_view_by_kind(self):
        self.assertEqual(views.default_view("routes"), "list")
        self.assertEqual(views.default_view("trace"), "compact")
        self.assertEqual(query_mod.dispatch(self.store, "trace", "/v1/servers/op0/{id}", format="json")["view"], "compact")

    def test_stats_and_coverage_are_unchanged(self):
        for kind in ("stats", "coverage"):
            out = query_mod.dispatch(self.store, kind)
            self.assertNotIn("view", out)
            with self.assertRaises(ValueError):
                query_mod.dispatch(self.store, kind, view="list")

    # ---- regex

    def test_regex_on_structured_fields(self):
        routes = self.q("routes", r"^/v1/(servers|pools)", match="regex", view="list")
        self.assertEqual(routes["match"], "regex")
        self.assertEqual({r["name"].split()[1].split("/")[2] for r in routes["routes"]}, {"servers", "pools"})
        self.assertEqual(len(routes["routes"]), 7)
        symbols = self.q("symbol", r"Resource$", match="regex", view="list")["found"]
        self.assertEqual(sorted(r["name"] for r in symbols if r["name"].endswith("Resource")),
                         ["com.acme.web.JobResource", "com.acme.web.PoolResource", "com.acme.web.ServerResource"])
        self.assertTrue(all(r["name"].endswith("Resource") for r in symbols))
        config = self.q("config", r"^POOL_", match="regex", view="list")["keys"]
        self.assertEqual([k["name"] for k in config], ["POOL_OP0", "POOL_OP1", "POOL_OP2"])
        self.assertEqual([t["name"] for t in self.q("table", r"^server$", match="regex", view="list")["tables"]],
                         ["server"])  # `pool_servers` contains it but does not match the anchored pattern
        self.assertEqual(len(self.q("routes", "(?i)^get /V1/POOLS", match="regex", view="list")["routes"]), 3)

    def test_match_applies_to_every_kind_that_takes_a_term(self):
        from cdp.guide_kinds import APPLIES
        for kind, uses in APPLIES.items():
            takes = bool({"term", "frm", "to", "subject", "module"} & set(uses))
            self.assertEqual("match" in uses, takes, kind)
        # module
        self.assertTrue(self.q("module", "^s", match="regex", view="detail")["found"])
        self.assertTrue(self.q("module", "svc", match="exact", view="detail")["found"])
        self.assertFalse(self.q("module", "sv", match="exact", view="detail")["found"])
        # claims: the kind, subject and module filters
        kinds = {c["kind"] for c in self.q("claims", match="regex", claim_kind="^(entrypoint|naming)$",
                                           view="detail")["claims"]}
        self.assertIn("entrypoint", kinds)
        self.assertLessEqual(kinds, {"entrypoint", "naming"})
        self.assertEqual(self.q("claims", match="exact", claim_kind="entry", view="count")["counts"]["claims"], 0)
        routes = self.q("claims", match="regex", subject="^route:GET /v1/pools", view="detail")["claims"]
        self.assertEqual(len(routes), 3)
        # unknowns and paths accept it (this repo has none to match)
        self.assertEqual(self.q("unknowns", "^x", match="regex", view="count")["counts"], {"unknowns": 0})
        self.assertEqual(self.q("paths", frm="^zzz", match="regex", view="count")["counts"], {"paths": 0})
        for kind in ("module", "unknowns", "claims"):
            with self.assertRaises(ValueError, msg=kind):
                self.q(kind, "(bad", match="regex") if kind != "claims" else self.q(kind, subject="(bad", match="regex")

    def test_trace_match_modes(self):
        got = self.q("trace", r"^/v1/servers/op[01]/\{id\}$", match="regex", view="detail")
        self.assertTrue(got["found"])
        self.assertEqual(got["match"], "regex")
        self.assertEqual(got["also_matched"], ["GET /v1/servers/op1/{id}"])  # the other endpoint is named, not dropped
        self.assertTrue(self.q("trace", "/v1/servers/op0/{id}", match="exact", view="detail")["found"])
        self.assertFalse(self.q("trace", "/v1/servers/op", match="exact", view="detail")["found"])
        self.assertTrue(self.q("trace", "/v1/servers/op", view="detail")["found"])  # substring, as before

    def test_regex_is_case_sensitive_like_grep(self):
        self.assertEqual(self.q("routes", "^/V1/", match="regex", view="count")["counts"]["routes"], 0)

    def test_exact_alias_and_conflict(self):
        self.assertEqual(self.q("routes", "/v1/pools/op0/{id}", exact=True, view="count")["counts"]["routes"], 1)
        self.assertEqual(self.q("routes", "/v1/pools/op0/{id}", match="exact", view="count")["counts"]["routes"], 1)
        with self.assertRaises(ValueError):
            self.q("routes", "x", exact=True, match="regex")
        self.assertTrue(self.q("claims", match="regex", claim_kind="^entry", view="count")["counts"]["claims"])

    def test_source_regex_equals_grep(self):
        code = (getattr(self.store, "code", None) or {}).get("files") or {}
        self.assertTrue(code)
        for pattern in (r"getenv\(\"POOL_OP[0-9]\"\)", r"^public class [A-Z][a-z]+Resource", r"@Api(Operation|Responses)\(",
                        r"int op[0-9]+\(@PathParam"):
            got = {h["at"] for h in self.q("search", pattern, match="regex", view="detail")["code"]}
            want = set()
            for path in sorted(code):
                proc = subprocess.run(["grep", "-nE", "--", pattern, str(self.repo.path / path)],
                                      capture_output=True, text=True)
                want |= {"%s:%s" % (path, line.split(":", 1)[0]) for line in proc.stdout.splitlines()}
            self.assertEqual(want, got, pattern)
            self.assertTrue(want, pattern)

    def test_regex_guards_are_named(self):
        out = self.q("search", "needle", match="regex", view="detail")
        self.assertIn("longer than %d characters" % common.REGEX_MAX_LINE, out["not_searched"])
        self.assertTrue(any(h["at"].endswith("Long.java:3") for h in out["code"]))
        self.assertFalse(any(h["at"].endswith("Long.java:2") for h in out["code"]))
        saved = search.REGEX_TIME_BUDGET
        search.REGEX_TIME_BUDGET = -1
        try:
            out = self.q("search", "needle", match="regex", view="detail")
        finally:
            search.REGEX_TIME_BUDGET = saved
        self.assertIn("time budget", out["not_searched"])
        with self.assertRaises(ValueError):
            self.q("search", "a" * (common.REGEX_MAX_PATTERN + 1), match="regex")
        with self.assertRaises(ValueError):
            self.q("routes", "(unclosed", match="regex")

    # ---- the user's dial

    def test_config_sets_view_format_and_cap(self):
        cfg = {"max_tokens": 80, "view": {"routes": "count"}, "format": {"count": "json"}}
        out = query_mod.dispatch(self.store, "routes", None, query_config=cfg)
        self.assertEqual((out["view"], out["counts"]["routes"]), ("count", ROUTES))
        out = query_mod.dispatch(self.store, "routes", None, query_config={"default_view": "list", "max_tokens": 80})
        self.assertIn("next:", out["text"])
        # a call overrides the config
        out = query_mod.dispatch(self.store, "routes", None, query_config=cfg, view="list", max_tokens=0, format="json")
        self.assertEqual(len(out["routes"]), ROUTES)
        self.assertNotIn("next", out)

    def test_config_drop_fields_are_named(self):
        cfg = {"drop_fields": {"claims": ["source_nodes", "confidence"]}}
        out = query_mod.dispatch(self.store, "claims", "entrypoint", view="detail", format="json",
                                 query_config=cfg)
        self.assertTrue(out["claims"])
        self.assertFalse(any("source_nodes" in c or "confidence" in c for c in out["claims"]))
        self.assertIn("source_nodes", out["dropped_fields"])
        self.assertIn("confidence", out["dropped_fields"])

    def test_team_config_is_read_and_validated(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / ".cdp.toml").write_text(
                '[query]\nmax_tokens = 100\ndefault_view = "list"\nview = { trace = "compact" }\n'
                'format = { list = "text" }\ndrop_fields = { claims = ["source_nodes"] }\n')
            cfg = registry.team_query_config(Path(tmp))
            self.assertEqual(cfg["max_tokens"], 100)
            self.assertEqual(cfg["view"], {"trace": "compact"})
            self.assertEqual(cfg["drop_fields"], {"claims": ["source_nodes"]})
            with tempfile.TemporaryDirectory() as bare:
                self.assertEqual(registry.team_query_config(Path(bare)), {})
            for bad in ('max_tokens = -1', 'max_tokens = "x"', 'default_view = "huge"', 'view = { trace = "huge" }',
                        'format = { list = "xml" }', 'drop_fields = { claims = "x" }', 'bogus = 1'):
                (Path(tmp) / ".cdp.toml").write_text("[query]\n%s\n" % bad)
                with self.assertRaises(CdpError, msg=bad):
                    registry.team_query_config(Path(tmp))

    # ---- the surfaces

    def test_cli_views(self):
        def run(*args):
            return self.cdp.run("query", *args)
        text = run("routes").stdout
        self.assertIn("GET /v1/servers/op0/{id} → ServerResource#op0", text)
        self.assertEqual(json.loads(run("routes", "--view", "count", "--json").stdout)["counts"], {"routes": ROUTES})
        self.assertEqual(len(json.loads(run("routes", "--json", "--view", "detail", "--max-tokens", "0").stdout)["routes"]), ROUTES)
        self.assertIn("%d route(s)" % ROUTES, run("routes", "--view", "detail").stdout)  # the long-standing rendering
        for view in ("list", "compact", "count"):  # `--format json` without `--json` is JSON, not the detail renderer
            self.assertEqual(json.loads(run("routes", "--view", view, "--format", "json").stdout)["view"], view)
        self.assertIn("next: view=list offset=", run("routes", "--max-tokens", "100").stdout)
        self.assertEqual(self.cdp.run("query", "stats", "--view", "list", check=False).returncode, 2)



@unittest.skipUnless(have_git(), "needs git")
class FilterTest(unittest.TestCase):
    """`filter` (FILTER_PLAN.md): grep built into wide list/count answers, applied before totals, cap and paging."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.repo = build(cls.tmp.name)
        cls.cdp = Cdp(cls.tmp.name, cls.repo.path)
        cls.cdp.scan()
        cls.backend, cls.store = cls.cdp.open()

    @classmethod
    def tearDownClass(cls):
        cls.store.close()
        cls.tmp.cleanup()

    def q(self, kind, term=None, **kw):
        kw.setdefault("max_tokens", 0)
        return query_mod.dispatch(self.store, kind, term, **kw)

    def full_lines(self, kind, term=None):
        """Every row's full-name list line, as `--max-tokens 0 --view list` would print it."""
        out = self.q(kind, term, format="json", view="list")
        lines = []
        for key in views.PRIMARY[kind]:
            rows = out.get("unknowns" if key == "by_node" else key) or []
            lines += views._row_lines(rows, short=False)
        return lines

    def test_rows_equal_grep_on_the_full_lines(self):
        for kind, term, pat in (("routes", None, r"op1\b"), ("config", None, "_OP2"), ("search", "Resource", "op0")):
            every = self.full_lines(kind, term)
            want = [l for l in every if re.search(pat, l)]
            self.assertTrue(want, kind)
            self.assertLess(len(want), len(every), kind)
            got = self.q(kind, term, filter=pat, format="json")
            have = []
            for key in views.PRIMARY[kind]:
                have += views._row_lines(got.get(key) or [], short=False)
            self.assertEqual(have, want, kind)

    def test_cap_applies_after_the_filter(self):
        unfiltered = self.q("routes", format="text", view="list", max_tokens=0)
        every = self.full_lines("routes")
        pat = re.escape(every[-1].split()[0])  # a row at the very end of the answer
        want = [l for l in every if re.search(pat, l)]
        tight = len(unfiltered["text"]) // 40 or 1
        got = self.q("routes", filter=pat, max_tokens=tight, format="text")
        self.assertIn("matched: %d of %d rows" % (len(want), len(every)), got["text"])
        self.assertIn(every[-1].split()[0], got["text"])

    def test_count_reports_matched_totals(self):
        every = self.full_lines("routes")
        want = [l for l in every if "op1" in l]
        out = self.q("routes", view="count", filter="op1", format="json")
        self.assertEqual(out["counts"], {"routes": len(want)})
        self.assertEqual(out["matched"], "%d of %d rows" % (len(want), len(every)))
        self.assertIn("filter=op1", out["next"])

    def test_pages_join_to_the_matched_set_and_next_keeps_the_filter(self):
        every = self.full_lines("routes")
        want = [l for l in every if "op" in l]
        self.assertGreater(len(want), 2)
        seen, offset = [], 0
        while True:
            # a tight cap, so the filtered answer really pages
            out = self.q("routes", filter="op", format="json", max_tokens=60, offset=offset)
            page = views._row_lines(out["routes"], short=False)
            seen += page
            if not out.get("next"):
                break
            self.assertIn("filter=op", out["next"])
            offset += len(page)
        self.assertEqual(seen, want)

    def test_anchored_pattern_on_a_displayed_short_name_matches(self):
        # `search` symbols print `ServerResource`; the full name is `com.acme.web.ServerResource`. The expected
        # rows are literals, not rebuilt with the code under test.
        short = self.q("search", "ServerResource", filter="^ServerResource$", format="json")
        self.assertEqual(short["symbols"], [{"name": "com.acme.web.ServerResource"}])
        full = self.q("search", "ServerResource", filter=r"^com\.acme\.web\.ServerResource$", format="json")
        self.assertEqual(full["symbols"], [{"name": "com.acme.web.ServerResource"}])
        self.assertIn("matched: 1 of", self.q("search", "ServerResource", filter="^ServerResource$")["text"])

    def test_next_quotes_a_pattern_with_spaces_and_newlines(self):
        out = self.q("routes", filter="GET /v1|op", format="json", max_tokens=60)
        self.assertIn('filter="GET /v1|op"', out["next"])
        out = self.q("routes", filter="a\nb|op", format="text", max_tokens=60)
        self.assertIn('filter="a\\nb|op"', out["next"])
        self.assertNotIn("filter: a\n", out["text"])
        self.assertIn("filter=op ", self.q("routes", filter="op", format="json", max_tokens=60)["next"])

    def test_budget_with_filter_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "budget cuts rows before filter"):
            self.q("routes", filter="op", budget=2)

    def test_next_repeats_term_match_and_format(self):
        out = self.q("routes", "op", filter="GET", format="json", max_tokens=60)
        self.assertEqual(out["next"].split()[:5], ["view=list", "filter=GET", "term=op", "format=json", "offset=1"])
        out = self.q("config", "_OP", match="substring", filter="OP", max_tokens=40)
        self.assertIn("term=_OP match=substring", out["next"])
        self.assertEqual(query_mod._carried("x", {"exact": True}), {"term": "x", "match": "exact"})
        self.assertEqual(query_mod._carried(None, {}), {})
        self.assertIn("term=op", self.q("routes", "op", view="count", filter="GET", format="json")["next"])

    def test_following_next_returns_the_same_rows(self):
        first = self.q("routes", "op", match="regex", format="json", max_tokens=60)
        got = [r["name"] for r in first["routes"]]
        while first.get("next"):
            kw = dict(tok.split("=", 1) for tok in first["next"].split())
            first = self.q("routes", kw["term"], match=kw["match"], view=kw["view"], offset=int(kw["offset"]),
                           format=kw.get("format", "json"), max_tokens=60)
            got += [r["name"] for r in first["routes"]]
        every = self.q("routes", "op", match="regex", format="json", view="list")["routes"]
        self.assertEqual(got, [r["name"] for r in every])

    def test_filter_implies_list_and_rejects_compact_and_detail(self):
        self.assertEqual(self.q("trace", "/v1/servers/op0/{id}", filter="op")["view"], "list")
        for view in ("compact", "detail"):
            with self.assertRaisesRegex(ValueError, "term=<name> match=exact"):
                self.q("routes", filter="op", view=view)

    def test_zero_matches_still_says_how_many_rows_there_were(self):
        every = self.full_lines("routes")
        out = self.q("routes", filter="no-such-row-xyz", format="json")
        self.assertEqual(out["matched"], "0 of %d rows" % len(every))
        self.assertEqual(out["routes"], [])
        self.assertIn("0 of %d rows" % len(every), self.q("routes", filter="no-such-row-xyz")["text"])

    def test_text_and_json_return_the_same_rows(self):
        js = self.q("routes", filter="op1", format="json")
        tx = self.q("routes", filter="op1", format="text")["text"]
        for line in views._row_lines(js["routes"]):
            self.assertIn(line, tx)
        self.assertEqual(len(js["routes"]), len([l for l in tx.splitlines() if "→" in l]))

    def test_guards(self):
        with self.assertRaisesRegex(ValueError, "limit is"):
            self.q("routes", filter="a" * (common.REGEX_MAX_PATTERN + 1))
        with self.assertRaisesRegex(ValueError, "invalid regex"):
            self.q("routes", filter="(")
        rows = [("routes", {"verb": "GET", "route": "/x" * 1500, "handler": "a.B#c", "evidence": []})]
        kept, note = views._filter_rows("routes", rows, "x")
        self.assertEqual(kept, [])
        self.assertIn("not matched by filter", note[0])

    def test_unprojected_kinds_reject_filter(self):
        with self.assertRaises(ValueError):
            self.q("stats", filter="x")


if __name__ == "__main__":
    unittest.main()
