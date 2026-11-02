"""Shared tool-based (tree-sitter) extraction layer.

Entry point for language extractors: `extract(lang, path, text, prefix="")` -> list of define rows in the
cdp.lang.base schema (mk_define rows plus params/ret/ftype/supertypes), or None when the language has no rules or
grammar (the caller keeps its hand extractor). `extract_ex` also returns the parse meta. Switch: CDP_TS=<lang,lang|all|off>,
default java,scala,typescript,javascript,python in this branch; language extractors ask `enabled(lang)`. CDP_TS also turns on the day-0 baseline fallback for extensions
with no extractor when it is `all` or lists `baseline`."""
import logging
import os

log = logging.getLogger("cdp.ts")
_ALIAS = {"csharp": "c_sharp", "c#": "c_sharp", "js": "javascript", "ts": "typescript"}


def _modes():
    raw = os.environ.get("CDP_TS", "java,scala,typescript,javascript,python").strip().lower()
    return frozenset(_ALIAS.get(t.strip(), t.strip()) for t in raw.split(",") if t.strip()) or frozenset(("off",))


def enabled(lang):
    m = _modes()
    return "off" not in m and ("all" in m or _ALIAS.get(lang, lang) in m)


def baseline_enabled():
    m = _modes()
    return "off" not in m and ("all" in m or "baseline" in m)


def extract_ex(lang, path, text, prefix="", keep_raw=False):
    """-> (rows, meta) or None. meta: skipped (reason), has_error, errors, skipped_lines, retried, lang_used, dropped_no_anchor, crash/error."""
    from . import engine, front
    from cdp.lang.base import Ann, ExtractContext, anchor_at, mk_define
    lines = text.splitlines()
    why = engine.skip_reason(path, lines)
    if why:
        return [], {"skipped": why}
    r = front.call("extract", lang, "\n".join(lines))
    if "unsupported" in r:
        log.warning("cdp.ts: %s unsupported (%s); keep the hand extractor", lang, r["unsupported"])
        return None
    meta = {k: r[k] for k in ("has_error", "errors", "skipped_lines", "retried", "lang_used", "crash", "error") if k in r}
    ctx, rows, dropped = ExtractContext(path=path, lines=lines, module=""), [], 0
    sub = lambda s: s.replace("{P}.", prefix + "." if prefix else "").replace("{P}", prefix)
    for x in r["rows"]:
        a = anchor_at(ctx, x["line"])
        if a is None:
            dropped += 1
            continue
        anns = [Ann(n.rsplit(".", 1)[-1], t, s, e) for n, t, s, e in x.get("annotations", [])]
        row = mk_define(sub(x["fqn"]), x["kind"], x["visibility"], a, value=x.get("value"), end_line=x["end_line"], annotations=anns)
        if keep_raw:                           # untruncated annotation texts, for callers that re-render them
            row["raw_annotations"] = [n[1] for n in x.get("annotations", [])]
        for f in ("supertypes", "ret", "params"):
            if f in x:
                row[f] = x[f]
        if "ftype" in x:
            row["ftype"] = sub(x["ftype"])
        if r.get("has_error"):
            row["has_error"] = True
        rows.append(row)
    meta["dropped_no_anchor"] = dropped
    return rows, meta


def extract(lang, path, text, prefix=""):
    res = extract_ex(lang, path, text, prefix)
    return None if res is None else res[0]
