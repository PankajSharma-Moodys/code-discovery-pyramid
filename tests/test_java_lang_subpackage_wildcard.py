"""`import java.lang.annotation.*` (any `java.lang.*` subpackage) is a wildcard owner like another, not
`java.lang` itself: it must not make an implicit `java.lang.X` name ambiguous (JLS 7.3, 7.5.2).
A real on-demand owner of the same name still does (cdp/jtypes.py `SigScope`)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from helpers import Pipeline
from test_overload_sigs import _repo

FILES = {
    "p/Ann.java": ("package p;\nimport java.lang.annotation.*;\n"
                   "public @interface Ann {\n  Class<?>[] groups() default {};\n}\n"),
    "p/Refl.java": ("package p;\nimport java.lang.reflect.*;\nimport java.lang.invoke.*;\n"
                    "class Refl {\n  Class<?> type;\n  Exception fail(Class<?> c, Method m) { return null; }\n}\n"),
    "p/Two.java": ("package p;\nimport java.lang.annotation.*;\nimport owner.*;\n"
                   "class Two {\n  Class<?> both;\n}\n"),
    "q/Class.java": "package q;\npublic class Class {}\n",
    "q/Same.java": "package q;\nimport java.lang.annotation.*;\nclass Same {\n  Class own;\n}\n",
    "owner/Class.java": "package owner;\npublic class Class {}\n",
}


class JavaLangSubpackageWildcardTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        cls.p = Pipeline(_repo(Path(cls.tmp.name), FILES))

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def sym(self, fqn):
        return self.p.xref["symbols"][fqn]

    def test_annotation_element_return(self):
        self.assertEqual(self.sym("p.Ann#groups")["ret"], "java.lang.Class<?>[]")

    def test_field_and_params(self):
        self.assertEqual(self.sym("p.Refl.type")["ftype"], "java.lang.Class<?>")
        self.assertEqual(self.sym("p.Refl#fail")["ret"], "java.lang.Exception")
        self.assertEqual(self.sym("p.Refl#fail")["sites"][0]["params"][0]["type"], "java.lang.Class<?>")

    def test_real_second_owner_stays_ambiguous(self):
        self.assertEqual(self.sym("p.Two.both")["ftype"], "p.Class<?>")

    def test_same_package_class_shadows(self):
        self.assertEqual(self.sym("q.Same.own")["ftype"], "q.Class")


if __name__ == "__main__":
    unittest.main()
