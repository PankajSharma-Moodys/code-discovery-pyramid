"""Day-0 fallback: a tags.scm-style query gives definitions and calls for any language that has a grammar installed
and an entry in rules/baseline.json. Facts carry precision: baseline. Per-language shape lives in baseline.json."""
import json
import logging
import os

from . import engine

HERE = os.path.dirname(os.path.abspath(__file__))
CFG = json.load(open(os.path.join(HERE, "rules", "baseline.json")))
BASE_EXT = {e: n for n, c in CFG.items() for e in engine.GRAMMARS[n]["ext"]}
log = logging.getLogger("cdp.ts")
_Q = {}


def _txt(n):
    return n.text.decode("utf8", "replace")


def _name(c, n):
    f = n.child_by_field_name("name")
    if f is not None:
        return _txt(f).split(c["name_split"])[-1]
    v = n.child_by_field_name("value")
    return _txt(v) if v is not None and n.type in c["value_field_types"] else None


def _call(c, cap, n):
    if cap != "reference.call":
        return None
    cc, par = c["call"], n.parent
    if n.type == cc["node"]:
        m, r = n.child_by_field_name(cc["name"]), n.child_by_field_name(cc["recv"])
        if m is not None:
            return dict(name=_txt(m), recv=_txt(r) if r is not None and r.type in cc["recv_types"] else None, line=m.start_point[0])
    elif n.type == c["bare_call"]["node"] and par is not None and par.type in c["bare_call"]["parents"]:
        return dict(name=_txt(n), recv=None, line=n.start_point[0])
    elif n.type == c["bare_const"]["node"] and par is not None and par.type not in c["bare_const"]["not_parents"]:
        return dict(name=_txt(n), recv=None, line=n.start_point[0])
    return None


def run(lang, data):
    import tree_sitter as ts
    c = CFG[lang]
    if lang not in _Q:
        scm = "\n".join(open(os.path.join(HERE, "rules", "baseline", f)).read() for f in c["queries"])
        _Q[lang] = ts.Query(engine.language(lang), scm)
    root = engine.parser(lang).parse(data).root_node
    out = {"err_nodes": engine.error_nodes(root), "defs": [], "calls": []}
    for cap, nodes in ts.QueryCursor(_Q[lang]).captures(root).items():
        for n in nodes:
            if cap.startswith("definition."):
                nm = _txt(n.child_by_field_name(c["const_def_name_field"])) if cap == "definition.constant" else _name(c, n)
                if not nm:
                    continue
                chain, p = [], n.parent
                while p is not None:
                    cn = _name(c, p) if p.type in c["containers"] else None
                    if cn:
                        chain.append(cn)
                    p = p.parent
                out["defs"].append(dict(kind=cap.split(".")[1], name=nm, scope=chain[::-1], line=n.start_point[0],
                                        end=n.end_point[0], static=n.type in c["static"]))
            else:
                call = _call(c, cap, n)
                if call:
                    out["calls"].append(call)
    return out


def extractor_for(name):
    """cdp.lang Extractor for a file name whose extension has a baseline entry and an installed grammar, else None."""
    ext = "." + name.rsplit(".", 1)[-1].lower() if "." in name else ""
    lang = BASE_EXT.get(ext)
    if lang is None:
        return None
    try:
        engine.language(lang)
    except engine.GrammarMissing as e:
        log.warning("baseline for %s unavailable: %s", ext, e)
        return None
    return _EX.setdefault(lang, _make(lang))


_EX = {}


def _make(lang):
    from cdp.lang.base import Extractor, FileFacts, anchor_at, count_loc, mk_define, mk_use
    from . import front

    class BaselineExtractor(Extractor):
        language = lang
        extensions = tuple(engine.GRAMMARS[lang]["ext"])

        def extract(self, ctx):
            f = FileFacts(path=ctx.path, language=lang, loc=count_loc(ctx.lines))
            why = engine.skip_reason(ctx.path, ctx.lines)
            if why:
                f.notes.append("ts_skipped:" + why)
                return f
            r = front.call("baseline", lang, "\n".join(ctx.lines))
            if "defs" not in r:
                log.warning("baseline failed for %s: %s", ctx.path, r.get("crash") or r.get("error"))
                f.notes.append("baseline_parse_failed:%s" % (r.get("crash") or r.get("error")))
                return f
            f.notes += ["precision:baseline", "parse_errors:%d" % r["err_nodes"]]
            for d in r["defs"]:
                a = anchor_at(ctx, d["line"])
                if a is None:
                    continue
                sc = ".".join(d["scope"])
                fqn = (sc + ("." if d["static"] else "#") if sc else "") + d["name"] if d["kind"] == "method" else (sc + "." if sc else "") + d["name"]
                row = mk_define(fqn, d["kind"], "unknown", a, end_line=d["end"] + 1)
                row["precision"] = "baseline"
                f.defines.append(row)
            for cl in r["calls"]:
                a = anchor_at(ctx, cl["line"])
                if a is None:
                    continue
                u = mk_use((cl["recv"] + "." if cl["recv"] else "") + cl["name"], a, resolved="external")
                u["precision"] = "baseline"
                f.uses.append(u)
            f.primary = next((x["fqn"] for x in f.defines if x["kind"] in ("class", "module")), None)
            return f

    return BaselineExtractor()
