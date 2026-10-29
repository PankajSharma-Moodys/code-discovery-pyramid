"""Scala function types in `ret` / `ftype` (SLS 3.2.10; Scala 3 reference: context functions, dependent and
polymorphic function types): `=>` inside a type is part of the type, never a truncation point."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from helpers import Pipeline
from test_overload_sigs import _repo

from cdp.lang.scala_decl import scala_type_text

SRC = (
    "package p\nclass Foo\n"
    "class A {\n"
    "  def f: () => Int = () => 1\n"
    "  def g: Int => Int = x => x\n"
    "  def h(a: Int): (Int, String) => Boolean = (x, y) => true\n"
    "  def curried: Int => Int => String = a => b => \"\"\n"
    "  def nested: Map[String, Int => Int] = Map()\n"
    "  def paren: (Int => Int) = x => x\n"
    "  def hof: (Int => Int) => Int = f => f(1)\n"
    "  def byName(x: => Int): Int = x\n"
    "  def ctx: Int ?=> String = \"\"\n"
    "  def poly: [T] => T => T = [T] => (x: T) => x\n"
    "  def dep(a: A): (b: Int) => String = b => \"\"\n"
    "  def opt: Option[() => Unit] = None\n"
    "  def unit: Int => Unit = x => ()\n"
    "  def cls: Foo => Foo = x => x\n"
    "  def plain: Int = 1 == 1\n"
    "  val vf: Int => Int = x => x\n"
    "  var vg: (Int, Int) => Int = _ + _\n"
    "  val vc: Int ?=> Int = 1\n"
    "}\n")


class ScalaFnTypesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        p = Pipeline(_repo(Path(cls.tmp.name), {"src/p/A.scala": SRC}))
        cls.d = {x["fqn"]: x for x in p.extraction["defines"]}

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def test_returns(self):
        want = {"f": "Function0<Int>", "g": "Function1<Int,Int>", "h": "Function2<Int,String,Boolean>",
                "curried": "Function1<Int,Function1<Int,String>>", "nested": "Map<String,Function1<Int,Int>>",
                "paren": "Function1<Int,Int>", "hof": "Function1<Function1<Int,Int>,Int>",
                "byName": "Int", "ctx": "ContextFunction1<Int,String>", "poly": "PolyFunction",
                "dep": "Function1<Int,String>", "opt": "Option<Function0<Unit>>",
                "unit": "Function1<Int,Unit>", "plain": "Int"}
        for n, w in want.items():
            self.assertEqual(self.d["p.A#" + n].get("ret"), w, n)

    def test_class_params_resolve(self):
        self.assertEqual(self.d["p.A#cls"]["ret"], "Function1<p.Foo,p.Foo>")

    def test_fields(self):
        self.assertEqual(self.d["p.A.vf"]["ftype"], "Function1<Int,Int>")
        self.assertEqual(self.d["p.A.vg"]["ftype"], "Function2<Int,Int,Int>")
        self.assertEqual(self.d["p.A.vc"]["ftype"], "ContextFunction1<Int,Int>")

    def test_text(self):
        self.assertEqual(scala_type_text("=> Int"), "Int")
        self.assertEqual(scala_type_text("List[(Int,Int)=>Int]"), "List<Function2<Int,Int,Int>>")
        self.assertIn("=>>", scala_type_text("[F[_]] =>> F[Int]"))   # type lambda is not a function type
        self.assertEqual(scala_type_text("(A,B)"), "(A,B)")


if __name__ == "__main__":
    unittest.main()
