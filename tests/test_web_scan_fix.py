"""JSX text (apostrophes, quotes, backticks) must not be lexed as strings."""

import unittest

from cdp.lang.base import ExtractContext
from cdp.lang.web import WebExtractor
from cdp.lang.web_scan import scan

COMP = """class Foo extends React.Component {
  render() {
    return (
      <div>
        {ok && <p>Don't do that</p>}
      </div>
    )
  }

  second() {
    return 1
  }
}
"""


def _members(text):
    r = WebExtractor().extract(ExtractContext(path="a.jsx", lines=text.split("\n"), module="m"))
    return [d["fqn"] for d in r.defines]


class JsxTextTest(unittest.TestCase):
    def test_apostrophe_keeps_later_members(self):
        self.assertEqual(_members(COMP), ["a.Foo", "a.Foo.render", "a.Foo.second"])
        self.assertTrue(scan(COMP.split("\n"))[2])

    def test_quote_and_backtick_text(self):
        for txt in ("say \"hi\"", "a `b"):
            src = COMP.replace("Don't do that", txt)
            self.assertEqual(_members(src)[-1], "a.Foo.second", txt)
            self.assertTrue(scan(src.split("\n"))[2], txt)

    def test_expression_container_stays_js(self):
        src = COMP.replace("Don't do that", "it's {`x}${y}` + '}'} ok")
        self.assertEqual(_members(src)[-1], "a.Foo.second")
        self.assertTrue(scan(src.split("\n"))[2])

    def test_plain_js_unchanged(self):
        src = ("class A {\n  m() {\n    const s = 'it}s'; const t = `a${'}'}`; const r = /}/;\n"
               "    if (a < b && c > d) { return x => y }\n  }\n  n() {}\n}\n")
        self.assertEqual(_members(src), ["a.A", "a.A.m", "a.A.n"])
        self.assertTrue(scan(src.split("\n"))[2])

    def test_ts_generics(self):
        src = ("class A {\n  m<T>(x: T): Array<T> {\n    const f = <T,>(y: T) => y\n"
               "    return [] as Array<T>\n  }\n  n() {}\n}\n")
        self.assertEqual(_members(src)[-1], "a.A.n")
        self.assertTrue(scan(src.split("\n"))[2])

    def test_closers_and_fragments(self):
        src = ("class A {\n  m() {\n    return <><b>Don't</b><i/>\n      <C a=\"x'\" b={'}'}>it's</C></>\n"
               "  }\n  n() {}\n}\n")
        self.assertEqual(_members(src)[-1], "a.A.n")
        self.assertTrue(scan(src.split("\n"))[2])


if __name__ == "__main__":
    unittest.main()
