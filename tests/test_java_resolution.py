"""Java resolution corners: implicit constructors, config through providers,
`in` as an identifier, fully qualified types, type-parameter bounds, `Outer.this`."""

from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from helpers import Pipeline, have_git


def inline_repo(tmp: Path, files: dict) -> Path:
    for rel, text in files.items():
        f = tmp / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(text)
    env = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@x", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@x", "PATH": "/usr/bin:/bin:/usr/local/bin", "HOME": str(tmp)}
    for args in (["init", "-q", "-b", "main"], ["add", "-A"],
                 ["-c", "commit.gpgsign=false", "commit", "-q", "-m", "x"]):
        subprocess.run(["git", "-C", str(tmp)] + args, check=True, capture_output=True, env=env)
    return tmp


class Base(unittest.TestCase):
    FILES: dict = {}

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.p = Pipeline(inline_repo(Path(cls.tmp.name), cls.FILES))

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def callers(self, target: str):
        """`(file basename, line)` of every use of `target`."""
        return {(u["file"].rsplit("/", 1)[-1], u["anchor"]["line"])
                for u in self.p.xref["used_by"].get(target, [])}

    def sites(self, target: str):
        return {(u["file"].rsplit("/", 1)[-1]) for u in self.p.xref["used_by"].get(target, [])}


class ImplicitCtorTest(Base):
    FILES = {
        "pom.xml": "<project><artifactId>m</artifactId></project>",
        "src/main/java/a/Plain.java": "package a;\npublic class Plain { public void go() {} }\n",
        "src/main/java/a/Explicit.java": "package a;\npublic class Explicit { public Explicit(int x) {}\n"
                                         "  public Explicit() {} }\n",
        "src/main/java/a/User.java": "package a;\npublic class User {\n"
                                     "  void f() {\n    use(new Plain());\n    use(new Explicit(1));\n"
                                     "    new Plain().go();\n  }\n  void use(Object o) {}\n}\n",
    }

    def test_implicit_constructor_use_lands_on_the_class(self):
        self.assertEqual({("User.java", 4), ("User.java", 6)}, self.callers("a.Plain"))

    def test_explicit_constructor_use_lands_on_the_constructor(self):
        self.assertEqual({("User.java", 5)}, self.callers("a.Explicit#<init>"))

    def test_symbol_query_lists_instantiations(self):
        from cdp.query import lookup
        store = _store(self.p)
        for cls, want in (("a.Plain", {4, 6}), ("a.Explicit", {5})):
            found = lookup.q_symbol(store, cls, exact=True)["found"]
            row = [f for f in found if f["fqn"] == cls][0]
            lines = {int(u["at"].rsplit(":", 1)[1]) for u in row["used_by"] if "User.java" in u["at"]}
            self.assertEqual(lines, want)


class _Store:
    def __init__(self, p):
        self.extraction, self.xref, self.inventory = p.extraction, p.xref, p.inventory
        self.graph = p.graph
        self.state = {"claims": []}


def _store(p):
    return _Store(p)


class InKeywordTest(Base):
    FILES = {
        "pom.xml": "<project><artifactId>m</artifactId></project>",
        "src/main/java/a/W.java": "package a;\npublic class W { public void w0() {} }\n",
        "src/main/java/a/U.java": "package a;\npublic class U {\n  void f() {\n    W in = new W();\n"
                                  "    in.w0(\"in-f\");\n  }\n  void g(W in) {\n    in.w0(\"in-g\");\n  }\n}\n",
    }

    def test_local_and_param_named_in_are_typed(self):
        self.assertEqual({("U.java", 5), ("U.java", 8)}, self.callers("a.W#w0"))


POM = "<project><artifactId>m</artifactId></project>"


class QualifiedTypeTest(Base):
    FILES = {
        "pom.xml": POM,
        "src/main/java/p/W.java": "package p;\npublic class W { public void w0() {} }\n",
        "src/main/java/q/W.java": "package q;\npublic class W { public void w0() {} }\n",
        "src/main/java/a/Repo.java": "package a;\npublic class Repo<T> { public T first() { return null; } public void drop() {} }\n",
        "src/main/java/b/Repo.java": "package b;\npublic class Repo<T> { public void drop() {} }\n",
        "src/main/java/q/Outer.java": "package q;\npublic class Outer { public static class W { public void w0() {} }\n"
                                      "  public static class In { public void deep() {} } }\n",
        "src/main/java/q/U.java": "package q;\nimport b.Repo;\npublic class U {\n"
                                  "  void f() {\n    p.W x = new p.W();\n    x.w0(\"px\");\n    W y = new W();\n    y.w0(\"qy\");\n  }\n"
                                  "  void g(a.Repo<String> names, Repo<String> other) {\n    names.drop(\"n1\");\n    other.drop(\"n2\");\n  }\n"
                                  "  void h(q.Outer.In i, Outer.W w) {\n    i.deep(\"d1\");\n    w.w0(\"w1\");\n  }\n}\n",
    }

    def test_package_qualified_type_is_not_the_same_package_class(self):
        self.assertIn(("U.java", 6), self.callers("p.W#w0"))
        self.assertNotIn(("U.java", 6), self.callers("q.W#w0"))
        self.assertIn(("U.java", 8), self.callers("q.W#w0"))

    def test_qualified_generic_beats_the_import_of_the_same_simple_name(self):
        self.assertIn(("U.java", 11), self.callers("a.Repo#drop"))
        self.assertNotIn(("U.java", 11), self.callers("b.Repo#drop"))
        self.assertIn(("U.java", 12), self.callers("b.Repo#drop"))

    def test_nested_types_by_outer_path(self):
        self.assertIn(("U.java", 15), self.callers("q.Outer.In#deep"))
        self.assertIn(("U.java", 16), self.callers("q.Outer.W#w0"))
        self.assertNotIn(("U.java", 16), self.callers("q.W#w0"))


