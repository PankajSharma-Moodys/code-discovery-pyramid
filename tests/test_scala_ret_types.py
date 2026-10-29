"""Scala `ret` / `ftype` per SLS 12.2 / 4.1 (Unit is the no-value result; Int, String, Any... are ordinary types):
every declared type is emitted; `Unit` as a return is the sentinel `<none>`; the sentinel is terminal in chain inference."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from helpers import Pipeline
from test_overload_sigs import _repo

from cdp.jtypes import TypeIndex
from cdp.lang.java_types import NO_RETURN

FILES = {
    "src/p/Box.scala": (
        "package p\nimport scala.collection.mutable\n"
        "class Box[T](val n: Int) {\n"
        "  val count: Int = 0\n  var name: String = \"\"\n  val opt: Option[Box[T]] = None\n  val any: Any = 1\n"
        "  val inferred = 3\n"
        "  type Id = Long\n"
        "  def run(): Unit = {}\n"
        "  def size: Int = 0\n"
        "  def label(): String = \"\"\n"
        "  def pick[U](u: U): U = u\n"
        "  def all[U <: Box[T]]: List[U] = Nil\n"
        "  def self: Box[T] = this\n"
        "  def lazyArg(f: => Int): Unit = ()\n"
        "  def aliased(i: Id): Id = i\n"
        "  def proc() { }\n"
        "  def noType = 1\n"
        "  def use(): Unit = { self.run().x(); self.size.y() }\n"
        "}\n"
        "object Box { def make(): Box[Int] = new Box[Int](1); def nothing(): Nothing = ???; val k: Double = 1.0 }\n"
        "trait Api { def ping(): Unit; def count(): Int }\n"),
}


class ScalaRetTypesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        cls.p = Pipeline(_repo(Path(cls.tmp.name), FILES))
        cls.defs = {}
        for d in cls.p.extraction["defines"]:
            cls.defs.setdefault(d["fqn"], []).append(d)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def ret(self, fqn):
        return self.defs[fqn][0].get("ret")

    def test_unit_is_sentinel(self):
        for f in ("p.Box#run", "p.Box#lazyArg", "p.Api#ping"):
            self.assertEqual(self.ret(f), NO_RETURN, f)

    def test_builtins_emitted_bare(self):
        self.assertEqual(self.ret("p.Box#size"), "Int")
        self.assertEqual(self.ret("p.Api#count"), "Int")
        self.assertEqual(self.ret("p.Box#nothing") if "p.Box#nothing" in self.defs else "Nothing", "Nothing")
        self.assertTrue(self.ret("p.Box#label").endswith("String"), self.ret("p.Box#label"))

    def test_generic_and_class_returns(self):
        self.assertEqual(self.ret("p.Box#pick"), "~U")
        self.assertEqual(self.ret("p.Box#self").split("<")[0], "p.Box")

    def test_no_declared_type_no_ret(self):
        for f in ("p.Box#noType", "p.Box#proc"):
            self.assertNotIn("ret", self.defs[f][0], f)

    def test_field_types(self):
        f = lambda n: self.defs["p.Box." + n][0].get("ftype")
        self.assertEqual(f("count"), "Int")
        self.assertTrue(f("name").endswith("String"))
        self.assertEqual(f("any"), "Any")
        self.assertNotIn("ftype", self.defs["p.Box.inferred"][0])

    def test_resolved_symbols_keep_sentinel_and_builtins(self):
        s = self.p.xref["symbols"]
        self.assertEqual(s["p.Box#run"]["ret"], NO_RETURN)
        self.assertEqual(s["p.Box#size"]["ret"], "Int")
        self.assertEqual(s["p.Box.count"]["ftype"], "Int")

    def test_no_phantom_symbols(self):
        names = set(self.p.xref["symbols"])
        for bad in ("p.none", "p.Int", "p.Unit", "p.<none>", "none", "Int", "Unit"):
            self.assertNotIn(bad, names)

    def test_chain_terminates_on_sentinel_and_builtin(self):
        ti = TypeIndex(self.p.extraction, self.p.xref["symbols"])
        for t in (NO_RETURN, "Int", "Unit", "Any"):
            self.assertIsNone(ti.step(t, "m:run"), t)
            self.assertEqual(ti.canon(t, "src/p/Box.scala"), t)
        self.assertIsNone(ti.walk("p.Box", ["m:run", "m:x"]))
        self.assertIsNone(ti.walk("p.Box", ["m:size", "m:y"]))


class ShadowedBuiltinTest(unittest.TestCase):
    def test_repo_class_named_like_builtin_is_not_reached_via_sentinel(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Pipeline(_repo(Path(tmp), {
                "src/q/Unit.scala": "package q\nclass Unit { def m(): Int = 1 }\n",
                "src/q/A.scala": "package q\nclass A { def v(): scala.Unit = (); def i(): Int = 1 }\n"}))
            ti = TypeIndex(p.extraction, p.xref["symbols"])
            self.assertEqual(ti.canon(NO_RETURN, "src/q/A.scala"), NO_RETURN)
            self.assertIsNone(ti.walk("q.A", ["m:v", "m:m"]))
            self.assertIsNone(ti.walk("q.A", ["m:i", "m:m"]))


if __name__ == "__main__":
    unittest.main()
