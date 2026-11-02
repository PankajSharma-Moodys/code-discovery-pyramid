"""cdp.ts C# rules: declarations, namespaces (block + file-scoped), nesting, const, enum members, supertypes."""
import pytest

pytest.importorskip("tree_sitter_c_sharp")
from cdp import ts  # noqa: E402

SRC = '''namespace A.B { [Route("x")] public class C<T> : Base, IFoo {
  public const string K = "v"; private readonly int _f; public int P { get; set; }
  public C(int a) {} [HttpGet("a")] public async Task<int> M(string a, int b = 1) { return 1; }
  enum E { X, Y } } }
namespace D2; public interface I { void F(); }
'''


def _rows():
    rows = ts.extract("csharp", "t.cs", SRC, "")
    return {r["fqn"]: r for r in rows}


def test_fqns_kinds_and_namespaces():
    r = _rows()
    assert r["A.B.C"]["kind"] == "class" and r["A.B.C"]["supertypes"] == ["Base", "IFoo"]
    assert r["A.B.C.K"]["kind"] == "constant" and r["A.B.C.K"]["value"] == '"v"'
    assert r["A.B.C._f"]["visibility"] == "private" and r["A.B.C.P"]["ftype"] == "int"
    assert r["A.B.C#<init>"]["params"] == [{"name": "a", "type": "int"}]
    assert r["A.B.C#M"]["ret"] == "Task<int>" and r["A.B.C#M"]["annotations"][0]["name"] == "HttpGet"
    assert r["A.B.C.E.X"]["kind"] == "field" and r["A.B.C.E"]["visibility"] == "private"
    assert r["D2.I"]["visibility"] == "public" and r["D2.I#F"]["visibility"] == "public"
