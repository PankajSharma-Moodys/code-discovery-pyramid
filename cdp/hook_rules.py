"""What a search or read is really asking, and the index's answer to it.

The hook's gate uses this to replace a recursive grep, a find by name or a
whole-file Read with the answer the index already holds. Everything here fails
open: an unparsable command, an unknown term or a failed lookup means the tool
call runs as it would have.
"""

from __future__ import annotations

import fnmatch
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
#: Options that narrow a search by leaving something out: the index's answer covers the
#: whole repository, so a call using any of them runs as written.
_EXCLUSION_OPTIONS = ("--exclude", "--exclude-dir", "--exclude-from", "--ignore", "--ignore-dir",
                      "--ignore-file", "--ignore-case-not")

_VALUE_FLAGS = frozenset(["-A", "-B", "-C", "-m", "-g", "-t", "-T", "-d", "-f", "-j",
                          "--include", "--exclude", "--exclude-dir", "--exclude-from", "--ignore-dir",
                          "--ignore-file", "--type", "--max-count",
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
    """`(text, piped, separator)` for each command in a shell line, split on `|`,
    `||`, `&&` and `;` outside quotes. `piped` is true when the previous separator
    was `|`; `separator` is that separator (`""` for the first command)."""
    out: List[tuple] = []
    buf: List[str] = []
    quote = ""
    piped = False
    sep = ""
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
                out.append(("".join(buf), piped, sep))
                buf = []
                piped = two != "||" and ch == "|"
                sep = two if two in ("||", "&&") else ch
                if two in ("||", "&&"):
                    i += 1
        else:
            buf.append(ch)
        i += 1
    out.append(("".join(buf), piped, sep))
    return out


def _tokens(segment: str) -> List[str]:
    try:
        tokens = shlex.split(segment)
    except ValueError:
        tokens = segment.split()
    # Redirects (`2>&1`, `2>/dev/null`, `> out`) are not operands.
    kept: List[str] = []
    skip_next = False
    for token in tokens:
        if skip_next:
            skip_next = False
        elif re.match(r"^(\d*|&)>>?", token):
            skip_next = re.fullmatch(r"(\d*|&)>>?", token) is not None
        else:
            kept.append(token)
    return kept


def shell_searches(command: str, targeted: bool = False) -> List[Dict]:
    """Recursive greps and finds in a shell command, as `{"kind", "terms"}`.

    `grep` fed by a pipe, or pointed at single files, is not a repository
    search and is left out, unless `targeted` (an empty result is worth a hint
    whatever the scope).
    """
    found: List[Dict] = []
    for part, piped, _sep in _split_command(command):
        tokens = _tokens(part.strip())
        if not tokens:
            continue
        program = tokens[0].rsplit("/", 1)[-1]
        if program in GREP_COMMANDS and not piped:
            hit = _grep(program, tokens[1:], targeted)
        elif program == "find":
            hit = _find(tokens[1:])
        else:
            hit = None
        if hit and hit["terms"]:
            found.append(hit)
    return found


#: File types the index's symbols come from. A search restricted to anything else
#: (`--include=*.xml`) asks something the symbol index cannot answer.
SOURCE_EXTENSIONS = frozenset(["java", "kt", "scala", "py", "cs", "js", "ts", "go", "groovy"])

#: A pipe may only feed these into a search: they limit or order output, so the
#: index's answer still covers what was asked. (`grep -v`, `wc`, `xargs` change it.)
OUTPUT_FILTERS = frozenset(["head", "tail", "sort", "uniq", "cut", "cat"])

#: grep options that change what a match means or ask for more than a location.
_UNANSWERABLE_FLAGS = frozenset("vocLABC")
_ESCAPE = re.compile(r"\\.")


def _source_scope(value: str) -> bool:
    """Whether an include glob / file type names only source languages."""
    ext = value.rsplit(".", 1)[-1].strip("*'\"") if "." in value else value.strip("*'\"")
    return not ext or ext in SOURCE_EXTENSIONS


def _single_term(alternative: str) -> Optional[str]:
    """The one identifier an alternative of a pattern is exactly, or None when it
    says anything more (`get.*Priority`, `jdbc:sqlserver`, a plain word)."""
    words = re.findall(r"[A-Za-z0-9_$]+", _ESCAPE.sub(" ", alternative))
    if len(words) != 1:
        return None
    word = words[0]
    return word if _IDENT.fullmatch(word) and is_identifier_like(word) else None


def _answerable(pattern_text: str) -> bool:
    """True when every alternative of the pattern is one identifier."""
    alternatives = [a for a in re.split(r"\\\||\||\n", pattern_text)]
    return bool(alternatives) and all(_single_term(a) for a in alternatives)


def _grep(program: str, args: List[str], targeted: bool = False) -> Optional[Dict]:
    recursive = program in RECURSIVE_BY_DEFAULT
    patterns: List[str] = []
    positionals: List[str] = []
    skip = ""
    expect_pattern = False
    complete = True
    for arg in args:
        if skip:
            if skip in ("--include", "-g", "--glob", "-t", "--type") and not _source_scope(arg):
                complete = False
            if skip in _EXCLUSION_OPTIONS or (skip in ("-g", "--glob") and arg.startswith("!")):
                complete = False
            if skip in ("-A", "-B", "-C"):
                complete = False
            skip = ""
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
            skip = arg
        elif arg.startswith("--"):
            name, _, value = arg.partition("=")
            if name in ("--include", "--glob", "--type") and value and not _source_scope(value):
                complete = False
            if name in _EXCLUSION_OPTIONS or (name == "--glob" and value.startswith("!")):
                complete = False
            if name in ("--invert-match", "--only-matching", "--count", "--files-without-match",
                        "--after-context", "--before-context", "--context"):
                complete = False
            continue
        elif arg.startswith("-") and len(arg) > 1:
            letters = arg[1:]
            if "r" in letters or "R" in letters:
                recursive = True
            if any(c in _UNANSWERABLE_FLAGS for c in letters) or letters.isdigit():
                complete = False
        else:
            positionals.append(arg)
    if not patterns and positionals:
        patterns.append(positionals.pop(0))
    if not patterns or not (recursive or targeted):
        return None
    if positionals and all(_file_like(p) for p in positionals) and not targeted:
        return None  # a named file or files: already targeted
    text = "\n".join(patterns)
    return {"kind": "grep", "terms": _terms(" ".join(patterns)), "paths": positionals,
            "complete": complete and _answerable(text)}


def _name_term(pattern: str) -> Optional[str]:
    """`ReservationService*.java` -> `ReservationService`; None for a glob the
    name alone cannot stand for (`*Service.java`, `Foo*Bar`)."""
    stem = re.sub(r"\.[A-Za-z0-9]+$", "", pattern).rstrip("*")
    return _single_term(stem) if stem and "*" not in stem and "?" not in stem and "[" not in stem else None


def _find(args: List[str]) -> Optional[Dict]:
    terms: List[str] = []
    globs: List[str] = []
    complete = True
    negate = False
    paths: List[str] = []
    for arg in args:  # the operands before the first expression
        if arg.startswith(("-", "!", "(")):
            break
        paths.append(arg)
    for i, arg in enumerate(args):
        if arg in ("!", "-not", "-prune", "-o", "-or", "("):
            complete = False  # an exclusion or alternative: the index cannot reproduce it
        if arg in ("!", "-not"):
            negate = True
            continue
        value = args[i + 1] if i + 1 < len(args) else ""
        if arg in ("-name", "-iname", "-path", "-ipath", "-wholename") and not negate:
            term = _name_term(value) if arg in ("-name", "-iname") else None
            if term:
                terms.append(term)
                globs.append(value)
            else:
                complete = False
        elif arg == "-type" and value != "f":
            complete = False
        elif arg in ("-exec", "-execdir", "-ok", "-delete", "-print0"):
            complete = False
        negate = False
    return ({"kind": "find", "terms": terms, "complete": complete, "globs": globs, "paths": paths}
            if terms else None)


def tool_searches(tool_name: str, tool_input: Dict, targeted: bool = False) -> List[Dict]:
    """The Grep and Glob tools, in the same shape as `shell_searches`."""
    if tool_name == "Grep":
        pattern, path = tool_input.get("pattern"), str(tool_input.get("path") or "")
        if isinstance(pattern, str) and (targeted or not (path and _file_like(path))):
            terms = _terms(pattern)
            complete = _answerable(pattern)
            if any(tool_input.get(k) for k in ("-A", "-B", "-C", "context", "-v", "invert", "multiline")):
                complete = False
            scope = tool_input.get("glob") or tool_input.get("type")
            if scope and not _source_scope(str(scope)):
                complete = False
            return [{"kind": "grep", "terms": terms, "complete": complete}] if terms else []
    if tool_name == "Glob":
        pattern = tool_input.get("pattern")
        if isinstance(pattern, str):
            last = pattern.rsplit("/", 1)[-1]
            term = _name_term(last)
            return [{"kind": "find", "terms": [term], "complete": True, "globs": [last]}] if term else []
    return []


def _unquoted(command: str) -> str:
    """`command` with quoted text and escaped characters blanked out, same length."""
    out: List[str] = []
    quote = ""
    i = 0
    while i < len(command):
        ch = command[i]
        if quote:
            if ch == "\\" and quote == '"' and i + 1 < len(command):
                out.append("  ")
                i += 2
                continue
            if ch == quote:
                quote = ""
            out.append(" ")
        elif ch in "'\"":
            quote = ch
            out.append(" ")
        elif ch == "\\" and i + 1 < len(command):
            out.append("  ")
            i += 2
            continue
        else:
            out.append(ch)
        i += 1
    return "".join(out)


def redirects(command: str) -> List[tuple]:
    """`(fd, target)` for every unquoted output redirect in a shell line: `2>&1` is
    `("2", "&1")`, `&>f` and `>f` are `("", "f")`, `.>/tmp/o` is `("", "/tmp/o")`."""
    text = _unquoted(command)
    found: List[tuple] = []
    for match in re.finditer(r">>?\|?(&?)[ \t]*([^\s;|&<>()]*)", text):
        before = text[:match.start()]
        digits = re.search(r"(\d+)$", before)
        fd = digits.group(1) if digits else ""
        target = match.group(1) + match.group(2)
        if match.group(0).startswith(">|"):
            target = "|"
        found.append((fd, target))
    return found


def is_pure_search(command: str) -> bool:
    """True only when a shell line is nothing but a repository search, optionally
    followed by output limiters (`| head`). A `;`, `&&`, `||`, a `cd`, a `git log`,
    a redirect or a substitution makes it something else, and a denial would drop
    the part that is not a search."""
    if "$(" in command or "`" in command or "\n" in command.strip():
        return False
    for fd, target in redirects(command):
        if target not in (("&1", "/dev/null") if fd == "2" else ("&1", "&2", "/dev/null")):
            return False  # a redirect into a file: a denial would drop the write
    if "<(" in _unquoted(command) or ">(" in _unquoted(command):
        return False
    parts = _split_command(command)
    for index, (text, piped, sep) in enumerate(parts):
        tokens = _tokens(text.strip())
        if not tokens:
            return False
        if index and sep != "|":
            return False
        program = tokens[0].rsplit("/", 1)[-1]
        if index == 0:
            if program not in GREP_COMMANDS and program != "find":
                return False
        elif program not in OUTPUT_FILTERS:
            return False
        if index and program == "sort" and any(
                t == "--output" or t.startswith("--output=") or (re.match(r"^-[^-]", t) and "o" in t)
                for t in tokens[1:]):
            return False  # `sort -o FILE` writes a file
        if index and program == "uniq" and len([t for t in tokens[1:] if not t.startswith("-")]) > 1:
            return False  # `uniq IN OUT` writes OUT
        if any(t in ("-exec", "-execdir", "-ok", "-delete") for t in tokens):
            return False
    return True


# --------------------------------------------------------------- the index


def _query(repo: Path, args: List[str]) -> Optional[Dict]:
    run_py = Path(__file__).resolve().parent.parent / "run.py"
    try:
        proc = subprocess.run(
            [sys.executable, str(run_py), "query"] + args + ["--repo", str(repo), "--json", "--view", "detail"],
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
    """Definitions and uses of exactly `term`, or None when the index cannot stand
    in for a grep: no such symbol (a substring match is not an answer to a grep
    for a name), or no recorded use at all -- the index may simply not see the
    callers (reflection, config, strings, an unindexed language), and an answer
    that says "defined here" to a who-uses-this question is wrong, not short."""
    data = _query(repo, ["symbol", term, "--budget", "40"])
    entries = [e for e in (data or {}).get("found", []) if _last_name(e["fqn"]) == term]
    if not entries or not any(e.get("used_by_count", len(e.get("used_by") or [])) for e in entries):
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


def file_answer(repo: Path, term: str, glob: Optional[str] = None) -> Optional[str]:
    """Files whose name is `term` (with or without an extension), or, given the
    `find -name` glob, every file the glob matches."""
    data = _query(repo, ["file", term, "--budget", "100"])
    found = (data or {}).get("found", [])
    if glob:
        hits = [f for f in found if fnmatch.fnmatchcase(Path(f["path"]).name, glob)]
    else:
        hits = [f for f in found
                if Path(f["path"]).stem == Path(term).stem or Path(f["path"]).name == term]
    if not hits:
        return None
    return "files named %s\n%s" % (glob or term, "\n".join(
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
    """The index's answer to a set of searches, or None. All or nothing: a search
    with any part the index cannot answer (a plain word, a regex, a name it does not
    know, more terms than fit) runs as written, so a partial answer is never
    presented as the whole one."""
    if not searches or any(not s.get("complete") for s in searches):
        return None
    if sum(len(s["terms"]) for s in searches) > MAX_TERMS:
        return None
    blocks: List[str] = []
    for search in searches:
        for index, term in enumerate(search["terms"]):
            if search["kind"] == "find":
                glob = (search.get("globs") or [None] * (index + 1))[index]
                block = file_answer(repo, term, glob)
            else:
                block = symbol_answer(repo, term)
            if not block:
                return None
            blocks.append(block)
    return "\n".join(blocks)


def empty_search_hint(repo: Path, searches: List[Dict]) -> Optional[str]:
    """For a search that found nothing: what the index knows about its terms, as a
    pointer to `cdp_query`. None when it knows none of them."""
    known: List[str] = []
    for search in searches:
        for term in search["terms"][:2]:
            if search["kind"] == "find":
                hit = file_answer(repo, term)
                if hit:
                    known.append("a file named `%s` is indexed (`cdp_query` kind `file`, term `%s`)" % (
                        term, term))
                continue
            data = _query(repo, ["symbol", term, "--budget", "10"])
            exact = [e for e in (data or {}).get("found", []) if _last_name(e["fqn"]) == term]
            if exact:
                where = _group_ranges(exact[0].get("defined_range") or exact[0].get("defined_at") or [])
                known.append("`%s` is indexed, defined at %s (`cdp_query` kind `symbol`, term `%s` "
                             "gives its definition and callers; kind `trace` follows the call chain)"
                             % (term, where or "?", term))
            else:
                near = list(dict.fromkeys(_last_name(e["fqn"]) for e in (data or {}).get("found", []))) \
                    or ((data or {}).get("not_found") or {}).get("did_you_mean") or []
                if near:
                    known.append("no symbol `%s`; the index has %s (`cdp_query` kind `symbol`)" % (
                        term, ", ".join("`%s`" % n for n in near[:3])))
    return "; ".join(known) if known else None


def silent_by_design(command: str) -> bool:
    """Whether a shell line prints nothing on success: `grep -q`, or output sent to a file
    or `/dev/null`. Its empty stdout says nothing about whether anything matched."""
    if any(fd in ("", "1", "&") and target not in ("&2",) for fd, target in redirects(command)):
        return True
    for part, _piped, _sep in _split_command(command):
        tokens = _tokens(part.strip())
        if tokens and tokens[0].rsplit("/", 1)[-1] in GREP_COMMANDS:
            for token in tokens[1:]:
                if token in ("--quiet", "--silent") or (re.match(r"^-[^-]", token) and "q" in token):
                    return True
    return False


def is_empty_result(tool_name: str, response: object, tool_input: Optional[Dict] = None) -> bool:
    """Whether a PostToolUse `tool_response` says the search found nothing.

    Shapes seen live (Claude Code 2.1.296): Bash gives `{"stdout": "", "stderr": "",
    "returnCodeInterpretation": "No matches found"}` for a grep that matched nothing
    (a `PostToolUse`, not a failure). Grep/Glob results are tolerated in the shapes
    they are documented to take: file/line counts of 0, or empty content/filenames."""
    if isinstance(response, str):
        text = response.strip().lower()
        return not text or text.startswith(("no matches", "no files found"))
    if not isinstance(response, dict):
        return False
    if tool_name == "Bash":
        interp = str(response.get("returnCodeInterpretation") or "").lower()
        silent = not str(response.get("stdout") or "").strip() and not str(response.get("stderr") or "").strip()
        command = (tool_input or {}).get("command")
        if isinstance(command, str) and silent_by_design(command):
            return False
        return silent and "no match" in interp
    counts = [response[k] for k in ("numFiles", "numLines", "numMatches") if k in response]
    if counts:
        return all(c == 0 for c in counts)
    texts = [response[k] for k in ("content", "filenames", "files", "matches") if k in response]
    return bool(texts) and not any(texts)
