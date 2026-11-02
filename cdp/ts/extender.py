"""Data-driven extender: runs rules/<rule_file>.scm, applies rules/emit_map.json, adds only what a query cannot say
(fqn building, nesting/scope, text rendering). All per-language behaviour is in the .scm and the map (lang_overrides).
Pure function of (bytes, lang); runs in the worker."""
import json
import os
import re

import tree_sitter as ts

from . import engine

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = json.load(open(os.path.join(HERE, "rules", "emit_map.json")))
_Q, _M = {}, {}


class NoRules(Exception):
    pass


def rulemap(lang):
    if lang not in _M:
        _M[lang] = {**BASE, **BASE.get("lang_overrides", {}).get(lang, {})}
    return _M[lang]


def _query(lang, m):
    if lang not in _Q:
        f = os.path.join(HERE, "rules", m.get("rule_file", lang) + ".scm")
        if not os.path.exists(f):
            raise NoRules("no rules for %s (%s)" % (lang, os.path.basename(f)))
        _Q[lang] = ts.Query(engine.language(lang), open(f).read())
    return _Q[lang]


def _txt(data, n):
    return data[n.start_byte:n.end_byte].decode("utf8", "replace")


def _ty(data, n):
    return re.sub(r"\s+", " ", _txt(data, n)).strip()


def _unwrap(m, node):
    """Climb scope wrappers (export/declare/const-decl). Returns (outer, exported)."""
    exported = False
    while node.parent is not None and node.parent.type in m["scope_wrappers"]:
        node = node.parent
        exported |= node.type == "export_statement"
    return node, exported


def _scope(m, node):
    """(owner_class_node|None, exported) if node is top-level or a member of a top-level class; else None."""
    outer, exp = _unwrap(m, node)
    p = outer.parent
    if p is None:
        return None
    if p.type in m["root_types"] or (p.type in m.get("namespace_bodies", ()) and p.parent is not None
                                     and p.parent.type in m.get("namespace_types", ())):
        return (None, exp)
    if p.type in m.get("transparent_bodies", ()) and p.parent is not None:
        p = p.parent
    if p.type in m["member_bodies"] and p.parent is not None:
        o = _scope(m, p.parent)
        if o is not None and (o[0] is None or m.get("nested")) and p.parent.type in m.get("owner_types", [p.parent.type]):
            return (p.parent, o[1])
    return None


def _qual(m, data, owner):
    sc = _scope(m, owner)
    return (_qual(m, data, sc[0]) + "." if sc and sc[0] is not None else "") + _txt(data, owner.child_by_field_name("name"))


def _ns(m, data, node):
    """Dotted namespace of a top-level node (block namespaces around it + a preceding file-scoped one); '' if none."""
    names, n = [], node
    while n is not None:
        if n.type in m.get("namespace_types", ()) and n.child_by_field_name("name") is not None and n is not node:
            names.insert(0, _txt(data, n.child_by_field_name("name")))
        if n.parent is not None and n.parent.type in m["root_types"]:
            s = n.prev_sibling
            while s is not None and s.type not in m.get("file_scoped_types", ()):
                s = s.prev_sibling
            if s is not None:
                names.insert(0, _txt(data, s.child_by_field_name("name")))
        n = n.parent
    return ".".join(names)


def _collect(m, data, root, q):
    best, aux, params = {}, {}, {}
    for _pi, caps in ts.QueryCursor(q).matches(root):
        dk = next((k for k in caps if k in m["definitions"]), None)
        if dk:
            nid, pr = caps[dk][0].id, m.get("def_priority", {}).get(dk, 0)
            if nid not in best or best[nid][0] < pr:
                best[nid] = (pr, (dk, caps))
        elif "param" in caps:
            pn = caps["param"][0]
            d = params.setdefault(pn.id, {"node": pn})
            for cap, fld in m["param_fields"].items():
                if cap in caps:
                    d[fld] = _ty(data, caps[cap][0])
        elif "decl" in caps:
            b = aux.setdefault(caps["decl"][0].id, {})
            for cap, fld in m["aux_fields"].items():
                for n in caps.get(cap, []):
                    if n not in b.setdefault(fld, []):
                        b[fld].append(n)
    byowner = {}
    for p in params.values():
        o = p["node"].parent
        o = o.parent if o.type in m["param_list_types"] else o
        byowner.setdefault(o.id, []).append(p)
    return [v[1] for v in best.values()], aux, byowner


