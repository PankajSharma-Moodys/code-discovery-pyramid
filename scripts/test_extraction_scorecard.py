"""Fixture checks for the scorer's C# attribute counting (M1 'present'). No corpus reads.
Run: python3 -I scripts/test_extraction_scorecard.py"""
import importlib.util
import os
import sys

here = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("extraction_scorecard", os.path.join(here, "extraction_scorecard.py"))
sc = importlib.util.module_from_spec(spec)
sys.modules["extraction_scorecard"] = sc
spec.loader.exec_module(sc)


def present(src):
    """{(kind, name): ann_count} for every C# type/member/property with attributes; plus total."""
    scan = sc.Scan("csharp", ".cs", src.strip("\n").split("\n"))
    out = {}
    for it in scan.types + scan.members + scan.props:
        if it.get("ann"):
            out[(it["cat"], it["name"])] = it["ann"]
    return out


CASES = [
    ("same-line property attributes",
     "class C {\n  [A] [B(1)] public int P { get; set; }\n  public override string ToString() { return \"\"; }\n}",
     {("field", "P"): 2}),
    ("stacked attributes above property",
     "class C {\n  [A]\n  [B]\n  public int P { get; set; }\n}",
     {("field", "P"): 2}),
    ("multi-line attribute list",
     "class C {\n  [A,\n   B]\n  public void M() { }\n}",
     {("method", "M"): 2}),
    ("method after properties",
     "class C {\n  [A] public int P { get; set; }\n  public int Q { get; set; }\n  [X]\n  public void M() { }\n}",
     {("field", "P"): 1, ("method", "M"): 1}),
    ("collection expression one line",
     "class C {\n  static readonly int[] L =\n    [ a, b ];\n  public void M() { }\n}",
     {}),
    ("collection expression multi-line with spread",
     "class C {\n  static readonly int[] L =\n  [\n    x,\n    .. y\n  ];\n  public void M() { }\n}",
     {}),
    ("plain declarations, no attributes",
     "class C {\n  public int P { get; set; }\n  public void M() { }\n}",
     {}),
    ("type attribute",
     "[Serializable]\nclass C {\n  public int f;\n}",
     {("type", "C"): 1}),
]

fails = 0
for name, src, want in CASES:
    got = present(src)
    ok = got == want
    fails += not ok
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else f"  got={got} want={want}"))
print(f"{len(CASES) - fails}/{len(CASES)} passed")
sys.exit(1 if fails else 0)
