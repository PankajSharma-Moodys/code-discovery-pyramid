"""ANNOTATIONS_PLAN P5: the built-in rule table (`cdp/rules/*.json`, `cdp/rules.py`).

Engine tests use their own small rules, so they hold whatever the shipped families say; the
family tests pin the shipped rules to what the extractors used to emit.
"""

from __future__ import annotations

import json
import re
import tempfile
import unittest
from pathlib import Path

from helpers import extraction_of, facts_edges

from cdp import rules
from cdp.lang.base import ExtractContext
from cdp.lang.java import JavaExtractor

ROOT = Path(__file__).resolve().parent.parent


def extract(src: str, path: str = "a/C.java"):
    return JavaExtractor().extract(ExtractContext(path, src.split("\n"), "a"))


def mk(rule: dict, family: str = "t") -> dict:
    return rules._check(rule, {"family": family, "language": "java"})


def route_rule(**over) -> dict:
    rule = {"id": "t.get", "match": {"fqn": "x.Get", "on": "method"}, "aliases": ["Get"],
            "emit": {"channel": "http_in", "signal": "entity",
                     "target": "route:GET {join(owner.Base.value, value|path)}"}}
    rule.update(over)
    return mk(rule)


def run(src: str, rule_list, path: str = "a/C.java"):
    ex = extraction_of(extract(src, path))
    return rules.apply(ex, rule_list)


def targets(ex) -> list:
    return [e["target"] for e in rules.all_edges(ex) if e.get("rule")]


class LoaderTest(unittest.TestCase):
    def test_shipped_rules_load_and_have_unique_ids(self):
        loaded = rules.load_rules()
        self.assertTrue(loaded)
        self.assertEqual(len({r["id"] for r in loaded}), len(loaded))
        self.assertTrue(all(r["emit"]["channel"] for r in loaded))

    def test_bad_rules_are_refused(self):
        for bad in ({"id": "x", "match": {"on": "method"}, "emit": {"channel": "c", "target": "t"}},
                    {"id": "x", "match": {"fqn": "a.B", "on": "weird"}, "emit": {"channel": "c", "target": "t"}},
                    {"id": "x", "match": {"fqn": "a.B", "on": "method"}, "emit": {"channel": "c"}},
                    {"id": "x", "match": {"fqn": "a.B", "on": "method"}, "emit": {"channel": "c", "target": "t"},
                     "bogus": 1}):
            with self.assertRaises(rules.RuleError):
                mk(bad)

    def test_duplicate_ids_are_refused(self):
        rule = {"id": "dup", "match": {"fqn": "a.B", "on": "class"}, "emit": {"channel": "c", "target": "t"}}
        with tempfile.TemporaryDirectory() as tmp:
            for name in ("a.json", "b.json"):
                (Path(tmp) / name).write_text(json.dumps({"family": name, "rules": [rule]}))
            with self.assertRaises(rules.RuleError):
                rules.load_rules(Path(tmp))

    def test_p7_sql_hook_point_is_the_only_emit_extension(self):
        rule = mk({"id": "q", "match": {"fqn": "x.Query", "on": "method"},
                   "emit": {"channel": "read", "sql": "{value}"}})
        src = 'package a;\nimport x.Query;\nclass C {\n  @Query("select 1 from t")\n  void m() {}\n}\n'
        self.assertEqual(targets(run(src, [rule])), [])        # no hook installed: nothing emitted
        try:
            rules.SQL_HOOK = lambda text: [("table:t", "read")] if "from t" in text else []
            self.assertEqual(targets(run(src, [rule])), ["table:t"])
        finally:
            rules.SQL_HOOK = None


class MatcherTest(unittest.TestCase):
    SRC = ('package a;\nimport %s;\n@Base("/b")\nclass C {\n  @Get("/x") void m() {}\n}\n')

    def test_fqn_match(self):
        self.assertEqual(targets(run(self.SRC % "x.Get", [route_rule()])), ["route:GET /b/x"])

    def test_alias_matches_only_when_the_fqn_is_unresolved(self):
        ex = run('package a;\nimport x.*;\nclass C {\n  @Get("/x") void m() {}\n}\n', [route_rule()])
        self.assertEqual(targets(ex), ["route:GET /x"])           # wildcard import: alias fallback

    def test_same_simple_name_from_two_packages_does_not_collide(self):
        other = run(self.SRC % "other.pkg.Get", [route_rule()])
        self.assertEqual(targets(other), [])                        # resolved to another package's Get
        qualified = run('package a;\nclass C {\n  @x.Get("/q") void m() {}\n}\n', [route_rule()])
        self.assertEqual(targets(qualified), ["route:GET /q"])      # fully-qualified use
        both = run('package a;\nimport x.Get;\nclass C {\n  @Get("/a") void m() {}\n'
                   '  @other.pkg.Get("/b") void n() {}\n}\n', [route_rule()])
        self.assertEqual(targets(both), ["route:GET /a"])

    def test_edges_are_tagged_and_kept_out_of_io_edges(self):
        ex = run(self.SRC % "x.Get", [route_rule()])
        self.assertEqual([e["rule"] for e in ex["rule_edges"]], ["t.get"])
        self.assertTrue(all("rule" not in e for e in ex["io_edges"]))
        self.assertEqual(ex["rule_edges"][0]["file"], "a/C.java")


