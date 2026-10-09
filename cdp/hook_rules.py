"""What a search or read is really asking, and the index's answer to it.

The hook's gate uses this to replace a recursive grep, a find by name or a
whole-file Read with the answer the index already holds. Everything here fails
open: an unparsable command, an unknown term or a failed lookup means the tool
call runs as it would have.
"""

from __future__ import annotations

import json
import re
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional

GREP_COMMANDS = frozenset(["grep", "egrep", "fgrep", "rg", "ag", "ack"])
RECURSIVE_BY_DEFAULT = frozenset(["rg", "ag", "ack"])

#: Options that take the next token as their value; it is not the pattern.
_VALUE_FLAGS = frozenset(["-A", "-B", "-C", "-m", "-g", "-t", "-T", "-d", "-f", "-j",
                          "--include", "--exclude", "--exclude-dir", "--type", "--max-count",
                          "--glob", "--max-depth"])

_IDENT = re.compile(r"[A-Za-z_$][A-Za-z0-9_$]{3,}")

#: Seconds a lookup may take before the call is let through.
LOOKUP_TIMEOUT = 10

#: How much of the index's answer goes into one denial.
MAX_USES_SHOWN = 8
MAX_TERMS = 3
MAX_OUTLINE_LINES = 70


def is_identifier_like(term: str) -> bool:
    """A name worth looking up: camelCase, PascalCase or snake_case. Plain
    lowercase words (`save`, `reservations`) match too much to mean a symbol."""
    return any(c.isupper() for c in term[1:]) or "_" in term or term[:1].isupper()


def _terms(text: str) -> List[str]:
    seen: List[str] = []
    for term in _IDENT.findall(text):
        if is_identifier_like(term) and term not in seen:
            seen.append(term)
    return seen


def _file_like(path: str) -> bool:
    return bool(Path(path).suffix)


def _split_command(command: str) -> List[tuple]:
    """`(text, piped)` for each command in a shell line, split on `|`, `||`, `&&`
    and `;` outside quotes. `piped` is true when the previous separator was `|`."""
    out: List[tuple] = []
    buf: List[str] = []
    quote = ""
    piped = False
    i = 0
    while i < len(command):
        ch = command[i]
        if quote:
            buf.append(ch)
            if ch == "\\" and quote == '"' and i + 1 < len(command):
                i += 1
                buf.append(command[i])
            elif ch == quote:
                quote = ""
        elif ch in "'\"":
            quote = ch
            buf.append(ch)
        elif ch == "\\" and i + 1 < len(command):
            buf.append(ch)
            i += 1
            buf.append(command[i])
        elif ch in "|;&":
            two = command[i:i + 2]
            if ch == "&" and two != "&&":
                buf.append(ch)  # a lone `&` (background, or inside `2>&1`) is not a separator
            else:
                out.append(("".join(buf), piped))
                buf = []
                piped = two != "||" and ch == "|"
                if two in ("||", "&&"):
                    i += 1
        else:
            buf.append(ch)
        i += 1
    out.append(("".join(buf), piped))
    return out


def _tokens(segment: str) -> List[str]:
    try:
        return shlex.split(segment)
    except ValueError:
        return segment.split()


def shell_searches(command: str) -> List[Dict]:
    """Recursive greps and finds in a shell command, as `{"kind", "terms"}`.

    `grep` fed by a pipe, or pointed at single files, is not a repository
    search and is left out.
    """
    found: List[Dict] = []
    for part, piped in _split_command(command):
        tokens = _tokens(part.strip())
        if not tokens:
            continue
        program = tokens[0].rsplit("/", 1)[-1]
        if program in GREP_COMMANDS and not piped:
            hit = _grep(program, tokens[1:])
        elif program == "find":
            hit = _find(tokens[1:])
        else:
            hit = None
        if hit and hit["terms"]:
            found.append(hit)
    return found


def _grep(program: str, args: List[str]) -> Optional[Dict]:
    recursive = program in RECURSIVE_BY_DEFAULT
    patterns: List[str] = []
    positionals: List[str] = []
    skip = False
    expect_pattern = False
    for arg in args:
        if skip:
            skip = False
            continue
        if expect_pattern:
            patterns.append(arg)
            expect_pattern = False
        elif arg == "-e":
            expect_pattern = True
        elif arg.startswith("--regexp="):
            patterns.append(arg.split("=", 1)[1])
        elif arg in ("--recursive", "--dereference-recursive"):
            recursive = True
        elif arg in _VALUE_FLAGS:
            skip = True
        elif arg.startswith("--"):
            continue
        elif arg.startswith("-") and len(arg) > 1:
            if "r" in arg[1:] or "R" in arg[1:]:
                recursive = True
        else:
            positionals.append(arg)
    if not patterns and positionals:
        patterns.append(positionals.pop(0))
    if not recursive or not patterns:
        return None
    if positionals and all(_file_like(p) for p in positionals):
        return None  # a named file or files: already targeted
    return {"kind": "grep", "terms": _terms(" ".join(patterns))}


