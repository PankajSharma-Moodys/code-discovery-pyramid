"""Tree-sitter engine: grammar loading, parse policy, generated/vendor filter. No cdp imports (runs in the worker).

Parse policy (P8): lines over `max_line_bytes` (minified) are blanked, never the file; a `.js` file whose JS parse has
errors is retried with the TSX grammar and the parse with fewer ERROR/MISSING nodes wins; a file that still has errors
is indexed partially and flagged `has_error`. Every skip or retry is reported in the returned stats."""
import importlib
import json
import logging
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
log = logging.getLogger("cdp.ts")
CFG = json.load(open(os.path.join(HERE, "rules", "grammars.json")))
POLICY, GRAMMARS = CFG["policy"], CFG["grammars"]
EXT = {e: n for n, g in GRAMMARS.items() for e in g["ext"]}
_L, _P = {}, {}


class GrammarMissing(Exception):
    pass


def language(name):
    """tree_sitter.Language for `name`; GrammarMissing when the grammar package is not installed."""
    if name not in _L:
        import tree_sitter as ts
        g = GRAMMARS.get(name)
        if g is None:
            raise GrammarMissing("no grammar registered for %s" % name)
        try:
            _L[name] = ts.Language(getattr(importlib.import_module(g["module"]), g["fn"])())
        except ImportError as e:
            raise GrammarMissing("%s: %s" % (g["module"], e))
    return _L[name]


def parser(name):
    if name not in _P:
        import tree_sitter as ts
        _P[name] = ts.Parser(language(name))
    return _P[name]


def lang_for_path(path):
    return EXT.get(os.path.splitext(path)[1].lower())


def error_nodes(root):
    """Count ERROR/MISSING nodes with an iterative walk (no recursion limit on deep trees)."""
    n, cur, going = 0, root.walk(), True
    while going:
        n += cur.node.is_error or cur.node.is_missing
        if cur.goto_first_child():
            continue
        while not cur.goto_next_sibling():
            if not cur.goto_parent():
                going = False
                break
    return n


def blank_long_lines(data):
    """Replace over-long (minified) lines by empty ones so line numbers stay stable. -> (data, [1-based lines])."""
    mx, skipped, out = POLICY["max_line_bytes"], [], data.split(b"\n")
    for i, ln in enumerate(out):
        if len(ln) > mx:
            skipped.append(i + 1)
            out[i] = b""
    return (b"\n".join(out) if skipped else data), skipped


def parse(data, lang):
    """-> (tree, lang_used, stats). stats: errors (nodes), has_error, skipped_lines, retried."""
    data, skipped = blank_long_lines(data)
    tree = parser(lang).parse(data)
    errs, used, retried = error_nodes(tree.root_node), lang, None
    alt = POLICY["retry"].get(lang)
    if errs and alt:
        try:
            t2 = parser(alt).parse(data)
            e2 = error_nodes(t2.root_node)
            retried = {"lang": alt, "errors_before": errs, "errors_after": e2, "adopted": e2 < errs}
            if e2 < errs:
                tree, errs, used = t2, e2, alt
        except GrammarMissing as e:
            log.warning("retry grammar %s unavailable: %s", alt, e)
    return tree, used, {"errors": errs, "has_error": bool(tree.root_node.has_error), "skipped_lines": skipped,
                        "retried": retried}


_VENDOR_FILES = [re.compile(p) for p in POLICY["vendor_files"]]


def skip_reason(path, head):
    """Why a generated/vendored file is not indexed (None to index it). `head` = first lines of text."""
    parts = path.replace("\\", "/").split("/")
    for d in POLICY["vendor_dirs"]:
        if d in parts[:-1]:
            return "vendor_dir:" + d
    for rx in _VENDOR_FILES:
        if rx.search(parts[-1]):
            return "vendor_file:" + rx.pattern
    h = "\n".join(head[:POLICY["generated_head_lines"]]).lower()
    for m in POLICY["generated_markers"]:
        if m in h:
            return "generated:" + m
    return None
