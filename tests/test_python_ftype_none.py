"""X11d1: `x: T = None` keeps T as the field type (PEP 526 annotations, PEP 604 unions).
References: https://peps.python.org/pep-0526/ https://peps.python.org/pep-0604/
https://docs.python.org/3/library/dataclasses.html"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cdp.lang.base import ExtractContext
from cdp.lang.python import PythonExtractor

B = "M:m|.B|()"


def ft(src: str) -> dict:
    facts = PythonExtractor().extract(ExtractContext(path="m.py", lines=src.splitlines(), module="root"))
    return {d["fqn"].split(".", 1)[-1]: d.get("ftype") for d in facts.defines if d["kind"] in ("field", "constant")}


class FtypeNone(unittest.TestCase):
    def test_class_level_variants(self):
        f = ft("class B: pass\nclass C:\n"
               "    a: B = None\n    b: Optional[B] = None\n    c: B | None = None\n    d: None | B = None\n"
               "    e: Union[B, None] = None\n    f: 'B' = None\n    g: ClassVar[B] = None\n"
               "    h: B = field(default=None)\n    i: B | None = Field(None)\n    j: B\n")
        for k in "abcdefghij":
            self.assertEqual(f["C." + k], B, k)

    def test_dataclass_namedtuple_typeddict(self):
        f = ft("from dataclasses import dataclass, field\nclass B: pass\n@dataclass\nclass D:\n    x: Optional[B] = None\n"
               "class N(NamedTuple):\n    y: B | None = None\n")
        self.assertEqual(f["D.x"], B)
        self.assertEqual(f["N.y"], B)

    def test_instance_and_module(self):
        f = ft("class B: pass\nclass C:\n    def __init__(self):\n        self.x: Optional[B] = None\n"
               "        self.y = None\nDEFAULT: Final[B] = None\n")
        self.assertEqual(f["C.x"], B)
        self.assertIsNone(f["C.y"])
        self.assertEqual(f["DEFAULT"], B)

    def test_unannotated_none_is_ignored(self):
        f = ft("class B: pass\nclass C:\n    a = None\n    def __init__(self):\n        self.a = B()\n")
        self.assertEqual(f["C.a"], B)

    def test_conflicts_stay_unknown(self):
        f = ft("class B: pass\nclass E: pass\nclass C:\n    a: B = None\n    def __init__(self):\n        self.a: E = None\n")
        self.assertIsNone(f["C.a"])

    def test_annotated_none_with_bare_type_keeps_it(self):
        f = ft("class C:\n    a: int = None\n")     # X11d2: tag-less name, never `NoneType`
        self.assertEqual(f["C.a"], "int")


if __name__ == "__main__":
    unittest.main()
