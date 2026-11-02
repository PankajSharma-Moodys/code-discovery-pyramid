"""Java declarations through the tree-sitter layer (cdp.ts) and the hand fallback agree.
JLS 9.5: a member class or interface in the body of an interface (or annotation) is implicitly public and static."""
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cdp.lang.base import ExtractContext
from cdp.lang.java import JavaExtractor

SRC = """package p;
import java.util.List;
public interface Api {
  class Inner {}
  interface Cb {}
  enum Mode { A }
  @interface Marker {}
  public static class Pub {}
  List<String> names();
}
@interface Ann { class N {} }
class Outer { class Plain {} }
"""


def defs(mode):
    old = os.environ.get("CDP_TS")
    os.environ["CDP_TS"] = mode
    try:
        f = JavaExtractor().extract(ExtractContext(path="p/Api.java", lines=SRC.splitlines(), module=""))
    finally:
        os.environ.pop("CDP_TS") if old is None else os.environ.__setitem__("CDP_TS", old)
    return {d["fqn"]: d["visibility"] for d in f.defines}


class JavaTsLayer(unittest.TestCase):
    def test_interface_member_types_public(self):
        for mode in ("off", "java"):
            v = defs(mode)
            for n in ("Inner", "Cb", "Mode", "Marker", "Pub"):
                self.assertEqual(v["p.Api." + n], "public", (mode, n))
            self.assertEqual(v["p.Ann.N"], "public", mode)
            self.assertEqual(v["p.Outer.Plain"], "package", mode)

    def test_paths_agree(self):
        self.assertEqual(defs("off"), defs("java"))


if __name__ == "__main__":
    unittest.main()
