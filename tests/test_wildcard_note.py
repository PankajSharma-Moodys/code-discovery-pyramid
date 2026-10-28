"""`query symbol` not-found note built from `wildcard:` file signals."""

from __future__ import annotations

import unittest

from helpers import Pipeline  # noqa: F401  (puts the skill root on sys.path)
from cdp.query.suggest import wildcard_note


class WildcardNoteTest(unittest.TestCase):
    def test_note_lists_sorted_files_capped_at_three(self):
        class S:
            extraction = {"files": {"b.py": {"signals": ["wildcard:x"]}, "a.py": {"signals": ["wildcard:y"]},
                                    "c.py": {"signals": ["wildcard:z"]}, "d.py": {"signals": ["wildcard:z"]},
                                    "e.py": {"signals": ["di:x"]}}}
        self.assertEqual(wildcard_note(S), "not found; may come from a wildcard import in: a.py, b.py, c.py (+1 more)")
        S.extraction = {"files": {"e.py": {"signals": []}}}
        self.assertIsNone(wildcard_note(S))


if __name__ == "__main__":
    unittest.main()
