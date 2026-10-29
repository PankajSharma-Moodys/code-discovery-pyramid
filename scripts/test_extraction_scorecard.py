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


def pyprops(src):
    """{name: 'prop' | 'ret=<r>' | 'noret'} for Python class-level defs."""
    scan = sc.Scan("python", ".py", src.strip("\n").split("\n"))
    return {m["name"]: ("prop" if m.get("prop") else ("ret=" + m["ret"] if m["ret"] else "noret"))
            for m in scan.members if m["cat"] == "method"}


PYP = [
    ("py @property", "class C:\n    @property\n    def x(self) -> str:\n        return ''", {"x": "prop"}),
    ("py setter/getter/deleter", "class C:\n    @x.setter\n    def x(self, v) -> None:\n        pass\n    @x.getter\n    def y(self) -> int:\n        pass\n    @x.deleter\n    def z(self) -> int:\n        pass", {"x": "prop", "y": "prop", "z": "prop"}),
    ("py cached_property forms", "class C:\n    @functools.cached_property\n    def a(self) -> int:\n        pass\n    @cached_property\n    def b(self) -> int:\n        pass", {"a": "prop", "b": "prop"}),
    ("py stacked + comment + blank between", "class C:\n    @property\n    # note\n\n    @other(1)\n    def x(self) -> str:\n        pass", {"x": "prop"}),
    ("py property without annotation", "class C:\n    @property\n    def x(self):\n        pass", {"x": "prop"}),
    ("py plain method scored", "class C:\n    def m(self) -> str:\n        pass", {"m": "ret=str"}),
    ("py classmethod/staticmethod scored", "class C:\n    @classmethod\n    def a(cls) -> int:\n        pass\n    @staticmethod\n    def b() -> int:\n        pass", {"a": "ret=int", "b": "ret=int"}),
    ("py property flag does not leak", "class C:\n    @property\n    def x(self) -> str:\n        pass\n    def m(self) -> str:\n        pass", {"x": "prop", "m": "ret=str"}),
]
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

# D4: is_bundled_asset on inline path strings (second arg = sibling paths for the `.dev.js` twin rule)
D4 = [
    ("d4 keep app file", "src/app/store.js", (), False),
    ("d4 keep app file under assets dir", "CTFd/themes/admin/assets/js/pages/challenges.js", (), False),
    ("d4 keep camelCase name under static dir", "static/js/userController.js", (), False),
    ("d4 keep config file", "vite.config.js", (), False),
    ("d4 exclude .min.js", "static/js/core.min.js", (), True),
    ("d4 exclude .min.mjs", "lib/x.min.mjs", (), True),
    ("d4 exclude bundle word", "static/js/vendor.bundle.dev.js", (), True),
    ("d4 exclude x-bundle-core", "res/swagger-ui-es-bundle-core.js", (), True),
    ("d4 exclude hex hash under static", "themes/core/static/assets/index.0eace8c9.js", (), True),
    ("d4 exclude base64 hash under assets", "themes/admin/static/assets/pages/main-OdxfRQdf.js", (), True),
    ("d4 hash name outside asset dirs is kept", "src/index.0eace8c9.js", (), False),
    ("d4 dev twin of min is excluded", "static/js/helpers.dev.js", ("static/js/helpers.min.js",), True),
    ("d4 dev file without min twin is kept", "static/js/helpers.dev.js", (), False),
    # decision: a bare `vendor.js` has no minified/bundle/hash signal in its name, so it stays scored (a `vendor/`
    # directory alone is not enough: vendored-but-readable code cannot be told from the project's own by name)
    ("d4 file named vendor.js is kept", "static/js/vendor.js", (), False),
    ("d4 ts file never excluded", "static/assets/main-OdxfRQdf.ts", (), False),
]
CASES += [(n, "d4", (p_, sib), want) for n, p_, sib, want in D4]

def f2_js(src):
    """Marker lines of the JS F2 row (axios/fetch) on an inline snippet, over blanked source."""
    class C:
        def lang(self, rel):
            return "javascript"
    scan = sc.Scan("javascript", ".js", src.strip("\n").split("\n"))
    return sorted(ln for (fid, fw, _k), site in sc.framework_sites(C(), "a.js", scan).items()
                  if fid == "F2" and fw == "axios/fetch" for ln in site["lines"])


for _n, _src, _want in [
    ("d5 bare fetch counts", "fetch('/a')", [1]),
    ("d5 window.fetch counts", "window.fetch('/a')", [1]),
    ("d5 globalThis.fetch counts", "globalThis.fetch('/a')", [1]),
    ("d5 self.fetch counts", "self.fetch('/a')", [1]),
    ("d5 CTFd.fetch does not count", "CTFd.fetch('/a')", []),
    ("d5 this.fetch does not count", "this.fetch('/a')", []),
    ("d5 other.window.fetch does not count", "foo.window.fetch('/a')", []),
    ("d5 axios.get still counts", "axios.get('/a')", [1]),
    ("d5 fetch in a comment does not count", "// fetch('/a')\nx = 1", []),
    ("d5 fetch in a string does not count", "x = \"fetch('/a')\"", []),
    ("d5 prefixed name does not count", "prefetch('/a')", []),
]:
    CASES.append((_n, "d5", _src, _want))

