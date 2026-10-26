"""X5: Python decorators become `annotations` on defines (EXTRACTION_METRICS M1).
Reference: https://docs.python.org/3/reference/compound_stmts.html#function-definitions"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cdp.lang.base import ExtractContext
from cdp.lang.python import PythonExtractor


def defs(src: str) -> dict:
    facts = PythonExtractor().extract(ExtractContext(path="m.py", lines=src.splitlines(), module="root"))
    return {d["fqn"].split("#")[-1].split(".")[-1]: d for d in facts.defines}


class PythonAnnotations(unittest.TestCase):
    def test_forms(self):
        d = defs("@bare\n@a.b.c\n@call(1, x=2)\n@a.b(\n    3,\n)\ndef f(): pass\n")
        anns = d["f"]["annotations"]
        self.assertEqual([a["name"] for a in anns], ["bare", "a.b.c", "call", "a.b"])
        self.assertEqual([a["line"] for a in anns], [1, 2, 3, 4])
        self.assertEqual([a["end_line"] for a in anns], [1, 2, 3, 6])
        self.assertEqual(anns[2]["text"], "@call(1, x=2)")
        self.assertEqual(anns[3]["text"], "@a.b( 3, )")

    def test_class_method_async(self):
        d = defs("@dc\nclass C:\n    @property\n    def p(self): pass\n    @app.get('/x')\n    async def h(self): pass\n")
        self.assertEqual(d["C"]["annotations"][0]["name"], "dc")
        self.assertEqual(d["p"]["annotations"][0]["name"], "property")
        self.assertEqual(d["h"]["annotations"][0]["name"], "app.get")
        self.assertEqual(d["h"]["annotations"][0]["line"], 5)

    def test_arbitrary_expression_pep614(self):
        d = defs("@buttons[0].clicked.connect\ndef f(): pass\n@(lambda g: g)\ndef g(): pass\n")
        self.assertEqual(d["f"]["annotations"][0]["name"], "buttons[0].clicked.connect")
        self.assertEqual(d["g"]["annotations"][0]["text"], "@(lambda g: g)")

    def test_parenthesised_multiline_and_call(self):
        d = defs("@(\n    reg(1)\n)\ndef f(): pass\n")
        a = d["f"]["annotations"][0]
        self.assertEqual((a["line"], a["end_line"]), (1, 3))
        self.assertTrue(a["text"].startswith("@(") and a["text"].endswith(")"))

    def test_none_and_nested(self):
        d = defs("def plain(): pass\ndef outer():\n    @inner_dec\n    def inner(): pass\n")
        self.assertNotIn("annotations", d["plain"])
        self.assertEqual(d["inner"]["annotations"][0]["name"], "inner_dec")

    def test_unicode_before_decorator(self):
        d = defs("x = 'é'; y = 1\n@dec('ü')\ndef f(): pass\n")
        self.assertEqual(d["f"]["annotations"][0]["text"], "@dec('ü')")


if __name__ == "__main__":
    unittest.main()