def _row(m, data, dk, caps, aux, byowner):
    node, name_n = caps[dk][0], caps["name"][0]
    if name_n.type not in m["name_node_types"]:
        return None
    sc = _scope(m, node)
    if sc is None:
        return None
    owner, exported = sc
    name = m.get("name_by_def", {}).get(dk, _txt(data, name_n))
    init = caps.get("init", [None])[0]
    kind = m["definitions"][dk]
    is_fn = init is not None and init.type in m["function_value_types"]
    if kind == "var":
        kw = node.parent.children[0].type if node.parent is not None else "var"
        kind = "function" if is_fn else m["var_kind_by_keyword"].get(kw, "field")
    elif kind == "field" and is_fn:
        kind = "function"
    if kind == "function" and owner is not None:
        kind = m["function_kind_in_class"]
    outer, _ = _unwrap(m, node)
    top = owner if owner is not None else node
    while owner is not None and _scope(m, top) and _scope(m, top)[0] is not None:
        top = _scope(m, top)[0]
    ns = _ns(m, data, top) if m.get("namespace_types") else ""
    prim = "{P}" + ("." + ns if ns else "")
    if owner is None:
        fqn = prim + "." + name
    else:
        fqn = prim + "." + _qual(m, data, owner) + m["separators"]["method" if kind == "method" else "field"] + name
    ids = [node.id] + ([init.id] if init is not None else [])
    ids_wrap = [outer.id] + ([outer.parent.id] if outer.parent is not None and outer.parent.type == "export_statement" else [])
    merged = {}
    for i in ids + ids_wrap:
        for f, ns in aux.get(i, {}).items():
            merged.setdefault(f, []).extend(n for n in ns if n not in merged.get(f, []))
    sib = node.prev_sibling                    # a class_body keeps a member's decorators as preceding siblings
    while sib is not None and sib.type in m["decorator_sibling_types"]:
        merged.setdefault("annotations", []).append(sib)
        sib = sib.prev_sibling
    mod = [_txt(data, n) for n in merged.get("modifier", [])]
    pp = m.get("private_name_prefix")
    if owner is not None and pp and name.startswith(pp):
        vis = "private"
    elif mod:
        vis = mod[0]
    elif dk in m.get("vis_by_def", {}):
        vis = m["vis_by_def"][dk]
    elif owner is None:
        vis = m["visibility"]["exported" if exported else "unexported"]
    else:
        vis = m.get("default_vis_by_owner", {}).get(owner.type, m["visibility"]["default_member"])
    row = {"fqn": fqn, "kind": kind, "visibility": vis, "line": name_n.start_point[0], "end_line": outer.end_point[0] + 1}
    if kind == "constant" and merged.get("value"):
        row["value"] = _txt(data, merged["value"][0])
    if kind in m.get("supertype_kinds", ("class", "interface", "enum")) and merged.get("supertypes"):
        row["supertypes"] = [_ty(data, n) for n in sorted(merged["supertypes"], key=lambda n: n.start_byte)]
    if merged.get("annotations"):
        row["annotations"] = []
        for n in sorted(merged["annotations"], key=lambda n: n.start_byte):
            t = _txt(data, n)
            mt = re.match(m["annotation_name_re"], t)
            row["annotations"].append([mt.group(1) if mt else t, t, n.start_point[0], n.end_point[0]])
    if kind in ("method", "function"):
        ps = []
        for p in sorted([p for i in ids for p in byowner.get(i, [])], key=lambda p: p["node"].start_byte):
            pr = {"name": re.sub(m["param_name_strip"], "", p.get("name", _ty(data, p["node"])))}
            if p.get("type"):
                pr["type"] = p["type"] + m.get("param_type_suffix", {}).get(p["node"].type, "")
            ps.append(pr)
        if ps:
            row["params"] = ps
        if merged.get("ret") and name not in m["ctor_names"]:
            r = _ty(data, merged["ret"][0])
            row["ret"] = m["void_sentinel"] if r == m["void_text"] else r
    elif kind in ("field", "constant") and merged.get("ftype"):
        row["ftype"] = _ty(data, merged["ftype"][0])
    if dk in m.get("ftype_owner_defs", ()):
        row["ftype"] = prim + "." + _qual(m, data, owner)
    return row


def extract(data, lang):
    """-> {"rows": [...], "errors": n, "has_error": bool, "lang_used", "skipped_lines", "retried"}; raises NoRules/GrammarMissing."""
    tree, used, stats = engine.parse(data, lang)
    data, _ = engine.blank_long_lines(data)
    m = rulemap(used)
    defs, aux, byowner = _collect(m, data, tree.root_node, _query(used, m))
    rows = [r for dk, caps in defs for r in [_row(m, data, dk, caps, aux, byowner)] if r]
    seen, out = set(), []
    for r in sorted(rows, key=lambda r: (r["line"], r["fqn"])):
        k = (r["fqn"], r["line"], r["kind"])
        if k not in seen:
            seen.add(k)
            out.append(r)
    return {"rows": out, "lang_used": used, **stats}