class BoundsTest(Base):
    FILES = {
        "pom.xml": POM,
        "src/main/java/t/Base.java": "package t;\npublic class Base { public void exec(String s) {} }\n",
        "src/main/java/t/A.java": "package t;\npublic class A extends Base { public void exec2(String s) {} }\n",
        "src/main/java/t/Cap.java": "package t;\npublic interface Cap { void ping(String s); }\n",
        "src/main/java/t/Q.java": "package t;\npublic class Q { public void ping(String s) {} }\n",
        "src/main/java/t/U.java": """package t;
import java.util.List;
public class U {
  <T extends Base> void f(T t) {
    t.exec("f-one");
  }
  <X extends A> void g(X x) {
    x.exec2("g-two");
    x.exec("g-inh");
  }
  void h(List<? extends Base> l) {
    l.get(0).exec("h-three");
  }
  <Z extends Base & Cap> void i(Z z) {
    z.ping("i-four");
    z.exec("i-four-b");
  }
  static class Box<T extends Base> {
    T v;
    void k() {
      v.exec("k-five");
    }
  }
  void unbounded(Object o, List<Base> lst) {
    lst.get(0).exec("u-six");
  }
}
""",
        "src/main/java/t/S.java": """package t;
public class S {
  void calc(String q) {}
  class Inner {
    void go() {
      S.this.calc("c-seven");
    }
    class Deeper {
      void dive() {
        S.this.calc("d-eight");
        Inner.this.go();
      }
    }
  }
}
""",
    }

    def test_method_type_parameter_bound(self):
        self.assertIn(("U.java", 5), self.callers("t.Base#exec"))

    def test_bound_inherited_method(self):
        self.assertIn(("U.java", 8), self.callers("t.A#exec2"))
        self.assertIn(("U.java", 9), self.callers("t.Base#exec"))

    def test_wildcard_bound_element(self):
        self.assertIn(("U.java", 12), self.callers("t.Base#exec"))

    def test_intersection_bound_tries_each(self):
        self.assertIn(("U.java", 15), self.callers("t.Cap#ping"))
        self.assertIn(("U.java", 16), self.callers("t.Base#exec"))

    def test_class_type_parameter_bound_on_field(self):
        self.assertIn(("U.java", 21), self.callers("t.Base#exec"))

    def test_qualifier_dot_this(self):
        self.assertIn(("S.java", 6), self.callers("t.S#calc"))
        self.assertIn(("S.java", 10), self.callers("t.S#calc"))
        self.assertIn(("S.java", 11), self.callers("t.S.Inner#go"))


class ConfigThroughProviderTest(Base):
    FILES = {
        "pom.xml": POM,
        "src/main/java/c/Keys.java": """package c;
public final class Keys {
  public static final String URL = "APP_URL";
  public static final String SCHEMA = "APP_SCHEMA";
  public static final String ENVK = "APP_ENV_KEY";
  public static final String DEEP = "APP_DEEP_KEY";
  public static final String NOT_CONFIG = "NOT_A_CONFIG_KEY";
}
""",
        "src/main/java/c/Conn.java": """package c;
import com.vendor.config.ConfigProvider;
import java.util.Map;
public class Conn {
  private Map<String, String> cache;
  private Registry registry;
  String direct(ConfigProvider configProvider) {
    return configProvider.getValue(Keys.URL);
  }
  String literal(Ctx ctx) {
    return ctx.getConfigProvider().getValue("LIT_KEY");
  }
  String viaWrapper(ConfigProvider cp) {
    return opt(cp, Keys.SCHEMA);
  }
  static String opt(ConfigProvider p, String key) {
    return p.getOptionalValue(key);
  }
  String viaEnv() {
    return env(Keys.ENVK) + env2(Keys.DEEP);
  }
  static String env(String name) {
    return System.getenv(name);
  }
  static String env2(String k) {
    return env(k);
  }
  void notConfig() {
    cache.get(Keys.NOT_CONFIG);
    registry.get(Keys.NOT_CONFIG);
    opt2(Keys.NOT_CONFIG);
  }
  static void opt2(String x) {}
}
""",
    }

    @classmethod
    def reads(cls):
        from cdp.resolve import config_reads
        return {(r["key"], r["anchor"]["line"]) for r in config_reads(
            cls.p.extraction, cls.p.xref["constants"], cls.p.xref["config_wrapped"])
            if r["file"].endswith("Conn.java")}

    def test_provider_reads_through_constants_and_literals(self):
        r = self.reads()
        self.assertIn(("APP_URL", 8), r)
        self.assertIn(("LIT_KEY", 11), r)

    def test_calls_to_a_wrapper_read_the_key_they_pass(self):
        r = self.reads()
        self.assertIn(("APP_SCHEMA", 14), r)
        self.assertIn(("APP_ENV_KEY", 20), r)

    def test_wrapper_of_a_wrapper(self):
        self.assertIn(("APP_DEEP_KEY", 20), self.reads())

    def test_maps_and_unrelated_receivers_are_not_config(self):
        self.assertFalse([k for k, _ in self.reads() if k == "NOT_A_CONFIG_KEY"])

    def test_query_config_lists_the_read_sites(self):
        from cdp.query import lookup
        out = lookup.q_config(_store(self.p), "APP_URL", exact=True)
        self.assertEqual(1, len(out["keys"]))
        self.assertTrue(any("Conn.java:8" in r["at"] for r in out["keys"][0]["read"]))


if __name__ == "__main__":
    unittest.main()
