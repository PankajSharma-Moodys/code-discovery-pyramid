"""Scala declarations through the tool layer (cdp.ts, scala.scm): same rows as the hand extractor, plus the
class-parameter fields the hand parser loses; a file with a parse error keeps the hand rows."""

from __future__ import annotations

import os
import unittest
from unittest import mock

from cdp.lang.base import ExtractContext
from cdp.lang.scala import ScalaExtractor

SRC = """package com.x

import a.b.C

@Path("/x")
class Foo[T](val a: Int, b: String = "s")(implicit c: Ctx) extends Bar with Baz[T] {
  @GET @Path("{id}")
  def get[U](id: String, f: Int => String): Option[U] = None

  def long(x: Int) =
    x

  /** trailing doc */
  def next: Unit = ()
  protected[x] val y: T = ???
}
case class CC(a: Int, private val z: Long)
"""
WEIRD = """package p
case class N(
    @BeanProperty @(Schema @field)(description = "d")
    server: String,
    @BeanProperty @(Schema @field)(description = "p")
    path: String
)
"""


def rows(src, mode):
    with mock.patch.dict(os.environ, {"CDP_TS": mode}):
        f = ScalaExtractor().extract(ExtractContext(path="a/F.scala", lines=src.splitlines(), module=""))
    return {(r["fqn"], r["kind"]): r for r in f.defines if not (r.get("object") and r.get("companion"))}


class ScalaTs(unittest.TestCase):
    def test_parity_with_hand(self):
        new = rows(SRC, "scala")
        for r in new.values():
            if r["kind"] in ("class", "interface", "enum"):
                self.assertGreaterEqual(r.pop("end_line"), r["anchor"]["line"])   # S3: only the tool rows span types
        self.assertEqual(rows(SRC, "off"), new)

    def test_companion_object_has_own_row(self):
        src = "package p\nclass A\n@Ann\nobject A {\n  val k = 1\n}\n"
        with mock.patch.dict(os.environ, {"CDP_TS": "scala"}):
            f = ScalaExtractor().extract(ExtractContext(path="p/A.scala", lines=src.splitlines(), module=""))
        objs = [r for r in f.defines if r["fqn"] == "p.A" and r.get("object")]
        self.assertEqual([(r["anchor"]["line"], r["end_line"]) for r in objs], [(4, 6)])

    def test_extent_excludes_blank_and_doc(self):
        r = rows(SRC, "scala")
        self.assertEqual(r[("com.x.Foo#long", "method")]["end_line"], 11)

    def test_class_params_hand_loses(self):
        self.assertNotIn(("p.N.path", "field"), rows(WEIRD, "off"))
        r = rows(WEIRD, "scala")
        self.assertEqual(r[("p.N.path", "field")]["ftype"], "String")
        self.assertEqual(r[("p.N.path", "field")]["visibility"], "public")

    def test_parse_error_keeps_hand(self):
        bad = SRC + "\nobject Z { def f( = }\n"
        self.assertEqual(rows(bad, "off"), rows(bad, "scala"))


if __name__ == "__main__":
    unittest.main()