def _find(args: List[str]) -> Optional[Dict]:
    names = [args[i + 1] for i, a in enumerate(args[:-1]) if a in ("-name", "-iname", "-path")]
    terms = _terms(" ".join(names))
    return {"kind": "find", "terms": terms} if terms else None


def tool_searches(tool_name: str, tool_input: Dict) -> List[Dict]:
    """The Grep and Glob tools, in the same shape as `shell_searches`."""
    if tool_name == "Grep":
        pattern, path = tool_input.get("pattern"), str(tool_input.get("path") or "")
        if isinstance(pattern, str) and not (path and _file_like(path)):
            terms = _terms(pattern)
            return [{"kind": "grep", "terms": terms}] if terms else []
    if tool_name == "Glob":
        pattern = tool_input.get("pattern")
        if isinstance(pattern, str):
            terms = _terms(pattern.rsplit("/", 1)[-1])
            return [{"kind": "find", "terms": terms}] if terms else []
    return []


# --------------------------------------------------------------- the index


def _query(repo: Path, args: List[str]) -> Optional[Dict]:
    run_py = Path(__file__).resolve().parent.parent / "run.py"
    try:
        proc = subprocess.run(
            [sys.executable, str(run_py), "query"] + args + ["--repo", str(repo), "--json"],
            capture_output=True, text=True, timeout=LOOKUP_TIMEOUT, check=False)
        data = json.loads(proc.stdout)
    except Exception:  # noqa: BLE001 -- fail open
        return None
    return data if isinstance(data, dict) else None


def _last_name(fqn: str) -> str:
    return fqn.rsplit(".", 1)[-1].rsplit("#", 1)[-1]


def _group_ranges(cites: List[str]) -> str:
    """`a.java:1-2, a.java:5, b.java:9` -> `a.java:1-2,5; b.java:9`."""
    by_file: Dict[str, List[str]] = {}
    for c in cites:
        file, _, span = c.rpartition(":")
        by_file.setdefault(file, []).append(span)
    return "; ".join("%s:%s" % (f, ",".join(spans)) for f, spans in by_file.items())


def symbol_answer(repo: Path, term: str) -> Optional[str]:
    """Definitions and uses of exactly `term`, or None if the index has no such
    symbol (a substring match is not an answer to a grep for a name)."""
    data = _query(repo, ["symbol", term, "--budget", "40"])
    entries = [e for e in (data or {}).get("found", []) if _last_name(e["fqn"]) == term]
    if not entries:
        return None
    lines = ["symbol %s" % term]
    for e in entries[:6]:
        where = _group_ranges(e.get("defined_range") or e.get("defined_at") or [])
        lines.append("  %s [%s %s] defined %s" % (e["fqn"].rsplit(".", 1)[-1], e["visibility"],
                                                    e["kind"], where))
        uses = e.get("used_by") or []
        count = e.get("used_by_count", len(uses))
        if count:
            shown = ", ".join(u["at"] for u in uses[:MAX_USES_SHOWN])
            more = " (+%d more)" % (count - min(len(uses), MAX_USES_SHOWN)) if count > MAX_USES_SHOWN else ""
            lines.append("    used by %d: %s%s" % (count, shown, more))
    if len(entries) > 6:
        lines.append("  (+%d more definitions)" % (len(entries) - 6))
    return "\n".join(lines)


def file_answer(repo: Path, term: str) -> Optional[str]:
    """Files whose name is `term` (with or without an extension)."""
    data = _query(repo, ["file", term, "--budget", "20"])
    hits = [f for f in (data or {}).get("found", [])
            if Path(f["path"]).stem == Path(term).stem or Path(f["path"]).name == term]
    if not hits:
        return None
    return "files named %s\n%s" % (term, "\n".join(
        "  %s (%s, %d loc)" % (f["path"], f["role"], f["loc"]) for f in hits[:10]))


def outline(repo: Path, rel: str) -> Optional[Dict]:
    """`{"loc": N, "lines": [...]}` for one source file: each member with its
    line range, in file order."""
    data = _query(repo, ["file", rel, "--budget", "200"])
    entries = [f for f in (data or {}).get("found", []) if f["path"] == rel]
    if not entries:
        return None
    entry = entries[0]
    lines = []
    for d in entry.get("defines", []):
        end = d.get("end_line")
        span = "%s-%s" % (d["line"], end) if end and end != d["line"] else str(d["line"])
        lines.append("L%-9s %-9s %-8s %s" % (span, d.get("visibility") or "", d["kind"],
                                             d.get("name") or d["fqn"]))
    return {"loc": entry["loc"], "lines": lines}


def search_answer(repo: Path, searches: List[Dict]) -> Optional[str]:
    """The index's answer to a set of searches, or None if it has none."""
    blocks: List[str] = []
    for search in searches:
        for term in search["terms"]:
            if len(blocks) >= MAX_TERMS:
                break
            block = (file_answer if search["kind"] == "find" else symbol_answer)(repo, term)
            if block:
                blocks.append(block)
    return "\n".join(blocks) if blocks else None
