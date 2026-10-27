"""A Java base type naming an implicit `java.lang` type settles to `java.lang.X` unless the JLS
shadows it: a single-type import, a same-package class, or a nested type of the file wins; a second
on-demand owner makes it ambiguous (cdp/jtypes.py `SigScope`, JLS 7.3 / 7.5.2 / 6.4.1)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from helpers import Pipeline
from test_overload_sigs import _repo

FILES = {
    "a/Plain.java": (
        "package a;\npublic class Plain {}\nclass Err extends RuntimeException {}\n"
        "class Res implements AutoCloseable, Comparable<Plain> { public void close() {} }\n"
        "class Run implements Runnable {}\nclass Obj extends Object {}\n"
        "class Gen extends Thread implements Comparable<Run> {}\n"
        "class Ann implements java.io.Serializable, Iterable<Exception> {}\n"),
    "a/Exception.java": "package a;\npublic class Exception {}\n",
    "a/Shadowed.java": "package a;\nclass Shadowed extends Exception {}\n",
    "b/Imp.java": (
        "package b;\nimport lib.Runnable;\nclass Imp implements Runnable {}\n"),
    "b/Nested.java": (
        "package b;\nclass Nested {\n  static class Error {}\n  static class Sub extends Error {}\n"
        "  static class Inner extends Outer.Deep {}\n  static class Outer { static class Deep {} }\n}\n"),
    "c/Wild.java": (
        "package c;\nimport java.lang.*;\nimport lib.*;\nclass Wild extends RuntimeException implements Marker {}\n"),
    "c/Two.java": "package c;\nimport owner.*;\nclass Two extends Throwable {}\n",
    "c/Both.java": "package c;\nimport lib.*;\nimport owner.*;\nclass Both extends Taken {}\n",
    "c/Absent.java": "package c;\nimport lib.*;\nclass Absent extends Unknown implements Record {}\n",
    "lib/Marker.java": "package lib;\npublic interface Marker {}\n",
    "owner/Throwable.java": "package owner;\npublic class Throwable {}\n",
    "lib/Taken.java": "package lib;\npublic class Taken {}\n",
    "owner/Taken.java": "package owner;\npublic class Taken {}\n",
}


class JavaLangSupertypeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        cls.p = Pipeline(_repo(Path(cls.tmp.name), FILES))

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def sup(self, fqn):
        return [s for site in self.p.xref["symbols"][fqn]["sites"] for s in site.get("supertypes", ())]

    def test_implicit_java_lang(self):
        self.assertEqual(self.sup("a.Err"), ["java.lang.RuntimeException"])
        self.assertEqual(self.sup("a.Run"), ["java.lang.Runnable"])
        self.assertEqual(self.sup("a.Obj"), ["Object"])   # JAVA_BUILTINS names are never qualified by the extractor

    def test_generic_supertypes(self):
        self.assertEqual(self.sup("a.Res"), ["java.lang.AutoCloseable", "java.lang.Comparable<a.Plain>"])
        self.assertEqual(self.sup("a.Gen"), ["java.lang.Thread", "java.lang.Comparable<a.Run>"])
        self.assertEqual(self.sup("a.Ann")[0], "java.io.Serializable")
        self.assertEqual(self.sup("a.Ann")[1], "java.lang.Iterable<a.Exception>")   # same-package Exception shadows

    def test_same_package_class_shadows(self):
        self.assertEqual(self.sup("a.Shadowed"), ["a.Exception"])

    def test_single_type_import_shadows(self):
        self.assertEqual(self.sup("b.Imp"), ["lib.Runnable"])

    def test_nested_types(self):
        self.assertEqual(self.sup("b.Nested.Sub"), ["b.Nested.Error"])
        self.assertEqual(self.sup("b.Nested.Inner"), ["b.Nested.Outer.Deep"])

    def test_explicit_java_lang_wildcard_is_not_a_second_owner(self):
        self.assertEqual(self.sup("c.Wild"), ["java.lang.RuntimeException", "lib.Marker"])

    def test_wildcard_and_java_lang_both_own_the_name(self):
        self.assertEqual(self.sup("c.Two"), ["c.Throwable"])      # ambiguous (javac rejects it): kept as guessed

    def test_two_wildcards_stay_guessed(self):
        self.assertEqual(self.sup("c.Both"), ["c.Taken"])

    def test_names_not_in_java_lang_become_bare(self):
        self.assertEqual(self.sup("c.Absent"), ["Unknown", "Record"])   # Record: Java 16+, not in the Java 8 set


if __name__ == "__main__":
    unittest.main()
