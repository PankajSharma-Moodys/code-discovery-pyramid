import time
from cdp.lang.scala_tokens import ScTokens


def toks(src):
    t = ScTokens(src.split("\n"))
    return list(zip(t.kind, t.text)), t


def test_nested_block_comment_hides_nothing_after():
    k, t = toks("/* a /* b */ c */\nval x = 1\n")
    assert [x for _, x in k] == ["val", "x", "=", "1"]
    assert t.line[0] == 1


def test_deeply_nested_and_star_slash_edges():
    k, _ = toks("/* /* /* */ */ **/ val a /**/ val b /*/ x */ val c")
    assert [x for _, x in k] == ["val", "a", "val", "b", "val", "c"]


def test_comment_markers_in_strings_and_chars():
    k, _ = toks('val a = "http://x /* y"\nval b = \'/\'\nval c = 1')
    assert [x for _, x in k].count("val") == 3
    assert ('str', '"http://x /* y"') in k


def test_unterminated_comment_runs_to_eof_without_hang():
    t0 = time.time()
    k, _ = toks("val a = 1\n/* /* oops */ val b = 2\n" + "/* " * 500)
    assert [x for _, x in k] == ["val", "a", "=", "1"]
    assert time.time() - t0 < 2
