"""F2 -- the Scala extractor. New code with real risk (no prior extractor
for this language), so it gets direct tests rather than relying solely on
the real-target exercise recorded in PHASE/TARGET.md."""

from __future__ import annotations

import unittest

from helpers import SKILL_ROOT  # noqa: F401  (sets sys.path)

from cdp.lang.base import ExtractContext
from cdp.lang.scala import ScalaExtractor


def extract(src: str, path: str = "sdk/DataCatalogService.scala"):
    ctx = ExtractContext(path=path, lines=src.splitlines(), module="root")
    return ScalaExtractor().extract(ctx)


class PackageAndImportsTest(unittest.TestCase):
    def test_flat_package(self) -> None:
        facts = extract("package com.rms.unifiedstore.sdk\n\nclass Foo\n")
        self.assertEqual(facts.package, "com.rms.unifiedstore.sdk")

    def test_single_and_wildcard_imports(self) -> None:
        facts = extract(
            "package p\n\n"
            "import com.fasterxml.jackson.databind.ObjectMapper\n"
            "import scala.collection.mutable._\n"
        )
        self.assertEqual(
            [i["fqn"] for i in facts.imports],
            ["com.fasterxml.jackson.databind.ObjectMapper", "scala.collection.mutable"],
        )

    def test_multi_import_expands_each_member(self) -> None:
        facts = extract(
            "package p\n\n"
            "import com.rms.unifiedstore.sdk.model.{ArtifactDetails, PortfolioDetails}\n"
        )
        self.assertEqual(
            [i["fqn"] for i in facts.imports],
            ["com.rms.unifiedstore.sdk.model.ArtifactDetails",
             "com.rms.unifiedstore.sdk.model.PortfolioDetails"],
        )


class DeclarationsTest(unittest.TestCase):
    def test_bodyless_case_class_does_not_swallow_the_next_declaration(self) -> None:
        """The real, common shape in this corpus: a multi-line `case class`
        with no trailing `{` at all, immediately followed by another
        declaration."""
        src = (
            "package p\n\n"
            "case class CatalogDetails(\n"
            "  id: String,\n"
            "  name: String\n"
            ")\n\n"
            "class DataCatalogService(config: String) {\n"
            "  def foo(): Unit = {}\n"
            "}\n"
        )
        facts = extract(src)
        fqns = [d["fqn"] for d in facts.defines]
        self.assertIn("p.CatalogDetails", fqns)
        self.assertIn("p.DataCatalogService", fqns)

    def test_same_line_brace_class(self) -> None:
        src = "package p\n\nclass Foo extends Bar {\n  val x = 1\n}\n"
        facts = extract(src)
        self.assertIn("p.Foo", [d["fqn"] for d in facts.defines])

    def test_object_declaration(self) -> None:
        facts = extract("package p\n\nobject ScalaRetryUtil {\n  def retry(): Unit = {}\n}\n")
        self.assertIn("p.ScalaRetryUtil", [d["fqn"] for d in facts.defines])


def defs(facts):
    return {d["fqn"]: d for d in facts.defines}


RESOURCE = (
    "package com.x.api\n"
    "\n"
    "import javax.ws.rs.{GET, PATCH, Path, Produces}\n"
    "import com.x.Consts\n"
    "\n"
    "@Path(Consts.BASE)\n"
    "@Produces(Array(MediaType.APPLICATION_JSON))\n"
    "class WorkflowResource @Inject() (\n"
    "    service: WorkflowService,\n"
    "    val mapper: Mapper[String, Int]\n"
    ") extends ResponseMapper with Other[T] {\n"
    "\n"
    "  @PATCH\n"
    "  @Path(\"/{id}\")\n"
    "  @Operation(security = Array(new SecurityRequirement(name = \"A\", scopes = Array(\"A\"))),\n"
    "    schema = classOf[JobResponse], `type` = X.Y, description = \"a\" + \"b\")\n"
    "  def update(@Auth user: User, @QueryParam(\"c\") clientId: String): JobResponse = {\n"
    "    service.go(user)\n"
    "  }\n"
    "\n"
    "  private[api] def hidden = 1\n"
    "  protected val p: Int = 2\n"
    "}\n"
    "\n"
    "object WorkflowResource {\n"
    "  final val Label = \"v2\"\n"
    "  val Q = \"\"\"\n"
    "    |select * from t\n"
    "    |where x = 1\"\"\".stripMargin\n"
    "}\n"
)