class TemplateTest(unittest.TestCase):
    def test_args_owner_annotation_and_join(self):
        src = ('package a;\nimport x.Get;\nimport x.Base;\n@Base("/b/")\nclass C {\n'
               '  @Get("/x") void m() {}\n  @Get(path = "y") void n() {}\n  @Get void o() {}\n}\n')
        self.assertEqual(sorted(targets(run(src, [route_rule()]))),
                         ["route:GET /b/", "route:GET /b/x", "route:GET /b/y"])

    def test_constants_stay_symbolic(self):
        src = ('package a;\nimport x.Get;\nimport x.Base;\n@Base(Api.ROOT + "/v1")\nclass C {\n'
               '  static final String P = "/p";\n  @Get(Api.USERS) void m() {}\n  @Get(P) void n() {}\n}\n')
        self.assertEqual(sorted(targets(run(src, [route_rule()]))),
                         ["route:GET ${Api.ROOT}/v1/${Api.USERS}", "route:GET ${Api.ROOT}/v1/${C.P}"])

    def test_first_alternative_with_a_value_wins_and_literals_fall_back(self):
        rule = mk({"id": "cfg", "match": {"fqn": "x.Props", "on": "class"},
                   "emit": {"channel": "config_read", "target": "config:{prefix|value|'(class)'}"}})
        for ann, want in (('@Props(prefix = "a.b")', "config:a.b"), ('@Props("c")', "config:c"),
                          ("@Props", "config:(class)")):
            self.assertEqual(targets(run("package a;\nimport x.Props;\n%s\nclass C {}\n" % ann, [rule])), [want])

    def test_keys_filter_yields_one_target_per_placeholder_key(self):
        rule = mk({"id": "v", "match": {"fqn": "x.Val", "on": ["field", "param"]},
                   "emit": {"channel": "config_read", "target": "config:{value:keys}"}})
        src = ('package a;\nimport x.Val;\nclass C {\n  @Val("${a.b:5}-${c}") String f;\n'
               '  C(@Val("${d}") String d) {}\n  @Val(Keys.X) String g;\n}\n')
        self.assertEqual(sorted(targets(run(src, [rule]))), ["config:a.b", "config:c", "config:d"])

    def test_alternative_targets_fall_back_in_order(self):
        rule = mk({"id": "e", "match": {"fqn": "x.Ent", "on": "class"},
                   "emit": {"channel": "persist", "target": ["table:{owner.Tab.name}", "entity:{owner.fqn}"]}})
        src = "package a;\nimport x.Ent;\nimport x.Tab;\n%sclass %s {}\n"
        self.assertEqual(targets(run(src % ('@Ent @Tab(name="t")\n', "C"), [rule])), ["table:t"])
        self.assertEqual(targets(run(src % ("@Ent\n", "C"), [rule])), ["entity:a.C"])

    def test_signals_and_counts_are_recomputed_idempotently(self):
        ex = run('package a;\nimport x.Get;\nclass C {\n  @Get("/x") void m() {}\n}\n', [route_rule()])
        self.assertIn("entity", ex["files"]["a/C.java"]["signals"])
        before = json.dumps(ex, sort_keys=True)
        rules.apply(ex, [route_rule()])
        self.assertEqual(json.dumps(ex, sort_keys=True), before)
        rules.apply(ex, [])
        self.assertNotIn("entity", ex["files"]["a/C.java"]["signals"])
        self.assertEqual(ex["rule_edges"], [])


