"""X11d2: annotations with no project anchor are emitted bare (`int`, `datetime.date`); `None` is `<none>`.
References: https://peps.python.org/pep-0484/ https://peps.python.org/pep-0604/ https://peps.python.org/pep-0526/"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cdp.lang.base import ExtractContext
from cdp.lang.python import PythonExtractor
from cdp.pytypes import PyIndex


def rows(src: str) -> dict:
    facts = PythonExtractor().extract(ExtractContext(path="m.py", lines=src.splitlines(), module="root"))
    return {d["fqn"].split(".", 1)[-1]: (d.get("ret"), d.get("ftype")) for d in facts.defines}


class BareTypes(unittest.TestCase):
    def test_returns(self):
        r = rows("import datetime\nfrom typing import Optional, List, Union\nclass B: pass\nclass C:\n"
                 "    def a(self) -> int: ...\n    async def b(self) -> str: ...\n    def c(self) -> None: ...\n"
                 "    def d(self) -> Optional[int]: ...\n    def e(self) -> int | None: ...\n"
                 "    def f(self) -> List[int]: ...\n    def g(self) -> 'datetime.date': ...\n"
                 "    def h(self) -> list[int]: ...\n    def i(self) -> Union[str, None]: ...\n"
                 "    def j(self) -> None | None: ...\n    def k(self) -> Optional[B]: ...\n"
                 "    def l(self) -> int | str: ...\n    def m(self): return\n    def n(self): return 1\n")
        want = {"a": "int", "b": "str", "c": "<none>", "d": "int", "e": "int", "f": "List", "g": "datetime.date",
                "h": "list", "i": "str", "j": "<none>", "k": "M:m|.B|()", "l": None, "m": None, "n": None}
        for k, v in want.items():
            self.assertEqual(r["C#" + k][0], v, k)

    def test_fields_and_properties(self):
        r = rows("class C:\n    a: int = 0\n    b: Optional[str] = None\n    c: float\n    d = 1\n"
                 "    @property\n    def p(self) -> bool: ...\n")
        self.assertEqual(r["C.a"][1], "int")
        self.assertEqual(r["C.b"][1], "str")
        self.assertEqual(r["C.c"][1], "float")
        self.assertIsNone(r["C.d"][1])
        self.assertEqual(r["C#p"][1], "bool")

    def test_annotation_beats_value(self):
        r = rows("from contextvars import ContextVar\ndef mk(): ...\nX: int = mk()\nclass C:\n    y: str = mk()\n")
        self.assertEqual(r["X"][1], "int")
        self.assertEqual(r["C.y"][1], "str")

    def test_bare_is_terminal(self):
        idx = PyIndex({"files": {}, "uses": [], "imports": []}, {})
        for ex in ("int", "datetime.date", "<none>", "int|()", "List|()"):
            self.assertIsNone(idx.eval(ex), ex)


if __name__ == "__main__":
    unittest.main()