class TokensTest(unittest.TestCase):
    def test_triple_interpolated_backtick_and_lines(self) -> None:
        from cdp.lang.scala_tokens import ScTokens, string_value
        tk = ScTokens(['val a = s"x ${y("q")} $w" + """a', ' "q" b""" + `type`', "def f[T](x: T)"])
        strs = [t for k, t in zip(tk.kind, tk.text) if k == "str"]
        self.assertEqual(len(strs), 2)
        self.assertIsNone(string_value(strs[0]))
        self.assertEqual(string_value(strs[1]), 'a\n "q" b')
        self.assertIn("type", tk.text)
        self.assertEqual(tk.line[tk.text.index("def")], 2)
        self.assertEqual(tk.text[tk.close(tk.text.index("["))], "]")


class DeclarationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.f = extract(RESOURCE, "api/WorkflowResource.scala")
        self.d = defs(self.f)

    def test_kinds_visibility_and_extents(self) -> None:
        d = self.d
        self.assertEqual(d["com.x.api.WorkflowResource"]["kind"], "class")
        self.assertTrue(d["com.x.api.WorkflowResource"].get("companion"))
        self.assertEqual(d["com.x.api.WorkflowResource#hidden"]["visibility"], "package")
        self.assertEqual(d["com.x.api.WorkflowResource.p"]["visibility"], "protected")
        m = d["com.x.api.WorkflowResource#update"]
        self.assertEqual((m["anchor"]["line"], m["end_line"]), (17, 19))
        self.assertEqual(m["ret"], "com.x.api.JobResponse")

    def test_constructor_params_are_fields_and_ctor_takes_inject(self) -> None:
        d = self.d
        self.assertEqual(d["com.x.api.WorkflowResource.service"]["visibility"], "private")
        self.assertEqual(d["com.x.api.WorkflowResource.mapper"]["visibility"], "public")
        ctor = d["com.x.api.WorkflowResource#<init>"]
        self.assertEqual([a["name"] for a in ctor["annotations"]], ["Inject"])
        self.assertEqual([p["name"] for p in ctor["params"]], ["service", "mapper"])
        self.assertIn("di:Inject", self.f.signals)

    def test_supers_and_constants(self) -> None:
        d = self.d
        self.assertEqual(d["com.x.api.WorkflowResource"]["supertypes"],
                         ["com.x.api.ResponseMapper", "com.x.api.Other<com.x.api.T>"])
        self.assertEqual(d["com.x.api.WorkflowResource.Label"]["kind"], "constant")
        self.assertEqual(d["com.x.api.WorkflowResource.Label"]["value"], "v2")
        self.assertEqual(d["com.x.api.WorkflowResource.Q"]["value"], "\nselect * from t\nwhere x = 1")

    def test_trait_object_and_nested_package(self) -> None:
        f = extract("package a {\n  package b {\n    trait T { def m(x: Int): Unit }\n    object O extends App\n  }\n}\n")
        d = defs(f)
        self.assertEqual(d["a.b.T"]["kind"], "interface")
        self.assertTrue(d["a.b.O"]["object"])
        self.assertEqual(f.package, "a")
        self.assertIn("a.b.T#m", d)
        self.assertIn("main", f.signals)


class AnnotationTest(unittest.TestCase):
    def test_args_shapes(self) -> None:
        d = defs(extract(RESOURCE, "api/WorkflowResource.scala"))
        cls = {a["name"]: a for a in d["com.x.api.WorkflowResource"]["annotations"]}
        self.assertEqual(cls["Path"]["args"], {"value": {"ref": "Consts.BASE"}})
        self.assertEqual(cls["Path"]["fqn"], "javax.ws.rs.Path")
        self.assertEqual(cls["Produces"]["args"], {"value": [{"ref": "MediaType.APPLICATION_JSON"}]})
        m = {a["name"]: a for a in d["com.x.api.WorkflowResource#update"]["annotations"]}
        self.assertEqual([a for a in m], ["PATCH", "Path", "Operation"])
        self.assertEqual(m["Path"]["args"], {"value": "/{id}"})
        op = m["Operation"]["args"]
        self.assertEqual(op["schema"], {"class": "JobResponse"})
        self.assertEqual(op["type"], {"ref": "X.Y"})
        self.assertEqual(op["description"], "ab")
        nested = op["security"][0]
        self.assertEqual((nested["name"], nested["args"]["scopes"]), ("SecurityRequirement", ["A"]))
        params = d["com.x.api.WorkflowResource#update"]["params"]
        self.assertEqual(params[1]["annotations"][0]["args"], {"value": "c"})


