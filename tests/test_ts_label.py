"""Inventory language label for JS/TS files follows the extension (X26, H4)."""
import unittest

from cdp.lang import get_extractor, language_of


def label(path):
    return language_of(path, get_extractor(path))


class TsLabelTest(unittest.TestCase):
    def test_typescript_extensions(self):
        for p in ("a/b.ts", "a/b.tsx", "a/b.d.ts", "a/b.mts", "a/b.cts"):
            self.assertEqual(label(p), "typescript", p)

    def test_javascript_extensions(self):
        for p in ("a/b.js", "a/b.jsx", "a/b.mjs", "a/b.cjs"):
            self.assertEqual(label(p), "javascript", p)

    def test_uppercase_extension(self):
        self.assertEqual(label("a/B.TS"), "typescript")
        self.assertEqual(label("a/B.TSX"), "typescript")
        self.assertEqual(label("a/B.JS"), "javascript")

    def test_ts_mid_name(self):
        self.assertEqual(label("a/x.ts.js"), "javascript")
        self.assertEqual(label("a.ts/b.js"), "javascript")
        self.assertEqual(label("a/utils.tsconfig.js"), "javascript")

    def test_other_languages_untouched(self):
        self.assertEqual(label("a/B.java"), "java")
        self.assertEqual(label("a/b.py"), "python")

    def test_extractor_still_web(self):
        self.assertEqual(get_extractor("a/b.tsx").extensions, get_extractor("a/b.js").extensions)


if __name__ == "__main__":
    unittest.main()
