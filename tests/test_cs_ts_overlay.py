"""C# tool overlay (cdp/lang/cs_ts.py): tool rows, hand fill-ins, and the fallback to hand rows."""
import pytest

pytest.importorskip("tree_sitter_c_sharp")
from cdp.lang.base import ExtractContext  # noqa: E402
from cdp.lang.csharp import CSharpExtractor  # noqa: E402

SRC = '''using System;
namespace N {
  public class C<T> : Base<T>, IFoo {
    public C(int a) {}
    public (int a, string b) M(params string[] xs, int @internal = 1) { return default; }
#if X
    [Fact]
#else
    [Fact(Skip = "s")]
#endif
    public void Test() {}
    public int @internal;
  }
  public record R(int Id, string Name);
}
'''


def _defs(src, mode, monkeypatch):
    monkeypatch.setenv("CDP_TS", mode)
    facts = CSharpExtractor().extract(ExtractContext(path="a.cs", lines=src.splitlines(), module=""))
    return {d["fqn"]: d for d in facts.defines}


def test_tool_rows_with_hand_fill(monkeypatch):
    d = _defs(SRC, "csharp", monkeypatch)
    assert d["N.C"]["end_line"] == 13 and d["N.C"]["supertypes"] == ["N.Base<~T>", "N.IFoo"]
    assert d["N.C#M"]["ret"] == "System.ValueTuple<int,string>"
    assert [p["name"] for p in d["N.C#M"]["params"]] == ["xs", "internal"]
    assert d["N.C#M"]["params"][0]["modifier"] == "params"
    assert [a["line"] for a in d["N.C#Test"]["annotations"]] == [7, 9]      # both #if branches kept
    assert "N.C.internal" in d and "N.R#<init>" in d and "N.R.Id" in d      # `@` stripped; primary constructor / record fields from hand


def test_same_rows_as_hand_except_spans(monkeypatch):
    a, b = _defs(SRC, "off", monkeypatch), _defs(SRC, "csharp", monkeypatch)
    assert a.keys() == b.keys()
    for k in a:
        for f in set(a[k]) | set(b[k]):
            assert f == "end_line" or a[k].get(f) == b[k].get(f), (k, f)


def test_parse_error_falls_back_to_hand(monkeypatch):
    bad = "namespace N { public class C { void M( { } } \n public class D { int x = ; ] }\n"
    a, b = _defs(bad, "off", monkeypatch), _defs(bad, "csharp", monkeypatch)
    assert a == b