class MetaAnnotationTest(unittest.TestCase):
    def _run(self, files, rule_list):
        ex = extraction_of(*[extract(src, path) for path, src in files])
        return rules.apply(ex, rule_list)

    def test_custom_annotation_inherits_ruled_meta_annotations_with_their_arguments(self):
        files = [("a/MyGet.java", 'package a;\nimport x.Get;\n@Get("/meta")\npublic @interface MyGet {}\n'),
                 ("a/C.java", "package a;\nclass C {\n  @MyGet void m() {}\n}\n")]
        ex = self._run(files, [route_rule()])
        self.assertEqual(targets(ex), ["route:GET /meta"])
        edge = ex["rule_edges"][0]
        self.assertEqual((edge["file"], edge["source"], edge["anchor"]["line"]), ("a/C.java", "a.C#m", 3))

    def test_depth_is_bounded_and_cycles_terminate(self):
        files = [("a/A.java", "package a;\n@B\npublic @interface A {}\n"),
                 ("a/B.java", "package a;\n@A\npublic @interface B {}\n"),
                 ("a/C.java", "package a;\nclass C {\n  @A void m() {}\n}\n")]
        self.assertEqual(targets(self._run(files, [route_rule()])), [])
        chain = [("a/M%d.java" % i, "package a;\n@M%d\npublic @interface M%d {}\n" % (i + 1, i)) for i in range(5)]
        chain.append(("a/M5.java", 'package a;\nimport x.Get;\n@Get("/deep")\npublic @interface M5 {}\n'))

        def use(name):
            return chain + [("a/C.java", "package a;\nclass C {\n  @%s void m() {}\n}\n" % name)]
        self.assertEqual(targets(self._run(use("M0"), [route_rule()])), [])             # deeper than META_DEPTH
        self.assertEqual(targets(self._run(use("M3"), [route_rule()])), ["route:GET /deep"])

    def test_an_annotation_with_its_own_rule_does_not_also_inherit(self):
        files = [("a/Get.java", 'package a;\n@Other\npublic @interface Get {}\n'),
                 ("a/C.java", 'package a;\nimport x.Get;\nclass C {\n  @Get("/x") void m() {}\n}\n')]
        self.assertEqual(targets(self._run(files, [route_rule()])), ["route:GET /x"])


class InheritanceTest(unittest.TestCase):
    FILES = [("a/Api.java", 'package a;\nimport x.Get;\nimport x.Base;\n@Base("/api")\npublic interface Api {\n'
                            '  @Get("/items") String items();\n}\n'),
             ("a/Impl.java", "package a;\npublic class Impl implements Api {\n  public String items() { return \"\"; }\n"
                             "  public String other() { return \"\"; }\n}\n")]

    def _run(self, rule):
        return rules.apply(extraction_of(*[extract(s, p) for p, s in self.FILES]), [rule])

    def test_off_by_default_the_interface_declaration_only(self):
        ex = self._run(route_rule())
        self.assertEqual([(e["source"], e["target"]) for e in ex["rule_edges"]],
                         [("a.Api#items", "route:GET /api/items")])

    def test_flag_applies_it_to_the_implementation_citing_the_interface_annotation(self):
        ex = self._run(route_rule(inherit=True))
        got = {(e["source"], e["target"]): e for e in ex["rule_edges"]}
        self.assertEqual(sorted(got), [("a.Api#items", "route:GET /api/items"),
                                       ("a.Impl#items", "route:GET /api/items")])
        self.assertEqual(got[("a.Impl#items", "route:GET /api/items")]["anchor"]["line"], 6)
        self.assertEqual(got[("a.Impl#items", "route:GET /api/items")]["file"], "a/Api.java")

    def test_inherit_only_rules_skip_the_declaration_and_methods_with_their_own_annotation(self):
        ex = self._run(route_rule(inherit=True, declared=False))
        self.assertEqual([e["source"] for e in ex["rule_edges"]], ["a.Impl#items"])
        files = [self.FILES[0], ("a/Impl.java", 'package a;\nimport x.Get;\npublic class Impl implements Api {\n'
                                                '  @Get("/own") public String items() { return ""; }\n}\n')]
        own = rules.apply(extraction_of(*[extract(s, p) for p, s in files]), [route_rule(inherit=True, declared=False)])
        self.assertEqual(own["rule_edges"], [])

    def test_supertype_cycles_terminate(self):
        files = [("a/P.java", "package a;\nimport x.Get;\ninterface P extends Q {\n  @Get(\"/p\") void m();\n}\n"),
                 ("a/Q.java", "package a;\ninterface Q extends P {}\n"),
                 ("a/I.java", "package a;\nclass I implements P { public void m() {} }\n")]
        ex = rules.apply(extraction_of(*[extract(s, p) for p, s in files]), [route_rule(inherit=True)])
        self.assertEqual(sorted(e["source"] for e in ex["rule_edges"]), ["a.I#m", "a.P#m"])


def shipped(src: str, path: str = "a/C.java"):
    """Edges the shipped rules make for one file, as `(rule id, source, target, line)`."""
    ex = extraction_of(extract(src, path))
    return [(e["rule"], e["source"], e["target"], e["anchor"]["line"]) for e in ex["rule_edges"]]


