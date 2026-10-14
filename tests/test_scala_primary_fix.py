"""Scala primary is the first top-level type; a preceding companion object's members must not win."""

import unittest

from cdp.lang.base import ExtractContext
from cdp.lang.scala import ScalaExtractor


def primary(src: str, path: str = "a/X.scala") -> str:
    return ScalaExtractor().extract(ExtractContext(path, src.split("\n"), "a")).primary


class PrimaryTest(unittest.TestCase):
    def test_object_before_class(self):
        self.assertEqual(primary("package a\nobject X {\n  val Name = \"n\"\n}\nclass X {\n}\n"), "a.X")

    def test_object_with_nested_type_before_class(self):
        self.assertEqual(primary("package a\nobject X {\n  case class P(i: Int)\n}\nclass X {\n}\n"), "a.X")

    def test_class_first(self):
        self.assertEqual(primary("package a\nclass X {\n}\nobject X {\n  val N = 1\n}\n"), "a.X")

    def test_first_toplevel_wins(self):
        self.assertEqual(primary("package a\ntrait A {\n}\nclass B {\n}\n"), "a.A")

    def test_lone_object(self):
        self.assertEqual(primary("package a\nobject O {\n  val V = 1\n}\n"), "a.O")


if __name__ == "__main__":
    unittest.main()
