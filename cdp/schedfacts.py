"""Schedule claims with values (ANNOTATIONS_PLAN P6, fixes T6).

The schedule edge says *that* a class or method is timer-triggered; the interval, cron expression,
start delay, misfire policy and concurrency live in the annotation arguments. This module reads
those from the parsed annotation rows of the declarations a `schedule.*` rule matched, and states
them as one sentence per scheduled symbol, phrased from the cited annotation text so the evidence
holds every value the sentence names.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence

from .anchor import build_anchor, verify_anchor
from .rules import JVM_LANGS, ON_KINDS, TYPE_KINDS, _Index, _decl_sites, _flatten, _on_for, _owner_of, _source, builtin_rules
from .util import normalise_ws, read_lines

MAX_CHUNK_LINES = 4
MAX_EVIDENCE = 6


def _text(v) -> str:
    """An argument as sentence text: strings and numbers as written, a constant by its last segment."""
    if isinstance(v, bool) or v is None:
        return "" if v is None else str(v).lower()
    if isinstance(v, (str, int, float)):
        return str(v)
    if isinstance(v, list):
        return ", ".join(t for t in (_text(x) for x in v) if t)
    if isinstance(v, dict):
        if "ref" in v:
            return v["ref"].rsplit(".", 1)[-1]
        if "concat" in v:
            return "".join(_text(p) for p in v["concat"])
    return ""


def _unit(args: Dict) -> str:
    unit = _text(args.get("timeUnit")).lower()
    return " " + unit if unit else "ms"


def _amount(args: Dict, key: str, numeric_unit: str) -> str:
    raw = args.get(key)
    text = _text(raw)
    if not text:
        return ""
    return text + (numeric_unit if isinstance(raw, (int, float)) and not isinstance(raw, bool) else "")


def _timing(name: str, args: Dict):
    """`(timing phrase, start-delay phrase)` of one schedule annotation, either may be empty."""
    unit = _unit(args)
    if name == "Every":
        every = _text(args.get("value"))
        return ("every " + every if every else ""), ""
    if name == "On":
        cron = _text(args.get("value"))
        return ("on cron %s" % cron if cron else ""), ""
    if name == "DelayStart":
        delay = _text(args.get("value"))
        return "", ("after a %s start delay" % delay if delay else "")
    if name == "OnApplicationStart":
        return "on application start", ""
    if name == "OnApplicationStop":
        return "on application stop", ""
    if name in ("Scheduled", "Schedule"):
        parts = []
        if name == "Schedule":
            fields = [(k, _text(args[k])) for k in ("second", "minute", "hour", "dayOfMonth", "month", "dayOfWeek", "year")
                      if args.get(k) is not None and _text(args.get(k))]
            parts.append("on a calendar schedule (%s)" % ", ".join("%s=%s" % kv for kv in fields) if fields
                         else "on the default calendar schedule")
        for key, fmt in (("cron", "on cron %s"), ("every", "every %s")):
            if _text(args.get(key)):
                parts.append(fmt % _text(args[key]))
        for key, fmt in (("fixedRate", "at a fixed rate of %s"), ("fixedRateString", "at a fixed rate of %s"),
                         ("fixedDelay", "with a fixed delay of %s between runs"),
                         ("fixedDelayString", "with a fixed delay of %s between runs")):
            amount = _amount(args, key, unit)
            if amount:
                parts.append(fmt % amount)
        delay = _amount(args, "initialDelay", unit) or _amount(args, "initialDelayString", unit) \
            or _amount(args, "delayed", "")
        return " ".join(parts), ("after a %s start delay" % delay if delay else "")
    return "", ""


def describe(name: str, items: Sequence[Dict]) -> Optional[str]:
    """`<name> runs <timings> <start delay> (<misfire>, no concurrent runs)`, or None when no
    annotation states a timing (a bare `@DisallowConcurrentExecution` schedules nothing)."""
    timings: List[str] = []
    delays: List[str] = []
    extras: List[str] = []
    for it in items:
        ann = it["ann"]
        args = ann.get("args") or {}
        simple = ann.get("name") or ""
        if simple == "DisallowConcurrentExecution":
            if "no concurrent runs" not in extras:
                extras.append("no concurrent runs")
            continue
        timing, delay = _timing(simple, args)
        if timing:
            timings.append(timing)
        if delay:
            delays.append(delay)
        misfire = _text(args.get("misfirePolicy")) or _text(args.get("misfire"))
        if misfire and "misfire %s" % misfire not in extras:
            extras.insert(0, "misfire %s" % misfire)
    if not timings:
        return None
    text = "%s runs %s" % (name, " and ".join(timings))
    if delays:
        text += " " + " ".join(delays)
    if extras:
        text += " (%s)" % ", ".join(extras)
    return text


def schedule_sources(extraction: Dict) -> List[Dict]:
    """One row per scheduled symbol: `{source, file, module, decl, owner, items}` where `items` are
    the declaration's directly matched `schedule.*` annotation rows."""
    rules = [r for r in builtin_rules() if r["id"].startswith("schedule.")]
    idx = _Index(extraction, rules)
    out: Dict[str, Dict] = {}
    for d in extraction.get("defines") or ():
        rel = d.get("file")
        if idx.lang(rel) not in JVM_LANGS:
            continue
        owner = _owner_of(d, idx)
        for role, ann, _param in _decl_sites(d):
            if role != "decl":
                continue
            for rule in idx.direct(ann, _on_for(d, role), idx.lang(rel)):
                source = _source(d, owner)
                row = out.setdefault(source, {"source": source, "file": rel, "module": d.get("module"), "decl": d,
                                              "owner": owner, "items": []})
                row["items"].append({"rule": rule["id"], "ann": ann, "decl": d})
    return [out[k] for k in sorted(out)]


def _span_anchors(rel: str, lines: Sequence[str], first: int, last: int) -> List[Dict]:
    """Anchors that together cover source lines `first..last` (1-based): chunks of up to 4 lines,
    so a multi-line `@Every(...)` is cited with every argument it states."""
    out = []
    line = first
    while line <= last and len(out) < 3:
        end = min(last, line + MAX_CHUNK_LINES - 1)
        anchor = {"file": rel, "line": line, "anchor": normalise_ws(" ".join(lines[line - 1:end]))}
        if verify_anchor(lines, anchor)[0]:
            out.append(anchor)
        else:
            grown = build_anchor(rel, lines, line - 1)
            if grown:
                out.append(grown)
        line = end + 1
    return out


def evidence(repo, row: Dict) -> List[Dict]:
    lines = read_lines(repo / row["file"]) if repo is not None else []
    if not lines:
        return []
    out: List[Dict] = []
    seen = set()
    for it in sorted(row["items"], key=lambda i: i["ann"].get("line") or 0):
        ann = it["ann"]
        first = ann.get("line") or 0
        last = ann.get("end_line") or first
        if not first or (first, last) in seen:
            continue
        seen.add((first, last))
        out += _span_anchors(row["file"], lines, first, last)
    owner = row["owner"] or row["decl"]
    line = (owner.get("anchor") or {}).get("line")
    if line:
        for a in _span_anchors(row["file"], lines, line, line):
            out.append(a)
    uniq, keys = [], set()
    for a in out:
        k = (a["file"], a["line"], a["anchor"])
        if k not in keys:
            keys.add(k)
            uniq.append(a)
    return uniq[:MAX_EVIDENCE]
