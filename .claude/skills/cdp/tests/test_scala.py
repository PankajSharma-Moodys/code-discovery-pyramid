"""F2 -- the Scala extractor. New code with real risk (no prior extractor
for this language), so it gets direct tests rather than relying solely on
the real-target exercise recorded in PHASE/TARGET.md."""

from __future__ import annotations

import unittest

from helpers import SKILL_ROOT  # noqa: F401  (sets sys.path)

from cdp.lang.base import ExtractContext
from cdp.lang.scala import ScalaExtractor


def extract(src: str, path: str = "sdk/DataCatalogService.scala"):
    ctx = ExtractContext(path=path, lines=src.splitlines(), module="root")
    return ScalaExtractor().extract(ctx)


class PackageAndImportsTest(unittest.TestCase):
    def test_flat_package(self) -> None:
        facts = extract("package com.rms.unifiedstore.sdk\n\nclass Foo\n")
        self.assertEqual(facts.package, "com.rms.unifiedstore.sdk")

    def test_single_and_wildcard_imports(self) -> None:
        facts = extract(
            "package p\n\n"
            "import com.fasterxml.jackson.databind.ObjectMapper\n"
            "import scala.collection.mutable._\n"
        )
        self.assertEqual(
            [i["fqn"] for i in facts.imports],
            ["com.fasterxml.jackson.databind.ObjectMapper", "scala.collection.mutable"],
        )

    def test_multi_import_expands_each_member(self) -> None:
        facts = extract(
            "package p\n\n"
            "import com.rms.unifiedstore.sdk.model.{ArtifactDetails, PortfolioDetails}\n"
        )
        self.assertEqual(
            [i["fqn"] for i in facts.imports],
            ["com.rms.unifiedstore.sdk.model.ArtifactDetails",
             "com.rms.unifiedstore.sdk.model.PortfolioDetails"],
        )


class DeclarationsTest(unittest.TestCase):
    def test_bodyless_case_class_does_not_swallow_the_next_declaration(self) -> None:
        """The real, common shape in this corpus: a multi-line `case class`
        with no trailing `{` at all, immediately followed by another
        declaration."""
        src = (
            "package p\n\n"
            "case class CatalogDetails(\n"
            "  id: String,\n"
            "  name: String\n"
            ")\n\n"
            "class DataCatalogService(config: String) {\n"
            "  def foo(): Unit = {}\n"
            "}\n"
        )
        facts = extract(src)
        fqns = [d["fqn"] for d in facts.defines]
        self.assertIn("p.CatalogDetails", fqns)
        self.assertIn("p.DataCatalogService", fqns)

    def test_same_line_brace_class(self) -> None:
        src = "package p\n\nclass Foo extends Bar {\n  val x = 1\n}\n"
        facts = extract(src)
        self.assertIn("p.Foo", [d["fqn"] for d in facts.defines])

    def test_object_declaration(self) -> None:
        facts = extract("package p\n\nobject ScalaRetryUtil {\n  def retry(): Unit = {}\n}\n")
        self.assertIn("p.ScalaRetryUtil", [d["fqn"] for d in facts.defines])


if __name__ == "__main__":
    unittest.main()
