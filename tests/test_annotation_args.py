"""Java annotation arguments (ANNOTATIONS_PLAN P2): every value shape parsed from tokens into
`args`, constants resolved on xref sites, and a `@Value` default surfaced by `config`."""

from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path

from helpers import Pipeline, facts_edges

from cdp.lang.base import ExtractContext
from cdp.lang.java import JavaExtractor
from cdp.query.lookup import q_config
from cdp.query.render import render


def extract(src: str):
    return JavaExtractor().extract(ExtractContext("a/C.java", src.split("\n"), "a"))


def ann(src: str, fqn: str = "a.C", name: str = None):
    f = extract(src)
    row = next(d for d in f.defines if d["fqn"] == fqn)
    rows = row["annotations"]
    return rows[0] if name is None else next(a for a in rows if a["name"] == name)


def args_of(expr: str) -> dict:
    return ann("package a;\n@X(%s)\nclass C {}\n" % expr)["args"]


class ValueShapeTest(unittest.TestCase):
    def test_single_unnamed_argument_is_value(self):
        self.assertEqual(args_of('"/x"'), {"value": "/x"})

    def test_named_string_number_bool(self):
        self.assertEqual(args_of('s="a", n=30, l=60L, f=1.5, h=0x10, neg=-2, b=true, c=false'),
                         {"s": "a", "n": 30, "l": 60, "f": 1.5, "h": 16, "neg": -2, "b": True, "c": False})

    def test_string_escapes(self):
        self.assertEqual(args_of(r'v="a\"b\nA"'), {"v": 'a"b\nA'})

    def test_enum_and_constant_refs(self):
        self.assertEqual(args_of("misfirePolicy=Every.MisfirePolicy.NOW_WITH_REMAINING_COUNT, p=BASE"),
                         {"misfirePolicy": {"ref": "Every.MisfirePolicy.NOW_WITH_REMAINING_COUNT"},
                          "p": {"ref": "BASE"}})

    def test_class_literal(self):
        self.assertEqual(args_of("value=Foo.class, o=a.b.Bar.class"),
                         {"value": {"class": "Foo"}, "o": {"class": "a.b.Bar"}})

    def test_array_values(self):
        self.assertEqual(args_of('value={"a", "b"}'), {"value": ["a", "b"]})
        self.assertEqual(args_of("value={}"), {"value": []})
        self.assertEqual(args_of("x={A.B, Foo.class, 3,}"),
                         {"x": [{"ref": "A.B"}, {"class": "Foo"}, 3]})

    def test_concatenation(self):
        self.assertEqual(args_of('BASE + "/x"'), {"value": {"concat": [{"ref": "BASE"}, "/x"]}})
        self.assertEqual(args_of('"/a" + "/b"'), {"value": "/a/b"})
        self.assertEqual(args_of('Api.ROOT + "/v" + 1 + Api.TAIL'),
                         {"value": {"concat": [{"ref": "Api.ROOT"}, "/v1", {"ref": "Api.TAIL"}]}})

    def test_unparseable_falls_back_to_text(self):
        self.assertEqual(args_of("value = compute(1, 2)"), {"value": {"text": "compute(1,2)"}})
        self.assertEqual(args_of("a = cond ? 1 : 2, b = 1"), {"a": {"text": "cond?1:2"}, "b": 1})

    def test_no_arguments_means_no_args_key(self):
        self.assertNotIn("args", ann("package a;\n@X\nclass C {}\n"))
        self.assertNotIn("args", ann("package a;\n@X()\nclass C {}\n"))

    def test_nested_annotation_array(self):
        a = ann('package a;\n@Schedules({@Scheduled(cron="0 0 * * * *"), @Scheduled(fixedRate=5000, zone="UTC")})\n'
                "class C {}\n")
        first, second = a["args"]["value"]
        self.assertEqual((first["name"], first["args"]), ("Scheduled", {"cron": "0 0 * * * *"}))
        self.assertEqual(second["args"], {"fixedRate": 5000, "zone": "UTC"})
        self.assertEqual(first["line"], 2)
        self.assertTrue(first["text"].startswith("@Scheduled("))

    def test_single_nested_annotation_and_attribute_named_value(self):
        a = ann('package a;\n@Outer(inner=@Inner("z"), value=@Other)\nclass C {}\n')
        self.assertEqual(a["args"]["inner"]["args"], {"value": "z"})
        self.assertEqual(a["args"]["value"]["name"], "Other")
        self.assertNotIn("args", a["args"]["value"])

    def test_text_block_in_query(self):
        src = ('package a;\nclass C {\n  @Query(value = """\n      SELECT *\n        FROM t\n'
               '      WHERE x = 1\n      """, nativeQuery = true)\n  void q() {}\n}\n')
        a = ann(src, "a.C#q")
        self.assertEqual(a["args"], {"value": "SELECT *\n  FROM t\nWHERE x = 1\n", "nativeQuery": True})

    def test_text_block_with_quotes_and_close_on_last_content_line(self):
        src = 'package a;\n@Q("""\n  say "hi"\\\n  there""")\nclass C {}\n'
        self.assertEqual(ann(src)["args"], {"value": 'say "hi"there'})

    def test_string_with_annotation_lookalike_is_just_a_string(self):
        self.assertEqual(args_of('"@Foo(1), {x}"'), {"value": "@Foo(1), {x}"})