class JpaFamilyTest(unittest.TestCase):
    def test_entity_with_table_on_one_line_or_two(self):
        one = 'package a;\nimport javax.persistence.*;\n@Entity @Table(name="pool_config") class E {}\n'
        two = 'package a;\nimport jakarta.persistence.Entity;\nimport jakarta.persistence.Table;\n@Entity\n@Table(name = "w")\nclass E {}\n'
        self.assertEqual(shipped(one), [("jpa.entity", "a.E", "table:pool_config", 3)])
        self.assertEqual(shipped(two), [("jpa.entity", "a.E", "table:w", 4)])

    def test_entity_without_table_points_at_the_entity_not_a_guessed_table(self):
        self.assertEqual(shipped("package a;\nimport javax.persistence.Entity;\n@Entity\nclass E {}\n"),
                         [("jpa.entity", "a.E", "entity:a.E", 3)])

    def test_each_entity_takes_the_table_of_its_own_declaration(self):
        src = ('package a;\nimport javax.persistence.*;\n@Entity @Table(name="one") class A {}\n'
               '@Entity class B {}\n')
        self.assertEqual([(s, t) for _, s, t, _ in shipped(src)], [("a.A", "table:one"), ("a.B", "entity:a.B")])

    def test_another_packages_entity_is_not_jpa(self):
        self.assertEqual(shipped("package a;\nimport org.other.Entity;\n@Entity\nclass E {}\n"), [])

    def test_the_entity_signal_comes_from_the_rule(self):
        ex = extraction_of(extract("package a;\nimport javax.persistence.Entity;\n@Entity\nclass E {}\n"))
        self.assertIn("entity", ex["files"]["a/C.java"]["signals"])
        self.assertEqual(ex["files"]["a/C.java"]["io_edges"], len(rules.all_edges(ex)))


class ConfigFamilyTest(unittest.TestCase):
    def test_value_keys_from_field_method_and_constructor_parameter(self):
        src = ('package a;\nimport org.springframework.beans.factory.annotation.Value;\nclass C {\n'
               '  @Value("${a.b:30}") int f;\n'
               '  C(\n    @Value("${c.d}") String d,\n    @Value("${e}") String e) {}\n'
               '  @Value("${x}-${y:1}") void set(String s) {}\n}\n')
        got = [(s, t, line) for _, s, t, line in shipped(src)]
        self.assertEqual(sorted(got), [("a.C", "config:a.b", 4), ("a.C#<init>", "config:c.d", 6),
                                        ("a.C#<init>", "config:e", 7), ("a.C#set", "config:x", 8),
                                        ("a.C#set", "config:y", 8)])

    def test_configuration_properties_prefix_forms(self):
        for ann, want in (('@ConfigurationProperties(prefix = "pool")', "config:pool"),
                          ('@ConfigurationProperties("srv")', "config:srv"),
                          ("@ConfigurationProperties", "config:(class)")):
            src = "package a;\nimport org.springframework.boot.context.properties.*;\n%s\nclass P {}\n" % ann
            self.assertEqual([(s, t) for _, s, t, _ in shipped(src)], [("a.P", want)])

    def test_a_value_annotation_of_another_package_is_not_config(self):
        self.assertEqual(shipped('package a;\nimport org.other.Value;\nclass C {\n  @Value("${k}") int f;\n}\n'), [])


class AllEdgesTest(unittest.TestCase):
    def test_all_edges_merges_in_io_edges_order_and_returns_io_edges_when_there_are_no_rule_edges(self):
        io = [{"source": "b", "target": "t", "channel": "c", "file": "f", "anchor": {"file": "f", "line": 1}}]
        ex = {"io_edges": io}
        self.assertIs(rules.all_edges(ex), io)
        ex["rule_edges"] = [{"source": "a", "target": "t", "channel": "c", "file": "f", "anchor": {"file": "f", "line": 9},
                             "rule": "r"}]
        self.assertEqual([e["source"] for e in rules.all_edges(ex)], ["a", "b"])
        self.assertEqual([e for e in rules.edges_untagged(ex) if "rule" in e], [])
        self.assertEqual(rules.legacy_view(ex)["io_edges"], rules.edges_untagged(ex))
        self.assertNotIn("rule_edges", rules.legacy_view(ex))

    def test_no_consumer_reads_io_edges_directly(self):
        """Every read goes through `all_edges`; the allowed readers are the writers of `io_edges`
        and the leaf-prompt builder (owned by another change, listed so it is not forgotten)."""
        allowed = {"extract.py", "refresh.py", "rules.py", "prompts.py", "render.py"}
        pattern = re.compile(r"""(?:\[|get\()["']io_edges["']""")
        offenders = []
        for path in sorted((ROOT / "cdp").rglob("*.py")):
            if "_vendor" in path.parts or path.name in allowed:
                continue
            for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if pattern.search(line) and "totals" not in line:
                    offenders.append("%s:%d" % (path.relative_to(ROOT), n))
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