def g1(src):
    """[(name, np)] of C# methods/ctors the scorer counts as G1-present."""
    scan = sc.Scan("csharp", ".cs", src.strip("\n").split("\n"))
    return [(m["name"], m["np"]) for m in scan.members if m["cat"] == "method"]


for _n, _src, _want in [
    ("g1 tuple return type is not a method named static",
     "class C {\n  private static (string A, string B) M(string x) { return default; }\n}", [("M", 1)]),
    ("g1 tuple-typed field is not a method",
     "class C {\n  private static readonly (string P, string[] K)[] s_k =\n  { };\n}", []),
    ("g1 verbatim string spanning lines is blanked",
     "class C {\n  const string Q = @\"\n    SELECT MAX(x) AS y FROM t\n  \";\n  void M(int a) { }\n}", [("M", 1)]),
    ("g1 constructor with 15 one-per-line parameters",
     "class C {\n  public C(" + ",\n".join("int p%d" % k for k in range(15)) + ")\n  { }\n}", [("C", 15)]),
]:
    CASES.append((_n, "g1", _src, _want))

def jmembers(src):
    scan = sc.Scan("java", ".java", src.strip("\n").split("\n"))
    return [(m["name"], m["ret"], m["ctor"]) for m in scan.members if m["cat"] == "method"]


for _n, _src, _want in [
    ("g2 java public constructor is a ctor, not return type public",
     "public class A {\n  public A(int x) { }\n  private A() { }\n  public void run() { }\n}",
     [("A", None, True), ("A", None, True), ("run", "void", False)]),
    ("g2 java modified method keeps its return type",
     "class A {\n  public static final int f(int x) { return x; }\n}", [("f", "int", False)]),
]:
    CASES.append((_n, "g2", _src, _want))

# python: text inside prefixed (f/r/b/fr/rb) triple-quoted strings is not a member
for _n, _src, _want in [
    ("py f-triple-quoted string is blanked", 'X = f"""a\n  image: python:3\n"""\nclass C:\n    y: int = 1\n', ["y"]),
    ("py fr-triple-quoted string is blanked", "X = fr\'\'\'a\n  image: python:3\n\'\'\'\nclass C:\n    y: int = 1\n", ["y"]),
    ("py plain prefixed single-line string", 'X = f"a: b"\nclass C:\n    y: int = 1\n', ["y"]),
]:
    CASES.append((_n, "pyf", _src, _want))

def csfields(src):
    scan = sc.Scan("csharp", ".cs", src.strip("\n").split("\n"))
    return [(m["name"], m["ftype"]) for m in scan.members if m["cat"] == "field"]


for _n, _src, _want in [
    ("g3 csharp operator declaration is not a field",
     "class A {\n  public static bool operator ==(A a, A b) => true;\n  int n;\n}", [("n", "int")]),
    ("g3 csharp collection-spread element is not a field",
     "class A {\n  static readonly string[] Xs = [\n    .. Ys,\n    \"a\"];\n}", [("Xs", "string[]")]),
]:
    CASES.append((_n, "g3cs", _src, _want))


def csmembers(src):
    scan = sc.Scan("csharp", ".cs", src.strip("\n").split("\n"))
    return [(m["name"], m["ret"], m["ctor"]) for m in scan.members if m["cat"] == "method"]


for _n, _src, _want in [
    ("g2 csharp public constructor is a ctor, not return type public",
     "public class A {\n  public A(int x) { }\n  private A() { }\n  public void Run() { }\n}",
     [("A", None, True), ("A", None, True), ("Run", "void", False)]),
    ("g2 csharp modified method keeps its return type",
     "class A {\n  public static async Task<int> F(int x) { return x; }\n}", [("F", "Task<int>", False)]),
]:
    CASES.append((_n, "g2cs", _src, _want))

fails = 0
CASES += [(n, "pyp", s, w) for n, s, w in PYP]
for case in CASES:
    if case[1] == "pyf":
        name, _, src, want = case
        sn = sc.Scan("python", ".py", src.split("\n"))
        got = [m["name"] for m in sn.members if m["cat"] == "field" and m.get("ftype")]
    elif case[1] == "g3cs":
        name, _, src, want = case
        got = csfields(src)
    elif case[1] == "g2cs":
        name, _, src, want = case
        got = csmembers(src)
    elif case[1] == "pyp":
        name, _, src, want = case
        got = pyprops(src)
    elif case[1] == "g2":
        name, _, src, want = case
        got = jmembers(src)
    elif case[1] == "g1":
        name, _, src, want = case
        got = g1(src)
    elif case[1] == "d5":
        name, _, src, want = case
        got = f2_js(src)
    elif case[1] == "d4":
        name, _, (path, sib), want = case
        got = sc.is_bundled_asset(path, set(sib))
    elif case[1] is None:
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