class PlacementTest(unittest.TestCase):
    def test_args_on_members_and_parameters(self):
        f = extract('package a;\nclass C {\n  @GetMapping(path="/p")\n  String m(@PathVariable("id") Long id, '
                    '@RequestParam(required=false) String q) { return ""; }\n}\n')
        m = next(d for d in f.defines if d["fqn"] == "a.C#m")
        self.assertEqual(m["annotations"][0]["args"], {"path": "/p"})
        self.assertEqual(m["params"][0]["annotations"][0]["args"], {"value": "id"})
        self.assertEqual(m["params"][1]["annotations"][0]["args"], {"required": False})

    def test_repeated_annotations_each_keep_their_args(self):
        f = extract('package a;\n@Role("a")\n@Role("b")\nclass C {}\n')
        rows = next(d for d in f.defines if d["fqn"] == "a.C")["annotations"]
        self.assertEqual([r["args"]["value"] for r in rows], ["a", "b"])

    def test_fully_qualified_annotation_name(self):
        a = ann('package a;\n@org.quartz.DisallowConcurrentExecution @x.y.Every(value="1s")\nclass C {}\n',
                name="Every")
        self.assertEqual(a["args"], {"value": "1s"})

    def test_annotation_in_comment_or_string_is_not_parsed(self):
        f = extract('package a;\n// @Every("1s")\nclass C { String s = "@Every(\\"2s\\")"; }\n')
        self.assertFalse(next(d for d in f.defines if d["fqn"] == "a.C").get("annotations"))

    def test_2000_char_query_keeps_full_args_and_truncated_text(self):
        sql = "SELECT " + ", ".join("col%d" % i for i in range(300)) + " FROM t"
        self.assertGreater(len(sql), 1800)
        a = ann('package a;\nclass C {\n  @Query("%s")\n  void q() {}\n}\n' % sql, "a.C#q")
        self.assertEqual(a["args"]["value"], sql)
        self.assertTrue(a["text"].endswith("..."))
        self.assertLessEqual(len(a["text"]), 400)

    def test_500_annotated_fields_are_fast(self):
        fields = "\n".join('  @Value("${k%d:%d}") @Size(min=1, max=%d) String f%d;' % (i, i, i, i)
                           for i in range(500))
        src = "package a;\nclass C {\n%s\n}\n" % fields
        t = time.time()
        f = extract(src)
        self.assertLess(time.time() - t, 5.0)
        d = next(d for d in f.defines if d["fqn"] == "a.C.f499" or d["fqn"] == "a.C#f499")
        self.assertEqual(d["annotations"][0]["args"], {"value": "${k499:499}"})
        self.assertEqual(d["annotations"][1]["args"], {"min": 1, "max": 499})

    def test_edges_are_unchanged_by_args(self):
        f = extract('package a;\nimport org.springframework.beans.factory.annotation.Value;\nclass C {\n'
                    '  @Value("${k:30}") int n;\n}\n')
        self.assertIn("config:k", [e["target"] for e in facts_edges(f) if e["channel"] == "config_read"])


