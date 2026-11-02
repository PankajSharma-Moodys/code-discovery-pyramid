"""TS/JS fqns use `/` in the owner and kind `function`; query helpers must handle both."""
from cdp.query import lookup


def test_short_name_splits_slash_owner():
    assert lookup._short_name("fx/sub/overloads#parse") == "parse"
    assert lookup._short_name("src/jpath#findPath") == "findPath"
    assert lookup._short_name("src/a/Svc.Cls#run") == "Cls#run"   # a method keeps its owner
    assert lookup._short_name("pkg.Outer.Inner#m") == "Inner#m"
    assert lookup._short_name("pkg.Type") == "Type"


def test_symbol_body_accepts_function_kind():
    # no store needed: a non-callable kind returns {}, a function kind must proceed past the kind gate
    assert lookup._symbol_body(None, "k", {"kind": "class"}, []) == {}
    assert lookup._symbol_body(None, "k", {"kind": "function"}, []) == {}  # no sites -> empty body, no crash