class FlowTest(unittest.TestCase):
    def edges(self, src: str):
        f = extract(src)
        return [(e["source"].rsplit(".", 1)[-1], e["target"], e["channel"]) for e in f.io_edges]

    def test_config_reads(self) -> None:
        src = (
            "package p\nobject C {\n  final val K = \"KEY_A\"\n"
            "  def f(): Unit = {\n"
            "    val a = System.getenv(\"E1\")\n"
            "    val b = sys.env.getOrElse(K, \"d\")\n"
            "    val c = sys.props(\"p.x\")\n"
            "    val d = System.getenv(s\"X_${i}\")\n"
            "  }\n}\n"
        )
        got = [(s, t) for s, t, c in self.edges(src) if c == "config_read"]
        self.assertEqual(sorted(t for _, t in got), ["config:(dynamic)", "config:E1", "config:KEY_A", "config:p.x"])

    def test_main_and_http_out(self) -> None:
        src = (
            "package p\nobject App1 {\n  def main(args: Array[String]): Unit = {\n"
            "    client.target(\"http://svc/api\").path(\"/x\").request(MediaType.APPLICATION_JSON).post(e)\n"
            "    client.target(url.get).request().get()\n"
            "  }\n}\n"
        )
        got = self.edges(src)
        self.assertIn(("App1", "process:p.App1", "process_boundary"), got)
        self.assertIn(("App1#main", "http:POST http://svc/api/x", "http_out"), got)
        self.assertEqual(len([g for g in got if g[2] == "http_out"]), 1)   # an unknown URL is not an edge


class CallGraphTest(unittest.TestCase):
    SRC = (
        "package p\n"
        "import q.{Repo, Util}\n"
        "class Svc(repo: Repo, other: Other) {\n"
        "  private val dao: Dao = null\n"
        "  def run(id: Long): Unit = {\n"
        "    val r = repo.find(id)\n"
        "    r.touch(1)\n"
        "    val d: Dao = new Dao()\n"
        "    d.save(r)\n"
        "    Util.log(\"x\")\n"
        "    helper(1)(2)\n"
        "    xs.map { x => x.foo() }\n"
        "    unknown.call()\n"
        "    dao.put(id)\n"
        "  }\n"
        "  def helper(a: Int)(b: Int): Int = a + b\n"
        "}\n"
    )

    def calls(self):
        f = extract(self.SRC)
        return [(u["fqn"], u.get("chain"), u.get("recv"), bool(u.get("strict"))) for u in f.uses
                if u.get("kind") == "call"]

    def test_typed_chained_and_dropped(self) -> None:
        got = self.calls()
        self.assertIn(("q.Repo#find", None, None, False), got)                 # declared param type
        self.assertIn(("p.Dao#<init>", None, None, False), got)                # new Dao()
        self.assertIn(("p.Dao#save", None, None, False), got)                  # val d: Dao
        self.assertIn(("q.Util#log", None, None, False), got)                  # imported object
        self.assertIn(("p.Svc#helper", None, None, True), got)                 # curried bare call, strict
        self.assertIn(("p.Dao#put", None, None, False), got)                   # field typed by declaration
        # `val r = repo.find(id)` is untyped here: `r.m` carries the chain for the resolver
        self.assertTrue(any(c[0].endswith("#touch") and c[1] == ["m:find"] and c[2] == "q.Repo" for c in got))
        self.assertFalse(any("unknown" in c[0] or c[0].endswith("#foo") for c in got))  # untypable: no row


if __name__ == "__main__":
    unittest.main()
