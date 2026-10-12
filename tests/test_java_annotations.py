"""Java annotations on the index (ANNOTATIONS_PLAN P1): every annotation is stored verbatim
with its 1-based line span on the define row it decorates, including parameters, enum
constants and record components, and the annotation reader no longer assumes one annotation
per line at line start (T2-T4)."""

from __future__ import annotations

import unittest

from cdp.lang.base import ExtractContext
from cdp.lang.java import JavaExtractor


def extract(src: str):
    return JavaExtractor().extract(ExtractContext("a/C.java", src.split("\n"), "a"))


def define(facts, fqn):
    return next(d for d in facts.defines if d["fqn"] == fqn)


def edges(facts, channel):
    return [e["target"] for e in facts.io_edges if e["channel"] == channel]


class AnnotationCaptureTest(unittest.TestCase):
    def test_route_prefix_on_the_same_line_as_another_annotation(self):
        f = extract('package a;\nimport org.springframework.web.bind.annotation.*;\n'
                    '@RestController @RequestMapping("/c")\nclass C {\n'
                    '  @GetMapping("/x") String x() { return ""; }\n}\n')
        self.assertIn("route:GET /c/x", edges(f, "http_in"))

    def test_inline_table_annotation(self):
        f = extract('package a;\nimport javax.persistence.*;\n'
                    '@Entity @Table(name="pool_config") class E {}\n')
        self.assertIn("table:pool_config", edges(f, "persist"))

    def test_lines_are_one_based_and_span_multi_line_annotations(self):
        f = extract('package a;\nclass C {\n  @Every(\n    value = "60s")\n  void run() {}\n}\n')
        (ann,) = define(f, "a.C#run")["annotations"]
        self.assertEqual((ann["name"], ann["line"], ann["end_line"]), ("Every", 3, 4))
        self.assertEqual(ann["text"], '@Every(value="60s")')

    def test_parameter_annotations(self):
        f = extract('package a;\nclass C {\n'
                    '  void x(@PathVariable("id") Long id, @Valid @RequestBody String body) {}\n}\n')
        params = define(f, "a.C#x")["params"]
        self.assertEqual([(p["name"], [a["name"] for a in p.get("annotations", [])]) for p in params],
                         [("id", ["PathVariable"]), ("body", ["Valid", "RequestBody"])])

    def test_supertypes_resolved_through_imports(self):
        f = extract('package a;\nimport b.Base;\nclass C extends Base implements java.io.Serializable {}\n')
        self.assertEqual(define(f, "a.C")["supertypes"], ["b.Base", "java.io.Serializable"])

    def test_enum_constant_and_record_component_annotations(self):
        f = extract('package a;\nenum K { @Deprecated A, B }\nrecord R(@NotNull String id) {}\n')
        self.assertEqual(define(f, "a.K.A")["annotations"][0]["name"], "Deprecated")
        self.assertNotIn("annotations", define(f, "a.K.B"))
        self.assertEqual(define(f, "a.R.id")["annotations"][0]["name"], "NotNull")

    def test_annotation_in_string_or_comment_is_not_captured(self):
        f = extract('package a;\nclass C {\n  /* @Foo */ void x() { String s = "@Bar"; // @Baz\n  }\n}\n')
        self.assertNotIn("annotations", define(f, "a.C#x"))
        self.assertNotIn("annotations", define(f, "a.C"))

    def test_fqn_only_where_the_file_says_so(self):
        f = extract('package a;\nimport org.springframework.web.bind.annotation.GetMapping;\n'
                    '@interface Mine {}\n@Mine @org.x.Y("q") class C {\n'
                    '  @GetMapping("/x") @Transactional void x() {}\n}\n')
        cls = {a["name"]: a.get("fqn") for a in define(f, "a.C")["annotations"]}
        self.assertEqual(cls, {"Mine": "a.Mine", "Y": "org.x.Y"})
        meth = {a["name"]: a.get("fqn") for a in define(f, "a.C#x")["annotations"]}
        self.assertEqual(meth, {"GetMapping": "org.springframework.web.bind.annotation.GetMapping",
                                "Transactional": None})

    def test_long_annotation_text_is_cut(self):
        body = "\n".join('    + "%s"' % ("x" * 60) for _ in range(10))
        f = extract('package a;\nclass C {\n  @Query(""\n%s)\n  void q() {}\n}\n' % body)
        ann = define(f, "a.C#q")["annotations"][0]
        self.assertEqual(len(ann["text"]), 400)
        self.assertTrue(ann["text"].endswith("..."))

    def test_annotations_in_method_bodies_make_no_routes(self):
        f = extract('package a;\nimport org.springframework.web.bind.annotation.*;\nclass C {\n'
                    '  void m() { new Thread() { @GetMapping("/anon") public void run() {} }; }\n'
                    '  @GetMapping("/ok") void k() {}\n}\n')
        routes = [t for t in edges(f, "http_in") if t.startswith("route:")]
        self.assertEqual(routes, ["route:GET /ok"])

    def test_type_use_annotations_stay_out_of_type_text(self):
        f = extract('package a;\nclass C extends Base<@Baz String> {\n'
                    '  void f(List<@NonNull String> a) {}\n}\n')
        self.assertEqual(define(f, "a.C")["supertypes"], ["a.Base<String>"])
        self.assertEqual(define(f, "a.C#f")["params"][0]["type"], "List<String>")
        self.assertNotIn("annotations", define(f, "a.C#f")["params"][0])

    def test_string_literals_keep_their_spaces(self):
        f = extract('package a;\nclass C {\n  @Foo(b = "p  q")\n  void m() {}\n}\n')
        self.assertEqual(define(f, "a.C#m")["annotations"][0]["text"], '@Foo(b="p  q")')

    def test_type_keeps_its_static_flag(self):
        from cdp.lang.java_decl import JType
        self.assertFalse(JType("class", "C", "C", None).static)


if __name__ == "__main__":
    unittest.main()
