"""Coverage wording must not contradict itself; docs query examples come from the repo's own data."""
import unittest

from cdp import docs
import importlib
render = importlib.import_module("cdp.query.render")


class CoverageWording(unittest.TestCase):
    def _cov(self):
        return {"query": "coverage", "coverage": {"files_complete": 0, "files_total": 8, "fraction": 0.0,
                                                 "incomplete_nodes": ["root/shop"]},
                "warning": "", "nodes": {"root/shop": "complete"}, "skipped": []}

    def test_no_incomplete_complete_line(self):
        out = render.render(self._cov())
        self.assertNotIn("incomplete: root/shop (complete)", out)
        self.assertIn("not model-reviewed: root/shop", out)


class DocsExamples(unittest.TestCase):
    def test_examples_from_data(self):
        xref = {"used_by": {"com.x.Order": ["a", "b"], "table:t": ["a"]}}
        sym, tbl = docs._example_names(xref, {"io_edges": [{"target": "table:orders"}]})
        self.assertEqual((sym, tbl), ("com.x.Order", "orders"))

    def test_placeholders_when_empty(self):
        self.assertEqual(docs._example_names({"used_by": {}}, {}), ("<symbol>", "<table>"))


if __name__ == "__main__":
    unittest.main()
