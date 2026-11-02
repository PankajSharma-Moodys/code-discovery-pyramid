"""U1: `used_by` of a JS/TS/Vue symbol, one test per import form (default, named, alias, namespace,
re-export, dynamic import, same-file call, spec file, .vue script and template)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from helpers import Pipeline
from test_java_resolution import inline_repo

FILES = {
    "package.json": '{"name": "fx"}',
    "src/util/jp.ts":
        "export function findPath(o: any, d: number): any {\n  return d ? findPath(o, d - 1) : o\n}\n"
        "export function nameA(x: string) { return x }\nexport function nameB(x: string) { return x }\n"
        "export function nsFn(x: string) { return x }\nexport function aliased(x: string) { return x }\n"
        "export function neverUsed() { return 1 }\nexport const arrow = (x: number) => x + 1\n"
        "export function typed(x: number) { return x }\nexport function viaTpl(x: number) { return x }\n"
        "export function viaMap(x: number) { return x }\n",
    "src/util/index.ts": "export { nameB } from \"./jp\"\n",
    "src/pages/Page.js": "class Page { render() { return null } }\nexport default Page\n",
    "src/pages/Wrapped.js": "class Inner { render() { return null } }\nexport default hoc(Inner)\n",
    "src/a_named.ts": "import { nameA } from \"./util/jp\"\nexport function useIt() { return nameA(\"x\") }\n",
    "src/b_alias.ts":
        "import { findPath as fp, aliased } from \"@/util/jp\"\nexport function useIt2() { return fp({}, 1) + aliased(\"y\") }\n",
    "src/c_ns.ts": "import * as jp from \"./util/jp\"\nexport function useIt3() { return jp.nsFn(\"z\") }\n",
    "src/d_reexport.ts": "import { nameB } from \"./util\"\nexport function useIt4() { return nameB(\"q\") }\n",
    "src/e_default.js":
        "import Page from './pages/Page'\nimport W from './pages/Wrapped'\n"
        "export const r = () => <Page x={1} />\nexport const w = () => <W />\n",
    "src/tests/jp.spec.ts": "import { nameA } from \"@/util/jp\"\ndescribe(\"a\", () => { it(\"b\", () => { nameA(\"1\") }) })\n",
    "src/comp/C.vue":
        "<template><div @click=\"viaTpl(1)\">{{ viaMap(2) }}</div></template>\n<script setup lang=\"ts\">\n"
        "import { nameA, viaTpl, viaMap } from \"@/util/jp\"\nconst v = nameA(\"v\")\n</script>\n<p hint=\"viaTpl is plain text\"/>\n",
    "src/f_dyn.ts": "export async function lazy() { const m = await import(\"./util/jp\"); return m.typed(1) }\n",
    "src/h_text.ts":
        "import { nameA } from './util/jp'\nexport const t = /nameA/.test('nameA') && 'nameA(1)'\n",
    "src/g_ref.ts": "import { arrow } from './util/jp'\nexport const xs = [1].map(arrow)\n",
}


class WebImportUsesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.p = Pipeline(inline_repo(Path(cls.tmp.name), FILES))
        cls.used = cls.p.xref["used_by"]

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def files(self, key):
        return sorted({(u["file"], u["anchor"]["line"]) for u in self.used.get(key, [])})

    def test_named_import_call(self):
        self.assertIn(("src/a_named.ts", 2), self.files("src/util/jp#nameA"))

    def test_alias_import_and_renamed_binding(self):
        self.assertEqual([("src/b_alias.ts", 2)], self.files("src/util/jp#aliased"))
        self.assertIn(("src/b_alias.ts", 2), self.files("src/util/jp#findPath"))

    def test_same_file_recursion(self):
        self.assertIn(("src/util/jp.ts", 2), self.files("src/util/jp#findPath"))

    def test_namespace_import(self):
        self.assertEqual([("src/c_ns.ts", 2)], self.files("src/util/jp#nsFn"))

    def test_reexport_through_index(self):
        self.assertIn(("src/d_reexport.ts", 2), self.files("src/util/jp#nameB"))

    def test_default_import_jsx(self):
        self.assertEqual([("src/e_default.js", 3)], self.files("src/pages/Page.Page"))

    def test_default_import_of_wrapped_class(self):
        self.assertEqual([("src/e_default.js", 4)], self.files("src/pages/Wrapped.Inner"))

    def test_spec_file_use_is_resolved(self):
        self.assertIn(("src/tests/jp.spec.ts", 2), self.files("src/util/jp#nameA"))

    def test_vue_script_and_template(self):
        self.assertIn(("src/comp/C.vue", 4), self.files("src/util/jp#nameA"))
        self.assertEqual([("src/comp/C.vue", 1)], self.files("src/util/jp#viaTpl"))
        self.assertEqual([("src/comp/C.vue", 1)], self.files("src/util/jp#viaMap"))

    def test_dynamic_import(self):
        self.assertEqual([("src/f_dyn.ts", 1)], self.files("src/util/jp#typed"))

    def test_function_passed_as_value(self):
        self.assertIn(("src/g_ref.ts", 2), self.files("src/util/jp#arrow"))

    def test_unused_symbol_stays_unused(self):
        self.assertEqual([], self.files("src/util/jp#neverUsed"))

    def test_name_in_string_or_regex_is_not_a_use(self):
        self.assertNotIn("src/h_text.ts", {f for f, _ in self.files("src/util/jp#nameA")})

    def test_import_line_itself_is_not_a_use(self):
        self.assertNotIn(("src/a_named.ts", 1), self.files("src/util/jp#nameA"))


if __name__ == "__main__":
    unittest.main()
