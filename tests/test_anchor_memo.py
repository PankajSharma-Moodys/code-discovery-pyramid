"""build_fact_anchor is memoised per file; the memo must never change an answer."""
from cdp import anchor as A


def _lines(n=40, dup=True):
    out = ["unique line number %d with enough text" % i for i in range(n)]
    if dup:
        out += ["foo();"] * 10
    return out


def _fresh(path, lines, i):
    return A._build_fact_anchor(path, lines, i)


def test_memo_matches_unmemoised_for_every_index():
    lines = _lines()
    for i in list(range(len(lines))) + [-1, len(lines), len(lines) + 5]:
        assert A.build_fact_anchor("a.py", lines, i) == _fresh("a.py", lines, i)
        assert A.build_fact_anchor("a.py", lines, i) == _fresh("a.py", lines, i)  # second call = hit


def test_repeated_lines_keep_exact_marker():
    lines = _lines()
    a = A.build_fact_anchor("a.py", lines, 45)
    assert a and a.get(A.EXACT) and a["line"] == 46


def test_returned_dict_is_a_copy():
    lines = _lines()
    first = A.build_fact_anchor("a.py", lines, 3)
    first["line"] = 999
    first["extra"] = 1
    assert A.build_fact_anchor("a.py", lines, 3) == _fresh("a.py", lines, 3)


def test_files_do_not_share_entries():
    a, b = _lines(), ["other text entirely %d here ok" % i for i in range(40)]
    ax = A.build_fact_anchor("a.py", a, 3)
    bx = A.build_fact_anchor("b.py", b, 3)
    assert ax["file"] == "a.py" and bx["file"] == "b.py" and ax["anchor"] != bx["anchor"]
    # same path, different list object: no stale hit
    c = list(b)
    c[3] = "changed line three has new text"
    assert A.build_fact_anchor("a.py", c, 3)["anchor"] == "changed line three has new text"


def test_memo_is_bounded():
    keep = [_lines(5 + i) for i in range(10)]
    for ls in keep:
        A.build_fact_anchor("f.py", ls, 0)
    assert len(A._FACT_MEMO) <= A._FACT_MEMO_MAX
