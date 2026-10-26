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

class _Ctx:
    def lang(self, rel):
        return "python"


def routes(src):
    """{framework: [decorator lines]} for the Python F1 rows (Flask/FastAPI) on an inline snippet."""
    scan = sc.Scan("python", ".py", src.strip("\n").split("\n"))
    out = {}
    for (fid, fw, _k), site in sc.framework_sites(_Ctx(), "app.py", scan).items():
        if fid == "F1":
            out.setdefault(fw, []).append(min(site["lines"]))
    return out


FLASK_IMP = "from flask import Flask, Blueprint\napp = Flask(__name__)\nbp = Blueprint('b', __name__)\n"
CASES += [
    ("flask route with methods list",
     None, FLASK_IMP + "@app.route('/a', methods=['POST', 'PUT'])\ndef a():\n    pass", {"Flask": [4]}),
    ("flask route default GET",
     None, FLASK_IMP + "@app.route(\"/b\")\ndef b():\n    pass", {"Flask": [4]}),
    ("flask blueprint route",
     None, FLASK_IMP + "@bp.route('/c')\ndef c():\n    pass", {"Flask": [4]}),
    ("flask 2 shortcut",
     None, FLASK_IMP + "@bp.post('/d')\ndef d():\n    pass\n@app.get('/e')\ndef e():\n    pass", {"Flask": [4, 7]}),
    ("fastapi route is not flask",
     None, "from fastapi import APIRouter\nrouter = APIRouter()\n@router.get('/f')\ndef f():\n    pass", {"FastAPI": [3]}),
    ("flask file without routes",
     None, FLASK_IMP + "def g():\n    return app.config.get('X')", {}),
]

fails = 0
for case in CASES:
    if case[1] is None:
        name, _, src, want = case
        got = routes(src)
    else:
        name, src, want = case
        got = present(src)
    ok = got == want
    fails += not ok
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else f"  got={got} want={want}"))
print(f"{len(CASES) - fails}/{len(CASES)} passed")
sys.exit(1 if fails else 0)