CONSTANTS = """package a.api;

public final class ApiConstants {
    public static final String ROOT = "/v1";
    public static final String SERVERS = ROOT + "/servers";
}
"""

CONTROLLER = """package a.web;

import a.api.ApiConstants;
import org.springframework.web.bind.annotation.*;
import org.springframework.beans.factory.annotation.Value;

@RestController
@RequestMapping(ApiConstants.SERVERS)
public class C {
    static final String LOCAL = "/local";

    @GetMapping(LOCAL + "/x")
    public String x() { return ""; }

    @GetMapping(ApiConstants.ROOT + "/y" + Missing.NOPE)
    public String y() { return ""; }

    @Scheduled(zone = ApiConstants.NOPE)
    public void z() {}

    @Value("${pool.size:30}")
    private int size;

    @Value("${pool.name}")
    private String name;

    @Value("${a.b:x}:${c.d:y}")
    private String both;

    public int read(@RequestParam(ApiConstants.ROOT) String p) { return size; }
}
"""


class ResolveAndConfigTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        root = Path(cls.tmp.name) / "r"
        for rel, body in (("src/main/java/a/api/ApiConstants.java", CONSTANTS),
                          ("src/main/java/a/web/C.java", CONTROLLER)):
            path = root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(body)
        (root / "build.gradle").write_text("apply plugin: 'java'\n")
        cls.p = Pipeline(root)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def site(self, fqn):
        return self.p.xref["symbols"][fqn]["sites"][0]

    def test_constant_from_another_file_resolves(self):
        a = self.site("a.web.C")["annotations"][1]
        self.assertEqual(a["args"]["value"], {"ref": "ApiConstants.SERVERS", "resolved": "/v1/servers"})

    def test_concat_with_same_class_constant_resolves(self):
        a = self.site("a.web.C#x")["annotations"][0]
        self.assertEqual(a["args"]["value"]["resolved"], "/local/x")

    def test_param_annotation_ref_resolves(self):
        p = self.site("a.web.C#read")["params"][0]["annotations"][0]
        self.assertEqual(p["args"]["value"]["resolved"], "/v1")

    def test_unresolvable_stays_as_is(self):
        y = self.site("a.web.C#y")["annotations"][0]["args"]["value"]
        self.assertNotIn("resolved", y)
        self.assertEqual(y["concat"][2], {"ref": "Missing.NOPE"})
        z = self.site("a.web.C#z")["annotations"][0]["args"]["zone"]
        self.assertEqual(z, {"ref": "ApiConstants.NOPE"})

    def test_extraction_rows_are_not_mutated(self):
        row = next(d for d in self.p.extraction["defines"] if d["fqn"] == "a.web.C")
        self.assertNotIn("resolved", str(row["annotations"][1]["args"]))

    def test_config_surfaces_the_value_default(self):
        class S:
            extraction, xref, inventory = self.p.extraction, self.p.xref, self.p.inventory
            dataflow = self.p.dataflow
            state = {"claims": [], "unknowns": [], "provenance": {}}

            def node_of(self, path):
                return "root"

        out = q_config(S(), "pool.size")
        (key,) = out["keys"]
        self.assertEqual(key["read"][0]["default"], "30")
        self.assertIn("default: '30'", render(out))
        (nodef,) = q_config(S(), "pool.name")["keys"]
        self.assertNotIn("default", nodef["read"][0])
        both = {k["key"]: k["read"][0].get("default") for k in q_config(S(), "d")["keys"] + q_config(S(), "a.b")["keys"]}
        self.assertEqual(both["c.d"], "y")
        self.assertEqual(both["a.b"], "x")


if __name__ == "__main__":
    unittest.main()
