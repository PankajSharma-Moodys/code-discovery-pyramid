"""Name the one `cdp_query` call a prompt or a search needs.

Two hooks share it. UserPromptSubmit reads the user's question and says which kind answers it,
with the call spelled out; PreToolUse reads the Grep/Glob/Read/Bash-grep the model reached for
and says which call replaces *that* pattern. Generic "use the index" text is read once and then
ignored; a concrete call for the question in front of the model is not. Kinds come from
`guide_kinds.KINDS`, so a kind that does not exist (yet) is never named: `jobs` falls back to
`search`. Everything here fails open: no match is `None`, and the caller stays silent.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

from . import hook_rules
from .guide_kinds import KINDS

_NAME = re.compile(r"[A-Za-z_$][A-Za-z0-9_$]*(?:\.[A-Za-z_$][A-Za-z0-9_$]*)*")
_ROUTE = re.compile(r"(?<![\w.])/[\w{}\-.]+(?:/[\w{}\-.:]+)+")
_UPPER_KEY = re.compile(r"\b[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+\b|\b[a-z][\w-]*(?:\.[a-z][\w-]*)+\b")
_QUOTED = re.compile(r"[\"'`]([^\"'`]{2,60})[\"'`]")
_STOP = frozenset("""What Which Where Who How Why When Does This That These Those The Are Show List Find Tell Explain
Give Can Could Would Should Please Quartz HTTP HTTPS REST API URL SQL JSON YAML POST GET PUT PATCH DELETE
README TODO NOTE""".split())

# Intent rules, most specific first. Each: (name, regex over the lowercased prompt).
_INTENTS: List[Tuple[str, "re.Pattern[str]"]] = [
    ("jobs", re.compile(r"\b(jobs?|scheduled|schedul\w*|cron\w*|quartz|background (?:task|worker|process)\w*|periodic\w*|timers?)\b")),
    ("constant", re.compile(r"\b(string|constant|literal|magic (?:value|string)|hard-?coded)\b")),
    ("callers", re.compile(r"\b(who|what) (calls?|uses?|invokes?|references?)\b|\bcallers? of\b|\b(used|called|referenced) by\b|"
                           r"\busages? of\b|\bwhere (?:is|are) .{1,60}?\b(called|used|referenced|invoked)\b|\bfind (?:all )?(?:the )?(?:callers|usages)\b")),
    ("config", re.compile(r"\b(config\w*|env(?:ironment)?(?: var\w*| variable\w*)?|settings?|propert(?:y|ies)|feature flags?)\b")),
    ("table", re.compile(r"\b(tables?|database|db|schemas?|persist\w*|migrations?)\b")),
    ("impact", re.compile(r"\b(what breaks|break\w*|impact|blast radius|if i (?:change|rename|remove|delete|modify)|"
                          r"how does .{1,80}?(?:work|flow)|flow|walk me through|trace|explain|end[- ]to[- ]end|lifecycle)\b")),
    ("routes", re.compile(r"\b(endpoints?|routes?|apis?|http|rest|controllers?|resources?)\b")),
]


def _has(kind: str) -> bool:
    return kind in KINDS


def _call(repo: str, kind: str, term: Optional[str] = None) -> str:
    return 'cdp_query(repo="%s", kind="%s"%s)' % (repo, kind, ', term="%s"' % term if term else "")


def _identifier(text: str) -> Optional[str]:
    """The first name in `text` that looks like code: `Foo.bar` -> `bar`, `FooService` -> itself."""
    for match in _NAME.finditer(text):
        token = match.group(0)
        if "." in token:
            parts = [p for p in token.split(".") if p]
            token = parts[-1] if len(parts[-1]) > 2 else parts[0]
        if token in _STOP or len(token) < 4:
            continue
        if hook_rules.is_identifier_like(token) and not token.isupper() or "_" in token:
            return token
    return None


def prompt_intent(prompt: str) -> Optional[Tuple[str, str, Optional[str], str]]:
    """`(intent, kind, term, why)` for a user prompt, or None when it is not a code question."""
    text = prompt.strip()
    if len(text) < 8:
        return None
    low = text.lower()
    route = _ROUTE.search(text)
    ident = _identifier(text)
    for name, pattern in _INTENTS:
        if not pattern.search(low):
            continue
        if name == "jobs":
            if _has("jobs"):
                return name, "jobs", None, "every scheduled job and its schedule"
            return name, "search", "Job", "classes named *Job and their schedule (then `symbol`/`file` on one)"
        if name == "callers":
            return name, "symbol", ident, "definition and every caller, cited"
        if name == "config":
            key = _UPPER_KEY.search(text)
            return name, "config", key.group(0) if key else None, "where each config key / env var is read"
        if name == "table":
            if route:
                return name, "trace", route.group(0), "the route's call chain with the persistence edges; then `table` on a table it reaches"
            return name, "table", None, "who owns, writes and reads each table (omit `term` for all)"
        if name == "constant":
            quoted = _QUOTED.search(text)
            return name, "search", quoted.group(1) if quoted else ident, "every file and line mentioning it (then `symbol` for a named constant)"
        if name == "impact":
            return name, "trace", route.group(0) if route else ident, "the reading list for its call chain; `symbol` on a hop shows its callers"
        if name == "routes":
            return name, "routes", None, "every HTTP route with its handler"
    if ident and re.search(r"\b(where|find|show|locate|defined?|definition|implement\w*|what is|how is)\b", low):
        return "symbol", "symbol", ident, "definition and every caller, cited"
    return None


def prompt_hint(prompt: str, repo: str) -> Optional[str]:
    """The UserPromptSubmit text: at most three short lines, silent for a prompt that is not about code."""
    found = prompt_intent(prompt)
    if found is None:
        return None
    _intent, kind, term, why = found
    return ("This repo has a CDP index. For this question: `%s` returns %s, so no grep/find is needed; "
            "then Read only the cited line ranges.\n"
            "If it says nothing is found, check `cdp_query` kind `coverage` before concluding it is absent."
            % (_call(repo, kind, term), why))


# ------------------------------------------------------------ PreToolUse (call-specific)

_JOBS_WORDS = re.compile(r"cron|schedul|quartz|\bjob|@every|trigger|timer|periodic", re.I)
_CONFIG_WORDS = re.compile(r"getenv|getproperty|environ|@value|configproperty|\bconfig|\bsettings?\b|process\.env|os\.environ", re.I)
_ROUTE_WORDS = re.compile(r"@path|@(?:get|post|put|patch|delete|request)mapping|@app\.route|router\.|@route|\bendpoint|\broute", re.I)
_TABLE_WORDS = re.compile(r"\bfrom\s+\w|\bjoin\s+\w|insert\s+into|create\s+table|@table|\bselect\b.*\bfrom\b", re.I)


def _pattern_of(tool: str, tool_input: Dict) -> Tuple[str, str]:
    """`(pattern, scope)` the call searches for, or `("", "")`."""
    if tool in ("Grep", "Glob"):
        return str(tool_input.get("pattern") or ""), str(tool_input.get("glob") or tool_input.get("path") or "")
    if tool == "Bash":
        command = str(tool_input.get("command") or "")
        searches = hook_rules.shell_searches(command, targeted=True)
        for search in searches:
            if search.get("terms"):
                return " ".join(search["terms"]), command
        match = re.search(r"\b(?:e?grep|rg|ag|ack)\b(?:\s+-[\w-]+(?:\s+\d+)?)*\s+(?:'([^']*)'|\"([^\"]*)\"|(\S+))", command)
        if match:
            return next(g for g in match.groups() if g is not None), command
        match = re.search(r"\bfind\b.*-i?name\s+(?:'([^']*)'|\"([^\"]*)\"|(\S+))", command)
        if match:
            return next(g for g in match.groups() if g is not None), command
    return "", ""


def call_hint(tool: str, tool_input: Dict, repo: str, rel: str = "") -> Optional[Tuple[str, str]]:
    """`(subject, text)`: the exact `cdp_query` that replaces this Grep/Glob/Read/Bash-grep, or None."""
    if tool == "Read":
        if not rel or rel == "." or "offset" in tool_input or "limit" in tool_input:
            return None
        return ("file:" + rel, "CDP has this file's members and their callers: `%s` (outline with line numbers); "
                "Read only the member range you need (offset/limit)." % _call(repo, "file", rel))
    pattern, scope = _pattern_of(tool, tool_input)
    if not pattern:
        return None
    if tool == "Glob" or (tool == "Bash" and re.search(r"\bfind\b", scope) and not re.search(r"\bgrep\b", scope)):
        name = re.sub(r"\*+|\.[A-Za-z]{1,5}$|/", " ", pattern).split()
        term = max(name, key=len) if name else ""
        if not term or len(term) < 3:
            return None
        return ("file:" + term, "CDP finds files by name: `%s` lists the matching paths with their roles; use `file` "
                "again with a path for its members." % _call(repo, "file", term))
    if _JOBS_WORDS.search(pattern):
        kind = "jobs" if _has("jobs") else "search"
        term = None if kind == "jobs" else "Job"
        return ("jobs", "Looking for scheduled jobs? `%s` answers this from the index (cited, with schedules where known); "
                "grep only what it does not hold." % _call(repo, kind, term))
    if _ROUTE_WORDS.search(pattern):
        return ("routes", "Every HTTP route and its handler is indexed: `%s`; `trace` on one gives its call chain." % _call(repo, "routes"))
    if _TABLE_WORDS.search(pattern):
        return ("table", "Tables are indexed with who owns, reads and writes them: `%s` (omit `term` for all)." % _call(repo, "table"))
    if _CONFIG_WORDS.search(pattern):
        key = _UPPER_KEY.search(pattern)
        return ("config:" + (key.group(0) if key else ""), "Config keys and the code that reads them are indexed: `%s`."
                % _call(repo, "config", key.group(0) if key else None))
    term = _identifier(pattern)
    if term:
        return ("symbol:" + term, "CDP has `%s` as an indexed name: `%s` returns its definition and every use with file:line, "
                "cheaper than this search." % (term, _call(repo, "symbol", term)))
    plain = re.sub(r"[\\^$.*+?()\[\]{}|]", " ", pattern).split()
    plain = [w for w in plain if len(w) >= 4]
    if plain and tool != "Glob":
        return ("search:" + plain[0], "For free text, `%s` searches the index's names, paths and claims with citations." % _call(repo, "search", plain[0]))
    return None
