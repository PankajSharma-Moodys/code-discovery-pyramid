"""X24: an annotation written with empty parentheses (`@A()`) emits `args: {}`; one written
without (`@A`) emits no `args` key. Python decorators never parse arguments, so neither form gets one."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from helpers import Pipeline

from cdp.query.lookup import q_file
from cdp.query.render import render

JAVA = """public class J {
    @A void a() {}
    @A() void b() {}
    @A(1) void c() {}
    @A(k = 1) void d() {}
}
"""

SCALA = """class S {
  @A def a = 1
  @A() def b = 1
  @A(1) def c = 1
  @A(k = 1) def d = 1
}
class T @A() (x: Int)
"""

PY = "@A\ndef a(): pass\n@A()\ndef b(): pass\n"


class _Store:
    def __init__(self, p: Pipeline) -> None:
        self.extraction, self.xref, self.inventory = p.extraction, p.xref, p.inventory
        self.dataflow = p.dataflow
        self.state = {"claims": [], "unknowns": [], "provenance": {}}

    def node_of(self, path):
        return "root"


class EmptyParenAnnotationsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        root = Path(cls.tmp.name) / "emptyparens"
        for rel, body in (("src/main/java/J.java", JAVA), ("src/main/scala/S.scala", SCALA),
                          ("p/a.py", PY)):
            path = root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(body)
        (root / "build.gradle").write_text("apply plugin: 'java'\n")
        cls.pipe = Pipeline(root)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def args_by_text(self, suffix):
        out = {}
        for d in self.pipe.extraction["defines"]:
            if not str(d["anchor"].get("file", "")).endswith(suffix):
                continue
            for a in d.get("annotations") or ():
                out.setdefault(a["text"], a.get("args", "<none>"))
        return out

    def test_java(self):
        got = self.args_by_text(".java")
        self.assertEqual(got["@A"], "<none>")
        self.assertEqual(got["@A()"], {})
        self.assertEqual(got["@A(1)"], {"value": 1})
        self.assertEqual(got["@A(k=1)"], {"k": 1})

    def test_scala(self):
        got = self.args_by_text(".scala")
        self.assertEqual(got["@A"], "<none>")
        self.assertEqual(got["@A()"], {})   # method and constructor-parameter-list forms
        self.assertEqual(got["@A(1)"], {"value": 1})

    def test_scala_constructor_annotation_is_empty_args(self):
        (t,) = [d for d in self.pipe.extraction["defines"] if d["fqn"] == "T#<init>"]
        self.assertEqual([a.get("args") for a in t["annotations"]], [{}])

    def test_python_decorators_unchanged(self):
        got = self.args_by_text(".py")
        self.assertEqual(got["@A"], "<none>")
        self.assertEqual(got["@A()"], "<none>")

    def test_query_file_renders_an_empty_args_object(self):
        store = _Store(self.pipe)
        for fmt in ("compact", "detail"):
            ans = q_file(store, "J.java")
            text = json.dumps(ans, default=str)
            self.assertIn("@A()", text)
            self.assertIsInstance(render(ans), str)


if __name__ == "__main__":
    unittest.main()
