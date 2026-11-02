"""cdp.ts shared layer: switch, grammars, parse policy, extender rules, crash isolation, day-0 baseline."""
import importlib
import importlib.metadata as md

import pytest

from cdp import ts
from cdp.lang import get_extractor
from cdp.lang.base import ExtractContext
from cdp.ts import engine, front

PINS = {"tree-sitter-java": "0.23.5", "tree-sitter-c-sharp": "0.23.5", "tree-sitter-scala": "0.26.3",
        "tree-sitter-python": "0.25.0", "tree-sitter-typescript": "0.23.2", "tree-sitter-javascript": "0.25.0"}
JAVA = ("package a;\n@Foo(1) public class A extends B implements C { private static final int X = 3;\n"
        "  public static String m(int a, String... b) { return null; } A() {} }\n")
TSX = "export class A extends B { private x: number = 1; m(a: string): void {} }\nexport const K = 'v';\n"


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("CDP_HOME", str(tmp_path))
    monkeypatch.setenv("CDP_TS_INPROC", "1")


def by(rows):
    return {r["fqn"]: r for r in rows}


def test_switch(monkeypatch):
    monkeypatch.delenv("CDP_TS", raising=False)
    assert ts.enabled("java") and ts.enabled("scala") and ts.enabled("typescript") and ts.enabled("python") and not ts.enabled("c_sharp") and not ts.baseline_enabled()
    monkeypatch.setenv("CDP_TS", "java,csharp")
    assert ts.enabled("java") and ts.enabled("c_sharp") and not ts.enabled("python") and not ts.baseline_enabled()
    monkeypatch.setenv("CDP_TS", "all")
    assert ts.enabled("python") and ts.baseline_enabled()
    monkeypatch.setenv("CDP_TS", "off")
    assert not ts.enabled("java")


@pytest.mark.parametrize("dist,ver", sorted(PINS.items()))
def test_grammar_pins_and_import(dist, ver):
    assert md.version(dist) == ver
    for name, g in engine.GRAMMARS.items():
        if g["module"].replace("_", "-") == dist or g["module"] == dist.replace("-", "_"):
            importlib.import_module(g["module"])
            assert engine.parser(name).parse(b"").root_node is not None


def test_java_rows_schema():
    rows, meta = ts.extract_ex("java", "A.java", JAVA, "a")
    r = by(rows)
    assert r["a.A"]["supertypes"] == ["B", "C"] and r["a.A"]["annotations"][0]["name"] == "Foo"
    assert r["a.A.X"]["kind"] == "constant" and r["a.A.X"]["ftype"] == "int"
    m = r["a.A#m"]
    assert m["ret"] == "String" and m["params"] == [{"name": "a", "type": "int"}, {"name": "b", "type": "String[]"}]
    assert not meta["has_error"] and meta["dropped_no_anchor"] == 0


def test_typescript_and_tsx():
    for lang in ("typescript", "tsx"):
        r = by(ts.extract(lang, "a.ts", TSX, "mod"))
        assert r["mod.A#m"]["ret"] == "<none>" and r["mod.A.x"]["visibility"] == "private"
        assert r["mod.K"]["kind"] == "constant" and r["mod.K"]["value"] == "v"


def test_unsupported_returns_none():
    assert ts.extract("ruby", "a.rb", "x = 1\n") is None      # grammar present, no rules
    assert ts.extract("nosuchlang", "a.zz", "x") is None


def test_minified_line_skipped_not_file():
    src = "export const A = 1;\n" + "var x=" + "1+" * 600 + "1;\nexport const B = 2;\n"
    rows, meta = ts.extract_ex("javascript", "a.js", src, "m")
    assert meta["skipped_lines"] == [2] and set(by(rows)) == {"m.A", "m.B"}
    assert by(rows)["m.B"]["anchor"]["line"] == 3


def test_js_retry_with_tsx_and_partial_index():
    src = "export class A {\n  m(a: string) { return a }\n}\n"      # types in .js: JS grammar errors, TSX parses
    rows, meta = ts.extract_ex("javascript", "a.js", src, "m")
    assert meta["retried"]["adopted"] and meta["lang_used"] == "tsx" and not meta["has_error"] and "m.A#m" in by(rows)
    rows, meta = ts.extract_ex("javascript", "b.js", "export class A { m() {} }\nfunction ((( {\nexport const B = 1;\n", "m")
    assert meta["has_error"] and all(r["has_error"] for r in rows) and "m.A" in by(rows)


def test_vendor_and_generated_filter():
    for p, t in (("node_modules/x/a.js", "var a=1"), ("a/b.min.js", "var a=1"), ("a.ts", "// @generated\nexport const A = 1;")):
        rows, meta = ts.extract_ex("typescript", p, t)
        assert rows == [] and meta["skipped"]
    assert engine.skip_reason("src/a.ts", ["export const A = 1;"]) is None


def test_crash_isolated_and_logged(monkeypatch, caplog):
    monkeypatch.delenv("CDP_TS_INPROC")
    front._stop()                                   # a worker started by an earlier test would not crash
    monkeypatch.setattr(front, "_BOOT", "import os; os._exit(139)")
    rows, meta = ts.extract_ex("java", "A.java", JAVA, "a")
    assert rows == [] and meta["crash"] and meta["has_error"]
    assert "worker failure" in caplog.text
    monkeypatch.setattr(front, "_BOOT", front._BOOT.replace("os._exit(139)", "import time; time.sleep(30)"))
    monkeypatch.setenv("CDP_TS_TIMEOUT", "1")
    assert ts.extract_ex("java", "B.java", JAVA, "a")[1]["crash"]


def test_worker_process_roundtrip_and_cache(monkeypatch):
    monkeypatch.delenv("CDP_TS_INPROC")
    a = ts.extract("java", "A.java", JAVA, "a")
    monkeypatch.setattr(front, "_roundtrip", lambda *x: 1 / 0)     # second call must come from the disk cache
    assert ts.extract("java", "A.java", JAVA, "a") == a and a


RB = "module M\n  class C\n    def go\n      helper(1)\n    end\n    def self.mk; end\n  end\nend\n"


def test_baseline_day0_ruby_and_off_mode(monkeypatch):
    monkeypatch.setenv("CDP_TS", "off")
    assert type(get_extractor("lib/a.rb")).__name__ == "GenericExtractor"
    monkeypatch.setenv("CDP_TS", "java")
    assert type(get_extractor("lib/a.rb")).__name__ == "GenericExtractor"      # a language list does not enable baseline
    monkeypatch.setenv("CDP_TS", "all")
    ex = get_extractor("lib/a.rb")
    f = ex.extract(ExtractContext(path="lib/a.rb", lines=RB.splitlines(), module=""))
    d = {x["fqn"]: x for x in f.defines}
    assert "precision:baseline" in f.notes and d["M.C#go"]["precision"] == "baseline" and "M.C.mk" in d
    assert any(u["fqn"] == "helper" for u in f.uses)


def test_baseline_failure_is_logged_not_swallowed(monkeypatch, caplog):
    monkeypatch.setenv("CDP_TS", "all")
    monkeypatch.setattr(front, "_run", lambda *a: {"error": "boom"})
    f = get_extractor("lib/a.rb").extract(ExtractContext(path="lib/a.rb", lines=RB.splitlines(), module=""))
    assert any(n.startswith("baseline_parse_failed") for n in f.notes) and "boom" in caplog.text
